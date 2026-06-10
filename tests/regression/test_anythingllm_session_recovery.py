from __future__ import annotations

from pathlib import Path

from vllm_agent_gateway.acceptance.anythingllm_session_recovery import (
    AnythingLLMSessionRecoveryConfig,
    build_report_from_cases,
    classify_greeting_text,
    direct_greeting_case,
    validate_anythingllm_session_recovery_report,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def passing_text() -> str:
    return (
        "I completed workflow_router.plan.\n"
        "workflow_router.plan completed\n"
        "run_id: workflow-router-general-test\n\n"
        "Result:\n"
        "- Workflow: workflow_router.plan\n"
        "- Status: completed\n"
        "- Selected workflow: none\n\n"
        "Summary:\n"
        "- route_status: general_chat_no_target\n"
        "- selected_workflow: none\n"
        "- answer: Hi. For coding workflow help, include an allowed target_root path and the task.\n"
    )


def test_greeting_text_classifier_accepts_general_chat() -> None:
    status, findings = classify_greeting_text(passing_text())
    assert status == "passed"
    assert findings == []


def test_greeting_text_classifier_rejects_repository_workflow() -> None:
    status, findings = classify_greeting_text(passing_text() + "\nSelected workflow: code_investigation.plan\n")
    assert status == "failed"
    assert any(item["code"] == "repository_workflow_triggered" for item in findings)


def test_greeting_text_classifier_rejects_missing_marker() -> None:
    status, findings = classify_greeting_text(passing_text().replace("general_chat_no_target", "other"))
    assert status == "failed"
    assert any(item["code"] == "missing_greeting_marker" for item in findings)


def test_direct_greeting_uses_latest_message_and_ignores_stale_repo_history(tmp_path: Path) -> None:
    config = AnythingLLMSessionRecoveryConfig(config_root=REPO_ROOT, output_path=tmp_path / "report.json")
    case = direct_greeting_case(
        config,
        case_id="DIRECT-STALE",
        messages=[
            {
                "role": "user",
                "content": (
                    "In /mnt/c/coinbase_testing_repo_frozen_tmp.github, explain what "
                    "find_stealth_order_by_placed_order_id does. Read only."
                ),
            },
            {"role": "assistant", "content": "prior workflow_router run"},
            {"role": "user", "content": "hi"},
        ],
    )
    assert case["status"] == "passed"
    assert "general_chat_no_target" in case["text_sample"]
    assert "Selected workflow: none" in case["text_sample"]


def test_session_recovery_report_rejects_hidden_summary_change() -> None:
    report = build_report_from_cases(
        cases=[
            {
                "case_id": "DIRECT-HI",
                "surface": "direct_controller",
                "status": "passed",
                "http_status": 200,
                "text_sample": passing_text(),
                "finding_count": 0,
                "findings": [],
            }
        ]
    )
    report["summary"]["case_count"] = 99
    errors = validate_anythingllm_session_recovery_report(report)
    assert any("report.summary must match rebuilt" in error for error in errors)


def test_session_recovery_report_rejects_no_direct_case() -> None:
    report = build_report_from_cases(
        cases=[
            {
                "case_id": "ANY-HI",
                "surface": "anythingllm",
                "status": "passed",
                "http_status": 200,
                "text_sample": passing_text(),
                "finding_count": 0,
                "findings": [],
            }
        ],
        anythingllm_preflight_result={"status": "passed"},
    )
    errors = validate_anythingllm_session_recovery_report(report)
    assert any("direct_controller case" in error for error in errors)
