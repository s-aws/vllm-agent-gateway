"""Phase 227 founder-feedback loop rebaseline gate."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.founder_feedback_loop import (
    FounderFeedbackLoopCase,
    load_founder_feedback_loop_cases,
    validate_case_catalog,
    validate_founder_feedback_loop_report,
)


SCHEMA_VERSION = 1
EXPECTED_KIND = "founder_feedback_loop_rebaseline_report"
EXPECTED_PHASE = 227
EXPECTED_BACKLOG_ID = "P0-M9-227"
EXPECTED_MILESTONE_IDS = {"M9"}
DEFAULT_CASES_PATH = Path("runtime") / "founder_feedback_loop_phase227_cases.json"
DEFAULT_LIVE_REPORT_PATH = (
    Path("runtime-state") / "founder-feedback-loop" / "phase227" / "phase227-founder-feedback-loop-live.json"
)
DEFAULT_OUTPUT_PATH = (
    Path("runtime-state") / "founder-feedback-loop" / "phase227" / "phase227-founder-feedback-loop-rebaseline-report.json"
)
DEFAULT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state") / "founder-feedback-loop" / "phase227" / "phase227-founder-feedback-loop-rebaseline-report.md"
)
REQUIRED_DECISIONS = {
    "baseline_prompt_candidate",
    "holdout_prompt_candidate",
    "repair_followup",
    "rejected_finding",
    "advisory_finding",
    "deferred_finding",
}
REQUIRED_SURFACES = {"gateway", "anythingllm"}
REQUIRED_TARGET_ROOTS = {
    "/mnt/c/agentic_agents/runtime-state/phase214/generated-large-corpus",
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
}


@dataclass(frozen=True)
class FounderFeedbackLoopRebaselineConfig:
    config_root: Path
    cases_path: Path = DEFAULT_CASES_PATH
    live_report_path: Path = DEFAULT_LIVE_REPORT_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    require_live_report: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else config_root / path


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object at {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def case_summary(cases: list[FounderFeedbackLoopCase]) -> dict[str, Any]:
    decisions = sorted({case.expected_decision_kind for case in cases})
    surfaces = sorted({case.surface for case in cases})
    target_roots = sorted({case.target_root for case in cases})
    return {
        "case_count": len(cases),
        "decision_kinds": decisions,
        "surface_count": len(surfaces),
        "surfaces": surfaces,
        "target_root_count": len(target_roots),
        "target_roots": target_roots,
        "required_decisions_present": REQUIRED_DECISIONS.issubset(set(decisions)),
        "required_surfaces_present": REQUIRED_SURFACES.issubset(set(surfaces)),
        "required_target_roots_present": REQUIRED_TARGET_ROOTS.issubset(set(target_roots)),
    }


def validate_phase227_cases(cases: list[FounderFeedbackLoopCase]) -> list[str]:
    errors = validate_case_catalog(cases, required_decisions=REQUIRED_DECISIONS)
    summary = case_summary(cases)
    if not summary["required_surfaces_present"]:
        errors.append("phase227 cases must cover gateway and anythingllm")
    if not summary["required_target_roots_present"]:
        errors.append("phase227 cases must cover generated large corpus and both frozen Coinbase roots")
    if summary["case_count"] < 6:
        errors.append("phase227 requires at least six feedback cases")
    return errors


def live_report_summary(report: dict[str, Any]) -> dict[str, Any]:
    cases = report.get("cases") if isinstance(report.get("cases"), list) else []
    decisions = []
    for item in cases:
        if not isinstance(item, dict):
            continue
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        if isinstance(decision.get("kind"), str):
            decisions.append(decision["kind"])
    mutation = report.get("mutation_proof") if isinstance(report.get("mutation_proof"), dict) else {}
    return {
        "status": report.get("status"),
        "case_count": len(cases),
        "decision_kinds": sorted(set(decisions)),
        "required_decisions_present": REQUIRED_DECISIONS.issubset(set(decisions)),
        "runtime_changed_files": mutation.get("runtime_changed_files"),
        "target_changed_files": mutation.get("target_changed_files"),
        "target_git_changed": mutation.get("target_git_changed"),
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    live = summary.get("live_report") if isinstance(summary.get("live_report"), dict) else {}
    lines = [
        "# Founder Feedback Loop Rebaseline",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Case count: `{summary.get('case_count')}`",
        f"- Decisions: `{', '.join(summary.get('decision_kinds', []))}`",
        f"- Live report status: `{live.get('status')}`",
        f"- Live report case count: `{live.get('case_count')}`",
        "",
        "## Validation Errors",
    ]
    errors = report.get("validation_errors") if isinstance(report.get("validation_errors"), list) else []
    if errors:
        lines.extend(f"- {error}" for error in errors)
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def validate_founder_feedback_loop_rebaseline(config: FounderFeedbackLoopRebaselineConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    cases_path = resolve_path(config_root, config.cases_path)
    live_report_path = resolve_path(config_root, config.live_report_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path)
    validation_errors: list[str] = []

    cases = load_founder_feedback_loop_cases(cases_path)
    validation_errors.extend(validate_phase227_cases(cases))

    live_report: dict[str, Any] = {}
    live_summary: dict[str, Any] = {}
    if live_report_path.exists():
        live_report = read_json_object(live_report_path)
        validation_errors.extend(
            validate_founder_feedback_loop_report(
                live_report,
                cases,
                required_decisions=REQUIRED_DECISIONS,
            )
        )
        live_summary = live_report_summary(live_report)
        if live_summary.get("required_decisions_present") is not True:
            validation_errors.append("live report must include every Phase 227 decision kind")
    elif config.require_live_report:
        validation_errors.append(f"live report is required: {live_report_path}")

    summary = {
        **case_summary(cases),
        "live_report_path": str(live_report_path),
        "live_report": live_summary,
        "phase228_ready": not validation_errors and bool(live_report),
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": sorted(EXPECTED_MILESTONE_IDS),
        "generated_at": utc_timestamp(),
        "status": "passed" if not validation_errors else "failed",
        "cases_path": str(cases_path),
        "live_report_path": str(live_report_path),
        "validation_errors": validation_errors,
        "summary": summary,
    }
    write_json(output_path, report)
    markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_output_path.write_text(render_markdown(report), encoding="utf-8")
    return report
