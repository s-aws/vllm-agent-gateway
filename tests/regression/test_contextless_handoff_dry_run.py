from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.contextless_handoff_dry_run import (
    DEFAULT_POLICY_PATH,
    build_contextless_handoff_dry_run_report,
    read_json_object,
    validate_contextless_handoff_dry_run_report,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def source(kind: str, report: dict[str, Any]) -> tuple[Path | None, dict[str, Any]]:
    return None, {"kind": kind, **report}


def small_repo_report() -> dict[str, Any]:
    cases = []
    for case_id in (
        "python-service-code-explanation",
        "python-service-endpoint-route-lookup",
        "python-service-schema-lookup",
    ):
        for client in ("gateway", "anythingllm"):
            cases.append({"case_id": case_id, "client": client, "status": "passed", "source_unchanged": True})
    return {"kind": "multi_repo_fixture_live_report", "status": "passed", "cases": cases}


def large_context_report() -> dict[str, Any]:
    return {
        "kind": "large_context_usability_live_closeout_report",
        "status": "passed",
        "live": True,
        "responses": [
            {"surface": "gateway", "case_id": "P221-LC-001", "status": "passed"},
            {"surface": "anythingllm", "case_id": "P221-LC-001", "status": "passed"},
        ],
    }


def sources() -> dict[str, tuple[Path | None, dict[str, Any]]]:
    return {
        "phase232_handoff": source(
            "onboarding_release_handoff_refresh_report",
            {"status": "passed", "decision": "handoff_ready", "summary": {"validation_error_count": 0}},
        ),
        "runtime_recovery": source(
            "runtime_recovery_reliability_rebaseline_report",
            {"status": "passed", "decision": "ready_after_recovery", "summary": {"missing_required_surface_count": 0}},
        ),
        "release_channels": source(
            "release_channel_validation_report",
            {"status": "passed", "summary": {"failed_check_ids": []}},
        ),
        "security_policy": source(
            "security_policy_validation_report",
            {"status": "passed", "summary": {"failed_check_ids": []}},
        ),
        "first_time_user_doctor": source(
            "first_time_user_doctor_report",
            {"status": "passed", "summary": {"failed_check_ids": []}},
        ),
        "external_tester_dry_run": source(
            "external_tester_dry_run_report",
            {
                "status": "passed",
                "environment": {
                    "workflow_router_gateway_base_url": "http://127.0.0.1:8500/v1",
                    "anythingllm_api_base_url": "http://127.0.0.1:3001",
                    "workspace": "my-workspace",
                },
                "summary": {
                    "live_runtime": True,
                    "onboarding_live_status": "passed",
                    "onboarding_live_case_count": 1,
                    "feedback_count": 1,
                },
                "manual_prompt": {"case_id": "ONB-001"},
                "feedback_capture": {"feedback_run_id": "workflow-feedback-20260614T000000000000Z"},
            },
        ),
        "external_onboarding_static": source(
            "external_tester_onboarding_validation_report",
            {"status": "passed", "summary": {"case_count": 5}},
        ),
        "external_onboarding_live": source(
            "external_tester_onboarding_validation_report",
            {"status": "passed", "summary": {"live_status": "passed", "live_case_count": 1, "feedback_count": 1}},
        ),
        "small_repo_live": (None, small_repo_report()),
        "small_skill_admission_gate": source(
            "small_skill_admission_pilot_report",
            {"status": "passed", "summary": {"phase231_ready": True}},
        ),
        "large_context_live": (None, large_context_report()),
        "blind_audit": source(
            "contextless_handoff_dry_run_blind_audit",
            {"phase": 233, "status": "passed", "summary": {"contextless": True}},
        ),
    }


def build_report(current_sources: dict[str, tuple[Path | None, dict[str, Any]]] | None = None) -> dict[str, Any]:
    return build_contextless_handoff_dry_run_report(
        config_root=REPO_ROOT,
        policy=policy(),
        policy_path=POLICY_PATH,
        sources=current_sources or sources(),
        source_errors=[],
    )


def error_ids(report: dict[str, Any]) -> set[str]:
    return {str(item.get("id")) for item in report["validation_errors"]}


def test_phase233_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase233_report_passes_clean_sources() -> None:
    report = build_report()

    assert report["status"] == "passed"
    assert report["decision"] == "handoff_dry_run_passed"
    assert report["summary"]["missing_required_surface_count"] == 0
    assert report["summary"]["handoff_ready"] is True


def test_phase233_rejects_wrong_anythingllm_target() -> None:
    current_sources = copy.deepcopy(sources())
    current_sources["external_tester_dry_run"][1]["environment"]["workflow_router_gateway_base_url"] = "http://127.0.0.1:8300/v1"

    report = build_report(current_sources)

    assert report["status"] == "failed"
    assert "external_tester.workflow_router_gateway_base_url" in error_ids(report)


def test_phase233_rejects_missing_anythingllm_small_repo_surface() -> None:
    current_sources = copy.deepcopy(sources())
    current_sources["small_repo_live"][1]["cases"] = [
        item for item in current_sources["small_repo_live"][1]["cases"] if item["client"] == "gateway"
    ]

    report = build_report(current_sources)

    assert report["status"] == "failed"
    assert "small_repo.anythingllm" in report["missing_required_surfaces"]


def test_phase233_rejects_missing_feedback_link() -> None:
    current_sources = copy.deepcopy(sources())
    current_sources["external_onboarding_live"][1]["summary"]["feedback_count"] = 0
    current_sources["external_tester_dry_run"][1]["summary"]["feedback_count"] = 0
    current_sources["external_tester_dry_run"][1]["feedback_capture"]["feedback_run_id"] = ""

    report = build_report(current_sources)

    assert report["status"] == "failed"
    assert "feedback.workflow_feedback" in report["missing_required_surfaces"]


def test_phase233_rejects_hidden_summary_edit() -> None:
    current_policy = policy()
    current_sources = sources()
    report = build_contextless_handoff_dry_run_report(
        config_root=REPO_ROOT,
        policy=current_policy,
        policy_path=POLICY_PATH,
        sources=current_sources,
        source_errors=[],
    )
    edited = copy.deepcopy(report)
    edited["summary"]["source_report_count"] = 999

    errors = validate_contextless_handoff_dry_run_report(
        edited,
        config_root=REPO_ROOT,
        policy=current_policy,
        policy_path=POLICY_PATH,
        sources=current_sources,
        source_errors=[],
    )

    assert errors == ["report must match rebuilt contextless handoff dry-run report"]
