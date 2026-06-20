from __future__ import annotations

import json
from pathlib import Path

from vllm_agent_gateway.acceptance.eig_baseline_candidate_live_replay import (
    EIGBaselineCandidateLiveReplayConfig,
    run_eig_baseline_candidate_live_replay,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "eig_baseline_candidate_live_replay_policy.json"


def load_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def test_eig_baseline_candidate_live_replay_static_preflight_passes(tmp_path: Path) -> None:
    report = run_eig_baseline_candidate_live_replay(
        EIGBaselineCandidateLiveReplayConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase308.json",
            run_live=False,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["candidate_count"] == 2
    assert report["summary"]["total_source_case_count"] == 7
    assert report["summary"]["stable_corpus_entry_count"] == 5
    assert report["summary"]["stable_corpus_mutated"] is False
    assert report["summary"]["stable_corpus_promotion_allowed"] is False
    assert report["summary"]["phase309_ready"] is False


def test_eig_baseline_candidate_live_replay_rejects_stale_candidate_source_hash() -> None:
    policy = load_policy()
    policy["candidate_source"]["sha256"] = "0" * 64

    errors = validate_policy(policy, config_root=REPO_ROOT)

    assert any("candidate_source.sha256 is stale" in error for error in errors)


def test_eig_baseline_candidate_live_replay_rejects_promotion_allowed() -> None:
    policy = load_policy()
    policy["replay_policy"]["stable_corpus_promotion_allowed"] = True

    errors = validate_policy(policy, config_root=REPO_ROOT)

    assert any("stable_corpus_promotion_allowed must be false" in error for error in errors)
