from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from vllm_agent_gateway.prompt_catalogs import (
    load_prompt_catalog,
    prompt_cases_from_catalog,
    validate_prompt_catalog,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_founder_field_prompt_eval.py"
MATRIX_SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_founder_field_prompt_matrix.py"
CATALOG_PATH = REPO_ROOT / "runtime" / "prompt_catalogs" / "founder_field_v1.json"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("run_founder_field_prompt_eval", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_matrix_module():
    spec = importlib.util.spec_from_file_location("validate_founder_field_prompt_matrix", MATRIX_SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_founder_field_prompt_catalog_is_bounded_and_unique() -> None:
    module = load_runner_module()

    cases = module.FIELD_PROMPTS
    case_ids = [case.case_id for case in cases]

    assert len(cases) == 34
    assert len(case_ids) == len(set(case_ids))
    assert case_ids[0] == "P01"
    assert case_ids[-1] == "P34"


def test_founder_field_prompt_catalog_fixture_is_governed() -> None:
    catalog = load_prompt_catalog(REPO_ROOT, CATALOG_PATH)

    assert validate_prompt_catalog(catalog) == []
    assert catalog["catalog_id"] == "founder_field_v1"
    assert catalog["version"] == "1.0.0"
    assert catalog["change_history"]

    cases = prompt_cases_from_catalog(catalog)
    assert len(cases) == 34
    assert all(case.expected_rule for case in cases)
    assert all(case.semantic_markers for case in cases)
    assert all(case.forbidden_markers for case in cases)
    assert all(case.tags for case in cases)
    assert all(raw_case["change_history"] for raw_case in catalog["cases"])


def test_prompt_catalog_validator_detects_duplicate_case_ids() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    catalog["cases"][1]["case_id"] = catalog["cases"][0]["case_id"]

    problems = validate_prompt_catalog(catalog)

    assert any("duplicate case_id P01" in problem for problem in problems)


def test_founder_field_prompt_catalog_has_baselines_and_target_roots() -> None:
    module = load_runner_module()

    allowed_workflows = {
        "code_context.lookup",
        "code_investigation.plan",
        "execution_planning.plan",
        "task.decompose",
    }
    for case in module.FIELD_PROMPTS:
        assert case.prompt
        assert case.baseline_target
        assert case.expected_workflow in allowed_workflows
        assert case.expected_markers
        assert case.miss_suggestion
        assert case.target_root in case.prompt
    batch_d_cases = {case.case_id: case for case in module.FIELD_PROMPTS if case.case_id >= "P27"}
    assert len(batch_d_cases) == 8
    assert {case.expected_skill_id for case in batch_d_cases.values()} == {
        "handler-branch-tracer",
        "table-schema-isolator",
        "runtime-entrypoint-disambiguator",
        "change-boundary-summarizer",
    }
    assert all(case.expected_artifact_key.startswith("downstream_") for case in batch_d_cases.values())


def test_founder_field_prompt_evaluator_reports_missing_markers() -> None:
    module = load_runner_module()
    case = module.FIELD_PROMPTS[0]

    result = module.evaluate_text(case, "workflow_router.plan completed")

    assert result["status"] == "failed"
    assert result["output_contract_status"] == "failed"
    assert result["semantic_quality_status"] == "failed"
    assert result["missing_markers"]
    assert result["suggested_prompt_if_missed"] == module.PROMPT_REFINEMENTS[case.case_id]["refined_prompt"]


def test_founder_field_prompt_evaluator_reports_forbidden_semantic_markers() -> None:
    module = load_runner_module()
    case = module.FIELD_PROMPTS[1]
    text = "\n".join(
        (
            *module.COMMON_FORMAT_A_MARKERS,
            f"selected_workflow: {case.expected_workflow}",
            *case.expected_markers,
            "source_changed: True",
        )
    )

    result = module.evaluate_text(case, text)

    assert result["status"] == "failed"
    assert result["output_contract_status"] == "passed"
    assert result["semantic_quality_status"] == "failed"
    assert "source_changed: True" in result["forbidden_markers_found"]


def test_founder_field_prompt_refinements_cover_known_ambiguity_cases() -> None:
    module = load_runner_module()

    assert set(module.PROMPT_REFINEMENTS) == {
        "P01",
        "P08",
        "P11",
        "P16",
        "P17",
        "P21",
        "P23",
        "P26",
        "P27",
        "P28",
        "P29",
        "P30",
        "P31",
        "P32",
        "P33",
        "P34",
    }
    assert "first source point" in module.PROMPT_REFINEMENTS["P01"]["refined_prompt"]
    assert "approved disposable copy apply only" in module.PROMPT_REFINEMENTS["P26"]["refined_prompt"]
    assert "handler branch trace" in module.PROMPT_REFINEMENTS["P27"]["refined_prompt"]
    assert "change boundary" in module.PROMPT_REFINEMENTS["P34"]["refined_prompt"]


def test_founder_field_prompt_runner_can_select_refined_prompt_variant() -> None:
    module = load_runner_module()
    case = next(item for item in module.FIELD_PROMPTS if item.case_id == "P01")

    class Args:
        use_refined_prompts = True

    assert module.prompt_for_case(Args(), case) == module.PROMPT_REFINEMENTS["P01"]["refined_prompt"]


def test_founder_field_prompt_runner_uses_refined_expectations_when_requested() -> None:
    module = load_runner_module()
    case = next(item for item in module.FIELD_PROMPTS if item.case_id == "P08")

    class Args:
        use_refined_prompts = True

    evaluation_case = module.evaluation_case_for_prompt(Args(), case)

    assert case.expected_rule == "l1_endpoint_route_lookup_terms"
    assert evaluation_case.expected_rule == "l2_request_flow_map_terms"
    assert evaluation_case.expected_skill_id == "handler-branch-tracer"
    assert evaluation_case.expected_artifact_key == "downstream_request_flow_map"
    assert "Source refs:" in evaluation_case.expected_markers
    assert "send_stealth_orders_snapshot" in evaluation_case.semantic_markers


def test_founder_field_prompt_matrix_catalog_routes_without_conflicts() -> None:
    module = load_matrix_module()

    cases = module.catalog_matrix_prompts()
    report = module.build_report(cases, REPO_ROOT)

    assert len(cases) >= 50
    assert report["status"] == "passed"
    assert report["summary"]["failed"] == 0
    assert any(case.case_id == "P01-V1" for case in cases)
    assert any(case.case_id == "P34-V1" for case in cases)


def test_founder_field_prompt_matrix_detects_wrong_expected_rule() -> None:
    module = load_matrix_module()
    case = module.MatrixPrompt(
        case_id="BAD",
        source_case_id="P01",
        variant_kind="fixture",
        prompt=module.VARIANT_PROMPTS[0].prompt,
        expected_workflow="task.decompose",
        expected_rule="task_decomposition_terms",
        note="intentional wrong expectation",
    )

    result = module.evaluate_matrix_prompt(case)

    assert result["status"] == "failed"
    assert result["problems"]
