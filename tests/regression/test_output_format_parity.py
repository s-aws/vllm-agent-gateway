from __future__ import annotations

from vllm_agent_gateway.acceptance.output_format_parity import (
    OutputFormatParityCase,
    load_output_format_parity_cases,
    validate_case_catalog,
    validate_output_format_pair,
    validate_output_format_parity_report,
)


def synthetic_case() -> OutputFormatParityCase:
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


def test_output_format_parity_catalog_is_governed() -> None:
    cases = load_output_format_parity_cases()

    assert not validate_case_catalog(cases)
    assert len(cases) == 8
    assert {case.target_root for case in cases} >= {
        "/mnt/c/coinbase_testing_repo_frozen_tmp",
        "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    }


def test_output_format_pair_passes_when_json_inline_text_matches_format_a() -> None:
    case = synthetic_case()
    json_object = synthetic_json_contract()
    format_a_text = (
        "Result:\n"
        "- Selected workflow: code_investigation.plan\n\n"
        "Code Quality Review:\n"
        "- Findings:\n"
        "  - CQ-001 [medium/duplication]: repeated branch\n"
        "- Source mutation: false\n\n"
        "Artifacts:\n"
        "- downstream_code_quality_review: /tmp/review.json"
    )

    assert validate_output_format_pair(case, format_a_text=format_a_text, json_object=json_object) == []


def test_output_format_pair_rejects_artifact_only_json() -> None:
    case = synthetic_case()
    json_object = synthetic_json_contract()
    json_object.pop("inline_answer_contract")

    errors = validate_output_format_pair(
        case,
        format_a_text="Result:\nArtifacts:\n- downstream_code_quality_review: /tmp/review.json",
        json_object=json_object,
    )

    assert any("missing inline_answer_contract" in error for error in errors)
    assert any("FormatA missing marker: Code Quality Review:" in error for error in errors)


def test_output_format_pair_allows_independent_run_volatile_source_rank_differences() -> None:
    case = synthetic_case()
    json_object = synthetic_json_contract()
    json_object["inline_answer_contract"]["text"] = (  # type: ignore[index]
        "Code Quality Review:\n"
        "- Target: core/stealth_order_manager.py; dashboard_server.py\n"
        "- Status: ready\n"
        "- Review mode: duplication_review\n"
        "- Recommendation: Keep one authoritative lookup path.\n"
        "- Evidence files: dashboard_server.py (source, 1 match(es))\n"
        "- Source refs: dashboard_server.py:10\n"
        "- Source mutation: false"
    )
    format_a_text = (
        "Result:\n"
        "- Selected workflow: code_investigation.plan\n\n"
        "Code Quality Review:\n"
        "- Target: core/stealth_order_manager.py; core/enums.py\n"
        "- Status: ready\n"
        "- Review mode: duplication_review\n"
        "- Recommendation: Keep one authoritative lookup path.\n"
        "- Evidence files: core/stealth_order_manager.py (source, 1 match(es))\n"
        "- Source refs: core/stealth_order_manager.py:120\n"
        "- Source mutation: false\n\n"
        "Artifacts:\n"
        "- downstream_code_quality_review: /tmp/review.json"
    )

    assert validate_output_format_pair(
        case,
        format_a_text=format_a_text,
        json_object=json_object,
        require_exact_inline_match=False,
    ) == []


def test_output_format_pair_tolerant_mode_rejects_marker_only_overlap() -> None:
    case = synthetic_case()
    json_object = synthetic_json_contract()
    json_object["inline_answer_contract"]["text"] = (  # type: ignore[index]
        "Code Quality Review:\n"
        "- Target: unrelated.py\n"
        "- Source mutation: false"
    )
    format_a_text = (
        "Result:\n"
        "Code Quality Review:\n"
        "- Target: other.py\n"
        "- Source mutation: false\n"
        "Artifacts:"
    )

    errors = validate_output_format_pair(
        case,
        format_a_text=format_a_text,
        json_object=json_object,
        require_exact_inline_match=False,
    )

    assert any("shared only" in error for error in errors)


def test_output_format_parity_report_rejects_missing_anythingllm_surface() -> None:
    report = {
        "kind": "output_format_parity_live_report",
        "cases": [
            {
                "case_id": "CQ116-001",
                "responses": {"gateway": {"status": "passed"}},
                "errors": [],
            }
        ],
        "mutation_proof": {
            "runtime_changed_files": [],
            "target_changed_files": {},
            "target_git_changed": {},
        },
    }

    errors = validate_output_format_parity_report(report)

    assert "CQ116-001 missing anythingllm response" in errors
