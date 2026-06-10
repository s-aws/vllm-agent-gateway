from __future__ import annotations

from copy import deepcopy

from vllm_agent_gateway.acceptance.natural_output_format_preference import (
    NATURAL_JSON_SELECTOR_KIND,
    load_natural_output_format_preference_cases,
    validate_default_format_a_response,
    validate_json_preference_response,
    validate_natural_output_format_preference_report,
    validate_preference_case_catalog,
)
from vllm_agent_gateway.acceptance.output_format_parity import OutputFormatParityCase
from vllm_agent_gateway.controller_service.server import (
    ControllerOutputFormat,
    select_controller_output_format,
)


def synthetic_source_case() -> OutputFormatParityCase:
    return OutputFormatParityCase(
        case_id="CQ116-001",
        prompt="Review code quality.",
        target_root="/mnt/c/coinbase_testing_repo_frozen_tmp.github",
        prompt_family="code_quality_and_self_review",
        expected_selected_workflow="code_investigation.plan",
        expected_heading="Code Quality Review:",
        expected_artifact_kind="code_quality_review",
        expected_artifact_keys=("downstream_code_quality_review", "code_quality_review"),
        required_text_markers=("Code Quality Review:", "Source mutation: false", "Artifacts:"),
        required_json_markers=("Code Quality Review:", "Source mutation: false"),
    )


def synthetic_json_contract() -> dict[str, object]:
    return {
        "kind": "agentic_controller_chat_response",
        "output_format": "json",
        "workflow": "workflow_router.plan",
        "status": "completed",
        "chat_contract": {"selected_workflow": "code_investigation.plan"},
        "inline_answer_contract": {
            "kind": "inline_artifact_answer_contract",
            "artifact_kind": "code_quality_review",
            "artifact_key": "downstream_code_quality_review",
            "heading": "Code Quality Review:",
            "lines": [
                "- Findings:",
                "  - CQ-001 [medium/duplication]: repeated branch",
                "- Source mutation: false",
            ],
            "text": (
                "Code Quality Review:\n"
                "- Findings:\n"
                "  - CQ-001 [medium/duplication]: repeated branch\n"
                "- Source mutation: false"
            ),
        },
    }


def synthetic_report() -> dict[str, object]:
    return {
        "kind": "natural_output_format_preference_live_report",
        "cases": [
            {
                "case_id": "NOFP-CQ116-001",
                "responses": {
                    "gateway": {
                        "status": "passed",
                            "preferences": {
                                "default_format_a": {"status": "passed"},
                                "natural_format_a": {"status": "passed"},
                                "natural_json": {
                                    "status": "passed",
                                    "request": {
                                    "selector_kind": NATURAL_JSON_SELECTOR_KIND,
                                    "explicit_output_format_fields": [],
                                },
                            },
                            "explicit_output_format_json": {"status": "passed"},
                            "openai_response_format_json": {"status": "passed"},
                        },
                    },
                    "anythingllm": {
                        "status": "passed",
                        "preferences": {
                            "default_format_a": {"status": "passed"},
                            "natural_format_a": {"status": "passed"},
                            "natural_json": {
                                "status": "passed",
                                "request": {
                                    "selector_kind": NATURAL_JSON_SELECTOR_KIND,
                                    "explicit_output_format_fields": [],
                                },
                            },
                        },
                    },
                },
                "errors": [],
            }
        ],
        "mutation_proof": {
            "runtime_changed_files": [],
            "target_changed_files": {
                "/mnt/c/coinbase_testing_repo_frozen_tmp": [],
                "/mnt/c/coinbase_testing_repo_frozen_tmp.github": [],
            },
            "target_git_changed": {},
        },
    }


def test_natural_output_format_preference_catalog_is_governed() -> None:
    cases = load_natural_output_format_preference_cases()

    assert len(cases) == 4
    assert not validate_preference_case_catalog(cases)
    assert {case.prompt_family for case in cases} == {
        "code_quality_and_self_review",
        "testing_and_defect_diagnosis",
        "tradeoffs_debt_and_engineering_judgment",
        "delivery_and_mentorship",
    }
    assert {case.target_root for case in cases} >= {
        "/mnt/c/coinbase_testing_repo_frozen_tmp",
        "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    }


def test_default_format_a_response_rejects_json_content() -> None:
    case = load_natural_output_format_preference_cases()[0]

    errors = validate_default_format_a_response(
        case,
        text='{"output_format":"json"}',
        selected_output_format="json",
    )

    assert any("default selected output_format" in error for error in errors)
    assert any("default FormatA response was JSON" in error for error in errors)


def test_json_preference_requires_natural_selector_when_requested() -> None:
    case = load_natural_output_format_preference_cases()[0]
    errors = validate_json_preference_response(
        case,
        format_a_text=(
            "Result:\n"
            "Code Quality Review:\n"
            "- Findings:\n"
            "  - CQ-001 [medium/duplication]: repeated branch\n"
            "- Source mutation: false\n"
            "Artifacts:"
        ),
        json_object=synthetic_json_contract(),
        selector_kind="explicit_output_format",
        selected_output_format="json",
        require_natural_selector=True,
    )

    assert any("natural JSON selector_kind" in error for error in errors)


def test_natural_output_format_preference_report_passes_clean_shape() -> None:
    assert validate_natural_output_format_preference_report(synthetic_report()) == []


def test_natural_output_format_preference_report_rejects_hidden_explicit_natural_json() -> None:
    report = synthetic_report()
    gateway_natural = report["cases"][0]["responses"]["gateway"]["preferences"]["natural_json"]  # type: ignore[index]
    gateway_natural["request"]["explicit_output_format_fields"] = ["output_format"]  # type: ignore[index]

    errors = validate_natural_output_format_preference_report(report)

    assert any("natural_json used explicit selector fields" in error for error in errors)


def test_natural_output_format_preference_report_rejects_missing_openai_holdout() -> None:
    report = deepcopy(synthetic_report())
    gateway_preferences = report["cases"][0]["responses"]["gateway"]["preferences"]  # type: ignore[index]
    gateway_preferences.pop("openai_response_format_json")  # type: ignore[union-attr]

    errors = validate_natural_output_format_preference_report(report)

    assert "NOFP-CQ116-001 gateway missing preference openai_response_format_json" in errors


def test_selector_uses_latest_user_message_for_natural_format() -> None:
    selected = select_controller_output_format(
        {
            "messages": [
                {"role": "user", "content": "Return JSON."},
                {"role": "assistant", "content": "Previous answer."},
                {"role": "user", "content": "Now answer in plain English."},
            ]
        }
    )

    assert selected == ControllerOutputFormat.FORMAT_A


def test_selector_explicit_format_beats_natural_json_request() -> None:
    selected = select_controller_output_format(
        {
            "output_format": "format_a",
            "messages": [{"role": "user", "content": "Return JSON."}],
        }
    )

    assert selected == ControllerOutputFormat.FORMAT_A


def test_selector_natural_json_works_without_explicit_fields() -> None:
    payload = {"messages": [{"role": "user", "content": "Respond with JSON."}]}

    assert "output_format" not in payload
    assert "response_format" not in payload
    assert select_controller_output_format(payload) == ControllerOutputFormat.JSON
