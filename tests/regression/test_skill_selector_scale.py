from __future__ import annotations

from pathlib import Path
from time import perf_counter

from vllm_agent_gateway.skills.registry import explain_skill_selection_for_workflow
from vllm_agent_gateway.skills.selector_scale import (
    build_synthetic_catalog,
    build_skill_selector_scale_report,
    catalog_issue_summary,
    run_negative_fixtures,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_skill_selector_scale_report_is_stable_and_metadata_only(tmp_path: Path, monkeypatch) -> None:
    def fail_read_text(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise AssertionError(f"selector scale benchmark attempted to read a file body: {self}")

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    report = build_skill_selector_scale_report(
        REPO_ROOT,
        output_path=tmp_path / "selector-scale.json",
        skill_counts=(100, 1_000),
        repetitions=3,
        threshold_10000_seconds=10.0,
    )

    assert report["status"] == "passed"
    assert report["summary"]["largest_skill_count"] == 1_000
    assert report["summary"]["body_reads_during_selection"] == 0
    assert report["summary"]["negative_fixture_rejected_count"] == 5
    assert (tmp_path / "selector-scale.json").exists()
    for benchmark in report["benchmarks"]:
        assert benchmark["catalog_analysis"]["status"] == "passed"
        assert benchmark["selection_benchmark"]["status"] == "passed"
        for result in benchmark["selection_benchmark"]["representative_results"]:
            assert result["stable"] is True
            assert result["expected_selected"] is True


def test_skill_selector_scale_negative_fixtures_fail_deterministically() -> None:
    expected_errors = {
        "duplicate_route_key": "duplicate_route_keys",
        "unsupported_namespace": "unsupported_route_namespaces",
        "trigger_collision": "trigger_collisions",
        "semantic_overlap": "semantic_overlaps",
        "missing_eval_case": "missing_eval_cases",
    }

    results = {item["id"]: item for item in run_negative_fixtures()}

    assert set(results) == set(expected_errors)
    for fixture_id, expected_error in expected_errors.items():
        assert results[fixture_id]["status"] == "rejected"
        assert expected_error in results[fixture_id]["detected_errors"]


def test_catalog_issue_summary_reports_route_namespace_saturation() -> None:
    skills = {
        "one": {
            "id": "one",
            "workflows": ["code_context.lookup"],
            "triggers": ["phase41 one trigger"],
            "capability_contract": {
                "route_key": "code.one",
                "task_types": ["phase41_one"],
                "output_artifacts": ["phase41_one"],
                "mutation_policy": "no_repository_mutation",
                "eval_case_ids": ["phase41_one"],
            },
        },
        "two": {
            "id": "two",
            "workflows": ["code_context.lookup"],
            "triggers": ["phase41 two trigger"],
            "capability_contract": {
                "route_key": "docs.two",
                "task_types": ["phase41_two"],
                "output_artifacts": ["phase41_two"],
                "mutation_policy": "no_repository_mutation",
                "eval_case_ids": ["phase41_two"],
            },
        },
    }
    eval_cases = [
        {"id": "phase41_one", "prompt_family": "phase41-one"},
        {"id": "phase41_two", "prompt_family": "phase41-two"},
    ]

    summary = catalog_issue_summary(skills, eval_cases)

    assert summary["status"] == "passed"
    assert summary["route_namespace_saturation"] == {"code": 1, "docs": 1}


def test_skill_selection_explanation_scales_to_10000_metadata_entries() -> None:
    skills, _eval_cases = build_synthetic_catalog(10_000)

    started = perf_counter()
    explanation = explain_skill_selection_for_workflow(
        skills,
        "code_investigation.plan",
        query_text="In the repo, phase41 explain code behavior for the selected function.",
        limit=5,
    )
    elapsed = perf_counter() - started

    assert elapsed < 10.0
    assert explanation["body_reads_during_selection"] == 0
    assert "phase41-target-explain-code" in explanation["selected_skill_ids"]
    selected = {item["skill_id"]: item for item in explanation["selected"]}
    assert selected["phase41-target-explain-code"]["route_key"] == "code.phase41_explain_code"
