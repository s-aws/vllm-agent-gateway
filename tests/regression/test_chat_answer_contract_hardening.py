import json
from pathlib import Path

from vllm_agent_gateway.acceptance.chat_answer_contract_hardening import (
    ChatAnswerContractHardeningConfig,
    build_chat_answer_contract_hardening_report,
    read_json_object,
    run_chat_answer_contract_hardening,
    synthetic_response_for_case,
    validate_policy,
    validate_rendered_case,
)
from vllm_agent_gateway.controller_service.server import (
    ControllerOutputFormat,
    assistant_content_for_controller_response,
)


POLICY_PATH = Path(__file__).resolve().parents[2] / "runtime" / "chat_answer_contract_hardening_policy.json"


def load_policy() -> dict:
    return read_json_object(POLICY_PATH)


def test_chat_answer_contract_hardening_policy_passes() -> None:
    assert validate_policy(load_policy()) == []


def test_chat_answer_contract_hardening_report_passes_current_policy(tmp_path: Path) -> None:
    policy = load_policy()

    report = build_chat_answer_contract_hardening_report(
        config_root=tmp_path,
        policy=policy,
        fixture_root=tmp_path / "fixtures",
        policy_path=POLICY_PATH,
    )

    assert report["status"] == "passed"
    assert report["summary"]["case_count"] == 7
    assert report["summary"]["blocking_error_count"] == 0


def test_chat_answer_contract_hardening_rejects_missing_required_marker(tmp_path: Path) -> None:
    policy = load_policy()
    policy["cases"][0]["required_format_a_markers"].append("marker that should not render")

    report = build_chat_answer_contract_hardening_report(
        config_root=tmp_path,
        policy=policy,
        fixture_root=tmp_path / "fixtures",
    )

    assert report["status"] == "failed"
    assert any("marker that should not render" in error["message"] for error in report["validation_errors"])


def test_chat_answer_contract_hardening_requires_negative_artifact_guard() -> None:
    policy = load_policy()
    for case in policy["cases"]:
        case.pop("negative_artifact_only_guard", None)

    errors = validate_policy(policy)

    assert any(error["id"] == "policy.negative_artifact_only_guard" for error in errors)


def test_chat_answer_contract_hardening_mixed_guard_prefers_investigation_plan(tmp_path: Path) -> None:
    policy = load_policy()
    case = next(item for item in policy["cases"] if item["case_id"] == "P180-007")
    response = synthetic_response_for_case(case, tmp_path / "fixtures")

    result = validate_rendered_case(case, response)
    format_a = assistant_content_for_controller_response(response, ControllerOutputFormat.FORMAT_A)
    parsed = json.loads(assistant_content_for_controller_response(response, ControllerOutputFormat.JSON))

    assert result["status"] == "passed"
    assert "- Beginning point: core/stealth_order_manager.py:4169" in format_a
    assert "- Source mutation: false" in format_a
    assert "- Entrypoints:" not in format_a
    assert parsed["inline_answer_contract"]["artifact_kind"] == "investigation_plan"
    assert parsed["inline_answer_contract"]["source_mutation"] == "false"


def test_run_chat_answer_contract_hardening_writes_json_and_markdown(tmp_path: Path) -> None:
    policy = load_policy()
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    report = run_chat_answer_contract_hardening(
        ChatAnswerContractHardeningConfig(
            config_root=tmp_path,
            policy_path=Path("policy.json"),
            output_path=Path("out/report.json"),
            markdown_output_path=Path("out/report.md"),
            fixture_root=Path("fixtures"),
        )
    )

    persisted = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))

    assert report["status"] == "passed"
    assert persisted["report_path"] == str((tmp_path / "out" / "report.json").resolve())
    assert (tmp_path / "out" / "report.md").read_text(encoding="utf-8").startswith(
        "# Chat Answer Contract Hardening"
    )
