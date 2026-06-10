from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.founder_feedback_triage_dashboard import (
    DEFAULT_POLICY_PATH,
    build_founder_feedback_triage_dashboard,
    read_json_object,
    validate_founder_feedback_triage_dashboard,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH
FEEDBACK_REPORT_PATH = REPO_ROOT / "runtime-state" / "founder-feedback-loop" / "phase125-founder-feedback-loop-live.json"
FEEDBACK_CASES_PATH = REPO_ROOT / "runtime" / "founder_feedback_loop_cases.json"
SMOKE_FEEDBACK_PATH = (
    REPO_ROOT / "runtime-state" / "founder-smoke-feedback" / "phase135" / "phase135-founder-smoke-feedback.json"
)
SMOKE_SOURCE_PATH = REPO_ROOT / "runtime-state" / "founder-field-tests" / "phase134-founder-smoke.json"
CLOSURE_REPORT_PATH = (
    REPO_ROOT
    / "runtime-state"
    / "stable-release-blocker-closure"
    / "phase131"
    / "phase131-stable-release-blocker-closure-report.json"
)
CLOSURE_POLICY_PATH = REPO_ROOT / "runtime" / "stable_release_blocker_closure_policy.json"


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def feedback_report() -> dict[str, Any]:
    return read_json_object(FEEDBACK_REPORT_PATH)


def feedback_cases() -> dict[str, Any]:
    return read_json_object(FEEDBACK_CASES_PATH)


def smoke_feedback_report() -> dict[str, Any]:
    return read_json_object(SMOKE_FEEDBACK_PATH)


def smoke_source_report() -> dict[str, Any]:
    return read_json_object(SMOKE_SOURCE_PATH)


def closure_report() -> dict[str, Any]:
    return read_json_object(CLOSURE_REPORT_PATH)


def closure_policy() -> dict[str, Any]:
    return read_json_object(CLOSURE_POLICY_PATH)


def project_dashboard(
    *,
    policy_payload: dict[str, Any] | None = None,
    feedback_payload: dict[str, Any] | None = None,
    feedback_cases_payload: dict[str, Any] | None = None,
    smoke_payload: dict[str, Any] | None = None,
    smoke_source_payload: dict[str, Any] | None = None,
    closure_payload: dict[str, Any] | None = None,
    closure_policy_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_founder_feedback_triage_dashboard(
        policy=policy_payload or policy(),
        feedback_report=feedback_payload or feedback_report(),
        feedback_cases_catalog=feedback_cases_payload or feedback_cases(),
        smoke_feedback_report=smoke_payload or smoke_feedback_report(),
        smoke_source_report=smoke_source_payload or smoke_source_report(),
        closure_report=closure_payload or closure_report(),
        closure_policy=closure_policy_payload or closure_policy(),
        policy_path=POLICY_PATH,
        feedback_report_path=FEEDBACK_REPORT_PATH,
        feedback_cases_path=FEEDBACK_CASES_PATH,
        smoke_feedback_report_path=SMOKE_FEEDBACK_PATH,
        smoke_source_report_path=SMOKE_SOURCE_PATH,
        closure_report_path=CLOSURE_REPORT_PATH,
        closure_policy_path=CLOSURE_POLICY_PATH,
    )


def validate_dashboard(
    report: dict[str, Any],
    *,
    policy_payload: dict[str, Any] | None = None,
    feedback_payload: dict[str, Any] | None = None,
    feedback_cases_payload: dict[str, Any] | None = None,
    smoke_payload: dict[str, Any] | None = None,
    smoke_source_payload: dict[str, Any] | None = None,
    closure_payload: dict[str, Any] | None = None,
    closure_policy_payload: dict[str, Any] | None = None,
) -> list[str]:
    return validate_founder_feedback_triage_dashboard(
        report,
        policy=policy_payload or policy(),
        feedback_report=feedback_payload or feedback_report(),
        feedback_cases_catalog=feedback_cases_payload or feedback_cases(),
        smoke_feedback_report=smoke_payload or smoke_feedback_report(),
        smoke_source_report=smoke_source_payload or smoke_source_report(),
        closure_report=closure_payload or closure_report(),
        closure_policy=closure_policy_payload or closure_policy(),
        policy_path=POLICY_PATH,
        feedback_report_path=FEEDBACK_REPORT_PATH,
        feedback_cases_path=FEEDBACK_CASES_PATH,
        smoke_feedback_report_path=SMOKE_FEEDBACK_PATH,
        smoke_source_report_path=SMOKE_SOURCE_PATH,
        closure_report_path=CLOSURE_REPORT_PATH,
        closure_policy_path=CLOSURE_POLICY_PATH,
    )


def test_project_founder_feedback_triage_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_project_founder_feedback_triage_dashboard_passes() -> None:
    report = project_dashboard()

    assert validate_dashboard(report) == []
    assert report["status"] == "passed"
    assert report["summary"]["feedback_loop_case_count"] == 4
    assert report["summary"]["accepted_feedback_count"] == 3
    assert report["summary"]["rejected_feedback_count"] == 1
    assert report["summary"]["closed_feedback_count"] == 4
    assert report["summary"]["unresolved_feedback_count"] == 0
    assert report["summary"]["open_next_action_count"] == 0
    assert {record["feedback_run_id"] for record in report["feedback_records"] if record["decision_status"] == "accepted"}
    assert all(record["target_run_id"] for record in report["feedback_records"])
    assert all(record["roadmap_refs"] for record in report["feedback_records"])
    assert all("decision_namespace" in record for record in report["feedback_records"])
    assert all(isinstance(record["next_action"], dict) for record in report["feedback_records"])
    assert all(record["linked_run"]["found"] is True for record in report["feedback_records"])


def test_triage_dashboard_rejects_accepted_feedback_without_closure() -> None:
    closure = copy.deepcopy(closure_report())
    closure["founder_feedback_closures"] = [
        item for item in closure["founder_feedback_closures"] if item["case_id"] != "FL125-001"
    ]

    report = project_dashboard(closure_payload=closure)

    assert report["status"] == "failed"
    assert report["summary"]["blocker_count"] == 1
    assert any("feedback_loop[FL125-001]: accepted feedback missing closure record" in error for error in report["errors"])


def test_triage_dashboard_rejects_feedback_run_id_mismatch() -> None:
    feedback = copy.deepcopy(feedback_report())
    first = feedback["cases"][0]
    first["feedback_record"]["run_id"] = "workflow-feedback-other"

    report = project_dashboard(feedback_payload=feedback)

    assert report["status"] == "failed"
    assert any("feedback_run_id does not match feedback_record.run_id" in error for error in report["errors"])


def test_triage_dashboard_rejects_unlinked_accepted_feedback() -> None:
    feedback = copy.deepcopy(feedback_report())
    first = feedback["cases"][0]
    first["feedback_record"]["linked_run"]["found"] = False

    report = project_dashboard(feedback_payload=feedback)

    assert report["status"] == "failed"
    assert any("accepted feedback linked target run was not found" in error for error in report["errors"])


def test_triage_dashboard_rejects_extra_closure_id() -> None:
    closure = copy.deepcopy(closure_report())
    extra = copy.deepcopy(closure["founder_feedback_closures"][0])
    extra["case_id"] = "FL125-extra"
    closure["founder_feedback_closures"].append(extra)

    report = project_dashboard(closure_payload=closure)

    assert report["status"] == "failed"
    assert any("extra closure ID has no current feedback case" in error for error in report["errors"])


def test_triage_dashboard_rejects_duplicate_feedback_run_id() -> None:
    feedback = copy.deepcopy(feedback_report())
    feedback["cases"][1]["decision"]["feedback_run_id"] = feedback["cases"][0]["decision"]["feedback_run_id"]
    feedback["cases"][1]["feedback_record"]["run_id"] = feedback["cases"][0]["decision"]["feedback_run_id"]

    report = project_dashboard(feedback_payload=feedback)

    assert report["status"] == "failed"
    assert any("duplicate feedback_run_id" in error for error in report["errors"])


def test_triage_dashboard_adds_next_action_for_actionable_smoke_feedback() -> None:
    smoke = copy.deepcopy(smoke_feedback_report())
    smoke["summary"]["classification_count"] = 1
    smoke["summary"]["actionable_feedback_count"] = 1
    smoke["classifications"] = [
        {
            "case_id": "P99",
            "status": "classified",
            "decision_kind": "repair_followup",
            "gap_class": "model_capability",
            "run_id": "workflow-router-smoke",
            "expected_workflow": "code_investigation.plan",
        }
    ]

    report = project_dashboard(smoke_payload=smoke)

    assert report["status"] == "passed"
    assert report["summary"]["smoke_actionable_feedback_count"] == 1
    assert report["summary"]["open_next_action_count"] == 1
    assert report["next_actions"][0]["source"] == "founder_smoke_feedback"
    assert "eval repair loop" in report["next_actions"][0]["action"].lower()


def test_triage_dashboard_rejects_actionable_smoke_without_run_id() -> None:
    smoke = copy.deepcopy(smoke_feedback_report())
    smoke["summary"]["classification_count"] = 1
    smoke["summary"]["actionable_feedback_count"] = 1
    smoke["classifications"] = [
        {
            "case_id": "P99",
            "status": "classified",
            "decision_kind": "repair_followup",
            "gap_class": "model_capability",
            "expected_workflow": "code_investigation.plan",
        }
    ]

    report = project_dashboard(smoke_payload=smoke)

    assert report["status"] == "failed"
    assert any("actionable smoke feedback missing source run_id" in error for error in report["errors"])


def test_triage_dashboard_rejects_failed_source_artifact() -> None:
    feedback = copy.deepcopy(feedback_report())
    feedback["status"] = "failed"

    report = project_dashboard(feedback_payload=feedback)

    assert report["status"] == "failed"
    assert "founder_feedback_loop_report.status must be passed" in report["errors"]


def test_triage_dashboard_rejects_hidden_summary_change() -> None:
    report = project_dashboard()
    report["summary"]["open_next_action_count"] = 99

    errors = validate_dashboard(report)

    assert "report.summary must match rebuilt founder feedback triage dashboard" in errors
