from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.context_index_prototype import read_json_object, write_json
from vllm_agent_gateway.acceptance.context_strategy_router_rebaseline import (
    DEFAULT_POLICY_PATH,
    ContextStrategyRouterRebaselineConfig,
    run_context_strategy_router_rebaseline,
    validate_policy,
)
from tests.regression.test_retrieval_backed_chat_answer_gate import make_context_index_policy


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def phase318_report(path: Path) -> Path:
    report = {
        "status": "passed",
        "summary": {
            "result_count": 4,
            "phase319_ready": True,
            "raw_500k_prompt_support_proven": False,
            "stable_corpus_mutated": False,
            "max_prompt_tokens": 249354,
        },
    }
    write_json(path, report)
    return path


def custom_policy(tmp_path: Path) -> Path:
    target_root, context_policy_path = make_context_index_policy(tmp_path)
    mutated = copy.deepcopy(policy())
    mutated["target_root"] = str(target_root)
    mutated["context_index_policy_path"] = str(context_policy_path)
    mutated["phase318_report_path"] = str(phase318_report(tmp_path / "phase318.json"))
    path = tmp_path / "phase319-policy.json"
    write_json(path, mutated)
    return path


def test_phase319_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase319_policy_rejects_missing_case_kind() -> None:
    mutated = copy.deepcopy(policy())
    mutated["required_case_kinds"] = [item for item in mutated["required_case_kinds"] if item != "missing_index"]

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.required_case_kinds" for item in errors)


def test_phase319_rebaseline_passes_with_fixture_policy(tmp_path: Path) -> None:
    report = run_context_strategy_router_rebaseline(
        ContextStrategyRouterRebaselineConfig(
            config_root=REPO_ROOT,
            policy_path=custom_policy(tmp_path),
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
            require_artifacts=True,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["all_strategies_covered"] is True
    assert report["summary"]["deterministic_replay_passed"] is True
    assert report["summary"]["sensitive_or_secret_request_refused"] is True
    assert report["summary"]["raw_500k_prompt_support_proven"] is False
    assert report["summary"]["phase320_ready"] is True


def test_phase319_requires_phase318_report_when_artifacts_required(tmp_path: Path) -> None:
    policy_path = custom_policy(tmp_path)
    mutated = read_json_object(policy_path)
    mutated["phase318_report_path"] = str(tmp_path / "missing-phase318.json")
    write_json(policy_path, mutated)

    report = run_context_strategy_router_rebaseline(
        ContextStrategyRouterRebaselineConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
            require_artifacts=True,
        )
    )

    assert report["status"] == "failed"
    assert any(item["id"] == "phase318.missing" for item in report["validation_errors"])


def test_phase319_case_results_include_blind_audit_evidence_fields(tmp_path: Path) -> None:
    report = run_context_strategy_router_rebaseline(
        ContextStrategyRouterRebaselineConfig(
            config_root=REPO_ROOT,
            policy_path=custom_policy(tmp_path),
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
            require_artifacts=True,
        )
    )

    required = set(policy()["required_evidence_fields"])
    for case in report["case_results"]:
        assert required.issubset(case)
    serialized = json.dumps(report, sort_keys=True)
    assert "PHASE216_DUMMY_SECRET_DO_NOT_EXPOSE" not in serialized
