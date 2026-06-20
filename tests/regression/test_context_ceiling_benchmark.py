from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.context_ceiling_benchmark import (
    ContextCeilingBenchmarkConfig,
    run_context_ceiling_benchmark,
    score_answer,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "context_ceiling_benchmark_policy.json"


def load_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def test_context_ceiling_benchmark_policy_passes() -> None:
    assert validate_policy(load_policy()) == []


def test_context_ceiling_benchmark_no_live_validates_policy_without_claiming_raw_500k(tmp_path: Path) -> None:
    report = run_context_ceiling_benchmark(
        ContextCeilingBenchmarkConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase318.json",
            run_live=False,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["run_live"] is False
    assert report["summary"]["raw_500k_prompt_support_proven"] is False
    assert report["summary"]["governed_500k_project_usability_unchanged"] is True
    assert report["summary"]["stable_corpus_mutated"] is False
    assert report["summary"]["phase319_ready"] is False


def test_context_ceiling_benchmark_policy_rejects_missing_256k_class() -> None:
    policy = copy.deepcopy(load_policy())
    policy["context_classes"] = policy["context_classes"][:-1]

    errors = validate_policy(policy)

    assert any("context_classes must be ordered" in error for error in errors)


def test_context_ceiling_benchmark_policy_rejects_raw_500k_claim_allowed() -> None:
    policy = copy.deepcopy(load_policy())
    policy["benchmark_policy"]["raw_500k_prompt_support_claim_allowed"] = True

    errors = validate_policy(policy)

    assert any("raw_500k_prompt_support_claim_allowed must be false" in error for error in errors)


def test_context_ceiling_benchmark_score_answer_detects_missing_and_forbidden_fragments() -> None:
    expected = load_policy()["expected_answer"]
    passing = "BRIDGE-42 LANTERN-29 ALPHA-32 BRAVO-64 CHARLIE-128 DELTA-256 SILVER-11 obsolete"
    failing = "controlling decision id is SILVER-11 with ALPHA-32"

    assert score_answer(passing, expected)["passed"] is True
    failed = score_answer(failing, expected)
    assert failed["passed"] is False
    assert "controlling decision id is SILVER-11" in failed["forbidden_fragments"]
