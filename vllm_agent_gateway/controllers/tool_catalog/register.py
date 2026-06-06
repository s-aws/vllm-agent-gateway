"""Approval-gated tool catalog registration workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.controllers.tool_catalog.validate import (
    ToolCatalogValidationError,
    load_manifest,
)
from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus
from vllm_agent_gateway.tools.catalog import (
    SCHEMA_VERSION,
    TOOL_CATALOG_PATH,
    ToolCatalogError,
    artifact_timestamp,
    atomic_write_json,
    build_tool_catalog_validation_report,
    read_json_object,
    runtime_tool_entry,
    sha256_file,
    string_list,
    utc_now,
    write_json,
)


WORKFLOW_ID = "tool_catalog.register"
DEFAULT_OUTPUT_DIR = "tool-catalog-registrations"


class ToolCatalogRegistrationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "tool_catalog_registration_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class ToolCatalogRegistrationRequest:
    config_root: Path | str = "."
    output_root: Path | str = ".agentic_controller"
    workflow: str = WORKFLOW_ID
    schema_version: int = SCHEMA_VERSION
    tool_manifest: dict[str, Any] | None = None
    tool_manifest_path: str | None = None
    approval: dict[str, Any] = field(default_factory=dict)
    role_id: str = "architect/default"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        config_root: Path,
        output_root: Path,
    ) -> "ToolCatalogRegistrationRequest":
        values: dict[str, Any] = {
            "config_root": config_root,
            "output_root": output_root,
        }
        names = {item.name for item in fields(cls)}
        for key, value in payload.items():
            if key in names:
                values[key] = value
        return cls(**values)


def validate_approval(approval: Any) -> dict[str, Any]:
    if not isinstance(approval, dict):
        raise ToolCatalogRegistrationError(
            "approval must be a JSON object.",
            code="missing_tool_catalog_registration_approval",
            status=HTTPStatus.BAD_REQUEST,
        )
    if approval.get("status") != "approved_for_tool_catalog_registration":
        raise ToolCatalogRegistrationError(
            "tool_catalog.register requires approval.status=approved_for_tool_catalog_registration.",
            code="missing_tool_catalog_registration_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    scope = approval.get("scope")
    scopes = set(scope) if isinstance(scope, list) else {scope} if isinstance(scope, str) else set()
    if "tool_catalog_registration" not in scopes:
        raise ToolCatalogRegistrationError(
            "tool_catalog.register requires approval.scope=tool_catalog_registration.",
            code="invalid_tool_catalog_registration_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    if approval.get("runtime_tool_append") is not True:
        raise ToolCatalogRegistrationError(
            "tool_catalog.register requires approval.runtime_tool_append=true.",
            code="invalid_tool_catalog_registration_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    try:
        approval_refs = string_list(approval.get("approval_refs"), "approval.approval_refs")
    except ToolCatalogError as exc:
        raise ToolCatalogRegistrationError(str(exc), code=exc.code, status=HTTPStatus.FORBIDDEN) from exc
    return {
        "status": approval["status"],
        "scope": sorted(scopes),
        "runtime_tool_append": True,
        "approval_refs": approval_refs,
    }


def validate_request(request: ToolCatalogRegistrationRequest) -> None:
    if request.workflow != WORKFLOW_ID:
        raise ToolCatalogRegistrationError("workflow must be tool_catalog.register.", code="unsupported_workflow")
    if request.schema_version != SCHEMA_VERSION:
        raise ToolCatalogRegistrationError("schema_version must be 1.", code="unsupported_schema_version")
    if bool(request.tool_manifest) == bool(request.tool_manifest_path):
        raise ToolCatalogRegistrationError(
            "Exactly one of tool_manifest or tool_manifest_path is required.",
            code="missing_tool_manifest",
            status=HTTPStatus.BAD_REQUEST,
        )
    validate_approval(request.approval)


def changed_hashes(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(key for key, value in after.items() if before.get(key) != value)


def append_runtime_tool(config_root: Path, tool_entry: dict[str, Any]) -> dict[str, Any]:
    tools_path = config_root / TOOL_CATALOG_PATH
    manifest = read_json_object(tools_path, "tool catalog")
    tools = manifest.get("tools")
    if not isinstance(tools, list):
        raise ToolCatalogRegistrationError("runtime/tools.json must contain a tools list.", code="invalid_tool_catalog")
    if any(isinstance(item, dict) and item.get("id") == tool_entry["id"] for item in tools):
        raise ToolCatalogRegistrationError(
            f"Tool already exists in runtime/tools.json: {tool_entry['id']}",
            code="tool_already_registered",
        )
    updated = {**manifest, "tools": [*tools, tool_entry]}
    atomic_write_json(tools_path, updated)
    return updated


def rollback_instructions(tool_id: str, config_root: Path) -> dict[str, Any]:
    return {
        "kind": "tool_catalog_registration_rollback_instructions",
        "schema_version": SCHEMA_VERSION,
        "tool_id": tool_id,
        "restore_files": ["runtime/tools.json"],
        "note": "Restore the recorded runtime/tools.json backup or remove the appended tool entry with the matching id.",
        "config_root": str(config_root),
    }


def invoke_tool_catalog_registration(request: ToolCatalogRegistrationRequest) -> InvocationResult:
    validate_request(request)
    output_root = Path(request.output_root).resolve()
    config_root = Path(request.config_root).resolve()
    run_id = f"tool-catalog-registration-{artifact_timestamp()}"
    run_dir = output_root / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, str] = {}
    approval = validate_approval(request.approval)
    try:
        manifest, manifest_path = load_manifest(request)
    except ToolCatalogValidationError as exc:
        raise ToolCatalogRegistrationError(str(exc), code=exc.code, status=exc.status) from exc
    request_artifact = {
        "kind": "tool_catalog_registration_request",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "tool_manifest_path": manifest_path,
        "tool_manifest": manifest,
        "approval": approval,
        "metadata": request.metadata,
        "created_at": utc_now(),
    }
    write_json(run_dir / "request.json", request_artifact)
    artifacts["request"] = str(run_dir / "request.json")

    validation_report = build_tool_catalog_validation_report(
        config_root,
        manifest,
        output_path=run_dir / "tool-catalog-validation-before-registration.json",
    )
    artifacts["tool_catalog_validation"] = str(run_dir / "tool-catalog-validation-before-registration.json")
    if validation_report["status"] != "passed":
        first_error = validation_report["errors"][0] if validation_report["errors"] else {}
        raise ToolCatalogRegistrationError(
            first_error.get("message", "Tool catalog validation failed before registration."),
            code=first_error.get("code", "tool_catalog_validation_failed"),
        )

    tool = validation_report["validation"]["tool"]
    tool_entry = runtime_tool_entry(tool)
    tools_path = config_root / TOOL_CATALOG_PATH
    before_hashes = {
        "runtime/tools.json": sha256_file(tools_path),
        "runtime/workflows.json": sha256_file(config_root / "runtime" / "workflows.json"),
        "runtime/roles.json": sha256_file(config_root / "runtime" / "roles.json"),
    }
    append_runtime_tool(config_root, tool_entry)
    after_hashes = {
        "runtime/tools.json": sha256_file(tools_path),
        "runtime/workflows.json": sha256_file(config_root / "runtime" / "workflows.json"),
        "runtime/roles.json": sha256_file(config_root / "runtime" / "roles.json"),
    }
    rollback = rollback_instructions(tool_entry["id"], config_root)
    write_json(run_dir / "rollback-instructions.json", rollback)
    artifacts["rollback_instructions"] = str(run_dir / "rollback-instructions.json")

    hash_proof = {"before": before_hashes, "after": after_hashes, "changed": changed_hashes(before_hashes, after_hashes)}
    summary = {
        "registration_status": "installed",
        "tool_id": tool_entry["id"],
        "runtime_tool_count_delta": 1,
        "changed_runtime_files": hash_proof["changed"],
        "runtime_tool_registry_changed": True,
        "runtime_workflow_registry_changed": False,
        "runtime_role_registry_changed": False,
        "target_repository_changed": False,
        "next_action": "run_tool_policy_resolution_for_allowed_workflows",
    }
    registration = {
        "kind": "tool_catalog_registration",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": "installed",
        "summary": summary,
        "tool": tool_entry,
        "approval": approval,
        "hash_proof": hash_proof,
        "rollback_instructions": rollback,
        "created_at": utc_now(),
    }
    write_json(run_dir / "tool-catalog-registration.json", registration)
    artifacts["tool_catalog_registration"] = str(run_dir / "tool-catalog-registration.json")
    run_state = {
        "kind": "tool_catalog_registration_run_state",
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
        "kind": "tool_catalog_registration_report",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "summary": summary,
        "registration": registration,
        "warnings": [],
        "artifacts": artifacts,
    }
    return InvocationResult(
        workflow=WORKFLOW_ID,
        status=WorkflowStatus.COMPLETED,
        artifact_paths=artifacts,
        summary_text=f"{WORKFLOW_ID} completed with registration_status=installed",
        failures=[],
        resume_key={"schema_version": SCHEMA_VERSION, "run_state": str(run_dir / "run-state.json")},
        report=report,
        run_id=run_id,
    )

