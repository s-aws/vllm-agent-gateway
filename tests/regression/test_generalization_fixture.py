from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from vllm_agent_gateway.controllers.code_investigation.plan import (
    CodeInvestigationRequest,
    data_model_target_from_request,
    is_endpoint_route_lookup_request,
    is_table_read_write_lookup_request,
    query_candidates,
    table_schema_fields,
)
from vllm_agent_gateway.controllers.natural_query import change_subject_queries_from_request
from vllm_agent_gateway.controllers.workflow_router.plan import (
    apply_router_rule_skill_overrides,
    extract_queries,
    is_l1_endpoint_route_lookup_request,
    is_l2_table_read_write_lookup_request,
    workflow_kind_for_request,
)
from vllm_agent_gateway.skills.registry import load_skill_registry


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_generalization_fixture_live.py"
TEMPLATE_ROOT = REPO_ROOT / "tests" / "fixtures" / "generalization" / "python_service_fixture"


def load_module():
    spec = importlib.util.spec_from_file_location("validate_generalization_fixture_live", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_phase66_generalization_case_catalog_covers_required_prompt_kinds() -> None:
    module = load_module()

    cases = module.GENERALIZATION_CASES
    by_id = {case.case_id: case for case in cases}

    assert set(by_id) == {"G01", "G02", "G03", "G04", "G05", "G06"}
    assert by_id["G01"].category == "l1_explain_code"
    assert by_id["G06"].category == "l2_test_selection"
    assert {by_id[key].expected_skill_id for key in ("G02", "G03", "G04", "G05")} == {
        "handler-branch-tracer",
        "table-schema-isolator",
        "runtime-entrypoint-disambiguator",
        "change-boundary-summarizer",
    }
    assert all(case.expected_artifact_key.startswith("downstream_") for case in cases)


def test_phase66_generalization_fixture_copy_and_cleanup(tmp_path: Path) -> None:
    module = load_module()
    before = module.hash_tree(TEMPLATE_ROOT)

    copied = module.copy_disposable_fixture(TEMPLATE_ROOT, tmp_path, run_id="unit-copy")
    copied_hashes = module.hash_tree(copied)
    removed = module.remove_fixture(copied.parent)

    assert copied_hashes == before
    assert removed
    assert not copied.parent.exists()
    assert module.hash_tree(TEMPLATE_ROOT) == before


def test_data_model_target_prefers_schema_subject_over_target_root_path() -> None:
    prompt = (
        "In /mnt/c/agentic_agents/runtime-state/generalization-fixtures/tmp/python_service_fixture, "
        "find the orders table schema only. Read only. Return schema field names."
    )

    assert data_model_target_from_request(prompt, ["agentic_agents"], "find orders table schema only") == "orders"


def test_data_model_target_extracts_schema_fields_for_subject() -> None:
    prompt = (
        "In C:/tmp/repo, find the database schema fields for stealth_orders. "
        "Read only. Return model files, fields, and source refs."
    )

    assert data_model_target_from_request(prompt, ["agentic_agents"], "find database schema fields") == "stealth_orders"


def test_generalization_fixture_schema_fields_are_extractable() -> None:
    fields = table_schema_fields(TEMPLATE_ROOT, "database/schema.py", "orders")

    assert {field["name"] for field in fields} == {"id", "status", "item_count", "created_at"}


def test_runtime_entrypoint_prompt_does_not_trigger_endpoint_route_lookup() -> None:
    prompt = (
        "locate the runtime entrypoint for the order worker, not the request handler. "
        "Read only. Return command, source refs, and exclusions."
    )

    assert not is_l1_endpoint_route_lookup_request(prompt)
    assert not is_endpoint_route_lookup_request(prompt)


def test_change_boundary_prompt_extracts_concrete_behavior_subject() -> None:
    prompt = (
        "In /mnt/c/agentic_agents/runtime-state/generalization-fixtures/tmp/python_service_fixture, "
        "identify files to touch and files not to touch for the minimal safe change surface "
        "and change boundary for order status behavior. Read only and stop before implementation. "
        "Return risks, gaps, and verification commands."
    )

    assert change_subject_queries_from_request(prompt)[:2] == ["order_status", "order status"]
    assert extract_queries(prompt)[:2] == ["order_status", "order status"]

    request = CodeInvestigationRequest(user_request=prompt, behavior="identify files touch files touch minimal")
    assert query_candidates(request, [])[:2] == ["order_status", "order status"]


def test_l2_test_selection_rule_promotes_specific_skill_within_budget() -> None:
    skill_registry = load_skill_registry(REPO_ROOT)
    selected = [
        "request-triage",
        "scope-and-assumptions",
        "entrypoint-finder",
        "context-plan-builder",
        "code-explanation-summarizer",
    ]

    adjusted = apply_router_rule_skill_overrides(
        selected,
        workflow_id="code_investigation.plan",
        skill_registry=skill_registry,
        route_evidence=[{"source": "router_rule", "rule": "l2_test_selection_terms"}],
        limit=5,
    )

    assert adjusted == [
        "request-triage",
        "scope-and-assumptions",
        "entrypoint-finder",
        "context-plan-builder",
        "test-selection-rationale",
    ]


def test_table_read_write_natural_definition_reads_writes_phrase_routes() -> None:
    prompt = (
        "In C:/tmp/go_http_fixture, locate the orders table definition, reads, and writes. "
        "Read only. Return definition sites, read sites, write sites, source refs, gaps, and mutation policy."
    )

    workflow_id, status, evidence = workflow_kind_for_request(prompt)

    assert is_l2_table_read_write_lookup_request(prompt)
    assert is_table_read_write_lookup_request(prompt)
    assert workflow_id == "code_investigation.plan"
    assert status == "ready"
    assert any(item.get("rule") == "l2_table_read_write_lookup_terms" for item in evidence)


def test_feedback_term_inside_target_path_does_not_trigger_feedback_route() -> None:
    workflow_id, status, evidence = workflow_kind_for_request(
        "In C:/tmp/phase67-feedback-target, explain what resolve_order_status does. "
        "Read only. Include inputs, outputs, side effects, and tests."
    )

    assert workflow_id == "code_investigation.plan"
    assert status == "ready"
    assert not any(item.get("rule") == "feedback_terms" for item in evidence)


def test_windows_target_path_action_terms_do_not_block_l1_routes() -> None:
    coverage_workflow, coverage_status, coverage_evidence = workflow_kind_for_request(
        r"In C:\tmp\test_workflow_router_chat_l1_coverage_gap_summary_returns_artifact-add3\allowed\repo, "
        "identify test coverage gaps for placed_order_id stealth lookup. Read only. "
        "Return covered tests, uncovered source files, verification commands, and gaps."
    )
    cli_workflow, cli_status, cli_evidence = workflow_kind_for_request(
        r"In C:\tmp\test_workflow_router_chat_l1_cli_entrypoint_lookup_returns_artifact-refactor\allowed\repo, "
        "locate the CLI/script entrypoint main.py for running the trading engine. Read only. "
        "Return entrypoint files, command, and source refs."
    )

    assert coverage_workflow == "code_investigation.plan"
    assert coverage_status == "ready"
    assert any(item.get("rule") == "l1_coverage_gap_summary_terms" for item in coverage_evidence)
    assert cli_workflow == "code_investigation.plan"
    assert cli_status == "ready"
    assert any(item.get("rule") == "l1_cli_entrypoint_lookup_terms" for item in cli_evidence)
