"""Read-only connector catalog admission validation workflow."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.connectors.catalog import (
    SCHEMA_VERSION,
    ConnectorCatalogError,
    artifact_timestamp,
    build_connector_catalog_validation_report,
    read_json_object,
    utc_now,
    write_json,
)
from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus


WORKFLOW_ID = "connector_catalog.validate"
DEFAULT_OUTPUT_DIR = "connector-catalog-validations"


class ConnectorCatalogValidationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "connector_catalog_validation_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class ConnectorCatalogValidationRequest:
    config_root: Path | str = "."
    output_root: Path | str = ".agentic_controller"
    workflow: str = WORKFLOW_ID
    schema_version: int = SCHEMA_VERSION
    connector_manifest: dict[str, Any] | None = None
    connector_manifest_path: str | None = None
    role_id: str = "architect/default"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        config_root: Path,
        output_root: Path,
    ) -> "ConnectorCatalogValidationRequest":
        values: dict[str, Any] = {
            "config_root": config_root,
            "output_root": output_root,
        }
        names = {item.name for item in fields(cls)}
        for key, value in payload.items():
            if key in names:
                values[key] = value
        return cls(**values)


def require_under(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ConnectorCatalogValidationError(
            f"{label} is outside the configured root: {resolved}",
            code="connector_manifest_path_not_allowed",
            status=HTTPStatus.FORBIDDEN,
        ) from exc
    return resolved


def validate_request(request: ConnectorCatalogValidationRequest) -> None:
    if request.workflow != WORKFLOW_ID:
        raise ConnectorCatalogValidationError("workflow must be connector_catalog.validate.", code="unsupported_workflow")
    if request.schema_version != SCHEMA_VERSION:
        raise ConnectorCatalogValidationError("schema_version must be 1.", code="unsupported_schema_version")
    if bool(request.connector_manifest) == bool(request.connector_manifest_path):
        raise ConnectorCatalogValidationError(
            "Exactly one of connector_manifest or connector_manifest_path is required.",
            code="missing_connector_manifest",
            status=HTTPStatus.BAD_REQUEST,
        )


def load_manifest(request: ConnectorCatalogValidationRequest) -> tuple[dict[str, Any], str | None]:
    if request.connector_manifest is not None:
        if not isinstance(request.connector_manifest, dict):
            raise ConnectorCatalogValidationError("connector_manifest must be an object.", code="invalid_connector_manifest")
        return request.connector_manifest, None
    assert request.connector_manifest_path is not None
    config_root = Path(request.config_root).resolve()
    output_root = Path(request.output_root).resolve()
    raw_path = Path(request.connector_manifest_path)
    path = raw_path if raw_path.is_absolute() else output_root / raw_path
    if not path.resolve().is_relative_to(output_root) and not path.resolve().is_relative_to(config_root):
        path = require_under(path, output_root, "connector_manifest_path")
    try:
        manifest = read_json_object(path, "connector admission manifest")
    except ConnectorCatalogError as exc:
        raise ConnectorCatalogValidationError(str(exc), code=exc.code, status=exc.status) from exc
    return manifest, str(path.resolve())


def invoke_connector_catalog_validation(request: ConnectorCatalogValidationRequest) -> InvocationResult:
    validate_request(request)
    output_root = Path(request.output_root).resolve()
    config_root = Path(request.config_root).resolve()
    run_id = f"connector-catalog-validation-{artifact_timestamp()}"
    run_dir = output_root / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest, manifest_path = load_manifest(request)
    artifacts: dict[str, str] = {}
    request_artifact = {
        "kind": "connector_catalog_validation_request",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "connector_manifest_path": manifest_path,
        "connector_manifest": manifest,
        "metadata": request.metadata,
        "created_at": utc_now(),
    }
    write_json(run_dir / "request.json", request_artifact)
    artifacts["request"] = str(run_dir / "request.json")

    report = build_connector_catalog_validation_report(
        config_root,
        manifest,
        output_path=run_dir / "connector-catalog-validation.json",
    )
    artifacts["connector_catalog_validation"] = str(run_dir / "connector-catalog-validation.json")
    status = WorkflowStatus.COMPLETED if report["status"] == "passed" else WorkflowStatus.FAILED
    run_state = {
        "kind": "connector_catalog_validation_run_state",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": status.value,
        "summary": report["summary"],
        "artifacts": artifacts,
        "updated_at": utc_now(),
    }
    write_json(run_dir / "run-state.json", run_state)
    artifacts["run_state"] = str(run_dir / "run-state.json")
    report["workflow"] = WORKFLOW_ID
    report["run_id"] = run_id
    report["artifacts"] = artifacts
    return InvocationResult(
        workflow=WORKFLOW_ID,
        status=status,
        artifact_paths=artifacts,
        summary_text=f"{WORKFLOW_ID} completed with validation_status={report['summary'].get('validation_status')}",
        failures=report.get("errors", []),
        resume_key={"schema_version": SCHEMA_VERSION, "run_state": str(run_dir / "run-state.json")},
        report=report,
        run_id=run_id,
    )
