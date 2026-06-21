from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.eig_baseline_candidate_holdout_proof import (
    EIGBaselineCandidateHoldoutProofConfig,
    run_eig_baseline_candidate_holdout_proof,
    validate_cases_pack,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "eig_baseline_candidate_holdout_proof_policy.json"
CASES_PATH = REPO_ROOT / "runtime" / "eig_baseline_candidate_holdout_cases.json"


def load_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def load_cases() -> dict:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def test_holdout_policy_and_cases_pass_shape_validation() -> None:
    assert validate_policy(load_policy(), config_root=REPO_ROOT) == []
    assert validate_cases_pack(load_cases()) == []


def test_holdout_no_live_validates_shape_without_recording_evidence(tmp_path: Path) -> None:
    report = run_eig_baseline_candidate_holdout_proof(
        EIGBaselineCandidateHoldoutProofConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "holdout.json",
            run_live=False,
            include_anythingllm=False,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["holdout_case_count"] == 7
    assert report["summary"]["result_count"] == 0
    assert report["summary"]["recorded_evidence"] == []
    assert report["summary"]["remaining_missing_evidence"] == ["founder_approval", "holdout"]
    assert report["summary"]["phase317_ready"] is False


def test_holdout_cases_require_contextless_baseline_order() -> None:
    pack = copy.deepcopy(load_cases())
    pack["contextless_baseline"]["local_model_output_seen"] = True

    errors = validate_cases_pack(pack)

    assert any("local_model_output_seen must be false" in error for error in errors)


def test_holdout_policy_rejects_stable_corpus_promotion_allowed() -> None:
    policy = copy.deepcopy(load_policy())
    policy["stable_corpus_promotion_allowed"] = True

    errors = validate_policy(policy, config_root=REPO_ROOT)

    assert any("stable_corpus_promotion_allowed must be false" in error for error in errors)


def test_holdout_cases_require_three_connector_and_four_privacy_cases() -> None:
    pack = copy.deepcopy(load_cases())
    pack["holdout_cases"] = pack["holdout_cases"][:-1]

    errors = validate_cases_pack(pack)

    assert any("exactly 7 cases" in error for error in errors)
    assert any("4 privacy cases" in error for error in errors)
