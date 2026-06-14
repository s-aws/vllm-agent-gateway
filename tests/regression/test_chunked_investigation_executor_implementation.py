from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.chunked_investigation_executor_implementation import (
    ChunkedInvestigationExecutorImplementationConfig,
    validate_chunked_investigation_executor_implementation,
    validate_policy,
)
from vllm_agent_gateway.acceptance.context_index_prototype import read_json_object, write_json


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "chunked_investigation_executor_implementation_policy.json"


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def test_phase223_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase223_policy_rejects_missing_negative_control() -> None:
    mutated = copy.deepcopy(policy())
    mutated["negative_controls"] = ["single_step_prompt_not_chunked"]

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.negative_controls" for item in errors)


def test_phase223_offline_preflight_passes(tmp_path: Path) -> None:
    report = validate_chunked_investigation_executor_implementation(
        ChunkedInvestigationExecutorImplementationConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase223-report.json",
            markdown_output_path=tmp_path / "phase223-report.md",
            live=False,
            require_artifacts=True,
        )
    )

    assert report["status"] == "preflight_passed"
    assert report["summary"]["response_count"] == 1
    assert report["responses"][0]["status"] == "passed"
    assert report["responses"][0]["selected_context_strategy"] == "chunked_investigation"
    assert report["responses"][0]["phase222_contract_satisfied"] is True


def test_phase223_preflight_requires_phase222_ready(tmp_path: Path) -> None:
    mutated = copy.deepcopy(policy())
    phase222_report = tmp_path / "phase222-report.json"
    write_json(
        phase222_report,
        {
            "schema_version": 1,
            "kind": "chunked_investigation_executor_contract_report",
            "status": "passed",
            "summary": {"phase223_ready": False},
        },
    )
    mutated["phase222_precondition"]["report_path"] = str(phase222_report)
    policy_path = tmp_path / "policy.json"
    write_json(policy_path, mutated)

    report = validate_chunked_investigation_executor_implementation(
        ChunkedInvestigationExecutorImplementationConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            output_path=tmp_path / "phase223-report.json",
            markdown_output_path=tmp_path / "phase223-report.md",
            live=False,
            require_artifacts=True,
        )
    )

    assert report["status"] == "failed"
    assert any(item["id"] == "phase222_report.phase223_ready" for item in report["validation_errors"])
