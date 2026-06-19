"""Approval-gated connector invocation workflow for local stubs."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.connectors.catalog import SCHEMA_VERSION, artifact_timestamp, utc_now, write_json
from vllm_agent_gateway.connectors.mediator import ConnectorMediationError, mediate_connector_operation
from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus


WORKFLOW_ID = "connector.invoke"
DEFAULT_OUTPUT_DIR = "connector-invocations"


class ConnectorInvocationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "connector_invocation_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class ConnectorInvocationRequest:
    config_root: Path | str = "."
    output_root: Path | str = ".agentic_controller"
    workflow: str = WORKFLOW_ID
    schema_version: int = SCHEMA_VERSION
    connector_id: str = ""
    operation_id: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    dry_run: bool = True
    approval: dict[str, Any] | None = None
    role_id: str = "architect/default"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        config_root: Path,
        output_root: Path,
    ) -> "ConnectorInvocationRequest":
        values: dict[str, Any] = {
            "config_root": config_root,
            "output_root": output_root,
        }
        names = {item.name for item in fields(cls)}
        for key, value in payload.items():
            if key in names:
                values[key] = value
        return cls(**values)


def validate_request(request: ConnectorInvocationRequest) -> None:
    if request.workflow != WORKFLOW_ID:
        raise ConnectorInvocationError("workflow must be connector.invoke.", code="unsupported_workflow")
    if request.schema_version != SCHEMA_VERSION:
        raise ConnectorInvocationError("schema_version must be 1.", code="unsupported_schema_version")
    if not isinstance(request.connector_id, str) or not request.connector_id.strip():
        raise ConnectorInvocationError("connector_id is required.", code="missing_connector_id", status=HTTPStatus.BAD_REQUEST)
    if not isinstance(request.operation_id, str) or not request.operation_id.strip():
        raise ConnectorInvocationError("operation_id is required.", code="missing_connector_operation_id", status=HTTPStatus.BAD_REQUEST)
    if not isinstance(request.arguments, dict):
        raise ConnectorInvocationError("arguments must be a JSON object.", code="invalid_connector_arguments", status=HTTPStatus.BAD_REQUEST)
    if not isinstance(request.dry_run, bool):
        raise ConnectorInvocationError("dry_run must be boolean.", code="invalid_connector_invocation", status=HTTPStatus.BAD_REQUEST)


def invoke_connector_invocation(request: ConnectorInvocationRequest) -> InvocationResult:
    validate_request(request)
    output_root = Path(request.output_root).resolve()
    config_root = Path(request.config_root).resolve()
    run_id = f"connector-invocation-{artifact_timestamp()}"
    run_dir = output_root / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, str] = {}
    request_artifact = {
        "kind": "connector_invocation_request",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "connector_id": request.connector_id,
        "operation_id": request.operation_id,
        "arguments": request.arguments,
        "dry_run": request.dry_run,
        "approval": request.approval,
        "metadata": request.metadata,
        "created_at": utc_now(),
    }
    write_json(run_dir / "request.json", request_artifact)
    artifacts["request"] = str(run_dir / "request.json")

    try:
        invocation = mediate_connector_operation(
            config_root=config_root,
            connector_id=request.connector_id,
            operation_id=request.operation_id,
            arguments=request.arguments,
            dry_run=request.dry_run,
            approval=request.approval,
        )
    except ConnectorMediationError as exc:
        failure = {"code": exc.code, "message": str(exc)}
        summary = {
            "invocation_status": "failed",
            "connector_id": request.connector_id,
            "operation_id": request.operation_id,
            "runtime_registry_changed": False,
            "target_repository_changed": False,
            "error_count": 1,
        }
        report = {
            "kind": "connector_invocation_report",
            "schema_version": SCHEMA_VERSION,
            "workflow": WORKFLOW_ID,
            "run_id": run_id,
            "status": WorkflowStatus.FAILED.value,
            "summary": summary,
            "errors": [failure],
            "artifacts": artifacts,
            "created_at": utc_now(),
        }
        write_json(run_dir / "connector-invocation.json", report)
        artifacts["connector_invocation"] = str(run_dir / "connector-invocation.json")
        write_json(run_dir / "run-state.json", {**report, "kind": "connector_invocation_run_state", "artifacts": artifacts})
        artifacts["run_state"] = str(run_dir / "run-state.json")
        report["artifacts"] = artifacts
        return InvocationResult(
            workflow=WORKFLOW_ID,
            status=WorkflowStatus.FAILED,
            artifact_paths=artifacts,
            summary_text=f"{WORKFLOW_ID} failed with code={exc.code}",
            failures=[failure],
            resume_key={"schema_version": SCHEMA_VERSION, "run_state": str(run_dir / "run-state.json")},
            report=report,
            run_id=run_id,
        )

    summary = {
        "invocation_status": "completed",
        "connector_id": invocation["connector_id"],
        "operation_id": invocation["operation_id"],
        "operation_class": invocation["operation_class"],
        "dry_run": invocation["dry_run"],
        "controller_owned_path": True,
        "raw_mcp_used": False,
        "direct_model_tool_access_used": False,
        "external_network_called": False,
        "runtime_registry_changed": False,
        "target_repository_changed": False,
    }
    report = {
        "kind": "connector_invocation_report",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "summary": summary,
        "invocation": invocation,
        "errors": [],
        "artifacts": artifacts,
        "created_at": utc_now(),
    }
    write_json(run_dir / "connector-invocation.json", report)
    artifacts["connector_invocation"] = str(run_dir / "connector-invocation.json")
    write_json(run_dir / "run-state.json", {**report, "kind": "connector_invocation_run_state", "artifacts": artifacts})
    artifacts["run_state"] = str(run_dir / "run-state.json")
    report["artifacts"] = artifacts
    return InvocationResult(
        workflow=WORKFLOW_ID,
        status=WorkflowStatus.COMPLETED,
        artifact_paths=artifacts,
        summary_text=f"{WORKFLOW_ID} completed with invocation_status=completed",
        failures=[],
        resume_key={"schema_version": SCHEMA_VERSION, "run_state": str(run_dir / "run-state.json")},
        report=report,
        run_id=run_id,
    )
