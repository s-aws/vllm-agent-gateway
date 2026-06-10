from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.transcript_quality_feedback_intake import (
    DEFAULT_POLICY_PATH,
    FindingCategory,
    build_transcript_quality_feedback_intake_report,
    read_json_object,
    validate_policy,
    validate_transcript_quality_feedback_intake_report,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH
PHASE157_PATH = Path("runtime-state/founder-field-round1/phase157/phase157-founder-field-round1-report.json")
FIELD_PATH = Path("runtime-state/founder-field-round1/phase157/phase157-founder-field-run.json")
FIELD_MARKDOWN_PATH = Path("runtime-state/founder-field-round1/phase157/phase157-founder-field-run.md")
_FIELD_SENTINEL = object()


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def case(
    case_id: str,
    classification: str,
    *,
    output_contract_status: str = "passed",
    semantic_quality_status: str = "passed",
    prompt_risk: str = "",
    expected_skill_id: str = "",
) -> dict[str, Any]:
    prompt = f"Prompt for {case_id}"
    if classification == "advisory" and not prompt_risk:
        prompt_risk = "Prompt wording can select a nearby handler unless the boundary is explicit."
    if classification == "blocker" and output_contract_status == "passed" and semantic_quality_status == "passed":
        output_contract_status = "failed"
    return {
        "case_id": case_id,
        "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8", errors="replace")).hexdigest(),
        "expected_workflow": "code_investigation.plan",
        "expected_skill_id": expected_skill_id,
        "expected_artifact_key": "",
        "status": "passed" if classification != "blocker" else "failed",
        "quality_classification": classification,
        "output_contract_status": output_contract_status,
        "semantic_quality_status": semantic_quality_status,
        "run_id": f"workflow-router-{case_id}",
        "text_sha256": "b" * 64,
        "initial_difference": "No marker-level or semantic difference from the baseline target.",
        "suggested_prompt_if_missed": "",
        "prompt_risk": prompt_risk,
    }


def phase157_report(cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "founder_field_round1_report",
        "phase": 157,
        "priority_backlog_id": "P0-BB-021",
        "status": "passed",
        "quality_status": "advisory",
        "field_report_path": str(FIELD_PATH),
        "field_report_sha256": "c" * 64,
        "markdown_report_path": str(FIELD_MARKDOWN_PATH),
        "case_results": cases,
        "validation_errors": [],
        "phase158_required": True,
        "summary": {
            "case_count": len(cases),
            "pass_case_count": sum(1 for item in cases if item["quality_classification"] == "pass"),
            "advisory_case_count": sum(1 for item in cases if item["quality_classification"] == "advisory"),
            "blocker_case_count": sum(1 for item in cases if item["quality_classification"] == "blocker"),
            "target_root_count": 1,
            "target_roots": ["/mnt/c/coinbase_testing_repo_frozen_tmp.github"],
            "workflow_count": 1,
            "workflows": ["code_investigation.plan"],
            "phase158_required": True,
            "source_status": "passed",
            "source_passed": len(cases),
            "source_failed": 0,
        },
    }


def field_report(cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "founder_field_prompt_evaluation",
        "status": "passed",
        "cases": [
            {
                "case_id": item["case_id"],
                "run_id": item["run_id"],
                "prompt": f"Prompt for {item['case_id']}",
                "refined_prompt": f"Refined prompt for {item['case_id']}",
                "text_sample": f"Selected workflow: {item['expected_workflow']}",
                "text_sha256": item["text_sha256"],
            }
            for item in cases
        ],
    }


def build_report(
    *,
    cases: list[dict[str, Any]] | None = None,
    policy_payload: dict[str, Any] | None = None,
    phase157_payload: dict[str, Any] | None = None,
    field_payload: dict[str, Any] | None | object = _FIELD_SENTINEL,
    founder_notes: dict[str, Any] | None = None,
    phase157_report_path: Path | None = PHASE157_PATH,
    field_report_path: Path | None = FIELD_PATH,
) -> dict[str, Any]:
    source_cases = cases if cases is not None else [case("P01", "advisory"), case("P02", "pass")]
    raw_field_payload = field_report(source_cases) if field_payload is _FIELD_SENTINEL else field_payload
    return build_transcript_quality_feedback_intake_report(
        policy=policy_payload or policy(),
        phase157_report=phase157_payload or phase157_report(source_cases),
        field_report=raw_field_payload,  # type: ignore[arg-type]
        founder_notes=founder_notes,
        policy_path=POLICY_PATH,
        phase157_report_path=phase157_report_path,
        field_report_path=field_report_path,
        field_markdown_path=FIELD_MARKDOWN_PATH,
    )


def validate_report(
    report: dict[str, Any],
    *,
    cases: list[dict[str, Any]] | None = None,
    policy_payload: dict[str, Any] | None = None,
    phase157_payload: dict[str, Any] | None = None,
    field_payload: dict[str, Any] | None | object = _FIELD_SENTINEL,
    founder_notes: dict[str, Any] | None = None,
    phase157_report_path: Path | None = PHASE157_PATH,
    field_report_path: Path | None = FIELD_PATH,
) -> list[str]:
    source_cases = cases if cases is not None else [case("P01", "advisory"), case("P02", "pass")]
    raw_field_payload = field_report(source_cases) if field_payload is _FIELD_SENTINEL else field_payload
    return validate_transcript_quality_feedback_intake_report(
        report,
        policy=policy_payload or policy(),
        phase157_report=phase157_payload or phase157_report(source_cases),
        field_report=raw_field_payload,  # type: ignore[arg-type]
        founder_notes=founder_notes,
        policy_path=POLICY_PATH,
        phase157_report_path=phase157_report_path,
        field_report_path=field_report_path,
        field_markdown_path=FIELD_MARKDOWN_PATH,
    )


def test_project_transcript_quality_feedback_intake_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_advisory_cases_become_monitoring_findings_not_phase159_repairs() -> None:
    report = build_report()

    assert validate_report(report) == []
    assert report["status"] == "passed"
    assert report["summary"]["accepted_finding_count"] == 1
    assert report["summary"]["phase159_eligible_count"] == 0
    assert report["phase159_required"] is False
    finding = report["accepted_findings"][0]
    assert finding["category"] == FindingCategory.PROMPT_ISSUE.value
    assert finding["decision"] == "accepted_for_monitoring"
    assert finding["owner_path"] == "prompt_catalog_review"
    assert finding["required_rerun_gate"] == "phase157_founder_field_round1"
    assert finding["transcript_reference"]["field_report_path"] == str(FIELD_PATH)


def test_output_contract_blocker_is_phase159_harness_issue() -> None:
    cases = [case("P01", "blocker", output_contract_status="failed"), case("P02", "pass")]
    report = build_report(cases=cases)

    assert report["status"] == "passed"
    finding = report["accepted_findings"][0]
    assert finding["category"] == FindingCategory.HARNESS_ISSUE.value
    assert finding["decision"] == "accepted_for_phase159"
    assert finding["phase159_eligible"] is True
    assert finding["required_rerun_gate"] == "phase159_target_plus_holdout"
    assert report["phase159_required"] is True


def test_skill_backed_semantic_blocker_is_skill_tool_gap_candidate() -> None:
    cases = [
        case(
            "P01",
            "blocker",
            output_contract_status="passed",
            semantic_quality_status="failed",
            expected_skill_id="code.entrypoint_discovery",
        )
    ]
    report = build_report(cases=cases)

    assert report["status"] == "passed"
    assert report["accepted_findings"][0]["category"] == FindingCategory.MISSING_SKILL_TOOL.value
    assert report["accepted_findings"][0]["owner_path"] == "skill_tool_gap_review"
    assert report["summary"]["phase159_eligible_count"] == 1


def test_founder_note_can_create_phase159_eligible_finding() -> None:
    notes = {
        "kind": "transcript_quality_founder_notes",
        "phase": 158,
        "notes": [
            {
                "note_id": "FN-001",
                "case_id": "P02",
                "category": "model_capability",
                "severity": "medium",
                "text": "The answer missed the requested confidence statement in chat.",
            }
        ],
    }
    report = build_report(founder_notes=notes)

    assert report["status"] == "passed"
    assert report["summary"]["founder_note_count"] == 1
    note_findings = [item for item in report["accepted_findings"] if item["source"] == "founder_note"]
    assert len(note_findings) == 1
    assert note_findings[0]["decision"] == "accepted_for_phase159"
    assert note_findings[0]["phase159_eligible"] is True


def test_vague_or_unlinked_founder_note_is_rejected_without_creating_work() -> None:
    notes = {
        "kind": "transcript_quality_founder_notes",
        "phase": 158,
        "notes": [
            {
                "note_id": "FN-001",
                "case_id": "missing",
                "category": "model_capability",
                "severity": "medium",
                "text": "bad",
            }
        ],
    }
    report = build_report(founder_notes=notes)

    assert report["status"] == "passed"
    assert report["summary"]["rejected_finding_count"] == 1
    assert report["summary"]["phase159_eligible_count"] == 0
    rejected = report["rejected_findings"][0]
    assert rejected["decision"] == "rejected_no_action"
    assert "unlinked_case_id" in rejected["reasons"]
    assert "vague_or_empty_feedback" in rejected["reasons"]


def test_founder_note_missing_severity_is_rejected_without_creating_work() -> None:
    notes = {
        "kind": "transcript_quality_founder_notes",
        "phase": 158,
        "notes": [
            {
                "note_id": "FN-001",
                "case_id": "P02",
                "category": "model_capability",
                "text": "The answer missed the requested confidence statement in chat.",
            }
        ],
    }
    report = build_report(founder_notes=notes)

    assert report["status"] == "passed"
    assert report["summary"]["rejected_finding_count"] == 1
    assert "unknown_or_missing_severity" in report["rejected_findings"][0]["reasons"]


def test_non_object_founder_note_is_rejected_without_creating_work() -> None:
    notes = {
        "kind": "transcript_quality_founder_notes",
        "phase": 158,
        "notes": ["bad"],
    }
    report = build_report(founder_notes=notes)

    assert report["status"] == "passed"
    assert report["summary"]["founder_note_count"] == 1
    assert report["summary"]["rejected_finding_count"] == 1
    assert report["rejected_findings"][0]["reasons"] == ["malformed_note"]


def test_invalid_founder_notes_payload_fails_intake() -> None:
    notes = {"kind": "wrong", "phase": 158, "notes": []}
    report = build_report(founder_notes=notes)

    assert report["status"] == "failed"
    assert any("founder_notes.kind" in error["id"] for error in report["validation_errors"])


def test_missing_raw_field_report_fails_intake() -> None:
    report = build_report(field_payload=None)

    assert report["status"] == "failed"
    assert any(error["id"] == "field_report.missing" for error in report["validation_errors"])


def test_unknown_quality_classification_fails_intake() -> None:
    cases = [case("P01", "advisory")]
    source = phase157_report(cases)
    source["case_results"][0]["quality_classification"] = "unclear"
    source["summary"]["advisory_case_count"] = 0
    report = build_report(cases=cases, phase157_payload=source)

    assert report["status"] == "failed"
    assert any("quality_classification" in error["id"] for error in report["validation_errors"])


def test_advisory_without_prompt_risk_fails_intake() -> None:
    cases = [case("P01", "advisory", prompt_risk="explicit")]
    source = phase157_report(cases)
    source["case_results"][0]["prompt_risk"] = ""
    report = build_report(cases=cases, phase157_payload=source)

    assert report["status"] == "failed"
    assert any(error["id"].endswith(".prompt_risk") for error in report["validation_errors"])


def test_raw_field_report_run_id_mismatch_fails_intake() -> None:
    cases = [case("P01", "advisory")]
    raw = field_report(cases)
    raw["cases"][0]["run_id"] = "workflow-router-other"
    report = build_report(cases=cases, field_payload=raw)

    assert report["status"] == "failed"
    assert any("run_id_mismatch" in error["id"] for error in report["validation_errors"])


def test_raw_field_report_prompt_hash_mismatch_fails_intake() -> None:
    cases = [case("P01", "advisory")]
    raw = field_report(cases)
    raw["cases"][0]["prompt"] = "Different prompt"
    report = build_report(cases=cases, field_payload=raw)

    assert report["status"] == "failed"
    assert any("prompt_sha256_mismatch" in error["id"] for error in report["validation_errors"])


def test_raw_field_report_text_hash_mismatch_fails_intake() -> None:
    cases = [case("P01", "advisory")]
    raw = field_report(cases)
    raw["cases"][0]["text_sha256"] = "different"
    report = build_report(cases=cases, field_payload=raw)

    assert report["status"] == "failed"
    assert any("text_sha256_mismatch" in error["id"] for error in report["validation_errors"])


def test_field_report_file_hash_mismatch_fails_intake(tmp_path: Path) -> None:
    cases = [case("P01", "advisory")]
    raw = field_report(cases)
    raw_path = tmp_path / "field.json"
    raw_path.write_text(json.dumps(raw), encoding="utf-8")
    source = phase157_report(cases)
    source["field_report_sha256"] = "0" * 64

    report = build_report(
        cases=cases,
        phase157_payload=source,
        field_payload=raw,
        field_report_path=raw_path,
    )

    assert report["status"] == "failed"
    assert any(error["id"] == "field_report.sha256_mismatch" for error in report["validation_errors"])


def test_policy_declared_phase157_input_path_must_match_classified_report() -> None:
    policy_payload = copy.deepcopy(policy())
    policy_payload["inputs"]["phase157_report"] = "runtime-state/other-report.json"

    report = build_report(policy_payload=policy_payload)

    assert report["status"] == "failed"
    assert any("phase157_report_mismatch" in error["id"] for error in report["validation_errors"])


def test_hidden_summary_edit_is_rejected_by_validation() -> None:
    report = build_report()
    edited = copy.deepcopy(report)
    edited["summary"]["phase159_eligible_count"] = 99

    assert validate_report(edited) == ["report must match rebuilt transcript quality feedback intake report"]
