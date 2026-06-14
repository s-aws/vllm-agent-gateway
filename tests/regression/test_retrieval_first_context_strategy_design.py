from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.retrieval_first_context_strategy_design import (
    DEFAULT_POLICY_PATH,
    RetrievalFirstContextStrategyDesignConfig,
    read_json_object,
    run_retrieval_first_context_strategy_design,
    validate_policy,
    write_json,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def phase214_report() -> dict:
    return {
        "schema_version": 1,
        "kind": "large_corpus_context_budget_inventory_report",
        "phase": 214,
        "status": "passed",
        "summary": {
            "estimated_token_count": 1_250_000,
            "model_limit": 65_536,
            "target_input_limit": 24_000,
            "raw_1m_prompt_support_proven": False,
            "phase215_ready": True,
        },
    }


def policy_with_temp_phase214(tmp_path: Path) -> dict:
    mutated = copy.deepcopy(policy())
    report_path = tmp_path / "phase214-report.json"
    write_json(report_path, phase214_report())
    mutated["phase214_precondition"]["report_path"] = str(report_path)
    return mutated


def run_with_policy(tmp_path: Path, value: dict) -> dict:
    policy_path = tmp_path / "policy.json"
    write_json(policy_path, value)
    return run_retrieval_first_context_strategy_design(
        RetrievalFirstContextStrategyDesignConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
        )
    )


def test_phase215_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase215_report_passes_with_temp_phase214_report(tmp_path: Path) -> None:
    report = run_with_policy(tmp_path, policy_with_temp_phase214(tmp_path))

    assert report["status"] == "passed"
    assert report["summary"]["strategy_count"] == 6
    assert report["summary"]["phase216_ready"] is True
    assert report["summary"]["raw_1m_prompt_support_proven"] is False
    assert report["summary"]["retrieval_index_implementation_in_scope"] is False
    assert (tmp_path / "report.md").read_text(encoding="utf-8").startswith(
        "# Retrieval-First Context Strategy Design"
    )


def test_phase215_policy_rejects_missing_strategy() -> None:
    mutated = copy.deepcopy(policy())
    mutated["required_strategy_ids"] = [
        item for item in mutated["required_strategy_ids"] if item != "artifact_paging"
    ]
    mutated["strategy_definitions"] = [
        item for item in mutated["strategy_definitions"] if item.get("strategy_id") != "artifact_paging"
    ]

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.required_strategy_ids" for item in errors)
    assert any(item["id"] == "policy.strategy_definitions" for item in errors)


def test_phase215_policy_rejects_retrieval_without_safety_governance() -> None:
    mutated = copy.deepcopy(policy())
    for item in mutated["strategy_definitions"]:
        if item.get("strategy_id") == "retrieval":
            item["forbidden_when"] = ["retrieved chunks lack source references"]

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.strategy_definitions.retrieval.forbidden_when" for item in errors)


def test_phase215_report_rejects_raw_1m_phase214_claim(tmp_path: Path) -> None:
    mutated = policy_with_temp_phase214(tmp_path)
    report_path = Path(mutated["phase214_precondition"]["report_path"])
    raw_claim = phase214_report()
    raw_claim["summary"]["raw_1m_prompt_support_proven"] = True
    write_json(report_path, raw_claim)

    report = run_with_policy(tmp_path, mutated)

    assert report["status"] == "failed"
    assert any(item["id"] == "phase214_report.raw_1m_prompt_support_proven" for item in report["validation_errors"])


def test_phase215_report_rejects_missing_phase214_artifact(tmp_path: Path) -> None:
    mutated = copy.deepcopy(policy())
    mutated["phase214_precondition"]["report_path"] = str(tmp_path / "missing-phase214.json")

    report = run_with_policy(tmp_path, mutated)

    assert report["status"] == "failed"
    assert any(item["id"] == "phase214_report.missing" for item in report["validation_errors"])
