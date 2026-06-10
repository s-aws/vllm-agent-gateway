from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.stable_release_blocker_closure import (
    build_stable_release_blocker_closure_report,
    read_json_object,
    validate_policy,
    validate_stable_release_blocker_closure_report,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "stable_release_blocker_closure_policy.json"
PROMPT_REPORT_PATH = (
    REPO_ROOT
    / "runtime-state"
    / "prompt-tightening-recommendations"
    / "phase128"
    / "phase128-prompt-tightening-recommendations-report.json"
)
FOUNDER_REPORT_PATH = REPO_ROOT / "runtime-state" / "founder-feedback-loop" / "phase125-founder-feedback-loop-live.json"
FOUNDER_CASES_PATH = REPO_ROOT / "runtime" / "founder_feedback_loop_cases.json"


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def prompt_report() -> dict[str, Any]:
    return read_json_object(PROMPT_REPORT_PATH)


def founder_report() -> dict[str, Any]:
    return read_json_object(FOUNDER_REPORT_PATH)


def founder_cases() -> dict[str, Any]:
    return read_json_object(FOUNDER_CASES_PATH)


def project_report(
    *,
    policy_payload: dict[str, Any] | None = None,
    prompt_payload: dict[str, Any] | None = None,
    founder_payload: dict[str, Any] | None = None,
    founder_cases_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_stable_release_blocker_closure_report(
        policy=policy_payload or policy(),
        prompt_report=prompt_payload or prompt_report(),
        founder_report=founder_payload or founder_report(),
        founder_cases_catalog=founder_cases_payload or founder_cases(),
        policy_path=POLICY_PATH,
        prompt_report_path=PROMPT_REPORT_PATH,
        founder_report_path=FOUNDER_REPORT_PATH,
        founder_cases_path=FOUNDER_CASES_PATH,
    )


def validate_report(
    report: dict[str, Any],
    *,
    policy_payload: dict[str, Any] | None = None,
    prompt_payload: dict[str, Any] | None = None,
    founder_payload: dict[str, Any] | None = None,
    founder_cases_payload: dict[str, Any] | None = None,
) -> list[str]:
    return validate_stable_release_blocker_closure_report(
        report,
        policy=policy_payload or policy(),
        prompt_report=prompt_payload or prompt_report(),
        founder_report=founder_payload or founder_report(),
        founder_cases_catalog=founder_cases_payload or founder_cases(),
        policy_path=POLICY_PATH,
        prompt_report_path=PROMPT_REPORT_PATH,
        founder_report_path=FOUNDER_REPORT_PATH,
        founder_cases_path=FOUNDER_CASES_PATH,
    )


def test_project_stable_release_blocker_closure_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_project_stable_release_blocker_closure_report_passes() -> None:
    report = project_report()
    assert validate_report(report) == []
    assert report["status"] == "passed"
    assert report["summary"]["prompt_tightening_blocker_count"] == 1
    assert report["summary"]["prompt_tightening_closed_count"] == 1
    assert report["summary"]["founder_feedback_blocker_count"] == 3
    assert report["summary"]["founder_feedback_closed_count"] == 3
    assert report["summary"]["unresolved_blocker_count"] == 0


def test_closure_rejects_missing_prompt_tightening_candidate_closure() -> None:
    broken = policy()
    broken["prompt_tightening_closures"] = []
    report = project_report(policy_payload=broken)
    errors = validate_report(report, policy_payload=broken)
    assert any("unresolved_blocker_count must be 0" in error for error in errors)
    assert any("missing prompt-tightening closure" in error for error in report["errors"])


def test_closure_rejects_prompt_catalog_mutation() -> None:
    broken = policy()
    broken["prompt_tightening_closures"][0]["prompt_catalog_changed"] = True
    report = project_report(policy_payload=broken)
    assert any("prompt catalog must not change" in error for error in report["errors"])


def test_closure_rejects_short_rationale() -> None:
    broken = policy()
    broken["founder_feedback_closures"][0]["rationale"] = "synthetic"
    report = project_report(policy_payload=broken)
    assert any("closure rationale must explain the decision" in error for error in report["errors"])


def test_closure_rejects_missing_founder_feedback_case_closure() -> None:
    broken = policy()
    broken["founder_feedback_closures"] = broken["founder_feedback_closures"][1:]
    report = project_report(policy_payload=broken)
    assert any("founder_feedback_closures[FL125-001]: missing founder-feedback closure" in error for error in report["errors"])


def test_closure_rejects_synthetic_fixture_without_explicit_non_production_boundary() -> None:
    broken = policy()
    broken["founder_feedback_closures"][0]["rationale"] = (
        "This synthetic fixture proves the feedback decision path and should be closed by the release gate."
    )
    report = project_report(policy_payload=broken)
    assert any("not production founder feedback" in error for error in report["errors"])


def test_closure_rejects_prompt_rejection_with_unresolved_findings() -> None:
    prompt = copy.deepcopy(prompt_report())
    prompt["candidates"][0]["unresolved_findings"] = [{"severity": "medium", "message": "needs work"}]
    report = project_report(prompt_payload=prompt)
    assert any("cannot reject prompt-tightening candidate while unresolved findings remain" in error for error in report["errors"])


def test_closure_rejects_extra_prompt_closure_id() -> None:
    broken = policy()
    broken["prompt_tightening_closures"].append(
        {
            "candidate_id": "PTR-extra",
            "closure_status": "rejected",
            "prompt_catalog_changed": False,
            "rationale": "This extra closure is not tied to a current blocker and must fail closed.",
        }
    )
    report = project_report(policy_payload=broken)
    assert any("PTR-extra" in error and "extra closure ID" in error for error in report["errors"])


def test_closure_rejects_extra_founder_feedback_closure_id() -> None:
    broken = policy()
    broken["founder_feedback_closures"].append(
        {
            "case_id": "FL125-999",
            "closure_status": "closed_as_synthetic_fixture",
            "required_gate": "baseline_corpus",
            "rationale": "This synthetic closure is not production founder feedback but the case is not a current blocker.",
        }
    )
    report = project_report(policy_payload=broken)
    assert any("FL125-999" in error and "extra closure ID" in error for error in report["errors"])


def test_closure_rejects_prompt_rejection_with_active_drift() -> None:
    prompt = copy.deepcopy(prompt_report())
    prompt["candidates"][0]["fresh_drift_context"]["drift_severity"] = "watch"
    report = project_report(prompt_payload=prompt)
    assert any("cannot reject prompt-tightening candidate with active fresh drift" in error for error in report["errors"])


def test_closure_rejects_prompt_rejection_with_baseline_failure_trigger() -> None:
    prompt = copy.deepcopy(prompt_report())
    prompt["candidates"][0]["trigger_reasons"] = ["baseline_failure", "low_confidence_pass"]
    report = project_report(prompt_payload=prompt)
    assert any("requires only low_confidence_pass" in error for error in report["errors"])


def test_closure_rejects_prompt_report_catalog_mutation() -> None:
    prompt = copy.deepcopy(prompt_report())
    prompt["summary"]["applied_prompt_catalog_change_count"] = 1
    report = project_report(prompt_payload=prompt)
    assert any("applied_prompt_catalog_change_count must be 0" in error for error in report["errors"])


def test_closure_rejects_synthetic_founder_feedback_not_in_fixture_catalog() -> None:
    cases = copy.deepcopy(founder_cases())
    cases["cases"] = [case for case in cases["cases"] if case["case_id"] != "FL125-001"]
    report = project_report(founder_cases_payload=cases)
    assert any("governed Phase 125 fixture case" in error for error in report["errors"])


def test_closure_rejects_synthetic_founder_feedback_decision_kind_mismatch() -> None:
    cases = copy.deepcopy(founder_cases())
    cases["cases"][0]["expected_decision_kind"] = "holdout_prompt_candidate"
    report = project_report(founder_cases_payload=cases)
    assert any("decision kind must match fixture catalog" in error for error in report["errors"])


def test_closure_rejects_accepted_prompt_without_rerun_proof() -> None:
    broken = policy()
    broken["prompt_tightening_closures"][0]["closure_status"] = "accepted_with_rerun_proof"
    report = project_report(policy_payload=broken)
    assert any("requires target and holdout rerun proof" in error for error in report["errors"])
