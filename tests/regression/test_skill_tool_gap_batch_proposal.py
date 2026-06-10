from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.skill_tool_gap_batch_proposal import (
    DEFAULT_POLICY_PATH,
    build_skill_tool_gap_batch_proposal_report,
    read_json_object,
    validate_policy,
    validate_skill_tool_gap_batch_proposal_report,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def finding(
    finding_id: str,
    *,
    category: str = "prompt_issue",
    owner_path: str = "prompt_catalog_review",
    phase159_eligible: bool = False,
    source: str = "phase157_case",
) -> dict[str, Any]:
    return {
        "finding_id": finding_id,
        "source": source,
        "case_id": "P01",
        "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
        "selected_workflow": "code_investigation.plan",
        "run_id": "workflow-router-test",
        "quality_classification": "advisory",
        "category": category,
        "severity": "low",
        "decision": "accepted_for_phase159" if phase159_eligible else "accepted_for_monitoring",
        "owner_path": owner_path,
        "required_rerun_gate": "phase159_target_plus_holdout" if phase159_eligible else "phase157_founder_field_round1",
        "phase159_eligible": phase159_eligible,
        "message": "Synthetic finding for Phase 161 tests.",
        "initial_difference": "No difference.",
    }


def phase157_report(*, advisory_count: int = 1, blocker_count: int = 0, case_count: int | None = None) -> dict[str, Any]:
    total_cases = case_count if case_count is not None else advisory_count + blocker_count
    return {
        "schema_version": 1,
        "kind": "founder_field_round1_report",
        "phase": 157,
        "priority_backlog_id": "P0-BB-021",
        "status": "passed",
        "summary": {
            "case_count": total_cases,
            "advisory_case_count": advisory_count,
            "blocker_case_count": blocker_count,
            "pass_case_count": 0,
            "target_roots": [
                "/mnt/c/coinbase_testing_repo_frozen_tmp",
                "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
            ],
        },
    }


def phase158_report(findings: list[dict[str, Any]], *, founder_note_count: int = 0) -> dict[str, Any]:
    eligible_count = sum(1 for item in findings if item.get("phase159_eligible") is True)
    category_counts: dict[str, int] = {}
    owner_counts: dict[str, int] = {}
    for item in findings:
        category = str(item.get("category"))
        category_counts[category] = category_counts.get(category, 0) + 1
        owner = str(item.get("owner_path"))
        owner_counts[owner] = owner_counts.get(owner, 0) + 1
    return {
        "schema_version": 1,
        "kind": "transcript_quality_feedback_intake_report",
        "phase": 158,
        "priority_backlog_id": "P0-BB-022",
        "status": "passed",
        "accepted_findings": findings,
        "rejected_findings": [],
        "validation_errors": [],
        "phase159_required": eligible_count > 0,
        "summary": {
            "source_case_count": 1,
            "accepted_finding_count": len(findings),
            "rejected_finding_count": 0,
            "phase157_advisory_finding_count": len(findings) - founder_note_count,
            "phase157_blocker_finding_count": 0,
            "founder_note_count": founder_note_count,
            "phase159_eligible_count": eligible_count,
            "phase159_required": eligible_count > 0,
            "category_counts": category_counts,
            "owner_counts": owner_counts,
            "validation_error_count": 0,
        },
    }


def phase159_report(*, eligible_count: int = 0, repair_mode: str = "no_repair_required", status: str = "passed") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "priority0_repair_loop_report",
        "phase": 159,
        "priority_backlog_id": "P0-BB-023",
        "status": status,
        "repair_mode": repair_mode,
        "repair_items": [],
        "monitoring_items": [],
        "validation_errors": [],
        "summary": {
            "phase158_finding_count": 1,
            "monitoring_only_count": 1 - eligible_count,
            "phase159_eligible_count": eligible_count,
            "closed_repair_count": 1 if repair_mode == "repairs_closed" else 0,
            "open_repair_count": 0,
            "missing_repair_record_count": 0,
            "validation_error_count": 0,
            "repair_mode": repair_mode,
        },
    }


def phase160_report(*, readiness: str = "ready_for_founder_testing", decision: str = "release_for_founder_testing") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "stable_release_refresh_report",
        "phase": 160,
        "priority_backlog_id": "P0-BB-024",
        "status": "passed",
        "readiness": readiness,
        "decision": decision,
        "source_refs": {},
        "refresh_results": [],
        "validation_errors": [],
        "summary": {
            "refresh_command_count": 5,
            "source_report_count": 8,
            "validation_error_count": 0,
            "readiness": readiness,
            "decision": decision,
            "phase159_repair_mode": "no_repair_required",
            "model_ids": ["Qwen3-Coder-30B-A3B-Instruct"],
        },
    }


def sources(
    *,
    phase157: dict[str, Any] | None = None,
    phase158: dict[str, Any] | None = None,
    phase159: dict[str, Any] | None = None,
    phase160: dict[str, Any] | None = None,
) -> dict[str, tuple[Path | None, dict[str, Any]]]:
    default_findings = [finding("phase158-P01-prompt-risk")]
    return {
        "phase157_report": (None, phase157 or phase157_report()),
        "phase158_report": (None, phase158 or phase158_report(default_findings)),
        "phase159_report": (None, phase159 or phase159_report()),
        "phase160_report": (None, phase160 or phase160_report()),
    }


def build_report(
    *,
    policy_payload: dict[str, Any] | None = None,
    source_payloads: dict[str, tuple[Path | None, dict[str, Any]]] | None = None,
    load_errors: list[str] | None = None,
) -> dict[str, Any]:
    return build_skill_tool_gap_batch_proposal_report(
        policy=policy_payload or policy(),
        sources=source_payloads or sources(),
        load_errors=load_errors or [],
        policy_path=POLICY_PATH,
    )


def validate_report(
    report: dict[str, Any],
    *,
    policy_payload: dict[str, Any] | None = None,
    source_payloads: dict[str, tuple[Path | None, dict[str, Any]]] | None = None,
    load_errors: list[str] | None = None,
) -> list[str]:
    return validate_skill_tool_gap_batch_proposal_report(
        report,
        policy=policy_payload or policy(),
        sources=source_payloads or sources(),
        load_errors=load_errors or [],
        policy_path=POLICY_PATH,
    )


def test_project_skill_tool_gap_batch_proposal_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_current_prompt_issue_only_chain_produces_no_new_batch_decision() -> None:
    report = build_report()

    assert validate_report(report) == []
    assert report["status"] == "passed"
    assert report["decision"] == "no_new_batch_justified"
    assert report["implementation_authorized"] is False
    assert report["summary"]["gap_candidate_count"] == 0
    assert report["non_batch_findings"][0]["classified_as"] == "not_skill_tool_gap_batch"


def test_missing_skill_tool_finding_generates_bounded_candidate() -> None:
    gap = finding(
        "phase158-founder-note-skill-gap",
        category="missing_skill_tool",
        owner_path="skill_tool_gap_review",
        phase159_eligible=True,
        source="founder_note",
    )
    source_payloads = sources(
        phase157=phase157_report(advisory_count=0, case_count=1),
        phase158=phase158_report([gap], founder_note_count=1),
        phase159=phase159_report(eligible_count=1, repair_mode="repairs_closed"),
        phase160=phase160_report(),
    )
    report = build_report(source_payloads=source_payloads)

    assert validate_report(report, source_payloads=source_payloads) == []
    assert report["status"] == "passed"
    assert report["decision"] == "propose_batch_for_founder_approval"
    assert report["implementation_authorized"] is False
    assert report["summary"]["missing_skill_tool_finding_count"] == 1
    candidate = report["gap_candidates"][0]
    assert candidate["source_finding_id"] == "phase158-founder-note-skill-gap"
    assert candidate["implementation_status"] == "not_started"
    assert candidate["auto_register"] is False
    assert "gateway_anythingllm_fixture_mutation" in candidate["validation_tiers"]
    assert "anythingllm_chat_quality_required" in candidate["safety_boundaries"]


def test_missing_skill_tool_candidate_is_stale_proof_if_removed() -> None:
    gap = finding(
        "phase158-founder-note-skill-gap",
        category="missing_skill_tool",
        owner_path="skill_tool_gap_review",
        phase159_eligible=True,
        source="founder_note",
    )
    source_payloads = sources(
        phase157=phase157_report(advisory_count=0, case_count=1),
        phase158=phase158_report([gap], founder_note_count=1),
        phase159=phase159_report(eligible_count=1, repair_mode="repairs_closed"),
    )
    report = build_report(source_payloads=source_payloads)
    edited = copy.deepcopy(report)
    edited["gap_candidates"] = []
    edited["summary"]["gap_candidate_count"] = 0

    assert validate_report(edited, source_payloads=source_payloads) == [
        "report must match rebuilt skill/tool gap batch proposal report"
    ]


def test_prompt_issue_cannot_be_reclassified_as_skill_tool_batch() -> None:
    report = build_report()
    edited = copy.deepcopy(report)
    edited["gap_candidates"] = [
        {
            "candidate_id": "P161-STG-999",
            "source_finding_id": "phase158-P01-prompt-risk",
            "capability_type": "skill_and_tool",
            "capability_id": "phase161.prompt_issue.bad_gap",
            "proposal_summary": "Incorrectly convert a prompt issue into new skill work.",
            "eval_gate": "phase161_target_holdout_gateway_anythingllm",
            "approval_boundary": "founder_approval_required",
            "implementation_status": "not_started",
        }
    ]
    edited["decision"] = "propose_batch_for_founder_approval"
    edited["summary"]["gap_candidate_count"] = 1

    assert validate_report(edited) == ["report must match rebuilt skill/tool gap batch proposal report"]


def test_phase158_prompt_issue_with_skill_tool_owner_fails_closed() -> None:
    bad_finding = finding(
        "phase158-P01-owner-mismatch",
        category="prompt_issue",
        owner_path="skill_tool_gap_review",
        phase159_eligible=False,
    )
    source_payloads = sources(phase158=phase158_report([bad_finding]))
    report = build_report(source_payloads=source_payloads)

    assert report["status"] == "failed"
    assert report["decision"] == "blocked"
    assert report["summary"]["gap_candidate_count"] == 0
    assert any("owner_category_mismatch" in error["id"] for error in report["validation_errors"])


def test_phase158_unknown_category_fails_closed_instead_of_non_batch() -> None:
    bad_finding = finding(
        "phase158-P01-unknown-category",
        category="missing_skill_tol",
        owner_path="prompt_catalog_review",
    )
    source_payloads = sources(phase158=phase158_report([bad_finding]))
    report = build_report(source_payloads=source_payloads)

    assert report["status"] == "failed"
    assert report["decision"] == "blocked"
    assert any(error["id"].endswith(".category") for error in report["validation_errors"])


def test_phase158_summary_category_count_mismatch_fails_closed() -> None:
    phase158 = phase158_report([finding("phase158-P01-prompt-risk")])
    phase158["summary"]["category_counts"] = {"prompt_issue": 0}
    source_payloads = sources(phase158=phase158)
    report = build_report(source_payloads=source_payloads)

    assert report["status"] == "failed"
    assert any(error["id"] == "phase158.summary.category_counts" for error in report["validation_errors"])


def test_phase158_summary_owner_count_mismatch_fails_closed() -> None:
    phase158 = phase158_report([finding("phase158-P01-prompt-risk")])
    phase158["summary"]["owner_counts"] = {"prompt_catalog_review": 0}
    source_payloads = sources(phase158=phase158)
    report = build_report(source_payloads=source_payloads)

    assert report["status"] == "failed"
    assert any(error["id"] == "phase158.summary.owner_counts" for error in report["validation_errors"])


def test_phase158_summary_accepted_count_mismatch_fails_closed() -> None:
    phase158 = phase158_report([finding("phase158-P01-prompt-risk")])
    phase158["summary"]["accepted_finding_count"] = 0
    source_payloads = sources(phase158=phase158)
    report = build_report(source_payloads=source_payloads)

    assert report["status"] == "failed"
    assert any(error["id"] == "phase158.summary.accepted_finding_count" for error in report["validation_errors"])


def test_failed_phase160_blocks_phase161_decision() -> None:
    source_payloads = sources(phase160=phase160_report(readiness="blocked", decision="blocked"))
    report = build_report(source_payloads=source_payloads)

    assert report["status"] == "failed"
    assert report["decision"] == "blocked"
    assert any(error["id"] == "phase160.readiness" for error in report["validation_errors"])
    assert any(error["id"] == "phase160.decision" for error in report["validation_errors"])


def test_open_phase159_repair_blocks_phase161_decision() -> None:
    phase159 = phase159_report()
    phase159["summary"]["open_repair_count"] = 1
    source_payloads = sources(phase159=phase159)
    report = build_report(source_payloads=source_payloads)

    assert report["status"] == "failed"
    assert report["decision"] == "blocked"
    assert any(error["id"] == "phase159.open_repair_count" for error in report["validation_errors"])


def test_phase158_phase159_eligible_mismatch_blocks_phase161() -> None:
    gap = finding(
        "phase158-founder-note-skill-gap",
        category="missing_skill_tool",
        owner_path="skill_tool_gap_review",
        phase159_eligible=True,
        source="founder_note",
    )
    source_payloads = sources(
        phase157=phase157_report(advisory_count=0, case_count=1),
        phase158=phase158_report([gap], founder_note_count=1),
        phase159=phase159_report(eligible_count=0),
    )
    report = build_report(source_payloads=source_payloads)

    assert report["status"] == "failed"
    assert any("eligible_count_mismatch" in error["id"] for error in report["validation_errors"])


def test_policy_declared_source_paths_are_required() -> None:
    policy_payload = copy.deepcopy(policy())
    policy_payload["inputs"]["phase160_report"] = ""
    report = build_report(policy_payload=policy_payload)

    assert report["status"] == "failed"
    assert any("policy.inputs.phase160_report" in error["message"] or "phase160_report" in error["id"] for error in report["validation_errors"])


def test_hidden_summary_edit_is_rejected_by_validation() -> None:
    report = build_report()
    edited = copy.deepcopy(report)
    edited["summary"]["missing_skill_tool_finding_count"] = 99

    assert validate_report(edited) == ["report must match rebuilt skill/tool gap batch proposal report"]
