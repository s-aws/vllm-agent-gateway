from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.workflow_skill_tool_selection_matrix import (
    DEFAULT_POLICY_PATH,
    WorkflowSkillToolSelectionMatrixConfig,
    build_workflow_skill_tool_selection_matrix_report,
    load_sources,
    matrix_records,
    read_json_object,
    run_workflow_skill_tool_selection_matrix,
    validate_matrix_records,
    validate_policy,
    validate_workflow_skill_tool_selection_matrix_report,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def loaded_sources() -> tuple[dict[str, tuple[Path, dict[str, Any]]], list[dict[str, str]]]:
    return load_sources(REPO_ROOT, policy())


def build_report() -> dict[str, Any]:
    sources, errors = loaded_sources()
    return build_workflow_skill_tool_selection_matrix_report(
        config_root=REPO_ROOT,
        policy=policy(),
        sources=sources,
        source_errors=errors,
        policy_path=POLICY_PATH,
    )


def error_ids(errors: list[dict[str, str]]) -> set[str]:
    return {str(item.get("id")) for item in errors}


def test_workflow_skill_tool_selection_matrix_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_workflow_skill_tool_selection_matrix_report_passes() -> None:
    report = build_report()

    assert report["status"] == "passed"
    assert report["summary"]["matrix_record_count"] == 39
    assert report["summary"]["registered_gap_count"] == 0
    assert report["summary"]["phase151_explainability_covered_count"] >= 3
    assert report["summary"]["phase204_explainability_needed_count"] > 0
    assert report["summary"]["holdout_proof_needed_count"] > 0
    assert any(gap["gap_class"] == "missing_holdout_proof" for gap in report["gap_records"])
    assert report["summary"]["non_coinbase_proof_row_count"] > 0
    assert report["summary"]["phase204_ready"] is True


def test_workflow_skill_tool_selection_matrix_records_registered_expectations() -> None:
    sources, errors = loaded_sources()
    assert errors == []
    records = matrix_records(policy(), sources)

    for record in records:
        assert record["registered_workflow"] is True
        assert record["missing_skills"] == []
        assert record["missing_tools"] == []
        assert set(record["route_surfaces"]) == {"gateway", "anythingllm"}


def test_workflow_skill_tool_selection_matrix_rejects_missing_skill() -> None:
    sources, _errors = loaded_sources()
    records = matrix_records(policy(), sources)
    records[0]["missing_skills"] = ["missing-skill"]

    errors = validate_matrix_records(policy(), records)

    assert "matrix[0].missing_skills" in error_ids(errors)


def test_workflow_skill_tool_selection_matrix_rejects_missing_non_coinbase_proof() -> None:
    sources, _errors = loaded_sources()
    records = matrix_records(policy(), sources)
    for record in records:
        record["non_coinbase_proof_count"] = 0

    errors = validate_matrix_records(policy(), records)

    assert "matrix.non_coinbase_proof" in error_ids(errors)


def test_workflow_skill_tool_selection_matrix_rejects_hidden_report_edit() -> None:
    sources, source_errors = loaded_sources()
    report = build_report()
    edited = copy.deepcopy(report)
    edited["summary"]["matrix_record_count"] = 999

    errors = validate_workflow_skill_tool_selection_matrix_report(
        edited,
        config_root=REPO_ROOT,
        policy=policy(),
        sources=sources,
        source_errors=source_errors,
        policy_path=POLICY_PATH,
    )

    assert errors == ["report must match rebuilt workflow/skill/tool selection matrix"]


def test_workflow_skill_tool_selection_matrix_writes_project_report() -> None:
    report = run_workflow_skill_tool_selection_matrix(
        WorkflowSkillToolSelectionMatrixConfig(config_root=REPO_ROOT, policy_path=DEFAULT_POLICY_PATH)
    )

    assert report["status"] == "passed"
    assert report["summary"]["phase204_ready"] is True
