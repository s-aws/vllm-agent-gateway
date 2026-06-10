from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.prompt_tightening_recommendations import (
    build_prompt_tightening_report,
    read_json_object,
    validate_prompt_tightening_policy,
    validate_prompt_tightening_report,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "prompt_tightening_recommendation_policy.json"
CORPUS_PATH = REPO_ROOT / "runtime" / "baseline_corpus.json"
FRESH_DRIFT_PATH = REPO_ROOT / "runtime-state" / "fresh-local-model-drift" / "phase127" / "phase127-fresh-local-model-drift-report.json"


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def corpus() -> dict[str, Any]:
    return read_json_object(CORPUS_PATH)


def drift_report() -> dict[str, Any]:
    return read_json_object(FRESH_DRIFT_PATH)


def project_report() -> dict[str, Any]:
    return build_prompt_tightening_report(
        config_root=REPO_ROOT,
        policy=policy(),
        baseline_corpus=corpus(),
        fresh_drift_report=drift_report(),
        policy_path=POLICY_PATH,
        baseline_corpus_path=CORPUS_PATH,
        fresh_drift_report_path=FRESH_DRIFT_PATH,
    )


def test_project_prompt_tightening_policy_passes() -> None:
    assert validate_prompt_tightening_policy(policy()) == []


def test_project_prompt_tightening_report_passes() -> None:
    report = project_report()
    errors = validate_prompt_tightening_report(
        report,
        policy=policy(),
        baseline_corpus=corpus(),
        config_root=REPO_ROOT,
        require_artifacts=True,
    )
    assert errors == []
    assert report["summary"]["candidate_count"] == 1
    assert report["candidates"][0]["case_id"] == "DD117-009"
    assert report["candidates"][0]["trigger_reasons"] == ["low_confidence_pass"]
    assert report["candidates"][0]["decision"]["status"] == "pending_review"


def test_high_confidence_passes_do_not_become_candidates() -> None:
    report = project_report()
    candidate_ids = {candidate["candidate_id"] for candidate in report["candidates"]}
    assert "PTR-phase116_code_quality-CQ116-001" not in candidate_ids


def test_policy_rejects_broad_low_confidence_floor() -> None:
    broken = policy()
    broken["low_confidence_maximum_route_score"] = 84
    errors = validate_prompt_tightening_policy(broken)
    assert any("low_confidence_maximum_route_score" in error for error in errors)


def test_report_rejects_baseline_suggestion_without_trigger() -> None:
    report = project_report()
    candidate = copy.deepcopy(report["candidates"][0])
    candidate["candidate_id"] = "PTR-phase116_code_quality-CQ116-001"
    candidate["family_id"] = "phase116_code_quality"
    candidate["priority_backlog_id"] = "P0-BB-001"
    candidate["case_id"] = "CQ116-001"
    candidate["trigger_reasons"] = []
    report["candidates"].append(candidate)
    report["summary"]["candidate_count"] += 1
    report["status"] = "failed"
    errors = validate_prompt_tightening_report(
        report,
        policy=policy(),
        baseline_corpus=corpus(),
        config_root=REPO_ROOT,
        require_artifacts=True,
    )
    assert any("trigger_reasons is required" in error for error in errors)


def test_report_rejects_rewritten_prompt() -> None:
    report = project_report()
    report["candidates"][0]["rewritten_prompt"] = "Use this better prompt"
    report["status"] = "failed"
    errors = validate_prompt_tightening_report(
        report,
        policy=policy(),
        baseline_corpus=corpus(),
        config_root=REPO_ROOT,
        require_artifacts=True,
    )
    assert any("must not include rewritten or applied prompt text" in error for error in errors)


def test_report_rejects_prompt_catalog_mutation_claim() -> None:
    report = project_report()
    report["candidates"][0]["applied_to_prompt_catalog"] = True
    report["summary"]["applied_prompt_catalog_change_count"] = 1
    report["status"] = "failed"
    errors = validate_prompt_tightening_report(
        report,
        policy=policy(),
        baseline_corpus=corpus(),
        config_root=REPO_ROOT,
        require_artifacts=True,
    )
    assert any("applied_to_prompt_catalog must be false" in error for error in errors)


def test_report_rejects_accepted_without_approval_and_rerun() -> None:
    report = project_report()
    report["candidates"][0]["decision"]["status"] = "accepted"
    report["summary"]["decision_status_counts"]["accepted"] = 1
    report["summary"]["decision_status_counts"]["pending_review"] = 0
    report["status"] = "failed"
    errors = validate_prompt_tightening_report(
        report,
        policy=policy(),
        baseline_corpus=corpus(),
        config_root=REPO_ROOT,
        require_artifacts=True,
    )
    assert any("approval with approved_by" in error for error in errors)
    assert any("rerun_proof.status must be passed" in error for error in errors)


def test_report_accepts_accepted_with_approval_and_rerun() -> None:
    report = project_report()
    candidate = report["candidates"][0]
    candidate["decision"]["status"] = "accepted"
    candidate["decision"]["rationale"] = "Clarifies diagnosability output without changing task semantics."
    candidate["approval"] = {
        "approved_by": "founder",
        "approved_at": "2026-06-09T00:00:00Z",
        "approval_artifact": "runtime-state/prompt-tightening-recommendations/phase128/approval.json",
    }
    candidate["rerun_proof"] = {
        "status": "passed",
        "target_case_status": "passed",
        "holdout_status": "passed",
        "routes": ["gateway", "anythingllm"],
    }
    report["summary"] = {
        **report["summary"],
        "decision_status_counts": {
            "accepted": 1,
            "pending_review": 0,
            "rejected": 0,
        },
    }
    errors = validate_prompt_tightening_report(
        report,
        policy=policy(),
        baseline_corpus=corpus(),
        config_root=REPO_ROOT,
        require_artifacts=True,
    )
    assert errors == []


def test_report_rejects_pending_with_rerun_proof() -> None:
    report = project_report()
    report["candidates"][0]["rerun_proof"] = {"status": "passed"}
    report["status"] = "failed"
    errors = validate_prompt_tightening_report(
        report,
        policy=policy(),
        baseline_corpus=corpus(),
        config_root=REPO_ROOT,
        require_artifacts=True,
    )
    assert any("rerun_proof must not exist while pending review" in error for error in errors)


def test_report_rejects_stale_source_hash() -> None:
    report = project_report()
    report["candidates"][0]["source_comparison_sha256"] = "0" * 64
    report["status"] = "failed"
    errors = validate_prompt_tightening_report(
        report,
        policy=policy(),
        baseline_corpus=corpus(),
        config_root=REPO_ROOT,
        require_artifacts=True,
    )
    assert any("source_comparison_sha256 must match baseline corpus" in error for error in errors)


def test_report_rejects_category_mismatch() -> None:
    report = project_report()
    report["candidates"][0]["suggestion_class"] = "magic_prompt"
    report["summary"]["suggestion_class_counts"] = {"magic_prompt": 1}
    report["status"] = "failed"
    errors = validate_prompt_tightening_report(
        report,
        policy=policy(),
        baseline_corpus=corpus(),
        config_root=REPO_ROOT,
        require_artifacts=True,
    )
    assert any("suggestion_class must be governed" in error for error in errors)


def test_report_rejects_low_confidence_reason_when_score_is_not_low() -> None:
    report = project_report()
    report["candidates"][0]["minimum_route_score"] = 90
    report["candidates"][0]["route_scores"] = {"anythingllm": 90, "gateway": 90}
    report["status"] = "failed"
    errors = validate_prompt_tightening_report(
        report,
        policy=policy(),
        baseline_corpus=corpus(),
        config_root=REPO_ROOT,
        require_artifacts=True,
    )
    assert any("low_confidence_pass requires a score at or below" in error for error in errors)
