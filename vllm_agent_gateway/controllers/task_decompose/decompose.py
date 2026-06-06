"""Read-only deterministic multi-step task decomposition workflow."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus


WORKFLOW_ID = "task.decompose"
SCHEMA_VERSION = 1
DEFAULT_OUTPUT_DIR = "task-decompositions"
MAX_SELECTED_SKILLS = 5
MAX_SELECTED_TOOLS = 5


class TaskDecompositionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "task_decomposition_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class TaskDecompositionRequest:
    config_root: Path | str = "."
    target_root: Path | str = "."
    output_root: Path | str = ".agentic_controller"
    workflow: str = WORKFLOW_ID
    schema_version: int = SCHEMA_VERSION
    user_request: str = ""
    role_id: str = "architect/default"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        config_root: Path,
        target_root: Path,
        output_root: Path,
    ) -> "TaskDecompositionRequest":
        values: dict[str, Any] = {
            "config_root": config_root,
            "target_root": target_root,
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


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TaskDecompositionError(f"Missing {label}: {path}", code=f"missing_{label.replace(' ', '_')}") from exc
    except json.JSONDecodeError as exc:
        raise TaskDecompositionError(f"Invalid {label} JSON: {exc}", code=f"invalid_{label.replace(' ', '_')}") from exc
    if not isinstance(value, dict):
        raise TaskDecompositionError(f"{label} must contain a JSON object.", code=f"invalid_{label.replace(' ', '_')}")
    return value


def lower_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def load_workflows(config_root: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json_object(config_root / "runtime" / "workflows.json", "workflow catalog")
    workflows = manifest.get("workflows")
    if not isinstance(workflows, list):
        raise TaskDecompositionError("runtime/workflows.json must contain a workflows list.", code="invalid_workflow_catalog")
    return {item["id"]: item for item in workflows if isinstance(item, dict) and isinstance(item.get("id"), str)}


def load_skills(config_root: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json_object(config_root / "runtime" / "skills.json", "skill catalog")
    skills = manifest.get("skills")
    if not isinstance(skills, list):
        raise TaskDecompositionError("runtime/skills.json must contain a skills list.", code="invalid_skill_catalog")
    return {item["id"]: item for item in skills if isinstance(item, dict) and isinstance(item.get("id"), str)}


def load_tools(config_root: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json_object(config_root / "runtime" / "tools.json", "tool catalog")
    tools = manifest.get("tools")
    if not isinstance(tools, list):
        raise TaskDecompositionError("runtime/tools.json must contain a tools list.", code="invalid_tool_catalog")
    return {item["id"]: item for item in tools if isinstance(item, dict) and isinstance(item.get("id"), str)}


def workflow_tool_ids(workflow: dict[str, Any], limit: int = MAX_SELECTED_TOOLS) -> list[str]:
    values = string_list(workflow.get("controller_tool_ids"))
    conditional = workflow.get("conditional_controller_tool_ids")
    if isinstance(conditional, list):
        for rule in conditional:
            if isinstance(rule, dict):
                values.extend(string_list(rule.get("tool_ids")))
    deduped = sorted(set(values))
    return deduped[:limit]


def skill_ids_for_workflow(
    skills: dict[str, dict[str, Any]],
    workflow_id: str,
    request_text: str,
    *,
    limit: int = MAX_SELECTED_SKILLS,
) -> list[str]:
    scored: list[tuple[int, str]] = []
    words = set(re.findall(r"[a-z0-9_]+", request_text))
    for skill_id, skill in skills.items():
        if workflow_id not in string_list(skill.get("workflows")):
            continue
        if skill.get("eval_status") == "deprecated":
            continue
        triggers = string_list(skill.get("triggers"))
        hit_count = sum(1 for trigger in triggers if trigger.lower() in request_text or trigger.lower() in words)
        priority = 0
        priorities = skill.get("workflow_priorities")
        if isinstance(priorities, dict) and isinstance(priorities.get(workflow_id), int):
            priority = int(priorities[workflow_id])
        scored.append((hit_count * 100 + priority, skill_id))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [skill_id for score, skill_id in scored if score >= 0][:limit]


def validate_request(request: TaskDecompositionRequest) -> None:
    if request.workflow != WORKFLOW_ID:
        raise TaskDecompositionError("workflow must be task.decompose.", code="unsupported_workflow")
    if request.schema_version != SCHEMA_VERSION:
        raise TaskDecompositionError("schema_version must be 1.", code="unsupported_schema_version")
    if not isinstance(request.user_request, str) or not request.user_request.strip():
        raise TaskDecompositionError("user_request is required.", code="missing_user_request", status=HTTPStatus.BAD_REQUEST)
    if not Path(request.target_root).resolve().is_dir():
        raise TaskDecompositionError("target_root must be an existing directory.", code="invalid_target_root")


def is_ambiguous_request(user_request: str) -> bool:
    text = lower_text(user_request)
    meaningful = re.findall(r"[a-z0-9_]+", text)
    if len(meaningful) < 5:
        return True
    return bool(re.fullmatch(r"(fix|change|update|refactor|investigate)\s+(it|this|that)", text))


def classify_prompt_family(user_request: str) -> tuple[str, str]:
    text = lower_text(user_request)
    if any(term in text for term in ("refactor", "single path", "one code path", "consolidate", "duplicate path")):
        return "multi_step_refactor", "high"
    if any(term in text for term in ("failing test", "pytest failure", "fix test", "test failure")):
        return "failing_test_remediation", "medium"
    if any(term in text for term in ("add", "create", "implement", "build", "feature")):
        return "feature_or_small_change", "medium"
    if any(term in text for term in ("investigate", "diagnose", "trace", "map")):
        return "multi_step_investigation", "low"
    return "general_development_task", "medium"


def package(
    package_id: str,
    *,
    title: str,
    workflow_id: str,
    objective: str,
    depends_on: list[str],
    workflows: dict[str, dict[str, Any]],
    skills: dict[str, dict[str, Any]],
    request_text: str,
    approval_required: bool,
    expected_artifacts: list[str],
) -> dict[str, Any]:
    workflow = workflows[workflow_id]
    return {
        "id": package_id,
        "title": title,
        "workflow_id": workflow_id,
        "objective": objective,
        "depends_on": depends_on,
        "selected_tools": workflow_tool_ids(workflow),
        "selected_skills": skill_ids_for_workflow(skills, workflow_id, request_text),
        "approval_required": approval_required,
        "mutation_policy": "no_repository_mutation" if not approval_required else "draft_only_until_approval",
        "expected_artifacts": expected_artifacts,
        "uncertainty": [
            {
                "code": "repo_evidence_not_read",
                "reason": "task.decompose does not inspect source files; this package must gather or validate repo evidence.",
            }
        ],
    }


def build_work_packages(
    *,
    family: str,
    workflows: dict[str, dict[str, Any]],
    skills: dict[str, dict[str, Any]],
    request_text: str,
) -> list[dict[str, Any]]:
    packages: list[dict[str, Any]] = []
    if family == "multi_step_refactor" and "refactor.single_path" in workflows:
        packages.append(
            package(
                "WP1",
                title="Investigate single-path refactor surface",
                workflow_id="refactor.single_path",
                objective="Find the logic beginning point, existing paths, related tests, and risk before packet design.",
                depends_on=[],
                workflows=workflows,
                skills=skills,
                request_text=request_text,
                approval_required=False,
                expected_artifacts=["investigation_plan", "refactor_plan"],
            )
        )
    else:
        packages.append(
            package(
                "WP1",
                title="Gather bounded repository evidence",
                workflow_id="code_investigation.plan",
                objective="Find beginning points, participating files, related tests, risks, and verification commands.",
                depends_on=[],
                workflows=workflows,
                skills=skills,
                request_text=request_text,
                approval_required=False,
                expected_artifacts=["investigation_plan"],
            )
        )
    packages.append(
        package(
            "WP2",
            title="Draft implementation packet plan",
            workflow_id="execution_planning.plan",
            objective="Convert approved evidence into bounded draft packet candidates without applying source changes.",
            depends_on=["WP1"],
            workflows=workflows,
            skills=skills,
            request_text=request_text,
            approval_required=True,
            expected_artifacts=["packet_file", "verification_plan", "implementation_draft"],
        )
    )
    if family in {"failing_test_remediation", "feature_or_small_change", "multi_step_refactor"}:
        packages.append(
            {
                "id": "GATE3",
                "title": "Approval gate before mutation",
                "workflow_id": None,
                "objective": "Stop before source mutation. Phase 54 is the approved scope for controlled apply behavior.",
                "depends_on": ["WP2"],
                "selected_tools": [],
                "selected_skills": [],
                "approval_required": True,
                "mutation_policy": "repository_mutation_blocked_in_phase_53",
                "expected_artifacts": ["approval_record"],
                "uncertainty": [
                    {
                        "code": "apply_workflow_not_registered",
                        "reason": "No registered source-apply workflow exists in Phase 53; do not invent one.",
                    }
                ],
            }
        )
    return packages


def dependency_edges(work_packages: list[dict[str, Any]]) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    for item in work_packages:
        package_id = item.get("id")
        for dependency in string_list(item.get("depends_on")):
            if isinstance(package_id, str):
                edges.append({"from": dependency, "to": package_id})
    return edges


def selected_values(work_packages: list[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    for item in work_packages:
        for value in string_list(item.get(key)):
            if value not in values:
                values.append(value)
    return values


def selected_workflow_ids(work_packages: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for item in work_packages:
        workflow_id = item.get("workflow_id")
        if isinstance(workflow_id, str) and workflow_id and workflow_id not in values:
            values.append(workflow_id)
    return values


def validate_registered_references(plan: dict[str, Any], workflows: dict[str, dict[str, Any]], skills: dict[str, dict[str, Any]], tools: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for item in plan.get("work_packages", []):
        if not isinstance(item, dict):
            continue
        workflow_id = item.get("workflow_id")
        if isinstance(workflow_id, str) and workflow_id not in workflows:
            errors.append({"code": "unknown_workflow", "value": workflow_id})
        for skill_id in string_list(item.get("selected_skills")):
            if skill_id not in skills:
                errors.append({"code": "unknown_skill", "value": skill_id})
        for tool_id in string_list(item.get("selected_tools")):
            if tool_id not in tools:
                errors.append({"code": "unknown_tool", "value": tool_id})
    return errors


def build_decomposition(request: TaskDecompositionRequest) -> dict[str, Any]:
    config_root = Path(request.config_root).resolve()
    workflows = load_workflows(config_root)
    skills = load_skills(config_root)
    tools = load_tools(config_root)
    text = lower_text(request.user_request)
    family, risk_level = classify_prompt_family(request.user_request)

    if is_ambiguous_request(request.user_request):
        return {
            "kind": "task_decomposition",
            "schema_version": SCHEMA_VERSION,
            "workflow": WORKFLOW_ID,
            "status": "needs_clarification",
            "prompt_family": "ambiguous",
            "risk_level": "unknown",
            "target_root": str(Path(request.target_root).resolve()),
            "user_request": request.user_request,
            "work_packages": [],
            "dependency_edges": [],
            "selected_workflow_ids": [],
            "selected_skill_ids": [],
            "selected_tool_ids": [],
            "approval_gates": [],
            "verification_strategy": {
                "status": "blocked",
                "commands": [],
                "proof_gates": [],
                "reason": "The task is too ambiguous to decompose safely.",
            },
            "uncertainty": [
                {
                    "code": "ambiguous_task",
                    "reason": "Name the behavior, failing test, file, or desired outcome before decomposition.",
                }
            ],
            "blockers": [{"reason": "ambiguous_task", "message": "Clarify the requested behavior or outcome."}],
            "next_action": "ask_blocking_question",
            "mutation_policy": "no_repository_mutation",
            "runtime_registry_changed": False,
            "target_repository_changed": False,
        }

    work_packages = build_work_packages(family=family, workflows=workflows, skills=skills, request_text=text)
    plan = {
        "kind": "task_decomposition",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "status": "ready",
        "prompt_family": family,
        "risk_level": risk_level,
        "target_root": str(Path(request.target_root).resolve()),
        "user_request": request.user_request,
        "work_packages": work_packages,
        "dependency_edges": dependency_edges(work_packages),
        "selected_workflow_ids": selected_workflow_ids(work_packages),
        "selected_skill_ids": selected_values(work_packages, "selected_skills"),
        "selected_tool_ids": selected_values(work_packages, "selected_tools"),
        "approval_gates": [
            {
                "id": "approval_before_packet_design",
                "required_before": "execution_planning.plan",
                "approval_scope": "packet_design_only",
            },
            {
                "id": "approval_before_repository_mutation",
                "required_before": "any_source_apply",
                "approval_scope": "not_available_in_phase_53",
            },
        ],
        "verification_strategy": {
            "status": "pending_repo_evidence",
            "commands": [],
            "proof_gates": [
                "run WP1 read-only evidence workflow",
                "derive smallest related test command from WP1 artifacts",
                "run full regression only after an approved implementation phase changes code",
            ],
            "reason": "No source files were read by task.decompose.",
        },
        "uncertainty": [
            {
                "code": "repo_evidence_not_read",
                "reason": "This workflow uses registry metadata only. Run the first work package to gather source evidence.",
            }
        ],
        "blockers": [],
        "next_action": "execute_read_only",
        "mutation_policy": "no_repository_mutation",
        "runtime_registry_changed": False,
        "target_repository_changed": False,
    }
    reference_errors = validate_registered_references(plan, workflows, skills, tools)
    if reference_errors:
        plan["status"] = "blocked"
        plan["blockers"] = [{"reason": "unregistered_reference", "message": json.dumps(reference_errors, ensure_ascii=True)}]
        plan["next_action"] = "none"
    return plan


def summary_for(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "decomposition_status": plan.get("status"),
        "prompt_family": plan.get("prompt_family"),
        "risk_level": plan.get("risk_level"),
        "package_count": len(plan.get("work_packages", [])) if isinstance(plan.get("work_packages"), list) else 0,
        "selected_workflow_ids": plan.get("selected_workflow_ids", []),
        "selected_skill_ids": plan.get("selected_skill_ids", []),
        "selected_tool_ids": plan.get("selected_tool_ids", []),
        "approval_gate_count": len(plan.get("approval_gates", [])) if isinstance(plan.get("approval_gates"), list) else 0,
        "uncertainty_count": len(plan.get("uncertainty", [])) if isinstance(plan.get("uncertainty"), list) else 0,
        "next_action": plan.get("next_action"),
        "runtime_registry_changed": False,
        "target_repository_changed": False,
    }


def invoke_task_decomposition(request: TaskDecompositionRequest) -> InvocationResult:
    validate_request(request)
    output_root = Path(request.output_root).resolve()
    run_id = f"task-decomposition-{artifact_timestamp()}"
    run_dir = output_root / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    request_artifact = {
        "kind": "task_decomposition_request",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "target_root": str(Path(request.target_root).resolve()),
        "user_request": request.user_request,
        "metadata": request.metadata,
        "created_at": utc_now(),
    }
    write_json(run_dir / "request.json", request_artifact)

    plan = build_decomposition(request)
    plan["run_id"] = run_id
    plan["created_at"] = utc_now()
    write_json(run_dir / "task-decomposition.json", plan)
    summary = summary_for(plan)
    status = WorkflowStatus.COMPLETED
    artifacts = {
        "request": str(run_dir / "request.json"),
        "task_decomposition": str(run_dir / "task-decomposition.json"),
    }
    run_state = {
        "kind": "task_decomposition_run_state",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": status.value,
        "summary": summary,
        "artifacts": artifacts,
        "updated_at": utc_now(),
    }
    write_json(run_dir / "run-state.json", run_state)
    artifacts["run_state"] = str(run_dir / "run-state.json")
    report = {
        "kind": "task_decomposition_report",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": status.value,
        "summary": summary,
        "task_decomposition": plan,
        "artifacts": artifacts,
        "warnings": [],
        "failures": [],
    }
    return InvocationResult(
        workflow=WORKFLOW_ID,
        status=status,
        artifact_paths=artifacts,
        summary_text=f"{WORKFLOW_ID} completed with decomposition_status={summary['decomposition_status']}",
        failures=[],
        resume_key={"schema_version": SCHEMA_VERSION, "run_state": str(run_dir / "run-state.json")},
        report=report,
        run_id=run_id,
    )
