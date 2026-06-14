from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.context_index_prototype import read_json_object, write_json
from vllm_agent_gateway.acceptance.founder_feedback_repair_rerun_gate import (
    FounderFeedbackRepairRerunGateConfig,
    validate_founder_feedback_repair_rerun_gate,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "founder_feedback_repair_rerun_gate_policy.json"


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def test_phase228_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase228_policy_rejects_manual_success_without_rerun() -> None:
    mutated = copy.deepcopy(policy())
    mutated["rerun_gate_contract"]["manual_success_without_rerun_allowed"] = True

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.rerun_gate_contract.manual_success_without_rerun_allowed" for item in errors)


def test_phase228_policy_rejects_missing_holdout_rerun() -> None:
    mutated = copy.deepcopy(policy())
    mutated["rerun_gate_contract"]["holdout_prompt_rerun_required"] = False

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.rerun_gate_contract.holdout_prompt_rerun_required" for item in errors)


def test_phase228_policy_rejects_missing_negative_control() -> None:
    mutated = copy.deepcopy(policy())
    mutated["negative_controls"] = ["missing_target_rerun"]

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.negative_controls" for item in errors)


def test_phase228_preflight_allows_missing_live_artifacts(tmp_path: Path) -> None:
    mutated = copy.deepcopy(policy())
    mutated["phase227_precondition"]["report_path"] = str(tmp_path / "missing-phase227.json")
    mutated["live_feedback_report_path"] = str(tmp_path / "missing-live.json")
    path = tmp_path / "policy.json"
    write_json(path, mutated)

    report = validate_founder_feedback_repair_rerun_gate(
        FounderFeedbackRepairRerunGateConfig(
            config_root=REPO_ROOT,
            policy_path=path,
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
            require_live_artifacts=False,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["phase229_ready"] is True


def test_phase228_requires_live_artifacts_by_default(tmp_path: Path) -> None:
    mutated = copy.deepcopy(policy())
    mutated["phase227_precondition"]["report_path"] = str(tmp_path / "missing-phase227.json")
    mutated["live_feedback_report_path"] = str(tmp_path / "missing-live.json")
    path = tmp_path / "policy.json"
    write_json(path, mutated)

    report = validate_founder_feedback_repair_rerun_gate(
        FounderFeedbackRepairRerunGateConfig(
            config_root=REPO_ROOT,
            policy_path=path,
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
        )
    )

    assert report["status"] == "failed"
    assert any(item["id"] == "report.missing" for item in report["validation_errors"])


def test_phase228_project_report_passes_when_phase227_live_artifacts_exist(tmp_path: Path) -> None:
    report = validate_founder_feedback_repair_rerun_gate(
        FounderFeedbackRepairRerunGateConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["repair_case_count"] == 1
    assert report["summary"]["phase229_ready"] is True
