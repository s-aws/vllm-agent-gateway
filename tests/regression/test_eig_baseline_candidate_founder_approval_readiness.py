from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.eig_baseline_candidate_founder_approval_readiness import (
    EIGBaselineCandidateFounderApprovalReadinessConfig,
    run_eig_baseline_candidate_founder_approval_readiness,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "eig_baseline_candidate_founder_approval_readiness_policy.json"


def load_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def write_report(path: Path, *, kind: str, phase: int, recorded_evidence: list[str], summary_extra: dict | None = None) -> None:
    summary = {
        "status": "passed",
        "recorded_evidence": recorded_evidence,
        "validation_error_count": 0,
        "promotion_allowed": False,
        "stable_corpus_promotion_allowed": False,
    }
    if summary_extra:
        summary.update(summary_extra)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": kind,
                "phase": phase,
                "status": "passed",
                "summary": summary,
                "validation_errors": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def write_required_reports(tmp_path: Path) -> dict[str, Path]:
    paths = {
        "blind": tmp_path / "blind.json",
        "local": tmp_path / "local.json",
        "route": tmp_path / "route.json",
        "holdout": tmp_path / "holdout.json",
    }
    write_report(
        paths["blind"],
        kind="eig_baseline_candidate_blind_baselines_report",
        phase=312,
        recorded_evidence=["blind_baseline"],
    )
    write_report(
        paths["local"],
        kind="eig_baseline_candidate_local_comparison_report",
        phase=313,
        recorded_evidence=["blind_baseline", "local_model_comparison"],
    )
    write_report(
        paths["route"],
        kind="eig_baseline_candidate_route_mutation_proof_report",
        phase=315,
        recorded_evidence=["route_proof", "no_mutation_proof"],
        summary_extra={"stable_corpus_mutated": False},
    )
    write_report(
        paths["holdout"],
        kind="eig_baseline_candidate_holdout_proof_report",
        phase=316,
        recorded_evidence=["holdout"],
        summary_extra={"stable_corpus_mutated": False, "connector_registry_mutated": False},
    )
    return paths


def test_founder_approval_readiness_policy_passes() -> None:
    assert validate_policy(load_policy(), config_root=REPO_ROOT) == []


def test_founder_approval_readiness_blocks_only_on_founder_approval(tmp_path: Path) -> None:
    paths = write_required_reports(tmp_path)

    report = run_eig_baseline_candidate_founder_approval_readiness(
        EIGBaselineCandidateFounderApprovalReadinessConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase317.json",
            blind_baseline_report_path=paths["blind"],
            local_comparison_report_path=paths["local"],
            route_mutation_report_path=paths["route"],
            holdout_report_path=paths["holdout"],
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["candidate_count"] == 2
    assert report["summary"]["blocked_candidate_count"] == 2
    assert report["summary"]["missing_evidence"] == ["founder_approval"]
    assert report["summary"]["ready_for_founder_decision"] is True
    assert report["summary"]["promotion_allowed"] is False
    assert report["summary"]["founder_approval_recorded"] is False
    assert report["summary"]["stable_corpus_mutated"] is False


def test_founder_approval_readiness_rejects_missing_holdout_evidence(tmp_path: Path) -> None:
    paths = write_required_reports(tmp_path)
    write_report(
        paths["holdout"],
        kind="eig_baseline_candidate_holdout_proof_report",
        phase=316,
        recorded_evidence=[],
    )

    report = run_eig_baseline_candidate_founder_approval_readiness(
        EIGBaselineCandidateFounderApprovalReadinessConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase317.json",
            blind_baseline_report_path=paths["blind"],
            local_comparison_report_path=paths["local"],
            route_mutation_report_path=paths["route"],
            holdout_report_path=paths["holdout"],
        )
    )

    assert report["status"] == "failed"
    assert report["summary"]["ready_for_founder_decision"] is False
    assert any("holdout.summary.recorded_evidence" in error for error in report["validation_errors"])


def test_founder_approval_readiness_rejects_founder_approval_recorded_in_artifact(tmp_path: Path) -> None:
    paths = write_required_reports(tmp_path)
    write_report(
        paths["local"],
        kind="eig_baseline_candidate_local_comparison_report",
        phase=313,
        recorded_evidence=["blind_baseline", "local_model_comparison", "founder_approval"],
    )

    report = run_eig_baseline_candidate_founder_approval_readiness(
        EIGBaselineCandidateFounderApprovalReadinessConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase317.json",
            blind_baseline_report_path=paths["blind"],
            local_comparison_report_path=paths["local"],
            route_mutation_report_path=paths["route"],
            holdout_report_path=paths["holdout"],
        )
    )

    assert report["status"] == "failed"
    assert any("must not include founder_approval" in error for error in report["validation_errors"])


def test_founder_approval_readiness_policy_rejects_auto_promote() -> None:
    policy = copy.deepcopy(load_policy())
    policy["promotion_policy"]["auto_promote_allowed"] = True

    errors = validate_policy(policy, config_root=REPO_ROOT)

    assert any("auto_promote_allowed must be false" in error for error in errors)
