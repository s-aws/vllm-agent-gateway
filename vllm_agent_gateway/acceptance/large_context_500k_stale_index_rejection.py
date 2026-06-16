"""Phase 272 500k stale-index rejection gate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.large_context_384k_stale_index_rejection import (
    LargeContext384kStaleIndexRejectionConfig,
    LargeContext384kStaleIndexRejectionStatus,
    validate_large_context_384k_stale_index_rejection,
)
from vllm_agent_gateway.acceptance.large_context_500k_candidate_rebaseline import (
    dict_value,
    read_json_object,
    sha256_file,
    string_list,
    validation_error,
    write_json,
    write_text,
)
from vllm_agent_gateway.acceptance.large_context_500k_fixture_index_readiness import (
    LargeContext500kFixtureIndexReadinessConfig,
    LargeContext500kFixtureIndexReadinessStatus,
    validate_large_context_500k_fixture_index_readiness,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "large_context_500k_stale_index_rejection_policy"
EXPECTED_REPORT_KIND = "large_context_500k_stale_index_rejection_report"
EXPECTED_PHASE = 272
EXPECTED_BACKLOG_ID = "P0-M15-272"
EXPECTED_MILESTONE_IDS = {"M6", "M8", "M15", "M16"}
CANDIDATE_ESTIMATED_PROJECT_TOKENS = 500_000
DEFAULT_POLICY_PATH = Path("runtime") / "large_context_500k_stale_index_rejection_policy.json"
DEFAULT_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase272"
    / "phase272-large-context-500k-stale-index-rejection-report.json"
)
DEFAULT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase272"
    / "phase272-large-context-500k-stale-index-rejection-report.md"
)


class LargeContext500kStaleIndexRejectionStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class LargeContext500kStaleIndexRejectionConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    validate_phase271_precondition: bool = True
    validate_phase260_delegate: bool = True


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
        errors.append(validation_error("policy.phase", "phase must be 272"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be M6, M8, M15, and M16"))
    if policy.get("candidate_estimated_project_tokens") != CANDIDATE_ESTIMATED_PROJECT_TOKENS:
        errors.append(validation_error("policy.candidate_estimated_project_tokens", "candidate target must be 500000"))
    phase271 = dict_value(policy.get("phase271_precondition"))
    if not phase271:
        errors.append(validation_error("policy.phase271_precondition", "phase271_precondition is required"))
    if phase271.get("required_status") != LargeContext500kFixtureIndexReadinessStatus.PASSED.value:
        errors.append(validation_error("policy.phase271_precondition.required_status", "Phase 271 must be required to pass"))
    if phase271.get("required_phase272_ready") is not True:
        errors.append(validation_error("policy.phase271_precondition.required_phase272_ready", "Phase 271 must be phase272_ready"))
    delegate = dict_value(policy.get("phase260_delegate"))
    if not delegate:
        errors.append(validation_error("policy.phase260_delegate", "phase260_delegate is required"))
    if delegate.get("required_status") != LargeContext384kStaleIndexRejectionStatus.PASSED.value:
        errors.append(validation_error("policy.phase260_delegate.required_status", "Phase 260 must be required to pass"))
    if delegate.get("required_phase261_ready") is not True:
        errors.append(validation_error("policy.phase260_delegate.required_phase261_ready", "Phase 260 must be phase261_ready"))
    if int(delegate.get("minimum_case_count", 0)) < 6:
        errors.append(validation_error("policy.phase260_delegate.minimum_case_count", "minimum case count must be at least 6"))
    properties = dict_value(policy.get("required_fail_closed_properties"))
    for key in (
        "artifact_only_answers_allowed",
        "raw_prompt_stuffing_allowed",
        "store_source_text",
        "store_rejected_content",
        "serve_stale_evidence_allowed",
        "serve_ignored_or_secret_like_evidence_allowed",
    ):
        if properties.get(key) is not False:
            errors.append(validation_error(f"policy.required_fail_closed_properties.{key}", f"{key} must be false"))
    if properties.get("source_text_retention") != "metadata_only":
        errors.append(validation_error("policy.required_fail_closed_properties.source_text_retention", "source_text_retention must be metadata_only"))
    if len(string_list(policy.get("required_docs"))) < 5:
        errors.append(validation_error("policy.required_docs", "required docs are missing"))
    if not dict_value(policy.get("required_doc_markers")):
        errors.append(validation_error("policy.required_doc_markers", "required_doc_markers is required"))
    if policy.get("acceptance_marker") != "PHASE272 LARGE CONTEXT 500K STALE INDEX REJECTION PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 272"))
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


def run_phase271(config_root: Path) -> dict[str, Any]:
    return validate_large_context_500k_fixture_index_readiness(
        LargeContext500kFixtureIndexReadinessConfig(config_root=config_root)
    )


def run_phase260(config_root: Path) -> dict[str, Any]:
    return validate_large_context_384k_stale_index_rejection(
        LargeContext384kStaleIndexRejectionConfig(config_root=config_root)
    )


def phase271_errors(policy: dict[str, Any], phase271: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    required = dict_value(policy.get("phase271_precondition"))
    summary = dict_value(phase271.get("summary"))
    if phase271.get("status") != required.get("required_status"):
        errors.append(validation_error("phase271.status", "Phase 271 fixture/index readiness must pass", source="phase271"))
    if summary.get("phase272_ready") is not required.get("required_phase272_ready"):
        errors.append(validation_error("phase271.phase272_ready", "Phase 271 must be ready for Phase 272", source="phase271"))
    return errors


def phase260_errors(policy: dict[str, Any], phase260: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    delegate = dict_value(policy.get("phase260_delegate"))
    summary = dict_value(phase260.get("summary"))
    if phase260.get("status") != delegate.get("required_status"):
        errors.append(validation_error("phase260.status", "Phase 260 stale-index delegate must pass", source="phase260"))
    if summary.get("phase261_ready") is not delegate.get("required_phase261_ready"):
        errors.append(validation_error("phase260.phase261_ready", "Phase 260 must be phase261_ready", source="phase260"))
    if int(summary.get("case_count", 0)) < int(delegate.get("minimum_case_count", 0)):
        errors.append(validation_error("phase260.case_count", "Phase 260 case count is too low", source="phase260"))
    if summary.get("passed_case_count") != summary.get("case_count"):
        errors.append(validation_error("phase260.passed_case_count", "all Phase 260 cases must pass", source="phase260"))
    return errors


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Large-Context 500k Stale-Index Rejection",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Error count: `{summary.get('error_count')}`",
        f"- Candidate estimated project tokens: `{summary.get('candidate_estimated_project_tokens')}`",
        f"- Phase 260 case count: `{summary.get('phase260_case_count')}`",
        f"- Phase 260 passed case count: `{summary.get('phase260_passed_case_count')}`",
        "",
        "## Errors",
    ]
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    if errors:
        lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in errors if isinstance(item, dict))
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def validate_large_context_500k_stale_index_rejection(
    config: LargeContext500kStaleIndexRejectionConfig,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path)
    policy = read_json_object(policy_path)

    policy_errors = validate_policy(policy)
    docs, docs_errors = docs_checks(config_root, policy)
    phase271 = (
        run_phase271(config_root)
        if config.validate_phase271_precondition
        else {"status": LargeContext500kFixtureIndexReadinessStatus.PASSED.value, "summary": {"phase272_ready": True}}
    )
    phase260 = (
        run_phase260(config_root)
        if config.validate_phase260_delegate
        else {"status": LargeContext384kStaleIndexRejectionStatus.PASSED.value, "summary": {"phase261_ready": True, "case_count": 6, "passed_case_count": 6}}
    )
    errors = policy_errors + docs_errors + phase271_errors(policy, phase271) + phase260_errors(policy, phase260)
    phase271_summary = dict_value(phase271.get("summary"))
    phase260_summary = dict_value(phase260.get("summary"))
    status = LargeContext500kStaleIndexRejectionStatus.PASSED.value if not errors else LargeContext500kStaleIndexRejectionStatus.FAILED.value
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": sorted(EXPECTED_MILESTONE_IDS),
        "generated_at": utc_timestamp(),
        "status": status,
        "policy_path": str(policy_path),
        "policy_sha256": sha256_file(policy_path) if policy_path.is_file() else None,
        "docs": docs,
        "phase271_summary": phase271_summary,
        "phase260_summary": phase260_summary,
        "phase260_case_results": phase260.get("case_results") if isinstance(phase260.get("case_results"), list) else [],
        "errors": errors,
        "summary": {
            "error_count": len(errors),
            "candidate_estimated_project_tokens": policy.get("candidate_estimated_project_tokens"),
            "phase271_status": phase271.get("status"),
            "phase271_phase272_ready": phase271_summary.get("phase272_ready"),
            "phase260_status": phase260.get("status"),
            "phase260_phase261_ready": phase260_summary.get("phase261_ready"),
            "phase260_case_count": phase260_summary.get("case_count"),
            "phase260_passed_case_count": phase260_summary.get("passed_case_count"),
            "phase273_ready": not errors,
        },
    }
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown(report))
    return report
