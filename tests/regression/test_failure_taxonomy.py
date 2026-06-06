from __future__ import annotations

import json
from pathlib import Path

from vllm_agent_gateway.acceptance.failure_taxonomy import FailureTaxonomyConfig, run_failure_taxonomy


def write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def categories(report: dict[str, object]) -> set[str]:
    findings = report.get("findings")
    assert isinstance(findings, list)
    return {str(item.get("category")) for item in findings if isinstance(item, dict)}


def run_report(tmp_path: Path, *reports: Path) -> dict[str, object]:
    return run_failure_taxonomy(
        FailureTaxonomyConfig(
            config_root=tmp_path,
            report_paths=tuple(reports),
            labels=tuple(path.stem for path in reports),
            output_path=tmp_path / "taxonomy.json",
            markdown_output_path=tmp_path / "taxonomy.md",
        )
    )


def test_failure_taxonomy_classifies_founder_field_misses(tmp_path: Path) -> None:
    founder = write_json(
        tmp_path / "founder.json",
        {
            "kind": "founder_field_prompt_evaluation",
            "status": "failed",
            "fixture_state_before": {"/mnt/c/example": {"hashes": {"a.py": "before"}}},
            "fixture_state_after": {"/mnt/c/example": {"hashes": {"a.py": "after"}}},
            "cases": [
                {
                    "case_id": "P01",
                    "status": "failed",
                    "output_contract_status": "failed",
                    "missing_markers": ["selected_workflow: code-context.plan"],
                    "expected_workflow": "code-context.plan",
                    "prompt_risk": "Ambiguous request needs a target file.",
                    "refined_prompt": "Explain foo in app.py.",
                },
                {
                    "case_id": "P02",
                    "status": "failed",
                    "output_contract_status": "failed",
                    "missing_markers": ["Answer:"],
                    "semantic_quality_status": "failed",
                    "missing_semantic_markers": ["source refs", "related tests"],
                },
            ],
        },
    )

    report = run_report(tmp_path, founder)

    assert report["status"] == "passed"
    assert {
        "routing_miss",
        "output_contract_miss",
        "semantic_miss",
        "prompt_ambiguity",
        "fixture_mutation",
    }.issubset(categories(report))
    assert Path(report["report_path"]).exists()
    assert (tmp_path / "taxonomy.md").read_text(encoding="utf-8").startswith("# Failure Taxonomy Report")


def test_failure_taxonomy_classifies_v1_health_preflight_and_suite_failures(tmp_path: Path) -> None:
    v1 = write_json(
        tmp_path / "v1.json",
        {
            "kind": "v1_acceptance_report",
            "status": "failed",
            "errors": ["RuntimeError: changed protected fixture state"],
            "health": [
                {
                    "name": "workflow-router",
                    "status": "failed",
                    "http_status": 200,
                    "error": "Timed out waiting for body bytes.",
                }
            ],
            "anythingllm_preflight": {"status": "failed", "error": "workspace not found"},
            "suite_runs": [
                {
                    "id": "approval",
                    "status": "failed",
                    "stdout_tail": "approval boundary was bypassed",
                    "stderr_tail": "",
                }
            ],
        },
    )

    report = run_report(tmp_path, v1)

    assert {"fixture_mutation", "model_timeout", "anythingllm_config_error", "approval_boundary_miss"}.issubset(
        categories(report)
    )
    assert report["summary"]["highest_severity"] == "critical"


def test_failure_taxonomy_classifies_model_portability_failures(tmp_path: Path) -> None:
    portability = write_json(
        tmp_path / "portability.json",
        {
            "kind": "model_portability_report",
            "status": "failed",
            "classified_failures": [
                {"classification": "classifier", "message": "selected wrong workflow", "source": "route"},
                {"classification": "prompt", "message": "prompt_risk: missing file path", "source": "prompt"},
                {"classification": "model_quality", "message": "not valid json schema", "source": "model"},
                {"classification": "harness", "message": "read timed out", "source": "health"},
            ],
            "classification_summary": {"classifier": 1, "prompt": 1, "model_quality": 1, "harness": 1},
        },
    )

    report = run_report(tmp_path, portability)

    assert {"routing_miss", "prompt_ambiguity", "model_quality", "model_timeout"}.issubset(categories(report))


def test_failure_taxonomy_classifies_run_artifact_diff_deltas(tmp_path: Path) -> None:
    diff = write_json(
        tmp_path / "diff.json",
        {
            "kind": "run_artifact_diff",
            "status": "passed",
            "diff": {
                "fixture_state_changes": [{"target_root": "/mnt/c/example"}],
                "semantic_miss_changes": {"added": ["P01"]},
                "output_miss_changes": {"added": ["P02"]},
                "route_rule_changes": {"changed_count": 1},
                "classification_summary_delta": {"model_quality": {"left": 0, "right": 1, "delta": 1}},
            },
        },
    )

    report = run_report(tmp_path, diff)

    assert {"fixture_mutation", "semantic_miss", "output_contract_miss", "routing_miss", "model_quality"}.issubset(
        categories(report)
    )


def test_failure_taxonomy_passes_clean_realistic_report(tmp_path: Path) -> None:
    clean = write_json(
        tmp_path / "clean.json",
        {
            "kind": "v1_acceptance_report",
            "status": "passed",
            "errors": [],
            "health": [{"name": "model", "status": "passed", "http_status": 200}],
            "suite_runs": [{"id": "founder_field_prompts", "status": "passed"}],
            "anythingllm_preflight": {"status": "passed"},
            "founder_field_summary": {"status": "passed", "summary": {"passed": 1, "failed": 0}, "errors": []},
        },
    )

    report = run_report(tmp_path, clean)

    assert report["status"] == "passed"
    assert report["summary"]["finding_count"] == 0
    assert report["summary"]["highest_severity"] == "none"
