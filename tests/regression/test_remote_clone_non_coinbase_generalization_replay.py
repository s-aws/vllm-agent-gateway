from __future__ import annotations

from vllm_agent_gateway.acceptance.remote_clone_non_coinbase_generalization_replay import (
    build_report,
    materialize_case,
    validate_policy,
    validate_report,
)


def policy() -> dict:
    return {
        "schema_version": 1,
        "kind": "remote_clone_non_coinbase_generalization_replay_policy",
        "phase": 240,
        "priority_backlog_id": "P0-M14-240",
        "milestone_id": "M5",
        "required_decision": "remote_clone_non_coinbase_generalization_ready",
        "required_anythingllm": {
            "api_base_url": "http://127.0.0.1:3001",
            "workflow_router_base_url": "http://127.0.0.1:8500/v1",
            "workspace": "my-workspace",
            "model": "Qwen3-Coder-30B-A3B-Instruct",
            "provider": "generic-openai",
        },
        "required_surfaces": ["gateway", "anythingllm"],
        "required_chat_markers": ["Answer:", "Source mutation: false"],
        "minimum_case_count": 2,
        "minimum_response_count": 4,
        "minimum_non_coinbase_root_count": 2,
        "minimum_score_for_pass": 80,
        "cases": [
            {
                "case_id": "PY",
                "category": "python",
                "prompt_family": "schema_lookup",
                "target_root": "{config_root}/tests/fixtures/generalization/python_service_fixture",
                "expected_workflow": "code_investigation.plan",
                "prompt": "In {config_root}/tests/fixtures/generalization/python_service_fixture, find schema.",
                "source_hints": ["database/schema.py"],
                "test_hints": ["tests/test_orders.py"],
            },
            {
                "case_id": "SR",
                "category": "staterail",
                "prompt_family": "code_explanation",
                "target_root": "/mnt/c/staterail_testing_repo_frozen_tmp.github",
                "expected_workflow": "code_investigation.plan",
                "prompt": "In /mnt/c/staterail_testing_repo_frozen_tmp.github, explain ActionGateway.",
                "source_hints": ["actions/gateway.py"],
                "test_hints": ["tests/regression/test_action_gateway.py"],
            },
        ],
        "safety_boundaries": ["do not commit or push to s-aws/staterail"],
        "acceptance_marker": "REMOTE CLONE NON-COINBASE GENERALIZATION REPLAY PASS",
    }


def response(surface: str, case_id: str) -> dict:
    return {
        "surface": surface,
        "case_id": case_id,
        "status": "completed",
        "score": 100,
        "gap_classes": ["none"],
        "errors": [],
        "run_id": f"workflow-router-{surface}-{case_id}",
        "selected_workflow": "code_investigation.plan",
        "source_changed": False,
    }


def passing_report() -> dict:
    current_policy = policy()
    before = {"root": {"status_clean": True}}
    return build_report(
        policy=current_policy,
        target_settings={"status": "passed"},
        cases=current_policy["cases"],
        responses=[
            response("gateway", "PY"),
            response("gateway", "SR"),
            response("anythingllm", "PY"),
            response("anythingllm", "SR"),
        ],
        repo_state_before=before,
        repo_state_after=before,
        errors=[],
    )


def test_phase240_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase240_report_passes() -> None:
    report = passing_report()
    assert report["status"] == "passed"
    assert report["decision"] == "remote_clone_non_coinbase_generalization_ready"
    assert validate_report(report, policy()) == []


def test_phase240_report_rejects_gap_response() -> None:
    report = passing_report()
    report["responses"][0]["gap_classes"] = ["evidence_gap"]
    errors = validate_report(report, policy())
    assert any("gap classes" in error for error in errors)


def test_phase240_report_rejects_repo_state_mutation() -> None:
    report = passing_report()
    report["repo_state_after"] = {"root": {"status_clean": False}}
    report["repo_state_unchanged"] = False
    errors = validate_report(report, policy())
    assert any("repo_state_unchanged" in error for error in errors)


def test_phase240_materializes_config_root_tokens() -> None:
    case = policy()["cases"][0]
    materialized = materialize_case(case, __import__("pathlib").Path("/tmp/clone"))
    assert materialized["target_root"] == "/tmp/clone/tests/fixtures/generalization/python_service_fixture"
    assert "/tmp/clone/tests/fixtures/generalization/python_service_fixture" in materialized["prompt"]
