from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.baseline_corpus import (
    BaselineCorpusConfig,
    run_baseline_corpus_governance,
    validate_baseline_corpus,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = REPO_ROOT / "runtime" / "baseline_corpus.json"


def load_project_corpus() -> dict[str, object]:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def first_entry(corpus: dict[str, object]) -> dict[str, object]:
    return corpus["entries"][0]  # type: ignore[index]


def phase242_entry(corpus: dict[str, object]) -> dict[str, object]:
    return next(entry for entry in corpus["entries"] if entry["phase"] == 242)  # type: ignore[index]


def write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_project_baseline_corpus_passes_with_current_artifacts() -> None:
    report = run_baseline_corpus_governance(
        BaselineCorpusConfig(
            config_root=REPO_ROOT,
            output_path=REPO_ROOT / "runtime-state" / "baseline-corpus" / "unit-project.json",
            require_artifacts=True,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["entry_count"] == 5  # type: ignore[index]
    assert report["summary"]["stable_entry_count"] == 5  # type: ignore[index]
    assert report["summary"]["error_count"] == 0  # type: ignore[index]


def test_baseline_corpus_rejects_policy_drift() -> None:
    corpus = load_project_corpus()
    policy = corpus["governance_policy"]  # type: ignore[index]
    policy["source_mutation_allowed"] = True  # type: ignore[index]

    errors = validate_baseline_corpus(corpus, config_root=REPO_ROOT)

    assert any("source_mutation_allowed must be false" in error for error in errors)


def test_baseline_corpus_rejects_missing_governed_phase() -> None:
    corpus = load_project_corpus()
    corpus["entries"] = corpus["entries"][:-1]  # type: ignore[index]

    errors = validate_baseline_corpus(corpus, config_root=REPO_ROOT)

    assert any("exactly cover phases 116, 117, 118, 119, and 242" in error for error in errors)


def test_baseline_corpus_rejects_missing_blind_baseline_summary() -> None:
    corpus = load_project_corpus()
    first_entry(corpus).pop("blind_baselines")

    errors = validate_baseline_corpus(corpus, config_root=REPO_ROOT)

    assert any("blind_baselines.path is required" in error for error in errors)


def test_baseline_corpus_rejects_weak_blind_baseline_record(tmp_path: Path) -> None:
    corpus = load_project_corpus()
    original_path = REPO_ROOT / first_entry(corpus)["blind_baselines"]["path"]  # type: ignore[index]
    baseline = json.loads(original_path.read_text(encoding="utf-8"))
    baseline["baselines"][0].pop("safety_boundaries")
    weak_path = write_json(tmp_path / "weak-baselines.json", baseline)
    blind_baselines = first_entry(corpus)["blind_baselines"]  # type: ignore[index]
    blind_baselines["path"] = str(weak_path)  # type: ignore[index]
    blind_baselines["sha256"] = sha256_file(weak_path)  # type: ignore[index]

    errors = validate_baseline_corpus(corpus, config_root=REPO_ROOT)

    assert any("safety_boundaries is required" in error for error in errors)


def test_baseline_corpus_rejects_baseline_after_local_output() -> None:
    corpus = load_project_corpus()
    source_order = first_entry(corpus)["source_order"]  # type: ignore[index]
    source_order["local_model_output_seen_by_blind_agent"] = True  # type: ignore[index]

    errors = validate_baseline_corpus(corpus, config_root=REPO_ROOT)

    assert any("local_model_output_seen_by_blind_agent must be false" in error for error in errors)


def test_baseline_corpus_rejects_blind_baseline_collected_after_local_output() -> None:
    corpus = load_project_corpus()
    source_order = first_entry(corpus)["source_order"]  # type: ignore[index]
    source_order["blind_baseline_collected_before_local_output"] = False  # type: ignore[index]

    errors = validate_baseline_corpus(corpus, config_root=REPO_ROOT)

    assert any("blind_baseline_collected_before_local_output must be true" in error for error in errors)


def test_baseline_corpus_rejects_missing_local_eval_summary() -> None:
    corpus = load_project_corpus()
    first_entry(corpus).pop("local_eval")

    errors = validate_baseline_corpus(corpus, config_root=REPO_ROOT)

    assert any("local_eval is required" in error for error in errors)


def test_baseline_corpus_rejects_missing_comparison_summary() -> None:
    corpus = load_project_corpus()
    first_entry(corpus).pop("comparison")

    errors = validate_baseline_corpus(corpus, config_root=REPO_ROOT)

    assert any("comparison is required" in error for error in errors)


def test_baseline_corpus_rejects_unresolved_critical_comparison() -> None:
    corpus = load_project_corpus()
    comparison = first_entry(corpus)["comparison"]  # type: ignore[index]
    comparison["critical_finding_count"] = 1  # type: ignore[index]

    errors = validate_baseline_corpus(corpus, config_root=REPO_ROOT)

    assert any("critical_finding_count must be 0" in error for error in errors)


def test_baseline_corpus_rejects_low_minimum_route_score() -> None:
    corpus = load_project_corpus()
    comparison = first_entry(corpus)["comparison"]  # type: ignore[index]
    comparison["minimum_route_score"] = 84  # type: ignore[index]

    errors = validate_baseline_corpus(corpus, config_root=REPO_ROOT)

    assert any("minimum_route_score must be >= 85" in error for error in errors)


def test_baseline_corpus_rejects_comparison_input_hash_mismatch() -> None:
    corpus = load_project_corpus()
    comparison = first_entry(corpus)["comparison"]  # type: ignore[index]
    inputs = comparison["inputs"]  # type: ignore[index]
    inputs["local_eval_sha256"] = "1" * 64  # type: ignore[index]

    errors = validate_baseline_corpus(corpus, config_root=REPO_ROOT)

    assert any("comparison.inputs.local_eval_sha256" in error for error in errors)


def test_baseline_corpus_rejects_wrong_expected_response_count() -> None:
    corpus = load_project_corpus()
    first_entry(corpus)["expected_response_count"] = 10

    errors = validate_baseline_corpus(corpus, config_root=REPO_ROOT)

    assert any("expected_response_count must equal expected_case_count" in error for error in errors)


def test_baseline_corpus_rejects_stale_prompt_case_hash() -> None:
    corpus = load_project_corpus()
    prompt_cases = first_entry(corpus)["prompt_cases"]  # type: ignore[index]
    prompt_cases["sha256"] = "0" * 64  # type: ignore[index]

    errors = validate_baseline_corpus(corpus, config_root=REPO_ROOT)

    assert any("prompt_cases.sha256 is stale" in error for error in errors)


def test_baseline_corpus_rejects_missing_anythingllm_route() -> None:
    corpus = load_project_corpus()
    local_eval = first_entry(corpus)["local_eval"]  # type: ignore[index]
    local_eval["routes"] = ["gateway"]  # type: ignore[index]

    errors = validate_baseline_corpus(corpus, config_root=REPO_ROOT)

    assert any("local_eval.routes missing required route" in error for error in errors)


def test_baseline_corpus_rejects_target_mutation_proof_gap() -> None:
    corpus = load_project_corpus()
    local_eval = first_entry(corpus)["local_eval"]  # type: ignore[index]
    mutation_proof = local_eval["mutation_proof"]  # type: ignore[index]
    mutation_proof["target_changed_files"] = {"/tmp/repo": ["changed.py"]}  # type: ignore[index]

    errors = validate_baseline_corpus(corpus, config_root=REPO_ROOT)

    assert any("target_changed_files must be {}" in error for error in errors)


def test_baseline_corpus_rejects_non_empty_git_mutation_proof() -> None:
    corpus = load_project_corpus()
    local_eval = first_entry(corpus)["local_eval"]  # type: ignore[index]
    mutation_proof = local_eval["mutation_proof"]  # type: ignore[index]
    mutation_proof["target_git_changed"] = {"/tmp/repo": {"before": "", "after": " M changed.py"}}  # type: ignore[index]

    errors = validate_baseline_corpus(corpus, config_root=REPO_ROOT)

    assert any("target_git_changed must be empty" in error for error in errors)


def test_baseline_corpus_rejects_missing_holdout() -> None:
    corpus = load_project_corpus()
    entry = first_entry(corpus)
    entry["expected_holdout_count"] = 3

    errors = validate_baseline_corpus(corpus, config_root=REPO_ROOT)

    assert any("fewer holdouts than expected" in error for error in errors)


def test_baseline_corpus_rejects_missing_phase242_category_coverage() -> None:
    corpus = load_project_corpus()
    phase242 = phase242_entry(corpus)
    phase242["required_prompt_categories"] = [*phase242["required_prompt_categories"], "missing_release_category"]  # type: ignore[index]

    errors = validate_baseline_corpus(corpus, config_root=REPO_ROOT)

    assert any("missing required category coverage: missing_release_category" in error for error in errors)


def test_baseline_corpus_rejects_phase242_missing_surface_metadata(tmp_path: Path) -> None:
    corpus = load_project_corpus()
    phase242 = phase242_entry(corpus)
    original_path = REPO_ROOT / phase242["prompt_cases"]["path"]  # type: ignore[index]
    prompt_cases = json.loads(original_path.read_text(encoding="utf-8"))
    prompt_cases["cases"][0]["target_surfaces"] = ["gateway"]
    weak_path = write_json(tmp_path / "phase242-missing-surface.json", prompt_cases)
    phase242["prompt_cases"]["path"] = str(weak_path)  # type: ignore[index]
    phase242["prompt_cases"]["sha256"] = sha256_file(weak_path)  # type: ignore[index]

    errors = validate_baseline_corpus(corpus, config_root=REPO_ROOT)

    assert any("target_surfaces missing required surface(s): anythingllm" in error for error in errors)


def test_baseline_corpus_rejects_phase242_empty_forbidden_behaviors(tmp_path: Path) -> None:
    corpus = load_project_corpus()
    phase242 = phase242_entry(corpus)
    original_path = REPO_ROOT / phase242["prompt_cases"]["path"]  # type: ignore[index]
    prompt_cases = json.loads(original_path.read_text(encoding="utf-8"))
    prompt_cases["cases"][0]["forbidden_behaviors"] = []
    weak_path = write_json(tmp_path / "phase242-empty-forbidden.json", prompt_cases)
    phase242["prompt_cases"]["path"] = str(weak_path)  # type: ignore[index]
    phase242["prompt_cases"]["sha256"] = sha256_file(weak_path)  # type: ignore[index]

    errors = validate_baseline_corpus(corpus, config_root=REPO_ROOT)

    assert any("forbidden_behaviors must be a non-empty string list" in error for error in errors)


def test_baseline_corpus_rejects_phase242_missing_promotion_evidence() -> None:
    corpus = load_project_corpus()
    phase242_entry(corpus).pop("promotion_evidence")

    errors = validate_baseline_corpus(corpus, config_root=REPO_ROOT)

    assert any("promotion_evidence is required" in error for error in errors)


def test_baseline_corpus_rejects_recommended_repair_without_rerun() -> None:
    corpus = load_project_corpus()
    entry = first_entry(corpus)
    comparison = entry["comparison"]  # type: ignore[index]
    comparison["recommended_next_repairs"] = ["baseline_topic_gap"]  # type: ignore[index]
    repair_status = copy.deepcopy(entry["repair_status"])  # type: ignore[index]
    repair_status["status"] = "not_required"
    entry["repair_status"] = repair_status

    errors = validate_baseline_corpus(corpus, config_root=REPO_ROOT)

    assert any("cannot be not_required" in error for error in errors)


def test_baseline_corpus_rejects_accepted_repair_without_holdout_rerun() -> None:
    corpus = load_project_corpus()
    repair_status = first_entry(corpus)["repair_status"]  # type: ignore[index]
    repair_status["status"] = "accepted_and_rerun"  # type: ignore[index]
    repair_status["holdout_rerun_status"] = "missing"  # type: ignore[index]

    errors = validate_baseline_corpus(corpus, config_root=REPO_ROOT)

    assert any("holdout_rerun_status must be passed" in error for error in errors)
