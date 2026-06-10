"""Classify founder smoke-suite feedback into governed next actions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_REPORT_KIND = "founder_smoke_feedback_classification"
EXPECTED_PHASE = 135
EXPECTED_BACKLOG_ID = "P0-BB-019"
DEFAULT_SMOKE_REPORT_PATH = Path("runtime-state") / "founder-field-tests" / "phase134-founder-smoke.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "founder-smoke-feedback" / "phase135"


class FounderSmokeFeedbackStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class FeedbackDecisionKind(str, Enum):
    BASELINE_CANDIDATE = "baseline_candidate"
    HOLDOUT_CANDIDATE = "holdout_candidate"
    REPAIR_FOLLOWUP = "repair_followup"
    REJECTED_FINDING = "rejected_finding"
    SKILL_TOOL_GAP = "skill_tool_gap"


@dataclass(frozen=True)
class FounderSmokeFeedbackConfig:
    config_root: Path
    smoke_report_path: Path = DEFAULT_SMOKE_REPORT_PATH
    output_path: Path | None = None
    require_artifacts: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"founder-smoke-feedback-{utc_timestamp()}.json"


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


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def classify_failed_case(case: dict[str, Any]) -> dict[str, Any]:
    case_id = str(case.get("case_id"))
    missing_markers = string_list(case.get("missing_markers"))
    missing_semantic = string_list(case.get("missing_semantic_markers"))
    forbidden = string_list(case.get("forbidden_markers_found"))
    http_status = case.get("http_status")
    if isinstance(http_status, int) and http_status != 200:
        decision = FeedbackDecisionKind.REPAIR_FOLLOWUP.value
        gap_class = "harness_error"
        rationale = "AnythingLLM did not return a successful chat response for this smoke prompt."
    elif missing_markers:
        decision = FeedbackDecisionKind.REPAIR_FOLLOWUP.value
        gap_class = "deterministic_formatter"
        rationale = "The selected workflow response missed required chat-visible contract markers."
    elif missing_semantic or forbidden:
        decision = FeedbackDecisionKind.REPAIR_FOLLOWUP.value
        gap_class = "model_capability"
        rationale = "The selected workflow response missed required semantic content or included forbidden content."
    else:
        decision = FeedbackDecisionKind.REJECTED_FINDING.value
        gap_class = "none"
        rationale = "The case was marked failed but did not include actionable failure evidence."
    return {
        "case_id": case_id,
        "status": "classified",
        "decision_kind": decision,
        "gap_class": gap_class,
        "rationale": rationale,
        "run_id": case.get("run_id"),
        "expected_workflow": case.get("expected_workflow"),
        "initial_difference": case.get("initial_difference"),
        "suggested_prompt_if_missed": case.get("suggested_prompt_if_missed"),
        "evidence": {
            "http_status": http_status,
            "missing_markers": missing_markers,
            "missing_semantic_markers": missing_semantic,
            "forbidden_markers_found": forbidden,
        },
    }


def build_founder_smoke_feedback_report(
    *,
    smoke_report: dict[str, Any],
    smoke_report_path: Path | None = None,
) -> dict[str, Any]:
    cases = object_list(smoke_report.get("cases"))
    failed_cases = [case for case in cases if case.get("status") != "passed"]
    classifications = [classify_failed_case(case) for case in failed_cases]
    fixture_unchanged = smoke_report.get("fixture_state_before") == smoke_report.get("fixture_state_after")
    errors: list[str] = []
    if smoke_report.get("kind") != "founder_field_prompt_evaluation":
        errors.append("smoke_report.kind must be founder_field_prompt_evaluation")
    if smoke_report.get("status") == "passed" and failed_cases:
        errors.append("smoke_report.status cannot be passed when failed cases exist")
    if not fixture_unchanged:
        errors.append("smoke report fixture state changed")
    if failed_cases and len(classifications) != len(failed_cases):
        errors.append("each failed smoke case must have a classification")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": FounderSmokeFeedbackStatus.PASSED.value if not errors else FounderSmokeFeedbackStatus.FAILED.value,
        "generated_at": utc_timestamp(),
        "smoke_report_path": str(smoke_report_path or DEFAULT_SMOKE_REPORT_PATH),
        "smoke_report_sha256": artifact_hash(smoke_report_path) if smoke_report_path else None,
        "smoke_status": smoke_report.get("status"),
        "smoke_summary": smoke_report.get("summary"),
        "fixture_unchanged": fixture_unchanged,
        "classifications": classifications,
        "summary": {
            "smoke_case_count": len(cases),
            "failed_smoke_case_count": len(failed_cases),
            "classification_count": len(classifications),
            "actionable_feedback_count": sum(
                1 for item in classifications if item.get("decision_kind") != FeedbackDecisionKind.REJECTED_FINDING.value
            ),
        },
        "errors": errors,
    }


def validate_founder_smoke_feedback_report(
    report: dict[str, Any],
    *,
    smoke_report: dict[str, Any],
    smoke_report_path: Path | None = None,
) -> list[str]:
    expected = build_founder_smoke_feedback_report(smoke_report=smoke_report, smoke_report_path=smoke_report_path)
    errors: list[str] = []
    for key in (
        "schema_version",
        "kind",
        "phase",
        "priority_backlog_id",
        "status",
        "smoke_report_path",
        "smoke_report_sha256",
        "smoke_status",
        "smoke_summary",
        "fixture_unchanged",
        "classifications",
        "summary",
        "errors",
    ):
        if report.get(key) != expected.get(key):
            errors.append(f"report.{key} must match rebuilt founder smoke feedback classification")
    return errors


def run_founder_smoke_feedback_gate(config: FounderSmokeFeedbackConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    smoke_path = resolve_path(config_root, config.smoke_report_path)
    missing = config.require_artifacts and not smoke_path.is_file()
    smoke_report = read_json_object(smoke_path) if smoke_path.is_file() else {}
    report = build_founder_smoke_feedback_report(smoke_report=smoke_report, smoke_report_path=smoke_path)
    errors = [f"required artifact is missing: {smoke_path}"] if missing else []
    errors.extend(validate_founder_smoke_feedback_report(report, smoke_report=smoke_report, smoke_report_path=smoke_path))
    if errors:
        report["status"] = FounderSmokeFeedbackStatus.FAILED.value
        report["errors"] = errors
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    write_json(output_path, report)
    return report
