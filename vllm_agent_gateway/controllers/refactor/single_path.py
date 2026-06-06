"""Controller-owned single-path refactor orchestration workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.controllers.code_investigation.plan import (
    CodeInvestigationRequest,
    invoke_code_investigation,
)
from vllm_agent_gateway.controllers.execution_planning.workflow import (
    WORKFLOW_ID as EXECUTION_PLANNING_WORKFLOW_ID,
    ExecutionPlanningInvocationRequest,
    invoke_execution_planning,
)
from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus


WORKFLOW_ID = "refactor.single_path"
SCHEMA_VERSION = 1
DEFAULT_OUTPUT_DIR = "refactor-single-path"
ALLOWED_MODES = {"investigation_only", "dry_run"}
DEFAULT_CONTEXT_TOOLS = ["structure_index", "git_grep", "read_file"]


class RefactorSinglePathError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "refactor_single_path_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class RefactorSinglePathRequest:
    config_root: Path | str = "."
    target_root: Path | str = "."
    output_root: Path | str = ".agentic_controller"
    workflow: str = WORKFLOW_ID
    schema_version: int = SCHEMA_VERSION
    user_request: str = ""
    behavior: str = ""
    mode: str = "investigation_only"
    entrypoint_hints: list[dict[str, Any]] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    allowed_context_tools: list[str] = field(default_factory=lambda: list(DEFAULT_CONTEXT_TOOLS))
    max_results: int = 50
    max_files: int = 10
    approval: dict[str, Any] = field(default_factory=dict)
    packet_operations: list[dict[str, Any]] = field(default_factory=list)
    budgets: dict[str, Any] = field(default_factory=dict)
    feedback: dict[str, Any] = field(default_factory=dict)
    role_id: str = "architect/default"
    role_base_url: str | None = None
    model: str | None = None

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        config_root: Path,
        target_root: Path,
        output_root: Path,
        role_base_url: str | None,
    ) -> "RefactorSinglePathRequest":
        values: dict[str, Any] = {
            "config_root": config_root,
            "target_root": target_root,
            "output_root": output_root,
            "role_base_url": role_base_url,
        }
        names = {item.name for item in fields(cls)}
        for key, value in payload.items():
            if key in names:
                values[key] = value
        return cls(**values)


def artifact_timestamp() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2) + "\n").encode("utf-8")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def validate_request(request: RefactorSinglePathRequest) -> None:
    if request.workflow != WORKFLOW_ID:
        raise RefactorSinglePathError("workflow must be refactor.single_path.", code="unsupported_workflow")
    if request.schema_version != SCHEMA_VERSION:
        raise RefactorSinglePathError("schema_version must be 1.")
    if request.mode not in ALLOWED_MODES:
        raise RefactorSinglePathError("Unsupported refactor mode.", code="unsupported_mode")
    if not isinstance(request.user_request, str) or not request.user_request.strip():
        raise RefactorSinglePathError("user_request is required.")
    if not isinstance(request.behavior, str):
        raise RefactorSinglePathError("behavior must be a string.")
    if not isinstance(request.entrypoint_hints, list) or not all(
        isinstance(item, dict) for item in request.entrypoint_hints
    ):
        raise RefactorSinglePathError("entrypoint_hints must be a list of objects.")
    if not isinstance(request.queries, list) or not all(isinstance(item, str) for item in request.queries):
        raise RefactorSinglePathError("queries must be a list of strings.")
    if not isinstance(request.paths, list) or not all(isinstance(item, str) for item in request.paths):
        raise RefactorSinglePathError("paths must be a list of strings.")
    if not isinstance(request.allowed_context_tools, list) or not all(
        isinstance(item, str) for item in request.allowed_context_tools
    ):
        raise RefactorSinglePathError("allowed_context_tools must be a list of strings.")
    if not isinstance(request.max_results, int) or isinstance(request.max_results, bool) or request.max_results < 1:
        raise RefactorSinglePathError("max_results must be an integer >= 1.")
    if not isinstance(request.max_files, int) or isinstance(request.max_files, bool) or request.max_files < 1:
        raise RefactorSinglePathError("max_files must be an integer >= 1.")
    if request.mode == "dry_run":
        if request.approval.get("status") != "approved_for_packet_design":
            raise RefactorSinglePathError(
                "dry_run requires packet-design approval.",
                code="missing_packet_design_approval",
                status=HTTPStatus.BAD_REQUEST,
            )
        if request.approval.get("apply_allowed") is True:
            raise RefactorSinglePathError(
                "Apply mode is not supported by refactor.single_path.",
                code="apply_mode_not_supported",
                status=HTTPStatus.BAD_REQUEST,
            )
        if not request.packet_operations:
            raise RefactorSinglePathError(
                "dry_run requires packet_operations.",
                code="missing_packet_operations",
                status=HTTPStatus.BAD_REQUEST,
            )


def prefixed_artifacts(prefix: str, artifacts: dict[str, str]) -> dict[str, str]:
    return {f"{prefix}_{key}": value for key, value in artifacts.items()}


def load_json_artifact(path_value: str | None) -> dict[str, Any]:
    if not path_value:
        return {}
    try:
        value = json.loads(Path(path_value).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def build_investigation_request(request: RefactorSinglePathRequest, run_dir: Path) -> CodeInvestigationRequest:
    return CodeInvestigationRequest(
        config_root=request.config_root,
        target_root=request.target_root,
        output_root=run_dir,
        user_request=request.user_request,
        behavior=request.behavior,
        entrypoint_hints=request.entrypoint_hints,
        queries=request.queries,
        paths=request.paths,
        allowed_context_tools=request.allowed_context_tools,
        max_results=request.max_results,
        max_files=request.max_files,
    )


def entrypoint_hints_from_plan(plan: dict[str, Any], fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    beginning = plan.get("likely_beginning_point") if isinstance(plan.get("likely_beginning_point"), dict) else {}
    path = beginning.get("path")
    if isinstance(path, str) and path:
        return [
            {
                "path": path,
                "symbol": beginning.get("symbol") if isinstance(beginning.get("symbol"), str) else None,
                "reason": "Resolved by refactor.single_path investigation.",
            }
        ]
    return fallback


def build_execution_planning_request(
    request: RefactorSinglePathRequest,
    run_dir: Path,
    investigation_result: InvocationResult,
    investigation_plan: dict[str, Any],
) -> ExecutionPlanningInvocationRequest:
    context = {
        "entrypoint_hints": entrypoint_hints_from_plan(investigation_plan, request.entrypoint_hints),
        "bounded_context": [
            {
                "source": WORKFLOW_ID,
                "investigation_run_id": investigation_result.run_id,
                "investigation_plan": investigation_result.artifact_paths.get("investigation_plan"),
                "summary": investigation_plan.get("multiple_path_assessment"),
            }
        ],
        "allowed_context_tools": ["structure_index", "git_grep", "read_file", "manual"],
    }
    payload: dict[str, Any] = {
        "workflow": EXECUTION_PLANNING_WORKFLOW_ID,
        "schema_version": SCHEMA_VERSION,
        "target_root": str(Path(request.target_root).resolve()),
        "user_request": request.user_request,
        "mode": "dry_run",
        "approval": request.approval,
        "context": context,
        "packet_operations": request.packet_operations,
        "budgets": request.budgets,
        "feedback": request.feedback,
        "role_id": request.role_id,
    }
    if request.model:
        payload["model"] = request.model
    return ExecutionPlanningInvocationRequest.from_payload(
        payload,
        config_root=Path(request.config_root).resolve(),
        target_root=Path(request.target_root).resolve(),
        output_root=run_dir,
        role_base_url=request.role_base_url,
    )


def summary_from_results(
    request: RefactorSinglePathRequest,
    investigation_result: InvocationResult,
    investigation_plan: dict[str, Any],
    execution_result: InvocationResult | None,
) -> dict[str, Any]:
    investigation_summary = (
        investigation_result.report.get("summary")
        if isinstance(investigation_result.report, dict) and isinstance(investigation_result.report.get("summary"), dict)
        else {}
    )
    summary = {
        "mode": request.mode,
        "target_root": str(Path(request.target_root).resolve()),
        "investigation_run_id": investigation_result.run_id,
        "execution_planning_run_id": execution_result.run_id if execution_result is not None else None,
        "beginning_point_status": investigation_summary.get("beginning_point_status"),
        "multiple_path_status": investigation_summary.get("multiple_path_status"),
        "source_file_count": investigation_summary.get("source_file_count"),
        "test_file_count": investigation_summary.get("test_file_count"),
        "refactor_status": "draft_packet_ready" if execution_result is not None else "approval_required",
    }
    seed = investigation_plan.get("implementation_packet_seed")
    if isinstance(seed, dict):
        summary["candidate_target_file_count"] = len(seed.get("candidate_target_files", [])) if isinstance(seed.get("candidate_target_files"), list) else 0
        summary["candidate_test_file_count"] = len(seed.get("candidate_test_files", [])) if isinstance(seed.get("candidate_test_files"), list) else 0
    verification_plan = investigation_plan.get("verification_plan")
    if isinstance(verification_plan, dict):
        commands = verification_plan.get("verification_commands")
        summary["verification_command_count"] = len(commands) if isinstance(commands, list) else 0
    return summary


def invoke_refactor_single_path(request: RefactorSinglePathRequest) -> InvocationResult:
    validate_request(request)
    target_root = Path(request.target_root).resolve()
    output_root = Path(request.output_root).resolve()
    run_id = f"refactor-single-path-{artifact_timestamp()}"
    run_dir = output_root / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {}

    request_artifact = {
        "kind": "refactor_single_path_request",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "target_root": str(target_root),
        "mode": request.mode,
        "user_request": request.user_request,
        "behavior": request.behavior,
        "entrypoint_hints": request.entrypoint_hints,
        "queries": request.queries,
        "paths": request.paths,
        "approval": request.approval,
        "packet_operations": request.packet_operations,
        "created_at": utc_now(),
    }
    write_json(run_dir / "request.json", request_artifact)
    artifacts["request"] = str(run_dir / "request.json")

    investigation_result = invoke_code_investigation(build_investigation_request(request, run_dir))
    artifacts.update(prefixed_artifacts("investigation", investigation_result.artifact_paths))
    investigation_plan = load_json_artifact(investigation_result.artifact_paths.get("investigation_plan"))

    execution_result: InvocationResult | None = None
    if request.mode == "dry_run":
        execution_result = invoke_execution_planning(
            build_execution_planning_request(request, run_dir, investigation_result, investigation_plan)
        )
        artifacts.update(prefixed_artifacts("execution_planning", execution_result.artifact_paths))

    summary = summary_from_results(request, investigation_result, investigation_plan, execution_result)
    refactor_plan = {
        "kind": "refactor_single_path_plan",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "target_root": str(target_root),
        "mode": request.mode,
        "summary": summary,
        "investigation": {
            "run_id": investigation_result.run_id,
            "artifacts": investigation_result.artifact_paths,
            "plan": investigation_plan,
        },
        "execution_planning": (
            {
                "run_id": execution_result.run_id,
                "artifacts": execution_result.artifact_paths,
                "status": execution_result.status.value,
            }
            if execution_result is not None
            else None
        ),
        "approval_gate": {
            "required_before_apply": True,
            "apply_supported": False,
            "next_allowed_workflow": "execution_planning.plan" if request.mode == "investigation_only" else "implementation.workflow draft artifacts only",
        },
    }
    write_json(run_dir / "refactor-plan.json", refactor_plan)
    artifacts["refactor_plan"] = str(run_dir / "refactor-plan.json")
    run_state = {
        "kind": "refactor_single_path_run_state",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "target_root": str(target_root),
        "summary": summary,
        "artifacts": artifacts,
        "updated_at": utc_now(),
    }
    write_json(run_dir / "run-state.json", run_state)
    artifacts["run_state"] = str(run_dir / "run-state.json")

    warnings: list[dict[str, Any]] = []
    if isinstance(investigation_result.report, dict):
        raw_warnings = investigation_result.report.get("warnings")
        if isinstance(raw_warnings, list):
            warnings.extend(item for item in raw_warnings if isinstance(item, dict))
    if execution_result is not None and isinstance(execution_result.report, dict):
        raw_warnings = execution_result.report.get("context_warnings")
        if isinstance(raw_warnings, list):
            warnings.extend(item for item in raw_warnings if isinstance(item, dict))

    report = {
        "kind": "refactor_single_path_report",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "summary": summary,
        "warnings": warnings,
        "artifacts": artifacts,
    }
    return InvocationResult(
        workflow=WORKFLOW_ID,
        status=WorkflowStatus.COMPLETED,
        artifact_paths=artifacts,
        summary_text=f"{WORKFLOW_ID} completed: {summary['refactor_status']}",
        failures=[],
        resume_key={"schema_version": SCHEMA_VERSION, "run_state": str(run_dir / "run-state.json")},
        report=report,
        run_id=run_id,
    )
