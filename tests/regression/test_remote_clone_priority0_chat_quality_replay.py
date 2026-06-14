from __future__ import annotations

import json
from pathlib import Path

from vllm_agent_gateway.acceptance.remote_clone_priority0_chat_quality_replay import (
    RemoteClonePriority0ReplayStatus,
    build_report,
    classify_text,
    validate_policy,
    validate_report,
)
from vllm_agent_gateway.controller_service.server import (
    InlineArtifactKind,
    inline_artifact_keys_for_response,
)


def policy() -> dict:
    return {
        "schema_version": 1,
        "kind": "remote_clone_priority0_chat_quality_replay_policy",
        "phase": 239,
        "priority_backlog_id": "P0-M14-239",
        "required_decision": "remote_clone_priority0_chat_quality_ready",
        "required_anythingllm": {
            "api_base_url": "http://127.0.0.1:3001",
            "workflow_router_base_url": "http://127.0.0.1:8500/v1",
            "workspace": "my-workspace",
            "model": "Qwen3-Coder-30B-A3B-Instruct",
            "provider": "generic-openai",
        },
        "fixture_ids": ["coinbase-frozen", "coinbase-frozen-git", "python-service-generalization"],
        "required_surfaces": ["workflow_router_gateway", "anythingllm_api"],
        "required_case_ids": [
            "GATEWAY-GREETING",
            "ANYTHINGLLM-GREETING",
            "GATEWAY-COINBASE-CODE-EXPLANATION",
            "ANYTHINGLLM-COINBASE-CODE-EXPLANATION",
        ],
        "blind_baseline_summary": {"global": ["narrowest workflow"]},
        "case_expectations": {
            "greeting": {"required_marker_groups": [["general_chat_no_target"]], "forbidden_markers": ["Source mutation: true"]},
            "code_explanation": {
                "required_marker_groups": [["workflow_router.plan completed"], ["find_stealth_order_by_placed_order_id"]],
                "expected_selected_workflow": "code_investigation.plan",
                "expected_artifact": "downstream_code_explanation",
            },
            "endpoint_route_lookup": {"required_marker_groups": [["endpoint-route-locator"]]},
            "schema_lookup": {"required_marker_groups": [["data-model-schema-locator"]]},
            "related_tests_lookup": {"required_marker_groups": [["Related tests:"]]},
            "feedback_capture": {"required_marker_groups": [["workflow_feedback.record"]]},
            "unsupported_boundary": {"required_marker_groups": [["route_status: blocked"]]},
        },
        "acceptance_marker": "REMOTE CLONE PRIORITY0 CHAT QUALITY REPLAY PASS",
    }


def passed_case(case_id: str) -> dict:
    return {
        "case_id": case_id,
        "surface": "workflow_router_gateway" if case_id.startswith("GATEWAY") else "anythingllm_api",
        "case_kind": "code_explanation",
        "prompt_family": "code_explanation",
        "status": "passed",
        "http_status": 200,
        "parsed_run_id": "workflow-router-test",
        "text_length": 100,
        "text_sample": "workflow_router.plan completed find_stealth_order_by_placed_order_id",
        "finding_count": 0,
        "findings": [],
        "run_record_summary": {"selected_workflow": "code_investigation.plan"},
    }


def passing_report() -> dict:
    current_policy = policy()
    fixture_state = {"fixture": {"watched_hashes": {"file.py": "same"}}}
    cases = [passed_case(case_id) for case_id in current_policy["required_case_ids"]]
    return build_report(
        policy=current_policy,
        target_settings={"status": "passed"},
        cases=cases,
        fixture_before=fixture_state,
        fixture_after=fixture_state,
        errors=[],
    )


def test_phase239_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase239_report_passes() -> None:
    report = passing_report()
    assert report["status"] == "passed"
    assert report["decision"] == "remote_clone_priority0_chat_quality_ready"
    assert validate_report(report, policy()) == []


def test_phase239_report_rejects_fixture_mutation() -> None:
    report = passing_report()
    report["fixture_state_after"] = {"fixture": {"watched_hashes": {"file.py": "changed"}}}
    report["fixture_unchanged"] = False
    errors = validate_report(report, policy())
    assert any("fixture_unchanged" in error for error in errors)


def test_phase239_report_rejects_missing_case() -> None:
    report = passing_report()
    report["cases"] = report["cases"][:-1]
    errors = validate_report(report, policy())
    assert any("missing required case" in error for error in errors)


def test_phase239_classifier_accepts_code_explanation_markers() -> None:
    text = "workflow_router.plan completed\nfind_stealth_order_by_placed_order_id\n"
    run_record = {
        "summary": {"selected_workflow": "code_investigation.plan"},
        "artifacts": {"downstream_code_explanation": "/tmp/code-explanation.json"},
    }
    status, findings = classify_text(
        case_kind="code_explanation",
        text=text,
        http_status=200,
        policy=policy(),
        run_record=run_record,
    )
    assert status == RemoteClonePriority0ReplayStatus.PASSED.value
    assert findings == []


def test_phase239_classifier_rejects_forbidden_marker() -> None:
    status, findings = classify_text(
        case_kind="greeting",
        text="general_chat_no_target\nSource mutation: true\n",
        http_status=200,
        policy=policy(),
    )
    assert status == RemoteClonePriority0ReplayStatus.FAILED.value
    assert any(item["code"] == "forbidden_marker" for item in findings)


def test_endpoint_route_rule_promotes_endpoint_answer_over_generic_behavior(tmp_path: Path) -> None:
    route_decision = tmp_path / "route-decision.json"
    route_decision.write_text(
        json.dumps({"evidence": [{"source": "router_rule", "rule": "l1_endpoint_route_lookup_terms"}]}),
        encoding="utf-8",
    )
    response = {
        "artifacts": {
            "route_decision": str(route_decision),
        }
    }

    ordered = inline_artifact_keys_for_response(response, response["artifacts"])
    assert ordered[0][0] == InlineArtifactKind.ENDPOINT_ROUTE_LOOKUP
    assert any(kind == InlineArtifactKind.BEHAVIOR_EXISTENCE for kind, _ in ordered[1:])


def test_schema_rule_promotes_data_model_answer_over_generic_behavior(tmp_path: Path) -> None:
    route_decision = tmp_path / "route-decision.json"
    route_decision.write_text(
        json.dumps({"evidence": [{"source": "router_rule", "rule": "l1_data_model_lookup_terms"}]}),
        encoding="utf-8",
    )
    response = {
        "artifacts": {
            "route_decision": str(route_decision),
        }
    }

    ordered = inline_artifact_keys_for_response(response, response["artifacts"])
    assert ordered[0][0] == InlineArtifactKind.DATA_MODEL_LOOKUP
    assert any(kind == InlineArtifactKind.BEHAVIOR_EXISTENCE for kind, _ in ordered[1:])
