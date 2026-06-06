"""Controller-owned skill-batch proposal workflow."""

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
from vllm_agent_gateway.skills.scale import build_skill_scale_report


WORKFLOW_ID = "skill_batch.propose"
SCHEMA_VERSION = 1
DEFAULT_OUTPUT_DIR = "skill-batch-proposals"


PHASE40_BATCH_B_SKILLS = [
    {
        "skill_id": "background-job-locator",
        "route_key": "code.background_job_lookup",
        "eval_case_id": "phase40_background_job_lookup",
        "prompt_family": "Phase40-background-job-lookup",
        "trigger": "background job",
        "task_type": "background_job_lookup",
        "output_artifact": "investigation_plan",
        "workflow": "code_investigation.plan",
        "description": "Locate background jobs, scheduled workers, sweepers, or periodic runtime tasks.",
        "natural_prompt": (
            "In <repo>, find background jobs, scheduled workers, sweepers, or periodic runtime tasks. "
            "Read only. Return entrypoints, evidence files, and related tests."
        ),
    },
    {
        "skill_id": "pytest-fixture-locator",
        "route_key": "test.pytest_fixture_lookup",
        "eval_case_id": "phase40_pytest_fixture_lookup",
        "prompt_family": "Phase40-pytest-fixture-lookup",
        "trigger": "pytest fixture",
        "task_type": "pytest_fixture_lookup",
        "output_artifact": "investigation_plan",
        "workflow": "code_investigation.plan",
        "description": "Locate pytest fixtures, test setup, and test data related to a named behavior.",
        "natural_prompt": (
            "In <repo>, find pytest fixtures or test setup code related to a named behavior. "
            "Read only. Return fixture files, setup evidence, and likely test commands."
        ),
    },
    {
        "skill_id": "api-reference-locator",
        "route_key": "docs.api_reference_lookup",
        "eval_case_id": "phase40_api_reference_lookup",
        "prompt_family": "Phase40-api-reference-lookup",
        "trigger": "api reference",
        "task_type": "api_reference_lookup",
        "output_artifact": "documentation_lookup",
        "workflow": "code_investigation.plan",
        "description": "Find API reference documentation, sample payloads, and contract files for a named request.",
        "natural_prompt": (
            "In <repo>, find API reference documentation for a named request or payload. "
            "Read only. Return docs, sample files, and evidence gaps."
        ),
    },
    {
        "skill_id": "agent-invariant-locator",
        "route_key": "docs.agent_invariant_lookup",
        "eval_case_id": "phase40_agent_invariant_lookup",
        "prompt_family": "Phase40-agent-invariant-lookup",
        "trigger": "agent invariant",
        "task_type": "agent_invariant_lookup",
        "output_artifact": "documentation_lookup",
        "workflow": "code_investigation.plan",
        "description": "Find agent-facing invariant, policy, or handoff documentation for a named behavior.",
        "natural_prompt": (
            "In <repo>, find agent invariant documentation for a named behavior. "
            "Read only. Return policy files, invariant statements, and evidence gaps."
        ),
    },
]


PHASE50_BATCH_C_SKILLS = [
    {
        "skill_id": "auth-check-locator",
        "route_key": "code.auth_check_lookup",
        "eval_case_id": "phase50_auth_check_lookup",
        "prompt_family": "Phase50-auth-check-lookup",
        "trigger": "auth check",
        "triggers": ["auth check", "auth checks", "permission guard", "permission guards", "access-control", "authorization"],
        "task_type": "auth_check_lookup",
        "output_artifact": "investigation_plan",
        "workflow": "code_investigation.plan",
        "description": "Locate authentication, authorization, permission, or access-control checks for a named behavior.",
        "natural_prompt": (
            "In <repo>, find auth or permission checks related to a named behavior. "
            "Read only. Return guard files, evidence, and related tests."
        ),
    },
    {
        "skill_id": "state-mutation-locator",
        "route_key": "code.state_mutation_lookup",
        "eval_case_id": "phase50_state_mutation_lookup",
        "prompt_family": "Phase50-state-mutation-lookup",
        "trigger": "state mutation",
        "triggers": [
            "state mutation",
            "state mutation sites",
            "mutation sites",
            "mutates state",
            "placed_order_id indexing",
            "indexing",
        ],
        "task_type": "state_mutation_lookup",
        "output_artifact": "investigation_plan",
        "workflow": "code_investigation.plan",
        "description": "Locate where a named behavior mutates in-memory state, indexes, caches, or persistent records.",
        "natural_prompt": (
            "In <repo>, find state mutation sites for a named behavior. "
            "Read only. Return mutation sites, evidence files, and related tests."
        ),
    },
    {
        "skill_id": "external-integration-locator",
        "route_key": "code.external_integration_lookup",
        "eval_case_id": "phase50_external_integration_lookup",
        "prompt_family": "Phase50-external-integration-lookup",
        "trigger": "external integration",
        "triggers": [
            "external integration",
            "integration points",
            "Coinbase order placement",
            "order placement client",
            "request boundaries",
        ],
        "task_type": "external_integration_lookup",
        "output_artifact": "investigation_plan",
        "workflow": "code_investigation.plan",
        "description": "Locate external API, exchange, webhook, SDK, or service integration points for a named behavior.",
        "natural_prompt": (
            "In <repo>, find external integration points for a named behavior. "
            "Read only. Return client files, request boundaries, and evidence gaps."
        ),
    },
    {
        "skill_id": "error-handling-path-locator",
        "route_key": "diagnostics.error_handling_path_lookup",
        "eval_case_id": "phase50_error_handling_path_lookup",
        "prompt_family": "Phase50-error-handling-path-lookup",
        "trigger": "error handling path",
        "triggers": [
            "error handling path",
            "error handling",
            "order placement failures",
            "exception handlers",
            "fallback logic",
        ],
        "task_type": "error_handling_path_lookup",
        "output_artifact": "investigation_plan",
        "workflow": "code_investigation.plan",
        "description": "Locate exception handling, retry, fallback, or failure-path logic for a named behavior.",
        "natural_prompt": (
            "In <repo>, find the error handling path for a named behavior. "
            "Read only. Return exception handlers, fallback logic, and related tests."
        ),
    },
]


PHASE61_BATCH_D_SKILLS = [
    {
        "skill_id": "handler-branch-tracer",
        "route_key": "code.handler_branch_trace",
        "eval_case_id": "phase61_handler_branch_trace",
        "prompt_family": "BatchD-handler-branch-trace",
        "trigger": "handler branch trace",
        "triggers": ["handler branch trace", "follow handler branch", "downstream snapshot function"],
        "task_type": "handler_branch_trace",
        "output_artifact": "request_flow_map",
        "workflow": "code_investigation.plan",
        "description": "Trace a named handler branch through downstream snapshot or service functions without mutating source.",
        "natural_prompt": (
            "In <repo>, follow a named handler branch through the downstream snapshot or service function. "
            "Read only. Return handler file, flow steps, evidence refs, and related tests."
        ),
    },
    {
        "skill_id": "table-schema-isolator",
        "route_key": "data.table_schema_only_lookup",
        "eval_case_id": "phase61_table_schema_only",
        "prompt_family": "BatchD-table-schema-only",
        "trigger": "table schema only",
        "triggers": ["table schema only", "schema field names", "exclude runtime fields"],
        "task_type": "table_schema_only_lookup",
        "output_artifact": "data_model_lookup",
        "workflow": "code_investigation.plan",
        "description": "Find only the named table schema and separate stored fields from runtime dictionary fields.",
        "natural_prompt": (
            "In <repo>, find only the named table schema. Read only. Return model files, schema field names, "
            "and source refs without mixing runtime dictionary fields."
        ),
    },
    {
        "skill_id": "runtime-entrypoint-disambiguator",
        "route_key": "code.runtime_entrypoint_disambiguation",
        "eval_case_id": "phase61_runtime_entrypoint_disambiguation",
        "prompt_family": "BatchD-runtime-entrypoint-disambiguation",
        "trigger": "runtime entrypoint",
        "triggers": ["runtime entrypoint", "trading engine entrypoint", "not dashboard server"],
        "task_type": "runtime_entrypoint_disambiguation",
        "output_artifact": "cli_entrypoint_lookup",
        "workflow": "code_investigation.plan",
        "description": "Locate a subsystem runtime entrypoint and distinguish it from adjacent service or UI entrypoints.",
        "natural_prompt": (
            "In <repo>, locate the runtime entrypoint for a named subsystem and distinguish it from adjacent service "
            "or UI entrypoints. Read only. Return command, source refs, and exclusions."
        ),
    },
    {
        "skill_id": "change-boundary-summarizer",
        "route_key": "planning.change_boundary_summary",
        "eval_case_id": "phase61_change_boundary_summary",
        "prompt_family": "BatchD-change-boundary-summary",
        "trigger": "change boundary",
        "triggers": ["files to touch", "files not to touch", "change boundary"],
        "task_type": "change_boundary_summary",
        "output_artifact": "change_surface_summary",
        "workflow": "code_investigation.plan",
        "description": "Summarize files to touch and files not to touch for a minimal safe behavior change.",
        "natural_prompt": (
            "In <repo>, identify files to touch and files not to touch for a minimal safe behavior change. "
            "Read only and stop before implementation. Return risks, gaps, and verification commands."
        ),
    },
]


class SkillBatchProposalError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "skill_batch_proposal_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class SkillBatchProposalRequest:
    config_root: Path | str = "."
    output_root: Path | str = ".agentic_controller"
    workflow: str = WORKFLOW_ID
    schema_version: int = SCHEMA_VERSION
    user_request: str = ""
    requested_batch_id: str | None = None
    role_id: str = "architect/default"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        config_root: Path,
        output_root: Path,
    ) -> "SkillBatchProposalRequest":
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


def bounded_string(value: Any, limit: int = 2000) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def slugify(value: str, *, fallback: str = "proposed-skill") -> str:
    words = re.findall(r"[a-z0-9]+", value.lower())
    stopwords = {
        "a",
        "add",
        "and",
        "batch",
        "build",
        "create",
        "for",
        "in",
        "of",
        "propose",
        "skill",
        "skills",
        "the",
        "to",
    }
    selected = [word for word in words if word not in stopwords][:5]
    slug = "-".join(selected) if selected else fallback
    return slug[:60].strip("-") or fallback


def validate_request(request: SkillBatchProposalRequest) -> None:
    if request.workflow != WORKFLOW_ID:
        raise SkillBatchProposalError("workflow must be skill_batch.propose.", code="unsupported_workflow")
    if request.schema_version != SCHEMA_VERSION:
        raise SkillBatchProposalError("schema_version must be 1.", code="unsupported_schema_version")
    if not isinstance(request.user_request, str) or not request.user_request.strip():
        raise SkillBatchProposalError("user_request is required.", code="missing_user_request", status=HTTPStatus.BAD_REQUEST)


def proposal_kind(user_request: str) -> str:
    text = user_request.lower()
    if "phase 61" in text or "phase 62" in text or "batch d" in text:
        return "phase61_batch_d"
    if "phase 50" in text or "batch c" in text:
        return "phase50_batch_c"
    if "phase 40" in text or "batch b" in text or "controlled l1/l2" in text:
        return "phase40_batch_b"
    if "duplicate" in text or "overlap" in text or "code explanation" in text:
        return "overlap_example"
    if "feature flag" in text or "feature flags" in text:
        return "feature_flag_lookup"
    return "general_read_only_lookup"


def one_skill_values(user_request: str, run_dir: Path) -> dict[str, Any]:
    kind = proposal_kind(user_request)
    if kind == "phase40_batch_b":
        raise SkillBatchProposalError(
            "phase40_batch_b uses skill_value_entries, not one_skill_values.",
            code="invalid_phase40_batch_generation",
        )
    if kind == "overlap_example":
        skill_id = "duplicate-code-explanation"
        route_key = "code.duplicate_explanation"
        eval_case_id = "duplicate_code_explanation"
        prompt_family = "duplicate-code-explanation"
        trigger = "explain"
        task_type = "code_explanation"
        output_artifact = "code_explanation"
        description = "Intentionally overlapping code explanation proposal used to prove do-not-admit behavior."
    elif kind == "feature_flag_lookup":
        skill_id = "feature-flag-locator"
        route_key = "config.feature_flag_lookup"
        eval_case_id = "feature_flag_lookup"
        prompt_family = "feature-flag-lookup"
        trigger = "feature flag"
        task_type = "feature_flag_lookup"
        output_artifact = "configuration_lookup"
        description = "Locate feature flag definitions and usages from bounded read-only evidence."
    else:
        base = slugify(user_request)
        skill_id = f"{base}-locator" if not base.endswith("locator") else base
        route_key = f"code.{skill_id.replace('-', '_')}"
        eval_case_id = skill_id.replace("-", "_")
        prompt_family = skill_id
        trigger = base.replace("-", " ")
        task_type = skill_id.replace("-", "_")
        output_artifact = "investigation_plan"
        description = "Locate bounded source evidence for a proposed read-only coding-agent prompt family."
    skill_path = run_dir / "draft-skills" / skill_id / "SKILL.md"
    return {
        "skill_id": skill_id,
        "skill_path": skill_path,
        "route_key": route_key,
        "eval_case_id": eval_case_id,
        "prompt_family": prompt_family,
        "trigger": trigger,
        "task_type": task_type,
        "output_artifact": output_artifact,
        "workflow": "code_investigation.plan",
        "description": description,
    }


def skill_value_entries(user_request: str, run_dir: Path) -> list[dict[str, Any]]:
    kind = proposal_kind(user_request)
    if kind in {"phase40_batch_b", "phase50_batch_c", "phase61_batch_d"}:
        source_by_kind = {
            "phase40_batch_b": PHASE40_BATCH_B_SKILLS,
            "phase50_batch_c": PHASE50_BATCH_C_SKILLS,
            "phase61_batch_d": PHASE61_BATCH_D_SKILLS,
        }
        source = source_by_kind[kind]
        values = []
        for item in source:
            value = dict(item)
            value["skill_path"] = run_dir / "draft-skills" / value["skill_id"] / "SKILL.md"
            if kind == "phase40_batch_b":
                value["failure_record_ref"] = (
                    "docs/SKILL_LIBRARY_SCALING_PLAN.md#phase-40-controlled-l1l2-skill-expansion-batch-b"
                )
            elif kind == "phase50_batch_c":
                value["failure_record_ref"] = (
                    "docs/SKILL_LIBRARY_SCALING_PLAN.md#phase-50-controlled-l1l2-skill-expansion-batch-c"
                )
            else:
                value["failure_record_ref"] = "docs/SKILL_SCALING_BATCH_D_PROPOSAL.md#candidate-skills"
                value["batch_doc_ref"] = "docs/SKILL_SCALING_BATCH_D_PROPOSAL.md"
            values.append(value)
        return values
    return [one_skill_values(user_request, run_dir)]


def draft_skill_body(values: dict[str, Any]) -> str:
    return (
        "---\n"
        f"name: {values['skill_id']}\n"
        f"description: {values['description']}\n"
        "---\n"
        "\n"
        f"# {values['skill_id']}\n"
        "\n"
        "Use this skill only after registry metadata selects it for the active workflow.\n"
        "\n"
        "Required behavior:\n"
        "\n"
        "- Keep the workflow read-only.\n"
        "- Cite bounded source or documentation evidence.\n"
        f"- Produce or support the `{values['output_artifact']}` artifact path.\n"
        "- Return gaps instead of guessing when the bounded evidence is incomplete.\n"
        "- Stop when the request falls outside this prompt family.\n"
    )


def draft_batch_manifest(request: SkillBatchProposalRequest, run_dir: Path) -> dict[str, Any]:
    value_entries = skill_value_entries(request.user_request, run_dir)
    for values in value_entries:
        write_text(values["skill_path"], draft_skill_body(values))
    first = value_entries[0]
    batch_id = request.requested_batch_id or f"proposed-{first['skill_id']}"
    batch_id = slugify(batch_id, fallback="proposed-skill-batch")
    doc_refs = ["README.skill-registry.md", "docs/SKILL_LIBRARY_SCALING_PLAN.md"]
    for values in value_entries:
        batch_doc_ref = values.get("batch_doc_ref")
        if isinstance(batch_doc_ref, str) and batch_doc_ref not in doc_refs:
            doc_refs.append(batch_doc_ref)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "skill_batch_manifest",
        "id": batch_id,
        "description": f"Draft skill batch proposal generated from: {bounded_string(request.user_request, 300)}",
        "doc_refs": doc_refs,
        "skills": [
            {
                "id": values["skill_id"],
                "path": str(values["skill_path"]),
                "version": "0.1.0",
                "owner": "agentic_agents",
                "description": values["description"],
                "compatibility": ["agent-skills-frontmatter", "openai-compatible-chat", "qwen-local"],
                "safety_level": "read_only_planning",
                "allowed_tools": [],
                "workflows": [values["workflow"]],
                "triggers": values.get("triggers") or [values["trigger"]],
                "workflow_priorities": {values["workflow"]: 1000},
                "capability_contract": {
                    "route_key": values["route_key"],
                    "task_types": [values["task_type"]],
                    "input_artifacts": ["natural_user_request"],
                    "output_artifacts": [values["output_artifact"]],
                    "approval_boundary": "none",
                    "mutation_policy": "no_repository_mutation",
                    "eval_case_ids": [values["eval_case_id"]],
                },
                "problem_solving_steps": [4],
                "eval_status": "draft",
                "evals": {
                    "fixtures": ["clear_request", "ambiguous_request", "unsafe_approval_bypass"],
                    "localhost_8000": "not_run",
                    "gateway_8300": "not_run",
                    "anythingllm": "not_run",
                },
                "failure_record_refs": [
                    values.get(
                        "failure_record_ref",
                        "docs/SKILL_LIBRARY_SCALING_PLAN.md#phase-50-controlled-l1l2-skill-expansion-batch-c",
                    )
                ],
            }
            for values in value_entries
        ],
        "eval_cases": [
            {
                "id": values["eval_case_id"],
                "prompt_family": values["prompt_family"],
                "natural_prompt": values.get("natural_prompt") or f"In <repo>, {request.user_request.strip()}",
                "expected_workflow": values["workflow"],
                "expected_artifacts": [values["output_artifact"]],
                "mutation_policy": "no_repository_mutation",
                "live_suite": "skill_registry_contract",
            }
            for values in value_entries
        ],
    }


def invoke_skill_batch_proposal(request: SkillBatchProposalRequest) -> InvocationResult:
    validate_request(request)
    output_root = Path(request.output_root).resolve()
    config_root = Path(request.config_root).resolve()
    run_id = f"skill-batch-proposal-{artifact_timestamp()}"
    run_dir = output_root / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, str] = {}
    request_artifact = {
        "kind": "skill_batch_proposal_request",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "user_request": bounded_string(request.user_request, 6000),
        "created_at": utc_now(),
    }
    write_json(run_dir / "request.json", request_artifact)
    artifacts["request"] = str(run_dir / "request.json")

    manifest = draft_batch_manifest(request, run_dir)
    write_json(run_dir / "batch.json", manifest)
    artifacts["draft_batch_manifest"] = str(run_dir / "batch.json")

    batch_report = build_skill_batch_report(
        config_root,
        run_dir / "batch.json",
        output_path=run_dir / "batch-validation-report.json",
    )
    artifacts["batch_validation_report"] = str(run_dir / "batch-validation-report.json")

    scale_report = build_skill_scale_report(
        config_root,
        output_path=run_dir / "scale-report.json",
    )
    artifacts["scale_report"] = str(run_dir / "scale-report.json")

    do_not_admit = []
    if batch_report["status"] != "passed":
        do_not_admit.append(
            {
                "source": "batch_validation",
                "errors": batch_report.get("errors", []),
                "action": "do_not_register_until_errors_are_resolved",
            }
        )
    if scale_report["summary"].get("do_not_admit_count"):
        do_not_admit.append(
            {
                "source": "scale_report",
                "conflicts": scale_report.get("do_not_admit", []),
                "action": "do_not_register_overlapping_skill",
            }
        )

    status = "ready" if not do_not_admit else "do_not_admit"
    summary = {
        "proposal_status": status,
        "skill_count": len(manifest["skills"]),
        "eval_case_count": len(manifest["eval_cases"]),
        "batch_validation_status": batch_report["status"],
        "scale_report_status": scale_report["status"],
        "do_not_admit_count": len(do_not_admit),
        "runtime_registry_changed": False,
        "next_action": "review_draft_manifest" if status == "ready" else "revise_or_reject_overlap",
    }
    proposal = {
        "kind": "skill_batch_proposal",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": status,
        "summary": summary,
        "draft_batch_manifest": manifest,
        "batch_validation": {
            "status": batch_report["status"],
            "summary": batch_report.get("summary", {}),
            "errors": batch_report.get("errors", []),
        },
        "scale_validation": {
            "status": scale_report["status"],
            "summary": scale_report.get("summary", {}),
        },
        "do_not_admit": do_not_admit,
        "artifacts": artifacts,
        "created_at": utc_now(),
    }
    write_json(run_dir / "skill-batch-proposal.json", proposal)
    artifacts["skill_batch_proposal"] = str(run_dir / "skill-batch-proposal.json")

    run_state = {
        "kind": "skill_batch_proposal_run_state",
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
        "kind": "skill_batch_proposal_report",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "summary": summary,
        "proposal": proposal,
        "warnings": [],
        "artifacts": artifacts,
    }
    return InvocationResult(
        workflow=WORKFLOW_ID,
        status=WorkflowStatus.COMPLETED,
        artifact_paths=artifacts,
        summary_text=f"{WORKFLOW_ID} completed with proposal_status={status}",
        failures=[],
        resume_key={"schema_version": SCHEMA_VERSION, "run_state": str(run_dir / "run-state.json")},
        report=report,
        run_id=run_id,
    )
