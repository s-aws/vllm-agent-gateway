from __future__ import annotations

import copy
import uuid
from pathlib import Path
from typing import Any

import pytest

from vllm_agent_gateway.acceptance.fresh_local_model_drift import (
    EXPECTED_OUTPUT_ROOT,
    FreshLocalModelDriftStatus,
    artifact_hash,
    expected_case_targets_for_family,
    read_json_object,
    source_hashes_for_family,
    validate_fresh_local_model_drift_catalog,
    validate_fresh_local_model_drift_report,
    write_json,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO_ROOT / "runtime" / "fresh_local_model_drift_cases.json"
CORPUS_PATH = REPO_ROOT / "runtime" / "baseline_corpus.json"


def project_catalog() -> dict[str, Any]:
    return read_json_object(CATALOG_PATH)


def project_corpus() -> dict[str, Any]:
    return read_json_object(CORPUS_PATH)


def stable_entries(corpus: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(entry["entry_id"]): entry
        for entry in corpus["entries"]
        if isinstance(entry, dict) and entry.get("status") == "stable"
    }


def write_family_artifacts(
    *,
    catalog: dict[str, Any],
    family: dict[str, Any],
    corpus_entry: dict[str, Any],
    score: int | None = None,
    route_override: list[str] | None = None,
    mutation: bool = False,
) -> None:
    routes = route_override or ["anythingllm", "gateway"]
    case_ids = list(family["case_ids"])
    case_targets = expected_case_targets_for_family(REPO_ROOT, family)
    target_roots = sorted(set(case_targets.values()))
    responses = {
        route: {
            "status": "captured",
            "http_status": 200,
            "route_summary": {"selected_workflow": "code_investigation.plan", "run_id": f"test-{route}"},
            "text": "workflow_router.plan completed\nResult:\nEvidence-backed answer\nSource mutation: false",
        }
        for route in routes
    }
    local_eval = {
        "kind": f"{family['family_id']}_local_eval",
        "schema_version": 1,
        "status": "captured",
        "priority_backlog_id": family["priority_backlog_id"],
        "case_count": len(case_ids),
        "target_roots": target_roots,
        "runtime_changed_files": ["runtime/baseline_corpus.json"] if mutation else [],
        "target_changed_files": {},
        "target_git_changed": {},
        "checks": {
            "cases": [
                {
                    "case_id": case_id,
                    "case_type": "test",
                    "holdout": False,
                    "target_root": case_targets[case_id],
                    "responses": copy.deepcopy(responses),
                }
                for case_id in case_ids
            ]
        },
    }
    route_score = score if isinstance(score, int) else int(corpus_entry["comparison"]["minimum_route_score"])
    comparison = {
        "kind": f"{family['family_id']}_comparison",
        "schema_version": 1,
        "status": "passed",
        "priority_backlog_id": family["priority_backlog_id"],
        "response_count": len(case_ids) * len(routes),
        "passed_response_count": len(case_ids) * len(routes),
        "critical_finding_count": 0,
        "high_finding_count": 0,
        "gap_categories": {},
        "recommended_next_repairs": [],
        "cases": [
            {
                "case_id": case_id,
                "case_type": "test",
                "holdout": False,
                "target_root": case_targets[case_id],
                "routes": [
                    {
                        "route": route,
                        "selected_workflow": "code_investigation.plan",
                        "score": route_score,
                        "pass": True,
                        "unresolved_findings": [],
                    }
                    for route in routes
                ],
            }
            for case_id in case_ids
        ],
    }
    write_json(REPO_ROOT / family["fresh_local_eval_path"], local_eval)
    write_json(REPO_ROOT / family["fresh_comparison_path"], comparison)


def fresh_catalog_and_report() -> tuple[dict[str, Any], dict[str, Any]]:
    token = uuid.uuid4().hex
    catalog = copy.deepcopy(project_catalog())
    corpus = project_corpus()
    entries = stable_entries(corpus)
    families: list[dict[str, Any]] = []
    minimum_scores: dict[str, int] = {}
    for family in catalog["families"]:
        family["fresh_local_eval_path"] = (
            f"{EXPECTED_OUTPUT_ROOT}/test-{token}-{family['family_id']}-local-eval.json"
        )
        family["fresh_comparison_path"] = (
            f"{EXPECTED_OUTPUT_ROOT}/test-{token}-{family['family_id']}-comparison.json"
        )
        entry = entries[family["family_id"]]
        write_family_artifacts(catalog=catalog, family=family, corpus_entry=entry)
        local_path = REPO_ROOT / family["fresh_local_eval_path"]
        comparison_path = REPO_ROOT / family["fresh_comparison_path"]
        min_score = int(entry["comparison"]["minimum_route_score"])
        minimum_scores[family["family_id"]] = min_score
        target_roots = sorted(set(expected_case_targets_for_family(REPO_ROOT, family).values()))
        families.append(
            {
                "family_id": family["family_id"],
                "priority_backlog_id": family["priority_backlog_id"],
                "status": "passed",
                "case_ids": list(family["case_ids"]),
                "target_roots": target_roots,
                "required_routes": ["anythingllm", "gateway"],
                "fresh_local_eval_path": family["fresh_local_eval_path"],
                "fresh_local_eval_sha256": artifact_hash(local_path),
                "fresh_comparison_path": family["fresh_comparison_path"],
                "fresh_comparison_sha256": artifact_hash(comparison_path),
                "source_hashes": source_hashes_for_family(REPO_ROOT, family),
                "commands": {
                    "local_eval": {"argv": ["python", "runner"], "returncode": 0, "duration_seconds": 0.1},
                    "comparison": {"argv": ["python", "comparator"], "returncode": 0, "duration_seconds": 0.1},
                },
                "comparison": {
                    "status": "passed",
                    "response_count": len(family["case_ids"]) * 2,
                    "passed_response_count": len(family["case_ids"]) * 2,
                    "critical_finding_count": 0,
                    "high_finding_count": 0,
                    "gap_categories": {},
                    "recommended_next_repairs": [],
                },
                "local_eval_summary": {
                    "status": "captured",
                    "case_count": len(family["case_ids"]),
                    "target_roots": target_roots,
                    "runtime_changed_files": [],
                    "target_changed_files": {},
                    "target_git_changed": {},
                },
                "minimum_route_score": min_score,
                "prior_minimum_route_score": min_score,
                "drift_severity": "none",
                "next_action": "none",
            }
        )
    report = {
        "schema_version": 1,
        "kind": "fresh_local_model_drift_report",
        "phase": 127,
        "priority_backlog_id": "P0-BB-012",
        "status": "passed",
        "families": families,
        "summary": {
            "family_count": 4,
            "selected_case_count": 8,
            "response_count": 16,
            "passed_response_count": 16,
            "failed_family_count": 0,
            "critical_finding_count": 0,
            "high_finding_count": 0,
            "gap_categories": {},
            "required_routes": ["anythingllm", "gateway"],
            "target_roots": [
                "/mnt/c/coinbase_testing_repo_frozen_tmp",
                "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
            ],
            "minimum_route_scores": minimum_scores,
            "drift_status": "no_drift_detected",
        },
        "errors": [],
    }
    return catalog, report


def test_project_fresh_local_model_drift_catalog_passes() -> None:
    errors = validate_fresh_local_model_drift_catalog(
        project_catalog(),
        config_root=REPO_ROOT,
        baseline_corpus=project_corpus(),
        require_baseline_artifacts=False,
    )
    assert errors == []


def test_catalog_rejects_missing_family() -> None:
    catalog = project_catalog()
    catalog["families"] = catalog["families"][:-1]
    errors = validate_fresh_local_model_drift_catalog(catalog, config_root=REPO_ROOT, baseline_corpus=project_corpus())
    assert any("exactly cover stable Phase 116-119" in error for error in errors)


def test_catalog_rejects_missing_frozen_root_coverage() -> None:
    catalog = project_catalog()
    catalog["families"][0]["case_ids"] = ["CQ116-001", "CQ116-007"]
    catalog["families"][0]["expected_response_count"] = 4
    errors = validate_fresh_local_model_drift_catalog(catalog, config_root=REPO_ROOT, baseline_corpus=project_corpus())
    assert any("cover exactly both frozen Coinbase target roots" in error for error in errors)


def test_catalog_rejects_stale_baseline_source_hash() -> None:
    corpus = project_corpus()
    corpus["entries"][0]["prompt_cases"]["sha256"] = "0" * 64
    errors = validate_fresh_local_model_drift_catalog(project_catalog(), config_root=REPO_ROOT, baseline_corpus=corpus)
    assert any("baseline_corpus:" in error and "sha256 is stale" in error for error in errors)


def test_catalog_rejects_overwriting_accepted_artifact_path() -> None:
    catalog = project_catalog()
    corpus = project_corpus()
    accepted_path = corpus["entries"][0]["local_eval"]["path"]
    catalog["families"][0]["fresh_local_eval_path"] = accepted_path
    errors = validate_fresh_local_model_drift_catalog(catalog, config_root=REPO_ROOT, baseline_corpus=corpus)
    assert any("must not overwrite accepted baseline corpus artifacts" in error for error in errors)


@pytest.mark.requires_baseline_artifacts
def test_report_accepts_fresh_passed_artifacts() -> None:
    catalog, report = fresh_catalog_and_report()
    errors = validate_fresh_local_model_drift_report(
        report,
        catalog=catalog,
        baseline_corpus=project_corpus(),
        config_root=REPO_ROOT,
        require_artifacts=True,
    )
    assert errors == []


def test_report_rejects_missing_route() -> None:
    catalog, report = fresh_catalog_and_report()
    corpus = project_corpus()
    family = catalog["families"][0]
    entry = stable_entries(corpus)[family["family_id"]]
    write_family_artifacts(catalog=catalog, family=family, corpus_entry=entry, route_override=["gateway"])
    report["families"][0]["fresh_local_eval_sha256"] = artifact_hash(REPO_ROOT / family["fresh_local_eval_path"])
    report["families"][0]["fresh_comparison_sha256"] = artifact_hash(REPO_ROOT / family["fresh_comparison_path"])
    report["status"] = "failed"
    errors = validate_fresh_local_model_drift_report(
        report,
        catalog=catalog,
        baseline_corpus=corpus,
        config_root=REPO_ROOT,
        require_artifacts=True,
    )
    assert any("responses must exactly include gateway and anythingllm" in error for error in errors)
    assert any("routes must exactly include gateway and anythingllm" in error for error in errors)


def test_report_rejects_score_regression_against_prior() -> None:
    catalog, report = fresh_catalog_and_report()
    corpus = project_corpus()
    family = catalog["families"][0]
    entry = stable_entries(corpus)[family["family_id"]]
    prior_min = int(entry["comparison"]["minimum_route_score"])
    write_family_artifacts(catalog=catalog, family=family, corpus_entry=entry, score=prior_min - 1)
    report["families"][0]["fresh_local_eval_sha256"] = artifact_hash(REPO_ROOT / family["fresh_local_eval_path"])
    report["families"][0]["fresh_comparison_sha256"] = artifact_hash(REPO_ROOT / family["fresh_comparison_path"])
    report["families"][0]["minimum_route_score"] = prior_min - 1
    report["families"][0]["drift_severity"] = "watch"
    report["families"][0]["status"] = "failed"
    report["summary"]["minimum_route_scores"][family["family_id"]] = prior_min - 1
    report["summary"]["failed_family_count"] = 1
    report["summary"]["drift_status"] = "drift_detected"
    report["status"] = "failed"
    errors = validate_fresh_local_model_drift_report(
        report,
        catalog=catalog,
        baseline_corpus=corpus,
        config_root=REPO_ROOT,
        require_artifacts=True,
    )
    assert any("minimum_route_score regressed below prior accepted result" in error for error in errors)


def test_report_rejects_stale_artifact_hash() -> None:
    catalog, report = fresh_catalog_and_report()
    report["families"][0]["fresh_comparison_sha256"] = "0" * 64
    report["status"] = "failed"
    errors = validate_fresh_local_model_drift_report(
        report,
        catalog=catalog,
        baseline_corpus=project_corpus(),
        config_root=REPO_ROOT,
        require_artifacts=True,
    )
    assert any("fresh_comparison_sha256 is stale or missing" in error for error in errors)


def test_report_rejects_mutation_proof() -> None:
    catalog, report = fresh_catalog_and_report()
    corpus = project_corpus()
    family = catalog["families"][0]
    entry = stable_entries(corpus)[family["family_id"]]
    write_family_artifacts(catalog=catalog, family=family, corpus_entry=entry, mutation=True)
    report["families"][0]["fresh_local_eval_sha256"] = artifact_hash(REPO_ROOT / family["fresh_local_eval_path"])
    report["families"][0]["fresh_comparison_sha256"] = artifact_hash(REPO_ROOT / family["fresh_comparison_path"])
    report["status"] = "failed"
    errors = validate_fresh_local_model_drift_report(
        report,
        catalog=catalog,
        baseline_corpus=corpus,
        config_root=REPO_ROOT,
        require_artifacts=True,
    )
    assert any("runtime_changed_files must be empty" in error for error in errors)


def test_report_rejects_nonzero_command_result() -> None:
    catalog, report = fresh_catalog_and_report()
    report["families"][0]["commands"]["local_eval"]["returncode"] = 2
    report["families"][0]["status"] = "failed"
    report["summary"]["failed_family_count"] = 1
    report["summary"]["drift_status"] = "drift_detected"
    report["status"] = "failed"
    errors = validate_fresh_local_model_drift_report(
        report,
        catalog=catalog,
        baseline_corpus=project_corpus(),
        config_root=REPO_ROOT,
        require_artifacts=True,
    )
    assert any("commands.local_eval.returncode must be 0" in error for error in errors)
