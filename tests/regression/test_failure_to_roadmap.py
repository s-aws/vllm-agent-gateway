from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.failure_to_roadmap import (
    DEFAULT_POLICY_PATH,
    FailureToRoadmapConfig,
    build_failure_to_roadmap_report,
    read_json_object,
    run_failure_to_roadmap,
    validate_failure_to_roadmap_report,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH
PHASE169_POLICY_PATH = REPO_ROOT / "runtime" / "failure_to_roadmap_phase169_policy.json"


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def phase169_policy() -> dict[str, Any]:
    return read_json_object(PHASE169_POLICY_PATH)


def passed_source(kind: str = "external_tester_dry_run_report") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": kind,
        "status": "passed",
        "summary": {"error_count": 0},
        "errors": [],
    }


def failed_source(message: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "external_tester_dry_run_report",
        "status": "failed",
        "summary": {"error_count": 1},
        "errors": [message],
    }


def source_reports(*, failed: dict[str, Any] | None = None) -> dict[str, tuple[Path | None, dict[str, Any]]]:
    return {
        "phase147_external_tester_dry_run": (
            REPO_ROOT / "runtime-state" / "external-tester-dry-run" / "phase147" / "phase147-external-tester-dry-run.json",
            failed or passed_source(),
        ),
        "phase146_release_notes": (
            REPO_ROOT / "runtime-state" / "release-notes" / "phase146" / "phase146-release-notes-report.json",
            passed_source("release_notes_validation_report"),
        ),
        "phase145_founder_feedback_triage_dashboard": (
            REPO_ROOT
            / "runtime-state"
            / "founder-feedback-triage-dashboard"
            / "phase145"
            / "phase145-founder-feedback-triage-dashboard.json",
            passed_source("founder_feedback_triage_dashboard"),
        ),
    }


def test_failure_to_roadmap_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase169_failure_to_roadmap_policy_passes() -> None:
    value = phase169_policy()

    assert validate_policy(value) == []
    assert value["phase"] == 169
    assert value["priority_backlog_id"] == "P0-BB-033"
    assert any(
        "prompt_advisory_product_gap_escalations" in source.get("finding_extractors", [])
        for source in value["source_reports"]
    )


def test_failure_to_roadmap_current_artifacts_pass_with_no_proposals() -> None:
    report = run_failure_to_roadmap(
        config=FailureToRoadmapConfig(
            config_root=REPO_ROOT,
            output_path=REPO_ROOT / "runtime-state" / "failure-to-roadmap" / "phase148" / "test-current-report.json",
            require_artifacts=True,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["finding_count"] == 0
    assert report["summary"]["proposal_count"] == 0
    assert report["summary"]["release_blocker_count"] == 0


def test_phase169_failure_to_roadmap_current_artifacts_generate_product_gap_proposals() -> None:
    report = run_failure_to_roadmap(
        config=FailureToRoadmapConfig(
            config_root=REPO_ROOT,
            policy_path=Path("runtime/failure_to_roadmap_phase169_policy.json"),
            output_path=REPO_ROOT / "runtime-state" / "failure-to-roadmap" / "phase169" / "test-current-report.json",
            require_artifacts=True,
        )
    )

    assert report["status"] == "passed"
    assert report["phase"] == 169
    assert report["priority_backlog_id"] == "P0-BB-033"
    assert report["summary"]["finding_count"] == 6
    assert report["summary"]["proposal_count"] == 6
    assert report["summary"]["unapproved_proposal_count"] == 6
    assert {finding["source_case_id"] for finding in report["findings"]} == {"P08", "P21", "P29", "P30", "P33", "P34"}
    assert all(proposal["approval_status"] == "unapproved" for proposal in report["proposals"])
    assert all(proposal["implementation_status"] == "not_started" for proposal in report["proposals"])


def test_phase169_product_gap_extractor_generates_unapproved_proposals() -> None:
    source_path = REPO_ROOT / "runtime-state" / "prompt-advisory-closure" / "phase165" / "synthetic.json"
    source_report = {
        "schema_version": 1,
        "kind": "prompt_advisory_closure_report",
        "status": "passed",
        "summary": {"product_gap_escalation_count": 2},
        "closure_records": [
            {
                "case_id": "P08",
                "decision": "product_gap_escalation",
                "phase158_finding_id": "phase158-P08-prompt-risk",
                "risk": "Handler prompts can stop at a UI sender unless the handler branch is named.",
                "rationale": "Refined prompt candidate produced a blocker-classified live result.",
                "refined_prompt": "Follow the handler branch through the snapshot function.",
                "refined_classification": "blocker",
                "refined_score": 64,
                "refined_run_id": "workflow-router-synthetic",
                "route_surface": "anythingllm_via_workflow_router_gateway",
                "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
            },
            {
                "case_id": "P21",
                "decision": "documented_guidance",
                "risk": "Closed by prompt guidance.",
            },
            {
                "case_id": "P30",
                "decision": "product_gap_escalation",
                "phase158_finding_id": "phase158-P30-prompt-risk",
                "risk": "Semantic answer missed required source refs.",
                "rationale": "Refined prompt did not recover enough evidence.",
                "refined_prompt": "Return source refs and tests.",
                "refined_classification": "blocker",
                "refined_score": 62,
            },
        ],
    }
    reports = {
        "phase165_prompt_advisory_closure": (source_path, source_report),
    }
    value = phase169_policy()
    value["source_reports"] = [
        source for source in value["source_reports"] if source["id"] == "phase165_prompt_advisory_closure"
    ]

    report = build_failure_to_roadmap_report(policy=value, source_reports=reports, policy_path=PHASE169_POLICY_PATH)

    assert report["status"] == "passed"
    assert report["summary"]["finding_count"] == 2
    assert report["summary"]["proposal_count"] == 2
    assert [proposal["proposal_id"] for proposal in report["proposals"]] == [
        "FTR-P169-001-p08",
        "FTR-P169-002-p30",
    ]
    assert all(proposal["approval_status"] == "unapproved" for proposal in report["proposals"])


def test_failure_to_roadmap_generates_unapproved_blocker_proposal() -> None:
    failed = failed_source("AnythingLLM preflight failed: workspace missing")

    report = build_failure_to_roadmap_report(
        policy=policy(),
        source_reports=source_reports(failed=failed),
        policy_path=POLICY_PATH,
    )

    assert report["status"] == "passed"
    assert report["summary"]["finding_count"] == 1
    assert report["summary"]["proposal_count"] == 1
    assert report["summary"]["release_blocker_count"] == 1
    proposal = report["proposals"][0]
    assert proposal["approval_status"] == "unapproved"
    assert proposal["implementation_status"] == "not_started"
    assert proposal["category"] == "anythingllm_config_error"
    assert proposal["recommended_roadmap_position"] == "before continuing approved release phases"


def test_failure_to_roadmap_model_quality_finding_is_not_auto_approved() -> None:
    failed = failed_source("model_quality: malformed response missing required schema")

    report = build_failure_to_roadmap_report(
        policy=policy(),
        source_reports=source_reports(failed=failed),
        policy_path=POLICY_PATH,
    )

    proposal = report["proposals"][0]
    assert proposal["approval_status"] == "unapproved"
    assert proposal["category"] == "model_quality"
    assert proposal["release_blocker"] is False
    assert proposal["recommended_roadmap_position"] == "after Phase 156 proposal review"


def test_failure_to_roadmap_rejects_missing_required_source_report() -> None:
    reports = source_reports()
    reports["phase147_external_tester_dry_run"] = (None, {})

    report = build_failure_to_roadmap_report(
        policy=policy(),
        source_reports=reports,
        policy_path=POLICY_PATH,
    )

    assert report["status"] == "failed"
    assert any("missing required source reports" in error for error in report["errors"])


def test_failure_to_roadmap_rejects_policy_that_allows_roadmap_mutation() -> None:
    bad_policy = copy.deepcopy(policy())
    bad_policy["proposal_policy"]["roadmap_mutation_allowed"] = True

    report = build_failure_to_roadmap_report(
        policy=bad_policy,
        source_reports=source_reports(),
        policy_path=POLICY_PATH,
    )

    assert report["status"] == "failed"
    assert "proposal_policy.roadmap_mutation_allowed must be false" in report["errors"]


def test_failure_to_roadmap_report_rejects_hidden_summary_edit() -> None:
    report = build_failure_to_roadmap_report(
        policy=policy(),
        source_reports=source_reports(),
        policy_path=POLICY_PATH,
    )
    report["summary"]["proposal_count"] = 99

    errors = validate_failure_to_roadmap_report(
        report,
        policy=policy(),
        source_reports=source_reports(),
        policy_path=POLICY_PATH,
    )

    assert "report.summary must match rebuilt failure-to-roadmap report" in errors
