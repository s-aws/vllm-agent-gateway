from __future__ import annotations

from pathlib import Path

from vllm_agent_gateway.acceptance.generic_chat_vague_prompt_contract import (
    DEFAULT_POLICY_PATH,
    GenericChatVaguePromptContractConfig,
    build_report,
    classify_case_response,
    load_policy,
    run_generic_chat_vague_prompt_contract,
    validate_generic_chat_vague_prompt_contract_report,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def make_target_roots(tmp_path: Path) -> tuple[str, str]:
    first = tmp_path / "coinbase_testing_repo_frozen_tmp"
    second = tmp_path / "coinbase_testing_repo_frozen_tmp.github"
    first.mkdir()
    second.mkdir()
    return (str(first), str(second))


def test_phase166_policy_is_governed() -> None:
    policy = load_policy(REPO_ROOT, DEFAULT_POLICY_PATH)

    assert validate_policy(policy) == []
    assert policy["phase"] == 166
    assert len(policy["required_cases"]) >= 6
    assert policy["blind_baseline"]["source"] == "contextless_blind_agent"


def test_phase166_direct_contract_passes_without_live_services(tmp_path: Path) -> None:
    report = run_generic_chat_vague_prompt_contract(
        GenericChatVaguePromptContractConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase166.json",
            target_roots=make_target_roots(tmp_path),
            run_live=False,
            include_anythingllm=False,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["failed_case_count"] == 0
    assert report["summary"]["surfaces"] == ["direct_controller"]
    by_class = {case["prompt_class"]: case for case in report["cases"] if case["surface"] == "direct_controller"}
    assert by_class["greeting_hi"]["artifact_count"] == 0
    assert by_class["vague_coding_no_path"]["selected_workflow"] == "none"
    assert by_class["unsupported_mutation_bypass"]["selected_workflow"] == "none"
    assert "blocked_approval_bypass" in by_class["unsupported_mutation_bypass"]["text_sample"]


def test_phase166_classifier_rejects_repository_workflow_marker() -> None:
    policy = load_policy(REPO_ROOT, DEFAULT_POLICY_PATH)
    case = policy["required_cases"][0]
    body = {
        "choices": [
            {
                "message": {
                    "content": (
                        "general_chat_no_target\n"
                        "Selected workflow: none\n"
                        "include an allowed target_root path\n"
                        "Selected workflow: code_investigation.plan\n"
                    )
                }
            }
        ],
        "agentic_controller_response": {
            "summary": {"route_status": "general_chat_no_target", "selected_workflow": "none"},
            "artifacts": {},
        },
    }

    result = classify_case_response(
        policy=policy,
        case=case,
        surface="direct_controller",
        prompt="hi",
        target_root=None,
        http_status=200,
        body=body,
    )

    assert result["status"] == "failed"
    assert any(finding["code"] == "repository_workflow_started" for finding in result["findings"])


def test_phase166_report_rejects_hidden_summary_edit(tmp_path: Path) -> None:
    policy = load_policy(REPO_ROOT, DEFAULT_POLICY_PATH)
    report = run_generic_chat_vague_prompt_contract(
        GenericChatVaguePromptContractConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase166.json",
            target_roots=make_target_roots(tmp_path),
            run_live=False,
            include_anythingllm=False,
        )
    )
    report["summary"]["case_count"] = 999

    errors = validate_generic_chat_vague_prompt_contract_report(report, policy)

    assert any("report.summary must match rebuilt" in error for error in errors)


def test_phase166_report_rebuild_fails_on_fixture_change() -> None:
    policy = load_policy(REPO_ROOT, DEFAULT_POLICY_PATH)
    report = build_report(
        policy=policy,
        cases=[],
        fixture_before={"repo": {"watched_files": {"a": "1"}}},
        fixture_after={"repo": {"watched_files": {"a": "2"}}},
        anythingllm_preflight_result={},
    )

    assert report["status"] == "failed"
    assert report["summary"]["fixture_state_changed"] is True
    assert "protected fixture state changed" in report["errors"]
