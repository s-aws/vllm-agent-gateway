from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.founder_feedback_intake_repair import (
    DEFAULT_POLICY_PATH,
    FounderFeedbackIntakeRepairConfig,
    build_founder_feedback_intake_repair_report,
    read_json_object,
    run_founder_feedback_intake_repair,
    validate_founder_feedback_intake_repair_report,
    validate_policy,
    write_json,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH
GIT_ROOT = "/mnt/c/coinbase_testing_repo_frozen_tmp.github"
NON_GIT_ROOT = "/mnt/c/coinbase_testing_repo_frozen_tmp"
ADVISORY_CASE_IDS = ["P01", "P08", "P17", "P21"]


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def write_response(tmp_path: Path, case_id: str) -> dict[str, Any]:
    path = tmp_path / "responses" / f"{case_id}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"selected_workflow: code_investigation.plan\nrun_id: workflow-router-{case_id.lower()}\n", encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "response_artifact_path": str(path),
        "response_artifact_sha256": digest,
    }


def phase197_case(tmp_path: Path, case_id: str, *, classification: str = "pass") -> dict[str, Any]:
    target_root = NON_GIT_ROOT if case_id == "P13" else GIT_ROOT
    risks = {
        "P01": "Ambiguous 'start' wording can be interpreted as a related usage point.",
        "P08": "Handler prompts can stop at a UI sender unless the handler branch is named.",
        "P17": "Validation prompts can omit shell surface, which matters because live validation should prefer Bash.",
        "P21": "Change-surface prompts should name both touch and do-not-touch boundaries.",
    }
    return {
        "case_id": case_id,
        "target_root": target_root,
        "prompt": f"In {target_root}, run {case_id}.",
        "expected_workflow": "code_investigation.plan",
        "status": "passed" if classification != "blocker" else "failed",
        "quality_classification": classification,
        "output_contract_status": "passed" if classification != "blocker" else "failed",
        "semantic_quality_status": "passed" if classification != "blocker" else "failed",
        "route_surface": "anythingllm_via_workflow_router_gateway",
        "run_id": f"workflow-router-{case_id.lower()}",
        "initial_difference": "No marker-level or semantic difference from the baseline target.",
        "suggested_prompt_if_missed": "",
        "prompt_risk": risks.get(case_id, ""),
        **write_response(tmp_path, case_id),
    }


def phase197_report(tmp_path: Path, *, blocker_case_id: str | None = None) -> tuple[Path, dict[str, Any]]:
    field_path = tmp_path / "phase197-field.json"
    field = {"kind": "founder_field_prompt_evaluation", "status": "passed", "phase": 197}
    write_json(field_path, field)
    case_ids = ["P01", "P02", "P03", "P22", "P04", "P05", "P06", "P08", "P09", "P10", "P13", "P17", "P19", "P21"]
    cases = []
    for case_id in case_ids:
        classification = "advisory" if case_id in ADVISORY_CASE_IDS else "pass"
        if case_id == blocker_case_id:
            classification = "blocker"
        cases.append(phase197_case(tmp_path, case_id, classification=classification))
    report_path = tmp_path / "phase197-report.json"
    report = {
        "schema_version": 1,
        "kind": "founder_trial_execution_round_report",
        "phase": 197,
        "priority_backlog_id": "P0-BB-061",
        "status": "passed",
        "quality_status": "failed" if blocker_case_id else "advisory",
        "source_refs": {
            "field_report": {
                "path": str(field_path),
                "sha256": hashlib.sha256(field_path.read_bytes()).hexdigest(),
                "kind": "founder_field_prompt_evaluation",
                "phase": 197,
                "status": "passed",
            }
        },
        "case_results": cases,
        "validation_errors": [],
        "summary": {"validation_error_count": 0},
    }
    write_json(report_path, report)
    return report_path, report


def build_report(
    tmp_path: Path,
    *,
    phase197: dict[str, Any] | None = None,
    phase197_path: Path | None = None,
    founder_notes: dict[str, Any] | None = None,
    founder_notes_path: Path | None = None,
) -> dict[str, Any]:
    source_path, source_report = phase197_report(tmp_path)
    return build_founder_feedback_intake_repair_report(
        config_root=REPO_ROOT,
        policy=policy(),
        phase197_path=phase197_path or source_path,
        phase197_report=phase197 or source_report,
        founder_notes_path=founder_notes_path,
        founder_notes=founder_notes or {},
        source_load_errors=[],
        policy_path=POLICY_PATH,
    )


def error_ids(report: dict[str, Any]) -> set[str]:
    return {str(item.get("id")) for item in report["validation_errors"]}


def test_founder_feedback_intake_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_founder_feedback_intake_creates_one_decision_per_phase197_advisory(tmp_path: Path) -> None:
    report = build_report(tmp_path)

    assert report["status"] == "passed"
    assert report["summary"]["source_advisory_count"] == 4
    assert report["summary"]["source_blocker_count"] == 0
    assert report["summary"]["accepted_proposal_count"] == 4
    assert report["summary"]["phase199_blocked"] is False
    assert [item["case_id"] for item in report["decision_records"]] == ADVISORY_CASE_IDS
    assert all(item["source_proof"]["response_artifact_hash_status"] == "passed" for item in report["decision_records"])


def test_founder_feedback_intake_blocks_phase199_for_source_blocker(tmp_path: Path) -> None:
    path, source = phase197_report(tmp_path, blocker_case_id="P02")

    report = build_report(tmp_path, phase197=source, phase197_path=path)

    assert report["status"] == "passed"
    assert report["summary"]["source_blocker_count"] == 1
    assert report["summary"]["phase199_blocked"] is True
    blocker = [item for item in report["decision_records"] if item["case_id"] == "P02"][0]
    assert blocker["decision"] == "accepted_release_blocker"
    assert blocker["closure_status"] == "open"


def test_founder_feedback_intake_rejects_response_artifact_hash_mismatch(tmp_path: Path) -> None:
    path, source = phase197_report(tmp_path)
    source["case_results"][0]["response_artifact_sha256"] = "bad"

    report = build_report(tmp_path, phase197=source, phase197_path=path)

    assert report["status"] == "failed"
    assert "decision_records[0].source_proof.response_artifact_hash" in error_ids(report)
    assert report["summary"]["phase199_blocked"] is True


def test_founder_feedback_intake_accepts_linked_founder_note(tmp_path: Path) -> None:
    path, source = phase197_report(tmp_path)
    case = copy.deepcopy(source["case_results"][1])
    notes = {
        "kind": "founder_feedback_notes",
        "phase": 198,
        "notes": [
            {
                "case_id": case["case_id"],
                "prompt": case["prompt"],
                "target_run_id": case["run_id"],
                "classification": "advisory",
                "severity": "medium",
                "actual_response_excerpt": "It missed one detail.",
                "expected_behavior": "Include the missing detail.",
                "fixture_root": case["target_root"],
                "created_at": "2026-06-11T00:00:00Z",
            }
        ],
    }

    report = build_report(tmp_path, phase197=source, phase197_path=path, founder_notes=notes)

    assert report["status"] == "passed"
    assert report["summary"]["founder_note_count"] == 1
    assert report["summary"]["accepted_proposal_count"] == 5
    assert report["summary"]["rejected_record_count"] == 0
    assert any(item["source_type"] == "founder_note" for item in report["decision_records"])


def test_founder_feedback_intake_rejects_unlinked_founder_note_without_failing_gate(tmp_path: Path) -> None:
    path, source = phase197_report(tmp_path)
    notes = {
        "kind": "founder_feedback_notes",
        "phase": 198,
        "notes": [
            {
                "case_id": "P01",
                "prompt": "wrong prompt",
                "target_run_id": "workflow-router-wrong",
                "classification": "advisory",
                "severity": "medium",
                "actual_response_excerpt": "It missed one detail.",
                "expected_behavior": "Include the missing detail.",
                "fixture_root": GIT_ROOT,
                "created_at": "2026-06-11T00:00:00Z",
            }
        ],
    }

    report = build_report(tmp_path, phase197=source, phase197_path=path, founder_notes=notes)

    assert report["status"] == "passed"
    assert report["summary"]["rejected_record_count"] == 1
    assert report["rejected_records"][0]["decision"] == "rejected_no_action"
    assert report["rejected_records"][0]["rejection_reasons"]


def test_founder_feedback_intake_rejects_hidden_report_edit(tmp_path: Path) -> None:
    report = build_report(tmp_path)
    report["summary"]["accepted_proposal_count"] = 999
    path, source = phase197_report(tmp_path)

    errors = validate_founder_feedback_intake_repair_report(
        report,
        config_root=REPO_ROOT,
        policy=policy(),
        phase197_path=path,
        phase197_report=source,
        founder_notes_path=None,
        founder_notes={},
        source_load_errors=[],
        policy_path=POLICY_PATH,
    )

    assert errors == ["report must match rebuilt founder feedback intake repair report"]


def test_founder_feedback_intake_project_report_passes_when_phase197_artifact_exists() -> None:
    phase197_artifact = REPO_ROOT / "runtime-state" / "phase197" / "phase197-founder-trial-execution-round-report.json"
    if not phase197_artifact.is_file():
        return

    report = run_founder_feedback_intake_repair(
        FounderFeedbackIntakeRepairConfig(config_root=REPO_ROOT, policy_path=DEFAULT_POLICY_PATH)
    )

    assert report["status"] == "passed"
    assert report["summary"]["accepted_proposal_count"] >= 4
