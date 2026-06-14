from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.context_index_prototype import read_json_object, write_json
from vllm_agent_gateway.acceptance.founder_feedback_loop import load_founder_feedback_loop_cases
from vllm_agent_gateway.acceptance.founder_feedback_loop_rebaseline import (
    REQUIRED_DECISIONS,
    FounderFeedbackLoopRebaselineConfig,
    validate_founder_feedback_loop_rebaseline,
    validate_phase227_cases,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = REPO_ROOT / "runtime" / "founder_feedback_loop_phase227_cases.json"


def test_phase227_case_catalog_covers_required_decisions_and_surfaces() -> None:
    cases = load_founder_feedback_loop_cases(CASES_PATH)

    assert validate_phase227_cases(cases) == []
    assert {case.expected_decision_kind for case in cases} == REQUIRED_DECISIONS
    assert {case.surface for case in cases} == {"gateway", "anythingllm"}


def test_phase227_case_catalog_rejects_missing_deferred_decision(tmp_path: Path) -> None:
    catalog = read_json_object(CASES_PATH)
    mutated = copy.deepcopy(catalog)
    mutated["cases"] = [case for case in mutated["cases"] if case["expected_decision_kind"] != "deferred_finding"]
    path = tmp_path / "cases.json"
    write_json(path, mutated)
    cases = load_founder_feedback_loop_cases(path)

    errors = validate_phase227_cases(cases)

    assert any("missing required decision kinds" in error for error in errors)


def test_phase227_preflight_passes_without_live_report(tmp_path: Path) -> None:
    report = validate_founder_feedback_loop_rebaseline(
        FounderFeedbackLoopRebaselineConfig(
            config_root=REPO_ROOT,
            live_report_path=tmp_path / "missing-live.json",
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
            require_live_report=False,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["required_decisions_present"] is True
    assert report["summary"]["phase228_ready"] is False


def test_phase227_requires_live_report_when_requested(tmp_path: Path) -> None:
    report = validate_founder_feedback_loop_rebaseline(
        FounderFeedbackLoopRebaselineConfig(
            config_root=REPO_ROOT,
            live_report_path=tmp_path / "missing.json",
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
            require_live_report=True,
        )
    )

    assert report["status"] == "failed"
    assert any("live report is required" in error for error in report["validation_errors"])


def test_phase227_validates_live_report_decision_coverage(tmp_path: Path) -> None:
    cases = load_founder_feedback_loop_cases(CASES_PATH)
    live_report = {
        "kind": "founder_feedback_loop_live_report",
        "status": "passed",
        "cases": [
            {
                "case_id": case.case_id,
                "status": "passed",
                "surface": case.surface,
                "target_root": case.target_root,
                "feedback_record": {
                    "kind": "workflow_feedback_record",
                    "status": "completed",
                    "run_id": f"feedback-{case.case_id}",
                    "target_run_id": f"target-{case.case_id}",
                    "target_workflow": "workflow_router.plan",
                    "target_root": case.target_root,
                    "feedback": {"useful": ["ok"], "notes": ""},
                    "feedback_context": {"prompt_case": case.case_id},
                    "classifications": list(case.expected_classifications),
                    "governed_decision": {
                        "kind": case.expected_decision_kind,
                        "decision_status": (
                            "accepted"
                            if case.expected_decision_kind
                            in {"baseline_prompt_candidate", "holdout_prompt_candidate", "repair_followup"}
                            else "advisory"
                            if case.expected_decision_kind == "advisory_finding"
                            else "deferred"
                            if case.expected_decision_kind == "deferred_finding"
                            else "rejected"
                        ),
                        "gap_class": case.expected_gap_class,
                        "target_run_id": f"target-{case.case_id}",
                        "feedback_run_id": f"feedback-{case.case_id}",
                        "target_workflow": "workflow_router.plan",
                        "prompt_case_id": case.case_id,
                        "mutation_policy": "controller_artifacts_only",
                        "validation_result": {"status": "passed"},
                    },
                },
                "decision": {
                    "kind": case.expected_decision_kind,
                    "decision_status": (
                        "accepted"
                        if case.expected_decision_kind
                        in {"baseline_prompt_candidate", "holdout_prompt_candidate", "repair_followup"}
                        else "advisory"
                        if case.expected_decision_kind == "advisory_finding"
                        else "deferred"
                        if case.expected_decision_kind == "deferred_finding"
                        else "rejected"
                    ),
                    "gap_class": case.expected_gap_class,
                    "target_run_id": f"target-{case.case_id}",
                    "feedback_run_id": f"feedback-{case.case_id}",
                    "target_workflow": "workflow_router.plan",
                    "prompt_case_id": case.case_id,
                    "mutation_policy": "controller_artifacts_only",
                    "validation_result": {"status": "passed"},
                },
                "errors": [],
            }
            for case in cases
        ],
        "mutation_proof": {
            "runtime_changed_files": [],
            "target_changed_files": {},
            "target_git_changed": {},
        },
    }
    live_path = tmp_path / "live.json"
    write_json(live_path, live_report)

    report = validate_founder_feedback_loop_rebaseline(
        FounderFeedbackLoopRebaselineConfig(
            config_root=REPO_ROOT,
            live_report_path=live_path,
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
            require_live_report=True,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["phase228_ready"] is True
