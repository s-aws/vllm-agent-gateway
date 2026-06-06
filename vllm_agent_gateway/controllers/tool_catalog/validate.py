"""Read-only tool catalog admission validation workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus
from vllm_agent_gateway.tools.catalog import (
    SCHEMA_VERSION,
    ToolCatalogError,
    artifact_timestamp,
    build_tool_catalog_validation_report,
    read_json_object,
    utc_now,
    write_json,
)


WORKFLOW_ID = "tool_catalog.validate"
DEFAULT_OUTPUT_DIR = "tool-catalog-validations"


class ToolCatalogValidationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "tool_catalog_validation_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class ToolCatalogValidationRequest:
    config_root: Path | str = "."
    output_root: Path | str = ".agentic_controller"
    workflow: str = WORKFLOW_ID
    schema_version: int = SCHEMA_VERSION
    tool_manifest: dict[str, Any] | None = None
    tool_manifest_path: str | None = None
    role_id: str = "architect/default"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        config_root: Path,
        output_root: Path,
    ) -> "ToolCatalogValidationRequest":
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
        raise ToolCatalogValidationError(
            f"{label} is outside the configured root: {resolved}",
            code="tool_manifest_path_not_allowed",
            status=HTTPStatus.FORBIDDEN,
        ) from exc
    return resolved


def validate_request(request: ToolCatalogValidationRequest) -> None:
    if request.workflow != WORKFLOW_ID:
        raise ToolCatalogValidationError("workflow must be tool_catalog.validate.", code="unsupported_workflow")
    if request.schema_version != SCHEMA_VERSION:
        raise ToolCatalogValidationError("schema_version must be 1.", code="unsupported_schema_version")
    if bool(request.tool_manifest) == bool(request.tool_manifest_path):
        raise ToolCatalogValidationError(
            "Exactly one of tool_manifest or tool_manifest_path is required.",
            code="missing_tool_manifest",
            status=HTTPStatus.BAD_REQUEST,
        )


def load_manifest(request: ToolCatalogValidationRequest) -> tuple[dict[str, Any], str | None]:
    if request.tool_manifest is not None:
        if not isinstance(request.tool_manifest, dict):
            raise ToolCatalogValidationError("tool_manifest must be an object.", code="invalid_tool_manifest")
        return request.tool_manifest, None
    assert request.tool_manifest_path is not None
    config_root = Path(request.config_root).resolve()
    output_root = Path(request.output_root).resolve()
    raw_path = Path(request.tool_manifest_path)
    path = raw_path if raw_path.is_absolute() else output_root / raw_path
    if not path.resolve().is_relative_to(output_root) and not path.resolve().is_relative_to(config_root):
        path = require_under(path, output_root, "tool_manifest_path")
    try:
        manifest = read_json_object(path, "tool admission manifest")
    except ToolCatalogError as exc:
        raise ToolCatalogValidationError(str(exc), code=exc.code, status=exc.status) from exc
    return manifest, str(path.resolve())


def invoke_tool_catalog_validation(request: ToolCatalogValidationRequest) -> InvocationResult:
    validate_request(request)
    output_root = Path(request.output_root).resolve()
    config_root = Path(request.config_root).resolve()
    run_id = f"tool-catalog-validation-{artifact_timestamp()}"
    run_dir = output_root / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest, manifest_path = load_manifest(request)
    artifacts: dict[str, str] = {}
    request_artifact = {
        "kind": "tool_catalog_validation_request",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "tool_manifest_path": manifest_path,
        "tool_manifest": manifest,
        "metadata": request.metadata,
        "created_at": utc_now(),
    }
    write_json(run_dir / "request.json", request_artifact)
    artifacts["request"] = str(run_dir / "request.json")

    report = build_tool_catalog_validation_report(
        config_root,
        manifest,
        output_path=run_dir / "tool-catalog-validation.json",
    )
    artifacts["tool_catalog_validation"] = str(run_dir / "tool-catalog-validation.json")
    status = WorkflowStatus.COMPLETED if report["status"] == "passed" else WorkflowStatus.FAILED
    run_state = {
        "kind": "tool_catalog_validation_run_state",
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

