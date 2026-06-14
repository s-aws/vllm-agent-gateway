"""Phase 229 skill-library scaling readiness inventory."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.context_index_prototype import dict_value, object_list, read_json_object, string_list, write_json


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "skill_library_scaling_readiness_inventory_policy"
EXPECTED_REPORT_KIND = "skill_library_scaling_readiness_inventory_report"
EXPECTED_PHASE = 229
EXPECTED_BACKLOG_ID = "P0-M12-229"
EXPECTED_MILESTONE_IDS = {"M12"}
DEFAULT_POLICY_PATH = Path("runtime") / "skill_library_scaling_readiness_inventory_policy.json"
DEFAULT_OUTPUT_PATH = (
    Path("runtime-state") / "skill-library-scaling" / "phase229" / "phase229-skill-library-scaling-readiness-inventory-report.json"
)
DEFAULT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state") / "skill-library-scaling" / "phase229" / "phase229-skill-library-scaling-readiness-inventory-report.md"
)


@dataclass(frozen=True)
class SkillLibraryScalingReadinessInventoryConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    require_artifacts: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def validation_error(error_id: str, message: str) -> dict[str, str]:
    return {"id": error_id, "message": message}


def load_optional(config_root: Path, raw_path: object, *, required: bool, error_id: str) -> tuple[Path | None, dict[str, Any], list[dict[str, str]]]:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None, {}, [validation_error(f"{error_id}.path", "path is required")]
    path = resolve_path(config_root, raw_path)
    if not path.is_file():
        if required:
            return path, {}, [validation_error(f"{error_id}.missing", f"required artifact missing: {path}")]
        return path, {}, []
    return path, read_json_object(path), []


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "phase must be 229"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be exactly M12"))
    precondition = dict_value(policy.get("phase228_precondition"))
    for key in ("report_path", "required_status"):
        if not isinstance(precondition.get(key), str) or not str(precondition[key]).strip():
            errors.append(validation_error(f"policy.phase228_precondition.{key}", f"{key} is required"))
    if precondition.get("required_phase229_ready") is not True:
        errors.append(validation_error("policy.phase228_precondition.required_phase229_ready", "must be true"))
    for key in ("source_prompt_coverage_path", "source_gap_intake_policy_path", "phase230_recommended_candidate_id"):
        if not isinstance(policy.get(key), str) or not str(policy[key]).strip():
            errors.append(validation_error(f"policy.{key}", f"{key} is required"))
    rules = dict_value(policy.get("selection_rules"))
    expected_rules = {
        "advanced_refactor_allowed": False,
        "missing_skill_gap_required_for_new_skill": True,
        "planned_fixture_coverage_allowed": True,
        "prompt_tightening_only_is_not_skill_gap": True,
        "mutation_capable_skill_allowed": False,
        "manual_skill_injection_allowed": False,
    }
    for key, expected in expected_rules.items():
        if rules.get(key) is not expected:
            errors.append(validation_error(f"policy.selection_rules.{key}", f"{key} must be {expected}"))
    if string_list(policy.get("candidate_status_order")) != ["implemented", "planned", "deferred"]:
        errors.append(validation_error("policy.candidate_status_order", "candidate status order must be implemented/planned/deferred"))
    if policy.get("acceptance_marker") != "PHASE229 SKILL LIBRARY SCALING READINESS INVENTORY PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 229"))
    return errors


def validate_phase228_precondition(policy: dict[str, Any], phase228_report: dict[str, Any]) -> list[dict[str, str]]:
    if not phase228_report:
        return []
    errors: list[dict[str, str]] = []
    precondition = dict_value(policy.get("phase228_precondition"))
    summary = dict_value(phase228_report.get("summary"))
    if phase228_report.get("status") != precondition.get("required_status"):
        errors.append(validation_error("phase228.status", "Phase 228 report status must be passed"))
    if summary.get("phase229_ready") is not precondition.get("required_phase229_ready"):
        errors.append(validation_error("phase228.phase229_ready", "Phase 228 report must mark phase229_ready"))
    return errors


def coverage_inventory(coverage: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    entries = object_list(coverage.get("entries"))
    status_counts = Counter(str(entry.get("status") or "unknown") for entry in entries)
    level_counts = Counter(str(entry.get("level") or "unknown") for entry in entries)
    planned = [entry for entry in entries if entry.get("status") == "planned"]
    implemented = [entry for entry in entries if entry.get("status") == "implemented"]
    return (
        {
            "entry_count": len(entries),
            "implemented_count": len(implemented),
            "planned_count": len(planned),
            "status_counts": dict(sorted(status_counts.items())),
            "level_counts": dict(sorted(level_counts.items())),
        },
        planned,
    )


def gap_intake_summary(policy: dict[str, Any]) -> dict[str, Any]:
    proposals = object_list(policy.get("proposals"))
    source_report = dict_value(policy.get("source_skill_tool_gap_report"))
    return {
        "proposal_count": len(proposals),
        "expected_new_capability_required": source_report.get("expected_new_capability_required"),
        "source_gap_report_status": source_report.get("expected_status"),
    }


def candidate_records(entries: list[dict[str, Any]], recommended_id: str) -> list[dict[str, Any]]:
    candidates = []
    for entry in entries:
        candidate_id = str(entry.get("id") or "")
        status = str(entry.get("status") or "")
        recommendation = "phase230_candidate" if candidate_id == recommended_id else "later_fixture_candidate"
        if candidate_id == recommended_id and status == "implemented":
            recommendation = "phase230_candidate_admitted"
        candidates.append(
            {
                "candidate_id": candidate_id,
                "prompt_family": entry.get("prompt_family"),
                "level": entry.get("level"),
                "status": status,
                "skill_ids": string_list(entry.get("skill_ids")),
                "tool_ids": string_list(entry.get("tool_ids")),
                "validation_suites": string_list(entry.get("validation_suites")),
                "recommendation": recommendation,
                "reason": (
                    "Fixture/eval coverage improves skill-library scaling without inventing a new runtime skill."
                    if candidate_id == recommended_id
                    else "Keep queued until the first fixture/eval candidate passes."
                ),
            }
        )
    return candidates


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Skill Library Scaling Readiness Inventory",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Coverage entries: `{summary.get('entry_count')}`",
        f"- Implemented: `{summary.get('implemented_count')}`",
        f"- Planned: `{summary.get('planned_count')}`",
        f"- Recommended Phase 230 candidate: `{summary.get('phase230_recommended_candidate_id')}`",
        "",
        "## Candidates",
    ]
    for item in object_list(report.get("candidate_records")):
        lines.append(f"- `{item.get('candidate_id')}` `{item.get('prompt_family')}`: {item.get('recommendation')}")
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(["", "## Validation Errors"])
        lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in errors)
    return "\n".join(lines) + "\n"


def validate_skill_library_scaling_readiness_inventory(
    config: SkillLibraryScalingReadinessInventoryConfig,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path)
    policy = read_json_object(policy_path)
    validation_errors = validate_policy(policy)
    phase228_path, phase228_report, phase228_errors = load_optional(
        config_root,
        dict_value(policy.get("phase228_precondition")).get("report_path"),
        required=config.require_artifacts,
        error_id="phase228_report",
    )
    validation_errors.extend(phase228_errors)
    validation_errors.extend(validate_phase228_precondition(policy, phase228_report))
    coverage_path, coverage, coverage_errors = load_optional(
        config_root,
        policy.get("source_prompt_coverage_path"),
        required=config.require_artifacts,
        error_id="prompt_coverage",
    )
    gap_path, gap_policy, gap_errors = load_optional(
        config_root,
        policy.get("source_gap_intake_policy_path"),
        required=config.require_artifacts,
        error_id="gap_intake_policy",
    )
    validation_errors.extend(coverage_errors)
    validation_errors.extend(gap_errors)
    if coverage and coverage.get("kind") != "prompt_skill_coverage_registry":
        validation_errors.append(validation_error("prompt_coverage.kind", "prompt coverage kind mismatch"))
    coverage_summary, planned_entries = coverage_inventory(coverage)
    entries = object_list(coverage.get("entries"))
    entries_by_id = {str(entry.get("id") or ""): entry for entry in entries}
    recommended_id = str(policy.get("phase230_recommended_candidate_id") or "")
    recommended_entry = entries_by_id.get(recommended_id)
    candidate_source_entries = [entry for entry in planned_entries if str(entry.get("id") or "")]
    if recommended_entry and recommended_entry.get("status") == "implemented":
        candidate_source_entries.append(recommended_entry)
    candidates = candidate_records(candidate_source_entries, recommended_id)
    recommended_status = recommended_entry.get("status") if isinstance(recommended_entry, dict) else None
    if not isinstance(recommended_entry, dict):
        validation_errors.append(validation_error("phase230_recommended_candidate_id", "recommended candidate must exist"))
    elif recommended_entry.get("level") != "fixture":
        validation_errors.append(validation_error("phase230_recommended_candidate_id", "recommended candidate must be fixture-level coverage"))
    elif recommended_status not in {"planned", "implemented"}:
        validation_errors.append(validation_error("phase230_recommended_candidate_id", "recommended candidate must be planned or implemented"))
    gap_summary = gap_intake_summary(gap_policy)
    if gap_summary.get("proposal_count") != 0:
        validation_errors.append(validation_error("gap_intake.proposal_count", "current inventory expects no active skill/tool proposals"))
    if gap_summary.get("expected_new_capability_required") is not False:
        validation_errors.append(validation_error("gap_intake.expected_new_capability_required", "new capability must not be required"))
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": sorted(EXPECTED_MILESTONE_IDS),
        "generated_at": utc_timestamp(),
        "status": "passed" if not validation_errors else "failed",
        "policy_path": str(policy_path),
        "phase228_report_path": str(phase228_path) if phase228_path else None,
        "prompt_coverage_path": str(coverage_path) if coverage_path else None,
        "gap_intake_policy_path": str(gap_path) if gap_path else None,
        "candidate_records": candidates,
        "validation_errors": validation_errors,
        "summary": {
            **coverage_summary,
            "gap_intake": gap_summary,
            "phase230_recommended_candidate_id": recommended_id,
            "phase230_recommended_candidate_status": recommended_status,
            "advanced_refactor_allowed": dict_value(policy.get("selection_rules")).get("advanced_refactor_allowed"),
            "new_runtime_skill_required": False,
            "phase230_ready": not validation_errors,
        },
    }
    write_json(output_path, report)
    markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_output_path.write_text(render_markdown(report), encoding="utf-8")
    return report
