"""Phase 274 targeted 500k answer-quality repair closure gate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.large_context_500k_candidate_rebaseline import (
    dict_value,
    read_json_object,
    sha256_file,
    string_list,
    validation_error,
    write_json,
    write_text,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "large_context_500k_answer_quality_repair_policy"
EXPECTED_REPORT_KIND = "large_context_500k_answer_quality_repair_report"
EXPECTED_PHASE = 274
EXPECTED_BACKLOG_ID = "P0-M15-274"
EXPECTED_MILESTONE_IDS = {"M2", "M4", "M6", "M8", "M15"}
DEFAULT_POLICY_PATH = Path("runtime") / "large_context_500k_answer_quality_repair_policy.json"
DEFAULT_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase274"
    / "phase274-large-context-500k-answer-quality-repair-report.json"
)
DEFAULT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase274"
    / "phase274-large-context-500k-answer-quality-repair-report.md"
)


class LargeContext500kAnswerQualityRepairStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class LargeContext500kAnswerQualityRepairConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "phase must be 274"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be M2, M4, M6, M8, and M15"))
    phase273 = dict_value(policy.get("phase273_live_acceptance"))
    if not phase273:
        errors.append(validation_error("policy.phase273_live_acceptance", "phase273_live_acceptance is required"))
    if phase273.get("required_status") != "passed":
        errors.append(validation_error("policy.phase273_live_acceptance.required_status", "Phase 273 must be required to pass"))
    if phase273.get("required_phase274_ready") is not True:
        errors.append(validation_error("policy.phase273_live_acceptance.required_phase274_ready", "Phase 273 must be phase274_ready"))
    if phase273.get("maximum_critical_or_high_finding_count") != 0:
        errors.append(validation_error("policy.phase273_live_acceptance.maximum_critical_or_high_finding_count", "critical/high findings maximum must be 0"))
    if policy.get("decision_when_no_findings") != "no_repair_required":
        errors.append(validation_error("policy.decision_when_no_findings", "no-findings decision must be no_repair_required"))
    if len(string_list(policy.get("required_docs"))) < 5:
        errors.append(validation_error("policy.required_docs", "required docs are missing"))
    if not dict_value(policy.get("required_doc_markers")):
        errors.append(validation_error("policy.required_doc_markers", "required_doc_markers is required"))
    if policy.get("acceptance_marker") != "PHASE274 LARGE CONTEXT 500K ANSWER QUALITY REPAIR PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 274"))
    return errors


def docs_checks(config_root: Path, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    results: list[dict[str, Any]] = []
    required_markers = dict_value(policy.get("required_doc_markers"))
    for raw_path in string_list(policy.get("required_docs")):
        path = resolve_path(config_root, raw_path)
        result: dict[str, Any] = {"path": raw_path, "exists": path.is_file(), "sha256": None, "missing_markers": []}
        if not path.is_file():
            errors.append(validation_error(f"docs.{raw_path}.missing", "required doc is missing", source="docs"))
            results.append(result)
            continue
        text = path.read_text(encoding="utf-8")
        result["sha256"] = sha256_file(path)
        missing = [marker for marker in string_list(required_markers.get(raw_path)) if marker not in text]
        result["missing_markers"] = missing
        for marker in missing:
            errors.append(validation_error(f"docs.{raw_path}.marker", f"required marker missing: {marker}", source="docs"))
        results.append(result)
    return results, errors


def load_phase273_report(config_root: Path, policy: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    raw_path = dict_value(policy.get("phase273_live_acceptance")).get("report_path")
    if not isinstance(raw_path, str) or not raw_path:
        return {}, [validation_error("phase273.report_path", "Phase 273 report path is required", source="phase273")]
    path = resolve_path(config_root, raw_path)
    if not path.is_file():
        return {}, [validation_error("phase273.report_missing", "Phase 273 report is missing", source="phase273")]
    return read_json_object(path), []


def phase273_errors(policy: dict[str, Any], phase273: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    required = dict_value(policy.get("phase273_live_acceptance"))
    summary = dict_value(phase273.get("summary"))
    if phase273.get("status") != required.get("required_status"):
        errors.append(validation_error("phase273.status", "Phase 273 live acceptance must pass", source="phase273", severity="critical"))
    if summary.get("phase274_ready") is not required.get("required_phase274_ready"):
        errors.append(validation_error("phase273.phase274_ready", "Phase 273 must be phase274_ready", source="phase273"))
    maximum = int(required.get("maximum_critical_or_high_finding_count", 0))
    if int(summary.get("critical_or_high_finding_count", 0)) > maximum:
        errors.append(validation_error("phase273.critical_or_high_finding_count", "accepted critical/high findings require repair before close", source="phase273", severity="critical"))
    if int(summary.get("error_count", 0)):
        errors.append(validation_error("phase273.error_count", "Phase 273 must have zero errors before no-repair close", source="phase273"))
    return errors


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Large-Context 500k Answer-Quality Repair",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Decision: `{report.get('decision')}`",
        f"- Error count: `{summary.get('error_count')}`",
        f"- Phase 273 critical/high findings: `{summary.get('phase273_critical_or_high_finding_count')}`",
        "",
        "## Errors",
    ]
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    if errors:
        lines.extend(f"- `{item.get('severity')}` `{item.get('id')}`: {item.get('message')}" for item in errors if isinstance(item, dict))
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def validate_large_context_500k_answer_quality_repair(
    config: LargeContext500kAnswerQualityRepairConfig,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path)
    policy = read_json_object(policy_path)

    policy_errors = validate_policy(policy)
    docs, docs_errors = docs_checks(config_root, policy)
    phase273, phase273_load_errors = load_phase273_report(config_root, policy)
    errors = policy_errors + docs_errors + phase273_load_errors + phase273_errors(policy, phase273)
    phase273_summary = dict_value(phase273.get("summary"))
    status = LargeContext500kAnswerQualityRepairStatus.PASSED.value if not errors else LargeContext500kAnswerQualityRepairStatus.FAILED.value
    decision = str(policy.get("decision_when_no_findings")) if status == LargeContext500kAnswerQualityRepairStatus.PASSED.value else "repair_required"
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": sorted(EXPECTED_MILESTONE_IDS),
        "generated_at": utc_timestamp(),
        "status": status,
        "decision": decision,
        "policy_path": str(policy_path),
        "policy_sha256": sha256_file(policy_path) if policy_path.is_file() else None,
        "docs": docs,
        "phase273_summary": phase273_summary,
        "phase273_report_path": dict_value(policy.get("phase273_live_acceptance")).get("report_path"),
        "errors": errors,
        "summary": {
            "error_count": len(errors),
            "phase273_status": phase273.get("status"),
            "phase273_phase274_ready": phase273_summary.get("phase274_ready"),
            "phase273_critical_or_high_finding_count": phase273_summary.get("critical_or_high_finding_count"),
            "accepted_repair_finding_count": 0 if not errors else None,
            "phase275_ready": not errors,
        },
    }
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown(report))
    return report
