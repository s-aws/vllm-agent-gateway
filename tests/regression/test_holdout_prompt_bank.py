from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.holdout_prompt_bank import (
    HoldoutPromptBankConfig,
    run_holdout_prompt_bank_validation,
    validate_holdout_prompt_bank,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = REPO_ROOT / "runtime" / "baseline_corpus.json"
BANK_PATH = REPO_ROOT / "runtime" / "holdout_prompt_bank.json"


def load_project_corpus() -> dict[str, object]:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def load_project_bank() -> dict[str, object]:
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def first_entry(value: dict[str, object]) -> dict[str, object]:
    return value["entries"][0]  # type: ignore[index]


def subset_first_entry(corpus: dict[str, object], bank: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    corpus = copy.deepcopy(corpus)
    bank = copy.deepcopy(bank)
    corpus["entries"] = [first_entry(corpus)]  # type: ignore[index]
    bank["entries"] = [first_entry(bank)]  # type: ignore[index]
    return corpus, bank


def replace_artifact_ref(
    *,
    tmp_path: Path,
    corpus: dict[str, object],
    bank: dict[str, object],
    ref_name: str,
    artifact: dict[str, object],
) -> None:
    artifact_path = write_json(tmp_path / f"{ref_name}.json", artifact)
    new_ref = {"path": str(artifact_path), "sha256": sha256_file(artifact_path)}
    first_entry(corpus)[ref_name] = new_ref
    first_entry(bank)["proof_refs"][ref_name] = copy.deepcopy(new_ref)  # type: ignore[index]


def test_project_holdout_prompt_bank_passes_with_current_artifacts() -> None:
    report = run_holdout_prompt_bank_validation(
        HoldoutPromptBankConfig(
            config_root=REPO_ROOT,
            output_path=REPO_ROOT / "runtime-state" / "holdout-prompt-bank" / "unit-project.json",
            require_artifacts=True,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["entry_count"] == 4  # type: ignore[index]
    assert report["summary"]["holdout_case_count"] == 8  # type: ignore[index]
    assert report["summary"]["holdout_response_count"] == 16  # type: ignore[index]
    assert report["summary"]["error_count"] == 0  # type: ignore[index]
    first_report_entry = report["entries"][0]  # type: ignore[index]
    assert "proof_hashes" in first_report_entry
    assert first_report_entry["proof_hashes"]["comparison"]["actual_sha256"]  # type: ignore[index]
    assert "target_coverage" in first_report_entry


def test_holdout_prompt_bank_rejects_missing_stable_entry() -> None:
    corpus = load_project_corpus()
    bank = load_project_bank()
    bank["entries"] = bank["entries"][:-1]  # type: ignore[index]

    errors, _checked = validate_holdout_prompt_bank(bank, corpus, config_root=REPO_ROOT, require_artifacts=False)

    assert any("entries must exactly match stable baseline corpus entry IDs" in error for error in errors)


def test_holdout_prompt_bank_rejects_missing_holdout_case_id() -> None:
    corpus, bank = subset_first_entry(load_project_corpus(), load_project_bank())
    first_entry(bank)["holdout_case_ids"] = ["CQ116-009"]

    errors, _checked = validate_holdout_prompt_bank(bank, corpus, config_root=REPO_ROOT, require_artifacts=True)

    assert any("holdout_case_ids must match expected_holdout_count" in error for error in errors)
    assert any("exactly match prompt cases marked holdout=true" in error for error in errors)


def test_holdout_prompt_bank_rejects_missing_blind_baseline_for_holdout(tmp_path: Path) -> None:
    corpus, bank = subset_first_entry(load_project_corpus(), load_project_bank())
    baseline_path = REPO_ROOT / first_entry(corpus)["blind_baselines"]["path"]  # type: ignore[index]
    baselines = json.loads(baseline_path.read_text(encoding="utf-8"))
    baselines["baselines"] = [item for item in baselines["baselines"] if item["case_id"] != "CQ116-009"]
    replace_artifact_ref(tmp_path=tmp_path, corpus=corpus, bank=bank, ref_name="blind_baselines", artifact=baselines)

    errors, _checked = validate_holdout_prompt_bank(bank, corpus, config_root=REPO_ROOT, require_artifacts=True)

    assert any("blind_baselines missing holdout case IDs" in error for error in errors)


def test_holdout_prompt_bank_rejects_missing_local_eval_route(tmp_path: Path) -> None:
    corpus, bank = subset_first_entry(load_project_corpus(), load_project_bank())
    local_eval_path = REPO_ROOT / first_entry(corpus)["local_eval"]["path"]  # type: ignore[index]
    local_eval = json.loads(local_eval_path.read_text(encoding="utf-8"))
    case = next(item for item in local_eval["checks"]["cases"] if item["case_id"] == "CQ116-009")
    case["responses"].pop("anythingllm")
    replace_artifact_ref(tmp_path=tmp_path, corpus=corpus, bank=bank, ref_name="local_eval", artifact=local_eval)

    errors, _checked = validate_holdout_prompt_bank(bank, corpus, config_root=REPO_ROOT, require_artifacts=True)

    assert any("local_eval case CQ116-009 missing route" in error for error in errors)


def test_holdout_prompt_bank_rejects_unexpected_local_eval_route(tmp_path: Path) -> None:
    corpus, bank = subset_first_entry(load_project_corpus(), load_project_bank())
    local_eval_path = REPO_ROOT / first_entry(corpus)["local_eval"]["path"]  # type: ignore[index]
    local_eval = json.loads(local_eval_path.read_text(encoding="utf-8"))
    case = next(item for item in local_eval["checks"]["cases"] if item["case_id"] == "CQ116-009")
    case["responses"]["shadow"] = copy.deepcopy(case["responses"]["gateway"])
    replace_artifact_ref(tmp_path=tmp_path, corpus=corpus, bank=bank, ref_name="local_eval", artifact=local_eval)

    errors, _checked = validate_holdout_prompt_bank(bank, corpus, config_root=REPO_ROOT, require_artifacts=True)

    assert any("local_eval case CQ116-009 has unexpected route" in error for error in errors)


def test_holdout_prompt_bank_rejects_failed_comparison_route(tmp_path: Path) -> None:
    corpus, bank = subset_first_entry(load_project_corpus(), load_project_bank())
    comparison_path = REPO_ROOT / first_entry(corpus)["comparison"]["path"]  # type: ignore[index]
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    case = next(item for item in comparison["cases"] if item["case_id"] == "CQ116-009")
    route = next(item for item in case["routes"] if item["route"] == "anythingllm")
    route["pass"] = False
    route["unresolved_findings"] = [{"severity": "high", "message": "artifact-only answer"}]
    replace_artifact_ref(tmp_path=tmp_path, corpus=corpus, bank=bank, ref_name="comparison", artifact=comparison)

    errors, _checked = validate_holdout_prompt_bank(bank, corpus, config_root=REPO_ROOT, require_artifacts=True)

    assert any("comparison case CQ116-009.anythingllm.pass must be true" in error for error in errors)
    assert any("unresolved_findings must be []" in error for error in errors)


def test_holdout_prompt_bank_rejects_low_comparison_score(tmp_path: Path) -> None:
    corpus, bank = subset_first_entry(load_project_corpus(), load_project_bank())
    comparison_path = REPO_ROOT / first_entry(corpus)["comparison"]["path"]  # type: ignore[index]
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    case = next(item for item in comparison["cases"] if item["case_id"] == "CQ116-009")
    route = next(item for item in case["routes"] if item["route"] == "gateway")
    route["score"] = 84
    replace_artifact_ref(tmp_path=tmp_path, corpus=corpus, bank=bank, ref_name="comparison", artifact=comparison)

    errors, _checked = validate_holdout_prompt_bank(bank, corpus, config_root=REPO_ROOT, require_artifacts=True)

    assert any("comparison case CQ116-009.gateway.score must be >= 85" in error for error in errors)


def test_holdout_prompt_bank_rejects_comparison_workflow_mismatch(tmp_path: Path) -> None:
    corpus, bank = subset_first_entry(load_project_corpus(), load_project_bank())
    comparison_path = REPO_ROOT / first_entry(corpus)["comparison"]["path"]  # type: ignore[index]
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    case = next(item for item in comparison["cases"] if item["case_id"] == "CQ116-009")
    route = next(item for item in case["routes"] if item["route"] == "gateway")
    route["selected_workflow"] = "wrong.workflow"
    replace_artifact_ref(tmp_path=tmp_path, corpus=corpus, bank=bank, ref_name="comparison", artifact=comparison)

    errors, _checked = validate_holdout_prompt_bank(bank, corpus, config_root=REPO_ROOT, require_artifacts=True)

    assert any("selected_workflow must match local_eval" in error for error in errors)


def test_holdout_prompt_bank_rejects_missing_frozen_target_justification() -> None:
    corpus, bank = subset_first_entry(load_project_corpus(), load_project_bank())
    target_coverage = first_entry(bank)["target_coverage"]  # type: ignore[index]
    target_coverage["justification"] = ""

    errors, _checked = validate_holdout_prompt_bank(bank, corpus, config_root=REPO_ROOT, require_artifacts=True)

    assert any("target_coverage.justification is required" in error for error in errors)


def test_holdout_prompt_bank_rejects_target_mutation_proof_gap(tmp_path: Path) -> None:
    corpus, bank = subset_first_entry(load_project_corpus(), load_project_bank())
    local_eval_path = REPO_ROOT / first_entry(corpus)["local_eval"]["path"]  # type: ignore[index]
    local_eval = json.loads(local_eval_path.read_text(encoding="utf-8"))
    local_eval["target_changed_files"] = {"/tmp/repo": ["changed.py"]}
    replace_artifact_ref(tmp_path=tmp_path, corpus=corpus, bank=bank, ref_name="local_eval", artifact=local_eval)

    errors, _checked = validate_holdout_prompt_bank(bank, corpus, config_root=REPO_ROOT, require_artifacts=True)

    assert any("local_eval.target_changed_files must be {}" in error for error in errors)


def test_holdout_prompt_bank_rejects_stale_comparison_hash() -> None:
    corpus, bank = subset_first_entry(load_project_corpus(), load_project_bank())
    comparison = first_entry(bank)["proof_refs"]["comparison"]  # type: ignore[index]
    comparison["sha256"] = "0" * 64

    errors, _checked = validate_holdout_prompt_bank(bank, corpus, config_root=REPO_ROOT, require_artifacts=True)

    assert any("proof_refs.comparison.sha256 must match baseline corpus" in error for error in errors)
