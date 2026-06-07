from __future__ import annotations

import json
from pathlib import Path

from vllm_agent_gateway.acceptance.semi_well_defined_prompts import (
    DEFAULT_CATALOG_PATH,
    DEFAULT_MANIFEST_PATH,
    DEFAULT_POLICY_PATH,
    build_offline_report,
    evaluate_route,
    evaluate_text,
    fixture_entries,
    load_fixture_manifest,
    load_prompt_catalog,
    prompt_cases_from_catalog,
    validate_catalog_contract,
)
from vllm_agent_gateway.prompt_catalogs import DEFAULT_FOUNDER_FIELD_CATALOG


REPO_ROOT = Path(__file__).resolve().parents[2]


def default_entries():
    manifest = load_fixture_manifest(REPO_ROOT, DEFAULT_MANIFEST_PATH)
    return fixture_entries(REPO_ROOT, manifest)


def test_phase110_semi_well_defined_catalog_routes_and_boundaries_pass() -> None:
    report = build_offline_report(
        config_root=REPO_ROOT,
        catalog_path=DEFAULT_CATALOG_PATH,
        manifest_path=DEFAULT_MANIFEST_PATH,
        policy_path=DEFAULT_POLICY_PATH,
    )

    assert report["status"] == "passed"
    assert report["summary"]["catalog_case_count"] == 24
    assert report["summary"]["route_passed"] == 24
    assert report["summary"]["boundary_passed"] == 2
    assert {"coinbase-frozen", "coinbase-frozen-git"} <= set(report["summary"]["fixture_ids"])
    assert {
        "python-service-generalization",
        "node-cli-generalization",
        "go-http-generalization",
    } <= set(report["summary"]["fixture_ids"])


def test_phase110_catalog_rejects_internal_workflow_terms(tmp_path: Path) -> None:
    catalog = load_prompt_catalog(REPO_ROOT, DEFAULT_CATALOG_PATH)
    catalog["cases"][0]["prompt"] += " Use workflow_router.plan."
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")
    loaded = load_prompt_catalog(REPO_ROOT, path)
    cases = prompt_cases_from_catalog(loaded)

    errors = validate_catalog_contract(
        config_root=REPO_ROOT,
        catalog=loaded,
        cases=cases,
        entries=default_entries(),
    )

    assert any("prompt contains internal workflow/tool terms" in error for error in errors)


def test_phase110_catalog_rejects_exact_founder_prompt_copy(tmp_path: Path) -> None:
    catalog = load_prompt_catalog(REPO_ROOT, DEFAULT_CATALOG_PATH)
    founder = load_prompt_catalog(REPO_ROOT, DEFAULT_FOUNDER_FIELD_CATALOG)
    catalog["cases"][0]["prompt"] = founder["cases"][0]["prompt"]
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")
    loaded = load_prompt_catalog(REPO_ROOT, path)
    cases = prompt_cases_from_catalog(loaded)

    errors = validate_catalog_contract(
        config_root=REPO_ROOT,
        catalog=loaded,
        cases=cases,
        entries=default_entries(),
    )

    assert any("prompt must not be an exact copy of a founder-field prompt" in error for error in errors)


def test_phase110_boundary_case_must_fail_closed(tmp_path: Path) -> None:
    catalog = load_prompt_catalog(REPO_ROOT, DEFAULT_CATALOG_PATH)
    catalog["boundary_cases"][0]["expected_status_reason"] = "ready"
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")

    report = build_offline_report(
        config_root=REPO_ROOT,
        catalog_path=path,
        manifest_path=DEFAULT_MANIFEST_PATH,
        policy_path=DEFAULT_POLICY_PATH,
    )

    assert report["status"] == "failed"
    assert report["summary"]["boundary_failed"] == 1
    assert any("status_reason expected ready got blocked_approval_bypass" in error for error in report["errors"])


def test_phase110_prompt_suggestion_does_not_turn_miss_into_pass() -> None:
    catalog = load_prompt_catalog(REPO_ROOT, DEFAULT_CATALOG_PATH)
    case = prompt_cases_from_catalog(catalog)[0]
    route = evaluate_route(case)
    text = "\n".join(
        (
            "I completed workflow_router.plan.",
            "workflow_router.plan completed",
            "run_id: workflow-router-unit",
            "Result:",
            "- Selected workflow: code_investigation.plan",
            "- Selected skills: none",
            "- Selected tools: none",
            "- Next action: none",
            "- Verification: none",
            "Skill Selection:",
            "- Route rules: l1_find_behavior_start_terms",
            "Artifacts:",
            "- downstream_investigation_plan: /tmp/plan.json",
            "Answer:",
        )
    )

    result = evaluate_text(
        case=case,
        text=text,
        route_result=route,
        common_markers=tuple(catalog["common_format_a_markers"]),
        policy=json.loads((REPO_ROOT / DEFAULT_POLICY_PATH).read_text(encoding="utf-8")),
    )

    assert result["status"] == "failed"
    assert result["suggested_prompt_if_missed"]
    assert result["missing_semantic_markers"]
