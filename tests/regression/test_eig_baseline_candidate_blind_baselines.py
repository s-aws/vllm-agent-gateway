from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.eig_baseline_candidate_blind_baselines import (
    EIGBaselineCandidateBlindBaselineConfig,
    run_eig_baseline_candidate_blind_baselines,
    validate_baselines,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = REPO_ROOT / "runtime" / "eig_baseline_candidate_blind_baselines.json"


def load_baselines() -> dict:
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def test_eig_baseline_candidate_blind_baselines_pass(tmp_path: Path) -> None:
    report = run_eig_baseline_candidate_blind_baselines(
        EIGBaselineCandidateBlindBaselineConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase312.json",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["case_count"] == 7
    assert report["summary"]["contextless_agent_first"] is True
    assert report["summary"]["local_model_output_seen"] is False
    assert report["summary"]["recorded_evidence"] == ["blind_baseline"]
    assert report["summary"]["promotion_allowed"] is False
    assert "blind_baseline" not in report["summary"]["remaining_missing_evidence"]
    assert report["summary"]["phase313_ready"] is True


def test_eig_baseline_candidate_blind_baselines_rejects_local_output_seen() -> None:
    baselines = copy.deepcopy(load_baselines())
    baselines["baseline_policy"]["local_model_output_seen"] = True

    errors = validate_baselines(baselines, config_root=REPO_ROOT)

    assert any("local_model_output_seen must be false" in error for error in errors)


def test_eig_baseline_candidate_blind_baselines_rejects_missing_case() -> None:
    baselines = copy.deepcopy(load_baselines())
    baselines["baselines"] = baselines["baselines"][:-1]

    errors = validate_baselines(baselines, config_root=REPO_ROOT)

    assert any("baselines case IDs must match" in error for error in errors)


def test_eig_baseline_candidate_blind_baselines_rejects_stale_source_hash() -> None:
    baselines = copy.deepcopy(load_baselines())
    baselines["source_packs"]["eig_runtime_breadth_chat_cases"]["sha256"] = "0" * 64

    errors = validate_baselines(baselines, config_root=REPO_ROOT)

    assert any("source_packs.eig_runtime_breadth_chat_cases.sha256 is stale" in error for error in errors)


def test_eig_baseline_candidate_blind_baselines_rejects_empty_required_fields() -> None:
    baselines = copy.deepcopy(load_baselines())
    baselines["baselines"][0]["must_include"] = []

    errors = validate_baselines(baselines, config_root=REPO_ROOT)

    assert any("must_include must be a non-empty string array" in error for error in errors)
