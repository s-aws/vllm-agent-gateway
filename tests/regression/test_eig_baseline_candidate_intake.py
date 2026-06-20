from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.eig_baseline_candidate_intake import (
    EIGBaselineCandidateIntakeConfig,
    run_eig_baseline_candidate_intake,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "eig_baseline_candidate_intake_policy.json"


def load_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def test_eig_baseline_candidate_intake_passes(tmp_path: Path) -> None:
    report = run_eig_baseline_candidate_intake(
        EIGBaselineCandidateIntakeConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase307.json",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["candidate_count"] == 2
    assert report["summary"]["total_source_case_count"] == 7
    assert report["summary"]["stable_corpus_entry_count"] == 5
    assert report["summary"]["stable_corpus_mutated"] is False
    assert report["summary"]["candidate_pending_live_replay_count"] == 2
    assert report["summary"]["phase308_ready"] is True


def test_eig_baseline_candidate_intake_rejects_stale_source_hash() -> None:
    policy = load_policy()
    policy["source_packs"]["eig_runtime_breadth_chat_cases"]["sha256"] = "0" * 64

    errors, _ = validate_policy(policy, config_root=REPO_ROOT)

    assert any("source_packs.eig_runtime_breadth_chat_cases.sha256 is stale" in error for error in errors)


def test_eig_baseline_candidate_intake_rejects_stable_corpus_mutation() -> None:
    policy = load_policy()
    policy["candidates"][0]["proposed_entry_id"] = "phase116_code_quality"

    errors, _ = validate_policy(policy, config_root=REPO_ROOT)

    assert any("proposed_entry_id must not already exist in stable corpus" in error for error in errors)


def test_eig_baseline_candidate_intake_rejects_premature_evidence_refs() -> None:
    policy = copy.deepcopy(load_policy())
    policy["candidates"][0]["evidence_refs"] = [{"evidence_type": "route_proof"}]

    errors, _ = validate_policy(policy, config_root=REPO_ROOT)

    assert any("evidence_refs must be empty before Phase 308 live replay" in error for error in errors)
