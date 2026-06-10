from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.priority0_repair_loop import (
    DEFAULT_POLICY_PATH,
    build_priority0_repair_loop_report,
    read_json_object,
    validate_policy,
    validate_priority0_repair_loop_report,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH
PHASE158_PATH = (
    Path("runtime-state")
    / "transcript-quality-feedback-intake"
    / "phase158"
    / "phase158-transcript-quality-feedback-intake-report.json"
)
REPAIR_RECORDS_PATH = Path("runtime-state") / "priority0-repair-loop" / "phase159" / "repair-records.json"


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def finding(
    finding_id: str,
    *,
    eligible: bool = False,
    category: str = "prompt_issue",
    decision: str | None = None,
) -> dict[str, Any]:
    return {
        "finding_id": finding_id,
        "source": "phase157_case",
        "case_id": "P01",
        "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
        "selected_workflow": "code_investigation.plan",
        "run_id": "workflow-router-test",
        "quality_classification": "advisory" if not eligible else "blocker",
        "category": category,
        "severity": "low" if not eligible else "high",
        "decision": decision or ("accepted_for_phase159" if eligible else "accepted_for_monitoring"),
        "owner_path": "prompt_catalog_review" if not eligible else "controller_or_formatter_repair",
        "required_rerun_gate": "phase159_target_plus_holdout" if eligible else "phase157_founder_field_round1",
        "phase159_eligible": eligible,
        "message": "Synthetic finding for repair-loop tests.",
        "initial_difference": "No difference.",
        "transcript_reference": {
            "phase157_report_path": "runtime-state/founder-field-round1/phase157/report.json",
            "field_report_path": "runtime-state/founder-field-round1/phase157/run.json",
            "response_text_sha256": "a" * 64,
        },
    }


def phase158_report(findings: list[dict[str, Any]] | None = None, *, status: str = "passed") -> dict[str, Any]:
    accepted_findings = findings if findings is not None else [finding("phase158-P01-prompt-risk")]
    eligible_count = sum(1 for item in accepted_findings if item["phase159_eligible"] is True)
    return {
        "schema_version": 1,
        "kind": "transcript_quality_feedback_intake_report",
        "phase": 158,
        "priority_backlog_id": "P0-BB-022",
        "status": status,
        "source_refs": {},
        "accepted_findings": accepted_findings,
        "rejected_findings": [],
        "validation_errors": [],
        "phase159_required": eligible_count > 0,
        "summary": {
            "source_case_count": 1,
            "accepted_finding_count": len(accepted_findings),
            "rejected_finding_count": 0,
            "phase157_advisory_finding_count": len(accepted_findings) - eligible_count,
            "phase157_blocker_finding_count": eligible_count,
            "founder_note_count": 0,
            "phase159_eligible_count": eligible_count,
            "phase159_required": eligible_count > 0,
            "category_counts": {},
            "owner_counts": {},
            "validation_error_count": 0,
        },
    }


def repair_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "kind": "priority0_repair_loop_records",
        "phase": 159,
        "records": records,
    }


def write_proof_files(tmp_path: Path, *, holdout_status: str = "passed") -> tuple[Path, Path]:
    target_path = tmp_path / "target.json"
    holdout_path = tmp_path / "holdout.json"
    target_path.write_text(
        """{"kind":"priority0_repair_target_proof","status":"passed","result_status":"passed"}""",
        encoding="utf-8",
    )
    holdout_path.write_text(
        (
            """{"kind":"priority0_repair_holdout_proof","status":"%s","result_status":"%s"}"""
            % (holdout_status, holdout_status)
        ),
        encoding="utf-8",
    )
    return target_path, holdout_path


def closed_record(finding_id: str, *, target_path: Path | None = None, holdout_path: Path | None = None) -> dict[str, Any]:
    return {
        "finding_id": finding_id,
        "closure_status": "closed_with_target_holdout_proof",
        "required_rerun_gate": "phase159_target_plus_holdout",
        "live_surfaces": ["gateway", "anythingllm"],
        "target_result_status": "passed",
        "holdout_result_status": "passed",
        "mutation_status": "unchanged",
        "target_report_path": str(target_path or "runtime-state/priority0-repair-loop/phase159/target.json"),
        "holdout_report_path": str(holdout_path or "runtime-state/priority0-repair-loop/phase159/holdout.json"),
        "repair_summary": "Closed with target and holdout proof.",
    }


def open_record(finding_id: str) -> dict[str, Any]:
    return {
        "finding_id": finding_id,
        "closure_status": "open_blocked",
        "blocker_reason": "The target repair needs a deterministic tool that is not approved yet.",
        "next_action": "Add a skill or tool gap proposal before implementation work continues.",
    }


def build_report(
    *,
    policy_payload: dict[str, Any] | None = None,
    phase158_payload: dict[str, Any] | None = None,
    repair_payload: dict[str, Any] | None = None,
    phase158_report_path: Path | None = PHASE158_PATH,
    repair_records_path: Path | None = REPAIR_RECORDS_PATH,
) -> dict[str, Any]:
    return build_priority0_repair_loop_report(
        policy=policy_payload or policy(),
        phase158_report=phase158_payload or phase158_report(),
        repair_records=repair_payload,
        policy_path=POLICY_PATH,
        phase158_report_path=phase158_report_path,
        repair_records_path=repair_records_path,
    )


def validate_report(
    report: dict[str, Any],
    *,
    policy_payload: dict[str, Any] | None = None,
    phase158_payload: dict[str, Any] | None = None,
    repair_payload: dict[str, Any] | None = None,
    phase158_report_path: Path | None = PHASE158_PATH,
    repair_records_path: Path | None = REPAIR_RECORDS_PATH,
) -> list[str]:
    return validate_priority0_repair_loop_report(
        report,
        policy=policy_payload or policy(),
        phase158_report=phase158_payload or phase158_report(),
        repair_records=repair_payload,
        policy_path=POLICY_PATH,
        phase158_report_path=phase158_report_path,
        repair_records_path=repair_records_path,
    )


def test_project_priority0_repair_loop_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_no_repair_required_path_passes_for_monitoring_only_findings() -> None:
    report = build_report()

    assert validate_report(report) == []
    assert report["status"] == "passed"
    assert report["repair_mode"] == "no_repair_required"
    assert report["summary"]["phase159_eligible_count"] == 0
    assert report["summary"]["monitoring_only_count"] == 1
    assert report["repair_items"] == []
    assert report["monitoring_items"][0]["closure_status"] == "monitoring_only"


def test_phase159_eligible_finding_requires_repair_record() -> None:
    phase158 = phase158_report([finding("phase158-P01-blocker", eligible=True, category="harness_issue")])
    report = build_report(phase158_payload=phase158)

    assert report["status"] == "failed"
    assert report["summary"]["missing_repair_record_count"] == 1
    assert any("requires a repair closure record" in error["message"] for error in report["validation_errors"])


def test_closed_repair_requires_target_and_holdout_proof(tmp_path: Path) -> None:
    phase158 = phase158_report([finding("phase158-P01-blocker", eligible=True, category="harness_issue")])
    target_path, holdout_path = write_proof_files(tmp_path)
    records = repair_records([closed_record("phase158-P01-blocker", target_path=target_path, holdout_path=holdout_path)])
    report = build_report(phase158_payload=phase158, repair_payload=records)

    assert report["status"] == "passed"
    assert report["repair_mode"] == "repairs_closed"
    assert report["summary"]["closed_repair_count"] == 1
    assert report["repair_items"][0]["target_result_status"] == "passed"
    assert report["repair_items"][0]["holdout_result_status"] == "passed"


def test_closed_repair_missing_holdout_fails(tmp_path: Path) -> None:
    phase158 = phase158_report([finding("phase158-P01-blocker", eligible=True, category="harness_issue")])
    target_path, holdout_path = write_proof_files(tmp_path, holdout_status="failed")
    record = closed_record("phase158-P01-blocker", target_path=target_path, holdout_path=holdout_path)
    record["holdout_result_status"] = "failed"
    records = repair_records([record])
    report = build_report(phase158_payload=phase158, repair_payload=records)

    assert report["status"] == "failed"
    assert any("holdout_result_status must be passed" in error["message"] for error in report["validation_errors"])


def test_closed_repair_nonexistent_proof_files_fail() -> None:
    phase158 = phase158_report([finding("phase158-P01-blocker", eligible=True, category="harness_issue")])
    records = repair_records([closed_record("phase158-P01-blocker")])
    report = build_report(phase158_payload=phase158, repair_payload=records)

    assert report["status"] == "failed"
    assert any("proof report must exist" in error["message"] for error in report["validation_errors"])


def test_open_blocked_record_passes_with_next_action() -> None:
    phase158 = phase158_report([finding("phase158-P01-blocker", eligible=True, category="model_capability")])
    records = repair_records([open_record("phase158-P01-blocker")])
    report = build_report(phase158_payload=phase158, repair_payload=records)

    assert report["status"] == "blocked"
    assert report["repair_mode"] == "blocked_with_next_action"
    assert report["summary"]["open_repair_count"] == 1
    assert report["repair_items"][0]["next_action"]


def test_duplicate_repair_records_fail() -> None:
    phase158 = phase158_report([finding("phase158-P01-blocker", eligible=True, category="harness_issue")])
    records = repair_records([closed_record("phase158-P01-blocker"), closed_record("phase158-P01-blocker")])
    report = build_report(phase158_payload=phase158, repair_payload=records)

    assert report["status"] == "failed"
    assert any("duplicate" in error["id"] for error in report["validation_errors"])


def test_malformed_repair_record_fails_even_without_eligible_findings() -> None:
    records = repair_records(["bad"])  # type: ignore[list-item]
    report = build_report(repair_payload=records)

    assert report["status"] == "failed"
    assert any("malformed" in error["id"] for error in report["validation_errors"])


def test_repair_record_missing_finding_id_fails_even_without_eligible_findings() -> None:
    records = repair_records([{"closure_status": "open_blocked"}])
    report = build_report(repair_payload=records)

    assert report["status"] == "failed"
    assert any("finding_id" in error["id"] for error in report["validation_errors"])


def test_repair_record_for_monitoring_finding_fails() -> None:
    records = repair_records([closed_record("phase158-P01-prompt-risk")])
    report = build_report(repair_payload=records)

    assert report["status"] == "failed"
    assert any("not_eligible" in error["id"] for error in report["validation_errors"])


def test_repair_record_for_unknown_finding_fails() -> None:
    records = repair_records([closed_record("phase158-unknown")])
    report = build_report(repair_payload=records)

    assert report["status"] == "failed"
    assert any("unknown_finding" in error["id"] for error in report["validation_errors"])


def test_failed_phase158_source_fails_repair_loop() -> None:
    report = build_report(phase158_payload=phase158_report(status="failed"))

    assert report["status"] == "failed"
    assert any(error["id"] == "phase158.status" for error in report["validation_errors"])


def test_phase158_summary_mismatch_fails_repair_loop() -> None:
    phase158 = phase158_report()
    phase158["summary"]["phase159_eligible_count"] = 99
    report = build_report(phase158_payload=phase158)

    assert report["status"] == "failed"
    assert any("phase159_eligible_count" in error["id"] for error in report["validation_errors"])


def test_policy_declared_phase158_input_path_must_match_closed_report() -> None:
    policy_payload = copy.deepcopy(policy())
    policy_payload["inputs"]["phase158_report"] = "runtime-state/other-report.json"
    report = build_report(policy_payload=policy_payload)

    assert report["status"] == "failed"
    assert any("phase158_report_mismatch" in error["id"] for error in report["validation_errors"])


def test_hidden_summary_edit_is_rejected_by_validation() -> None:
    report = build_report()
    edited = copy.deepcopy(report)
    edited["summary"]["phase159_eligible_count"] = 99

    assert validate_report(edited) == ["report must match rebuilt Priority 0 repair-loop report"]
