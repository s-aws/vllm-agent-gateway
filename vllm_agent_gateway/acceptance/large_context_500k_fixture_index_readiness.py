"""Phase 271 500k fixture and index readiness gate."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.large_context_384k_fixture_index_readiness import (
    LargeContext384kFixtureIndexReadinessConfig,
    LargeContext384kFixtureIndexReadinessStatus,
    validate_large_context_384k_fixture_index_readiness,
)
from vllm_agent_gateway.acceptance.large_context_500k_candidate_rebaseline import (
    LargeContext500kCandidateRebaselineConfig,
    LargeContext500kCandidateRebaselineStatus,
    dict_value,
    read_json_object,
    sha256_file,
    string_list,
    validate_large_context_500k_candidate_rebaseline,
    validation_error,
    write_json,
    write_text,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "large_context_500k_fixture_index_readiness_policy"
EXPECTED_REPORT_KIND = "large_context_500k_fixture_index_readiness_report"
EXPECTED_PHASE = 271
EXPECTED_BACKLOG_ID = "P0-M15-271"
EXPECTED_MILESTONE_IDS = {"M6", "M15", "M16"}
CANDIDATE_ESTIMATED_PROJECT_TOKENS = 500_000
DEFAULT_POLICY_PATH = Path("runtime") / "large_context_500k_fixture_index_readiness_policy.json"
DEFAULT_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase271"
    / "phase271-large-context-500k-fixture-index-readiness-report.json"
)
DEFAULT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase271"
    / "phase271-large-context-500k-fixture-index-readiness-report.md"
)


class LargeContext500kFixtureIndexReadinessStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class LargeContext500kFixtureIndexReadinessConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    bootstrap_composed_gates: bool = True
    validate_phase270_precondition: bool = True


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
        errors.append(validation_error("policy.phase", "phase must be 271"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be M6, M15, and M16"))
    if policy.get("candidate_estimated_project_tokens") != CANDIDATE_ESTIMATED_PROJECT_TOKENS:
        errors.append(validation_error("policy.candidate_estimated_project_tokens", "candidate target must be 500000"))
    if not dict_value(policy.get("phase270_precondition")):
        errors.append(validation_error("policy.phase270_precondition", "phase270_precondition is required"))
    phase259 = dict_value(policy.get("phase259_delegate"))
    if not phase259:
        errors.append(validation_error("policy.phase259_delegate", "phase259_delegate is required"))
    if phase259.get("required_status") != LargeContext384kFixtureIndexReadinessStatus.PASSED.value:
        errors.append(validation_error("policy.phase259_delegate.required_status", "Phase 259 must be required to pass"))
    if phase259.get("required_phase260_ready") is not True:
        errors.append(validation_error("policy.phase259_delegate.required_phase260_ready", "Phase 259 must be phase260_ready"))
    thresholds = dict_value(policy.get("required_thresholds"))
    for key in ("minimum_corpus_estimated_token_count", "minimum_estimated_indexed_token_count"):
        if thresholds.get(key) != CANDIDATE_ESTIMATED_PROJECT_TOKENS:
            errors.append(validation_error(f"policy.required_thresholds.{key}", f"{key} must be 500000"))
    if int(thresholds.get("minimum_indexed_file_count", 0)) < 220:
        errors.append(validation_error("policy.required_thresholds.minimum_indexed_file_count", "minimum indexed file count must be at least 220"))
    if int(thresholds.get("minimum_chunk_count", 0)) < 220:
        errors.append(validation_error("policy.required_thresholds.minimum_chunk_count", "minimum chunk count must be at least 220"))
    safety = dict_value(policy.get("required_index_safety"))
    if safety.get("source_text_retention") != "metadata_only":
        errors.append(validation_error("policy.required_index_safety.source_text_retention", "source_text_retention must be metadata_only"))
    for key in (
        "store_source_text",
        "store_rejected_content",
        "raw_prompt_stuffing_allowed",
        "raw_500k_prompt_support_claim_allowed",
        "artifact_only_answers_allowed",
    ):
        if safety.get(key) is not False:
            errors.append(validation_error(f"policy.required_index_safety.{key}", f"{key} must be false"))
    if len(string_list(policy.get("required_docs"))) < 5:
        errors.append(validation_error("policy.required_docs", "required docs are missing"))
    if not dict_value(policy.get("required_doc_markers")):
        errors.append(validation_error("policy.required_doc_markers", "required_doc_markers is required"))
    if policy.get("acceptance_marker") != "PHASE271 LARGE CONTEXT 500K FIXTURE INDEX READINESS PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 271"))
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


def run_phase270(config_root: Path) -> dict[str, Any]:
    return validate_large_context_500k_candidate_rebaseline(
        LargeContext500kCandidateRebaselineConfig(config_root=config_root)
    )


def run_phase259(config_root: Path, *, bootstrap_composed_gates: bool) -> dict[str, Any]:
    return validate_large_context_384k_fixture_index_readiness(
        LargeContext384kFixtureIndexReadinessConfig(
            config_root=config_root,
            bootstrap_composed_gates=bootstrap_composed_gates,
        )
    )


def phase270_errors(policy: dict[str, Any], phase270: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    required = dict_value(policy.get("phase270_precondition"))
    if phase270.get("status") != required.get("required_status"):
        errors.append(validation_error("phase270.status", "Phase 270 candidate rebaseline must pass", source="phase270"))
    if dict_value(phase270.get("summary")).get("phase270_ready") is not required.get("required_phase270_ready"):
        errors.append(validation_error("phase270.phase270_ready", "Phase 270 must be ready", source="phase270"))
    return errors


def composed_summary(composed: dict[str, Any], key: str) -> dict[str, Any]:
    value = dict_value(composed.get(key))
    nested = dict_value(value.get("summary"))
    return nested or value


def phase259_errors(policy: dict[str, Any], phase259: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    delegate = dict_value(policy.get("phase259_delegate"))
    thresholds = dict_value(policy.get("required_thresholds"))
    safety = dict_value(policy.get("required_index_safety"))
    phase259_summary = dict_value(phase259.get("summary"))
    composed = dict_value(phase259.get("composed_report_summaries"))
    phase214_summary = composed_summary(composed, "phase214")
    phase217_summary = composed_summary(composed, "phase217")

    if phase259.get("status") != delegate.get("required_status"):
        errors.append(validation_error("phase259.status", "Phase 259 readiness delegate must pass", source="phase259"))
    if phase259_summary.get("phase260_ready") is not delegate.get("required_phase260_ready"):
        errors.append(validation_error("phase259.phase260_ready", "Phase 259 must be phase260_ready", source="phase259"))
    if int(phase214_summary.get("estimated_token_count", 0)) < int(thresholds.get("minimum_corpus_estimated_token_count", 0)):
        errors.append(validation_error("phase214.estimated_token_count", "large corpus must meet 500k token candidate target", source="phase214"))
    if int(phase217_summary.get("estimated_indexed_token_count", 0)) < int(thresholds.get("minimum_estimated_indexed_token_count", 0)):
        errors.append(validation_error("phase217.estimated_indexed_token_count", "indexed token estimate must meet 500k target", source="phase217"))
    if int(phase217_summary.get("indexed_file_count", 0)) < int(thresholds.get("minimum_indexed_file_count", 0)):
        errors.append(validation_error("phase217.indexed_file_count", "indexed file count is too low", source="phase217"))
    if int(phase217_summary.get("chunk_count", 0)) < int(thresholds.get("minimum_chunk_count", 0)):
        errors.append(validation_error("phase217.chunk_count", "chunk count is too low", source="phase217"))
    if phase214_summary.get("raw_1m_prompt_support_proven") is not False:
        errors.append(validation_error("phase214.raw_1m_prompt_support_proven", "raw 1M prompt support must remain unproven", source="phase214"))
    if phase217_summary.get("source_text_retention") != safety.get("source_text_retention"):
        errors.append(validation_error("phase217.source_text_retention", "source_text_retention must match policy", source="phase217"))
    for key in ("store_source_text", "store_rejected_content"):
        if phase217_summary.get(key) != safety.get(key):
            errors.append(validation_error(f"phase217.{key}", f"{key} must match policy", source="phase217"))
    return errors


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Large-Context 500k Fixture And Index Readiness",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Error count: `{summary.get('error_count')}`",
        f"- Candidate estimated project tokens: `{summary.get('candidate_estimated_project_tokens')}`",
        f"- Corpus estimated tokens: `{summary.get('corpus_estimated_token_count')}`",
        f"- Indexed estimated tokens: `{summary.get('estimated_indexed_token_count')}`",
        f"- Indexed files: `{summary.get('indexed_file_count')}`",
        f"- Chunks: `{summary.get('chunk_count')}`",
        "",
        "## Errors",
    ]
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    if errors:
        lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in errors if isinstance(item, dict))
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def validate_large_context_500k_fixture_index_readiness(
    config: LargeContext500kFixtureIndexReadinessConfig,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path)
    policy = read_json_object(policy_path)

    policy_errors = validate_policy(policy)
    docs, docs_errors = docs_checks(config_root, policy)
    phase270 = (
        run_phase270(config_root)
        if config.validate_phase270_precondition
        else {"status": LargeContext500kCandidateRebaselineStatus.PASSED.value, "summary": {"phase270_ready": True}}
    )
    phase259 = run_phase259(config_root, bootstrap_composed_gates=config.bootstrap_composed_gates)
    errors = policy_errors + docs_errors + phase270_errors(policy, phase270) + phase259_errors(policy, phase259)

    phase259_summary = dict_value(phase259.get("summary"))
    composed = dict_value(phase259.get("composed_report_summaries"))
    phase214_summary = composed_summary(composed, "phase214")
    phase217_summary = composed_summary(composed, "phase217")
    status = (
        LargeContext500kFixtureIndexReadinessStatus.PASSED.value
        if not errors
        else LargeContext500kFixtureIndexReadinessStatus.FAILED.value
    )
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
        "bootstrap_composed_gates": config.bootstrap_composed_gates,
        "docs": docs,
        "phase270_summary": dict_value(phase270.get("summary")),
        "phase259_summary": phase259_summary,
        "phase259_composed_report_summaries": dict_value(phase259.get("composed_report_summaries")),
        "errors": errors,
        "summary": {
            "error_count": len(errors),
            "candidate_estimated_project_tokens": policy.get("candidate_estimated_project_tokens"),
            "corpus_estimated_token_count": phase214_summary.get("estimated_token_count"),
            "estimated_indexed_token_count": phase217_summary.get("estimated_indexed_token_count"),
            "indexed_file_count": phase217_summary.get("indexed_file_count"),
            "chunk_count": phase217_summary.get("chunk_count"),
            "phase259_status": phase259.get("status"),
            "phase259_phase260_ready": phase259_summary.get("phase260_ready"),
            "phase270_status": phase270.get("status"),
            "phase270_ready": dict_value(phase270.get("summary")).get("phase270_ready"),
            "phase272_ready": not errors,
        },
    }
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown(report))
    return report
