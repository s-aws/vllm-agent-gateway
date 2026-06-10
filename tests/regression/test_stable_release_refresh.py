from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.stable_release_refresh import (
    DEFAULT_POLICY_PATH,
    REFRESH_OUTPUTS,
    build_stable_release_refresh_report,
    read_json_object,
    validate_policy,
    validate_stable_release_refresh_report,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH
PHASE170_POLICY_PATH = REPO_ROOT / "runtime" / "stable_release_refresh_phase170_policy.json"
REQUIRED_COMMANDS = [
    "stable_chat_quality_release",
    "stable_release_reset_rehearsal",
    "model_swap_smoke_probe",
    "v1_product_readiness_review",
    "v1_stable_release_decision",
]
REQUIRED_LIMITATIONS = [
    "not_production_deployment",
    "not_advanced_broad_refactor_orchestration",
    "not_every_repository_language_or_coding_task",
    "not_direct_mutation_of_protected_fixtures",
    "not_unsupported_output_format_parity",
    "not_automatic_model_selection",
]


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def phase170_policy() -> dict[str, Any]:
    return read_json_object(PHASE170_POLICY_PATH)


def payloads() -> dict[str, dict[str, Any]]:
    return {
        "stable_chat_quality_release": {
            "kind": "stable_chat_quality_release_report",
            "phase": 130,
            "status": "passed",
            "readiness": "ready_for_founder_testing",
            "summary": {"readiness": "ready_for_founder_testing"},
            "errors": [],
        },
        "stable_release_reset_rehearsal": {
            "kind": "stable_release_reset_rehearsal_report",
            "phase": 153,
            "status": "passed",
            "summary": {"failed_check_ids": []},
            "errors": [],
        },
        "model_swap_smoke_probe": {
            "kind": "model_swap_smoke_probe_report",
            "phase": 154,
            "status": "passed",
            "decision": {
                "decision": "current_model_ready",
                "actual_model_ids": ["Qwen3-Coder-30B-A3B-Instruct"],
                "full_drift_gate_required": False,
            },
            "summary": {"decision": "current_model_ready"},
            "errors": [],
        },
        "v1_product_readiness_review": {
            "kind": "v1_product_readiness_review_report",
            "phase": 155,
            "status": "passed",
            "recommendation": "go_for_founder_testing",
            "summary": {"recommendation": "go_for_founder_testing"},
            "release_blockers": [],
        },
        "v1_stable_release_decision": {
            "kind": "v1_stable_release_decision_report",
            "phase": 156,
            "status": "passed",
            "decision": "release_for_founder_testing",
            "release_limitations": REQUIRED_LIMITATIONS,
            "summary": {"decision": "release_for_founder_testing"},
        },
        "founder_field_round1": {
            "kind": "founder_field_round1_report",
            "phase": 157,
            "status": "passed",
            "summary": {
                "case_count": 30,
                "advisory_case_count": 14,
                "target_roots": [
                    "/mnt/c/coinbase_testing_repo_frozen_tmp",
                    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
                ],
                "blocker_case_count": 0,
            },
            "validation_errors": [],
        },
        "transcript_quality_feedback_intake": {
            "kind": "transcript_quality_feedback_intake_report",
            "phase": 158,
            "status": "passed",
            "summary": {"source_case_count": 30, "accepted_finding_count": 14, "phase159_eligible_count": 0},
            "validation_errors": [],
        },
        "priority0_repair_loop": {
            "kind": "priority0_repair_loop_report",
            "phase": 159,
            "status": "passed",
            "repair_mode": "no_repair_required",
            "summary": {"phase159_eligible_count": 0, "monitoring_only_count": 14, "open_repair_count": 0},
            "validation_errors": [],
        },
    }


def phase170_payloads() -> dict[str, dict[str, Any]]:
    all_payloads = payloads()
    all_payloads.update(
        {
            "post_restart_runtime_readiness_phase163": {
                "kind": "post_restart_runtime_readiness_report",
                "phase": 163,
                "status": "passed",
                "decision": "ready_after_restart",
                "summary": {
                    "covered_surface_count": 16,
                    "required_surface_count": 16,
                    "missing_required_surface_count": 0,
                },
                "errors": [],
            },
            "founder_field_round2": {
                "kind": "founder_field_round2_report",
                "phase": 164,
                "status": "passed",
                "summary": {
                    "case_count": 16,
                    "classification_counts": {"blocker": 0, "pass": 16},
                    "min_score": 85,
                    "target_roots": [
                        "/mnt/c/coinbase_testing_repo_frozen_tmp",
                        "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
                    ],
                },
                "validation_errors": [],
            },
            "prompt_advisory_closure": {
                "kind": "prompt_advisory_closure_report",
                "phase": 165,
                "status": "passed",
                "summary": {"product_gap_escalation_count": 6, "validation_error_count": 0},
                "validation_errors": [],
            },
            "generic_chat_vague_prompt_contract": {
                "kind": "generic_chat_vague_prompt_contract_report",
                "phase": 166,
                "status": "passed",
                "summary": {"failed_case_count": 0, "fixture_state_changed": False, "target_root_count": 2},
                "validation_errors": [],
            },
            "anythingllm_ui_replay_phase167": {
                "kind": "anythingllm_ui_e2e_report",
                "status": "passed",
                "fixture_unchanged": True,
                "ui": {"status": "passed", "cases": [{"status": "passed"} for _ in range(11)]},
                "validation_errors": [],
            },
            "answer_first_ui_replay_phase168": {
                "kind": "anythingllm_ui_e2e_report",
                "status": "passed",
                "fixture_unchanged": True,
                "ui": {"status": "passed", "cases": [{"status": "passed"} for _ in range(11)]},
                "validation_errors": [],
            },
            "post_restart_runtime_readiness_phase168": {
                "kind": "post_restart_runtime_readiness_report",
                "phase": 163,
                "status": "passed",
                "decision": "ready_after_restart",
                "summary": {"missing_required_surface_count": 0},
                "errors": [],
            },
            "failure_to_roadmap_phase169": {
                "kind": "failure_to_roadmap_report",
                "phase": 169,
                "status": "passed",
                "summary": {
                    "proposal_count": 6,
                    "unapproved_proposal_count": 6,
                    "release_blocker_count": 0,
                    "roadmap_mutation_allowed": False,
                    "source_mutation_allowed": False,
                },
                "errors": [],
            },
            "release_notes_phase169": {
                "kind": "release_notes_validation_report",
                "phase": 146,
                "status": "passed",
                "summary": {"error_count": 0, "stable_blocker_count": 0},
                "errors": [],
            },
        }
    )
    return all_payloads


def sources(tmp_path: Path, payload_overrides: dict[str, dict[str, Any]] | None = None) -> dict[str, tuple[Path, dict[str, Any]]]:
    all_payloads = payloads()
    for key, value in (payload_overrides or {}).items():
        all_payloads[key] = value
    result: dict[str, tuple[Path, dict[str, Any]]] = {}
    for key, payload in all_payloads.items():
        path = tmp_path / f"{key}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        result[key] = (path, payload)
    return result


def phase170_sources(
    tmp_path: Path,
    payload_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, tuple[Path, dict[str, Any]]]:
    all_payloads = phase170_payloads()
    for key, value in (payload_overrides or {}).items():
        all_payloads[key] = value
    result: dict[str, tuple[Path, dict[str, Any]]] = {}
    for key, payload in all_payloads.items():
        path = tmp_path / f"{key}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        result[key] = (path, payload)
    return result


def refresh_results(overrides: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    result = [
        {
            "id": command_id,
            "command": ["python3", f"scripts/{command_id}.py"],
            "returncode": 0,
            "stdout_tail": "PASS",
            "stderr_tail": "",
            "outputs": [
                {"path": str(path), "exists": True, "sha256": "a" * 64}
                for path in REFRESH_OUTPUTS[command_id]
            ],
        }
        for command_id in REQUIRED_COMMANDS
    ]
    by_id = {item["id"]: item for item in result}
    for key, value in (overrides or {}).items():
        by_id[key].update(value)
    return list(by_id.values())


def build_report(
    tmp_path: Path,
    *,
    policy_payload: dict[str, Any] | None = None,
    source_overrides: dict[str, dict[str, Any]] | None = None,
    load_errors: list[str] | None = None,
    refresh_payload: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return build_stable_release_refresh_report(
        policy=policy_payload or policy(),
        sources=sources(tmp_path, source_overrides),
        load_errors=load_errors or [],
        refresh_results=refresh_payload if refresh_payload is not None else refresh_results(),
        policy_path=POLICY_PATH,
    )


def validate_report(
    tmp_path: Path,
    report: dict[str, Any],
    *,
    policy_payload: dict[str, Any] | None = None,
    source_overrides: dict[str, dict[str, Any]] | None = None,
    load_errors: list[str] | None = None,
    refresh_payload: list[dict[str, Any]] | None = None,
) -> list[str]:
    return validate_stable_release_refresh_report(
        report,
        policy=policy_payload or policy(),
        sources=sources(tmp_path, source_overrides),
        load_errors=load_errors or [],
        refresh_results=refresh_payload if refresh_payload is not None else refresh_results(),
        policy_path=POLICY_PATH,
    )


def build_phase170_report(
    tmp_path: Path,
    *,
    source_overrides: dict[str, dict[str, Any]] | None = None,
    refresh_payload: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return build_stable_release_refresh_report(
        policy=phase170_policy(),
        sources=phase170_sources(tmp_path, source_overrides),
        load_errors=[],
        refresh_results=refresh_payload if refresh_payload is not None else refresh_results(),
        policy_path=PHASE170_POLICY_PATH,
    )


def validate_phase170_report(
    tmp_path: Path,
    report: dict[str, Any],
    *,
    source_overrides: dict[str, dict[str, Any]] | None = None,
    refresh_payload: list[dict[str, Any]] | None = None,
) -> list[str]:
    return validate_stable_release_refresh_report(
        report,
        policy=phase170_policy(),
        sources=phase170_sources(tmp_path, source_overrides),
        load_errors=[],
        refresh_results=refresh_payload if refresh_payload is not None else refresh_results(),
        policy_path=PHASE170_POLICY_PATH,
    )


def test_project_stable_release_refresh_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_project_phase170_stable_release_refresh_policy_passes() -> None:
    assert validate_policy(phase170_policy()) == []


def test_stable_release_refresh_passes_with_current_contract(tmp_path: Path) -> None:
    report = build_report(tmp_path)

    assert validate_report(tmp_path, report) == []
    assert report["status"] == "passed"
    assert report["readiness"] == "ready_for_founder_testing"
    assert report["decision"] == "release_for_founder_testing"
    assert report["summary"]["refresh_command_count"] == 5
    assert report["summary"]["phase159_repair_mode"] == "no_repair_required"


def test_phase170_stable_release_refresh_passes_with_extended_chain(tmp_path: Path) -> None:
    report = build_phase170_report(tmp_path)

    assert validate_phase170_report(tmp_path, report) == []
    assert report["phase"] == 170
    assert report["priority_backlog_id"] == "P0-BB-034"
    assert report["status"] == "passed"
    assert report["summary"]["source_report_count"] == 17
    assert report["summary"]["phase169_proposal_count"] == 6
    assert report["summary"]["phase169_release_blocker_count"] == 0


def test_refresh_requires_command_results(tmp_path: Path) -> None:
    report = build_report(tmp_path, refresh_payload=[])

    assert report["status"] == "failed"
    assert any(error["id"] == "refresh_commands.ids" for error in report["validation_errors"])


def test_refresh_rejects_failed_command(tmp_path: Path) -> None:
    report = build_report(
        tmp_path,
        refresh_payload=refresh_results({"model_swap_smoke_probe": {"returncode": 1}}),
    )

    assert report["status"] == "failed"
    assert any("returncode" in error["id"] for error in report["validation_errors"])


def test_refresh_rejects_missing_output_hash(tmp_path: Path) -> None:
    results = refresh_results()
    results[0]["outputs"][0]["sha256"] = None
    report = build_report(tmp_path, refresh_payload=results)

    assert report["status"] == "failed"
    assert any("sha256" in error["id"] for error in report["validation_errors"])


def test_refresh_rejects_wrong_output_path_list(tmp_path: Path) -> None:
    results = refresh_results()
    results[0]["outputs"] = []
    report = build_report(tmp_path, refresh_payload=results)

    assert report["status"] == "failed"
    assert any("outputs" in error["id"] for error in report["validation_errors"])


def test_refresh_rejects_model_swap_drift_requirement(tmp_path: Path) -> None:
    model_swap = copy.deepcopy(payloads()["model_swap_smoke_probe"])
    model_swap["decision"]["full_drift_gate_required"] = True
    report = build_report(tmp_path, source_overrides={"model_swap_smoke_probe": model_swap})

    assert report["status"] == "failed"
    assert any("full_drift_gate_required" in error["id"] for error in report["validation_errors"])


def test_refresh_rejects_missing_model_swap_drift_schema(tmp_path: Path) -> None:
    model_swap = copy.deepcopy(payloads()["model_swap_smoke_probe"])
    del model_swap["decision"]["full_drift_gate_required"]
    report = build_report(tmp_path, source_overrides={"model_swap_smoke_probe": model_swap})

    assert report["status"] == "failed"
    assert any("full_drift_gate_required" in error["id"] for error in report["validation_errors"])


def test_refresh_rejects_wrong_model_identity(tmp_path: Path) -> None:
    model_swap = copy.deepcopy(payloads()["model_swap_smoke_probe"])
    model_swap["decision"]["actual_model_ids"] = ["other-model"]
    report = build_report(tmp_path, source_overrides={"model_swap_smoke_probe": model_swap})

    assert report["status"] == "failed"
    assert any("actual_model_ids" in error["id"] for error in report["validation_errors"])


def test_refresh_rejects_missing_frozen_fixture_coverage(tmp_path: Path) -> None:
    founder = copy.deepcopy(payloads()["founder_field_round1"])
    founder["summary"]["target_roots"] = ["/mnt/c/coinbase_testing_repo_frozen_tmp.github"]
    report = build_report(tmp_path, source_overrides={"founder_field_round1": founder})

    assert report["status"] == "failed"
    assert any("target_roots" in error["id"] for error in report["validation_errors"])


def test_refresh_rejects_blocked_phase159(tmp_path: Path) -> None:
    repair = copy.deepcopy(payloads()["priority0_repair_loop"])
    repair["status"] = "blocked"
    repair["repair_mode"] = "blocked_with_next_action"
    report = build_report(tmp_path, source_overrides={"priority0_repair_loop": repair})

    assert report["status"] == "failed"
    assert any("priority0_repair_loop.status_must_be_passed" in error["id"] for error in report["validation_errors"])
    assert any("priority0_repair_loop.repair_mode" in error["id"] for error in report["validation_errors"])


def test_refresh_rejects_phase158_phase159_eligible_mismatch(tmp_path: Path) -> None:
    intake = copy.deepcopy(payloads()["transcript_quality_feedback_intake"])
    intake["summary"]["phase159_eligible_count"] = 1
    report = build_report(tmp_path, source_overrides={"transcript_quality_feedback_intake": intake})

    assert report["status"] == "failed"
    assert any("eligible_count_mismatch" in error["id"] for error in report["validation_errors"])


def test_refresh_rejects_phase157_phase158_case_count_mismatch(tmp_path: Path) -> None:
    intake = copy.deepcopy(payloads()["transcript_quality_feedback_intake"])
    intake["summary"]["source_case_count"] = 29
    report = build_report(tmp_path, source_overrides={"transcript_quality_feedback_intake": intake})

    assert report["status"] == "failed"
    assert any("case_count_mismatch" in error["id"] for error in report["validation_errors"])


def test_refresh_rejects_phase159_monitoring_count_mismatch(tmp_path: Path) -> None:
    repair = copy.deepcopy(payloads()["priority0_repair_loop"])
    repair["summary"]["monitoring_only_count"] = 13
    report = build_report(tmp_path, source_overrides={"priority0_repair_loop": repair})

    assert report["status"] == "failed"
    assert any("monitoring_count_mismatch" in error["id"] for error in report["validation_errors"])


def test_refresh_rejects_phase159_open_repairs(tmp_path: Path) -> None:
    repair = copy.deepcopy(payloads()["priority0_repair_loop"])
    repair["summary"]["open_repair_count"] = 1
    report = build_report(tmp_path, source_overrides={"priority0_repair_loop": repair})

    assert report["status"] == "failed"
    assert any("open_repair_count" in error["id"] for error in report["validation_errors"])


def test_refresh_rejects_weakened_release_limitations(tmp_path: Path) -> None:
    decision = copy.deepcopy(payloads()["v1_stable_release_decision"])
    decision["release_limitations"] = REQUIRED_LIMITATIONS[:-1]
    report = build_report(tmp_path, source_overrides={"v1_stable_release_decision": decision})

    assert report["status"] == "failed"
    assert any("release_limitations" in error["id"] for error in report["validation_errors"])


def test_hidden_summary_edit_is_rejected_by_validation(tmp_path: Path) -> None:
    report = build_report(tmp_path)
    edited = copy.deepcopy(report)
    edited["summary"]["validation_error_count"] = 99

    assert validate_report(tmp_path, edited) == ["report must match rebuilt stable release refresh report"]


def test_phase170_rejects_failed_ui_replay_case(tmp_path: Path) -> None:
    ui_replay = copy.deepcopy(phase170_payloads()["answer_first_ui_replay_phase168"])
    ui_replay["ui"]["cases"][0]["status"] = "failed"
    report = build_phase170_report(tmp_path, source_overrides={"answer_first_ui_replay_phase168": ui_replay})

    assert report["status"] == "failed"
    assert any("answer_first_ui_replay_phase168.case_status" in error["id"] for error in report["validation_errors"])


def test_phase170_rejects_release_blocking_failure_to_roadmap_proposal(tmp_path: Path) -> None:
    failure_to_roadmap = copy.deepcopy(phase170_payloads()["failure_to_roadmap_phase169"])
    failure_to_roadmap["summary"]["release_blocker_count"] = 1
    report = build_phase170_report(
        tmp_path,
        source_overrides={"failure_to_roadmap_phase169": failure_to_roadmap},
    )

    assert report["status"] == "failed"
    assert any("phase169_failure_to_roadmap.proposals" in error["id"] for error in report["validation_errors"])
