from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.contextless_audit_scorecard import (
    DEFAULT_POLICY_PATH,
    ContextlessAuditScorecardConfig,
    build_contextless_audit_scorecard_report,
    load_recursive_policy,
    load_source_artifacts,
    read_json_object,
    run_contextless_audit_scorecard,
    validate_contextless_audit_scorecard_report,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def loaded_sources() -> dict[str, tuple[Path | None, dict[str, Any] | None]]:
    sources, errors = load_source_artifacts(config_root=REPO_ROOT, policy=policy(), require_artifacts=True)
    assert errors == []
    return sources


def loaded_recursive_policy() -> tuple[Path | None, dict[str, Any] | None]:
    recursive_path, recursive_policy, errors = load_recursive_policy(REPO_ROOT, policy())
    assert errors == []
    return recursive_path, recursive_policy


def clone_sources() -> dict[str, tuple[Path | None, dict[str, Any] | None]]:
    return {
        source_id: (path, copy.deepcopy(payload))
        for source_id, (path, payload) in loaded_sources().items()
    }


def build_report(
    *,
    sources: dict[str, tuple[Path | None, dict[str, Any] | None]] | None = None,
    recursive_policy: dict[str, Any] | None | object = None,
) -> dict[str, Any]:
    recursive_path, project_recursive_policy = loaded_recursive_policy()
    if recursive_policy is None:
        recursive_policy = project_recursive_policy
    return build_contextless_audit_scorecard_report(
        policy=policy(),
        sources=sources or loaded_sources(),
        recursive_policy=recursive_policy if isinstance(recursive_policy, dict) else None,
        policy_path=POLICY_PATH,
        recursive_policy_path=recursive_path,
    )


def blocker_codes(report: dict[str, Any]) -> set[str]:
    return {item["code"] for item in report["scorecard"]["hard_blockers"]}


def test_contextless_audit_scorecard_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_contextless_audit_scorecard_current_artifacts_pass(tmp_path: Path) -> None:
    output_path = tmp_path / "scorecard.json"
    markdown_path = tmp_path / "scorecard.md"

    report = run_contextless_audit_scorecard(
        ContextlessAuditScorecardConfig(
            config_root=REPO_ROOT,
            output_path=output_path,
            markdown_output_path=markdown_path,
            require_artifacts=True,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["source_count"] == 9
    assert report["summary"]["audit_record_count"] == 8
    assert report["summary"]["hard_blocker_count"] == 0
    assert report["summary"]["high_or_critical_residual_risk_count"] == 0
    assert report["summary"]["aggregate_score"] >= 90
    assert report["summary"]["release_readiness_signal"] == "candidate_ready_for_founder_review"
    assert markdown_path.read_text(encoding="utf-8").startswith("# Contextless Audit Scorecard")


def test_contextless_audit_scorecard_rejects_missing_required_artifact() -> None:
    sources = clone_sources()
    sources["phase127_fresh_local_model_drift"] = (None, None)

    report = build_report(sources=sources)

    assert report["status"] == "failed"
    assert "missing_required_artifact" in blocker_codes(report)
    assert report["summary"]["release_readiness_signal"] == "blocked"


def test_contextless_audit_scorecard_rejects_context_leakage() -> None:
    sources = clone_sources()
    path, recursive_report = sources["phase113_recursive_audit"]
    assert recursive_report is not None
    recursive_report["rounds"][0]["evaluator_context"]["fork_context"] = True  # type: ignore[index]
    sources["phase113_recursive_audit"] = (path, recursive_report)

    report = build_report(sources=sources)

    assert report["status"] == "failed"
    assert "context_leakage" in blocker_codes(report)
    context_dimension = [
        item for item in report["scorecard"]["dimension_scores"] if item["dimension_id"] == "context_isolation"
    ][0]
    assert context_dimension["score"] == 0


def test_contextless_audit_scorecard_rejects_blind_release_authority_text() -> None:
    sources = clone_sources()
    path, recursive_report = sources["phase114_recursive_audit"]
    assert recursive_report is not None
    recursive_report["release_note"] = "blind evaluator approved release"
    sources["phase114_recursive_audit"] = (path, recursive_report)

    report = build_report(sources=sources)

    assert report["status"] == "failed"
    assert "blind_agent_release_authority" in blocker_codes(report)


def test_contextless_audit_scorecard_rejects_recursive_policy_authority() -> None:
    recursive_path, recursive_policy = loaded_recursive_policy()
    assert recursive_path is not None
    assert recursive_policy is not None
    bad_policy = copy.deepcopy(recursive_policy)
    bad_policy["adjudication_policy"]["blind_evaluator_is_pass_fail_authority"] = True

    report = build_report(recursive_policy=bad_policy)

    assert report["status"] == "failed"
    assert "blind_agent_release_authority" in blocker_codes(report)


def test_contextless_audit_scorecard_rejects_missing_anythingllm_route() -> None:
    sources = clone_sources()
    path, drift_report = sources["phase127_fresh_local_model_drift"]
    assert drift_report is not None
    drift_report["summary"]["required_routes"] = ["gateway"]  # type: ignore[index]
    sources["phase127_fresh_local_model_drift"] = (path, drift_report)

    report = build_report(sources=sources)

    assert report["status"] == "failed"
    assert "missing_local_gateway_anythingllm_evidence" in blocker_codes(report)


def test_contextless_audit_scorecard_rejects_fixture_mutation() -> None:
    sources = clone_sources()
    path, drift_report = sources["phase127_fresh_local_model_drift"]
    assert drift_report is not None
    drift_report["families"][0]["local_eval_summary"]["target_changed_files"] = {  # type: ignore[index]
        "/mnt/c/coinbase_testing_repo_frozen_tmp.github": ["core/stealth_order_manager.py"]
    }
    sources["phase127_fresh_local_model_drift"] = (path, drift_report)

    report = build_report(sources=sources)

    assert report["status"] == "failed"
    assert "protected_fixture_mutation" in blocker_codes(report)


def test_contextless_audit_scorecard_rejects_low_source_score() -> None:
    sources = clone_sources()
    path, recursive_report = sources["phase115_recursive_audit"]
    assert recursive_report is not None
    recursive_report["score_summary"]["total_score"] = 60  # type: ignore[index]
    sources["phase115_recursive_audit"] = (path, recursive_report)

    report = build_report(sources=sources)

    assert report["status"] == "failed"
    assert "source_score_below_floor" in blocker_codes(report)


def test_contextless_audit_scorecard_rejects_unresolved_critical_risk() -> None:
    sources = clone_sources()
    path, recursive_report = sources["phase113_recursive_audit"]
    assert recursive_report is not None
    recursive_report["rounds"][0]["blind_findings"].append(  # type: ignore[index]
        {
            "id": "UNRESOLVED-CRITICAL",
            "category": "unsafe_behavior",
            "severity": "critical",
            "finding": "Fixture mutation was not ruled out.",
            "evidence_refs": ["synthetic"],
        }
    )
    sources["phase113_recursive_audit"] = (path, recursive_report)

    report = build_report(sources=sources)

    assert report["status"] == "failed"
    assert "unresolved_critical_high_risk" in blocker_codes(report)


def test_contextless_audit_scorecard_rejects_hidden_summary_edit() -> None:
    sources = loaded_sources()
    recursive_path, recursive_policy = loaded_recursive_policy()
    report = build_contextless_audit_scorecard_report(
        policy=policy(),
        sources=sources,
        recursive_policy=recursive_policy,
        policy_path=POLICY_PATH,
        recursive_policy_path=recursive_path,
    )
    report["summary"]["aggregate_score"] = 1

    errors = validate_contextless_audit_scorecard_report(
        report,
        policy=policy(),
        sources=sources,
        recursive_policy=recursive_policy,
        policy_path=POLICY_PATH,
        recursive_policy_path=recursive_path,
    )

    assert "report.summary must match rebuilt contextless audit scorecard" in errors


def test_contextless_audit_scorecard_policy_rejects_release_approval_claim() -> None:
    bad_policy = copy.deepcopy(policy())
    bad_policy["authority_policy"]["scorecard_grants_release_approval"] = True

    errors = validate_policy(bad_policy)

    assert "authority_policy.scorecard_grants_release_approval must be false" in errors
