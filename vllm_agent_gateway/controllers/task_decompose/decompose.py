"""Read-only deterministic multi-step task decomposition workflow."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from enum import Enum
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus


WORKFLOW_ID = "task.decompose"
SCHEMA_VERSION = 1
WORK_PACKAGE_SCHEMA_VERSION = 2
DEFAULT_OUTPUT_DIR = "task-decompositions"
MAX_SELECTED_SKILLS = 5
MAX_SELECTED_TOOLS = 5


class DecompositionStatus(str, Enum):
    READY = "ready"
    NEEDS_CLARIFICATION = "needs_clarification"
    BLOCKED = "blocked"


class PromptFamily(str, Enum):
    AMBIGUOUS = "ambiguous"
    ADVANCED_REFACTOR_DEFERRED = "advanced_refactor_deferred"
    FAILING_TEST_REMEDIATION = "failing_test_remediation"
    FEATURE_OR_SMALL_CHANGE = "feature_or_small_change"
    MULTI_STEP_INVESTIGATION = "multi_step_investigation"
    GENERAL_DEVELOPMENT_TASK = "general_development_task"


class RiskLevel(str, Enum):
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WorkPackageStage(str, Enum):
    INVESTIGATION = "investigation"
    PREP_APPROVAL_GATE = "prep_approval_gate"
    IMPLEMENTATION_PREP = "implementation_prep"
    VERIFICATION = "verification"
    TERMINAL_STOP = "terminal_stop"


class MutationPolicy(str, Enum):
    READ_ONLY = "read_only_no_source_mutation"
    DRAFT_ONLY_UNTIL_APPROVAL = "draft_only_until_approval"
    MUTATION_BLOCKED = "repository_mutation_blocked"
    UNSUPPORTED_DEFERRED = "unsupported_deferred_until_phase_105"


class NextAction(str, Enum):
    EXECUTE_READ_ONLY = "execute_read_only"
    ASK_BLOCKING_QUESTION = "ask_blocking_question"
    NONE = "none"


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


def is_advanced_refactor_request(user_request: str) -> bool:
    text = lower_text(user_request)
    explicit_advanced_terms = (
        "single path",
        "one code path",
        "only one path",
        "only one code path",
        "consolidate paths",
        "duplicate path",
        "broad refactor",
        "whole subsystem",
    )
    return any(term in text for term in explicit_advanced_terms)


def classify_prompt_family(user_request: str) -> tuple[PromptFamily, RiskLevel]:
    text = lower_text(user_request)
    if is_advanced_refactor_request(user_request):
        return PromptFamily.ADVANCED_REFACTOR_DEFERRED, RiskLevel.HIGH
    if any(term in text for term in ("failing test", "pytest failure", "fix test", "test failure")):
        return PromptFamily.FAILING_TEST_REMEDIATION, RiskLevel.MEDIUM
    if any(term in text for term in ("add", "create", "implement", "build", "feature")):
        return PromptFamily.FEATURE_OR_SMALL_CHANGE, RiskLevel.MEDIUM
    if any(term in text for term in ("investigate", "diagnose", "trace", "map")):
        return PromptFamily.MULTI_STEP_INVESTIGATION, RiskLevel.LOW
    return PromptFamily.GENERAL_DEVELOPMENT_TASK, RiskLevel.MEDIUM


def package(
    package_id: str,
    *,
    title: str,
    workflow_id: str,
    stage: WorkPackageStage,
    objective: str,
    depends_on: list[str],
    blocks: list[str],
    workflows: dict[str, dict[str, Any]],
    skills: dict[str, dict[str, Any]],
    request_text: str,
    approval_required: bool,
    approval_scope: str,
    mutation_policy: MutationPolicy,
    entry_conditions: list[str],
    exit_criteria: list[str],
    stop_conditions: list[dict[str, str]],
    expected_artifacts: list[str],
    verification: dict[str, Any],
) -> dict[str, Any]:
    workflow = workflows[workflow_id]
    return {
        "id": package_id,
        "title": title,
        "stage": stage.value,
        "workflow_id": workflow_id,
        "objective": objective,
        "depends_on": depends_on,
        "dependency_contract": {
            "depends_on": depends_on,
            "blocks": blocks,
            "can_start_when": "all_dependencies_complete",
            "parallelizable": False,
        },
        "selected_tools": workflow_tool_ids(workflow),
        "selected_skills": skill_ids_for_workflow(skills, workflow_id, request_text),
        "approval_gate": {
            "required": approval_required,
            "scope": approval_scope,
            "decision_options": ["approve", "deny"] if approval_required else [],
        },
        "approval_required": approval_required,
        "mutation_policy": mutation_policy.value,
        "entry_conditions": entry_conditions,
        "exit_criteria": exit_criteria,
        "stop_conditions": stop_conditions,
        "expected_artifacts": expected_artifacts,
        "verification": verification,
        "uncertainty": [
            {
                "code": "repo_evidence_not_read",
                "reason": "task.decompose does not inspect source files; this package must gather or validate repo evidence.",
            }
        ],
    }


def gate_package(
    package_id: str,
    *,
    title: str,
    stage: WorkPackageStage,
    objective: str,
    depends_on: list[str],
    blocks: list[str],
    approval_scope: str,
    decision_options: list[str],
    mutation_policy: MutationPolicy,
    entry_conditions: list[str],
    exit_criteria: list[str],
    stop_conditions: list[dict[str, str]],
    expected_artifacts: list[str],
    verification: dict[str, Any],
    uncertainty: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "id": package_id,
        "title": title,
        "stage": stage.value,
        "workflow_id": None,
        "objective": objective,
        "depends_on": depends_on,
        "dependency_contract": {
            "depends_on": depends_on,
            "blocks": blocks,
            "can_start_when": "all_dependencies_complete",
            "parallelizable": False,
        },
        "selected_tools": [],
        "selected_skills": [],
        "approval_gate": {
            "required": True,
            "scope": approval_scope,
            "decision_options": decision_options,
        },
        "approval_required": True,
        "mutation_policy": mutation_policy.value,
        "entry_conditions": entry_conditions,
        "exit_criteria": exit_criteria,
        "stop_conditions": stop_conditions,
        "expected_artifacts": expected_artifacts,
        "verification": verification,
        "uncertainty": uncertainty or [],
    }


def manual_package(
    package_id: str,
    *,
    title: str,
    stage: WorkPackageStage,
    objective: str,
    depends_on: list[str],
    blocks: list[str],
    mutation_policy: MutationPolicy,
    entry_conditions: list[str],
    exit_criteria: list[str],
    stop_conditions: list[dict[str, str]],
    expected_artifacts: list[str],
    verification: dict[str, Any],
    uncertainty: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "id": package_id,
        "title": title,
        "stage": stage.value,
        "workflow_id": None,
        "objective": objective,
        "depends_on": depends_on,
        "dependency_contract": {
            "depends_on": depends_on,
            "blocks": blocks,
            "can_start_when": "all_dependencies_complete",
            "parallelizable": False,
        },
        "selected_tools": [],
        "selected_skills": [],
        "approval_gate": {
            "required": False,
            "scope": "none",
            "decision_options": [],
        },
        "approval_required": False,
        "mutation_policy": mutation_policy.value,
        "entry_conditions": entry_conditions,
        "exit_criteria": exit_criteria,
        "stop_conditions": stop_conditions,
        "expected_artifacts": expected_artifacts,
        "verification": verification,
        "uncertainty": uncertainty or [],
    }


def advanced_refactor_deferred_package() -> list[dict[str, Any]]:
    return [
        manual_package(
            "DEFER1",
            title="Advanced refactor orchestration deferred",
            stage=WorkPackageStage.TERMINAL_STOP,
            objective="Stop broad single-path refactor orchestration until the Phase 105 readiness gate is explicitly satisfied.",
            depends_on=[],
            blocks=[],
            mutation_policy=MutationPolicy.UNSUPPORTED_DEFERRED,
            entry_conditions=["request asks for broad single-path or one-code-path refactor orchestration"],
            exit_criteria=["advanced refactor readiness is explicitly approved in Phase 105"],
            stop_conditions=[
                {
                    "code": "phase_105_not_ready",
                    "reason": "Do not create implementation prep or source-apply packages for broad refactor prompts yet.",
                },
                {
                    "code": "unsupported_refactor_orchestration",
                    "reason": "Use smaller L1/L2 investigation and change-surface prompts before advanced orchestration.",
                },
            ],
            expected_artifacts=[],
            verification={
                "commands": [],
                "proof_gates": ["confirm no implementation packet artifacts were created"],
                "status": "blocked_deferred_scope",
            },
            uncertainty=[
                {
                    "code": "advanced_refactor_deferred",
                    "reason": "Phase 102 plans multi-step work packages but does not enable broad refactor execution.",
                }
            ],
        )
    ]


def build_work_packages(
    *,
    family: PromptFamily,
    workflows: dict[str, dict[str, Any]],
    skills: dict[str, dict[str, Any]],
    request_text: str,
) -> list[dict[str, Any]]:
    if family == PromptFamily.ADVANCED_REFACTOR_DEFERRED:
        return advanced_refactor_deferred_package()

    packages: list[dict[str, Any]] = []
    packages.append(
        package(
            "WP1",
            title="Gather bounded repository evidence",
            workflow_id="code_investigation.plan",
            stage=WorkPackageStage.INVESTIGATION,
            objective="Find beginning points, participating files, related tests, risks, and verification commands.",
            depends_on=[],
            blocks=["GATE2"],
            workflows=workflows,
            skills=skills,
            request_text=request_text,
            approval_required=False,
            approval_scope="none",
            mutation_policy=MutationPolicy.READ_ONLY,
            entry_conditions=["request is specific enough to locate behavior, file, test, or desired outcome"],
            exit_criteria=[
                "entry point or explicit evidence gap is recorded",
                "related files and tests are bounded",
                "smallest useful verification command is proposed",
            ],
            stop_conditions=[
                {
                    "code": "no_repo_evidence",
                    "reason": "Stop if the investigation cannot identify evidence for the requested behavior.",
                },
                {
                    "code": "scope_too_large",
                    "reason": "Stop if the task expands beyond a bounded L1/L2 workflow or approved package.",
                },
            ],
            expected_artifacts=["investigation_plan"],
            verification={
                "commands": [],
                "proof_gates": ["inspect investigation evidence", "confirm selected tests are relevant"],
                "status": "pending_wp1_execution",
            },
        )
    )
    packages.append(
        gate_package(
            "GATE2",
            title="Approval gate before implementation prep",
            stage=WorkPackageStage.PREP_APPROVAL_GATE,
            objective="Stop after investigation until the caller approves draft-only implementation planning from the specific WP1 result.",
            depends_on=["WP1"],
            blocks=["WP3"],
            approval_scope="packet_design_only",
            decision_options=["approve_packet_design", "deny", "request_more_investigation"],
            mutation_policy=MutationPolicy.READ_ONLY,
            entry_conditions=["WP1 evidence has been reviewed"],
            exit_criteria=["approval decision is recorded with target root and source run identity"],
            stop_conditions=[
                {
                    "code": "missing_packet_design_approval",
                    "reason": "Stop until approval.status=approved_for_packet_design is present.",
                },
                {
                    "code": "evidence_not_reviewed",
                    "reason": "Stop if WP1 evidence has not been reviewed by the caller.",
                },
            ],
            expected_artifacts=["approval_record"],
            verification={
                "commands": [],
                "proof_gates": ["confirm approval is scoped to WP1 run identity"],
                "status": "waiting_for_approval",
            },
        )
    )
    packages.append(
        package(
            "WP3",
            title="Draft implementation packet plan",
            workflow_id="execution_planning.plan",
            stage=WorkPackageStage.IMPLEMENTATION_PREP,
            objective="Convert approved evidence into bounded draft packet candidates without applying source changes.",
            depends_on=["GATE2"],
            blocks=["WP4"],
            workflows=workflows,
            skills=skills,
            request_text=request_text,
            approval_required=False,
            approval_scope="preapproved_by_gate2",
            mutation_policy=MutationPolicy.DRAFT_ONLY_UNTIL_APPROVAL,
            entry_conditions=[
                "WP1 completed with bounded evidence",
                "GATE2 approval is recorded for packet design only",
            ],
            exit_criteria=[
                "packet objective is narrow",
                "candidate operations are draft-only",
                "verification commands are attached to the packet design",
            ],
            stop_conditions=[
                {
                    "code": "missing_packet_design_approval",
                    "reason": "Stop if approval.status=approved_for_packet_design is missing or references the wrong run.",
                },
                {
                    "code": "source_apply_requested",
                    "reason": "Stop if the request asks to mutate source files during implementation prep.",
                },
            ],
            expected_artifacts=["packet_file", "verification_plan", "implementation_draft"],
            verification={
                "commands": [],
                "proof_gates": ["inspect packet preview", "confirm no source files changed"],
                "status": "pending_approval_and_wp3_execution",
            },
        )
    )
    packages.append(
        manual_package(
            "WP4",
            title="Verify package readiness",
            stage=WorkPackageStage.VERIFICATION,
            objective="Review the draft plan, attached verification commands, and mutation proof before any apply decision.",
            depends_on=["WP3"],
            blocks=["STOP5"],
            mutation_policy=MutationPolicy.READ_ONLY,
            entry_conditions=["WP3 draft package plan exists"],
            exit_criteria=[
                "verification commands are present or an explicit gap is recorded",
                "draft package remains source-non-mutating",
                "review result is ready for an apply approval decision",
            ],
            stop_conditions=[
                {
                    "code": "verification_missing",
                    "reason": "Stop if no smallest useful verification command or explicit verification gap exists.",
                },
                {
                    "code": "draft_mutated_source",
                    "reason": "Stop if implementation prep changed repository files.",
                },
            ],
            expected_artifacts=["verification_review"],
            verification={
                "commands": [],
                "proof_gates": ["inspect WP3 verification plan", "confirm target_repository_changed=false"],
                "status": "pending_wp3_execution",
            },
        )
    )
    packages.append(
        gate_package(
            "STOP5",
            title="Stop before repository mutation",
            stage=WorkPackageStage.TERMINAL_STOP,
            objective="End this decomposition before source mutation; source apply requires a separate approved implementation workflow.",
            depends_on=["WP4"],
            blocks=[],
            approval_scope="repository_mutation",
            decision_options=["approve_apply_in_disposable_copy", "deny", "request_new_plan"],
            mutation_policy=MutationPolicy.MUTATION_BLOCKED,
            entry_conditions=["WP4 readiness review is complete", "caller asks to continue beyond draft-only prep"],
            exit_criteria=["separate source-apply approval is recorded with matching target root and run id"],
            stop_conditions=[
                {
                    "code": "missing_apply_approval",
                    "reason": "Stop until a separate source-apply approval is present.",
                },
                {
                    "code": "target_mismatch",
                    "reason": "Stop if the approval target differs from the planned target root.",
                },
            ],
            expected_artifacts=["approval_record"],
            verification={
                "commands": [],
                "proof_gates": ["confirm approval run identity", "confirm mutation policy before apply"],
                "status": "pending_separate_apply_approval",
            },
            uncertainty=[
                {
                    "code": "source_apply_not_part_of_task_decompose",
                    "reason": "task.decompose only plans; it does not apply repository changes.",
                }
            ],
        )
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


def approval_gates_for(work_packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gates: list[dict[str, Any]] = []
    for item in work_packages:
        if not isinstance(item, dict):
            continue
        gate = item.get("approval_gate")
        if not isinstance(gate, dict) or gate.get("required") is not True:
            continue
        package_id = item.get("id")
        if not isinstance(package_id, str):
            continue
        gates.append(
            {
                "id": f"approval_for_{package_id.lower()}",
                "package_id": package_id,
                "required_before": item.get("workflow_id") or package_id,
                "approval_scope": gate.get("scope"),
                "decision_options": gate.get("decision_options")
                if isinstance(gate.get("decision_options"), list)
                else [],
            }
        )
    return gates


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
            "work_package_schema_version": WORK_PACKAGE_SCHEMA_VERSION,
            "workflow": WORKFLOW_ID,
            "status": DecompositionStatus.NEEDS_CLARIFICATION.value,
            "prompt_family": PromptFamily.AMBIGUOUS.value,
            "risk_level": RiskLevel.UNKNOWN.value,
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
            "next_action": NextAction.ASK_BLOCKING_QUESTION.value,
            "mutation_policy": MutationPolicy.READ_ONLY.value,
            "runtime_registry_changed": False,
            "target_repository_changed": False,
        }

    work_packages = build_work_packages(family=family, workflows=workflows, skills=skills, request_text=text)
    is_deferred_advanced_refactor = family == PromptFamily.ADVANCED_REFACTOR_DEFERRED
    plan = {
        "kind": "task_decomposition",
        "schema_version": SCHEMA_VERSION,
        "work_package_schema_version": WORK_PACKAGE_SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "status": DecompositionStatus.BLOCKED.value if is_deferred_advanced_refactor else DecompositionStatus.READY.value,
        "prompt_family": family.value,
        "risk_level": risk_level.value,
        "target_root": str(Path(request.target_root).resolve()),
        "user_request": request.user_request,
        "work_packages": work_packages,
        "dependency_edges": dependency_edges(work_packages),
        "selected_workflow_ids": selected_workflow_ids(work_packages),
        "selected_skill_ids": selected_values(work_packages, "selected_skills"),
        "selected_tool_ids": selected_values(work_packages, "selected_tools"),
        "approval_gates": approval_gates_for(work_packages),
        "verification_strategy": {
            "status": "blocked_deferred_scope" if is_deferred_advanced_refactor else "pending_repo_evidence",
            "commands": [],
            "proof_gates": (
                ["confirm no implementation packet artifacts were created"]
                if is_deferred_advanced_refactor
                else [
                "run WP1 read-only evidence workflow",
                "derive smallest related test command from WP1 artifacts",
                    "run full regression only after an approved implementation phase changes code",
                ]
            ),
            "reason": (
                "Advanced refactor orchestration is deferred until Phase 105 readiness."
                if is_deferred_advanced_refactor
                else "No source files were read by task.decompose."
            ),
        },
        "uncertainty": (
            [
                {
                    "code": "advanced_refactor_deferred",
                    "reason": "Broad single-path refactor orchestration remains deferred until Phase 105 readiness.",
                }
            ]
            if is_deferred_advanced_refactor
            else [
            {
                "code": "repo_evidence_not_read",
                "reason": "This workflow uses registry metadata only. Run the first work package to gather source evidence.",
            }
            ]
        ),
        "blockers": (
            [
                {
                    "reason": "advanced_refactor_deferred",
                    "message": "Use smaller L1/L2 investigation and change-surface prompts until Phase 105 readiness is complete.",
                }
            ]
            if is_deferred_advanced_refactor
            else []
        ),
        "deferred_to_phase": 105 if is_deferred_advanced_refactor else None,
        "next_action": NextAction.NONE.value if is_deferred_advanced_refactor else NextAction.EXECUTE_READ_ONLY.value,
        "mutation_policy": (
            MutationPolicy.UNSUPPORTED_DEFERRED.value if is_deferred_advanced_refactor else MutationPolicy.READ_ONLY.value
        ),
        "runtime_registry_changed": False,
        "target_repository_changed": False,
    }
    reference_errors = validate_registered_references(plan, workflows, skills, tools)
    if reference_errors:
        plan["status"] = DecompositionStatus.BLOCKED.value
        plan["blockers"] = [{"reason": "unregistered_reference", "message": json.dumps(reference_errors, ensure_ascii=True)}]
        plan["next_action"] = NextAction.NONE.value
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
