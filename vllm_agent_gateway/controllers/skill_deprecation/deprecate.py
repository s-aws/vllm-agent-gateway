"""Approval-gated skill deprecation workflow."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from copy import deepcopy
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus
from vllm_agent_gateway.skills.evals import SKILL_EVALS_PATH, run_skill_eval_catalog
from vllm_agent_gateway.skills.registry import (
    SCHEMA_VERSION,
    SKILL_REGISTRY_PATH,
    SkillRegistryError,
    load_skill_registry,
    read_json_object,
    route_key_namespace,
    selected_skill_capability_route_keys,
    select_skills_for_workflow,
    validate_skill_registry_manifest,
)
from vllm_agent_gateway.skills.scale import build_skill_scale_report


WORKFLOW_ID = "skill.deprecate"
DEFAULT_OUTPUT_DIR = "skill-deprecations"
MIN_REASON_LENGTH = 20
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class SkillDeprecationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "skill_deprecation_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class SkillDeprecationRequest:
    config_root: Path | str = "."
    output_root: Path | str = ".agentic_controller"
    workflow: str = WORKFLOW_ID
    schema_version: int = SCHEMA_VERSION
    skill_id: str | None = None
    replacement_skill_id: str | None = None
    reason: str | None = None
    effective_date: str | None = None
    approval: dict[str, Any] = field(default_factory=dict)
    role_id: str = "architect/default"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        config_root: Path,
        output_root: Path,
    ) -> "SkillDeprecationRequest":
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


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{artifact_timestamp()}.tmp")
    temp_path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    temp_path.replace(path)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def string_field(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SkillDeprecationError(f"{label} must be a non-empty string.")
    return value.strip()


def string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise SkillDeprecationError(f"{label} must be a non-empty list of strings.")
    return list(value)


def validate_approval(approval: Any) -> dict[str, Any]:
    if not isinstance(approval, dict):
        raise SkillDeprecationError(
            "approval must be a JSON object.",
            code="missing_deprecation_approval",
            status=HTTPStatus.BAD_REQUEST,
        )
    if approval.get("status") != "approved_for_skill_deprecation":
        raise SkillDeprecationError(
            "skill.deprecate requires approval.status=approved_for_skill_deprecation.",
            code="missing_deprecation_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    scope = approval.get("scope")
    scopes = set(scope) if isinstance(scope, list) else {scope} if isinstance(scope, str) else set()
    if "skill_deprecation" not in scopes:
        raise SkillDeprecationError(
            "skill.deprecate requires approval.scope=skill_deprecation.",
            code="invalid_deprecation_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    if approval.get("eval_status_update") is not True:
        raise SkillDeprecationError(
            "skill.deprecate requires approval.eval_status_update=true.",
            code="invalid_deprecation_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    if approval.get("runtime_registry_update") is not True:
        raise SkillDeprecationError(
            "skill.deprecate requires approval.runtime_registry_update=true.",
            code="invalid_deprecation_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    approval_refs = string_list(approval.get("approval_refs"), "approval.approval_refs")
    return {
        "status": approval["status"],
        "scope": sorted(scopes),
        "eval_status_update": True,
        "runtime_registry_update": True,
        "approval_refs": approval_refs,
    }


def validate_request(request: SkillDeprecationRequest) -> None:
    if request.workflow != WORKFLOW_ID:
        raise SkillDeprecationError("workflow must be skill.deprecate.", code="unsupported_workflow")
    if request.schema_version != SCHEMA_VERSION:
        raise SkillDeprecationError("schema_version must be 1.", code="unsupported_schema_version")
    string_field(request.skill_id, "skill_id")
    string_field(request.replacement_skill_id, "replacement_skill_id")
    reason = string_field(request.reason, "reason")
    if len(reason) < MIN_REASON_LENGTH:
        raise SkillDeprecationError(
            f"reason must be at least {MIN_REASON_LENGTH} characters.",
            code="invalid_deprecation_reason",
        )
    effective_date = string_field(request.effective_date, "effective_date")
    if not DATE_RE.fullmatch(effective_date):
        raise SkillDeprecationError(
            "effective_date must use YYYY-MM-DD.",
            code="invalid_deprecation_effective_date",
        )
    validate_approval(request.approval)
    if request.metadata is not None and not isinstance(request.metadata, dict):
        raise SkillDeprecationError("metadata must be a JSON object.", code="invalid_metadata")


def raw_skill_map(registry_manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    skills = registry_manifest.get("skills")
    if not isinstance(skills, list):
        raise SkillDeprecationError("runtime/skills.json must contain a skills list.", code="invalid_skill_registry")
    values: dict[str, dict[str, Any]] = {}
    for item in skills:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            values[item["id"]] = item
    return values


def route_compatibility_check(deprecated_skill: dict[str, Any], replacement_skill: dict[str, Any]) -> dict[str, Any]:
    deprecated_contract = deprecated_skill["capability_contract"]
    replacement_contract = replacement_skill["capability_contract"]
    checks = {
        "same_workflows": sorted(deprecated_skill["workflows"]) == sorted(replacement_skill["workflows"]),
        "same_route_namespace": route_key_namespace(deprecated_contract["route_key"])
        == route_key_namespace(replacement_contract["route_key"]),
        "same_safety_level": deprecated_skill["safety_level"] == replacement_skill["safety_level"],
        "same_mutation_policy": deprecated_contract["mutation_policy"] == replacement_contract["mutation_policy"],
        "same_approval_boundary": deprecated_contract["approval_boundary"] == replacement_contract["approval_boundary"],
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "deprecated_route_key": deprecated_contract["route_key"],
        "replacement_route_key": replacement_contract["route_key"],
    }


def validate_deprecation_candidate(
    *,
    config_root: Path,
    skill_id: str,
    replacement_skill_id: str,
) -> dict[str, Any]:
    registry_manifest = read_json_object(config_root / SKILL_REGISTRY_PATH, "skill registry")
    registry = load_skill_registry(config_root)
    raw_skills = raw_skill_map(registry_manifest)
    if skill_id not in raw_skills:
        raise SkillDeprecationError(f"Requested skill is not registered: {skill_id}", code="skill_not_registered")
    if replacement_skill_id not in raw_skills:
        raise SkillDeprecationError(
            f"Replacement skill is not registered: {replacement_skill_id}",
            code="replacement_skill_not_registered",
        )
    if skill_id == replacement_skill_id:
        raise SkillDeprecationError("replacement_skill_id cannot equal skill_id.", code="invalid_replacement_skill")
    if skill_id not in registry:
        raise SkillDeprecationError(f"Requested skill failed registry validation: {skill_id}", code="invalid_skill")
    if replacement_skill_id not in registry:
        raise SkillDeprecationError(
            f"Replacement skill failed registry validation: {replacement_skill_id}",
            code="invalid_replacement_skill",
        )
    if raw_skills[skill_id].get("eval_status") == "deprecated":
        raise SkillDeprecationError(f"Skill is already deprecated: {skill_id}", code="skill_already_deprecated")
    if raw_skills[replacement_skill_id].get("eval_status") == "deprecated":
        raise SkillDeprecationError(
            f"Replacement skill is deprecated: {replacement_skill_id}",
            code="replacement_skill_deprecated",
        )
    compatibility = route_compatibility_check(registry[skill_id], registry[replacement_skill_id])
    if compatibility["status"] != "passed":
        raise SkillDeprecationError(
            "Replacement skill is not route-compatible with the deprecated skill.",
            code="replacement_route_incompatible",
        )
    return {
        "registry_manifest": registry_manifest,
        "registry": registry,
        "raw_skills": raw_skills,
        "route_compatibility": compatibility,
    }


def restore_backup(*, registry_path: Path, registry_backup: Path) -> None:
    shutil.copy2(registry_backup, registry_path)


def deprecate_runtime_registry(
    *,
    config_root: Path,
    registry_manifest: dict[str, Any],
    skill_id: str,
    replacement_skill_id: str,
    reason: str,
    effective_date: str,
    run_dir: Path,
) -> dict[str, Any]:
    registry_path = config_root / SKILL_REGISTRY_PATH
    eval_path = config_root / SKILL_EVALS_PATH
    backup_dir = run_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    registry_backup = backup_dir / "skills.before.json"
    shutil.copy2(registry_path, registry_backup)
    before_hashes = {
        "runtime/skills.json": sha256_file(registry_path),
        "runtime/skill_evals.json": sha256_file(eval_path),
    }

    updated = deepcopy(registry_manifest)
    mutated_count = 0
    for item in updated["skills"]:
        if not isinstance(item, dict) or item.get("id") != skill_id:
            continue
        item["eval_status"] = "deprecated"
        item["deprecation"] = {
            "replaced_by": replacement_skill_id,
            "reason": reason,
            "effective_date": effective_date,
        }
        mutated_count += 1
    if mutated_count != 1:
        raise SkillDeprecationError(
            f"Deprecation expected to update exactly one skill, updated {mutated_count}.",
            code="unexpected_deprecation_mutation_count",
        )

    try:
        atomic_write_json(registry_path, updated)
        validate_skill_registry_manifest(read_json_object(registry_path, "skill registry"), config_root)
    except (OSError, SkillRegistryError) as exc:
        restore_backup(registry_path=registry_path, registry_backup=registry_backup)
        raise SkillDeprecationError(
            f"Skill deprecation failed and runtime/skills.json was restored: {exc}",
            code="deprecation_rollback_completed",
        ) from exc

    after_hashes = {
        "runtime/skills.json": sha256_file(registry_path),
        "runtime/skill_evals.json": sha256_file(eval_path),
    }
    return {
        "backup_paths": {"runtime/skills.json": str(registry_backup)},
        "before_hashes": before_hashes,
        "after_hashes": after_hashes,
        "mutated_skill_count": mutated_count,
    }


def rollback_instructions(deprecation_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "skill_deprecation_rollback_instructions",
        "schema_version": SCHEMA_VERSION,
        "restore_backups": deprecation_result["backup_paths"],
        "note": "Restore runtime/skills.json from the recorded backup if this deprecation must be reverted. "
        "Skill body files and runtime/skill_evals.json are not changed by skill.deprecate.",
    }


def selector_exclusion_proof(
    registry: dict[str, dict[str, Any]],
    *,
    skill_id: str,
    replacement_skill_id: str,
) -> dict[str, Any]:
    skill = registry[skill_id]
    replacement = registry[replacement_skill_id]
    workflow_id = skill["workflows"][0]
    query_text = " ".join(skill["triggers"])
    selected = select_skills_for_workflow(registry, workflow_id, query_text=query_text, limit=10)
    return {
        "workflow_id": workflow_id,
        "query_text": query_text,
        "deprecated_skill_selected": skill_id in selected,
        "replacement_skill_selected": replacement_skill_id in selected,
        "selected_skill_ids": selected,
        "selected_route_keys": selected_skill_capability_route_keys(registry, selected),
        "deprecated_route_key": skill["capability_contract"]["route_key"],
        "replacement_route_key": replacement["capability_contract"]["route_key"],
    }


def invoke_skill_deprecation(request: SkillDeprecationRequest) -> InvocationResult:
    validate_request(request)
    output_root = Path(request.output_root).resolve()
    config_root = Path(request.config_root).resolve()
    run_id = f"skill-deprecation-{artifact_timestamp()}"
    run_dir = output_root / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    assert request.skill_id is not None
    assert request.replacement_skill_id is not None
    assert request.reason is not None
    assert request.effective_date is not None

    artifacts: dict[str, str] = {}
    approval = validate_approval(request.approval)
    skill_id = string_field(request.skill_id, "skill_id")
    replacement_skill_id = string_field(request.replacement_skill_id, "replacement_skill_id")
    reason = string_field(request.reason, "reason")
    effective_date = string_field(request.effective_date, "effective_date")
    request_artifact = {
        "kind": "skill_deprecation_request",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "skill_id": skill_id,
        "replacement_skill_id": replacement_skill_id,
        "reason": reason,
        "effective_date": effective_date,
        "approval": approval,
        "metadata": request.metadata,
        "created_at": utc_now(),
    }
    write_json(run_dir / "request.json", request_artifact)
    artifacts["request"] = str(run_dir / "request.json")

    validation = validate_deprecation_candidate(
        config_root=config_root,
        skill_id=skill_id,
        replacement_skill_id=replacement_skill_id,
    )
    deprecation_plan = {
        "kind": "skill_deprecation_plan",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "skill_id": skill_id,
        "replacement_skill_id": replacement_skill_id,
        "route_compatibility": validation["route_compatibility"],
        "status": "passed",
        "target_repository_changed": False,
        "skill_body_delete_allowed": False,
        "created_at": utc_now(),
    }
    write_json(run_dir / "skill-deprecation-plan.json", deprecation_plan)
    artifacts["skill_deprecation_plan"] = str(run_dir / "skill-deprecation-plan.json")

    pre_eval_report = run_skill_eval_catalog(config_root, output_path=run_dir / "skill-eval-report-before-deprecation.json")
    artifacts["skill_eval_report_before"] = str(run_dir / "skill-eval-report-before-deprecation.json")
    pre_scale_report = build_skill_scale_report(config_root, output_path=run_dir / "scale-report-before-deprecation.json")
    artifacts["scale_report_before"] = str(run_dir / "scale-report-before-deprecation.json")
    if pre_eval_report["status"] != "passed":
        raise SkillDeprecationError("Skill eval catalog failed before deprecation.", code="deprecation_eval_failed")
    if pre_scale_report["status"] != "passed":
        raise SkillDeprecationError("Skill scale report failed before deprecation.", code="deprecation_scale_failed")

    deprecation_result = deprecate_runtime_registry(
        config_root=config_root,
        registry_manifest=validation["registry_manifest"],
        skill_id=skill_id,
        replacement_skill_id=replacement_skill_id,
        reason=reason,
        effective_date=effective_date,
        run_dir=run_dir,
    )
    post_eval_report = run_skill_eval_catalog(config_root, output_path=run_dir / "skill-eval-report-after-deprecation.json")
    artifacts["skill_eval_report_after"] = str(run_dir / "skill-eval-report-after-deprecation.json")
    post_scale_report = build_skill_scale_report(config_root, output_path=run_dir / "scale-report-after-deprecation.json")
    artifacts["scale_report_after"] = str(run_dir / "scale-report-after-deprecation.json")
    if post_eval_report["status"] != "passed" or post_scale_report["status"] != "passed":
        restore_backup(
            registry_path=config_root / SKILL_REGISTRY_PATH,
            registry_backup=Path(deprecation_result["backup_paths"]["runtime/skills.json"]),
        )
        raise SkillDeprecationError(
            "Post-deprecation validation failed and runtime/skills.json was restored.",
            code="deprecation_rollback_completed",
        )

    post_registry = load_skill_registry(config_root)
    selector_proof = selector_exclusion_proof(
        post_registry,
        skill_id=skill_id,
        replacement_skill_id=replacement_skill_id,
    )
    if selector_proof["deprecated_skill_selected"]:
        restore_backup(
            registry_path=config_root / SKILL_REGISTRY_PATH,
            registry_backup=Path(deprecation_result["backup_paths"]["runtime/skills.json"]),
        )
        raise SkillDeprecationError(
            "Post-deprecation selector still selected the deprecated skill; runtime/skills.json was restored.",
            code="deprecated_skill_still_selected",
        )

    rollback = rollback_instructions(deprecation_result)
    write_json(run_dir / "rollback-instructions.json", rollback)
    artifacts["rollback_instructions"] = str(run_dir / "rollback-instructions.json")

    hash_proof = {
        "before": deprecation_result["before_hashes"],
        "after": deprecation_result["after_hashes"],
        "changed": sorted(
            key
            for key, after_hash in deprecation_result["after_hashes"].items()
            if deprecation_result["before_hashes"].get(key) != after_hash
        ),
    }
    changed_runtime_files = [item for item in hash_proof["changed"] if item.startswith("runtime/")]
    if changed_runtime_files != ["runtime/skills.json"]:
        restore_backup(
            registry_path=config_root / SKILL_REGISTRY_PATH,
            registry_backup=Path(deprecation_result["backup_paths"]["runtime/skills.json"]),
        )
        raise SkillDeprecationError(
            "skill.deprecate attempted to mutate files outside runtime/skills.json; runtime/skills.json was restored.",
            code="unexpected_deprecation_mutation",
        )

    summary = {
        "deprecation_status": "deprecated",
        "skill_id": skill_id,
        "replacement_skill_id": replacement_skill_id,
        "metadata_eval_status": post_eval_report["status"],
        "scale_report_status": post_scale_report["status"],
        "runtime_registry_changed": True,
        "changed_runtime_files": changed_runtime_files,
        "mutated_skill_count": deprecation_result["mutated_skill_count"],
        "target_repository_changed": False,
        "skill_body_deleted": False,
        "selector_excludes_deprecated_skill": not selector_proof["deprecated_skill_selected"],
        "next_action": "run_lifecycle_audit_or_restore_backup_if_needed",
    }
    deprecation = {
        "kind": "skill_deprecation",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": "deprecated",
        "summary": summary,
        "approval": approval,
        "deprecation": {
            "skill_id": skill_id,
            "replaced_by": replacement_skill_id,
            "reason": reason,
            "effective_date": effective_date,
        },
        "deprecation_plan": deprecation_plan,
        "selector_exclusion_proof": selector_proof,
        "hash_proof": hash_proof,
        "rollback_instructions": rollback,
        "created_at": utc_now(),
    }
    write_json(run_dir / "skill-deprecation.json", deprecation)
    artifacts["skill_deprecation"] = str(run_dir / "skill-deprecation.json")

    run_state = {
        "kind": "skill_deprecation_run_state",
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
        "kind": "skill_deprecation_report",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "summary": summary,
        "deprecation": deprecation,
        "warnings": [],
        "artifacts": artifacts,
    }
    return InvocationResult(
        workflow=WORKFLOW_ID,
        status=WorkflowStatus.COMPLETED,
        artifact_paths=artifacts,
        summary_text=f"{WORKFLOW_ID} completed with deprecation_status=deprecated",
        failures=[],
        resume_key={"schema_version": SCHEMA_VERSION, "run_state": str(run_dir / "run-state.json")},
        report=report,
        run_id=run_id,
    )
