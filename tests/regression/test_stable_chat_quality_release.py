from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.stable_chat_quality_release import (
    EXPECTED_GATE_ORDER,
    ChatQualityReadiness,
    StableChatQualityReleaseStatus,
    build_stable_chat_quality_release_report,
    gate_policy_by_id,
    read_json_object,
    resolve_path,
    validate_policy,
    validate_stable_chat_quality_release_report,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "stable_chat_quality_release_policy.json"


def project_inputs() -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Path]]:
    policy = read_json_object(POLICY_PATH)
    gate_map = gate_policy_by_id(policy)
    gate_paths = {
        gate_id: resolve_path(REPO_ROOT, gate_map[gate_id]["path"])
        for gate_id in EXPECTED_GATE_ORDER
    }
    gate_payloads = {gate_id: read_json_object(path) for gate_id, path in gate_paths.items()}
    return policy, gate_payloads, gate_paths


def project_report(
    *,
    policy: dict[str, Any] | None = None,
    gate_payloads: dict[str, dict[str, Any]] | None = None,
    missing_gates: set[str] | None = None,
) -> dict[str, Any]:
    loaded_policy, loaded_payloads, gate_paths = project_inputs()
    return build_stable_chat_quality_release_report(
        config_root=REPO_ROOT,
        policy=policy or loaded_policy,
        gate_payloads=gate_payloads or loaded_payloads,
        gate_paths=gate_paths,
        missing_gates=missing_gates,
        policy_path=POLICY_PATH,
        require_artifacts=True,
    )


def validate_report(
    report: dict[str, Any],
    *,
    policy: dict[str, Any] | None = None,
    gate_payloads: dict[str, dict[str, Any]] | None = None,
    missing_gates: set[str] | None = None,
) -> list[str]:
    loaded_policy, loaded_payloads, gate_paths = project_inputs()
    return validate_stable_chat_quality_release_report(
        report,
        policy=policy or loaded_policy,
        gate_payloads=gate_payloads or loaded_payloads,
        gate_paths=gate_paths,
        config_root=REPO_ROOT,
        missing_gates=missing_gates,
        policy_path=POLICY_PATH,
        require_artifacts=True,
    )


def cleared_payloads() -> dict[str, dict[str, Any]]:
    _policy, payloads, _paths = project_inputs()
    cleared = copy.deepcopy(payloads)
    prompt_summary = cleared["prompt_tightening_recommendations"]["summary"]
    prompt_summary["candidate_count"] = 0
    prompt_summary["decision_status_counts"] = {"accepted": 0, "pending_review": 0, "rejected": 0}
    prompt_summary["suggestion_class_counts"] = {}
    prompt_summary["trigger_reason_counts"] = {}
    cleared["prompt_tightening_recommendations"]["candidates"] = []
    for case in cleared["founder_feedback_loop"]["cases"]:
        decision = case.get("decision")
        if isinstance(decision, dict) and decision.get("decision_status") == "accepted":
            decision["validation_result"] = {"required_gate": "synthetic", "status": "passed"}
    return cleared


def test_project_stable_chat_quality_release_policy_passes() -> None:
    policy, _payloads, _paths = project_inputs()
    assert validate_policy(policy) == []


def test_project_release_report_passes_with_phase131_blocker_closure() -> None:
    report = project_report()
    errors = validate_report(report)
    assert errors == []
    assert report["status"] == StableChatQualityReleaseStatus.PASSED.value
    assert report["readiness"] == ChatQualityReadiness.READY_FOR_FOUNDER_TESTING.value
    assert report["summary"]["blocker_count"] == 0


def test_release_report_blocks_without_phase131_blocker_closure() -> None:
    _policy, payloads, _paths = project_inputs()
    without_closure = copy.deepcopy(payloads)
    without_closure["stable_release_blocker_closure"] = {}
    report = project_report(
        gate_payloads=without_closure,
        missing_gates={"stable_release_blocker_closure"},
    )
    errors = validate_report(
        report,
        gate_payloads=without_closure,
        missing_gates={"stable_release_blocker_closure"},
    )
    assert errors == []
    assert report["status"] == StableChatQualityReleaseStatus.FAILED.value
    assert report["readiness"] == ChatQualityReadiness.BLOCKED.value
    assert any("stable_release_blocker_closure.artifact is missing" in error for error in report["errors"])


def test_release_report_becomes_ready_when_synthetic_blockers_are_cleared() -> None:
    payloads = cleared_payloads()
    report = project_report(gate_payloads=payloads)
    errors = validate_report(report, gate_payloads=payloads)
    assert errors == []
    assert report["status"] == StableChatQualityReleaseStatus.PASSED.value
    assert report["readiness"] == ChatQualityReadiness.READY_FOR_FOUNDER_TESTING.value
    assert report["summary"]["blocker_count"] == 0


def test_release_report_rejects_hidden_blockers() -> None:
    _policy, payloads, _paths = project_inputs()
    mutated = copy.deepcopy(payloads)
    mutated["priority0_gap_taxonomy"]["summary"]["finding_count"] = 1
    report = project_report(gate_payloads=mutated)
    report["status"] = StableChatQualityReleaseStatus.PASSED.value
    report["readiness"] = ChatQualityReadiness.READY_FOR_FOUNDER_TESTING.value
    report["errors"] = []
    report["summary"]["blocker_count"] = 0
    errors = validate_report(report, gate_payloads=mutated)
    assert any("must match rebuilt release evidence" in error for error in errors)


def test_release_report_rejects_stale_artifact_hash() -> None:
    report = project_report()
    report["gate_results"][0]["artifact_sha256"] = "0" * 64
    errors = validate_report(report)
    assert any("report.gate_results must match rebuilt release evidence" in error for error in errors)


def test_release_report_blocks_stale_closure_source_hash() -> None:
    _policy, payloads, _paths = project_inputs()
    mutated = copy.deepcopy(payloads)
    mutated["stable_release_blocker_closure"]["prompt_tightening_report_sha256"] = "0" * 64
    report = project_report(gate_payloads=mutated)
    assert any("stable_release_blocker_closure.prompt_tightening_report_sha256" in error for error in report["errors"])


def test_release_report_blocks_missing_required_artifact() -> None:
    report = project_report(missing_gates={"holdout_prompt_bank"})
    errors = validate_report(report, missing_gates={"holdout_prompt_bank"})
    assert errors == []
    assert report["status"] == StableChatQualityReleaseStatus.FAILED.value
    assert any("holdout_prompt_bank.artifact is missing" in error for error in report["errors"])


def test_release_report_blocks_priority0_gap_findings() -> None:
    _policy, payloads, _paths = project_inputs()
    mutated = copy.deepcopy(payloads)
    mutated["priority0_gap_taxonomy"]["summary"]["finding_count"] = 1
    mutated["priority0_gap_taxonomy"]["summary"]["highest_severity"] = "high"
    report = project_report(gate_payloads=mutated)
    assert any("priority0_gap_taxonomy.summary.finding_count must be 0" in error for error in report["errors"])
    assert report["readiness"] == ChatQualityReadiness.BLOCKED.value


def test_release_report_blocks_skill_tool_gap_candidates() -> None:
    _policy, payloads, _paths = project_inputs()
    mutated = copy.deepcopy(payloads)
    summary = mutated["skill_tool_coverage_gap"]["summary"]
    summary["new_capability_required"] = True
    summary["gap_candidate_count"] = 1
    report = project_report(gate_payloads=mutated)
    assert any("skill_tool_coverage_gap.summary.new_capability_required must be false" in error for error in report["errors"])


def test_release_report_blocks_output_format_route_failure() -> None:
    _policy, payloads, _paths = project_inputs()
    mutated = copy.deepcopy(payloads)
    first_case = mutated["output_format_parity"]["cases"][0]
    first_case["responses"]["gateway"]["status"] = "failed"
    report = project_report(gate_payloads=mutated)
    assert any("output_format_parity.cases" in error and "status must be passed" in error for error in report["errors"])


def test_release_report_blocks_ui_missing_marker() -> None:
    _policy, payloads, _paths = project_inputs()
    mutated = copy.deepcopy(payloads)
    first_case = mutated["anythingllm_ui_e2e"]["ui"]["cases"][0]
    first_case["missing_required_markers"] = ["Source mutation: false"]
    report = project_report(gate_payloads=mutated)
    assert any("anythingllm_ui_e2e.ui.cases" in error and "missing_required_markers" in error for error in report["errors"])
