from __future__ import annotations

import json
import importlib.util
import sys
from copy import deepcopy
from pathlib import Path

from vllm_agent_gateway.skills.batches import build_skill_batch_report


REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE61_SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_skill_batch_d_proposal.py"
PHASE63_SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_phase63_skill_batch_live.py"


def load_phase61_module():
    spec = importlib.util.spec_from_file_location("validate_skill_batch_d_proposal", PHASE61_SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_phase63_module():
    spec = importlib.util.spec_from_file_location("validate_phase63_skill_batch_live", PHASE63_SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def make_batch_root(tmp_path: Path) -> Path:
    root = tmp_path / "skill-batch-root"
    write_json(
        root / "runtime" / "workflows.json",
        {
            "schema_version": 1,
            "workflows": [
                {
                    "id": "code_investigation.plan",
                    "controller_actions": [
                        {
                            "tool_id": "git_grep",
                            "action": "bounded_lookup",
                            "result_artifacts": ["investigation_plan"],
                        }
                    ],
                }
            ],
        },
    )
    write_json(root / "runtime" / "tools.json", {"schema_version": 1, "tools": []})
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
                },
                {
                    "id": "ambiguous_request",
                    "description": "Ambiguous request fixture.",
                    "expected_behavior": "stop_or_ask_blocking_question",
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
    write_json(
        root / "runtime" / "skills.json",
        {
            "schema_version": 1,
            "kind": "skill_registry",
            "policy": {
                "body_load_policy": "metadata_selected_only",
                "creation_rule": "Create or edit a skill only when an eval failure proves missing knowledge.",
            },
            "skills": [
                {
                    "id": "existing-skill",
                    "capability_contract": {"route_key": "existing.route_key"},
                }
            ],
        },
    )
    write_text(root / "README.skill-registry.md", "# Skill Registry\n")
    write_text(root / "docs" / "SKILL_LIBRARY_SCALING_PLAN.md", "# Skill Library Scaling Plan\n")
    write_text(
        root / ".qwen" / "skills" / "example-batch-skill" / "SKILL.md",
        "---\n"
        "name: example-batch-skill\n"
        "description: Example batch skill for validation coverage.\n"
        "---\n"
        "\n"
        "# Example Batch Skill\n",
    )
    write_text(
        root / ".qwen" / "skills" / "second-batch-skill" / "SKILL.md",
        "---\n"
        "name: second-batch-skill\n"
        "description: Second batch skill for duplicate route coverage.\n"
        "---\n"
        "\n"
        "# Second Batch Skill\n",
    )
    return root


def valid_skill(skill_id: str = "example-batch-skill", eval_case_id: str = "example_batch_eval") -> dict[str, object]:
    return {
        "id": skill_id,
        "path": f".qwen/skills/{skill_id}/SKILL.md",
        "version": "0.1.0",
        "owner": "agentic_agents",
        "description": "Describe the bounded procedural knowledge this batch skill adds.",
        "compatibility": ["agent-skills-frontmatter", "openai-compatible-chat", "qwen-local"],
        "safety_level": "read_only_planning",
        "allowed_tools": [],
        "workflows": ["code_investigation.plan"],
        "triggers": ["example batch trigger"],
        "workflow_priorities": {"code_investigation.plan": 1000},
        "capability_contract": {
            "route_key": f"code.{skill_id.replace('-', '_')}",
            "task_types": ["example_batch_task"],
            "input_artifacts": ["natural_user_request"],
            "output_artifacts": ["example_batch_artifact"],
            "approval_boundary": "none",
            "mutation_policy": "no_repository_mutation",
            "eval_case_ids": [eval_case_id],
        },
        "problem_solving_steps": [4],
        "eval_status": "draft",
        "evals": {
            "fixtures": ["clear_request", "ambiguous_request"],
            "localhost_8000": "not_run",
            "gateway_8300": "not_run",
            "anythingllm": "not_run",
        },
        "failure_record_refs": ["docs/SKILL_LIBRARY_SCALING_PLAN.md#phase-29-scaling-harness-hardening"],
    }


def valid_eval_case(eval_case_id: str = "example_batch_eval") -> dict[str, object]:
    return {
        "id": eval_case_id,
        "prompt_family": "example-batch",
        "natural_prompt": "In <repo>, run the example batch prompt. Read only.",
        "expected_workflow": "code_investigation.plan",
        "expected_artifacts": ["example_batch_artifact"],
        "mutation_policy": "no_repository_mutation",
        "live_suite": "skill_registry_contract",
    }


def valid_batch_manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "skill_batch_manifest",
        "id": "phase29-example-batch",
        "description": "Example skill batch manifest used to validate dry-run admission.",
        "doc_refs": ["README.skill-registry.md", "docs/SKILL_LIBRARY_SCALING_PLAN.md"],
        "skills": [valid_skill()],
        "eval_cases": [valid_eval_case()],
    }


def write_batch(root: Path, manifest: dict[str, object]) -> Path:
    path = root / "runtime-state" / "skill-batches" / "batch.json"
    write_json(path, manifest)
    return path


def test_skill_batch_validator_accepts_valid_batch_and_writes_report(tmp_path: Path) -> None:
    root = make_batch_root(tmp_path)
    batch_path = write_batch(root, valid_batch_manifest())

    report = build_skill_batch_report(root, batch_path, output_path=tmp_path / "report.json")

    assert report["status"] == "passed"
    assert report["batch_id"] == "phase29-example-batch"
    assert report["summary"]["skill_count"] == 1
    assert report["summary"]["eval_case_count"] == 1
    assert report["summary"]["route_key_count"] == 1
    assert report["entries"][0]["skill_id"] == "example-batch-skill"
    assert report["entries"][0]["route_key"] == "code.example_batch_skill"
    assert report["entries"][0]["live_mappings"][0]["status"] == "metadata_only"
    assert report["runtime_behavior_changed"] is False
    assert (tmp_path / "report.json").exists()


def test_skill_batch_validator_rejects_duplicate_route_keys_inside_batch(tmp_path: Path) -> None:
    root = make_batch_root(tmp_path)
    manifest = valid_batch_manifest()
    second_skill = valid_skill("second-batch-skill", "second_batch_eval")
    first_skill = manifest["skills"][0]
    assert isinstance(first_skill, dict)
    first_contract = first_skill["capability_contract"]
    second_contract = second_skill["capability_contract"]
    assert isinstance(first_contract, dict)
    assert isinstance(second_contract, dict)
    second_contract["route_key"] = first_contract["route_key"]
    manifest["skills"] = [first_skill, second_skill]
    manifest["eval_cases"] = [valid_eval_case(), valid_eval_case("second_batch_eval")]
    batch_path = write_batch(root, manifest)

    report = build_skill_batch_report(root, batch_path, output_path=tmp_path / "report.json")

    assert report["status"] == "failed"
    assert "Duplicate skill batch route_key" in report["errors"][0]


def test_skill_batch_validator_rejects_missing_eval_case_reference(tmp_path: Path) -> None:
    root = make_batch_root(tmp_path)
    manifest = valid_batch_manifest()
    skill = deepcopy(manifest["skills"][0])
    assert isinstance(skill, dict)
    contract = skill["capability_contract"]
    assert isinstance(contract, dict)
    contract["eval_case_ids"] = ["missing_batch_eval"]
    manifest["skills"] = [skill]
    batch_path = write_batch(root, manifest)

    report = build_skill_batch_report(root, batch_path, output_path=tmp_path / "report.json")

    assert report["status"] == "failed"
    assert "unknown case" in report["errors"][0]


def test_skill_batch_validator_rejects_missing_skill_body(tmp_path: Path) -> None:
    root = make_batch_root(tmp_path)
    manifest = valid_batch_manifest()
    skill = deepcopy(manifest["skills"][0])
    assert isinstance(skill, dict)
    skill["path"] = ".qwen/skills/missing-batch-skill/SKILL.md"
    manifest["skills"] = [skill]
    batch_path = write_batch(root, manifest)

    report = build_skill_batch_report(root, batch_path, output_path=tmp_path / "report.json")

    assert report["status"] == "failed"
    assert "path does not exist" in report["errors"][0]


def test_skill_batch_validator_rejects_unsupported_mutation_policy(tmp_path: Path) -> None:
    root = make_batch_root(tmp_path)
    manifest = valid_batch_manifest()
    eval_case = deepcopy(manifest["eval_cases"][0])
    assert isinstance(eval_case, dict)
    eval_case["mutation_policy"] = "mutate_anything"
    manifest["eval_cases"] = [eval_case]
    batch_path = write_batch(root, manifest)

    report = build_skill_batch_report(root, batch_path, output_path=tmp_path / "report.json")

    assert report["status"] == "failed"
    assert "unsupported mutation_policy" in report["errors"][0]


def test_skill_batch_validator_rejects_overlapping_semantic_intent(tmp_path: Path) -> None:
    root = make_batch_root(tmp_path)
    manifest = valid_batch_manifest()
    second_skill = valid_skill("second-batch-skill", "second_batch_eval")
    second_contract = second_skill["capability_contract"]
    assert isinstance(second_contract, dict)
    second_contract["route_key"] = "code.second_batch_unique_route"
    second_contract["task_types"] = ["example_batch_task"]
    second_contract["output_artifacts"] = ["example_batch_artifact"]
    second_skill["triggers"] = ["example batch trigger"]
    manifest["skills"] = [manifest["skills"][0], second_skill]
    manifest["eval_cases"] = [valid_eval_case(), valid_eval_case("second_batch_eval")]
    batch_path = write_batch(root, manifest)

    report = build_skill_batch_report(root, batch_path, output_path=tmp_path / "report.json")

    assert report["status"] == "failed"
    assert "overlapping semantic intent" in report["errors"][0]


def test_static_phase29_skill_batch_fixture_stays_valid(tmp_path: Path) -> None:
    fixture_root = REPO_ROOT / "tests" / "fixtures" / "skill_batches" / "phase29_valid"

    report = build_skill_batch_report(
        fixture_root,
        fixture_root / "batch.json",
        output_path=tmp_path / "static-fixture-report.json",
    )

    assert report["status"] == "passed"
    assert report["batch_id"] == "phase29-valid-batch"
    assert report["summary"]["skill_count"] == 1


def test_static_phase31_skill_batch_fixture_stays_valid(tmp_path: Path) -> None:
    fixture_root = REPO_ROOT / "tests" / "fixtures" / "skill_batches" / "phase31_l1_read_only_b"

    report = build_skill_batch_report(
        fixture_root,
        fixture_root / "batch.json",
        output_path=tmp_path / "phase31-fixture-report.json",
    )

    assert report["status"] == "passed"
    assert report["batch_id"] == "phase31-l1-read-only-b"
    assert report["summary"]["skill_count"] == 5
    assert report["summary"]["eval_case_count"] == 5


def test_static_phase32_skill_batch_fixture_stays_valid(tmp_path: Path) -> None:
    fixture_root = REPO_ROOT / "tests" / "fixtures" / "skill_batches" / "phase32_l2_diagnostic_a"

    report = build_skill_batch_report(
        fixture_root,
        fixture_root / "batch.json",
        output_path=tmp_path / "phase32-fixture-report.json",
    )

    assert report["status"] == "passed"
    assert report["batch_id"] == "phase32-l2-diagnostic-a"
    assert report["summary"]["skill_count"] == 4
    assert report["summary"]["eval_case_count"] == 4


def test_static_phase34_skill_batch_fixture_stays_valid(tmp_path: Path) -> None:
    fixture_root = REPO_ROOT / "tests" / "fixtures" / "skill_batches" / "phase34_draft_only_a"

    report = build_skill_batch_report(
        fixture_root,
        fixture_root / "batch.json",
        output_path=tmp_path / "phase34-fixture-report.json",
    )

    assert report["status"] == "passed"
    assert report["batch_id"] == "phase34-draft-only-a"
    assert report["summary"]["skill_count"] == 3
    assert report["summary"]["eval_case_count"] == 3
    assert report["summary"]["live_suite_counts"] == {"workflow_router_l1_suite": 3}


def test_phase61_batch_d_proposal_validates_against_current_registry(tmp_path: Path) -> None:
    module = load_phase61_module()

    report = module.build_proposal_report(
        REPO_ROOT,
        REPO_ROOT / "docs" / "skill-scaling-batch-d.json",
        output_path=tmp_path / "phase61-batch-d-proposal.json",
    )

    assert report["status"] == "passed"
    assert report["summary"]["candidate_count"] == 4
    assert report["summary"]["route_key_count"] == 4
    assert report["summary"]["semantic_conflict_count"] == 0


def test_phase61_batch_d_proposal_rejects_duplicate_route_keys(tmp_path: Path) -> None:
    module = load_phase61_module()
    proposal = json.loads((REPO_ROOT / "docs" / "skill-scaling-batch-d.json").read_text(encoding="utf-8"))
    proposal["candidates"][1]["route_key"] = proposal["candidates"][0]["route_key"]
    proposal_path = tmp_path / "duplicate-route-proposal.json"
    write_json(proposal_path, proposal)

    report = module.build_proposal_report(
        REPO_ROOT,
        proposal_path,
        output_path=tmp_path / "phase61-duplicate-route-report.json",
    )

    assert report["status"] == "failed"
    assert "duplicate candidate route key" in report["errors"][0]


def test_phase63_live_validator_catalog_covers_all_batch_d_skills() -> None:
    module = load_phase63_module()

    assert module.PHASE63_SKILL_IDS == [
        "handler-branch-tracer",
        "table-schema-isolator",
        "runtime-entrypoint-disambiguator",
        "change-boundary-summarizer",
    ]
    assert module.PHASE63_EVAL_CASE_IDS == [
        "phase61_handler_branch_trace",
        "phase61_table_schema_only",
        "phase61_runtime_entrypoint_disambiguation",
        "phase61_change_boundary_summary",
    ]
    cases_by_skill = {case.skill_id: case for case in module.PHASE63_CASES}
    assert set(cases_by_skill) == set(module.PHASE63_SKILL_IDS)
    assert {case.case_id for case in module.PHASE63_CASES} == set(module.PHASE63_EVAL_CASE_IDS)
    assert all(case.artifact_key.startswith("downstream_") for case in module.PHASE63_CASES)
