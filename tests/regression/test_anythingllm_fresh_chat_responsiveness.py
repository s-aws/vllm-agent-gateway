from __future__ import annotations

from pathlib import Path

from vllm_agent_gateway.acceptance.anythingllm_fresh_chat_responsiveness import (
    AnythingLLMFreshChatResponsivenessConfig,
    FreshChatStatus,
    build_report,
    classify_coding_text,
    target_settings_result,
    validate_policy,
    validate_report,
)


def policy() -> dict:
    return {
        "schema_version": 1,
        "kind": "anythingllm_fresh_chat_responsiveness_policy",
        "phase": 237,
        "priority_backlog_id": "P0-M14-237",
        "required_decision": "fresh_chat_responsive",
        "required_anythingllm": {
            "api_base_url": "http://127.0.0.1:3001",
            "workflow_router_base_url": "http://127.0.0.1:8500/v1",
            "workspace": "my-workspace",
            "model": "Qwen3-Coder-30B-A3B-Instruct",
            "provider": "generic-openai",
        },
        "required_cases": [
            "GATEWAY-HI",
            "ANYTHINGLLM-HI",
            "GATEWAY-CODE-EXPLANATION",
            "ANYTHINGLLM-CODE-EXPLANATION",
        ],
        "required_ui_case_ids": ["UI167-GENCHAT-001"],
        "acceptance_marker": "ANYTHINGLLM FRESH CHAT RESPONSIVENESS PASS",
    }


def passed_case(case_id: str, surface: str, kind: str) -> dict:
    return {
        "case_id": case_id,
        "surface": surface,
        "case_kind": kind,
        "status": "passed",
        "http_status": 200,
        "parsed_run_id": f"workflow-router-{case_id.lower()}",
        "text_sample": "ok",
        "text_length": 2,
        "finding_count": 0,
        "findings": [],
    }


def passing_report() -> dict:
    current_policy = policy()
    fixture_state = {"fixture": {"sha256": "same"}}
    return build_report(
        policy=current_policy,
        target_settings={"status": "passed"},
        cases=[
            passed_case("GATEWAY-HI", "workflow_router_gateway", "greeting"),
            passed_case("ANYTHINGLLM-HI", "anythingllm_api", "greeting"),
            passed_case("GATEWAY-CODE-EXPLANATION", "workflow_router_gateway", "coding"),
            passed_case("ANYTHINGLLM-CODE-EXPLANATION", "anythingllm_api", "coding"),
        ],
        ui_report={"status": "passed", "required_case_ids": ["UI167-GENCHAT-001"], "fixture_unchanged": True},
        fixture_before=fixture_state,
        fixture_after=fixture_state,
        errors=[],
    )


def test_phase237_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase237_report_passes() -> None:
    report = passing_report()
    assert report["status"] == "passed"
    assert report["decision"] == "fresh_chat_responsive"
    assert validate_report(report, policy()) == []


def test_phase237_report_rejects_missing_ui_proof() -> None:
    report = passing_report()
    report["ui_report"] = {"status": "failed", "errors": ["missing"]}
    errors = validate_report(report, policy())
    assert any("ui_report" in error for error in errors)


def test_phase237_report_rejects_wrong_target_settings() -> None:
    report = passing_report()
    report["target_settings"] = {"status": "failed"}
    errors = validate_report(report, policy())
    assert any("target_settings" in error for error in errors)


def test_phase237_target_settings_accepts_split_anythingllm_base_url() -> None:
    result = target_settings_result(
        AnythingLLMFreshChatResponsivenessConfig(
            config_root=Path("."),
            workflow_router_gateway_base_url="http://127.0.0.1:8500/v1",
            anythingllm_workflow_router_base_url="http://100.100.12.45:8500/v1",
        ),
        policy=policy(),
        status_code=200,
        settings={
            "LLMProvider": "generic-openai",
            "LLMModel": "Qwen3-Coder-30B-A3B-Instruct",
            "GenericOpenAiBasePath": "http://100.100.12.45:8500/v1",
        },
    )

    assert result["status"] == FreshChatStatus.PASSED.value
    assert result["required"]["workflow_router_base_url"] == "http://100.100.12.45:8500/v1"
    assert result["policy_required"]["workflow_router_base_url"] == "http://127.0.0.1:8500/v1"


def test_phase237_report_rejects_missing_run_id() -> None:
    report = passing_report()
    report["cases"][0]["parsed_run_id"] = None
    errors = validate_report(report, policy())
    assert any("missing parsed_run_id" in error for error in errors)


def test_coding_classifier_accepts_required_markers() -> None:
    text = (
        "workflow_router.plan completed\n"
        "selected_workflow: code_investigation.plan\n"
        "StealthOrderManager.find_stealth_order_by_placed_order_id\n"
        "Inputs:\nOutputs:\nSide effects:\nRelated tests:\nSource mutation: false\n"
    )
    status, findings = classify_coding_text(text)
    assert status == FreshChatStatus.PASSED.value
    assert findings == []


def test_coding_classifier_rejects_repository_mutation() -> None:
    text = (
        "workflow_router.plan completed\n"
        "selected_workflow: code_investigation.plan\n"
        "find_stealth_order_by_placed_order_id\n"
        "Inputs:\nOutputs:\nSide effects:\nRelated tests:\nSource mutation: false\nSource mutation: true\n"
    )
    status, findings = classify_coding_text(text)
    assert status == FreshChatStatus.FAILED.value
    assert any(item["code"] == "forbidden_coding_marker" for item in findings)
