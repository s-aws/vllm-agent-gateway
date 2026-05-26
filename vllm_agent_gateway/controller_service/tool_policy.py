"""Controller-owned workflow tool policy resolution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vllm_agent_gateway.tools.mediator import generate_tool_schemas


class ControllerToolPolicyError(RuntimeError):
    """Raised when workflow tool policy cannot be resolved safely."""


@dataclass(frozen=True)
class ResolvedControllerToolPolicy:
    workflow_id: str
    role_id: str
    controller_tool_ids: list[str]
    model_visible_tool_ids: list[str]
    role_tool_ids: list[str]
    denied_tool_ids: list[str]
    controller_actions: list[dict[str, Any]]
    runtime_policy_path: Path
    runtime_roles_path: Path
    runtime_tools_path: Path
    controller_tool_schema_count: int
    model_visible_tool_schema_count: int

    def audit_record(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "kind": "controller_tool_policy",
            "workflow": self.workflow_id,
            "role_id": self.role_id,
            "controller_tool_ids": self.controller_tool_ids,
            "model_visible_tool_ids": self.model_visible_tool_ids,
            "role_tool_ids": self.role_tool_ids,
            "denied_tool_ids": self.denied_tool_ids,
            "controller_actions": self.controller_actions,
            "controller_tool_schema_count": self.controller_tool_schema_count,
            "model_visible_tool_schema_count": self.model_visible_tool_schema_count,
            "runtime_policy_path": str(self.runtime_policy_path),
            "runtime_roles_path": str(self.runtime_roles_path),
            "runtime_tools_path": str(self.runtime_tools_path),
        }


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ControllerToolPolicyError(f"Missing runtime policy file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ControllerToolPolicyError(f"Invalid runtime policy JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ControllerToolPolicyError(f"Runtime policy JSON must contain an object: {path}")
    return value


def string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ControllerToolPolicyError(f"{label} must be a list of strings.")
    return list(value)


def load_role(roles_manifest: dict[str, Any], role_id: str) -> dict[str, Any]:
    roles = roles_manifest.get("roles")
    if not isinstance(roles, list):
        raise ControllerToolPolicyError("runtime/roles.json must contain a roles list.")
    for role in roles:
        if isinstance(role, dict) and role.get("id") == role_id:
            return role
    raise ControllerToolPolicyError(f"Role is not defined in runtime/roles.json: {role_id}")


def load_workflow(workflow_manifest: dict[str, Any], workflow_id: str) -> dict[str, Any]:
    workflows = workflow_manifest.get("workflows")
    if not isinstance(workflows, list):
        raise ControllerToolPolicyError("runtime/workflows.json must contain a workflows list.")
    for workflow in workflows:
        if isinstance(workflow, dict) and workflow.get("id") == workflow_id:
            return workflow
    raise ControllerToolPolicyError(f"Workflow is not defined in runtime/workflows.json: {workflow_id}")


def condition_matches(condition: dict[str, Any], request_context: dict[str, Any]) -> bool:
    for key, expected in condition.items():
        if request_context.get(key) != expected:
            return False
    return True


def workflow_controller_tool_ids(workflow: dict[str, Any], request_context: dict[str, Any]) -> list[str]:
    tool_ids = string_list(workflow.get("controller_tool_ids", []), "workflow.controller_tool_ids")
    conditional_rules = workflow.get("conditional_controller_tool_ids", [])
    if not isinstance(conditional_rules, list):
        raise ControllerToolPolicyError("workflow.conditional_controller_tool_ids must be a list.")
    for index, rule in enumerate(conditional_rules):
        if not isinstance(rule, dict):
            raise ControllerToolPolicyError(f"workflow.conditional_controller_tool_ids[{index}] must be an object.")
        condition = rule.get("when", {})
        if not isinstance(condition, dict):
            raise ControllerToolPolicyError(f"workflow.conditional_controller_tool_ids[{index}].when must be an object.")
        if condition_matches(condition, request_context):
            tool_ids.extend(string_list(rule.get("tool_ids", []), f"workflow.conditional_controller_tool_ids[{index}].tool_ids"))
    return sorted(set(tool_ids))


def workflow_controller_actions(workflow: dict[str, Any], controller_tool_ids: list[str]) -> list[dict[str, Any]]:
    raw_actions = workflow.get("controller_actions", [])
    if not isinstance(raw_actions, list):
        raise ControllerToolPolicyError("workflow.controller_actions must be a list.")
    enabled_tool_ids = set(controller_tool_ids)
    actions: list[dict[str, Any]] = []
    for index, raw_action in enumerate(raw_actions):
        if not isinstance(raw_action, dict):
            raise ControllerToolPolicyError(f"workflow.controller_actions[{index}] must be an object.")
        tool_id = raw_action.get("tool_id")
        action = raw_action.get("action")
        scope = raw_action.get("scope")
        if not isinstance(tool_id, str) or not isinstance(action, str) or not isinstance(scope, str):
            raise ControllerToolPolicyError(
                f"workflow.controller_actions[{index}] must contain string tool_id, action, and scope."
            )
        if tool_id not in enabled_tool_ids:
            continue
        result_artifacts = string_list(
            raw_action.get("result_artifacts", []),
            f"workflow.controller_actions[{index}].result_artifacts",
        )
        actions.append(
            {
                "tool_id": tool_id,
                "action": action,
                "scope": scope,
                "result_artifacts": result_artifacts,
            }
        )
    return actions


def resolve_controller_tool_policy(
    config_root: Path,
    workflow_id: str,
    role_id: str,
    request_context: dict[str, Any],
    requested_model_visible_tool_ids: list[str] | None = None,
) -> ResolvedControllerToolPolicy:
    runtime_policy_path = config_root / "runtime" / "workflows.json"
    runtime_roles_path = config_root / "runtime" / "roles.json"
    runtime_tools_path = config_root / "runtime" / "tools.json"
    workflow_manifest = read_json_object(runtime_policy_path)
    roles_manifest = read_json_object(runtime_roles_path)
    tool_catalog = read_json_object(runtime_tools_path)

    workflow = load_workflow(workflow_manifest, workflow_id)
    role = load_role(roles_manifest, role_id)

    allowed_role_ids = string_list(workflow.get("allowed_role_ids", []), "workflow.allowed_role_ids")
    if allowed_role_ids and role_id not in allowed_role_ids:
        raise ControllerToolPolicyError(f"Role {role_id} is not allowed for workflow {workflow_id}.")

    role_tool_ids = sorted(set(string_list(role.get("tool_ids", []), f"role {role_id}.tool_ids")))
    role_tool_set = set(role_tool_ids)
    controller_tool_ids = workflow_controller_tool_ids(workflow, request_context)
    controller_actions = workflow_controller_actions(workflow, controller_tool_ids)
    allowed_model_visible_tool_ids = sorted(set(string_list(workflow.get("model_visible_tool_ids", []), "workflow.model_visible_tool_ids")))
    model_visible_tool_ids = (
        sorted(set(requested_model_visible_tool_ids))
        if requested_model_visible_tool_ids is not None
        else allowed_model_visible_tool_ids
    )

    denied_tool_ids = sorted((set(controller_tool_ids) | set(model_visible_tool_ids)) - role_tool_set)
    denied_model_visible = sorted(set(model_visible_tool_ids) - set(allowed_model_visible_tool_ids))
    denied_tool_ids = sorted(set(denied_tool_ids) | set(denied_model_visible))
    if denied_tool_ids:
        raise ControllerToolPolicyError(
            f"Denied tool ids for workflow {workflow_id} and role {role_id}: {', '.join(denied_tool_ids)}"
        )

    try:
        controller_tool_schema_count = len(generate_tool_schemas(tool_catalog, set(controller_tool_ids)))
        model_visible_tool_schema_count = len(generate_tool_schemas(tool_catalog, set(model_visible_tool_ids)))
    except RuntimeError as exc:
        raise ControllerToolPolicyError(str(exc)) from exc

    return ResolvedControllerToolPolicy(
        workflow_id=workflow_id,
        role_id=role_id,
        controller_tool_ids=controller_tool_ids,
        model_visible_tool_ids=model_visible_tool_ids,
        role_tool_ids=role_tool_ids,
        denied_tool_ids=[],
        controller_actions=controller_actions,
        runtime_policy_path=runtime_policy_path,
        runtime_roles_path=runtime_roles_path,
        runtime_tools_path=runtime_tools_path,
        controller_tool_schema_count=controller_tool_schema_count,
        model_visible_tool_schema_count=model_visible_tool_schema_count,
    )
