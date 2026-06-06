"""Read-only skill-pack validation workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus
from vllm_agent_gateway.skills.packs import build_skill_pack_report
from vllm_agent_gateway.skills.registry import SCHEMA_VERSION


WORKFLOW_ID = "skill_pack.validate"
DEFAULT_OUTPUT_DIR = "skill-pack-validations"


class SkillPackValidationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "skill_pack_validation_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class SkillPackValidationRequest:
    config_root: Path | str = "."
    output_root: Path | str = ".agentic_controller"
    workflow: str = WORKFLOW_ID
    schema_version: int = SCHEMA_VERSION
    pack_path: str | None = None
    role_id: str = "architect/default"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        config_root: Path,
        output_root: Path,
    ) -> "SkillPackValidationRequest":
        values: dict[str, Any] = {
            "config_root": config_root,
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


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def require_under_any(path: Path, roots: tuple[Path, ...], label: str) -> Path:
    resolved = path.resolve()
    if not any(is_under(resolved, root) for root in roots):
        allowed = ", ".join(str(root.resolve()) for root in roots)
        raise SkillPackValidationError(
            f"{label} is outside allowed pack roots: {resolved}. Allowed roots: {allowed}",
            code="pack_path_not_allowed",
            status=HTTPStatus.FORBIDDEN,
        )
    return resolved


def validate_request(request: SkillPackValidationRequest) -> None:
    if request.workflow != WORKFLOW_ID:
        raise SkillPackValidationError("workflow must be skill_pack.validate.", code="unsupported_workflow")
    if request.schema_version != SCHEMA_VERSION:
        raise SkillPackValidationError("schema_version must be 1.", code="unsupported_schema_version")
    if not isinstance(request.pack_path, str) or not request.pack_path.strip():
        raise SkillPackValidationError("pack_path is required.", code="missing_pack_path", status=HTTPStatus.BAD_REQUEST)


def resolve_pack_path(request: SkillPackValidationRequest) -> Path:
    output_root = Path(request.output_root).resolve()
    config_root = Path(request.config_root).resolve()
    assert request.pack_path is not None
    raw_path = Path(request.pack_path)
    path = raw_path if raw_path.is_absolute() else output_root / raw_path
    return require_under_any(path, (output_root, config_root), "pack_path")


def invoke_skill_pack_validation(request: SkillPackValidationRequest) -> InvocationResult:
    validate_request(request)
    output_root = Path(request.output_root).resolve()
    config_root = Path(request.config_root).resolve()
    run_id = f"skill-pack-validation-{artifact_timestamp()}"
    run_dir = output_root / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, str] = {}
    request_artifact = {
        "kind": "skill_pack_validation_request",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "pack_path": request.pack_path,
        "metadata": request.metadata,
        "created_at": utc_now(),
    }
    write_json(run_dir / "request.json", request_artifact)
    artifacts["request"] = str(run_dir / "request.json")

    pack_path = resolve_pack_path(request)
    pack_report = build_skill_pack_report(
        config_root,
        pack_path,
        output_path=run_dir / "skill-pack-validation.json",
    )
    artifacts["skill_pack_validation"] = str(run_dir / "skill-pack-validation.json")

    status = "ready" if pack_report["status"] == "passed" else "failed"
    summary = {
        "validation_status": pack_report["status"],
        "pack_id": pack_report.get("pack_id"),
        "pack_version": pack_report.get("pack_version"),
        "skill_count": pack_report["summary"]["skill_count"],
        "eval_case_count": pack_report["summary"]["eval_case_count"],
        "namespace_count": pack_report["summary"]["namespace_count"],
        "runtime_registry_changed": False,
        "target_repository_changed": False,
        "next_action": "review_then_install_pack_with_approval" if status == "ready" else "revise_or_reject_pack",
    }
    validation = {
        "kind": "skill_pack_validation",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": status,
        "summary": summary,
        "pack_report": pack_report,
        "errors": pack_report.get("errors", []),
        "created_at": utc_now(),
    }
    write_json(run_dir / "skill-pack-validation-artifact.json", validation)
    artifacts["skill_pack_validation_artifact"] = str(run_dir / "skill-pack-validation-artifact.json")

    run_state = {
        "kind": "skill_pack_validation_run_state",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value if status == "ready" else WorkflowStatus.FAILED.value,
        "summary": summary,
        "artifacts": artifacts,
        "updated_at": utc_now(),
    }
    write_json(run_dir / "run-state.json", run_state)
    artifacts["run_state"] = str(run_dir / "run-state.json")

    report = {
        "kind": "skill_pack_validation_report",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": run_state["status"],
        "summary": summary,
        "validation": validation,
        "warnings": [],
        "artifacts": artifacts,
    }
    return InvocationResult(
        workflow=WORKFLOW_ID,
        status=WorkflowStatus.COMPLETED if status == "ready" else WorkflowStatus.FAILED,
        artifact_paths=artifacts,
        summary_text=f"{WORKFLOW_ID} completed with validation_status={pack_report['status']}",
        failures=[{"message": error} for error in pack_report.get("errors", [])],
        resume_key={"schema_version": SCHEMA_VERSION, "run_state": str(run_dir / "run-state.json")},
        report=report,
        run_id=run_id,
    )
