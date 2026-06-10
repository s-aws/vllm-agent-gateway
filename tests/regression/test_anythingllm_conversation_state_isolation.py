from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.anythingllm_conversation_state_isolation import (
    DEFAULT_POLICY_PATH,
    AnythingLLMConversationStateIsolationConfig,
    direct_controller_case,
    route_signature_from_current_response,
    run_anythingllm_conversation_state_isolation,
    validate_current_response,
    validate_policy,
)
from vllm_agent_gateway.acceptance.current_model_compatibility_matrix import read_json_object


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH
TARGET_ROOT = "/mnt/c/coinbase_testing_repo_frozen_tmp.github"


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def ready_case(output_format: str = "format_a") -> dict[str, Any]:
    forbidden = ["Selected workflow: code_investigation.plan"]
    if output_format == "format_a":
        forbidden.append('"output_format": "json"')
    return {
        "case_id": "ISO-TEST",
        "expected_route_status": "ready",
        "expected_selected_workflow": "code_context.lookup",
        "expected_route_rules": ["l1_callers_usages_terms"],
        "expected_output_format": output_format,
        "current_prompt_template": (
            "In {target_root}, find callers and usages of find_stealth_order_by_placed_order_id. "
            "Read only. Group by file and explain each usage briefly."
        ),
        "forbidden_current_markers": forbidden,
    }


def route_decision() -> dict[str, Any]:
    return {
        "target_root": TARGET_ROOT,
        "status": "ready",
        "selected_workflow": "code_context.lookup",
        "selected_skills": ["codegraph-context-lookup", "callers-usages-summarizer"],
        "selected_tools": ["structure_index", "git_grep", "read_file", "codegraph_context"],
        "selection_audit": {
            "selected": {"route_rules": ["l1_callers_usages_terms"]},
            "workflow_candidates": {"rejected_count": 1},
            "skill_candidates": {"rejected_count": 1},
            "tool_candidates": {"rejected_count": 1},
        },
    }


def format_a_text() -> str:
    return "\n".join(
        [
            "I completed workflow_router.plan.",
            "workflow_router.plan completed",
            "run_id: workflow-router-test",
            "",
            "Result:",
            "- Selected workflow: code_context.lookup",
            "",
            "Skill Selection:",
            "- Route rules: l1_callers_usages_terms",
        ]
    )


def json_text() -> str:
    return json.dumps(
        {
            "kind": "agentic_controller_chat_response",
            "output_format": "json",
            "run_id": "workflow-router-json-test",
            "workflow": "workflow_router.plan",
            "status": "completed",
            "chat_contract": {
                "selected_workflow": "code_context.lookup",
                "selected_skills": ["codegraph-context-lookup", "callers-usages-summarizer"],
                "selected_tools": ["structure_index", "git_grep", "read_file", "codegraph_context"],
            },
            "selection_explanation": {
                "route_rules": ["l1_callers_usages_terms"],
                "confidence": "medium",
                "coverage_entry_ids": ["L1-007"],
                "confidence_reasons": ["prompt_skill_coverage_match"],
                "rejected_candidates": {
                    "workflow_rejected_count": 1,
                    "skill_rejected_count": 1,
                    "tool_rejected_count": 1,
                },
            },
        },
        ensure_ascii=True,
        sort_keys=True,
    )


def test_conversation_state_isolation_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_conversation_state_isolation_policy_rejects_missing_seed_kind() -> None:
    mutated = copy.deepcopy(policy())
    mutated["cases"] = [case for case in mutated["cases"] if case["seed_kind"] != "stale_controller_envelope"]

    errors = validate_policy(mutated)

    assert any("missing seed kinds" in error for error in errors)


def test_validate_current_response_accepts_format_a_current_prompt() -> None:
    errors = validate_current_response(
        policy=policy(),
        case=ready_case("format_a"),
        target_root=TARGET_ROOT,
        surface="gateway_history_payload",
        text=format_a_text(),
        output_format="format_a",
        route_decision=route_decision(),
        request_artifact={
            "target_root": TARGET_ROOT,
            "user_request": ready_case("format_a")["current_prompt_template"].format(target_root=TARGET_ROOT),
        },
    )

    assert errors == []


def test_validate_current_response_rejects_stale_json_output_for_format_a_current_prompt() -> None:
    errors = validate_current_response(
        policy=policy(),
        case=ready_case("format_a"),
        target_root=TARGET_ROOT,
        surface="anythingllm_same_session",
        text=json_text(),
        output_format="json",
        route_decision=route_decision(),
        request_artifact=None,
    )

    assert any("output_format expected 'format_a' got 'json'" in error for error in errors)
    assert any("text is JSON even though current prompt expects FormatA" in error for error in errors)


def test_validate_current_response_accepts_json_current_prompt() -> None:
    case = ready_case("json")
    errors = validate_current_response(
        policy=policy(),
        case=case,
        target_root=TARGET_ROOT,
        surface="anythingllm_same_session",
        text=json_text(),
        output_format=None,
        route_decision=None,
        request_artifact=None,
    )

    assert errors == []


def test_route_signature_from_json_matches_artifact_signature() -> None:
    assert route_signature_from_current_response(case=ready_case("json"), text=json_text(), route_decision=None) == {
        "selected_workflow": "code_context.lookup",
        "selected_skills": ["codegraph-context-lookup", "callers-usages-summarizer"],
        "selected_tools": ["structure_index", "git_grep", "read_file", "codegraph_context"],
        "route_rules": ["l1_callers_usages_terms"],
    }


def test_conversation_state_isolation_report_fails_when_required_live_surfaces_are_skipped(tmp_path: Path) -> None:
    report = run_anythingllm_conversation_state_isolation(
        AnythingLLMConversationStateIsolationConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase152-report.json",
            markdown_output_path=tmp_path / "phase152-report.md",
            target_roots=(TARGET_ROOT,),
            include_direct=False,
            include_gateway=False,
            include_anythingllm=False,
        )
    )

    assert report["status"] == "failed"
    assert any("validation disabled" in error for error in report["errors"])
    assert (tmp_path / "phase152-report.md").exists()


def test_direct_controller_case_accepts_string_target_roots_for_latest_greeting(tmp_path: Path) -> None:
    phase_policy = policy()
    greeting_case = next(case for case in phase_policy["cases"] if case["case_id"] == "ISO-003")
    result = direct_controller_case(
        AnythingLLMConversationStateIsolationConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase152-report.json",
            target_roots=(TARGET_ROOT, "/mnt/c/coinbase_testing_repo_frozen_tmp"),
            include_gateway=False,
            include_anythingllm=False,
        ),
        policy=phase_policy,
        case=greeting_case,
        target_root=TARGET_ROOT,
    )

    assert result["status"] == "passed"
    assert "general_chat_no_target" in result["assistant_text_excerpt"]
