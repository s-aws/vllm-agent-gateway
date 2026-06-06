"""Governed runtime tool catalog admission and registration helpers."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.tools.mediator import SUPPORTED_TOOL_IDS, generate_tool_schemas


SCHEMA_VERSION = 1
TOOL_CATALOG_PATH = Path("runtime") / "tools.json"
WORKFLOW_CATALOG_PATH = Path("runtime") / "workflows.json"
ROLE_CATALOG_PATH = Path("runtime") / "roles.json"
SUPPORTED_SAFETY_CLASSES = {"read_only", "test_execution"}
SUPPORTED_MUTATION_POLICIES = {"no_repository_mutation", "test_execution"}
SUPPORTED_TOOL_KINDS = {"local_command", "filesystem_read", "local_workflow"}
TOOL_ID_PATTERN = re.compile(r"[a-z][a-z0-9_]*")


class ToolCatalogError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "tool_catalog_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def artifact_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ToolCatalogError(f"Missing {label}: {path}", code=f"missing_{label.replace(' ', '_')}") from exc
    except json.JSONDecodeError as exc:
        raise ToolCatalogError(f"Invalid {label} JSON: {exc}", code=f"invalid_{label.replace(' ', '_')}") from exc
    if not isinstance(value, dict):
        raise ToolCatalogError(f"{label} must contain a JSON object.", code=f"invalid_{label.replace(' ', '_')}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{artifact_timestamp()}.tmp")
    temp_path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    temp_path.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def string_list(value: Any, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ToolCatalogError(f"{label} must be a list of non-empty strings.", code="invalid_tool_catalog_manifest")
    if not allow_empty and not value:
        raise ToolCatalogError(f"{label} must not be empty.", code="invalid_tool_catalog_manifest")
    return list(value)


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ToolCatalogError(f"{label} must be a JSON object.", code="invalid_tool_catalog_manifest")
    return value


def runtime_tools_by_id(config_root: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json_object(config_root / TOOL_CATALOG_PATH, "tool catalog")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ToolCatalogError("runtime/tools.json schema_version must be 1.", code="invalid_tool_catalog")
    tools = manifest.get("tools")
    if not isinstance(tools, list):
        raise ToolCatalogError("runtime/tools.json must contain a tools list.", code="invalid_tool_catalog")
    values: dict[str, dict[str, Any]] = {}
    for item in tools:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ToolCatalogError("Every runtime tool entry must contain an id.", code="invalid_tool_catalog")
        if item["id"] in values:
            raise ToolCatalogError(f"Duplicate runtime tool id: {item['id']}", code="duplicate_tool_id")
        values[item["id"]] = item
    return values


def workflows_by_id(config_root: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json_object(config_root / WORKFLOW_CATALOG_PATH, "workflow catalog")
    workflows = manifest.get("workflows")
    if not isinstance(workflows, list):
        raise ToolCatalogError("runtime/workflows.json must contain a workflows list.", code="invalid_workflow_catalog")
    return {item["id"]: item for item in workflows if isinstance(item, dict) and isinstance(item.get("id"), str)}


def roles_by_id(config_root: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json_object(config_root / ROLE_CATALOG_PATH, "role catalog")
    roles = manifest.get("roles")
    if not isinstance(roles, list):
        raise ToolCatalogError("runtime/roles.json must contain a roles list.", code="invalid_role_catalog")
    return {item["id"]: item for item in roles if isinstance(item, dict) and isinstance(item.get("id"), str)}


def workflow_tool_ids(workflow: dict[str, Any]) -> set[str]:
    values: set[str] = set(string_list(workflow.get("controller_tool_ids", []), "workflow.controller_tool_ids", allow_empty=True))
    values.update(string_list(workflow.get("model_visible_tool_ids", []), "workflow.model_visible_tool_ids", allow_empty=True))
    conditional = workflow.get("conditional_controller_tool_ids", [])
    if conditional is None:
        conditional = []
    if not isinstance(conditional, list):
        raise ToolCatalogError("workflow.conditional_controller_tool_ids must be a list.", code="invalid_workflow_catalog")
    for item in conditional:
        if not isinstance(item, dict):
            raise ToolCatalogError("workflow.conditional_controller_tool_ids entries must be objects.", code="invalid_workflow_catalog")
        values.update(string_list(item.get("tool_ids", []), "workflow.conditional_controller_tool_ids.tool_ids", allow_empty=True))
    return values


def tool_command_key(tool: dict[str, Any]) -> tuple[str, str]:
    command = tool.get("command")
    command_text = json.dumps(command, ensure_ascii=True, sort_keys=True) if command is not None else ""
    return str(tool.get("kind")), command_text


def validate_json_schema_object(value: Any, label: str) -> dict[str, Any]:
    schema = require_object(value, label)
    if schema.get("type") != "object":
        raise ToolCatalogError(f"{label}.type must be object.", code="invalid_tool_schema")
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise ToolCatalogError(f"{label}.properties must be an object.", code="invalid_tool_schema")
    required = schema.get("required", [])
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        raise ToolCatalogError(f"{label}.required must be a list of strings.", code="invalid_tool_schema")
    return schema


def validate_args_schema(value: Any) -> dict[str, Any]:
    args_schema = require_object(value, "tool.args_schema")
    for name, raw_schema in args_schema.items():
        if not isinstance(name, str) or not name:
            raise ToolCatalogError("tool.args_schema keys must be non-empty strings.", code="invalid_tool_schema")
        schema = require_object(raw_schema, f"tool.args_schema.{name}")
        if schema.get("type") not in {"string", "array", "boolean", "integer"}:
            raise ToolCatalogError(f"tool.args_schema.{name}.type is unsupported.", code="invalid_tool_schema")
        if "required" in schema and not isinstance(schema["required"], bool):
            raise ToolCatalogError(f"tool.args_schema.{name}.required must be boolean.", code="invalid_tool_schema")
    return args_schema


def validate_tool_shape(raw_tool: Any) -> dict[str, Any]:
    tool = require_object(raw_tool, "tool")
    required = {
        "id",
        "owner",
        "description",
        "kind",
        "read_only",
        "args_schema",
        "input_schema",
        "output_schema",
        "safety_class",
        "mutation_policy",
        "allowed_workflows",
        "allowed_roles",
    }
    missing = sorted(required - set(tool))
    if missing:
        raise ToolCatalogError(f"tool is missing field(s): {', '.join(missing)}", code="invalid_tool_catalog_manifest")
    tool_id = tool["id"]
    if not isinstance(tool_id, str) or not TOOL_ID_PATTERN.fullmatch(tool_id):
        raise ToolCatalogError("tool.id must be snake_case and start with a letter.", code="invalid_tool_id")
    if not isinstance(tool["owner"], str) or not tool["owner"].strip():
        raise ToolCatalogError("tool.owner must be a non-empty string.", code="invalid_tool_catalog_manifest")
    if not isinstance(tool["description"], str) or len(tool["description"].strip()) < 12:
        raise ToolCatalogError("tool.description must be descriptive.", code="invalid_tool_catalog_manifest")
    if tool["kind"] not in SUPPORTED_TOOL_KINDS:
        raise ToolCatalogError(f"tool.kind is unsupported: {tool['kind']!r}", code="unsupported_tool_kind")
    if not isinstance(tool["read_only"], bool):
        raise ToolCatalogError("tool.read_only must be boolean.", code="invalid_tool_catalog_manifest")
    if tool["safety_class"] not in SUPPORTED_SAFETY_CLASSES:
        raise ToolCatalogError(f"tool.safety_class is unsupported: {tool['safety_class']!r}", code="unsupported_safety_class")
    if tool["mutation_policy"] not in SUPPORTED_MUTATION_POLICIES:
        raise ToolCatalogError(f"tool.mutation_policy is unsupported: {tool['mutation_policy']!r}", code="unsupported_mutation_policy")
    if tool["safety_class"] == "read_only" and (tool["read_only"] is not True or tool["mutation_policy"] != "no_repository_mutation"):
        raise ToolCatalogError("read_only tools must use mutation_policy=no_repository_mutation.", code="unsafe_tool_policy")
    if tool["safety_class"] == "test_execution" and (tool["read_only"] is not False or tool["mutation_policy"] != "test_execution"):
        raise ToolCatalogError("test_execution tools must use read_only=false and mutation_policy=test_execution.", code="unsafe_tool_policy")
    if tool["kind"] == "filesystem_read" and tool["mutation_policy"] != "no_repository_mutation":
        raise ToolCatalogError("filesystem_read tools cannot declare repository mutation.", code="unsafe_file_access")
    validate_args_schema(tool["args_schema"])
    validate_json_schema_object(tool["input_schema"], "tool.input_schema")
    validate_json_schema_object(tool["output_schema"], "tool.output_schema")
    string_list(tool["allowed_workflows"], "tool.allowed_workflows")
    string_list(tool["allowed_roles"], "tool.allowed_roles")
    return dict(tool)


def validate_tool_admission_manifest(manifest: dict[str, Any], config_root: Path) -> dict[str, Any]:
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ToolCatalogError("tool admission schema_version must be 1.", code="unsupported_schema_version")
    if manifest.get("kind") != "tool_admission_manifest":
        raise ToolCatalogError("tool admission kind must be tool_admission_manifest.", code="invalid_tool_catalog_manifest")
    tool = validate_tool_shape(manifest.get("tool"))
    tool_id = tool["id"]
    existing_tools = runtime_tools_by_id(config_root)
    workflows = workflows_by_id(config_root)
    roles = roles_by_id(config_root)

    if tool_id in existing_tools:
        raise ToolCatalogError(f"Tool already exists in runtime/tools.json: {tool_id}", code="tool_already_registered")
    if tool_id not in SUPPORTED_TOOL_IDS:
        raise ToolCatalogError(f"Tool has no executable mediator support: {tool_id}", code="unsupported_executable_tool")

    command_key = tool_command_key(tool)
    duplicates = [
        existing_id
        for existing_id, existing_tool in existing_tools.items()
        if command_key[1] and tool_command_key(existing_tool) == command_key
    ]
    if duplicates and not isinstance(manifest.get("consolidation_plan"), dict):
        raise ToolCatalogError(
            f"Tool duplicates existing controller action behavior: {', '.join(sorted(duplicates))}",
            code="duplicate_tool_behavior",
        )

    allowed_workflows = string_list(tool["allowed_workflows"], "tool.allowed_workflows")
    allowed_roles = string_list(tool["allowed_roles"], "tool.allowed_roles")
    workflow_checks: list[dict[str, Any]] = []
    role_checks: list[dict[str, Any]] = []
    for workflow_id in allowed_workflows:
        workflow = workflows.get(workflow_id)
        if workflow is None:
            raise ToolCatalogError(f"Unknown workflow in tool.allowed_workflows: {workflow_id}", code="unknown_workflow")
        referenced = tool_id in workflow_tool_ids(workflow)
        workflow_allowed_roles = set(string_list(workflow.get("allowed_role_ids", []), f"{workflow_id}.allowed_role_ids", allow_empty=True))
        default_role = workflow.get("default_role_id")
        if isinstance(default_role, str) and default_role:
            workflow_allowed_roles.add(default_role)
        compatible_roles = sorted(workflow_allowed_roles & set(allowed_roles))
        workflow_checks.append(
            {
                "workflow_id": workflow_id,
                "tool_referenced_by_workflow": referenced,
                "compatible_roles": compatible_roles,
                "status": "passed" if referenced and compatible_roles else "failed",
            }
        )
        if not referenced:
            raise ToolCatalogError(
                f"Workflow {workflow_id} does not expose proposed tool {tool_id}.",
                code="workflow_tool_exposure_missing",
            )
        if not compatible_roles:
            raise ToolCatalogError(
                f"Tool {tool_id} has no role compatible with workflow {workflow_id}.",
                code="role_exposure_incompatible",
            )

    for role_id in allowed_roles:
        role = roles.get(role_id)
        if role is None:
            raise ToolCatalogError(f"Unknown role in tool.allowed_roles: {role_id}", code="unknown_role")
        role_tool_ids = set(string_list(role.get("tool_ids", []), f"{role_id}.tool_ids", allow_empty=True))
        has_tool = tool_id in role_tool_ids
        role_checks.append({"role_id": role_id, "tool_referenced_by_role": has_tool, "status": "passed" if has_tool else "failed"})
        if not has_tool:
            raise ToolCatalogError(f"Role {role_id} does not expose proposed tool {tool_id}.", code="role_tool_exposure_missing")

    candidate_catalog = read_json_object(config_root / TOOL_CATALOG_PATH, "tool catalog")
    candidate_tools = list(candidate_catalog.get("tools", [])) + [runtime_tool_entry(tool)]
    candidate_catalog = {**candidate_catalog, "tools": candidate_tools}
    try:
        generate_tool_schemas(candidate_catalog, {tool_id})
    except RuntimeError as exc:
        raise ToolCatalogError(str(exc), code="tool_schema_generation_failed") from exc

    return {
        "status": "passed",
        "schema_version": SCHEMA_VERSION,
        "tool": tool,
        "tool_id": tool_id,
        "workflow_checks": workflow_checks,
        "role_checks": role_checks,
        "runtime_behavior_changed": False,
        "next_action": "review_then_register_tool_catalog_entry",
    }


def runtime_tool_entry(tool: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "id": tool["id"],
        "kind": tool["kind"],
        "description": tool["description"],
        "read_only": tool["read_only"],
        "args_schema": tool["args_schema"],
        "owner": tool["owner"],
        "safety_class": tool["safety_class"],
        "mutation_policy": tool["mutation_policy"],
        "input_schema": tool["input_schema"],
        "output_schema": tool["output_schema"],
        "allowed_workflows": tool["allowed_workflows"],
        "allowed_roles": tool["allowed_roles"],
    }
    if "command" in tool:
        entry["command"] = tool["command"]
    return entry


def build_tool_catalog_validation_report(
    config_root: Path,
    manifest: dict[str, Any],
    *,
    output_path: Path | None = None,
) -> dict[str, Any]:
    report = {
        "kind": "tool_catalog_validation_report",
        "schema_version": SCHEMA_VERSION,
        "status": "failed",
        "tool_id": None,
        "summary": {
            "validation_status": "failed",
            "runtime_registry_changed": False,
            "target_repository_changed": False,
        },
        "errors": [],
        "checks": [],
        "created_at": utc_now(),
    }
    try:
        validation = validate_tool_admission_manifest(manifest, config_root)
        report["status"] = "passed"
        report["tool_id"] = validation["tool_id"]
        report["summary"] = {
            "validation_status": "passed",
            "tool_id": validation["tool_id"],
            "workflow_count": len(validation["workflow_checks"]),
            "role_count": len(validation["role_checks"]),
            "runtime_registry_changed": False,
            "target_repository_changed": False,
            "next_action": validation["next_action"],
        }
        report["checks"] = validation["workflow_checks"] + validation["role_checks"]
        report["validation"] = validation
    except ToolCatalogError as exc:
        report["errors"].append({"code": exc.code, "message": str(exc)})
        report["summary"]["error_count"] = len(report["errors"])
    if output_path is not None:
        write_json(output_path, report)
        report["report_path"] = str(output_path.resolve())
        write_json(output_path, report)
    return report
