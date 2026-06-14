from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.corpus_index_safety_governance import (
    CorpusIndexSafetyGovernanceConfig,
    DEFAULT_POLICY_PATH,
    read_json_object,
    run_corpus_index_safety_governance,
    validate_policy,
    write_json,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def phase215_report() -> dict:
    return {
        "schema_version": 1,
        "kind": "retrieval_first_context_strategy_design_report",
        "phase": 215,
        "status": "passed",
        "summary": {
            "phase216_ready": True,
            "retrieval_index_implementation_in_scope": False,
            "retrieval_backed_chat_integration_in_scope": False,
        },
    }


def policy_with_temp_phase215(tmp_path: Path) -> dict:
    mutated = copy.deepcopy(policy())
    report_path = tmp_path / "phase215-report.json"
    write_json(report_path, phase215_report())
    mutated["phase215_precondition"]["report_path"] = str(report_path)
    mutated["negative_control_fixture"]["root"] = str(tmp_path / "negative-controls")
    mutated["root_policy"]["allowed_roots"] = [str(tmp_path / "negative-controls")]
    return mutated


def run_with_policy(tmp_path: Path, value: dict) -> dict:
    policy_path = tmp_path / "policy.json"
    write_json(policy_path, value)
    return run_corpus_index_safety_governance(
        CorpusIndexSafetyGovernanceConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
        )
    )


def test_phase216_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase216_report_passes_with_temp_phase215_report(tmp_path: Path) -> None:
    report = run_with_policy(tmp_path, policy_with_temp_phase215(tmp_path))

    assert report["status"] == "passed"
    assert report["summary"]["negative_control_count"] == 13
    assert report["summary"]["negative_control_passed_count"] == 13
    assert report["summary"]["admitted_count"] == 1
    assert report["summary"]["rejected_count"] == 12
    assert report["summary"]["phase217_ready"] is True
    assert report["summary"]["durable_index_implementation_in_scope"] is False
    assert report["summary"]["retrieval_backed_chat_integration_in_scope"] is False
    serialized = (tmp_path / "report.json").read_text(encoding="utf-8")
    assert "PHASE216_DUMMY_SECRET_DO_NOT_EXPOSE" not in serialized
    assert "ignored content" not in serialized
    assert (tmp_path / "report.md").read_text(encoding="utf-8").startswith("# Corpus Index Safety Governance")


def test_phase216_policy_rejects_missing_safety_rule() -> None:
    mutated = copy.deepcopy(policy())
    mutated["safety_rules"] = [item for item in mutated["safety_rules"] if item != "reject_symlink_escape"]

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.safety_rules" for item in errors)


def test_phase216_policy_rejects_source_text_retention() -> None:
    mutated = copy.deepcopy(policy())
    mutated["retention_policy"]["source_text_copy_allowed"] = True

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.retention_policy.source_text_copy_allowed" for item in errors)


def test_phase216_report_rejects_phase215_index_scope(tmp_path: Path) -> None:
    mutated = policy_with_temp_phase215(tmp_path)
    report_path = Path(mutated["phase215_precondition"]["report_path"])
    scoped = phase215_report()
    scoped["summary"]["retrieval_index_implementation_in_scope"] = True
    write_json(report_path, scoped)

    report = run_with_policy(tmp_path, mutated)

    assert report["status"] == "failed"
    assert any(
        item["id"] == "phase215_report.retrieval_index_implementation_in_scope"
        for item in report["validation_errors"]
    )


def test_phase216_policy_rejects_missing_negative_control() -> None:
    mutated = copy.deepcopy(policy())
    mutated["negative_controls"] = [
        item for item in mutated["negative_controls"] if item.get("case_id") != "P216-SAFE-010"
    ]

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.negative_controls" for item in errors)
