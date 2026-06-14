from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.route_stability_holdout_replay import (
    DEFAULT_POLICY_PATH,
    RouteStabilityHoldoutReplayConfig,
    build_replay_cases,
    compare_replay_result,
    read_json_object,
    validate_live_result_coverage,
    validate_matrix_source_report,
    validate_phase204_source_report,
    validate_policy,
    validate_route_stability_holdout_replay,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def policy() -> dict:
    return read_json_object(REPO_ROOT / DEFAULT_POLICY_PATH)


def phase204_report() -> dict:
    return read_json_object(REPO_ROOT / "runtime-state/phase204/phase204-no-manual-skill-injection-explainability-report.json")


def selector_contract_policy() -> dict:
    return read_json_object(REPO_ROOT / "runtime/no_manual_skill_injection_explainability_policy.json")


def matrix_report() -> dict:
    return read_json_object(REPO_ROOT / "runtime-state/phase203/phase203-workflow-skill-tool-selection-matrix-report.json")


def prompt_catalog(path: str) -> dict:
    return read_json_object(REPO_ROOT / path)


def test_phase205_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase205_preflight_builds_target_and_holdout_cases(tmp_path: Path) -> None:
    report = validate_route_stability_holdout_replay(
        RouteStabilityHoldoutReplayConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase205-preflight.json",
        )
    )

    assert report["status"] == "preflight_passed"
    assert report["summary"]["target_case_count"] == 33
    assert report["summary"]["holdout_case_count"] == 4
    assert report["summary"]["phase206_ready"] is False


def test_phase205_policy_rejects_missing_holdout_cases() -> None:
    mutated = copy.deepcopy(policy())
    mutated["holdout_case_ids"] = []

    errors = validate_policy(mutated)

    assert "policy.holdout_case_ids below policy.minimum_holdout_case_count" in errors


def test_phase205_policy_rejects_missing_holdout_exact_signature() -> None:
    mutated = copy.deepcopy(policy())
    del mutated["holdout_expected_signatures"]["P13"]

    errors = validate_policy(mutated)

    assert "policy.holdout_expected_signatures.P13 must contain a full route signature" in errors


def test_phase205_policy_rejects_wrong_required_live_response_count() -> None:
    mutated = copy.deepcopy(policy())
    mutated["required_live_response_count"] = 72

    errors = validate_policy(mutated)

    assert "policy.required_live_response_count must equal target plus holdout cases times required surfaces" in errors


def test_phase205_replays_target_prompt_from_phase204_report_not_current_catalog() -> None:
    mutated_report = copy.deepcopy(phase204_report())
    mutated_report["phase_cases"][0]["prompt"] = "PHASE204_SENTINEL_PROMPT"

    replay_cases, errors = build_replay_cases(
        policy=policy(),
        phase204_report=mutated_report,
        matrix_report=matrix_report(),
        target_catalog=prompt_catalog("runtime/prompt_catalogs/founder_field_v1.json"),
        holdout_catalog=prompt_catalog("runtime/prompt_catalogs/semi_well_defined_v1.json"),
    )

    assert errors == []
    assert replay_cases[0]["prompt"] == "PHASE204_SENTINEL_PROMPT"


def test_phase205_rejects_stale_phase204_report_shape() -> None:
    mutated_report = copy.deepcopy(phase204_report())
    mutated_report["phase"] = 999

    errors = validate_phase204_source_report(mutated_report, selector_contract_policy())

    assert any("phase204 report invalid: report.phase must be 204" in error for error in errors)


def test_phase205_rejects_phase204_source_report_with_errors() -> None:
    mutated_report = copy.deepcopy(phase204_report())
    mutated_report["errors"] = ["should not be accepted"]

    errors = validate_phase204_source_report(mutated_report, selector_contract_policy())

    assert "phase204 report must not contain errors" in errors


def test_phase205_rejects_failed_matrix_source_report() -> None:
    mutated_matrix = copy.deepcopy(matrix_report())
    mutated_matrix["status"] = "failed"
    mutated_matrix["validation_errors"] = ["broken matrix"]
    mutated_matrix["summary"]["validation_error_count"] = 1

    errors = validate_matrix_source_report(mutated_matrix)

    assert "matrix report status must be passed" in errors
    assert "matrix report validation_errors must be empty" in errors
    assert "matrix report summary.validation_error_count must be 0" in errors


def test_phase205_rejects_holdout_signature_extra_skill_tool() -> None:
    mutated_policy = copy.deepcopy(policy())
    mutated_policy["holdout_expected_signatures"]["P13"]["selected_skills"].append("unregistered-extra-skill")
    mutated_policy["holdout_expected_signatures"]["P13"]["selected_tools"].append("unregistered_extra_tool")

    _, errors = build_replay_cases(
        policy=mutated_policy,
        phase204_report=phase204_report(),
        matrix_report=matrix_report(),
        target_catalog=prompt_catalog("runtime/prompt_catalogs/founder_field_v1.json"),
        holdout_catalog=prompt_catalog("runtime/prompt_catalogs/semi_well_defined_v1.json"),
    )

    assert any("skill_selection_drift" in error for error in errors)
    assert any("tool_selection_drift" in error for error in errors)


def test_phase205_compare_replay_result_detects_target_skill_drift() -> None:
    item = {
        "case_id": "P01",
        "surface": "gateway",
        "status": "passed",
        "replay_set": "target",
        "selected_workflow": "code_investigation.plan",
        "selected_skills": ["wrong-skill"],
        "selected_tools": ["git_grep", "read_file", "structure_index"],
        "route_rules": ["l1_find_behavior_start_terms"],
    }
    baseline = {
        ("P01", "gateway"): {
            "selected_workflow": "code_investigation.plan",
            "selected_skills": ["entrypoint-finder"],
            "selected_tools": ["git_grep", "read_file", "structure_index"],
            "route_rules": ["l1_find_behavior_start_terms"],
        }
    }

    errors = compare_replay_result(item=item, phase204_signatures=baseline)

    assert any("skill_selection_drift" in error for error in errors)


def test_phase205_compare_replay_result_detects_target_extra_route_rule_drift() -> None:
    item = {
        "case_id": "P01",
        "surface": "gateway",
        "status": "passed",
        "run_id": "workflow-router-test",
        "replay_set": "target",
        "selected_workflow": "code_investigation.plan",
        "selected_skills": ["entrypoint-finder"],
        "selected_tools": ["git_grep", "read_file", "structure_index"],
        "route_rules": ["l1_find_behavior_start_terms", "unexpected_rule"],
    }
    baseline = {
        ("P01", "gateway"): {
            "selected_workflow": "code_investigation.plan",
            "selected_skills": ["entrypoint-finder"],
            "selected_tools": ["git_grep", "read_file", "structure_index"],
            "route_rules": ["l1_find_behavior_start_terms"],
        }
    }

    errors = compare_replay_result(item=item, phase204_signatures=baseline)

    assert any("route_rule_drift" in error for error in errors)


def test_phase205_compare_replay_result_detects_holdout_route_rule_drift() -> None:
    item = {
        "case_id": "H-P13",
        "surface": "gateway",
        "status": "passed",
        "run_id": "workflow-router-test",
        "replay_set": "holdout",
        "expected_holdout_signature": {
            "selected_workflow": "code_investigation.plan",
            "route_rules": ["l1_coverage_gap_summary_terms"],
            "selected_skills": ["coverage-gap-summarizer"],
            "selected_tools": ["git_grep", "read_file", "structure_index"],
        },
        "selected_workflow": "code_investigation.plan",
        "selected_skills": ["coverage-gap-summarizer"],
        "selected_tools": ["git_grep", "read_file", "structure_index"],
        "route_rules": ["l1_documentation_lookup_terms"],
    }

    errors = compare_replay_result(item=item, phase204_signatures={})

    assert any("route_rule_drift" in error for error in errors)


def test_phase205_compare_replay_result_detects_holdout_extra_skill_drift() -> None:
    item = {
        "case_id": "H-P13",
        "surface": "gateway",
        "status": "passed",
        "run_id": "workflow-router-test",
        "replay_set": "holdout",
        "expected_holdout_signature": {
            "selected_workflow": "code_investigation.plan",
            "route_rules": ["l1_coverage_gap_summary_terms"],
            "selected_skills": ["coverage-gap-summarizer"],
            "selected_tools": ["git_grep", "read_file", "structure_index"],
        },
        "selected_workflow": "code_investigation.plan",
        "selected_skills": ["coverage-gap-summarizer", "unexpected-skill"],
        "selected_tools": ["git_grep", "read_file", "structure_index"],
        "route_rules": ["l1_coverage_gap_summary_terms"],
    }

    errors = compare_replay_result(item=item, phase204_signatures={})

    assert any("skill_selection_drift" in error for error in errors)


def test_phase205_compare_replay_result_detects_missing_run_id() -> None:
    item = {
        "case_id": "P01",
        "surface": "gateway",
        "status": "passed",
        "run_id": "unknown",
        "replay_set": "target",
        "selected_workflow": "code_investigation.plan",
        "selected_skills": ["entrypoint-finder"],
        "selected_tools": ["git_grep", "read_file", "structure_index"],
        "route_rules": ["l1_find_behavior_start_terms"],
    }
    baseline = {
        ("P01", "gateway"): {
            "selected_workflow": "code_investigation.plan",
            "selected_skills": ["entrypoint-finder"],
            "selected_tools": ["git_grep", "read_file", "structure_index"],
            "route_rules": ["l1_find_behavior_start_terms"],
        }
    }

    errors = compare_replay_result(item=item, phase204_signatures=baseline)

    assert any("missing_run_id" in error for error in errors)


def test_phase205_live_coverage_requires_exact_response_cardinality() -> None:
    replay_cases = [{"case_id": "P01", "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github"}]
    results = [
        {
            "case_id": "P01",
            "surface": "gateway",
            "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
            "run_id": "workflow-router-test",
        }
    ]

    errors = validate_live_result_coverage(policy=policy(), replay_cases=replay_cases, results=results)

    assert any("response_count 1 must equal required case/surface pair count 2" in error for error in errors)
