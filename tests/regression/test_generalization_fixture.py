from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from vllm_agent_gateway.controllers.code_investigation.plan import (
    CodeInvestigationRequest,
    build_table_read_write_lookup,
    data_model_target_from_request,
    evidence_file_records,
    is_endpoint_route_lookup_request,
    is_table_read_write_lookup_request,
    query_candidates,
    request_flow_steps_from_matches,
    table_schema_fields,
)
from vllm_agent_gateway.controllers.natural_query import change_subject_queries_from_request
from vllm_agent_gateway.controllers.workflow_router.plan import (
    apply_router_rule_skill_overrides,
    extract_queries,
    is_l1_endpoint_route_lookup_request,
    is_l2_table_read_write_lookup_request,
    relationship_queries_from_request,
    workflow_kind_for_request,
)
from vllm_agent_gateway.skills.registry import load_skill_registry


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_generalization_fixture_live.py"
TEMPLATE_ROOT = REPO_ROOT / "tests" / "fixtures" / "generalization" / "python_service_fixture"
GO_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "generalization" / "go_http_fixture"


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


def test_configuration_query_extracts_natural_coinbase_api_key_phrase() -> None:
    prompt = (
        "In /mnt/c/coinbase_testing_repo_frozen_tmp, where is the Coinbase API key environment variable used? "
        "Do not edit. Include the files and runtime effect."
    )

    assert extract_queries(prompt)[0] == "COINBASE_API_KEY"
    request = CodeInvestigationRequest(
        user_request=prompt,
        behavior="where Coinbase environment variable used edit",
    )
    assert query_candidates(request, [])[0] == "COINBASE_API_KEY"


def test_data_model_target_extracts_table_subject_from_read_write_prompt() -> None:
    prompt = (
        "In /mnt/c/agentic_agents/tests/fixtures/generalization/go_http_fixture, "
        "find where the orders table is defined, read, and written. Don't change files. "
        "Return definition sites, read sites, write sites, gaps, and source refs."
    )

    assert data_model_target_from_request(prompt, ["agentic_agents"], "find where orders table defined read") == "orders"


def test_data_model_target_extracts_plural_schema_subject() -> None:
    prompt = (
        "In /mnt/c/coinbase_testing_repo_frozen_tmp, list the schema fields for stealth orders. "
        "Read only. Include model files, fields, and any gaps."
    )

    assert data_model_target_from_request(prompt, ["coinbase_testing_repo_frozen_tmp"], "stealth") == "stealth_orders"


def test_data_model_target_extracts_schema_fields_for_subject() -> None:
    prompt = (
        "In C:/tmp/repo, find the database schema fields for stealth_orders. "
        "Read only. Return model files, fields, and source refs."
    )

    assert data_model_target_from_request(prompt, ["agentic_agents"], "find database schema fields") == "stealth_orders"


def test_data_model_target_ignores_persisted_schema_scope_adjective() -> None:
    prompt = (
        "In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find only the persisted stealth_orders table schema. "
        "Read only. Return schema field names, model files, and source refs. Exclude runtime dictionary fields."
    )

    assert data_model_target_from_request(prompt, [], "") == "stealth_orders"


def test_table_schema_fields_include_persisted_alter_table_columns(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    schema_path = target / "database" / "order.py"
    schema_path.parent.mkdir(parents=True)
    schema_path.write_text(
        "\n".join(
            [
                "def create_stealth_orders_table():",
                "    create_table_query = \"\"\"",
                "    CREATE TABLE IF NOT EXISTS stealth_orders (",
                "        stealth_order_id UUID PRIMARY KEY,",
                "        status VARCHAR(32) NOT NULL",
                "    );",
                "    \"\"\"",
                "    cursor.execute(",
                "        \"ALTER TABLE stealth_orders ADD COLUMN IF NOT EXISTS anchor_repricing_policy_json JSONB DEFAULT '{}'::jsonb\"",
                "    )",
                "    cursor.execute(",
                "        \"\"\"ALTER TABLE stealth_orders",
                "           ADD COLUMN IF NOT EXISTS post_fill_retreat_policy_json",
                "           JSONB DEFAULT '{\"enabled\": false}'::jsonb\"\"\"",
                "    )",
            ]
        ),
        encoding="utf-8",
    )

    fields = table_schema_fields(target, "database/order.py", "stealth_orders")

    assert {field["name"] for field in fields} == {
        "stealth_order_id",
        "status",
        "anchor_repricing_policy_json",
        "post_fill_retreat_policy_json",
    }
    assert any(
        field["name"] == "anchor_repricing_policy_json" and field["source"] == "sql_alter_add_column"
        for field in fields
    )


def test_dependency_import_lookup_handles_import_or_depend_on_phrase() -> None:
    prompt = (
        "In /mnt/c/coinbase_testing_repo_frozen_tmp.github, what does core/stealth_order_manager.py "
        "import or depend on? Read only. Include local dependencies and files."
    )

    queries = extract_queries(prompt)
    relationships = relationship_queries_from_request(prompt, queries)

    assert queries[0] == "stealth_order_manager"
    assert relationships == [{"kind": "imports", "symbol": "stealth_order_manager", "max_results": 25}]


def test_table_read_write_lookup_scans_go_and_sql_fixture_files() -> None:
    request = CodeInvestigationRequest(
        target_root=GO_FIXTURE_ROOT,
        user_request=(
            "find where the orders table is defined, read, and written. "
            "Return definition sites, read sites, write sites, gaps, and source refs."
        ),
        behavior="find where orders table defined read",
    )

    artifact = build_table_read_write_lookup(
        request,
        target_root=GO_FIXTURE_ROOT,
        queries=[],
        matches=[],
        warnings=[],
    )

    assert artifact["target_table"] == "orders"
    assert artifact["status"] == "ready"
    assert any(site["path"] == "migrations/001_create_orders.sql" for site in artifact["definition_sites"])
    assert any(site["path"] == "internal/orders/sql_repository.go" for site in artifact["read_sites"])
    assert any(site["path"] == "internal/orders/sql_repository.go" for site in artifact["write_sites"])


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


def test_change_boundary_prompt_promotes_atomic_snake_case_subject_terms() -> None:
    prompt = (
        "In /mnt/c/coinbase_testing_repo_frozen_tmp, identify the minimal safe change surface "
        "for changing placed_order_id stealth lookup behavior. Read only. Return files that would "
        "need review, related tests, risk level, gaps, and verification commands. Stop before implementation."
    )

    assert change_subject_queries_from_request(prompt)[:3] == [
        "placed_order_id",
        "placed_order_id_stealth_lookup",
        "placed_order_id stealth lookup",
    ]
    assert extract_queries(prompt)[:3] == [
        "placed_order_id",
        "placed_order_id_stealth_lookup",
        "placed_order_id stealth lookup",
    ]

    request = CodeInvestigationRequest(user_request=prompt, behavior="placed_order_id_stealth_lookup")
    assert query_candidates(request, [])[:3] == [
        "placed_order_id",
        "placed_order_id_stealth_lookup",
        "placed_order_id stealth lookup",
    ]


def test_files_to_touch_prompt_extracts_change_subject_without_change_surface_phrase() -> None:
    prompt = (
        "In /mnt/c/coinbase_testing_repo_frozen_tmp.github, identify files to touch and files not to touch "
        "for a minimal safe placed_order_id stealth lookup change. Read only and stop before implementation."
    )

    assert change_subject_queries_from_request(prompt)[:3] == [
        "placed_order_id",
        "placed_order_id_stealth_lookup",
        "placed_order_id stealth lookup",
    ]
    assert extract_queries(prompt)[:3] == [
        "placed_order_id",
        "placed_order_id_stealth_lookup",
        "placed_order_id stealth lookup",
    ]

    request = CodeInvestigationRequest(user_request=prompt, behavior="placed_order_id")
    assert query_candidates(request, [])[:7] == [
        "placed_order_id",
        "placed_order_id_stealth_lookup",
        "placed_order_id stealth lookup",
        "find_stealth_order_by_placed_order_id",
        "_placed_order_index",
        "revealed_orders",
        "placement_client_order_id",
    ]


def test_evidence_records_rank_exact_behavior_above_broad_source_match() -> None:
    records = evidence_file_records(
        ["core/stealth_order_manager.py", "tests/unit/test_order_id_and_followup_rules.py"],
        [],
        [
            {
                "path": "core/stealth_order_manager.py",
                "line": 10,
                "query": "lookup",
                "source": "git_grep",
            },
            {
                "path": "tests/unit/test_order_id_and_followup_rules.py",
                "line": 42,
                "query": "placed_order_id_stealth_lookup",
                "source": "git_grep",
            },
            {
                "path": "tests/unit/test_order_id_and_followup_rules.py",
                "line": 45,
                "query": "placed_order_id",
                "source": "git_grep",
            },
        ],
    )

    assert records[0]["path"] == "tests/unit/test_order_id_and_followup_rules.py"
    assert records[0]["relevance"]["tier"] in {"direct", "strong"}
    assert "exact_behavior_or_symbol_query" in records[0]["relevance"]["reasons"]


def test_evidence_line_refs_rank_exact_symbol_before_broad_keyword() -> None:
    records = evidence_file_records(
        ["core/stealth_order_manager.py"],
        [],
        [
            {
                "path": "core/stealth_order_manager.py",
                "line": 10,
                "query": "lookup",
                "source": "git_grep",
            },
            {
                "path": "core/stealth_order_manager.py",
                "line": 250,
                "query": "placed_order_id",
                "source": "git_grep",
            },
        ],
    )

    assert records[0]["line_refs"][0]["query"] == "placed_order_id"
    assert records[0]["line_refs"][0]["relevance"]["tier"] == "direct"


def test_request_flow_steps_rank_direct_handler_branch_above_path_sorted_broad_match() -> None:
    steps = request_flow_steps_from_matches(
        [
            {
                "path": "api/audit.py",
                "line": 8,
                "text": "request audit metadata",
                "query": "request",
                "source": "git_grep",
            },
            {
                "path": "websocket/z_handler.py",
                "line": 91,
                "text": "if msg_type == 'request_stealth_orders':",
                "query": "request_stealth_orders",
                "source": "git_grep",
            },
        ],
        source_paths={"api/audit.py", "websocket/z_handler.py"},
        behavior="request_stealth_orders",
        beginning_path=None,
        max_steps=5,
    )

    assert steps[0]["path"] == "websocket/z_handler.py"
    assert steps[0]["role"] == "handler_branch"
    assert steps[0]["relevance"]["tier"] in {"direct", "strong"}


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
