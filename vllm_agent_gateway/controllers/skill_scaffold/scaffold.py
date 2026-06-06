"""Artifact-only skill authoring scaffold workflow."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus
from vllm_agent_gateway.skills.batches import build_skill_batch_report
from vllm_agent_gateway.skills.evals import (
    ALLOWED_LIVE_SUITES,
    MANUAL_ARTIFACT_IDS,
    skill_output_artifacts,
    workflow_result_artifacts,
)
from vllm_agent_gateway.skills.registry import (
    ROUTE_KEY_NAMESPACES,
    SCHEMA_VERSION,
    SKILL_REGISTRY_PATH,
    SkillRegistryError,
    read_json_object,
    route_key_namespace,
    validate_doc_refs,
)


WORKFLOW_ID = "skill.scaffold"
DEFAULT_OUTPUT_DIR = "skill-scaffolds"
DEFAULT_OWNER = "agentic_agents"
DEFAULT_COMPATIBILITY = ["agent-skills-frontmatter", "openai-compatible-chat", "qwen-local"]
DEFAULT_DOCS = ["README.skill-registry.md", "docs/SKILL_LIBRARY_SCALING_PLAN.md"]
DEFAULT_FIXTURES = ["clear_request", "ambiguous_request"]

REQUIRED_SPEC_FIELDS = {
    "skill_id",
    "description",
    "prompt_family",
    "natural_prompt",
    "workflow_id",
    "route_key",
    "trigger_terms",
    "task_types",
    "output_artifact",
    "live_suite",
}


class SkillScaffoldError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "skill_scaffold_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class SkillScaffoldRequest:
    config_root: Path | str = "."
    output_root: Path | str = ".agentic_controller"
    workflow: str = WORKFLOW_ID
    schema_version: int = SCHEMA_VERSION
    prompt_family_spec: dict[str, Any] = field(default_factory=dict)
    role_id: str = "architect/default"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        config_root: Path,
        output_root: Path,
    ) -> "SkillScaffoldRequest":
        values: dict[str, Any] = {
            "config_root": config_root,
            "output_root": output_root,
        }
        names = {item.name for item in fields(cls)}
        for key, value in payload.items():
            if key in names:
                values[key] = value
        return cls(**values)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def artifact_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def string_value(spec: dict[str, Any], key: str) -> str:
    value = spec.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SkillScaffoldError(f"prompt_family_spec.{key} must be a non-empty string.")
    return value.strip()


def string_list_value(spec: dict[str, Any], key: str) -> list[str]:
    value = spec.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise SkillScaffoldError(f"prompt_family_spec.{key} must be a non-empty list of strings.")
    return [item.strip() for item in value]


def int_list_value(spec: dict[str, Any], key: str, default: list[int]) -> list[int]:
    value = spec.get(key, default)
    if not isinstance(value, list) or not all(isinstance(item, int) and not isinstance(item, bool) for item in value):
        raise SkillScaffoldError(f"prompt_family_spec.{key} must be a list of integers.")
    if not all(1 <= item <= 8 for item in value):
        raise SkillScaffoldError(f"prompt_family_spec.{key} values must be 1 through 8.")
    return list(value)


def validate_request(request: SkillScaffoldRequest) -> None:
    if request.workflow != WORKFLOW_ID:
        raise SkillScaffoldError("workflow must be skill.scaffold.", code="unsupported_workflow")
    if request.schema_version != SCHEMA_VERSION:
        raise SkillScaffoldError("schema_version must be 1.", code="unsupported_schema_version")
    if not isinstance(request.prompt_family_spec, dict) or not request.prompt_family_spec:
        raise SkillScaffoldError(
            "prompt_family_spec is required.",
            code="missing_prompt_family_spec",
            status=HTTPStatus.BAD_REQUEST,
        )
    missing = sorted(REQUIRED_SPEC_FIELDS - set(request.prompt_family_spec))
    if missing:
        raise SkillScaffoldError(
            f"prompt_family_spec is missing field(s): {', '.join(missing)}",
            code="missing_prompt_family_spec_field",
            status=HTTPStatus.BAD_REQUEST,
        )


def known_output_artifacts(config_root: Path) -> set[str]:
    workflow_manifest = read_json_object(config_root / "runtime" / "workflows.json", "workflow registry")
    registry_manifest = read_json_object(config_root / SKILL_REGISTRY_PATH, "skill registry")
    existing_skills = {
        item["id"]: item
        for item in registry_manifest.get("skills", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    return workflow_result_artifacts(workflow_manifest) | skill_output_artifacts(existing_skills) | MANUAL_ARTIFACT_IDS


def normalized_eval_case_id(skill_id: str) -> str:
    return skill_id.replace("-", "_")


def normalized_test_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")
    return normalized or "scaffolded_skill"


def scaffold_skill_body(skill_id: str, description: str, output_artifact: str) -> str:
    return (
        "---\n"
        f"name: {skill_id}\n"
        f"description: {description}\n"
        "---\n"
        "\n"
        f"# {skill_id}\n"
        "\n"
        "Use this skill only after registry metadata selects it for the active workflow.\n"
        "\n"
        "Required behavior:\n"
        "\n"
        "- Keep the workflow within the declared mutation policy and approval boundary.\n"
        "- Start from bounded evidence instead of assumptions.\n"
        "- Cite source files, docs, commands, or artifacts used as evidence.\n"
        f"- Produce or support the `{output_artifact}` artifact path.\n"
        "- Return gaps or blockers when evidence is incomplete.\n"
        "- Stop when the request falls outside this prompt family.\n"
        "\n"
        "8-step alignment:\n"
        "\n"
        "- Define and clarify the requested problem before selecting actions.\n"
        "- Identify evidence and root-cause candidates before proposing implementation work.\n"
        "- Verify results and record lessons learned when the downstream workflow executes.\n"
    )


def scaffold_prompt_coverage_entry(
    spec: dict[str, Any],
    *,
    skill_id: str,
    prompt_family: str,
    workflow_id: str,
    output_artifact: str,
    live_suite: str,
    eval_case_id: str,
    docs: list[str],
) -> dict[str, Any]:
    tool_ids = string_list_value(spec, "tool_ids") if spec.get("tool_ids") is not None else []
    route_rule = str(spec.get("route_rule") or f"TODO_route_rule_for_{normalized_eval_case_id(skill_id)}")
    return {
        "id": str(spec.get("coverage_id") or eval_case_id),
        "prompt_family": prompt_family,
        "level": str(spec.get("level") or "draft"),
        "status": "planned",
        "selected_workflow": workflow_id,
        "route_rule": route_rule,
        "skill_ids": [skill_id],
        "tool_ids": tool_ids,
        "eval_case_ids": [eval_case_id],
        "expected_artifacts": [output_artifact],
        "validation_suites": [live_suite],
        "docs_examples": docs,
        "promotion_state": "not_promoted_by_scaffold",
        "next_action": "install_coverage_entry_only_after_skill_metadata_and_eval_gates_pass",
    }


def scaffold_docs_stub(
    *,
    skill_id: str,
    description: str,
    prompt_family: str,
    natural_prompt: str,
    workflow_id: str,
    output_artifact: str,
    eval_case_id: str,
) -> str:
    return (
        f"# {skill_id}\n"
        "\n"
        f"{description}\n"
        "\n"
        "## Prompt Family\n"
        "\n"
        f"- Prompt family: `{prompt_family}`\n"
        f"- Example prompt: `{natural_prompt}`\n"
        f"- Workflow: `{workflow_id}`\n"
        f"- Expected artifact: `{output_artifact}`\n"
        f"- Eval case: `{eval_case_id}`\n"
        "\n"
        "## Admission State\n"
        "\n"
        "This stub is generated by `skill.scaffold` for review. It is not shipped documentation until the skill, "
        "coverage entry, eval gates, and docs links are installed through the approved lifecycle path.\n"
        "\n"
        "## Required Proof Before Promotion\n"
        "\n"
        "- Registry admission passes.\n"
        "- Prompt coverage entry validates as implemented.\n"
        "- Routing test passes for the natural prompt family.\n"
        "- Artifact contract test verifies the expected artifact is produced.\n"
        "- Natural-language chat output includes immediate user-facing substance.\n"
    )


def scaffold_docs_example_stub(
    *,
    skill_id: str,
    natural_prompt: str,
    workflow_id: str,
) -> str:
    return (
        f"# {skill_id} Example\n"
        "\n"
        "Natural prompt:\n"
        "\n"
        "```text\n"
        f"{natural_prompt}\n"
        "```\n"
        "\n"
        "Expected route:\n"
        "\n"
        "```text\n"
        f"{workflow_id}\n"
        "```\n"
        "\n"
        "This example is a generated scaffold. Keep it in the disposable scaffold output until the skill is admitted.\n"
    )


def scaffold_eval_skeleton(
    *,
    skill_id: str,
    prompt_family: str,
    natural_prompt: str,
    workflow_id: str,
    output_artifact: str,
    live_suite: str,
    eval_case_id: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "skill_eval_skeleton",
        "skill_id": skill_id,
        "eval_case": {
            "id": eval_case_id,
            "prompt_family": prompt_family,
            "natural_prompt": natural_prompt,
            "expected_workflow": workflow_id,
            "expected_artifacts": [output_artifact],
            "live_suite": live_suite,
        },
        "required_gates": [
            {"id": "routing", "status": "not_run"},
            {"id": "artifact_contract", "status": "not_run"},
            {"id": "natural_language_chat_output", "status": "not_run"},
            {"id": "prompt_coverage", "status": "not_run"},
        ],
        "promotion_state": "not_promoted_by_scaffold",
    }


def scaffold_regression_test_skeleton(
    *,
    skill_id: str,
    natural_prompt: str,
    workflow_id: str,
    output_artifact: str,
    coverage_id: str,
) -> str:
    test_prefix = normalized_test_name(skill_id)
    return (
        '"""Fail-closed scaffolded regression gates for a draft skill.\n'
        "\n"
        "Copy this file into tests/regression only after the scaffolded skill metadata,\n"
        "prompt coverage entry, route rule, and eval case are installed through the\n"
        "approved lifecycle path. Until then these tests intentionally fail closed.\n"
        '"""\n'
        "\n"
        "import pytest\n"
        "\n"
        "\n"
        f"SKILL_ID = {skill_id!r}\n"
        f"NATURAL_PROMPT = {natural_prompt!r}\n"
        f"EXPECTED_WORKFLOW = {workflow_id!r}\n"
        f"EXPECTED_ARTIFACT = {output_artifact!r}\n"
        f"COVERAGE_ID = {coverage_id!r}\n"
        "\n"
        "\n"
        f"def test_{test_prefix}_routes_to_expected_workflow():\n"
        "    pytest.fail(\"Install the scaffolded route rule before enabling this test.\")\n"
        "\n"
        "\n"
        f"def test_{test_prefix}_emits_expected_artifact_contract():\n"
        "    pytest.fail(\"Install the scaffolded skill and eval case before enabling this test.\")\n"
        "\n"
        "\n"
        f"def test_{test_prefix}_chat_output_is_user_visible():\n"
        "    pytest.fail(\"Prove the natural-language chat answer before enabling this test.\")\n"
        "\n"
        "\n"
        f"def test_{test_prefix}_prompt_coverage_entry_is_implemented():\n"
        "    pytest.fail(\"Install and validate the prompt coverage entry before enabling this test.\")\n"
    )


def scaffold_authoring_factory_artifacts(
    spec: dict[str, Any],
    *,
    config_root: Path,
    run_dir: Path,
    skill_id: str,
    description: str,
    prompt_family: str,
    natural_prompt: str,
    workflow_id: str,
    route_key: str,
    output_artifact: str,
    live_suite: str,
    eval_case_id: str,
    docs: list[str],
) -> dict[str, Any]:
    coverage_entry = scaffold_prompt_coverage_entry(
        spec,
        skill_id=skill_id,
        prompt_family=prompt_family,
        workflow_id=workflow_id,
        output_artifact=output_artifact,
        live_suite=live_suite,
        eval_case_id=eval_case_id,
        docs=docs,
    )
    docs_stub_path = run_dir / "docs-stubs" / f"README.{skill_id}.md"
    docs_example_path = run_dir / "docs-stubs" / "examples" / f"{skill_id}.md"
    eval_skeleton_path = run_dir / "eval-skeleton.json"
    coverage_entry_path = run_dir / "prompt-coverage-entry.json"
    test_skeleton_path = run_dir / "test-skeletons" / f"test_{normalized_test_name(skill_id)}_authoring_gate.py"

    write_json(coverage_entry_path, coverage_entry)
    write_json(
        eval_skeleton_path,
        scaffold_eval_skeleton(
            skill_id=skill_id,
            prompt_family=prompt_family,
            natural_prompt=natural_prompt,
            workflow_id=workflow_id,
            output_artifact=output_artifact,
            live_suite=live_suite,
            eval_case_id=eval_case_id,
        ),
    )
    write_text(
        docs_stub_path,
        scaffold_docs_stub(
            skill_id=skill_id,
            description=description,
            prompt_family=prompt_family,
            natural_prompt=natural_prompt,
            workflow_id=workflow_id,
            output_artifact=output_artifact,
            eval_case_id=eval_case_id,
        ),
    )
    write_text(
        docs_example_path,
        scaffold_docs_example_stub(
            skill_id=skill_id,
            natural_prompt=natural_prompt,
            workflow_id=workflow_id,
        ),
    )
    write_text(
        test_skeleton_path,
        scaffold_regression_test_skeleton(
            skill_id=skill_id,
            natural_prompt=natural_prompt,
            workflow_id=workflow_id,
            output_artifact=output_artifact,
            coverage_id=str(coverage_entry["id"]),
        ),
    )

    namespace = route_key_namespace(route_key)
    factory_report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "skill_authoring_factory_report",
        "skill_id": skill_id,
        "coverage_id": coverage_entry["id"],
        "eval_case_id": eval_case_id,
        "promotion_state": "not_promoted_by_scaffold",
        "checks": [
            {"id": "skill_id_naming", "status": "passed", "value": skill_id},
            {
                "id": "route_namespace",
                "status": "passed" if namespace in ROUTE_KEY_NAMESPACES else "failed",
                "value": namespace,
            },
            {"id": "version", "status": "draft_semver", "value": "0.1.0"},
            {"id": "lifecycle_state", "status": "draft_only", "value": "draft"},
            {"id": "documentation_refs", "status": "validated", "value": docs},
            {"id": "coverage_entry", "status": "planned_not_installed", "value": str(coverage_entry_path)},
            {"id": "eval_skeleton", "status": "not_run", "value": str(eval_skeleton_path)},
            {"id": "test_skeleton", "status": "fail_closed", "value": str(test_skeleton_path)},
            {"id": "runtime_registry_mutation", "status": "not_mutated", "value": str(config_root)},
        ],
        "artifacts": {
            "prompt_coverage_entry": str(coverage_entry_path),
            "eval_skeleton": str(eval_skeleton_path),
            "docs_stub": str(docs_stub_path),
            "docs_example_stub": str(docs_example_path),
            "regression_test_skeleton": str(test_skeleton_path),
        },
    }
    factory_report_path = run_dir / "authoring-factory-report.json"
    write_json(factory_report_path, factory_report)
    return {
        "prompt_coverage_entry": str(coverage_entry_path),
        "eval_skeleton": str(eval_skeleton_path),
        "docs_stub": str(docs_stub_path),
        "docs_example_stub": str(docs_example_path),
        "regression_test_skeleton": str(test_skeleton_path),
        "authoring_factory_report": str(factory_report_path),
    }


def scaffold_manifest(spec: dict[str, Any], *, config_root: Path, run_dir: Path) -> dict[str, Any]:
    skill_id = string_value(spec, "skill_id")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", skill_id):
        raise SkillScaffoldError("prompt_family_spec.skill_id is invalid.")
    description = string_value(spec, "description")
    prompt_family = string_value(spec, "prompt_family")
    natural_prompt = string_value(spec, "natural_prompt")
    workflow_id = string_value(spec, "workflow_id")
    route_key = string_value(spec, "route_key")
    trigger_terms = string_list_value(spec, "trigger_terms")
    task_types = string_list_value(spec, "task_types")
    output_artifact = string_value(spec, "output_artifact")
    live_suite = string_value(spec, "live_suite")
    owner = str(spec.get("owner") or DEFAULT_OWNER)
    docs = validate_doc_refs(config_root, spec.get("docs", DEFAULT_DOCS))
    compatibility = string_list_value(spec, "compatibility") if spec.get("compatibility") is not None else list(DEFAULT_COMPATIBILITY)
    eval_fixtures = string_list_value(spec, "eval_fixtures") if spec.get("eval_fixtures") is not None else list(DEFAULT_FIXTURES)
    problem_steps = int_list_value(spec, "problem_solving_steps", [4])
    safety_level = str(spec.get("safety_level") or "read_only_planning")
    mutation_policy = str(spec.get("mutation_policy") or "no_repository_mutation")
    approval_boundary = str(spec.get("approval_boundary") or "none")
    eval_case_id = str(spec.get("eval_case_id") or normalized_eval_case_id(skill_id))

    artifacts = known_output_artifacts(config_root)
    if output_artifact not in artifacts:
        raise SkillScaffoldError(
            f"prompt_family_spec.output_artifact must be one known artifact; unknown: {output_artifact}",
            code="unknown_output_artifact",
        )
    if live_suite not in ALLOWED_LIVE_SUITES:
        raise SkillScaffoldError(
            f"prompt_family_spec.live_suite is unsupported: {live_suite}",
            code="unsupported_live_suite",
        )

    skill_path = run_dir / "draft-skills" / skill_id / "SKILL.md"
    write_text(skill_path, scaffold_skill_body(skill_id, description, output_artifact))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "skill_batch_manifest",
        "id": f"scaffold-{skill_id}",
        "description": f"Scaffolded skill batch for prompt family {prompt_family}.",
        "doc_refs": docs,
        "skills": [
            {
                "id": skill_id,
                "path": str(skill_path),
                "version": "0.1.0",
                "owner": owner,
                "description": description,
                "compatibility": compatibility,
                "safety_level": safety_level,
                "allowed_tools": [],
                "workflows": [workflow_id],
                "triggers": trigger_terms,
                "workflow_priorities": {workflow_id: int(spec.get("workflow_priority", 1000))},
                "capability_contract": {
                    "route_key": route_key,
                    "task_types": task_types,
                    "input_artifacts": ["natural_user_request"],
                    "output_artifacts": [output_artifact],
                    "approval_boundary": approval_boundary,
                    "mutation_policy": mutation_policy,
                    "eval_case_ids": [eval_case_id],
                },
                "problem_solving_steps": problem_steps,
                "eval_status": "draft",
                "evals": {
                    "fixtures": eval_fixtures,
                    "localhost_8000": "not_run",
                    "gateway_8300": "not_run",
                    "anythingllm": "not_run",
                },
                "failure_record_refs": docs,
            }
        ],
        "eval_cases": [
            {
                "id": eval_case_id,
                "prompt_family": prompt_family,
                "natural_prompt": natural_prompt,
                "expected_workflow": workflow_id,
                "expected_artifacts": [output_artifact],
                "mutation_policy": mutation_policy,
                "live_suite": live_suite,
            }
        ],
    }


def validation_checklist(
    *,
    batch_report: dict[str, Any],
    output_artifact: str,
    live_suite: str,
) -> dict[str, Any]:
    errors = batch_report.get("errors") if isinstance(batch_report.get("errors"), list) else []
    return {
        "kind": "skill_scaffold_validation_checklist",
        "schema_version": SCHEMA_VERSION,
        "checks": [
            {"id": "explicit_output_artifact", "status": "passed", "value": output_artifact},
            {"id": "allowed_live_suite", "status": "passed", "value": live_suite},
            {"id": "skill_body_frontmatter", "status": "passed" if not errors else "see_batch_validation"},
            {"id": "batch_admission", "status": "passed" if batch_report.get("status") == "passed" else "failed"},
            {"id": "authoring_factory_sidecars", "status": "generated"},
            {"id": "promotion_gate", "status": "blocked_until_eval_gates_pass"},
            {"id": "runtime_registry_mutation", "status": "not_mutated"},
        ],
        "errors": errors,
    }


def invoke_skill_scaffold(request: SkillScaffoldRequest) -> InvocationResult:
    validate_request(request)
    output_root = Path(request.output_root).resolve()
    config_root = Path(request.config_root).resolve()
    run_id = f"skill-scaffold-{artifact_timestamp()}"
    run_dir = output_root / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, str] = {}
    request_artifact = {
        "kind": "skill_scaffold_request",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "prompt_family_spec": request.prompt_family_spec,
        "metadata": request.metadata,
        "created_at": utc_now(),
    }
    write_json(run_dir / "request.json", request_artifact)
    artifacts["request"] = str(run_dir / "request.json")

    manifest = scaffold_manifest(request.prompt_family_spec, config_root=config_root, run_dir=run_dir)
    write_json(run_dir / "batch.json", manifest)
    artifacts["draft_batch_manifest"] = str(run_dir / "batch.json")
    artifacts["draft_skill_body"] = str(run_dir / "draft-skills" / manifest["skills"][0]["id"] / "SKILL.md")
    draft_skill = manifest["skills"][0]
    draft_contract = draft_skill["capability_contract"]
    draft_eval_case = manifest["eval_cases"][0]
    artifacts.update(
        scaffold_authoring_factory_artifacts(
            request.prompt_family_spec,
            config_root=config_root,
            run_dir=run_dir,
            skill_id=draft_skill["id"],
            description=draft_skill["description"],
            prompt_family=draft_eval_case["prompt_family"],
            natural_prompt=draft_eval_case["natural_prompt"],
            workflow_id=draft_eval_case["expected_workflow"],
            route_key=draft_contract["route_key"],
            output_artifact=draft_eval_case["expected_artifacts"][0],
            live_suite=draft_eval_case["live_suite"],
            eval_case_id=draft_eval_case["id"],
            docs=manifest["doc_refs"],
        )
    )

    batch_report = build_skill_batch_report(
        config_root,
        run_dir / "batch.json",
        output_path=run_dir / "batch-validation-report.json",
    )
    artifacts["batch_validation_report"] = str(run_dir / "batch-validation-report.json")

    do_not_admit = []
    if batch_report["status"] != "passed":
        do_not_admit.append(
            {
                "source": "batch_validation",
                "errors": batch_report.get("errors", []),
                "action": "do_not_register_until_errors_are_resolved",
            }
        )
    status = "ready" if not do_not_admit else "do_not_admit"
    checklist = validation_checklist(
        batch_report=batch_report,
        output_artifact=request.prompt_family_spec["output_artifact"],
        live_suite=request.prompt_family_spec["live_suite"],
    )
    write_json(run_dir / "validation-checklist.json", checklist)
    artifacts["validation_checklist"] = str(run_dir / "validation-checklist.json")

    summary = {
        "scaffold_status": status,
        "skill_id": manifest["skills"][0]["id"],
        "eval_case_id": manifest["eval_cases"][0]["id"],
        "output_artifact": request.prompt_family_spec["output_artifact"],
        "live_suite": request.prompt_family_spec["live_suite"],
        "batch_validation_status": batch_report["status"],
        "do_not_admit_count": len(do_not_admit),
        "authoring_factory_status": "draft_sidecars_generated",
        "promotion_state": "not_promoted_by_scaffold",
        "runtime_registry_changed": False,
        "target_repository_changed": False,
        "next_action": "review_then_propose_or_pack" if status == "ready" else "revise_or_reject_scaffold",
    }
    scaffold = {
        "kind": "skill_scaffold",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": status,
        "summary": summary,
        "draft_batch_manifest": manifest,
        "validation_checklist": checklist,
        "batch_validation": {
            "status": batch_report["status"],
            "summary": batch_report.get("summary", {}),
            "errors": batch_report.get("errors", []),
        },
        "do_not_admit": do_not_admit,
        "artifacts": artifacts,
        "created_at": utc_now(),
    }
    write_json(run_dir / "skill-scaffold.json", scaffold)
    artifacts["skill_scaffold"] = str(run_dir / "skill-scaffold.json")

    run_state = {
        "kind": "skill_scaffold_run_state",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "summary": summary,
        "artifacts": artifacts,
        "updated_at": utc_now(),
    }
    write_json(run_dir / "run-state.json", run_state)
    artifacts["run_state"] = str(run_dir / "run-state.json")

    report = {
        "kind": "skill_scaffold_report",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "summary": summary,
        "scaffold": scaffold,
        "warnings": [],
        "artifacts": artifacts,
    }
    return InvocationResult(
        workflow=WORKFLOW_ID,
        status=WorkflowStatus.COMPLETED,
        artifact_paths=artifacts,
        summary_text=f"{WORKFLOW_ID} completed with scaffold_status={status}",
        failures=[],
        resume_key={"schema_version": SCHEMA_VERSION, "run_state": str(run_dir / "run-state.json")},
        report=report,
        run_id=run_id,
    )
