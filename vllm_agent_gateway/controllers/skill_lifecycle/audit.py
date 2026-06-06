"""Read-only skill lifecycle audit workflow."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus
from vllm_agent_gateway.skills.evals import (
    MANUAL_ARTIFACT_IDS,
    SKILL_EVALS_PATH,
    build_skill_eval_report,
    live_mapping_for_case,
    skill_output_artifacts,
    workflow_result_artifacts,
)
from vllm_agent_gateway.skills.registry import (
    SCHEMA_VERSION,
    SKILL_REGISTRY_PATH,
    SkillRegistryError,
    load_skill_registry,
    read_json_object,
    semantic_intent_conflicts,
)
from vllm_agent_gateway.skills.scale import build_skill_scale_report


WORKFLOW_ID = "skill_lifecycle.audit"
DEFAULT_OUTPUT_DIR = "skill-lifecycle-audits"
PROMOTION_EVAL_FIELDS = ("localhost_8000", "gateway_8300", "anythingllm")
ORDERED_STATUSES = ("draft", "validated", "deprecated", "unknown")
ORDERED_ACTIONS = ("promote", "keep_draft", "revise", "deprecate", "no_action")


class SkillLifecycleAuditError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "skill_lifecycle_audit_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class SkillLifecycleAuditRequest:
    config_root: Path | str = "."
    output_root: Path | str = ".agentic_controller"
    workflow: str = WORKFLOW_ID
    schema_version: int = SCHEMA_VERSION
    skill_ids: list[str] | None = None
    role_id: str = "architect/default"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        config_root: Path,
        output_root: Path,
    ) -> "SkillLifecycleAuditRequest":
        values: dict[str, Any] = {
            "config_root": config_root,
            "output_root": output_root,
        }
        names = {item.name for item in fields(cls)}
        for key, value in payload.items():
            if key in names:
                values[key] = value
        return cls(**values)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def artifact_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def write_json(path: Path, value: dict[str, Any], *, sort_keys: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=sort_keys) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise SkillLifecycleAuditError(f"{label} must be a non-empty list of strings.")
    return list(value)


def validate_request(request: SkillLifecycleAuditRequest) -> None:
    if request.workflow != WORKFLOW_ID:
        raise SkillLifecycleAuditError("workflow must be skill_lifecycle.audit.", code="unsupported_workflow")
    if request.schema_version != SCHEMA_VERSION:
        raise SkillLifecycleAuditError("schema_version must be 1.", code="unsupported_schema_version")
    if request.skill_ids is not None:
        string_list(request.skill_ids, "skill_ids")
    if request.metadata is not None and not isinstance(request.metadata, dict):
        raise SkillLifecycleAuditError("metadata must be a JSON object.", code="invalid_metadata")


def load_raw_registry(config_root: Path) -> dict[str, Any]:
    registry = read_json_object(config_root / SKILL_REGISTRY_PATH, "skill registry")
    skills = registry.get("skills")
    if not isinstance(skills, list):
        raise SkillLifecycleAuditError("runtime/skills.json must contain a skills list.", code="invalid_skill_registry")
    return registry


def load_raw_eval_cases(config_root: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json_object(config_root / SKILL_EVALS_PATH, "skill eval catalog")
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise SkillLifecycleAuditError("runtime/skill_evals.json must contain a cases list.", code="invalid_skill_evals")
    values: dict[str, dict[str, Any]] = {}
    for item in cases:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            values[item["id"]] = item
    return values


def raw_skills_by_id(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for item in registry.get("skills", []):
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            values[item["id"]] = item
    return values


def selected_raw_skills(registry: dict[str, Any], requested_ids: list[str] | None) -> list[dict[str, Any]]:
    skills = [item for item in registry.get("skills", []) if isinstance(item, dict)]
    if not requested_ids:
        return skills
    requested = set(requested_ids)
    return [item for item in skills if item.get("id") in requested]


def known_artifacts(config_root: Path, validated_registry: dict[str, dict[str, Any]] | None, raw_skills: list[dict[str, Any]]) -> set[str]:
    artifacts: set[str] = set(MANUAL_ARTIFACT_IDS)
    try:
        workflows_manifest = read_json_object(config_root / "runtime" / "workflows.json", "workflow registry")
        artifacts.update(workflow_result_artifacts(workflows_manifest))
    except (OSError, SkillRegistryError):
        pass
    if validated_registry is not None:
        artifacts.update(skill_output_artifacts(validated_registry))
    for skill in raw_skills:
        contract = skill.get("capability_contract") if isinstance(skill.get("capability_contract"), dict) else {}
        outputs = contract.get("output_artifacts")
        if isinstance(outputs, list):
            artifacts.update(item for item in outputs if isinstance(item, str))
    return artifacts


def doc_ref_exists(config_root: Path, ref: str) -> bool:
    path_text = ref.split("#", 1)[0]
    if not path_text:
        return False
    return (config_root / path_text).is_file()


def route_key_conflicts(raw_skills: list[dict[str, Any]]) -> dict[str, list[str]]:
    by_route: dict[str, list[str]] = {}
    for skill in raw_skills:
        contract = skill.get("capability_contract") if isinstance(skill.get("capability_contract"), dict) else {}
        route_key = contract.get("route_key")
        skill_id = skill.get("id")
        if isinstance(route_key, str) and isinstance(skill_id, str):
            by_route.setdefault(route_key, []).append(skill_id)
    return {route_key: ids for route_key, ids in by_route.items() if len(ids) > 1}


def semantic_conflict_actions(raw_skills: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], set[str]]:
    candidates = {
        skill["id"]: skill
        for skill in raw_skills
        if isinstance(skill.get("id"), str)
        and isinstance(skill.get("workflows"), list)
        and isinstance(skill.get("triggers"), list)
        and isinstance(skill.get("capability_contract"), dict)
    }
    try:
        conflicts = semantic_intent_conflicts(candidates)
    except (KeyError, TypeError):
        return [], set()
    deprecate_ids: set[str] = set()
    for conflict in conflicts:
        skill_ids = conflict.get("skill_ids") if isinstance(conflict.get("skill_ids"), list) else []
        valid_ids = sorted(item for item in skill_ids if isinstance(item, str))
        if len(valid_ids) >= 2:
            deprecate_ids.add(valid_ids[-1])
    return conflicts, deprecate_ids


def eval_fields_passed(skill: dict[str, Any]) -> bool:
    evals = skill.get("evals")
    if not isinstance(evals, dict):
        return False
    return all(evals.get(field) == "passed" for field in PROMOTION_EVAL_FIELDS)


def skill_eval_case_ids(skill: dict[str, Any]) -> list[str]:
    contract = skill.get("capability_contract") if isinstance(skill.get("capability_contract"), dict) else {}
    case_ids = contract.get("eval_case_ids")
    return [item for item in case_ids if isinstance(item, str)] if isinstance(case_ids, list) else []


def blocked_by_codes(blockers: list[dict[str, Any]]) -> set[str]:
    return {item["code"] for item in blockers if isinstance(item.get("code"), str)}


def lifecycle_action(
    *,
    eval_status: str,
    blockers: list[dict[str, Any]],
    deprecate_candidate: bool,
) -> str:
    codes = blocked_by_codes(blockers)
    structural_codes = {
        "missing_skill_body",
        "missing_eval_case",
        "missing_live_mapping",
        "missing_failure_record_refs",
        "missing_doc_ref",
        "route_key_conflict",
        "unknown_expected_artifact",
        "deprecated_contract_invalid",
        "registry_validation_error",
    }
    if deprecate_candidate and eval_status == "validated":
        return "deprecate"
    if eval_status == "deprecated":
        return "revise" if codes & structural_codes else "no_action"
    if codes & structural_codes:
        return "revise"
    if eval_status == "draft":
        return "keep_draft" if "missing_live_proof" in codes or "stale_eval_status_fields" in codes else "promote"
    if eval_status == "validated":
        return "revise" if "stale_eval_status_fields" in codes else "no_action"
    return "revise"


def skill_lifecycle_record(
    *,
    config_root: Path,
    skill: dict[str, Any],
    eval_cases: dict[str, dict[str, Any]],
    known_output_artifacts: set[str],
    route_conflicts: dict[str, list[str]],
    deprecate_ids: set[str],
    registry_validation_error: str | None,
) -> dict[str, Any]:
    skill_id = str(skill.get("id", "<unknown>"))
    eval_status = skill.get("eval_status") if isinstance(skill.get("eval_status"), str) else "unknown"
    if eval_status not in ORDERED_STATUSES:
        eval_status = "unknown"
    blockers: list[dict[str, Any]] = []
    path_value = skill.get("path")
    if not isinstance(path_value, str) or not path_value.strip() or not (config_root / path_value).is_file():
        blockers.append({"code": "missing_skill_body", "message": "skill body path is missing or unreadable"})
    refs = skill.get("failure_record_refs")
    if not isinstance(refs, list) or not refs:
        blockers.append({"code": "missing_failure_record_refs", "message": "failure_record_refs is missing or empty"})
    else:
        missing_refs = [ref for ref in refs if isinstance(ref, str) and not doc_ref_exists(config_root, ref)]
        if missing_refs:
            blockers.append(
                {
                    "code": "missing_doc_ref",
                    "message": "failure_record_refs contains missing documentation path(s)",
                    "refs": missing_refs,
                }
            )
    contract = skill.get("capability_contract") if isinstance(skill.get("capability_contract"), dict) else {}
    route_key = contract.get("route_key")
    if isinstance(route_key, str) and route_key in route_conflicts:
        blockers.append(
            {
                "code": "route_key_conflict",
                "message": "route key is shared by multiple skills",
                "route_key": route_key,
                "skill_ids": route_conflicts[route_key],
            }
        )
    eval_case_ids = skill_eval_case_ids(skill)
    live_mappings: list[dict[str, Any]] = []
    missing_live_proof = False
    for case_id in eval_case_ids:
        case = eval_cases.get(case_id)
        if case is None:
            blockers.append({"code": "missing_eval_case", "message": f"missing eval case {case_id}", "eval_case_id": case_id})
            continue
        expected_artifacts = case.get("expected_artifacts")
        if isinstance(expected_artifacts, list):
            unknown_artifacts = sorted(item for item in expected_artifacts if isinstance(item, str) and item not in known_output_artifacts)
            if unknown_artifacts:
                blockers.append(
                    {
                        "code": "unknown_expected_artifact",
                        "message": f"eval case {case_id} references unknown expected artifact(s)",
                        "eval_case_id": case_id,
                        "expected_artifacts": unknown_artifacts,
                    }
                )
        try:
            mapping = live_mapping_for_case(case)
        except (KeyError, TypeError):
            mapping = {"status": "not_mapped", "live_suite": case.get("live_suite"), "reason": "invalid eval case"}
        if mapping.get("status") == "not_mapped" and eval_fields_passed(skill):
            mapping = {
                **mapping,
                "status": "suite_level_proof",
                "reason": "case has suite-level proof fields even though it is not mapped to an L1/L2 case id",
            }
        live_mappings.append({"eval_case_id": case_id, **mapping})
        if mapping.get("status") == "not_mapped":
            blockers.append(
                {
                    "code": "missing_live_mapping",
                    "message": f"eval case {case_id} is not mapped to an approved live proof path",
                    "eval_case_id": case_id,
                    "live_suite": mapping.get("live_suite"),
                }
            )
        elif mapping.get("status") == "mapped" and not eval_fields_passed(skill):
            missing_live_proof = True
    if missing_live_proof:
        blockers.append(
            {
                "code": "missing_live_proof",
                "message": "mapped live-suite case requires localhost, gateway, and AnythingLLM proof",
                "required_eval_fields": list(PROMOTION_EVAL_FIELDS),
            }
        )
    if eval_status == "validated" and not eval_fields_passed(skill):
        blockers.append(
            {
                "code": "stale_eval_status_fields",
                "message": "validated skill does not have all promotion eval fields marked passed",
                "required_eval_fields": list(PROMOTION_EVAL_FIELDS),
            }
        )
    if eval_status == "deprecated":
        deprecation = skill.get("deprecation")
        if not isinstance(deprecation, dict):
            blockers.append({"code": "deprecated_contract_invalid", "message": "deprecated skill is missing deprecation metadata"})
    if registry_validation_error is not None:
        blockers.append({"code": "registry_validation_error", "message": registry_validation_error})
    action = lifecycle_action(
        eval_status=eval_status,
        blockers=blockers,
        deprecate_candidate=skill_id in deprecate_ids,
    )
    return {
        "skill_id": skill_id,
        "eval_status": eval_status,
        "action": action,
        "route_key": route_key,
        "eval_case_ids": eval_case_ids,
        "live_mappings": live_mappings,
        "blockers": blockers,
    }


def queue_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    return {action: sum(1 for item in records if item["action"] == action) for action in ORDERED_ACTIONS}


def grouped_skill_ids(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        status: sorted(item["skill_id"] for item in records if item["eval_status"] == status)
        for status in ORDERED_STATUSES
    }


def referenced_eval_case_ids(raw_skills: list[dict[str, Any]]) -> set[str]:
    values: set[str] = set()
    for skill in raw_skills:
        values.update(skill_eval_case_ids(skill))
    return values


def audit_status(records: list[dict[str, Any]], registry_errors: list[str], orphan_eval_cases: list[str]) -> str:
    if registry_errors or orphan_eval_cases:
        return "blocked"
    actions = {item["action"] for item in records}
    if "revise" in actions or "deprecate" in actions:
        return "blocked"
    if "promote" in actions or "keep_draft" in actions:
        return "action_required"
    return "passed"


def build_lifecycle_audit(
    config_root: Path,
    *,
    output_path: Path,
    skill_ids: list[str] | None = None,
    eval_report: dict[str, Any] | None = None,
    scale_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config_root = config_root.resolve()
    registry_path = config_root / SKILL_REGISTRY_PATH
    eval_path = config_root / SKILL_EVALS_PATH
    before_hashes = {
        "runtime/skills.json": sha256_file(registry_path),
        "runtime/skill_evals.json": sha256_file(eval_path),
    }
    raw_registry = load_raw_registry(config_root)
    raw_eval_cases = load_raw_eval_cases(config_root)
    requested_skill_ids = sorted(set(skill_ids or []))
    raw_skill_items = selected_raw_skills(raw_registry, requested_skill_ids or None)
    raw_all_skills = [item for item in raw_registry.get("skills", []) if isinstance(item, dict)]
    raw_by_id = raw_skills_by_id(raw_registry)
    missing_requested = sorted(set(requested_skill_ids) - set(raw_by_id))
    registry_errors: list[str] = []
    validated_registry: dict[str, dict[str, Any]] | None = None
    try:
        validated_registry = load_skill_registry(config_root)
    except SkillRegistryError as exc:
        registry_errors.append(str(exc))
    route_conflicts = route_key_conflicts(raw_all_skills)
    semantic_conflicts, deprecate_ids = semantic_conflict_actions(raw_all_skills)
    artifacts = known_artifacts(config_root, validated_registry, raw_all_skills)
    registry_validation_error = registry_errors[0] if registry_errors else None
    records = [
        skill_lifecycle_record(
            config_root=config_root,
            skill=skill,
            eval_cases=raw_eval_cases,
            known_output_artifacts=artifacts,
            route_conflicts=route_conflicts,
            deprecate_ids=deprecate_ids,
            registry_validation_error=registry_validation_error,
        )
        for skill in raw_skill_items
    ]
    referenced_cases = referenced_eval_case_ids(raw_all_skills)
    orphan_cases = sorted(set(raw_eval_cases) - referenced_cases)
    for missing in missing_requested:
        records.append(
            {
                "skill_id": missing,
                "eval_status": "unknown",
                "action": "revise",
                "route_key": None,
                "eval_case_ids": [],
                "live_mappings": [],
                "blockers": [{"code": "missing_skill", "message": "requested skill is not registered"}],
            }
        )
    summary = {
        "lifecycle_status": audit_status(records, registry_errors, orphan_cases),
        "skill_count": len(records),
        "status_counts": {status: sum(1 for item in records if item["eval_status"] == status) for status in ORDERED_STATUSES},
        "queue_counts": queue_counts(records),
        "blocker_count": sum(len(item["blockers"]) for item in records),
        "orphan_eval_case_count": len(orphan_cases),
        "route_key_conflict_count": len(route_conflicts),
        "semantic_conflict_count": len(semantic_conflicts),
        "runtime_registry_changed": False,
        "target_repository_changed": False,
        "next_action": "none" if not records else "review_lifecycle_queue",
    }
    after_hashes = {
        "runtime/skills.json": sha256_file(registry_path),
        "runtime/skill_evals.json": sha256_file(eval_path),
    }
    summary["runtime_registry_changed"] = before_hashes != after_hashes
    audit = {
        "kind": "skill_lifecycle_audit",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "status": summary["lifecycle_status"],
        "config_root": str(config_root),
        "summary": summary,
        "groups": grouped_skill_ids(records),
        "action_queue": sorted(records, key=lambda item: (ORDERED_ACTIONS.index(item["action"]), item["skill_id"])),
        "catalog_findings": {
            "orphan_eval_cases": orphan_cases,
            "missing_requested_skill_ids": missing_requested,
            "route_key_conflicts": route_conflicts,
            "semantic_conflicts": semantic_conflicts,
            "registry_validation_errors": registry_errors,
            "eval_report_status": eval_report.get("status") if isinstance(eval_report, dict) else None,
            "scale_report_status": scale_report.get("status") if isinstance(scale_report, dict) else None,
        },
        "hash_proof": {
            "before": before_hashes,
            "after": after_hashes,
            "changed": sorted(key for key, value in after_hashes.items() if before_hashes.get(key) != value),
        },
        "created_at": utc_now(),
    }
    write_json(output_path, audit)
    return audit


def invoke_skill_lifecycle_audit(request: SkillLifecycleAuditRequest) -> InvocationResult:
    validate_request(request)
    output_root = Path(request.output_root).resolve()
    config_root = Path(request.config_root).resolve()
    run_id = f"skill-lifecycle-audit-{artifact_timestamp()}"
    run_dir = output_root / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, str] = {}
    requested_ids = sorted(set(request.skill_ids or []))
    request_artifact = {
        "kind": "skill_lifecycle_audit_request",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "skill_ids": requested_ids,
        "metadata": request.metadata,
        "created_at": utc_now(),
    }
    write_json(run_dir / "request.json", request_artifact)
    artifacts["request"] = str(run_dir / "request.json")

    eval_report = build_skill_eval_report(config_root)
    write_json(run_dir / "skill-eval-report.json", eval_report)
    artifacts["skill_eval_report"] = str(run_dir / "skill-eval-report.json")
    scale_report = build_skill_scale_report(config_root, output_path=run_dir / "scale-report.json")
    artifacts["scale_report"] = str(run_dir / "scale-report.json")
    audit = build_lifecycle_audit(
        config_root,
        output_path=run_dir / "skill-lifecycle-audit.json",
        skill_ids=requested_ids or None,
        eval_report=eval_report,
        scale_report=scale_report,
    )
    audit["run_id"] = run_id
    write_json(run_dir / "skill-lifecycle-audit.json", audit)
    artifacts["skill_lifecycle_audit"] = str(run_dir / "skill-lifecycle-audit.json")

    summary = audit["summary"]
    run_state = {
        "kind": "skill_lifecycle_audit_run_state",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "summary": summary,
        "artifacts": artifacts,
        "updated_at": utc_now(),
    }
    write_json(run_dir / "run-state.json", run_state)
    artifacts["run_state"] = str(run_dir / "run-state.json")

    report = {
        "kind": "skill_lifecycle_audit_report",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "summary": summary,
        "audit": audit,
        "warnings": [],
        "artifacts": artifacts,
    }
    return InvocationResult(
        workflow=WORKFLOW_ID,
        status=WorkflowStatus.COMPLETED,
        artifact_paths=artifacts,
        summary_text=f"{WORKFLOW_ID} completed with lifecycle_status={summary['lifecycle_status']}",
        failures=[],
        resume_key={"schema_version": SCHEMA_VERSION, "run_state": str(run_dir / "run-state.json")},
        report=report,
        run_id=run_id,
    )
