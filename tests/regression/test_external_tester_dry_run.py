from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import vllm_agent_gateway.acceptance.external_tester_dry_run as dry_run
from vllm_agent_gateway.acceptance.external_tester_dry_run import (
    ExternalTesterDryRunConfig,
    build_external_tester_dry_run_report,
    docs_audit,
    read_json_object,
    run_external_tester_dry_run,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "external_tester_dry_run_policy.json"


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def passed_release_channels() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "release_channel_validation_report",
        "status": "passed",
        "checks": [{"id": "stable.readiness", "status": "passed"}],
        "summary": {"failed_check_ids": []},
    }


def passed_doctor() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "first_time_user_doctor_report",
        "status": "passed",
        "summary": {"failed_check_ids": []},
    }


def passed_release_notes() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "release_notes_validation_report",
        "status": "passed",
        "summary": {"error_count": 0},
    }


def passed_onboarding_static() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "external_tester_onboarding_validation_report",
        "status": "passed",
        "pack_path": str(REPO_ROOT / "runtime" / "external_tester_onboarding.json"),
        "summary": {"case_count": 5},
    }


def passed_onboarding_live() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "external_tester_onboarding_validation_report",
        "status": "passed",
        "summary": {"live_status": "passed", "live_case_count": 1, "feedback_count": 1},
        "live": {
            "cases": [
                {
                    "case_id": "ONB-001",
                    "status": "passed",
                    "run_id": "workflow-router-20260609T000000000000Z",
                    "feedback_run_id": "workflow-feedback-20260609T000000000000Z",
                    "visible_response": {"marker_status": "passed", "missing_markers": []},
                    "feedback_response": {"marker_status": "passed", "missing_markers": []},
                }
            ]
        },
    }


def passed_docs() -> dict[str, Any]:
    return {
        "status": "passed",
        "docs_followed": policy()["required_docs_followed"],
        "docs": {},
        "blockers": [],
        "ambiguities": [],
        "resolved_findings": ["minimum dry-run command is explicit"],
    }


def environment(*, api_key_present: bool = True) -> dict[str, Any]:
    expected = policy()["expected_environment"]
    return {
        **expected,
        "anythingllm_api_key_present": api_key_present,
    }


def synthetic_report(
    *,
    docs: dict[str, Any] | None = None,
    release_channels: dict[str, Any] | None = None,
    doctor: dict[str, Any] | None = None,
    release_notes: dict[str, Any] | None = None,
    onboarding_static: dict[str, Any] | None = None,
    onboarding_live: dict[str, Any] | None = None,
    live_runtime: bool = True,
    api_key_present: bool = True,
) -> dict[str, Any]:
    return build_external_tester_dry_run_report(
        policy=policy(),
        docs=docs or passed_docs(),
        release_channels=release_channels or passed_release_channels(),
        doctor=doctor or passed_doctor(),
        release_notes=release_notes or passed_release_notes(),
        onboarding_static=onboarding_static or passed_onboarding_static(),
        onboarding_live=onboarding_live or passed_onboarding_live(),
        environment=environment(api_key_present=api_key_present),
        live_runtime=live_runtime,
    )


def test_external_tester_dry_run_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_external_tester_dry_run_docs_audit_passes_current_docs() -> None:
    audit = docs_audit(policy(), config_root=REPO_ROOT)

    assert audit["status"] == "passed"
    assert audit["blockers"] == []
    assert audit["ambiguities"] == []
    assert "minimum dry-run command is explicit" in audit["resolved_findings"]


def test_external_tester_dry_run_static_mode_passes_current_docs(tmp_path: Path) -> None:
    report = run_external_tester_dry_run(
        ExternalTesterDryRunConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase147-static.json",
            live_runtime=False,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["doc_blocker_count"] == 0
    assert report["summary"]["doc_ambiguity_count"] == 0
    assert report["child_reports"]["release_channels"]["status"] == "passed"
    assert report["child_reports"]["release_notes"]["status"] == "passed"
    assert report["child_reports"]["external_onboarding_static"]["status"] == "passed"


def test_external_tester_dry_run_synthetic_live_report_passes() -> None:
    report = synthetic_report()

    assert report["status"] == "passed"
    assert report["summary"]["feedback_count"] == 1
    assert report["manual_prompt"]["run_id"].startswith("workflow-router-")
    assert report["feedback_capture"]["feedback_run_id"].startswith("workflow-feedback-")


def test_external_tester_dry_run_rejects_doc_ambiguity() -> None:
    docs = passed_docs()
    docs["ambiguities"] = ["minimum external tester dry-run path is not explicit"]

    report = synthetic_report(docs=docs)

    assert report["status"] == "failed"
    assert "minimum external tester dry-run path is not explicit" in report["errors"]


def test_external_tester_dry_run_rejects_failed_stable_channel() -> None:
    release_channels = passed_release_channels()
    release_channels["checks"][0]["status"] = "failed"

    report = synthetic_report(release_channels=release_channels)

    assert report["status"] == "failed"
    assert "release_channels stable.readiness must be passed" in report["errors"]


def test_external_tester_dry_run_rejects_failed_doctor_in_live_mode() -> None:
    doctor = passed_doctor()
    doctor["status"] = "failed"
    doctor["summary"]["failed_check_ids"] = ["port.workflow_router_gateway"]

    report = synthetic_report(doctor=doctor)

    assert report["status"] == "failed"
    assert "first_time_user_doctor.status must be passed" in report["errors"]
    assert "first_time_user_doctor.summary.failed_check_ids must be empty" in report["errors"]


def test_external_tester_dry_run_rejects_missing_feedback_run() -> None:
    onboarding_live = copy.deepcopy(passed_onboarding_live())
    onboarding_live["summary"]["feedback_count"] = 0
    onboarding_live["live"]["cases"][0]["feedback_run_id"] = None

    report = synthetic_report(onboarding_live=onboarding_live)

    assert report["status"] == "failed"
    assert "external_onboarding_live.summary.feedback_count must be 1" in report["errors"]
    assert "external_onboarding_live ONB-001 must expose workflow-feedback run_id" in report["errors"]


def test_external_tester_dry_run_rejects_missing_api_key_for_live() -> None:
    report = synthetic_report(api_key_present=False)

    assert report["status"] == "failed"
    assert "environment.anythingllm_api_key_present must be true for live dry run" in report["errors"]


def test_external_tester_dry_run_live_mode_uses_existing_validators(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ANYTHINGLLM_API_KEY", "test-key")

    monkeypatch.setattr(dry_run, "validate_release_channels", lambda config: passed_release_channels())
    monkeypatch.setattr(dry_run, "run_release_notes_validation", lambda config: passed_release_notes())
    monkeypatch.setattr(dry_run, "validate_external_tester_onboarding", lambda config, api_key=None: passed_onboarding_live() if config.live_anythingllm else passed_onboarding_static())
    monkeypatch.setattr(dry_run, "run_first_time_user_doctor", lambda config: passed_doctor())

    report = run_external_tester_dry_run(
        ExternalTesterDryRunConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase147-live.json",
            live_runtime=True,
            include_feedback=True,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["live_runtime"] is True
    assert report["summary"]["feedback_count"] == 1
