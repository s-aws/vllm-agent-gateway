from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.context_index_prototype import read_json_object, write_json
from vllm_agent_gateway.acceptance.context_strategy_fixture_bootstrap import make_context_strategy_fixture_policy
from vllm_agent_gateway.acceptance.context_strategy_router_clone_replay import (
    DEFAULT_POLICY_PATH,
    ContextStrategyRouterCloneReplayConfig,
    run_context_strategy_router_clone_replay,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def test_phase320_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase320_policy_rejects_disabled_bootstrap() -> None:
    mutated = copy.deepcopy(policy())
    mutated["bootstrap_fixture"]["enabled"] = False

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.bootstrap_fixture.enabled" for item in errors)


def test_context_strategy_fixture_bootstrap_does_not_store_source_text(tmp_path: Path) -> None:
    fixture = make_context_strategy_fixture_policy(REPO_ROOT, tmp_path / "fixture")
    index = read_json_object(fixture["index_path"])

    assert index["source_text_retention"] == "metadata_only"
    assert index["store_source_text"] is False
    assert index["store_rejected_content"] is False
    assert "PHASE216_DUMMY_SECRET_DO_NOT_EXPOSE" not in str(index)


def test_phase320_clone_replay_passes_with_bootstrapped_fixture(tmp_path: Path) -> None:
    report = run_context_strategy_router_clone_replay(
        ContextStrategyRouterCloneReplayConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["phase319_status"] == "passed"
    assert report["summary"]["phase319_case_count"] == 11
    assert report["summary"]["phase319_passed_case_count"] == 11
    assert report["summary"]["persistent_runtime_state_required"] is False
    assert report["summary"]["phase321_ready"] is True
    assert "phase220-clone-replay-policy.json" in report["phase220_policy_path"]
    assert read_json_object(Path(report["phase220_policy_path"]))["target_root"] == report["bootstrap_fixture"]["target_root"]


def test_phase320_clone_replay_rejects_wrong_expected_summary(tmp_path: Path) -> None:
    mutated = copy.deepcopy(policy())
    mutated["required_phase319_summary"]["case_count"] = 999
    policy_path = tmp_path / "policy.json"
    write_json(policy_path, mutated)

    report = run_context_strategy_router_clone_replay(
        ContextStrategyRouterCloneReplayConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
        )
    )

    assert report["status"] == "failed"
    assert any(item["id"] == "phase319.summary.case_count" for item in report["validation_errors"])
