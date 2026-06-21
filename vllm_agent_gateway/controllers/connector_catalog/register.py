"""Approval-gated connector catalog registration workflow."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.connectors.catalog import (
    CONNECTOR_CATALOG_PATH,
    SCHEMA_VERSION,
    ConnectorCatalogError,
    artifact_timestamp,
    build_connector_catalog_validation_report,
    read_json_object,
    runtime_connector_entry,
    string_list,
    utc_now,
    write_json,
)
from vllm_agent_gateway.controllers.connector_catalog.validate import (
    ConnectorCatalogValidationError,
    load_manifest,
)
from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus
from vllm_agent_gateway.tools.catalog import atomic_write_json, sha256_file


WORKFLOW_ID = "connector_catalog.register"
DEFAULT_OUTPUT_DIR = "connector-catalog-registrations"


class ConnectorCatalogRegistrationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "connector_catalog_registration_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class ConnectorCatalogRegistrationRequest:
    config_root: Path | str = "."
    output_root: Path | str = ".agentic_controller"
    workflow: str = WORKFLOW_ID
    schema_version: int = SCHEMA_VERSION
    connector_manifest: dict[str, Any] | None = None
    connector_manifest_path: str | None = None
    release_gate_report_path: str | None = None
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
    ) -> "ConnectorCatalogRegistrationRequest":
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
        raise ConnectorCatalogRegistrationError(
            "approval must be a JSON object.",
            code="missing_connector_catalog_registration_approval",
            status=HTTPStatus.BAD_REQUEST,
        )
    if approval.get("status") != "approved_for_connector_catalog_registration":
        raise ConnectorCatalogRegistrationError(
            "connector_catalog.register requires approval.status=approved_for_connector_catalog_registration.",
            code="missing_connector_catalog_registration_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    scope = approval.get("scope")
    if isinstance(scope, str):
        scopes = {scope}
    elif isinstance(scope, list) and all(isinstance(item, str) and item.strip() for item in scope):
        scopes = set(scope)
    else:
        raise ConnectorCatalogRegistrationError(
            "connector_catalog.register requires approval.scope to be a non-empty string or list of strings.",
            code="invalid_connector_catalog_registration_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    if "connector_catalog_registration" not in scopes:
        raise ConnectorCatalogRegistrationError(
            "connector_catalog.register requires approval.scope=connector_catalog_registration.",
            code="invalid_connector_catalog_registration_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    if approval.get("runtime_connector_append") is not True:
        raise ConnectorCatalogRegistrationError(
            "connector_catalog.register requires approval.runtime_connector_append=true.",
            code="invalid_connector_catalog_registration_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    enabled = approval.get("enabled")
    if not isinstance(enabled, bool):
        raise ConnectorCatalogRegistrationError(
            "connector_catalog.register requires approval.enabled boolean.",
            code="invalid_connector_catalog_registration_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    if enabled and "connector_enablement" not in scopes:
        raise ConnectorCatalogRegistrationError(
            "enabled connector registration requires approval.scope=connector_enablement.",
            code="invalid_connector_catalog_registration_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    try:
        approval_refs = string_list(approval.get("approval_refs"), "approval.approval_refs")
    except ConnectorCatalogError as exc:
        raise ConnectorCatalogRegistrationError(str(exc), code=exc.code, status=HTTPStatus.FORBIDDEN) from exc
    return {
        "status": approval["status"],
        "scope": sorted(scopes),
        "runtime_connector_append": True,
        "enabled": enabled,
        "approval_refs": approval_refs,
    }


def validate_request(request: ConnectorCatalogRegistrationRequest) -> None:
    if request.workflow != WORKFLOW_ID:
        raise ConnectorCatalogRegistrationError("workflow must be connector_catalog.register.", code="unsupported_workflow")
    if request.schema_version != SCHEMA_VERSION:
        raise ConnectorCatalogRegistrationError("schema_version must be 1.", code="unsupported_schema_version")
    if bool(request.connector_manifest) == bool(request.connector_manifest_path):
        raise ConnectorCatalogRegistrationError(
            "Exactly one of connector_manifest or connector_manifest_path is required.",
            code="missing_connector_manifest",
            status=HTTPStatus.BAD_REQUEST,
        )
    approval = validate_approval(request.approval)
    if approval["enabled"] and not request.release_gate_report_path:
        raise ConnectorCatalogRegistrationError(
            "enabled connector registration requires release_gate_report_path.",
            code="missing_connector_release_gate_proof",
            status=HTTPStatus.FORBIDDEN,
        )


def resolve_report_path(request: ConnectorCatalogRegistrationRequest, raw_path: str) -> Path:
    config_root = Path(request.config_root).resolve()
    output_root = Path(request.output_root).resolve()
    path = Path(raw_path)
    candidate = path if path.is_absolute() else output_root / path
    resolved = candidate.resolve()
    if resolved.is_relative_to(output_root) or resolved.is_relative_to(config_root):
        return resolved
    raise ConnectorCatalogRegistrationError(
        f"release_gate_report_path is outside the configured roots: {resolved}",
        code="connector_release_gate_report_path_not_allowed",
        status=HTTPStatus.FORBIDDEN,
    )


def validate_release_gate_report(
    request: ConnectorCatalogRegistrationRequest,
    connector_id: str,
    operation_ids: list[str],
) -> dict[str, Any] | None:
    approval = validate_approval(request.approval)
    if not approval["enabled"]:
        return None
    assert request.release_gate_report_path is not None
    report_path = resolve_report_path(request, request.release_gate_report_path)
    try:
        report = read_json_object(report_path, "connector eval release gate report")
    except ConnectorCatalogError as exc:
        raise ConnectorCatalogRegistrationError(str(exc), code=exc.code, status=exc.status) from exc
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    if report.get("kind") != "connector_eval_release_gate_report" or report.get("status") != "passed":
        raise ConnectorCatalogRegistrationError(
            "enabled connector registration requires a passed connector eval release gate report.",
            code="connector_release_gate_not_passed",
            status=HTTPStatus.FORBIDDEN,
        )
    if summary.get("connector_id") != connector_id:
        raise ConnectorCatalogRegistrationError(
            "release gate connector_id must match the registered connector.",
            code="connector_release_gate_mismatch",
            status=HTTPStatus.FORBIDDEN,
        )
    if summary.get("release_decision") != "ship" or summary.get("connector_enabled_requested") is not True:
        raise ConnectorCatalogRegistrationError(
            "enabled connector registration requires release_decision=ship and connector_enabled_requested=true.",
            code="connector_release_gate_not_ship",
            status=HTTPStatus.FORBIDDEN,
        )
    report_operation_ids = string_list(summary.get("operation_ids", []), "release_gate.summary.operation_ids", allow_empty=True)
    if sorted(report_operation_ids) != sorted(operation_ids):
        raise ConnectorCatalogRegistrationError(
            "release gate operation_ids must match the registered connector operations.",
            code="connector_release_gate_stale_validation",
            status=HTTPStatus.FORBIDDEN,
        )
    return {"path": str(report_path), "summary": summary}


def changed_hashes(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(key for key, value in after.items() if before.get(key) != value)


def append_runtime_connector(config_root: Path, connector_entry: dict[str, Any]) -> dict[str, Any]:
    connectors_path = config_root / CONNECTOR_CATALOG_PATH
    catalog = read_json_object(connectors_path, "connector catalog")
    connectors = catalog.get("connectors")
    if not isinstance(connectors, list):
        raise ConnectorCatalogRegistrationError("runtime/connectors.json must contain a connectors list.", code="invalid_connector_catalog")
    if any(isinstance(item, dict) and item.get("id") == connector_entry["id"] for item in connectors):
        raise ConnectorCatalogRegistrationError(
            f"Connector already exists in runtime/connectors.json: {connector_entry['id']}",
            code="connector_already_registered",
        )
    updated = {**catalog, "connectors": [*connectors, connector_entry]}
    atomic_write_json(connectors_path, updated)
    return updated


def rollback_instructions(connector_id: str, config_root: Path) -> dict[str, Any]:
    return {
        "kind": "connector_catalog_registration_rollback_instructions",
        "schema_version": SCHEMA_VERSION,
        "connector_id": connector_id,
        "restore_files": ["runtime/connectors.json"],
        "note": "Restore the recorded runtime/connectors.json backup or remove the appended connector entry with the matching id.",
        "config_root": str(config_root),
    }


def runtime_hashes(config_root: Path) -> dict[str, str]:
    return {
        "runtime/connectors.json": sha256_file(config_root / "runtime" / "connectors.json"),
        "runtime/tools.json": sha256_file(config_root / "runtime" / "tools.json"),
        "runtime/workflows.json": sha256_file(config_root / "runtime" / "workflows.json"),
        "runtime/roles.json": sha256_file(config_root / "runtime" / "roles.json"),
    }


def invoke_connector_catalog_registration(request: ConnectorCatalogRegistrationRequest) -> InvocationResult:
    validate_request(request)
    output_root = Path(request.output_root).resolve()
    config_root = Path(request.config_root).resolve()
    run_id = f"connector-catalog-registration-{artifact_timestamp()}"
    run_dir = output_root / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, str] = {}
    approval = validate_approval(request.approval)
    try:
        manifest, manifest_path = load_manifest(request)
    except ConnectorCatalogValidationError as exc:
        raise ConnectorCatalogRegistrationError(str(exc), code=exc.code, status=exc.status) from exc
    request_artifact = {
        "kind": "connector_catalog_registration_request",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "connector_manifest_path": manifest_path,
        "connector_manifest": manifest,
        "release_gate_report_path": request.release_gate_report_path,
        "approval": approval,
        "metadata": request.metadata,
        "created_at": utc_now(),
    }
    write_json(run_dir / "request.json", request_artifact)
    artifacts["request"] = str(run_dir / "request.json")

    validation_report = build_connector_catalog_validation_report(
        config_root,
        manifest,
        output_path=run_dir / "connector-catalog-validation-before-registration.json",
    )
    artifacts["connector_catalog_validation"] = str(run_dir / "connector-catalog-validation-before-registration.json")
    if validation_report["status"] != "passed":
        first_error = validation_report["errors"][0] if validation_report["errors"] else {}
        raise ConnectorCatalogRegistrationError(
            first_error.get("message", "Connector catalog validation failed before registration."),
            code=first_error.get("code", "connector_catalog_validation_failed"),
        )

    connector = validation_report["validation"]["connector"]
    operation_ids = [operation["id"] for operation in connector["operations"] if isinstance(operation.get("id"), str)]
    release_gate = validate_release_gate_report(request, connector["id"], operation_ids)
    connector_entry = runtime_connector_entry(connector)
    connector_entry["enabled"] = approval["enabled"]
    connectors_path = config_root / CONNECTOR_CATALOG_PATH
    before_hashes = runtime_hashes(config_root)
    append_runtime_connector(config_root, connector_entry)
    after_hashes = runtime_hashes(config_root)
    rollback = rollback_instructions(connector_entry["id"], config_root)
    write_json(run_dir / "rollback-instructions.json", rollback)
    artifacts["rollback_instructions"] = str(run_dir / "rollback-instructions.json")

    hash_proof = {"before": before_hashes, "after": after_hashes, "changed": changed_hashes(before_hashes, after_hashes)}
    summary = {
        "registration_status": "installed",
        "connector_id": connector_entry["id"],
        "enabled": connector_entry["enabled"],
        "runtime_connector_count_delta": 1,
        "changed_runtime_files": hash_proof["changed"],
        "runtime_connector_registry_changed": True,
        "runtime_tool_registry_changed": False,
        "runtime_workflow_registry_changed": False,
        "runtime_role_registry_changed": False,
        "target_repository_changed": False,
        "release_gate_required": connector_entry["enabled"],
        "release_gate_passed": (release_gate is not None) if connector_entry["enabled"] else True,
        "next_action": "run_connector_invocation_or_natural_exposure_validation",
    }
    registration = {
        "kind": "connector_catalog_registration",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": "installed",
        "summary": summary,
        "connector": connector_entry,
        "approval": approval,
        "release_gate": release_gate,
        "hash_proof": hash_proof,
        "rollback_instructions": rollback,
        "connectors_path": str(connectors_path),
        "created_at": utc_now(),
    }
    write_json(run_dir / "connector-catalog-registration.json", registration)
    artifacts["connector_catalog_registration"] = str(run_dir / "connector-catalog-registration.json")
    run_state = {
        "kind": "connector_catalog_registration_run_state",
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
        "kind": "connector_catalog_registration_report",
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
