from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.chat_visible_output_usefulness_refresh import (
    DEFAULT_POLICY_PATH,
    ChatVisibleOutputUsefulnessRefreshConfig,
    build_chat_visible_output_usefulness_refresh_report,
    load_required_reports,
    read_json_object,
    run_chat_visible_output_usefulness_refresh,
    validate_chat_visible_output_usefulness_refresh_report,
    validate_parity_report,
    validate_policy,
    validate_usefulness_report,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def loaded_reports() -> tuple[dict[str, tuple[Path, dict[str, Any]]], list[dict[str, str]]]:
    return load_required_reports(REPO_ROOT, policy())


def build_report() -> dict[str, Any]:
    reports, errors = loaded_reports()
    return build_chat_visible_output_usefulness_refresh_report(
        config_root=REPO_ROOT,
        policy=policy(),
        policy_path=POLICY_PATH,
        loaded_reports=reports,
        load_errors=errors,
    )


def error_ids(errors: list[dict[str, str]]) -> set[str]:
    return {str(item.get("id")) for item in errors}


def test_chat_visible_output_usefulness_refresh_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_chat_visible_output_usefulness_refresh_project_report_passes() -> None:
    report = build_report()

    assert report["status"] == "passed"
    assert report["summary"]["live_case_count"] == 8
    assert report["summary"]["surface_pass_counts"] == {"gateway": 8, "anythingllm": 8}
    assert report["summary"]["answer_usefulness_checked_case_count"] == 40
    assert report["summary"]["m2_ready"] is True
    assert report["summary"]["phase203_ready"] is True


def test_chat_visible_output_usefulness_refresh_rejects_missing_anythingllm_surface() -> None:
    reports, _errors = loaded_reports()
    parity = copy.deepcopy(reports["output_format_parity"][1])
    parity["cases"][0]["responses"].pop("anythingllm")

    errors = validate_parity_report(parity, policy())

    assert "output_format_parity.report" in error_ids(errors)
    assert "output_format_parity.CQ116-001.anythingllm.status" in error_ids(errors)


def test_chat_visible_output_usefulness_refresh_rejects_json_missing_output_format() -> None:
    reports, _errors = loaded_reports()
    parity = copy.deepcopy(reports["output_format_parity"][1])
    parsed = parity["cases"][0]["responses"]["gateway"]["json"]["parsed"]
    parsed.pop("output_format", None)

    errors = validate_parity_report(parity, policy())

    assert "output_format_parity.CQ116-001.gateway.json.output_format" in error_ids(errors)


def test_chat_visible_output_usefulness_refresh_rejects_missing_port_health() -> None:
    reports, _errors = loaded_reports()
    parity = copy.deepcopy(reports["output_format_parity"][1])
    parity["port_health"] = []

    errors = validate_parity_report(parity, policy())

    assert "output_format_parity.port_health" in error_ids(errors)
    assert "output_format_parity.port_health.missing_probes" in error_ids(errors)


def test_chat_visible_output_usefulness_refresh_rejects_failed_port_health() -> None:
    reports, _errors = loaded_reports()
    parity = copy.deepcopy(reports["output_format_parity"][1])
    parity["port_health"][0]["status"] = "failed"

    errors = validate_parity_report(parity, policy())

    assert "output_format_parity.port_health[0].status" in error_ids(errors)


def test_chat_visible_output_usefulness_refresh_rejects_truncated_port_health() -> None:
    reports, _errors = loaded_reports()
    parity = copy.deepcopy(reports["output_format_parity"][1])
    parity["port_health"] = parity["port_health"][:1]

    errors = validate_parity_report(parity, policy())

    assert "output_format_parity.port_health.missing_probes" in error_ids(errors)


def test_chat_visible_output_usefulness_refresh_rejects_usefulness_errors() -> None:
    reports, _errors = loaded_reports()
    usefulness = copy.deepcopy(reports["answer_usefulness"][1])
    usefulness["summary"]["error_count"] = 1
    usefulness["errors"] = ["forced failure"]

    errors = validate_usefulness_report(usefulness, policy())

    assert "answer_usefulness.errors" in error_ids(errors)
    assert "answer_usefulness.error_count" in error_ids(errors)


def test_chat_visible_output_usefulness_refresh_rejects_usefulness_without_artifacts() -> None:
    reports, _errors = loaded_reports()
    usefulness = copy.deepcopy(reports["answer_usefulness"][1])
    usefulness["require_artifacts"] = False

    errors = validate_usefulness_report(usefulness, policy())

    assert "answer_usefulness.require_artifacts" in error_ids(errors)


def test_chat_visible_output_usefulness_refresh_rejects_entry_case_mismatch() -> None:
    reports, _errors = loaded_reports()
    usefulness = copy.deepcopy(reports["answer_usefulness"][1])
    usefulness["entries"][0]["checked_cases"] = 1

    errors = validate_usefulness_report(usefulness, policy())

    assert "answer_usefulness.entries.phase116_code_quality.case_count" in error_ids(errors)
    assert "answer_usefulness.checked_case_total" in error_ids(errors)


def test_chat_visible_output_usefulness_refresh_rejects_hidden_report_edit() -> None:
    reports, load_errors = loaded_reports()
    report = build_report()
    edited = copy.deepcopy(report)
    edited["summary"]["live_case_count"] = 999

    errors = validate_chat_visible_output_usefulness_refresh_report(
        edited,
        config_root=REPO_ROOT,
        policy=policy(),
        policy_path=POLICY_PATH,
        loaded_reports=reports,
        load_errors=load_errors,
    )

    assert errors == ["report must match rebuilt chat-visible output usefulness refresh"]


def test_chat_visible_output_usefulness_refresh_writes_project_report() -> None:
    report = run_chat_visible_output_usefulness_refresh(
        ChatVisibleOutputUsefulnessRefreshConfig(config_root=REPO_ROOT, policy_path=DEFAULT_POLICY_PATH)
    )

    assert report["status"] == "passed"
    assert report["summary"]["phase203_ready"] is True
