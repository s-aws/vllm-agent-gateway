from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.chat_visible_answer_contract_inventory import (
    DEFAULT_POLICY_PATH,
    ChatVisibleAnswerContractInventoryConfig,
    build_chat_visible_answer_contract_inventory_report,
    load_sources,
    read_json_object,
    run_chat_visible_answer_contract_inventory,
    validate_chat_visible_answer_contract_inventory_report,
    validate_contract_records,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def loaded_sources() -> dict[str, tuple[Path | None, dict[str, Any]]]:
    sources, errors = load_sources(REPO_ROOT, policy())
    assert errors == []
    return sources


def build_report() -> dict[str, Any]:
    return build_chat_visible_answer_contract_inventory_report(
        config_root=REPO_ROOT,
        policy=policy(),
        sources=loaded_sources(),
        source_load_errors=[],
        policy_path=POLICY_PATH,
    )


def error_ids(report: dict[str, Any]) -> set[str]:
    return {str(item.get("id")) for item in report["validation_errors"]}


def test_chat_visible_answer_contract_inventory_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_chat_visible_answer_contract_inventory_report_passes() -> None:
    report = build_report()

    assert report["status"] == "passed"
    assert report["summary"]["contract_count"] == 39
    assert report["summary"]["implemented_coverage_entry_count"] == 39
    assert report["summary"]["stable_baseline_count"] == 4
    assert report["summary"]["phase201_ready"] is True
    assert set(report["summary"]["workflow_counts"]) == set(policy()["required_workflows"])


def test_chat_visible_answer_contract_inventory_records_required_contract_fields() -> None:
    report = build_report()

    for record in report["contract_records"]:
        assert record["answer_heading"]
        assert record["required_sections"]
        assert record["evidence_expectations"]
        assert {"format_a", "json"} == set(record["output_format_behavior"])
        assert "source_mutation_status" in record["safety_boundaries"]
        assert record["run_traceability"]


def test_chat_visible_answer_contract_inventory_rejects_missing_output_format() -> None:
    report = build_report()
    records = copy.deepcopy(report["contract_records"])
    records[0]["output_format_behavior"].pop("json")

    errors = validate_contract_records(REPO_ROOT, policy(), records)

    assert {item["id"] for item in errors} == {"contracts[0].output_format_behavior"}


def test_chat_visible_answer_contract_inventory_rejects_missing_safety_boundary() -> None:
    report = build_report()
    records = copy.deepcopy(report["contract_records"])
    records[0]["safety_boundaries"] = ["source_mutation_status"]

    errors = validate_contract_records(REPO_ROOT, policy(), records)

    assert "contracts[0].safety_boundaries" in {item["id"] for item in errors}


def test_chat_visible_answer_contract_inventory_rejects_missing_workflow() -> None:
    sources = loaded_sources()
    path, coverage = sources["prompt_skill_coverage"]
    filtered = copy.deepcopy(coverage)
    filtered["entries"] = [
        entry for entry in filtered["entries"] if entry.get("selected_workflow") != "task.decompose"
    ]
    sources["prompt_skill_coverage"] = (path, filtered)

    report = build_chat_visible_answer_contract_inventory_report(
        config_root=REPO_ROOT,
        policy=policy(),
        sources=sources,
        source_load_errors=[],
        policy_path=POLICY_PATH,
    )

    assert report["status"] == "failed"
    assert "contracts.workflow.task.decompose" in error_ids(report)


def test_chat_visible_answer_contract_inventory_rejects_hidden_report_edit() -> None:
    report = build_report()
    report["summary"]["contract_count"] = 999

    errors = validate_chat_visible_answer_contract_inventory_report(
        report,
        config_root=REPO_ROOT,
        policy=policy(),
        sources=loaded_sources(),
        source_load_errors=[],
        policy_path=POLICY_PATH,
    )

    assert errors == ["report must match rebuilt chat-visible answer contract inventory"]


def test_chat_visible_answer_contract_inventory_project_report_passes() -> None:
    report = run_chat_visible_answer_contract_inventory(
        ChatVisibleAnswerContractInventoryConfig(config_root=REPO_ROOT, policy_path=DEFAULT_POLICY_PATH)
    )

    assert report["status"] == "passed"
    assert report["summary"]["phase201_ready"] is True
