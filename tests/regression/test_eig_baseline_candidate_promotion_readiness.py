from __future__ import annotations

import json
from pathlib import Path

from vllm_agent_gateway.acceptance.eig_baseline_candidate_promotion_readiness import (
    EIGBaselineCandidatePromotionReadinessConfig,
    run_eig_baseline_candidate_promotion_readiness,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "eig_baseline_candidate_promotion_readiness_policy.json"


def load_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def test_eig_baseline_candidate_promotion_readiness_policy_passes() -> None:
    assert validate_policy(load_policy(), config_root=REPO_ROOT) == []


def test_eig_baseline_candidate_promotion_readiness_static_report_blocks_promotion(tmp_path: Path) -> None:
    report = run_eig_baseline_candidate_promotion_readiness(
        EIGBaselineCandidatePromotionReadinessConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase311.json",
            skip_github=True,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["candidate_count"] == 2
    assert report["summary"]["blocked_candidate_count"] == 2
    assert report["summary"]["approved_candidate_count"] == 0
    assert report["summary"]["promotion_allowed"] is False
    assert report["summary"]["stable_corpus_mutated"] is False
    assert report["summary"]["phase312_ready"] is True
    assert set(report["summary"]["missing_evidence"]) == {
        "blind_baseline",
        "local_model_comparison",
        "holdout",
        "route_proof",
        "no_mutation_proof",
        "founder_approval",
    }


def test_eig_baseline_candidate_promotion_readiness_rejects_stale_candidate_source_hash() -> None:
    policy = load_policy()
    policy["candidate_source"]["sha256"] = "0" * 64

    errors = validate_policy(policy, config_root=REPO_ROOT)

    assert any("candidate_source.sha256 is stale" in error for error in errors)


def test_eig_baseline_candidate_promotion_readiness_rejects_promotion_mutation_allowed() -> None:
    policy = load_policy()
    policy["promotion_policy"]["stable_corpus_mutation_allowed"] = True

    errors = validate_policy(policy, config_root=REPO_ROOT)

    assert any("stable_corpus_mutation_allowed must be false" in error for error in errors)


def test_eig_baseline_candidate_promotion_readiness_rejects_missing_pr_marker() -> None:
    policy = load_policy()
    policy["pr_evidence"]["required_body_markers"] = []

    errors = validate_policy(policy, config_root=REPO_ROOT)

    assert any("required_body_markers must be non-empty" in error for error in errors)
