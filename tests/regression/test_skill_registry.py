from __future__ import annotations

import json
from pathlib import Path

import pytest

from vllm_agent_gateway.skills.registry import (
    SkillRegistryError,
    load_skill_registry,
    selected_skill_capability_route_keys,
    select_skills_for_workflow,
    validate_skill_admission_proposal,
    validate_skill_item,
    validate_skill_registry_manifest,
)
from vllm_agent_gateway.skills.scale import build_skill_scale_report


REPO_ROOT = Path(__file__).resolve().parents[2]
SEEDED_V1_SKILL_IDS = [
    "code-explanation-summarizer",
    "related-test-discovery",
    "safe-test-command-selector",
    "behavior-existence-checker",
    "callers-usages-summarizer",
    "configuration-lookup-guide",
    "pasted-failure-summarizer",
    "failing-test-diagnosis",
    "multi-file-investigation-planner",
    "dependency-impact-summarizer",
    "test-selection-rationale",
]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def make_skill_admission_root(tmp_path: Path, *, existing_route_key: str | None = None) -> Path:
    root = tmp_path / "admission-root"
    write_json(
        root / "runtime" / "workflows.json",
        {
            "schema_version": 1,
            "workflows": [
                {"id": "workflow_router.plan"},
                {"id": "code_investigation.plan"},
                {"id": "execution_planning.plan"},
                {"id": "workflow_feedback.record"},
            ],
        },
    )
    write_json(
        root / "runtime" / "tools.json",
        {
            "schema_version": 1,
            "tools": [
                {"id": "structure_index"},
                {"id": "git_grep"},
                {"id": "read_file"},
            ],
        },
    )
    write_json(
        root / "runtime" / "skill_evals.json",
        {
            "schema_version": 1,
            "kind": "skill_eval_fixture_registry",
            "fixtures": [
                {
                    "id": "clear_request",
                    "description": "Clear request.",
                    "expected_behavior": "produce_ready_or_next_step",
                },
                {
                    "id": "ambiguous_request",
                    "description": "Ambiguous request.",
                    "expected_behavior": "stop_or_ask_blocking_question",
                },
                {
                    "id": "unsafe_approval_bypass",
                    "description": "Unsafe request.",
                    "expected_behavior": "block_or_preserve_approval_gate",
                },
            ],
            "cases": [
                {
                    "id": "existing_eval_case",
                    "prompt_family": "existing",
                    "natural_prompt": "In <repo>, inspect existing behavior. Read only.",
                    "expected_workflow": "code_investigation.plan",
                    "expected_artifacts": ["investigation_plan"],
                    "mutation_policy": "no_repository_mutation",
                    "live_suite": "skill_registry_contract",
                }
            ],
        },
    )
    existing_skills: list[dict[str, object]] = []
    if existing_route_key:
        existing_skills.append(
            {
                "id": "existing-skill",
                "capability_contract": {"route_key": existing_route_key},
            }
        )
    write_json(
        root / "runtime" / "skills.json",
        {
            "schema_version": 1,
            "kind": "skill_registry",
            "policy": {
                "body_load_policy": "metadata_selected_only",
                "creation_rule": "Create or edit a skill only when an eval failure proves missing knowledge.",
            },
            "skills": existing_skills,
        },
    )
    write_text(root / "README.skill-registry.md", "# Skill Registry\n")
    write_text(root / "docs" / "examples" / "skill-registry.md", "# Skill Registry Examples\n")
    write_text(
        root / ".qwen" / "skills" / "example-skill" / "SKILL.md",
        "---\n"
        "name: example-skill\n"
        "description: Example admission skill for regression coverage.\n"
        "---\n"
        "\n"
        "# Example Skill\n",
    )
    return root


def valid_skill_admission_proposal() -> dict[str, object]:
    return {
        "skill": {
            "id": "example-skill",
            "path": ".qwen/skills/example-skill/SKILL.md",
            "version": "0.1.0",
            "owner": "agentic_agents",
            "description": "Describe the bounded procedural knowledge this draft skill adds.",
            "compatibility": ["agent-skills-frontmatter", "openai-compatible-chat", "qwen-local"],
            "safety_level": "read_only_planning",
            "allowed_tools": [],
            "workflows": ["code_investigation.plan"],
            "triggers": ["example trigger"],
            "workflow_priorities": {"code_investigation.plan": 50},
            "capability_contract": {
                "route_key": "code.unique_capability",
                "task_types": ["example_task_type"],
                "input_artifacts": ["natural_user_request"],
                "output_artifacts": ["example_artifact"],
                "approval_boundary": "none",
                "mutation_policy": "no_repository_mutation",
                "eval_case_ids": ["example_eval_case"],
            },
            "problem_solving_steps": [4],
            "eval_status": "draft",
            "evals": {
                "fixtures": ["clear_request", "ambiguous_request", "unsafe_approval_bypass"],
                "localhost_8000": "not_run",
                "gateway_8300": "not_run",
                "anythingllm": "not_run",
            },
            "failure_record_refs": ["README.skill-registry.md#skill-admission"],
        },
        "eval_case": {
            "id": "example_eval_case",
            "prompt_family": "example",
            "natural_prompt": "In <repo>, run the example read-only skill admission prompt.",
            "expected_workflow": "code_investigation.plan",
            "expected_artifacts": ["example_artifact"],
            "mutation_policy": "no_repository_mutation",
            "live_suite": "skill_registry_contract",
        },
        "doc_refs": ["README.skill-registry.md", "docs/examples/skill-registry.md"],
    }


def make_seeded_v1_admission_root(tmp_path: Path) -> Path:
    root = tmp_path / "seeded-v1-admission-root"
    skills_manifest = json.loads((REPO_ROOT / "runtime" / "skills.json").read_text(encoding="utf-8"))
    skill_by_id = {item["id"]: item for item in skills_manifest["skills"]}
    seeded_eval_case_ids = {
        case_id
        for skill_id in SEEDED_V1_SKILL_IDS
        for case_id in skill_by_id[skill_id]["capability_contract"]["eval_case_ids"]
    }
    skills_manifest["skills"] = [
        item for item in skills_manifest["skills"] if item["id"] not in SEEDED_V1_SKILL_IDS
    ]
    eval_manifest = json.loads((REPO_ROOT / "runtime" / "skill_evals.json").read_text(encoding="utf-8"))
    eval_manifest["cases"] = [
        item for item in eval_manifest["cases"] if item["id"] not in seeded_eval_case_ids
    ]
    write_json(root / "runtime" / "workflows.json", json.loads((REPO_ROOT / "runtime" / "workflows.json").read_text(encoding="utf-8")))
    write_json(root / "runtime" / "tools.json", json.loads((REPO_ROOT / "runtime" / "tools.json").read_text(encoding="utf-8")))
    write_json(root / "runtime" / "skills.json", skills_manifest)
    write_json(root / "runtime" / "skill_evals.json", eval_manifest)
    write_text(root / "README.skill-registry.md", "# Skill Registry\n")
    write_text(root / "docs" / "examples" / "skill-registry.md", "# Skill Registry Examples\n")
    for skill_id in SEEDED_V1_SKILL_IDS:
        relative_path = Path(skill_by_id[skill_id]["path"])
        write_text(root / relative_path, (REPO_ROOT / relative_path).read_text(encoding="utf-8"))
    return root


def test_skill_registry_validates_all_project_skill_metadata() -> None:
    registry = load_skill_registry(REPO_ROOT)

    assert len(registry) >= 46
    assert registry["request-triage"]["eval_status"] == "validated"
    assert registry["implementation-packet-designer"]["safety_level"] == "approval_gated_packet_design"
    assert registry["codegraph-context-lookup"]["allowed_tools"] == ["codegraph_context"]
    assert registry["code-explanation-summarizer"]["workflow_priorities"]["code_investigation.plan"] == 1000
    assert registry["test-selection-rationale"]["capability_contract"]["route_key"] == "verification.test_selection_rationale"
    assert registry["verification-planner"]["capability_contract"]["route_key"] == "verification.plan"
    assert registry["verification-planner"]["capability_contract"]["eval_case_ids"] == ["l2_test_selection"]
    assert registry["implementation-packet-designer"]["capability_contract"]["mutation_policy"] == "draft_artifacts_only"
    assert registry["endpoint-route-locator"]["capability_contract"]["route_key"] == "code.endpoint_route_lookup"
    assert registry["dependency-import-locator"]["workflows"] == ["code_context.lookup"]
    assert registry["coverage-gap-summarizer"]["capability_contract"]["route_key"] == "test.coverage_gap_summary"
    assert registry["documentation-locator"]["capability_contract"]["route_key"] == "docs.documentation_lookup"
    assert registry["cli-entrypoint-locator"]["capability_contract"]["route_key"] == "code.cli_entrypoint_lookup"
    assert registry["configuration-effect-summarizer"]["capability_contract"]["route_key"] == "config.effect_summary"
    assert registry["local-change-summarizer"]["capability_contract"]["route_key"] == "git.local_change_summary"
    assert registry["runtime-error-diagnoser"]["capability_contract"]["route_key"] == "diagnostics.runtime_error_diagnosis"
    assert registry["request-flow-mapper"]["capability_contract"]["route_key"] == "code.request_flow_map"
    assert registry["code-path-comparator"]["capability_contract"]["route_key"] == "code.path_comparison"
    assert registry["change-surface-summarizer"]["capability_contract"]["route_key"] == "planning.change_surface_summary"
    assert registry["config-default-test-drafter"]["capability_contract"]["route_key"] == "draft.config_default_test"
    assert registry["message-assertion-test-drafter"]["capability_contract"]["route_key"] == "draft.message_assertion_test"
    assert registry["test-assertion-update-drafter"]["capability_contract"]["route_key"] == "draft.test_assertion_update"
    assert registry["config-default-test-drafter"]["capability_contract"]["mutation_policy"] == "draft_artifacts_only"
    assert registry["auth-check-locator"]["capability_contract"]["route_key"] == "code.auth_check_lookup"
    assert registry["state-mutation-locator"]["capability_contract"]["route_key"] == "code.state_mutation_lookup"
    assert registry["external-integration-locator"]["capability_contract"]["route_key"] == "code.external_integration_lookup"
    assert (
        registry["error-handling-path-locator"]["capability_contract"]["route_key"]
        == "diagnostics.error_handling_path_lookup"
    )
    assert registry["handler-branch-tracer"]["capability_contract"]["route_key"] == "code.handler_branch_trace"
    assert registry["handler-branch-tracer"]["eval_status"] == "validated"
    assert registry["table-schema-isolator"]["capability_contract"]["route_key"] == "data.table_schema_only_lookup"
    assert registry["table-schema-isolator"]["eval_status"] == "validated"
    assert (
        registry["runtime-entrypoint-disambiguator"]["capability_contract"]["route_key"]
        == "code.runtime_entrypoint_disambiguation"
    )
    assert registry["runtime-entrypoint-disambiguator"]["eval_status"] == "validated"
    assert registry["change-boundary-summarizer"]["capability_contract"]["route_key"] == "planning.change_boundary_summary"
    assert registry["change-boundary-summarizer"]["eval_status"] == "validated"
    assert registry["ci-log-failure-summarizer"]["capability_contract"]["route_key"] == "diagnostics.ci_log_failure_summary"
    assert registry["ci-log-failure-summarizer"]["eval_status"] == "validated"
    assert registry["table-read-write-locator"]["capability_contract"]["route_key"] == "data.table_read_write_lookup"
    assert registry["table-read-write-locator"]["eval_status"] == "validated"
    assert (
        registry["runtime-reproduction-checklist-writer"]["capability_contract"]["route_key"]
        == "diagnostics.runtime_reproduction_checklist"
    )
    assert registry["runtime-reproduction-checklist-writer"]["eval_status"] == "validated"
    assert (
        registry["user-facing-message-test-target-locator"]["capability_contract"]["route_key"]
        == "diagnostics.user_facing_message_test_target"
    )
    assert registry["user-facing-message-test-target-locator"]["eval_status"] == "validated"
    assert all(Path(skill["path"]).exists() for skill in registry.values())


def test_seeded_v1_skills_pass_admission_validation_from_preseed_state(tmp_path: Path) -> None:
    root = make_seeded_v1_admission_root(tmp_path)
    skills_manifest = json.loads((REPO_ROOT / "runtime" / "skills.json").read_text(encoding="utf-8"))
    eval_manifest = json.loads((REPO_ROOT / "runtime" / "skill_evals.json").read_text(encoding="utf-8"))
    skill_by_id = {item["id"]: item for item in skills_manifest["skills"]}
    eval_by_id = {item["id"]: item for item in eval_manifest["cases"]}

    for skill_id in SEEDED_V1_SKILL_IDS:
        skill = dict(skill_by_id[skill_id])
        skill["eval_status"] = "draft"
        eval_case_ids = skill["capability_contract"]["eval_case_ids"]
        assert len(eval_case_ids) == 1
        result = validate_skill_admission_proposal(
            {
                "skill": skill,
                "eval_case": eval_by_id[eval_case_ids[0]],
                "doc_refs": ["README.skill-registry.md", "docs/examples/skill-registry.md"],
            },
            root,
        )

        assert result["status"] == "ready"
        assert result["skill"]["id"] == skill_id
        assert result["skill"]["eval_status"] == "draft"
        assert result["eval_case"]["id"] == eval_case_ids[0]


def test_skill_registry_rejects_malformed_skill_metadata() -> None:
    with pytest.raises(SkillRegistryError, match="missing field"):
        validate_skill_item(
            {"id": "bad-skill"},
            config_root=REPO_ROOT,
            workflow_ids={"workflow_router.plan"},
            tool_ids=set(),
            eval_fixture_ids={"clear_request"},
        )


def test_skill_registry_rejects_duplicate_capability_route_key() -> None:
    manifest = json.loads((REPO_ROOT / "runtime" / "skills.json").read_text(encoding="utf-8"))
    manifest["skills"][1]["capability_contract"]["route_key"] = manifest["skills"][0]["capability_contract"]["route_key"]

    with pytest.raises(SkillRegistryError, match="Duplicate skill capability route_key"):
        validate_skill_registry_manifest(manifest, REPO_ROOT)


def test_skill_registry_rejects_unknown_eval_case_reference() -> None:
    manifest = json.loads((REPO_ROOT / "runtime" / "skills.json").read_text(encoding="utf-8"))
    manifest["skills"][0]["capability_contract"]["eval_case_ids"] = ["missing_eval_case"]

    with pytest.raises(SkillRegistryError, match="unknown case"):
        validate_skill_registry_manifest(manifest, REPO_ROOT)


def test_skill_admission_accepts_one_valid_draft_skill_without_runtime_mutation(tmp_path: Path) -> None:
    root = make_skill_admission_root(tmp_path)

    result = validate_skill_admission_proposal(valid_skill_admission_proposal(), root)

    assert result["status"] == "ready"
    assert result["runtime_behavior_changed"] is False
    assert result["skill"]["id"] == "example-skill"
    assert result["skill"]["eval_status"] == "draft"
    assert result["eval_case"]["id"] == "example_eval_case"
    assert result["next_action"] == "review_then_append_skill_and_eval_case"


def test_skill_admission_rejects_duplicate_route_key(tmp_path: Path) -> None:
    root = make_skill_admission_root(tmp_path, existing_route_key="code.unique_capability")

    with pytest.raises(SkillRegistryError, match="route_key already exists"):
        validate_skill_admission_proposal(valid_skill_admission_proposal(), root)


def test_skill_admission_rejects_missing_eval_case(tmp_path: Path) -> None:
    root = make_skill_admission_root(tmp_path)
    proposal = valid_skill_admission_proposal()
    proposal.pop("eval_case")

    with pytest.raises(SkillRegistryError, match="missing field.*eval_case"):
        validate_skill_admission_proposal(proposal, root)


def test_skill_admission_rejects_packet_design_without_approval_boundary(tmp_path: Path) -> None:
    root = make_skill_admission_root(tmp_path)
    proposal = valid_skill_admission_proposal()
    skill = proposal["skill"]
    assert isinstance(skill, dict)
    contract = skill["capability_contract"]
    assert isinstance(contract, dict)
    contract["mutation_policy"] = "draft_artifacts_only"
    eval_case = proposal["eval_case"]
    assert isinstance(eval_case, dict)
    eval_case["mutation_policy"] = "draft_artifacts_only"

    with pytest.raises(SkillRegistryError, match="draft artifacts require packet-design approval"):
        validate_skill_admission_proposal(proposal, root)


def test_skill_admission_rejects_missing_skill_frontmatter(tmp_path: Path) -> None:
    root = make_skill_admission_root(tmp_path)
    write_text(root / ".qwen" / "skills" / "example-skill" / "SKILL.md", "# Missing Frontmatter\n")

    with pytest.raises(SkillRegistryError, match="missing Agent Skills frontmatter"):
        validate_skill_admission_proposal(valid_skill_admission_proposal(), root)


def test_skill_admission_rejects_missing_docs_link(tmp_path: Path) -> None:
    root = make_skill_admission_root(tmp_path)
    proposal = valid_skill_admission_proposal()
    proposal["doc_refs"] = ["docs/examples/missing.md"]

    with pytest.raises(SkillRegistryError, match="doc_refs path does not exist"):
        validate_skill_admission_proposal(proposal, root)


def test_skill_selection_is_stable_and_metadata_only() -> None:
    registry = load_skill_registry(REPO_ROOT)
    first = select_skills_for_workflow(
        registry,
        "code_investigation.plan",
        query_text="Find where placed_order_id stealth lookup begins. Return the entrypoint and related tests.",
        limit=5,
    )
    second = select_skills_for_workflow(
        registry,
        "code_investigation.plan",
        query_text="Find where placed_order_id stealth lookup begins. Return the entrypoint and related tests.",
        limit=5,
    )

    assert first == second
    assert first == [
        "request-triage",
        "scope-and-assumptions",
        "entrypoint-finder",
        "context-plan-builder",
        "related-test-discovery",
    ]
    assert "feedback-capture" not in first


def test_skill_selection_uses_capability_contract_prefilter() -> None:
    registry = load_skill_registry(REPO_ROOT)
    registry["unsafe-draft-context"] = {
        "id": "unsafe-draft-context",
        "workflows": ["code_investigation.plan"],
        "triggers": ["placed_order_id"],
        "workflow_priorities": {"code_investigation.plan": 0},
        "capability_contract": {
            "route_key": "unsafe.draft_context",
            "task_types": ["draft_packet_design"],
            "input_artifacts": ["natural_user_request"],
            "output_artifacts": ["draft_patch"],
            "approval_boundary": "packet_design_required",
            "mutation_policy": "draft_artifacts_only",
            "eval_case_ids": ["l1_draft_packet_design"],
        },
    }

    selected = select_skills_for_workflow(
        registry,
        "code_investigation.plan",
        query_text="Find where placed_order_id stealth lookup begins.",
        limit=6,
    )

    assert "unsafe-draft-context" not in selected
    assert selected == [
        "request-triage",
        "scope-and-assumptions",
        "entrypoint-finder",
        "context-plan-builder",
    ]


def test_selected_skill_capability_route_keys_are_reportable() -> None:
    registry = load_skill_registry(REPO_ROOT)
    selected = [
        "request-triage",
        "scope-and-assumptions",
        "entrypoint-finder",
        "context-plan-builder",
    ]

    routes = selected_skill_capability_route_keys(registry, selected)

    assert routes == {
        "request-triage": "planning.request_triage",
        "scope-and-assumptions": "planning.scope_assumptions",
        "entrypoint-finder": "code.entrypoint_discovery",
        "context-plan-builder": "context.plan_builder",
    }


def test_l1_related_tests_skill_selection_stays_read_only() -> None:
    registry = load_skill_registry(REPO_ROOT)

    selected = select_skills_for_workflow(
        registry,
        "code_investigation.plan",
        query_text="Find tests related to placed_order_id stealth lookup and recommend test commands.",
        limit=5,
    )

    assert selected == [
        "request-triage",
        "scope-and-assumptions",
        "entrypoint-finder",
        "context-plan-builder",
        "related-test-discovery",
    ]
    assert "implementation-packet-designer" not in selected
    assert "verification-planner" not in selected


def test_l1_explain_code_skill_selection_stays_read_only() -> None:
    registry = load_skill_registry(REPO_ROOT)

    selected = select_skills_for_workflow(
        registry,
        "code_investigation.plan",
        query_text="Explain what find_stealth_order_by_placed_order_id does in core/stealth_order_manager.py.",
        limit=5,
    )

    assert selected == [
        "request-triage",
        "scope-and-assumptions",
        "entrypoint-finder",
        "context-plan-builder",
        "code-explanation-summarizer",
    ]
    assert "implementation-packet-designer" not in selected
    assert "verification-planner" not in selected


def test_l1_behavior_exists_skill_selection_stays_read_only() -> None:
    registry = load_skill_registry(REPO_ROOT)

    selected = select_skills_for_workflow(
        registry,
        "code_investigation.plan",
        query_text="Check whether placed_order_id stealth lookup already exists.",
        limit=5,
    )

    assert selected == [
        "request-triage",
        "scope-and-assumptions",
        "entrypoint-finder",
        "context-plan-builder",
        "behavior-existence-checker",
    ]
    assert "implementation-packet-designer" not in selected
    assert "verification-planner" not in selected


def test_l1_callers_usages_skill_selection_uses_context_lookup_only() -> None:
    registry = load_skill_registry(REPO_ROOT)

    selected = select_skills_for_workflow(
        registry,
        "code_context.lookup",
        query_text="Find callers/usages of place_order and group by file.",
        limit=5,
    )

    assert selected == [
        "request-triage",
        "scope-and-assumptions",
        "context-plan-builder",
        "codegraph-context-lookup",
        "callers-usages-summarizer",
    ]
    assert "implementation-packet-designer" not in selected
    assert "verification-planner" not in selected


def test_l1_configuration_lookup_skill_selection_stays_read_only() -> None:
    registry = load_skill_registry(REPO_ROOT)

    selected = select_skills_for_workflow(
        registry,
        "code_investigation.plan",
        query_text="Find where COINBASE_API_KEY environment variable is defined or used.",
        limit=5,
    )

    assert selected == [
        "request-triage",
        "scope-and-assumptions",
        "entrypoint-finder",
        "context-plan-builder",
        "configuration-lookup-guide",
    ]
    assert "implementation-packet-designer" not in selected
    assert "verification-planner" not in selected


def test_l1_test_failure_summary_skill_selection_stays_read_only() -> None:
    registry = load_skill_registry(REPO_ROOT)

    selected = select_skills_for_workflow(
        registry,
        "code_investigation.plan",
        query_text="Summarize this pasted test failure and provide the next bounded inspection step.",
        limit=5,
    )

    assert selected == [
        "request-triage",
        "scope-and-assumptions",
        "entrypoint-finder",
        "context-plan-builder",
        "pasted-failure-summarizer",
    ]
    assert "implementation-packet-designer" not in selected
    assert "verification-planner" not in selected


def test_l1_safe_test_command_skill_selection_stays_read_only() -> None:
    registry = load_skill_registry(REPO_ROOT)

    selected = select_skills_for_workflow(
        registry,
        "code_investigation.plan",
        query_text="Recommend the smallest test command for placed_order_id stealth lookup.",
        limit=5,
    )

    assert selected == [
        "request-triage",
        "scope-and-assumptions",
        "entrypoint-finder",
        "context-plan-builder",
        "safe-test-command-selector",
    ]
    assert "implementation-packet-designer" not in selected
    assert "verification-planner" not in selected


def test_phase31_l1_skill_selection_stays_read_only() -> None:
    registry = load_skill_registry(REPO_ROOT)
    cases = [
        (
            "Identify test coverage gaps for placed_order_id stealth lookup.",
            "coverage-gap-summarizer",
        ),
        (
            "Find documentation for request_stealth_orders dashboard behavior.",
            "documentation-locator",
        ),
        (
            "Locate the CLI script entrypoint main.py for running the trading engine.",
            "cli-entrypoint-locator",
        ),
        (
            "Explain the runtime effect of COINBASE_API_KEY in configuration.py.",
            "configuration-effect-summarizer",
        ),
        (
            "Find recent or local changes and return git status.",
            "local-change-summarizer",
        ),
    ]

    for query_text, expected_skill in cases:
        selected = select_skills_for_workflow(
            registry,
            "code_investigation.plan",
            query_text=query_text,
            limit=5,
        )

        assert selected == [
            "request-triage",
            "scope-and-assumptions",
            "entrypoint-finder",
            "context-plan-builder",
            expected_skill,
        ]
        assert "implementation-packet-designer" not in selected
        assert "verification-planner" not in selected


def test_l2_v1_skill_selection_uses_matching_triggered_skill() -> None:
    registry = load_skill_registry(REPO_ROOT)
    cases = [
        (
            "Diagnose why this pytest failure is happening. Return root cause and smallest safe fix plan.",
            "failing-test-diagnosis",
        ),
        (
            "Investigate how placed_order_id stealth lookup flows across source files.",
            "multi-file-investigation-planner",
        ),
        (
            "Summarize dependency impact if placed_order_id stealth lookup behavior changes.",
            "dependency-impact-summarizer",
        ),
        (
            "Choose the smallest, medium, and broad validation commands and explain covered risks.",
            "test-selection-rationale",
        ),
    ]

    for query_text, expected_skill in cases:
        selected = select_skills_for_workflow(
            registry,
            "code_investigation.plan",
            query_text=query_text,
            limit=5,
        )

        assert selected == [
            "request-triage",
            "scope-and-assumptions",
            "entrypoint-finder",
            "context-plan-builder",
            expected_skill,
        ]


def test_phase32_l2_skill_selection_uses_matching_triggered_skill() -> None:
    registry = load_skill_registry(REPO_ROOT)
    cases = [
        (
            "Diagnose this runtime stack trace and return observed error, likely cause, and verification commands.",
            "runtime-error-diagnoser",
        ),
        (
            "Map the request flow for request_stealth_orders and return flow steps and participating files.",
            "request-flow-mapper",
        ),
        (
            "Compare the placed_order_id stealth lookup path with the client_order_id index path.",
            "code-path-comparator",
        ),
        (
            "Identify the minimal safe change surface and files that would need review before implementation.",
            "change-surface-summarizer",
        ),
    ]

    for query_text, expected_skill in cases:
        selected = select_skills_for_workflow(
            registry,
            "code_investigation.plan",
            query_text=query_text,
            limit=5,
        )

        assert selected == [
            "request-triage",
            "scope-and-assumptions",
            "entrypoint-finder",
            "context-plan-builder",
            expected_skill,
        ]


def test_phase99_batch_e_skill_selection_uses_matching_triggered_skill() -> None:
    registry = load_skill_registry(REPO_ROOT)
    cases = [
        (
            "Summarize this failing CI log and return the first failing command and next local command.",
            "ci-log-failure-summarizer",
        ),
        (
            "Find where database table stealth_orders is defined, read, and written.",
            "table-read-write-locator",
        ),
        (
            "Turn this runtime stack trace into a minimal reproduction checklist.",
            "runtime-reproduction-checklist-writer",
        ),
        (
            "Check if this user-facing error message has a test target and where it should be tested.",
            "user-facing-message-test-target-locator",
        ),
    ]

    for query_text, expected_skill in cases:
        selected = select_skills_for_workflow(
            registry,
            "code_investigation.plan",
            query_text=query_text,
            limit=5,
        )

        assert selected == [
            "request-triage",
            "scope-and-assumptions",
            "entrypoint-finder",
            "context-plan-builder",
            expected_skill,
        ]


def test_l1_small_text_edit_skill_selection_includes_packet_design() -> None:
    registry = load_skill_registry(REPO_ROOT)

    selected = select_skills_for_workflow(
        registry,
        "execution_planning.plan",
        query_text="Draft a small documentation edit to docs/agents/INVARIANTS.md with exact packet operations.",
        limit=9,
    )

    assert selected == [
        "request-triage",
        "scope-and-assumptions",
        "entrypoint-finder",
        "context-plan-builder",
        "execution-plan-writer",
        "impact-map-builder",
        "implementation-packet-designer",
        "verification-planner",
    ]
    assert "implementation-packet-designer" in selected
    assert "verification-planner" in selected


def test_l1_small_unit_test_skill_selection_includes_packet_design() -> None:
    registry = load_skill_registry(REPO_ROOT)

    selected = select_skills_for_workflow(
        registry,
        "execution_planning.plan",
        query_text=(
            "Draft a small unit test for sync_exchange_order_id_for_placed_order "
            "and produce exact packet operations."
        ),
        limit=9,
    )

    assert selected == [
        "request-triage",
        "scope-and-assumptions",
        "entrypoint-finder",
        "context-plan-builder",
        "execution-plan-writer",
        "impact-map-builder",
        "implementation-packet-designer",
        "verification-planner",
    ]
    assert "implementation-packet-designer" in selected
    assert "verification-planner" in selected


def test_l1_simple_failing_test_fix_skill_selection_includes_packet_design() -> None:
    registry = load_skill_registry(REPO_ROOT)

    selected = select_skills_for_workflow(
        registry,
        "execution_planning.plan",
        query_text="Draft the smallest fix for this simple failing pytest failure with exact packet operations.",
        limit=9,
    )

    assert selected == [
        "request-triage",
        "scope-and-assumptions",
        "entrypoint-finder",
        "context-plan-builder",
        "execution-plan-writer",
        "impact-map-builder",
        "implementation-packet-designer",
        "verification-planner",
    ]
    assert "implementation-packet-designer" in selected
    assert "verification-planner" in selected


def test_phase34_draft_skill_selection_uses_specific_triggered_skill() -> None:
    registry = load_skill_registry(REPO_ROOT)
    cases = [
        (
            "Draft a small unit test proving config default DEFAULT_PROFIT_MARGIN_PCT defaults to 0.5.",
            "config-default-test-drafter",
        ),
        (
            "Draft a small unit test asserting exact error message OrderBook is read-only.",
            "message-assertion-test-drafter",
        ),
        (
            "Draft a small test assertion update replacing the assertion in a pytest file.",
            "test-assertion-update-drafter",
        ),
    ]

    for query_text, expected_skill in cases:
        selected = select_skills_for_workflow(
            registry,
            "execution_planning.plan",
            query_text=query_text,
            limit=9,
        )

        assert selected == [
            "request-triage",
            "scope-and-assumptions",
            "entrypoint-finder",
            "context-plan-builder",
            "execution-plan-writer",
            "impact-map-builder",
            "implementation-packet-designer",
            "verification-planner",
            expected_skill,
        ]


def test_skill_selection_does_not_include_irrelevant_workflow_skills() -> None:
    registry = load_skill_registry(REPO_ROOT)

    selected = select_skills_for_workflow(
        registry,
        "code_context.lookup",
        query_text="Find callers and callees for reveal_order_slice.",
        limit=10,
    )

    assert selected == [
        "request-triage",
        "scope-and-assumptions",
        "context-plan-builder",
        "codegraph-context-lookup",
        "callers-usages-summarizer",
    ]
    assert "implementation-packet-designer" not in selected
    assert "verification-planner" not in selected


def test_skill_registry_rejects_unknown_route_key_namespace(tmp_path: Path) -> None:
    root = make_skill_admission_root(tmp_path)
    proposal = valid_skill_admission_proposal()
    skill = proposal["skill"]
    assert isinstance(skill, dict)
    contract = skill["capability_contract"]
    assert isinstance(contract, dict)
    contract["route_key"] = "unknown.namespace"

    with pytest.raises(SkillRegistryError, match="unsupported namespace"):
        validate_skill_admission_proposal(proposal, root)


def test_skill_registry_rejects_draft_namespace_without_packet_boundary(tmp_path: Path) -> None:
    root = make_skill_admission_root(tmp_path)
    proposal = valid_skill_admission_proposal()
    skill = proposal["skill"]
    assert isinstance(skill, dict)
    contract = skill["capability_contract"]
    assert isinstance(contract, dict)
    contract["route_key"] = "draft.bad_boundary"

    with pytest.raises(SkillRegistryError, match="namespace 'draft' requires workflows"):
        validate_skill_admission_proposal(proposal, root)


def test_skill_registry_rejects_deprecated_skill_without_replacement_metadata() -> None:
    manifest = json.loads((REPO_ROOT / "runtime" / "skills.json").read_text(encoding="utf-8"))
    manifest["skills"][0]["eval_status"] = "deprecated"

    with pytest.raises(SkillRegistryError, match="missing a deprecation object"):
        validate_skill_registry_manifest(manifest, REPO_ROOT)


def test_skill_registry_rejects_deprecated_skill_with_unknown_replacement() -> None:
    manifest = json.loads((REPO_ROOT / "runtime" / "skills.json").read_text(encoding="utf-8"))
    manifest["skills"][0]["eval_status"] = "deprecated"
    manifest["skills"][0]["deprecation"] = {
        "replaced_by": "missing-replacement",
        "reason": "Replacement must exist so deprecated skills do not strand route ownership.",
        "effective_date": "2026-06-05",
    }

    with pytest.raises(SkillRegistryError, match="references unknown skill"):
        validate_skill_registry_manifest(manifest, REPO_ROOT)


def test_skill_registry_rejects_overlapping_semantic_intent(tmp_path: Path) -> None:
    root = make_skill_admission_root(tmp_path)
    manifest = json.loads((REPO_ROOT / "runtime" / "skills.json").read_text(encoding="utf-8"))
    source_skill = next(item for item in manifest["skills"] if item["id"] == "code-explanation-summarizer")
    duplicate = json.loads(json.dumps(source_skill))
    duplicate["id"] = "duplicate-code-explanation"
    duplicate["path"] = ".qwen/skills/duplicate-code-explanation/SKILL.md"
    duplicate["capability_contract"]["route_key"] = "code.duplicate_explanation"
    write_text(
        root / ".qwen" / "skills" / "duplicate-code-explanation" / "SKILL.md",
        "---\n"
        "name: duplicate-code-explanation\n"
        "description: Duplicate code explanation skill for overlap regression coverage.\n"
        "---\n"
        "\n"
        "# Duplicate Code Explanation\n",
    )
    write_json(root / "runtime" / "workflows.json", json.loads((REPO_ROOT / "runtime" / "workflows.json").read_text(encoding="utf-8")))
    write_json(root / "runtime" / "tools.json", json.loads((REPO_ROOT / "runtime" / "tools.json").read_text(encoding="utf-8")))
    eval_manifest = json.loads((REPO_ROOT / "runtime" / "skill_evals.json").read_text(encoding="utf-8"))
    write_json(root / "runtime" / "skill_evals.json", eval_manifest)
    source_copy = json.loads(json.dumps(source_skill))
    source_copy["path"] = ".qwen/skills/code-explanation-summarizer/SKILL.md"
    write_text(
        root / ".qwen" / "skills" / "code-explanation-summarizer" / "SKILL.md",
        (REPO_ROOT / source_skill["path"]).read_text(encoding="utf-8"),
    )

    with pytest.raises(SkillRegistryError, match="overlapping semantic intent"):
        validate_skill_registry_manifest(
            {
                "schema_version": 1,
                "kind": "skill_registry",
                "skills": [source_copy, duplicate],
            },
            root,
        )


def test_skill_registry_allows_deprecated_overlap_with_replacement(tmp_path: Path) -> None:
    root = make_skill_admission_root(tmp_path)
    manifest = json.loads((REPO_ROOT / "runtime" / "skills.json").read_text(encoding="utf-8"))
    source_skill = next(item for item in manifest["skills"] if item["id"] == "code-explanation-summarizer")
    duplicate = json.loads(json.dumps(source_skill))
    duplicate["id"] = "deprecated-duplicate-code-explanation"
    duplicate["path"] = ".qwen/skills/deprecated-duplicate-code-explanation/SKILL.md"
    duplicate["capability_contract"]["route_key"] = "code.deprecated_duplicate_explanation"
    duplicate["eval_status"] = "deprecated"
    duplicate["deprecation"] = {
        "replaced_by": "code-explanation-summarizer",
        "reason": "Deprecated overlap regression keeps retired skills from blocking replacements.",
        "effective_date": "2026-06-05",
    }
    write_text(
        root / ".qwen" / "skills" / "deprecated-duplicate-code-explanation" / "SKILL.md",
        "---\n"
        "name: deprecated-duplicate-code-explanation\n"
        "description: Deprecated duplicate code explanation skill for overlap regression coverage.\n"
        "---\n"
        "\n"
        "# Deprecated Duplicate Code Explanation\n",
    )
    write_json(root / "runtime" / "workflows.json", json.loads((REPO_ROOT / "runtime" / "workflows.json").read_text(encoding="utf-8")))
    write_json(root / "runtime" / "tools.json", json.loads((REPO_ROOT / "runtime" / "tools.json").read_text(encoding="utf-8")))
    eval_manifest = json.loads((REPO_ROOT / "runtime" / "skill_evals.json").read_text(encoding="utf-8"))
    write_json(root / "runtime" / "skill_evals.json", eval_manifest)
    source_copy = json.loads(json.dumps(source_skill))
    source_copy["path"] = ".qwen/skills/code-explanation-summarizer/SKILL.md"
    write_text(
        root / ".qwen" / "skills" / "code-explanation-summarizer" / "SKILL.md",
        (REPO_ROOT / source_skill["path"]).read_text(encoding="utf-8"),
    )

    registry = validate_skill_registry_manifest(
        {
            "schema_version": 1,
            "kind": "skill_registry",
            "skills": [source_copy, duplicate],
        },
        root,
    )

    assert registry["deprecated-duplicate-code-explanation"]["eval_status"] == "deprecated"


def test_skill_selection_excludes_deprecated_skills() -> None:
    manifest = json.loads((REPO_ROOT / "runtime" / "skills.json").read_text(encoding="utf-8"))
    for item in manifest["skills"]:
        if item["id"] == "code-explanation-summarizer":
            item["eval_status"] = "deprecated"
            item["deprecation"] = {
                "replaced_by": "behavior-existence-checker",
                "reason": "Selector regression confirms deprecated skills are excluded from normal routing.",
                "effective_date": "2026-06-05",
            }
            break
    registry = validate_skill_registry_manifest(manifest, REPO_ROOT)

    selected = select_skills_for_workflow(
        registry,
        "code_investigation.plan",
        query_text="Explain what this function does, including inputs and outputs.",
        limit=10,
    )

    assert "code-explanation-summarizer" not in selected


def synthetic_skill(skill_id: str, eval_case_id: str, index: int) -> dict[str, object]:
    return {
        "id": skill_id,
        "path": f".qwen/skills/{skill_id}/SKILL.md",
        "version": "0.1.0",
        "owner": "agentic_agents",
        "description": f"Synthetic skill {index} used to validate large catalog admission.",
        "compatibility": ["agent-skills-frontmatter", "openai-compatible-chat", "qwen-local"],
        "safety_level": "read_only_planning",
        "allowed_tools": [],
        "workflows": ["code_investigation.plan"],
        "triggers": [f"synthetic unique trigger {index}"],
        "workflow_priorities": {"code_investigation.plan": 1000},
        "capability_contract": {
            "route_key": f"code.synthetic_{index}",
            "task_types": [f"synthetic_task_{index}"],
            "input_artifacts": ["natural_user_request"],
            "output_artifacts": [f"synthetic_artifact_{index}"],
            "approval_boundary": "none",
            "mutation_policy": "no_repository_mutation",
            "eval_case_ids": [eval_case_id],
        },
        "problem_solving_steps": [4],
        "eval_status": "validated",
        "evals": {"fixtures": ["clear_request"]},
        "failure_record_refs": ["README.skill-registry.md#skill-admission"],
    }


def synthetic_eval_case(eval_case_id: str, index: int) -> dict[str, object]:
    return {
        "id": eval_case_id,
        "prompt_family": f"synthetic-{index}",
        "natural_prompt": f"In <repo>, run synthetic read-only prompt {index}.",
        "expected_workflow": "code_investigation.plan",
        "expected_artifacts": [f"synthetic_artifact_{index}"],
        "mutation_policy": "no_repository_mutation",
        "live_suite": "skill_registry_contract",
    }


def test_skill_registry_validates_large_synthetic_catalog(tmp_path: Path) -> None:
    root = tmp_path / "large-synthetic-registry"
    skill_count = 250
    write_json(
        root / "runtime" / "workflows.json",
        {"schema_version": 1, "workflows": [{"id": "code_investigation.plan"}]},
    )
    write_json(root / "runtime" / "tools.json", {"schema_version": 1, "tools": []})
    write_text(root / "README.skill-registry.md", "# Skill Registry\n")
    skills = []
    eval_cases = []
    for index in range(skill_count):
        skill_id = f"synthetic-skill-{index}"
        eval_case_id = f"synthetic_eval_{index}"
        skills.append(synthetic_skill(skill_id, eval_case_id, index))
        eval_cases.append(synthetic_eval_case(eval_case_id, index))
        write_text(
            root / ".qwen" / "skills" / skill_id / "SKILL.md",
            "---\n"
            f"name: {skill_id}\n"
            f"description: Synthetic skill {index} used to validate large catalog admission.\n"
            "---\n"
            "\n"
            "# Synthetic Skill\n",
        )
    write_json(
        root / "runtime" / "skill_evals.json",
        {
            "schema_version": 1,
            "kind": "skill_eval_fixture_registry",
            "fixtures": [
                {
                    "id": "clear_request",
                    "description": "Clear request fixture.",
                    "expected_behavior": "produce_ready_or_next_step",
                }
            ],
            "cases": eval_cases,
        },
    )

    registry = validate_skill_registry_manifest(
        {"schema_version": 1, "kind": "skill_registry", "skills": skills},
        root,
    )

    assert len(registry) == skill_count


def test_skill_scale_report_passes_project_catalog(tmp_path: Path) -> None:
    report = build_skill_scale_report(REPO_ROOT, output_path=tmp_path / "skill-scale.json")
    registry = load_skill_registry(REPO_ROOT)
    eval_catalog = json.loads((REPO_ROOT / "runtime" / "skill_evals.json").read_text(encoding="utf-8"))

    assert report["status"] == "passed"
    assert report["summary"]["skill_count"] == len(registry)
    assert report["summary"]["eval_case_count"] == len(eval_catalog["cases"])
    assert report["summary"]["do_not_admit_count"] == 0
    assert report["coverage"]["by_route_namespace"]["code"] >= 16
    assert report["coverage"]["by_mutation_policy"]["draft_artifacts_only"] >= 4
    assert (tmp_path / "skill-scale.json").exists()
