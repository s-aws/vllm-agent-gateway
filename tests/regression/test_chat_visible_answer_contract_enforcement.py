from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.chat_visible_answer_contract_enforcement import (
    DEFAULT_POLICY_PATH,
    ChatVisibleAnswerContractEnforcementConfig,
    apply_negative_control_format_a,
    apply_negative_control_json,
    build_chat_visible_answer_contract_enforcement_report,
    enforcement_case,
    evaluate_format_a,
    evaluate_json,
    load_phase200,
    positive_format_a,
    positive_json,
    read_json_object,
    run_chat_visible_answer_contract_enforcement,
    validate_chat_visible_answer_contract_enforcement_report,
    validate_enforcement_cases,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def phase200() -> tuple[Path, dict[str, Any], list[dict[str, str]]]:
    return load_phase200(REPO_ROOT, policy())


def build_report() -> dict[str, Any]:
    phase200_path, phase200_report, errors = phase200()
    return build_chat_visible_answer_contract_enforcement_report(
        config_root=REPO_ROOT,
        policy=policy(),
        phase200_path=phase200_path,
        phase200_report=phase200_report,
        source_load_errors=errors,
        policy_path=POLICY_PATH,
    )


def first_contract_record() -> dict[str, Any]:
    _, phase200_report, errors = phase200()
    assert errors == []
    return phase200_report["contract_records"][0]


def test_chat_visible_answer_contract_enforcement_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_chat_visible_answer_contract_enforcement_report_passes() -> None:
    report = build_report()

    assert report["status"] == "passed"
    assert report["summary"]["contract_count"] == 39
    assert report["summary"]["positive_case_count"] == 78
    assert report["summary"]["passed_positive_case_count"] == 78
    assert report["summary"]["negative_case_count"] == 312
    assert report["summary"]["rejected_negative_case_count"] == 312
    assert report["summary"]["phase202_ready"] is True


def test_chat_visible_answer_contract_enforcement_format_a_positive_passes() -> None:
    reasons = evaluate_format_a(positive_format_a(first_contract_record()))

    assert reasons == []


def test_chat_visible_answer_contract_enforcement_json_positive_passes() -> None:
    reasons = evaluate_json(positive_json(first_contract_record()))

    assert reasons == []


def test_chat_visible_answer_contract_enforcement_rejects_artifact_only_answers() -> None:
    record = first_contract_record()
    format_a_reasons = evaluate_format_a(apply_negative_control_format_a(positive_format_a(record), "artifact_only"))
    json_reasons = evaluate_json(apply_negative_control_json(positive_json(record), "artifact_only"))

    assert "artifact_only" in format_a_reasons
    assert "artifact_only" in json_reasons


def test_chat_visible_answer_contract_enforcement_rejects_missing_evidence() -> None:
    record = first_contract_record()
    format_a_reasons = evaluate_format_a(apply_negative_control_format_a(positive_format_a(record), "missing_evidence"))
    json_reasons = evaluate_json(apply_negative_control_json(positive_json(record), "missing_evidence"))

    assert "missing_evidence" in format_a_reasons
    assert "missing_evidence" in json_reasons


def test_chat_visible_answer_contract_enforcement_rejects_missing_safety_boundary() -> None:
    record = first_contract_record()
    format_a_reasons = evaluate_format_a(apply_negative_control_format_a(positive_format_a(record), "missing_safety_boundary"))
    json_reasons = evaluate_json(apply_negative_control_json(positive_json(record), "missing_safety_boundary"))

    assert "missing_safety_boundary" in format_a_reasons
    assert "missing_safety_boundary" in json_reasons


def test_chat_visible_answer_contract_enforcement_rejects_unsupported_mutation_claim() -> None:
    record = first_contract_record()
    format_a_reasons = evaluate_format_a(apply_negative_control_format_a(positive_format_a(record), "unsupported_mutation_claim"))
    json_reasons = evaluate_json(apply_negative_control_json(positive_json(record), "unsupported_mutation_claim"))

    assert "unsupported_mutation_claim" in format_a_reasons
    assert "unsupported_mutation_claim" in json_reasons


def test_chat_visible_answer_contract_enforcement_rejects_vague_marker_filled_answer() -> None:
    record = first_contract_record()
    vague = (
        "Answer:\n"
        "This is handled.\n"
        "Evidence: source: something.\n"
        "Safety boundary: source_mutation_status=no source mutation.\n"
        "run_id: workflow-router-phase201"
    )

    reasons = evaluate_format_a(vague, record)

    assert "missing_contract_detail" in reasons


def test_chat_visible_answer_contract_enforcement_rejects_json_missing_output_format() -> None:
    payload = positive_json(first_contract_record())
    payload.pop("output_format", None)

    reasons = evaluate_json(payload)

    assert "missing_output_format" in reasons


def test_chat_visible_answer_contract_enforcement_rejects_missing_output_format_case() -> None:
    case = enforcement_case(first_contract_record(), "format_a")
    case.pop("output_format")

    errors = validate_enforcement_cases([case], policy())

    assert "cases[0].output_format" in {item["id"] for item in errors}


def test_chat_visible_answer_contract_enforcement_rejects_hidden_report_edit() -> None:
    phase200_path, phase200_report, source_errors = phase200()
    report = build_report()
    edited = copy.deepcopy(report)
    edited["summary"]["contract_count"] = 999

    errors = validate_chat_visible_answer_contract_enforcement_report(
        edited,
        config_root=REPO_ROOT,
        policy=policy(),
        phase200_path=phase200_path,
        phase200_report=phase200_report,
        source_load_errors=source_errors,
        policy_path=POLICY_PATH,
    )

    assert errors == ["report must match rebuilt chat-visible answer contract enforcement"]


def test_chat_visible_answer_contract_enforcement_project_report_passes() -> None:
    report = run_chat_visible_answer_contract_enforcement(
        ChatVisibleAnswerContractEnforcementConfig(config_root=REPO_ROOT, policy_path=DEFAULT_POLICY_PATH)
    )

    assert report["status"] == "passed"
    assert report["summary"]["phase202_ready"] is True
