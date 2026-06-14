from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.priority0_gap_taxonomy import (
    Priority0GapTaxonomyConfig,
    run_priority0_gap_taxonomy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = REPO_ROOT / "runtime" / "baseline_corpus.json"


def load_project_corpus() -> dict[str, object]:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_report(tmp_path: Path, corpus: dict[str, object], *, require_artifacts: bool = True) -> dict[str, object]:
    corpus_path = write_json(tmp_path / "baseline_corpus.json", corpus)
    return run_priority0_gap_taxonomy(
        Priority0GapTaxonomyConfig(
            config_root=REPO_ROOT,
            corpus_path=corpus_path,
            output_path=tmp_path / "priority0-gap-taxonomy.json",
            markdown_output_path=tmp_path / "priority0-gap-taxonomy.md",
            require_artifacts=require_artifacts,
        )
    )


def first_entry(corpus: dict[str, object]) -> dict[str, object]:
    return corpus["entries"][0]  # type: ignore[index]


def test_project_priority0_gap_taxonomy_passes_current_stable_corpus() -> None:
    report = run_priority0_gap_taxonomy(
        Priority0GapTaxonomyConfig(
            config_root=REPO_ROOT,
            output_path=REPO_ROOT / "runtime-state" / "priority0-gap-taxonomy" / "unit-project.json",
            require_artifacts=True,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["comparison_count"] == 5  # type: ignore[index]
    assert report["summary"]["finding_count"] == 0  # type: ignore[index]
    assert report["summary"]["error_count"] == 0  # type: ignore[index]


def test_priority0_gap_taxonomy_maps_comparison_misses_to_gap_classes(tmp_path: Path) -> None:
    corpus = load_project_corpus()
    entry = first_entry(corpus)
    comparison_path = REPO_ROOT / entry["comparison"]["path"]  # type: ignore[index]
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    route = comparison["cases"][0]["routes"][0]
    route["pass"] = False
    route["score"] = 35
    route["unresolved_findings"] = [
        {"severity": "critical", "category": "routing", "message": "selected wrong workflow"},
        {"severity": "high", "category": "evidence", "message": "response did not include source refs"},
        {"severity": "high", "category": "answer_contract", "message": "response omitted findings"},
        {"severity": "medium", "category": "test_level", "message": "response omitted validation tests"},
    ]
    comparison["status"] = "failed"
    comparison["passed_response_count"] -= 1
    comparison["critical_finding_count"] = 1
    comparison["high_finding_count"] = 2
    comparison["gap_categories"] = {"routing": 1, "evidence": 1, "answer_contract": 1, "test_level": 1}
    mutated_comparison_path = write_json(tmp_path / "comparison.json", comparison)
    comparison_ref = entry["comparison"]  # type: ignore[index]
    comparison_ref["path"] = str(mutated_comparison_path)  # type: ignore[index]
    comparison_ref["sha256"] = sha256_file(mutated_comparison_path)  # type: ignore[index]

    report = run_report(tmp_path, corpus)

    assert report["status"] == "failed"
    assert report["summary"]["finding_count"] >= 4  # type: ignore[index]
    assert report["summary"]["gap_class_counts"]["routing"] >= 1  # type: ignore[index]
    assert report["summary"]["gap_class_counts"]["context_gathering"] >= 1  # type: ignore[index]
    assert report["summary"]["gap_class_counts"]["deterministic_formatter"] >= 1  # type: ignore[index]
    assert report["summary"]["gap_class_counts"]["test_coverage"] >= 1  # type: ignore[index]
    assert all(item["evidence"]["bounded_repair_action"] for item in report["findings"])  # type: ignore[index]
    assert (tmp_path / "priority0-gap-taxonomy.md").read_text(encoding="utf-8").startswith(
        "# Priority 0 Gap Taxonomy Report"
    )


def test_priority0_gap_taxonomy_rejects_stale_comparison_hash(tmp_path: Path) -> None:
    corpus = copy.deepcopy(load_project_corpus())
    comparison = first_entry(corpus)["comparison"]  # type: ignore[index]
    comparison["sha256"] = "0" * 64  # type: ignore[index]

    report = run_report(tmp_path, corpus)

    assert report["status"] == "failed"
    assert any("comparison.sha256 is stale" in error for error in report["errors"])  # type: ignore[index]


def test_priority0_gap_taxonomy_requires_artifacts_by_default(tmp_path: Path) -> None:
    corpus = copy.deepcopy(load_project_corpus())
    comparison = first_entry(corpus)["comparison"]  # type: ignore[index]
    comparison["path"] = "runtime-state/missing/does-not-exist.json"  # type: ignore[index]

    corpus_path = write_json(tmp_path / "baseline_corpus.json", corpus)
    report = run_priority0_gap_taxonomy(
        Priority0GapTaxonomyConfig(
            config_root=REPO_ROOT,
            corpus_path=corpus_path,
            output_path=tmp_path / "priority0-gap-taxonomy.json",
        )
    )

    assert report["status"] == "failed"
    assert any("comparison artifact is required" in error for error in report["errors"])  # type: ignore[index]


def test_priority0_gap_taxonomy_allows_missing_artifacts_only_when_explicit(tmp_path: Path) -> None:
    corpus = copy.deepcopy(load_project_corpus())
    comparison = first_entry(corpus)["comparison"]  # type: ignore[index]
    comparison["path"] = "runtime-state/missing/does-not-exist.json"  # type: ignore[index]

    report = run_report(tmp_path, corpus, require_artifacts=False)

    assert report["status"] == "passed"
    assert report["summary"]["comparison_count"] == 5  # type: ignore[index]


def test_priority0_gap_taxonomy_rejects_summary_only_comparison_miss(tmp_path: Path) -> None:
    corpus = load_project_corpus()
    entry = first_entry(corpus)
    comparison_path = REPO_ROOT / entry["comparison"]["path"]  # type: ignore[index]
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    comparison["status"] = "passed"
    comparison["passed_response_count"] = comparison["response_count"]
    comparison["critical_finding_count"] = 1
    comparison["high_finding_count"] = 1
    comparison["gap_categories"] = {"evidence": 1}
    for case in comparison["cases"]:
        for route in case["routes"]:
            route["pass"] = True
            route["score"] = max(route["score"], 90)
            route["unresolved_findings"] = []
    mutated_comparison_path = write_json(tmp_path / "summary-comparison.json", comparison)
    comparison_ref = entry["comparison"]  # type: ignore[index]
    comparison_ref["path"] = str(mutated_comparison_path)  # type: ignore[index]
    comparison_ref["sha256"] = sha256_file(mutated_comparison_path)  # type: ignore[index]

    report = run_report(tmp_path, corpus)

    assert report["status"] == "failed"
    assert report["summary"]["gap_class_counts"]["context_gathering"] == 1  # type: ignore[index]
