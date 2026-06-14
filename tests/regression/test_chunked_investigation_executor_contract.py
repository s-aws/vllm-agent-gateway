from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.chunked_investigation_executor_contract import (
    DEFAULT_POLICY_PATH,
    ChunkedInvestigationExecutorContractConfig,
    read_json_object,
    run_chunked_investigation_executor_contract,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def phase221_report() -> dict:
    return {
        "schema_version": 1,
        "kind": "large_context_usability_live_closeout_report",
        "phase": 221,
        "status": "passed",
        "summary": {
            "m6_ready": True,
            "m8_ready": True,
            "raw_prompt_stuffing_allowed": False,
            "failed_response_count": 0,
        },
    }


def policy_with_temp_phase221(tmp_path: Path) -> dict:
    mutated = copy.deepcopy(policy())
    report_path = tmp_path / "phase221-report.json"
    write_json(report_path, phase221_report())
    mutated["phase221_precondition"]["report_path"] = str(report_path)
    return mutated


def run_with_policy(tmp_path: Path, value: dict) -> dict:
    policy_path = tmp_path / "policy.json"
    write_json(policy_path, value)
    return run_chunked_investigation_executor_contract(
        ChunkedInvestigationExecutorContractConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
        )
    )


def test_phase222_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase222_report_passes_with_temp_phase221_report(tmp_path: Path) -> None:
    report = run_with_policy(tmp_path, policy_with_temp_phase221(tmp_path))

    assert report["status"] == "passed"
    assert report["summary"]["stage_count"] == 7
    assert report["summary"]["artifact_contract_count"] == 6
    assert report["summary"]["phase223_ready"] is True
    assert (tmp_path / "report.md").read_text(encoding="utf-8").startswith(
        "# Chunked Investigation Executor Contract"
    )


def test_phase222_policy_rejects_missing_stage() -> None:
    mutated = copy.deepcopy(policy())
    mutated["stage_contracts"] = [
        item for item in mutated["stage_contracts"] if item.get("stage_id") != "source_verification"
    ]

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.stage_contracts" for item in errors)


def test_phase222_policy_rejects_missing_canonical_claim_map_artifact() -> None:
    mutated = copy.deepcopy(policy())
    mutated["artifact_contracts"] = [
        item for item in mutated["artifact_contracts"] if item.get("artifact_id") != "chunked_investigation_report"
    ]

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.artifact_contracts" for item in errors)


def test_phase222_policy_rejects_artifact_only_chat() -> None:
    mutated = copy.deepcopy(policy())
    mutated["answer_contract"]["artifact_only_allowed"] = True

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.answer_contract.artifact_only_allowed" for item in errors)


def test_phase222_policy_rejects_missing_negative_control() -> None:
    mutated = copy.deepcopy(policy())
    mutated["negative_controls"] = [
        item for item in mutated["negative_controls"] if item != "contradictory_evidence_uncertainty"
    ]

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.negative_controls" for item in errors)


def test_phase222_report_rejects_unready_phase221(tmp_path: Path) -> None:
    mutated = policy_with_temp_phase221(tmp_path)
    report_path = Path(mutated["phase221_precondition"]["report_path"])
    unready = phase221_report()
    unready["summary"]["m6_ready"] = False
    write_json(report_path, unready)

    report = run_with_policy(tmp_path, mutated)

    assert report["status"] == "failed"
    assert any(item["id"] == "phase221_report.m6_ready" for item in report["validation_errors"])
