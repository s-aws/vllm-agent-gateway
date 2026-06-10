from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.skill_tool_coverage_gap import (
    build_skill_tool_coverage_gap_report,
    read_json_object,
    validate_policy,
    validate_skill_tool_coverage_gap_report,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "skill_tool_coverage_gap_policy.json"
PRIORITY0_PATH = REPO_ROOT / "runtime-state" / "priority0-gap-taxonomy" / "phase123-priority0-gap-taxonomy-report.json"
PROMPT_TIGHTENING_PATH = (
    REPO_ROOT
    / "runtime-state"
    / "prompt-tightening-recommendations"
    / "phase128"
    / "phase128-prompt-tightening-recommendations-report.json"
)
BACKLOG_PATH = REPO_ROOT / "runtime" / "natural_language_capability_gap_backlog.json"
COVERAGE_PATH = REPO_ROOT / "runtime" / "prompt_skill_coverage.json"


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def priority0() -> dict[str, Any]:
    return read_json_object(PRIORITY0_PATH)


def prompt_tightening() -> dict[str, Any]:
    return read_json_object(PROMPT_TIGHTENING_PATH)


def backlog() -> dict[str, Any]:
    return read_json_object(BACKLOG_PATH)


def coverage() -> dict[str, Any]:
    return read_json_object(COVERAGE_PATH)


def project_report() -> dict[str, Any]:
    return build_skill_tool_coverage_gap_report(
        config_root=REPO_ROOT,
        policy=policy(),
        priority0_gap_taxonomy=priority0(),
        prompt_tightening_report=prompt_tightening(),
        capability_backlog=backlog(),
        prompt_coverage=coverage(),
        policy_path=POLICY_PATH,
        priority0_gap_taxonomy_path=PRIORITY0_PATH,
        prompt_tightening_report_path=PROMPT_TIGHTENING_PATH,
        capability_backlog_path=BACKLOG_PATH,
        prompt_coverage_path=COVERAGE_PATH,
    )


def add_skill_tool_finding(report: dict[str, Any], evidence: dict[str, Any] | None = None) -> None:
    finding = {
        "severity": "high",
        "category": "evidence_miss",
        "message": "selected tool was unavailable for the requested lookup",
        "report_label": "synthetic",
        "source": "case-1/gateway",
        "evidence": {
            "gap_class": "skill_tool_selection",
            "bounded_repair_action": "Repair the selected skill, rejected skill, tool catalog, or allowlist evidence before changing answer text.",
            **(evidence or {}),
        },
    }
    report["findings"] = [finding]
    report["summary"]["finding_count"] = 1
    report["summary"]["gap_class_counts"]["skill_tool_selection"] = 1


def test_project_skill_tool_coverage_gap_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_project_skill_tool_coverage_gap_report_passes_with_no_current_gap() -> None:
    report = project_report()
    errors = validate_skill_tool_coverage_gap_report(
        report,
        policy=policy(),
        priority0_gap_taxonomy=priority0(),
        prompt_tightening_report=prompt_tightening(),
        capability_backlog=backlog(),
        prompt_coverage=coverage(),
    )
    assert errors == []
    assert report["summary"]["skill_tool_finding_count"] == 0
    assert report["summary"]["gap_candidate_count"] == 0
    assert report["summary"]["new_capability_required"] is False
    assert report["non_skill_tool_records"][0]["classified_as"] == "not_skill_tool_gap"


def test_report_generates_candidate_for_skill_tool_finding_with_backlog_ref() -> None:
    priority = priority0()
    add_skill_tool_finding(priority, {"capability_backlog_ref": "P93-004"})
    report = build_skill_tool_coverage_gap_report(
        config_root=REPO_ROOT,
        policy=policy(),
        priority0_gap_taxonomy=priority,
        prompt_tightening_report=prompt_tightening(),
        capability_backlog=backlog(),
        prompt_coverage=coverage(),
    )
    errors = validate_skill_tool_coverage_gap_report(
        report,
        policy=policy(),
        priority0_gap_taxonomy=priority,
        prompt_tightening_report=prompt_tightening(),
        capability_backlog=backlog(),
        prompt_coverage=coverage(),
    )
    assert errors == []
    assert report["summary"]["new_capability_required"] is True
    assert report["gap_candidates"][0]["capability_backlog_ref"] == "P93-004"
    assert report["gap_candidates"][0]["eval_gate"] == "feature_flag_trace_eval"


def test_report_rejects_missing_gap_candidate_for_skill_tool_finding() -> None:
    priority = priority0()
    add_skill_tool_finding(priority, {"capability_backlog_ref": "P93-004"})
    report = project_report()
    report["status"] = "failed"
    errors = validate_skill_tool_coverage_gap_report(
        report,
        policy=policy(),
        priority0_gap_taxonomy=priority,
        prompt_tightening_report=prompt_tightening(),
        capability_backlog=backlog(),
        prompt_coverage=coverage(),
    )
    assert any("gap_candidates must match skill/tool findings" in error for error in errors)


def test_report_rejects_gap_candidate_without_eval_gate() -> None:
    priority = priority0()
    add_skill_tool_finding(priority, {"capability_backlog_ref": "P93-004"})
    report = build_skill_tool_coverage_gap_report(
        config_root=REPO_ROOT,
        policy=policy(),
        priority0_gap_taxonomy=priority,
        prompt_tightening_report=prompt_tightening(),
        capability_backlog=backlog(),
        prompt_coverage=coverage(),
    )
    report["gap_candidates"][0]["eval_gate"] = ""
    report["status"] = "failed"
    errors = validate_skill_tool_coverage_gap_report(
        report,
        policy=policy(),
        priority0_gap_taxonomy=priority,
        prompt_tightening_report=prompt_tightening(),
        capability_backlog=backlog(),
        prompt_coverage=coverage(),
    )
    assert any("eval_gate must be a non-empty string" in error for error in errors)


def test_report_rejects_invalid_validation_tier() -> None:
    priority = priority0()
    add_skill_tool_finding(priority, {"capability_backlog_ref": "P93-004"})
    report = build_skill_tool_coverage_gap_report(
        config_root=REPO_ROOT,
        policy=policy(),
        priority0_gap_taxonomy=priority,
        prompt_tightening_report=prompt_tightening(),
        capability_backlog=backlog(),
        prompt_coverage=coverage(),
    )
    report["gap_candidates"][0]["validation_tier"] = "trust_me"
    report["status"] = "failed"
    errors = validate_skill_tool_coverage_gap_report(
        report,
        policy=policy(),
        priority0_gap_taxonomy=priority,
        prompt_tightening_report=prompt_tightening(),
        capability_backlog=backlog(),
        prompt_coverage=coverage(),
    )
    assert any("validation_tier must be governed" in error for error in errors)


def test_report_rejects_invalid_approval_boundary() -> None:
    priority = priority0()
    add_skill_tool_finding(priority, {"capability_backlog_ref": "P93-004"})
    report = build_skill_tool_coverage_gap_report(
        config_root=REPO_ROOT,
        policy=policy(),
        priority0_gap_taxonomy=priority,
        prompt_tightening_report=prompt_tightening(),
        capability_backlog=backlog(),
        prompt_coverage=coverage(),
    )
    report["gap_candidates"][0]["approval_boundary"] = "ship_it"
    report["status"] = "failed"
    errors = validate_skill_tool_coverage_gap_report(
        report,
        policy=policy(),
        priority0_gap_taxonomy=priority,
        prompt_tightening_report=prompt_tightening(),
        capability_backlog=backlog(),
        prompt_coverage=coverage(),
    )
    assert any("approval_boundary must be governed" in error for error in errors)


def test_report_rejects_prompt_tightening_record_reclassified_as_skill_gap() -> None:
    report = project_report()
    report["non_skill_tool_records"][0]["classified_as"] = "skill_tool_gap"
    report["status"] = "failed"
    errors = validate_skill_tool_coverage_gap_report(
        report,
        policy=policy(),
        priority0_gap_taxonomy=priority0(),
        prompt_tightening_report=prompt_tightening(),
        capability_backlog=backlog(),
        prompt_coverage=coverage(),
    )
    assert any("non_skill_tool_records must classify prompt-tightening candidates separately" in error for error in errors)


def test_report_rejects_failed_priority0_taxonomy_input() -> None:
    priority = copy.deepcopy(priority0())
    priority["status"] = "failed"
    report = build_skill_tool_coverage_gap_report(
        config_root=REPO_ROOT,
        policy=policy(),
        priority0_gap_taxonomy=priority,
        prompt_tightening_report=prompt_tightening(),
        capability_backlog=backlog(),
        prompt_coverage=coverage(),
    )
    report["status"] = "failed"
    errors = validate_skill_tool_coverage_gap_report(
        report,
        policy=policy(),
        priority0_gap_taxonomy=priority,
        prompt_tightening_report=prompt_tightening(),
        capability_backlog=backlog(),
        prompt_coverage=coverage(),
    )
    assert any("priority0_gap_taxonomy.status must be passed" in error for error in errors)
