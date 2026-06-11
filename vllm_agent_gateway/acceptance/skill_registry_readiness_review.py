"""Phase 193 skill registry readiness review."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.skills.prompt_coverage import PromptCoverageConfig, validate_prompt_coverage
from vllm_agent_gateway.skills.registry import (
    EVAL_STATUSES,
    MUTATION_POLICIES,
    ROUTE_KEY_NAMESPACES,
    SAFETY_LEVELS,
    SkillRegistryError,
    load_skill_registry,
    normalized_trigger_phrases,
    semantic_intent_conflicts,
)
from vllm_agent_gateway.skills.scale import build_skill_scale_report


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "skill_registry_readiness_review_policy"
EXPECTED_REPORT_KIND = "skill_registry_readiness_review_report"
EXPECTED_PHASE = 193
EXPECTED_BACKLOG_ID = "P0-BB-057"
DEFAULT_POLICY_PATH = Path("runtime") / "skill_registry_readiness_review_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase193" / "phase193-skill-registry-readiness-review-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase193" / "phase193-skill-registry-readiness-review-report.md"
DEFAULT_SCALE_REPORT_PATH = Path("runtime-state") / "phase193" / "phase193-skill-scale-source.json"
DEFAULT_COVERAGE_REPORT_PATH = Path("runtime-state") / "phase193" / "phase193-prompt-skill-coverage-source.json"
DECISIONS = ("keep", "split", "merge", "retire", "defer")
REQUIRED_SKILL_FIELDS = (
    "skill_id",
    "decision",
    "route_key",
    "route_namespace",
    "workflows",
    "safety_level",
    "mutation_policy",
    "eval_status",
    "coverage_entry_ids",
    "planned_coverage_entry_ids",
    "eval_case_ids",
    "readiness_evidence",
    "reasoning_summary",
    "recommended_next_action",
)


class SkillRegistryReadinessStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class SkillRegistryReadinessConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path | None = DEFAULT_MARKDOWN_OUTPUT_PATH
    scale_report_path: Path = DEFAULT_SCALE_REPORT_PATH
    coverage_report_path: Path = DEFAULT_COVERAGE_REPORT_PATH


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object at {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_hash(path: Path | None) -> str | None:
    return sha256_file(path) if path is not None and path.is_file() else None


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validation_error(error_id: str, message: str, severity: str = "high") -> dict[str, str]:
    return {"id": error_id, "severity": severity, "message": message}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "policy.schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"policy.kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "policy.phase must be 193"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if policy.get("acceptance_marker") != "PHASE193 SKILL REGISTRY READINESS REVIEW PASS":
        errors.append(validation_error("policy.acceptance_marker", "policy acceptance marker must match Phase 193"))
    contract = dict_value(policy.get("decision_contract"))
    if string_list(contract.get("allowed_decisions")) != list(DECISIONS):
        errors.append(validation_error("decision_contract.allowed_decisions", "allowed decisions must be keep, split, merge, retire, defer"))
    if string_list(contract.get("required_report_fields")) != list(REQUIRED_SKILL_FIELDS):
        errors.append(validation_error("decision_contract.required_report_fields", "required report fields must match Phase 193"))
    source_paths = dict_value(policy.get("required_source_paths"))
    for key in ("skill_registry", "skill_evals", "prompt_skill_coverage", "workflows", "tools"):
        if not isinstance(source_paths.get(key), str) or not source_paths.get(key):
            errors.append(validation_error(f"required_source_paths.{key}", f"{key} source path is required"))
    scaling = dict_value(policy.get("scaling_requirements"))
    for key in (
        "metadata_only_selection",
        "no_body_reads_during_selection",
        "route_key_unique",
        "semantic_overlap_rejected",
        "batch_admission_required",
        "live_proof_required_before_validated",
    ):
        if scaling.get(key) is not True:
            errors.append(validation_error(f"scaling_requirements.{key}", f"{key} must be true"))
    return errors


def source_artifacts(config_root: Path, policy: dict[str, Any], extra_paths: dict[str, Path]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for key, path_text in sorted(dict_value(policy.get("required_source_paths")).items()):
        path = resolve_path(config_root, path_text)
        artifacts.append({"source_key": key, "path": str(path.resolve()), "sha256": artifact_hash(path)})
    for key, path in sorted(extra_paths.items()):
        artifacts.append({"source_key": key, "path": str(path.resolve()), "sha256": artifact_hash(path)})
    return artifacts


READ_ONLY_WORKFLOWS = {"code_context.lookup", "code_investigation.plan", "refactor.single_path", "task.decompose"}
ARTIFACT_OR_MUTATION_WORKFLOWS = {"execution_planning.plan", "implementation.workflow", "workflow_feedback.record"}


def coverage_by_skill(coverage_manifest: dict[str, Any], *, status: str) -> dict[str, list[str]]:
    by_skill: dict[str, list[str]] = defaultdict(list)
    for entry in object_list(coverage_manifest.get("entries")):
        if str(entry.get("status") or "") != status:
            continue
        entry_id = str(entry.get("id") or "")
        for skill_id in string_list(entry.get("skill_ids")):
            by_skill[skill_id].append(entry_id)
    return {skill_id: sorted(ids) for skill_id, ids in by_skill.items()}


def planned_coverage_entries(coverage_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "entry_id": str(entry.get("id") or ""),
            "prompt_family": str(entry.get("prompt_family") or ""),
            "status": str(entry.get("status") or ""),
            "selected_workflow": str(entry.get("selected_workflow") or ""),
            "reasoning_summary": "coverage entry is not implemented and should remain deferred until a bounded fixture or prompt need proves it",
            "recommended_next_action": "keep out of validated skill readiness until implementation and eval proof are approved",
        }
        for entry in object_list(coverage_manifest.get("entries"))
        if str(entry.get("status") or "") != "implemented"
    ]


def skill_body_present(skill: dict[str, Any]) -> bool:
    if "body_present" in skill:
        return bool(skill.get("body_present"))
    path_value = skill.get("path")
    if not isinstance(path_value, str) or not path_value.strip():
        return True
    return Path(path_value).is_file()


def mixed_mutation_boundary(skill: dict[str, Any]) -> bool:
    workflows = set(string_list(skill.get("workflows")))
    contract = dict_value(skill.get("capability_contract"))
    mutation_policy = str(contract.get("mutation_policy") or "")
    approval_boundary = str(contract.get("approval_boundary") or "")
    return bool(workflows & READ_ONLY_WORKFLOWS) and bool(workflows & ARTIFACT_OR_MUTATION_WORKFLOWS) and (
        mutation_policy != "no_repository_mutation" or approval_boundary != "none"
    )


def duplicate_route_skill_ids(skills: dict[str, dict[str, Any]]) -> set[str]:
    by_route: dict[str, list[str]] = defaultdict(list)
    for skill_id, skill in skills.items():
        route_key = str(dict_value(skill.get("capability_contract")).get("route_key") or "")
        if route_key:
            by_route[route_key].append(skill_id)
    return {skill_id for ids in by_route.values() if len(ids) > 1 for skill_id in ids}


def duplicate_trigger_boundary_skill_ids(skills: dict[str, dict[str, Any]]) -> set[str]:
    by_boundary: dict[tuple[tuple[str, ...], str, str, str], list[str]] = defaultdict(list)
    for skill_id, skill in skills.items():
        workflows = tuple(sorted(string_list(skill.get("workflows"))))
        contract = dict_value(skill.get("capability_contract"))
        mutation_policy = str(contract.get("mutation_policy") or "")
        namespace = str(skill.get("route_namespace") or "")
        for trigger in sorted(normalized_trigger_phrases(string_list(skill.get("triggers")))):
            by_boundary[(workflows, mutation_policy, namespace, trigger)].append(skill_id)
    return {skill_id for ids in by_boundary.values() if len(ids) > 1 for skill_id in ids}


def readiness_evidence(
    skill: dict[str, Any],
    *,
    implemented_coverage_ids: list[str],
    planned_coverage_ids: list[str],
    conflict_skill_ids: set[str],
    duplicate_route_ids: set[str],
    duplicate_trigger_ids: set[str],
) -> dict[str, Any]:
    contract = dict_value(skill.get("capability_contract"))
    return {
        "body_present": skill_body_present(skill),
        "workflow_count": len(string_list(skill.get("workflows"))),
        "task_type_count": len(string_list(contract.get("task_types"))),
        "trigger_count": len(string_list(skill.get("triggers"))),
        "implemented_coverage_count": len(implemented_coverage_ids),
        "planned_coverage_count": len(planned_coverage_ids),
        "eval_case_count": len(string_list(contract.get("eval_case_ids"))),
        "eval_status_valid": str(skill.get("eval_status") or "") in EVAL_STATUSES,
        "route_key_present": bool(str(contract.get("route_key") or "")),
        "route_namespace_valid": str(skill.get("route_namespace") or "") in ROUTE_KEY_NAMESPACES,
        "safety_level_valid": str(skill.get("safety_level") or "") in SAFETY_LEVELS,
        "mutation_policy_valid": str(contract.get("mutation_policy") or "") in MUTATION_POLICIES,
        "semantic_conflict": skill["id"] in conflict_skill_ids,
        "duplicate_route_key": skill["id"] in duplicate_route_ids,
        "duplicate_trigger_boundary": skill["id"] in duplicate_trigger_ids,
        "mixed_mutation_boundary": mixed_mutation_boundary(skill),
        "deprecated": skill.get("eval_status") == "deprecated" or bool(skill.get("deprecation")),
    }


def skill_decision(
    skill: dict[str, Any],
    *,
    implemented_coverage_ids: list[str],
    planned_coverage_ids: list[str],
    evidence: dict[str, Any],
) -> tuple[str, str, str]:
    contract = dict_value(skill.get("capability_contract"))
    task_types = string_list(contract.get("task_types"))
    workflows = string_list(skill.get("workflows"))
    if evidence["deprecated"]:
        return "retire", "retire trigger: skill is already deprecated", "complete retirement only through the deprecation workflow"
    if not evidence["body_present"]:
        return "retire", "retire trigger: skill body is missing", "restore the skill body or retire the registry entry through the deprecation workflow"
    if skill.get("eval_status") == "validated" and not string_list(contract.get("eval_case_ids")):
        return "retire", "retire trigger: validated skill has no eval evidence", "restore eval evidence or retire the registry entry"
    if evidence["semantic_conflict"]:
        return "merge", "merge trigger: skill participates in a semantic-intent overlap", "merge or replace overlapping skills through a governed batch"
    if evidence["duplicate_route_key"]:
        return "merge", "merge trigger: duplicate route key would create a parallel behavior path", "merge or rename duplicate route-key ownership through a governed batch"
    if evidence["duplicate_trigger_boundary"]:
        return "merge", "merge trigger: duplicate trigger boundary within the same workflow and mutation policy", "merge or disambiguate duplicate trigger ownership"
    if evidence["mixed_mutation_boundary"]:
        return "split", "split trigger: workflows cross read-only and artifact/mutation boundaries", "split into separate read-only and approval-gated skills"
    if len(workflows) > 5 or len(task_types) > 4:
        return "split", "split trigger: skill spans too many workflows or task types for deterministic small-model use", "split into smaller L1/L2 skills before scaling"
    if not implemented_coverage_ids and planned_coverage_ids:
        return "defer", "defer trigger: skill only appears in planned prompt coverage", "defer readiness until implemented coverage and eval proof are approved"
    if not implemented_coverage_ids and skill.get("route_namespace") in {"fixture", "experimental"}:
        return "defer", "defer trigger: skill lacks current prompt-family coverage and belongs to a future namespace", "defer until prompt coverage and eval proof are approved"
    return (
        "keep",
        "keep trigger: validated body, unique route key, no semantic conflict, acceptable workflow/task scope, and safe mutation boundary",
        "keep in current registry and require batch admission for changes",
    )


def build_skill_records(skills: dict[str, dict[str, Any]], coverage_manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    implemented_coverage_lookup = coverage_by_skill(coverage_manifest, status="implemented")
    planned_coverage_lookup = coverage_by_skill(coverage_manifest, status="planned")
    conflicts = semantic_intent_conflicts(skills)
    conflict_skill_ids = {skill_id for conflict in conflicts for skill_id in string_list(conflict.get("skill_ids"))}
    duplicate_route_ids = duplicate_route_skill_ids(skills)
    duplicate_trigger_ids = duplicate_trigger_boundary_skill_ids(skills)
    records: list[dict[str, Any]] = []
    for skill_id, skill in sorted(skills.items()):
        contract = dict_value(skill.get("capability_contract"))
        implemented_coverage_ids = implemented_coverage_lookup.get(skill_id, [])
        planned_coverage_ids = planned_coverage_lookup.get(skill_id, [])
        evidence = readiness_evidence(
            skill,
            implemented_coverage_ids=implemented_coverage_ids,
            planned_coverage_ids=planned_coverage_ids,
            conflict_skill_ids=conflict_skill_ids,
            duplicate_route_ids=duplicate_route_ids,
            duplicate_trigger_ids=duplicate_trigger_ids,
        )
        decision, reason, next_action = skill_decision(
            skill,
            implemented_coverage_ids=implemented_coverage_ids,
            planned_coverage_ids=planned_coverage_ids,
            evidence=evidence,
        )
        records.append(
            {
                "skill_id": skill_id,
                "decision": decision,
                "route_key": str(contract.get("route_key") or ""),
                "route_namespace": str(skill.get("route_namespace") or ""),
                "workflows": string_list(skill.get("workflows")),
                "safety_level": str(skill.get("safety_level") or ""),
                "mutation_policy": str(contract.get("mutation_policy") or ""),
                "eval_status": str(skill.get("eval_status") or ""),
                "coverage_entry_ids": implemented_coverage_ids,
                "planned_coverage_entry_ids": planned_coverage_ids,
                "eval_case_ids": string_list(contract.get("eval_case_ids")),
                "problem_solving_steps": skill.get("problem_solving_steps"),
                "trigger_count": len(string_list(skill.get("triggers"))),
                "readiness_evidence": evidence,
                "reasoning_summary": reason,
                "recommended_next_action": next_action,
            }
        )
    return records, conflicts


def validate_report_records(records: list[dict[str, Any]], policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    required_fields = string_list(dict_value(policy.get("decision_contract")).get("required_report_fields"))
    route_keys: dict[str, str] = {}
    for record in records:
        skill_id = str(record.get("skill_id") or "<unknown>")
        for field in required_fields:
            if field not in record:
                errors.append(validation_error(f"skills.{skill_id}.{field}", f"skill record missing {field}"))
        route_key = str(record.get("route_key") or "")
        if not route_key:
            errors.append(validation_error(f"skills.{skill_id}.route_key", "route_key must be non-empty"))
        elif route_key in route_keys:
            errors.append(validation_error(f"skills.{skill_id}.route_key", f"duplicate route_key also used by {route_keys[route_key]}"))
        else:
            route_keys[route_key] = skill_id
        if not string_list(record.get("workflows")):
            errors.append(validation_error(f"skills.{skill_id}.workflows", "workflows must be non-empty"))
        if record.get("safety_level") not in SAFETY_LEVELS:
            errors.append(validation_error(f"skills.{skill_id}.safety_level", "safety_level is unsupported"))
        if record.get("mutation_policy") not in MUTATION_POLICIES:
            errors.append(validation_error(f"skills.{skill_id}.mutation_policy", "mutation_policy is unsupported"))
        if record.get("eval_status") == "validated" and not string_list(record.get("eval_case_ids")):
            errors.append(validation_error(f"skills.{skill_id}.eval_case_ids", "validated skills require eval evidence"))
        evidence = dict_value(record.get("readiness_evidence"))
        if not evidence:
            errors.append(validation_error(f"skills.{skill_id}.readiness_evidence", "readiness_evidence is required"))
        elif record.get("decision") == "keep":
            for key in ("body_present", "route_key_present", "route_namespace_valid", "safety_level_valid", "mutation_policy_valid", "eval_status_valid"):
                if evidence.get(key) is not True:
                    errors.append(validation_error(f"skills.{skill_id}.readiness_evidence.{key}", f"keep decision requires {key}=true"))
            for key in ("semantic_conflict", "duplicate_route_key", "duplicate_trigger_boundary", "mixed_mutation_boundary", "deprecated"):
                if evidence.get(key) is True:
                    errors.append(validation_error(f"skills.{skill_id}.readiness_evidence.{key}", f"keep decision requires {key}=false"))
        if record.get("decision") not in DECISIONS:
            errors.append(validation_error(f"skills.{skill_id}.decision", "skill decision is unsupported"))
    return errors


def validate_source_reports(
    *,
    policy: dict[str, Any],
    skill_scale_report: dict[str, Any],
    prompt_coverage_report: dict[str, Any],
) -> list[dict[str, str]]:
    errors = validate_policy(policy)
    expected_counts = dict_value(policy.get("expected_counts"))
    scale_summary = dict_value(skill_scale_report.get("summary"))
    coverage_summary = dict_value(prompt_coverage_report.get("summary"))
    if skill_scale_report.get("status") != "passed":
        errors.append(validation_error("skill_scale.status", "skill scale report must pass"))
    if prompt_coverage_report.get("status") != "passed":
        errors.append(validation_error("prompt_coverage.status", "prompt skill coverage report must pass"))
    count_checks = {
        "skill_count": scale_summary.get("skill_count"),
        "eval_case_count": scale_summary.get("eval_case_count"),
        "route_key_count": scale_summary.get("route_key_count"),
        "deprecated_skill_count": scale_summary.get("deprecated_skill_count"),
        "do_not_admit_count": scale_summary.get("do_not_admit_count"),
        "prompt_coverage_entry_count": coverage_summary.get("entry_count"),
        "implemented_prompt_coverage_count": coverage_summary.get("implemented_count"),
        "planned_prompt_coverage_count": coverage_summary.get("entry_count", 0) - coverage_summary.get("implemented_count", 0),
    }
    for key, actual in count_checks.items():
        expected = expected_counts.get(key)
        if expected is not None and actual != expected:
            errors.append(validation_error(f"expected_counts.{key}", f"{key} expected {expected} but found {actual}"))
    return errors


def build_skill_registry_readiness_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    skills: dict[str, dict[str, Any]],
    coverage_manifest: dict[str, Any],
    skill_scale_report: dict[str, Any],
    prompt_coverage_report: dict[str, Any],
    policy_path: Path | None = None,
    scale_report_path: Path | None = None,
    coverage_report_path: Path | None = None,
) -> dict[str, Any]:
    records, conflicts = build_skill_records(skills, coverage_manifest)
    planned_entries = planned_coverage_entries(coverage_manifest)
    errors = validate_source_reports(policy=policy, skill_scale_report=skill_scale_report, prompt_coverage_report=prompt_coverage_report)
    errors.extend(validate_report_records(records, policy))
    decision_counts = dict(sorted(Counter(record["decision"] for record in records).items()))
    namespace_counts = dict(sorted(Counter(record["route_namespace"] for record in records).items()))
    safety_counts = dict(sorted(Counter(record["safety_level"] for record in records).items()))
    if decision_counts.get("split", 0) or decision_counts.get("merge", 0) or decision_counts.get("retire", 0):
        errors.append(validation_error("skills.blocking_decisions", "split, merge, and retire decisions require roadmap repair before scaling"))
    status = SkillRegistryReadinessStatus.FAILED.value if errors else SkillRegistryReadinessStatus.PASSED.value
    extra_paths = {
        "skill_scale_report": scale_report_path,
        "prompt_skill_coverage_report": coverage_report_path,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": status,
        "generated_at": utc_timestamp(),
        "policy_path": str(policy_path.resolve()) if policy_path else None,
        "policy_sha256": artifact_hash(policy_path),
        "source_artifacts": source_artifacts(config_root, policy, {key: value for key, value in extra_paths.items() if value is not None}),
        "skill_decisions": records,
        "planned_or_deferred_coverage": planned_entries,
        "semantic_conflicts": conflicts,
        "scaling_actions": [
            "keep metadata-only skill selection as the only selector path",
            "require skill-batch admission before adding or changing skills",
            "require live gateway and AnythingLLM proof before promoting draft skills to validated",
            "monitor planned fixture coverage entries separately from validated skill readiness",
        ],
        "summary": {
            "skill_count": len(records),
            "decision_counts": decision_counts,
            "namespace_counts": namespace_counts,
            "safety_counts": safety_counts,
            "planned_or_deferred_coverage_count": len(planned_entries),
            "semantic_conflict_count": len(conflicts),
            "validation_error_count": len(errors),
            "next_action": "work Phase 194 next" if not errors else "repair skill registry readiness findings before skill authoring pipeline V2",
        },
        "validation_errors": errors,
    }


def stable_report(value: dict[str, Any]) -> dict[str, Any]:
    stable = json.loads(json.dumps(value))
    stable.pop("generated_at", None)
    stable.pop("report_path", None)
    stable.pop("markdown_path", None)
    return stable


def validate_skill_registry_readiness_report(
    report: dict[str, Any],
    *,
    config_root: Path,
    policy: dict[str, Any],
    skills: dict[str, dict[str, Any]],
    coverage_manifest: dict[str, Any],
    skill_scale_report: dict[str, Any],
    prompt_coverage_report: dict[str, Any],
    policy_path: Path | None = None,
    scale_report_path: Path | None = None,
    coverage_report_path: Path | None = None,
) -> list[str]:
    expected = build_skill_registry_readiness_report(
        config_root=config_root,
        policy=policy,
        skills=skills,
        coverage_manifest=coverage_manifest,
        skill_scale_report=skill_scale_report,
        prompt_coverage_report=prompt_coverage_report,
        policy_path=policy_path,
        scale_report_path=scale_report_path,
        coverage_report_path=coverage_report_path,
    )
    if stable_report(report) != stable_report(expected):
        return ["report must match rebuilt skill registry readiness review report"]
    return []


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Skill Registry Readiness Review",
        "",
        f"- Status: {report['status']}",
        f"- Skills: {report['summary']['skill_count']}",
        f"- Decisions: {json.dumps(report['summary']['decision_counts'], sort_keys=True)}",
        f"- Planned/deferred coverage entries: {report['summary']['planned_or_deferred_coverage_count']}",
        f"- Semantic conflicts: {report['summary']['semantic_conflict_count']}",
        f"- Next action: {report['summary']['next_action']}",
        "",
        "## Skill Decisions",
        "",
    ]
    for record in object_list(report.get("skill_decisions")):
        lines.append(
            f"- `{record.get('skill_id')}` {record.get('decision')} "
            f"route={record.get('route_key')} coverage={','.join(string_list(record.get('coverage_entry_ids'))) or 'none'} "
            f"next={record.get('recommended_next_action')}"
        )
    lines.extend(["", "## Planned Or Deferred Coverage", ""])
    for entry in object_list(report.get("planned_or_deferred_coverage")):
        lines.append(f"- `{entry.get('entry_id')}` {entry.get('status')} {entry.get('prompt_family')}: {entry.get('recommended_next_action')}")
    if report.get("validation_errors"):
        lines.extend(["", "## Validation Errors", ""])
        for error in object_list(report.get("validation_errors")):
            lines.append(f"- `{error.get('id')}`: {error.get('message')}")
    write_text(path, "\n".join(lines) + "\n")


def run_skill_registry_readiness_review(config: SkillRegistryReadinessConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    scale_report_path = resolve_path(config_root, config.scale_report_path)
    coverage_report_path = resolve_path(config_root, config.coverage_report_path)
    skill_scale_report = build_skill_scale_report(config_root, output_path=scale_report_path)
    prompt_coverage_report = validate_prompt_coverage(
        PromptCoverageConfig(config_root=config_root, output_path=coverage_report_path)
    )
    try:
        skills = load_skill_registry(config_root)
    except SkillRegistryError as exc:
        skills = {}
        skill_scale_report = {**skill_scale_report, "status": "failed", "errors": [str(exc)]}
    coverage_manifest = read_json_object(resolve_path(config_root, dict_value(policy.get("required_source_paths")).get("prompt_skill_coverage", "")))
    report = build_skill_registry_readiness_report(
        config_root=config_root,
        policy=policy,
        skills=skills,
        coverage_manifest=coverage_manifest,
        skill_scale_report=skill_scale_report,
        prompt_coverage_report=prompt_coverage_report,
        policy_path=policy_path,
        scale_report_path=scale_report_path,
        coverage_report_path=coverage_report_path,
    )
    validation_errors = validate_skill_registry_readiness_report(
        report,
        config_root=config_root,
        policy=policy,
        skills=skills,
        coverage_manifest=coverage_manifest,
        skill_scale_report=skill_scale_report,
        prompt_coverage_report=prompt_coverage_report,
        policy_path=policy_path,
        scale_report_path=scale_report_path,
        coverage_report_path=coverage_report_path,
    )
    if validation_errors:
        report["status"] = SkillRegistryReadinessStatus.FAILED.value
        report["validation_errors"] = object_list(report.get("validation_errors")) + [
            validation_error(f"report.{index}", error) for index, error in enumerate(validation_errors)
        ]
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
        report["summary"]["next_action"] = "repair skill registry readiness findings before skill authoring pipeline V2"
    output_path = resolve_path(config_root, config.output_path)
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    if config.markdown_output_path:
        markdown_path = resolve_path(config_root, config.markdown_output_path)
        write_markdown(markdown_path, report)
        report["markdown_path"] = str(markdown_path.resolve())
        write_json(output_path, report)
    return report
