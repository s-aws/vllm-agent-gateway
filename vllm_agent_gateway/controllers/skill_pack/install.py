"""Approval-gated skill-pack installation workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.controllers.skill_batch.register import (
    SkillBatchRegistrationError,
    install_batch,
    rollback_instructions,
    sha256_file,
    string_list,
)
from vllm_agent_gateway.controllers.skill_pack.validate import (
    SkillPackValidationError,
    require_under_any,
)
from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus
from vllm_agent_gateway.skills.packs import build_skill_pack_report, read_pack_manifest, skill_pack_to_batch_manifest
from vllm_agent_gateway.skills.registry import SCHEMA_VERSION


WORKFLOW_ID = "skill_pack.install"
DEFAULT_OUTPUT_DIR = "skill-pack-installations"


class SkillPackInstallError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "skill_pack_install_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class SkillPackInstallRequest:
    config_root: Path | str = "."
    output_root: Path | str = ".agentic_controller"
    workflow: str = WORKFLOW_ID
    schema_version: int = SCHEMA_VERSION
    pack_path: str | None = None
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
    ) -> "SkillPackInstallRequest":
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


def validate_approval(approval: Any) -> dict[str, Any]:
    if not isinstance(approval, dict):
        raise SkillPackInstallError(
            "approval must be a JSON object.",
            code="missing_skill_pack_install_approval",
            status=HTTPStatus.BAD_REQUEST,
        )
    if approval.get("status") != "approved_for_skill_pack_install":
        raise SkillPackInstallError(
            "skill_pack.install requires approval.status=approved_for_skill_pack_install.",
            code="missing_skill_pack_install_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    scope = approval.get("scope")
    scopes = set(scope) if isinstance(scope, list) else {scope} if isinstance(scope, str) else set()
    if "skill_pack_install" not in scopes:
        raise SkillPackInstallError(
            "skill_pack.install requires approval.scope=skill_pack_install.",
            code="invalid_skill_pack_install_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    if approval.get("runtime_registry_append") is not True:
        raise SkillPackInstallError(
            "skill_pack.install requires approval.runtime_registry_append=true.",
            code="invalid_skill_pack_install_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    if approval.get("skill_body_install") is not True:
        raise SkillPackInstallError(
            "skill_pack.install requires approval.skill_body_install=true.",
            code="invalid_skill_pack_install_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    try:
        approval_refs = string_list(approval.get("approval_refs"), "approval.approval_refs")
    except RuntimeError as exc:
        raise SkillPackInstallError(
            str(exc),
            code="invalid_skill_pack_install_approval",
            status=HTTPStatus.FORBIDDEN,
        ) from exc
    return {
        "status": approval["status"],
        "scope": sorted(scopes),
        "runtime_registry_append": True,
        "skill_body_install": True,
        "approval_refs": approval_refs,
    }


def validate_request(request: SkillPackInstallRequest) -> None:
    if request.workflow != WORKFLOW_ID:
        raise SkillPackInstallError("workflow must be skill_pack.install.", code="unsupported_workflow")
    if request.schema_version != SCHEMA_VERSION:
        raise SkillPackInstallError("schema_version must be 1.", code="unsupported_schema_version")
    if not isinstance(request.pack_path, str) or not request.pack_path.strip():
        raise SkillPackInstallError("pack_path is required.", code="missing_pack_path", status=HTTPStatus.BAD_REQUEST)
    validate_approval(request.approval)


def resolve_pack_path(request: SkillPackInstallRequest) -> Path:
    output_root = Path(request.output_root).resolve()
    config_root = Path(request.config_root).resolve()
    assert request.pack_path is not None
    raw_path = Path(request.pack_path)
    path = raw_path if raw_path.is_absolute() else output_root / raw_path
    try:
        return require_under_any(path, (output_root, config_root), "pack_path")
    except SkillPackValidationError as exc:
        raise SkillPackInstallError(str(exc), code=exc.code, status=exc.status) from exc


def changed_hashes(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(key for key, value in after.items() if before.get(key) != value)


def invoke_skill_pack_install(request: SkillPackInstallRequest) -> InvocationResult:
    validate_request(request)
    output_root = Path(request.output_root).resolve()
    config_root = Path(request.config_root).resolve()
    run_id = f"skill-pack-install-{artifact_timestamp()}"
    run_dir = output_root / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, str] = {}
    approval = validate_approval(request.approval)
    request_artifact = {
        "kind": "skill_pack_install_request",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "pack_path": request.pack_path,
        "approval": approval,
        "metadata": request.metadata,
        "created_at": utc_now(),
    }
    write_json(run_dir / "request.json", request_artifact)
    artifacts["request"] = str(run_dir / "request.json")

    pack_path = resolve_pack_path(request)
    artifacts["skill_pack_manifest"] = str(pack_path)
    pack_report = build_skill_pack_report(
        config_root,
        pack_path,
        output_path=run_dir / "skill-pack-validation-before-install.json",
    )
    artifacts["skill_pack_validation"] = str(run_dir / "skill-pack-validation-before-install.json")
    if pack_report["status"] != "passed":
        errors = pack_report.get("errors", [])
        detail = f": {errors[0]}" if errors else "."
        raise SkillPackInstallError(
            f"Skill pack validation failed before install{detail}",
            code="skill_pack_validation_failed",
        )

    manifest = read_pack_manifest(pack_path)
    batch_manifest = skill_pack_to_batch_manifest(manifest)
    try:
        install_result = install_batch(
            batch_manifest,
            config_root=config_root,
            output_root=output_root,
            run_dir=run_dir,
        )
    except SkillBatchRegistrationError as exc:
        raise SkillPackInstallError(str(exc), code=exc.code, status=exc.status) from exc
    artifacts["skill_eval_report"] = str(run_dir / "skill-eval-report.json")
    artifacts["scale_report"] = str(run_dir / "scale-report.json")

    rollback = rollback_instructions(install_result, config_root=config_root)
    rollback["kind"] = "skill_pack_install_rollback_instructions"
    rollback["note"] = "Restore recorded runtime JSON backups and remove installed skill files if the installed pack must be reverted."
    write_json(run_dir / "rollback-instructions.json", rollback)
    artifacts["rollback_instructions"] = str(run_dir / "rollback-instructions.json")

    installed_skill_ids = [skill["id"] for skill in install_result["installed_skills"]]
    installed_eval_case_ids = [case["id"] for case in install_result["installed_eval_cases"]]
    hash_proof = {
        "before": install_result["before_hashes"],
        "after": install_result["after_hashes"],
        "changed": changed_hashes(install_result["before_hashes"], install_result["after_hashes"]),
    }
    for path in install_result["installed_paths"]:
        if isinstance(path, Path):
            hash_proof["after"][path.relative_to(config_root).as_posix()] = sha256_file(path)
    summary = {
        "install_status": "installed",
        "pack_id": pack_report["pack_id"],
        "pack_version": pack_report.get("pack_version"),
        "skill_count": len(installed_skill_ids),
        "eval_case_count": len(installed_eval_case_ids),
        "installed_skill_ids": installed_skill_ids,
        "installed_eval_case_ids": installed_eval_case_ids,
        "pack_validation_status": pack_report["status"],
        "runtime_registry_changed": True,
        "target_repository_changed": False,
        "next_action": "run_skill_evals_and_live_suite",
    }
    installation = {
        "kind": "skill_pack_installation",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": "installed",
        "summary": summary,
        "approval": approval,
        "pack_path": str(pack_path),
        "pack_validation": pack_report,
        "hash_proof": hash_proof,
        "rollback_instructions": rollback,
        "created_at": utc_now(),
    }
    write_json(run_dir / "skill-pack-installation.json", installation)
    artifacts["skill_pack_installation"] = str(run_dir / "skill-pack-installation.json")

    run_state = {
        "kind": "skill_pack_install_run_state",
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
        "kind": "skill_pack_install_report",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "summary": summary,
        "installation": installation,
        "warnings": [],
        "artifacts": artifacts,
    }
    return InvocationResult(
        workflow=WORKFLOW_ID,
        status=WorkflowStatus.COMPLETED,
        artifact_paths=artifacts,
        summary_text=f"{WORKFLOW_ID} completed with install_status=installed",
        failures=[],
        resume_key={"schema_version": SCHEMA_VERSION, "run_state": str(run_dir / "run-state.json")},
        report=report,
        run_id=run_id,
    )
