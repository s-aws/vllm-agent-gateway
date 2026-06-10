from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.chat_transcript_quality import (
    build_chat_transcript_quality_report,
    read_json_object,
    validate_chat_transcript_quality_report,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSCRIPT_REPORT_PATH = REPO_ROOT / "runtime-state" / "founder-field-tests" / "phase134-founder-smoke.json"
POLICY_PATH = REPO_ROOT / "runtime" / "chat_transcript_quality_policy.json"


def transcript_report() -> dict[str, Any]:
    return read_json_object(TRANSCRIPT_REPORT_PATH)


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def project_report(
    transcript_payload: dict[str, Any] | None = None,
    policy_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_chat_transcript_quality_report(
        transcript_report=transcript_payload or transcript_report(),
        policy=policy_payload or policy(),
        transcript_report_path=TRANSCRIPT_REPORT_PATH,
        policy_path=POLICY_PATH,
    )


def validate_report(
    report: dict[str, Any],
    transcript_payload: dict[str, Any] | None = None,
    policy_payload: dict[str, Any] | None = None,
) -> list[str]:
    return validate_chat_transcript_quality_report(
        report,
        transcript_report=transcript_payload or transcript_report(),
        policy=policy_payload or policy(),
        transcript_report_path=TRANSCRIPT_REPORT_PATH,
        policy_path=POLICY_PATH,
    )


def first_case_text() -> str:
    return str(transcript_report()["cases"][0]["text_sample"])


def test_project_chat_transcript_quality_passes_current_founder_smoke() -> None:
    report = project_report()
    assert validate_policy(policy()) == []
    assert validate_report(report) == []
    assert report["status"] == "passed"
    assert report["quality_status"] == "pass"
    assert report["summary"]["case_count"] == 4
    assert report["summary"]["blocker_case_count"] == 0


def test_chat_transcript_quality_rejects_artifact_only_answer() -> None:
    payload = copy.deepcopy(transcript_report())
    case = payload["cases"][0]
    run_id = case["run_id"]
    case["text_sample"] = (
        f"I completed workflow_router.plan.\nrun_id: {run_id}\n\n"
        "Artifacts:\n- route_decision: /tmp/route-decision.json\n"
    )
    report = project_report(payload)
    assert report["status"] == "failed"
    findings = report["cases"][0]["findings"]
    assert any(item["code"] == "artifact_only_or_artifact_first" for item in findings)


def test_chat_transcript_quality_rejects_missing_run_id() -> None:
    payload = copy.deepcopy(transcript_report())
    payload["cases"][0]["run_id"] = "unknown"
    report = project_report(payload)
    assert any(item["code"] == "missing_run_id" for item in report["cases"][0]["findings"])


def test_chat_transcript_quality_rejects_missing_evidence_section() -> None:
    payload = copy.deepcopy(transcript_report())
    payload["cases"][0]["text_sample"] = first_case_text().replace("- Grounded in:", "- Based on:")
    report = project_report(payload)
    assert any(item["code"] == "missing_evidence_section" for item in report["cases"][0]["findings"])


def test_chat_transcript_quality_rejects_route_workflow_mismatch() -> None:
    payload = copy.deepcopy(transcript_report())
    payload["cases"][0]["expected_workflow"] = "code_context.lookup"
    report = project_report(payload)
    assert any(item["code"] == "route_workflow_mismatch" for item in report["cases"][0]["findings"])


def test_chat_transcript_quality_rejects_unsafe_mutation_claim() -> None:
    payload = copy.deepcopy(transcript_report())
    payload["cases"][0]["text_sample"] = first_case_text() + "\nsource_changed: True\n"
    report = project_report(payload)
    assert any(item["code"] == "unsafe_mutation_claim" for item in report["cases"][0]["findings"])


def test_chat_transcript_quality_rejects_hidden_summary_change() -> None:
    report = project_report()
    report["summary"]["case_count"] = 99
    errors = validate_report(report)
    assert any("report.summary must match rebuilt chat transcript quality report" in error for error in errors)


def test_chat_transcript_quality_rejects_bad_policy_shape() -> None:
    broken_policy = copy.deepcopy(policy())
    broken_policy["required_markers"] = []
    report = project_report(policy_payload=broken_policy)
    assert report["status"] == "failed"
    assert any("policy.required_markers is required" in error for error in report["errors"])
