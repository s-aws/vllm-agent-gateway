"""Approval-gated skill-batch registration workflow."""

from __future__ import annotations

import hashlib
import json
import shutil
from copy import deepcopy
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus
from vllm_agent_gateway.skills.batches import build_skill_batch_report, read_batch_manifest
from vllm_agent_gateway.skills.evals import (
    MANUAL_ARTIFACT_IDS,
    SKILL_EVALS_PATH,
    run_skill_eval_catalog,
    skill_output_artifacts,
    workflow_result_artifacts,
)
from vllm_agent_gateway.skills.registry import (
    SCHEMA_VERSION,
    SKILL_REGISTRY_PATH,
    SkillRegistryError,
    load_skill_registry,
    read_json_object,
    validate_skill_registry_manifest,
)
from vllm_agent_gateway.skills.scale import build_skill_scale_report


WORKFLOW_ID = "skill_batch.register"
DEFAULT_OUTPUT_DIR = "skill-batch-registrations"


class SkillBatchRegistrationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "skill_batch_registration_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class SkillBatchRegistrationRequest:
    config_root: Path | str = "."
    output_root: Path | str = ".agentic_controller"
    workflow: str = WORKFLOW_ID
    schema_version: int = SCHEMA_VERSION
    proposal_path: str | None = None
    proposal_run_id: str | None = None
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
    ) -> "SkillBatchRegistrationRequest":
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


def write_json(path: Path, value: dict[str, Any], *, sort_keys: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=sort_keys) + "\n", encoding="utf-8")


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{artifact_timestamp()}.tmp")
    temp_path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    temp_path.replace(path)


def bounded_string(value: Any, limit: int = 2000) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        raise SkillBatchRegistrationError(
            f"{label} is outside allowed registration roots: {resolved}. Allowed roots: {allowed}",
            code="registration_path_not_allowed",
            status=HTTPStatus.FORBIDDEN,
        )
    return resolved


def string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise SkillBatchRegistrationError(f"{label} must be a non-empty list of strings.")
    return list(value)


def validate_request(request: SkillBatchRegistrationRequest) -> None:
    if request.workflow != WORKFLOW_ID:
        raise SkillBatchRegistrationError("workflow must be skill_batch.register.", code="unsupported_workflow")
    if request.schema_version != SCHEMA_VERSION:
        raise SkillBatchRegistrationError("schema_version must be 1.", code="unsupported_schema_version")
    if bool(request.proposal_path) == bool(request.proposal_run_id):
        raise SkillBatchRegistrationError(
            "Exactly one of proposal_path or proposal_run_id is required.",
            code="missing_proposal_reference",
            status=HTTPStatus.BAD_REQUEST,
        )
    validate_approval(request.approval)


def validate_approval(approval: Any) -> dict[str, Any]:
    if not isinstance(approval, dict):
        raise SkillBatchRegistrationError(
            "approval must be a JSON object.",
            code="missing_registration_approval",
            status=HTTPStatus.BAD_REQUEST,
        )
    if approval.get("status") != "approved_for_skill_registration":
        raise SkillBatchRegistrationError(
            "skill_batch.register requires approval.status=approved_for_skill_registration.",
            code="missing_registration_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    scope = approval.get("scope")
    scopes = set(scope) if isinstance(scope, list) else {scope} if isinstance(scope, str) else set()
    if "skill_batch_registration" not in scopes:
        raise SkillBatchRegistrationError(
            "skill_batch.register requires approval.scope=skill_batch_registration.",
            code="invalid_registration_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    if approval.get("runtime_registry_append") is not True:
        raise SkillBatchRegistrationError(
            "skill_batch.register requires approval.runtime_registry_append=true.",
            code="invalid_registration_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    if approval.get("skill_body_install") is not True:
        raise SkillBatchRegistrationError(
            "skill_batch.register requires approval.skill_body_install=true.",
            code="invalid_registration_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    approval_refs = string_list(approval.get("approval_refs"), "approval.approval_refs")
    return {
        "status": approval["status"],
        "scope": sorted(scopes),
        "runtime_registry_append": True,
        "skill_body_install": True,
        "approval_refs": approval_refs,
    }


def proposal_path_candidates(output_root: Path, run_id: str) -> list[Path]:
    candidates = [output_root / "skill-batch-proposals" / run_id / "skill-batch-proposal.json"]
    workflow_router_root = output_root / "workflow-router"
    if workflow_router_root.exists():
        candidates.extend(workflow_router_root.glob(f"*/skill-batch-proposals/{run_id}/skill-batch-proposal.json"))
    return candidates


def resolve_proposal_path(request: SkillBatchRegistrationRequest) -> Path:
    output_root = Path(request.output_root).resolve()
    config_root = Path(request.config_root).resolve()
    if request.proposal_path:
        raw_path = Path(request.proposal_path)
        path = raw_path if raw_path.is_absolute() else output_root / raw_path
        return require_under_any(path, (output_root, config_root), "proposal_path")
    assert request.proposal_run_id is not None
    for candidate in proposal_path_candidates(output_root, request.proposal_run_id):
        if candidate.is_file():
            return require_under_any(candidate, (output_root, config_root), "proposal_run_id")
    raise SkillBatchRegistrationError(
        f"Could not find skill-batch proposal artifact for proposal_run_id={request.proposal_run_id}.",
        code="proposal_not_found",
        status=HTTPStatus.NOT_FOUND,
    )


def load_proposal(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SkillBatchRegistrationError(f"Missing proposal artifact: {path}", code="proposal_not_found") from exc
    except json.JSONDecodeError as exc:
        raise SkillBatchRegistrationError(f"Invalid proposal artifact JSON: {exc}", code="invalid_proposal") from exc
    if not isinstance(value, dict):
        raise SkillBatchRegistrationError("Proposal artifact must contain a JSON object.", code="invalid_proposal")
    if value.get("kind") != "skill_batch_proposal":
        raise SkillBatchRegistrationError("Proposal artifact kind must be skill_batch_proposal.", code="invalid_proposal")
    if value.get("status") != "ready":
        raise SkillBatchRegistrationError("Only ready skill-batch proposals can be registered.", code="proposal_not_ready")
    summary = value.get("summary") if isinstance(value.get("summary"), dict) else {}
    if summary.get("batch_validation_status") != "passed":
        raise SkillBatchRegistrationError("Proposal batch validation status must be passed.", code="proposal_not_ready")
    if int(summary.get("do_not_admit_count", 0)) != 0:
        raise SkillBatchRegistrationError("Proposal has do-not-admit entries and cannot be registered.", code="proposal_not_ready")
    return value


def resolve_batch_path(proposal: dict[str, Any], proposal_path: Path, output_root: Path, config_root: Path) -> Path:
    artifacts = proposal.get("artifacts") if isinstance(proposal.get("artifacts"), dict) else {}
    raw_path = artifacts.get("draft_batch_manifest")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise SkillBatchRegistrationError("Proposal is missing artifacts.draft_batch_manifest.", code="invalid_proposal")
    candidate = Path(raw_path)
    path = candidate if candidate.is_absolute() else proposal_path.parent / candidate
    return require_under_any(path, (output_root, config_root), "draft_batch_manifest")


def validate_proposal_manifest_matches(proposal: dict[str, Any], manifest: dict[str, Any]) -> None:
    embedded = proposal.get("draft_batch_manifest")
    if not isinstance(embedded, dict):
        raise SkillBatchRegistrationError("Proposal is missing draft_batch_manifest.", code="invalid_proposal")
    if embedded != manifest:
        raise SkillBatchRegistrationError(
            "Proposal draft_batch_manifest does not match artifacts.draft_batch_manifest.",
            code="proposal_manifest_mismatch",
        )


def existing_known_artifacts(config_root: Path) -> set[str]:
    workflows_manifest = read_json_object(config_root / "runtime" / "workflows.json", "workflow registry")
    existing_skills = load_skill_registry(config_root)
    return workflow_result_artifacts(workflows_manifest) | skill_output_artifacts(existing_skills) | MANUAL_ARTIFACT_IDS


def validate_expected_artifacts_are_existing(manifest: dict[str, Any], *, config_root: Path) -> list[dict[str, Any]]:
    known = existing_known_artifacts(config_root)
    checks: list[dict[str, Any]] = []
    eval_cases = manifest.get("eval_cases")
    if not isinstance(eval_cases, list):
        raise SkillBatchRegistrationError("Skill batch manifest eval_cases must be a list.", code="invalid_batch_manifest")
    for eval_case in eval_cases:
        if not isinstance(eval_case, dict):
            raise SkillBatchRegistrationError("Skill batch eval case must be an object.", code="invalid_batch_manifest")
        case_id = eval_case.get("id") if isinstance(eval_case.get("id"), str) else "<unknown>"
        expected_artifacts = eval_case.get("expected_artifacts")
        if not isinstance(expected_artifacts, list):
            raise SkillBatchRegistrationError(
                f"Skill batch eval case {case_id} expected_artifacts must be a list.",
                code="invalid_batch_manifest",
            )
        unknown = sorted(item for item in expected_artifacts if isinstance(item, str) and item not in known)
        checks.append(
            {
                "eval_case_id": case_id,
                "expected_artifacts": [item for item in expected_artifacts if isinstance(item, str)],
                "unknown_artifacts": unknown,
                "status": "failed" if unknown else "passed",
            }
        )
        if unknown:
            raise SkillBatchRegistrationError(
                f"Skill batch eval case {case_id} references output artifact(s) that are not implemented yet: "
                f"{', '.join(unknown)}",
                code="unimplemented_output_artifact",
            )
    return checks


def load_runtime_manifests(config_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    registry_manifest = read_json_object(config_root / SKILL_REGISTRY_PATH, "skill registry")
    eval_manifest = read_json_object(config_root / SKILL_EVALS_PATH, "skill eval catalog")
    if not isinstance(registry_manifest.get("skills"), list):
        raise SkillBatchRegistrationError("runtime/skills.json must contain a skills list.", code="invalid_skill_registry")
    if not isinstance(eval_manifest.get("cases"), list):
        raise SkillBatchRegistrationError("runtime/skill_evals.json must contain a cases list.", code="invalid_skill_evals")
    return registry_manifest, eval_manifest


def skill_source_path(skill: dict[str, Any], *, config_root: Path, output_root: Path) -> Path:
    raw_path = skill.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise SkillBatchRegistrationError("Skill batch skill.path must be a string.", code="invalid_batch_manifest")
    candidate = Path(raw_path)
    path = candidate if candidate.is_absolute() else config_root / candidate
    return require_under_any(path, (output_root, config_root), f"{skill.get('id', '<unknown>')}.path")


def installed_skill_path(config_root: Path, skill_id: str) -> Path:
    return config_root / ".qwen" / "skills" / skill_id / "SKILL.md"


def install_skill_bodies(
    manifest: dict[str, Any],
    *,
    config_root: Path,
    output_root: Path,
) -> tuple[list[dict[str, Any]], list[Path]]:
    raw_skills = manifest.get("skills")
    if not isinstance(raw_skills, list) or not raw_skills:
        raise SkillBatchRegistrationError("Skill batch manifest skills must be a non-empty list.", code="invalid_batch_manifest")
    installed_skills: list[dict[str, Any]] = []
    installed_paths: list[Path] = []
    for raw_skill in raw_skills:
        if not isinstance(raw_skill, dict):
            raise SkillBatchRegistrationError("Skill batch skill entries must be objects.", code="invalid_batch_manifest")
        skill_id = raw_skill.get("id")
        if not isinstance(skill_id, str) or not skill_id.strip():
            raise SkillBatchRegistrationError("Skill batch skill entries must include id.", code="invalid_batch_manifest")
        source = skill_source_path(raw_skill, config_root=config_root, output_root=output_root)
        target = installed_skill_path(config_root, skill_id)
        if target.exists():
            raise SkillBatchRegistrationError(
                f"Refusing to overwrite existing installed skill body: {target}",
                code="installed_skill_body_exists",
            )
        target.parent.mkdir(parents=True, exist_ok=False)
        shutil.copy2(source, target)
        installed = deepcopy(raw_skill)
        installed["path"] = target.relative_to(config_root).as_posix()
        installed_skills.append(installed)
        installed_paths.append(target)
    return installed_skills, installed_paths


def restore_backups(
    *,
    registry_path: Path,
    eval_path: Path,
    registry_backup: Path,
    eval_backup: Path,
    installed_paths: list[Path],
    config_root: Path,
) -> None:
    shutil.copy2(registry_backup, registry_path)
    shutil.copy2(eval_backup, eval_path)
    skill_root = config_root / ".qwen" / "skills"
    for installed in installed_paths:
        if not is_under(installed, skill_root):
            continue
        if installed.exists():
            installed.unlink()
        try:
            installed.parent.rmdir()
        except OSError:
            pass


def install_batch(
    manifest: dict[str, Any],
    *,
    config_root: Path,
    output_root: Path,
    run_dir: Path,
) -> dict[str, Any]:
    registry_path = config_root / SKILL_REGISTRY_PATH
    eval_path = config_root / SKILL_EVALS_PATH
    backup_dir = run_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    registry_backup = backup_dir / "skills.before.json"
    eval_backup = backup_dir / "skill-evals.before.json"
    shutil.copy2(registry_path, registry_backup)
    shutil.copy2(eval_path, eval_backup)
    before_hashes = {
        "runtime/skills.json": sha256_file(registry_path),
        "runtime/skill_evals.json": sha256_file(eval_path),
    }
    installed_paths: list[Path] = []
    try:
        installed_skills, installed_paths = install_skill_bodies(
            manifest,
            config_root=config_root,
            output_root=output_root,
        )
        registry_manifest, eval_manifest = load_runtime_manifests(config_root)
        eval_cases = deepcopy(manifest["eval_cases"])
        registry_manifest["skills"].extend(installed_skills)
        eval_manifest["cases"].extend(eval_cases)
        atomic_write_json(registry_path, registry_manifest)
        atomic_write_json(eval_path, eval_manifest)

        validate_skill_registry_manifest(read_json_object(registry_path, "skill registry"), config_root)
        eval_case_ids = [case["id"] for case in eval_cases if isinstance(case, dict) and isinstance(case.get("id"), str)]
        eval_report = run_skill_eval_catalog(
            config_root,
            output_path=run_dir / "skill-eval-report.json",
            case_ids=eval_case_ids,
        )
        if eval_report["status"] != "passed":
            raise SkillBatchRegistrationError(
                "Skill eval catalog failed after registration.",
                code="post_install_eval_failed",
            )
        scale_report = build_skill_scale_report(
            config_root,
            output_path=run_dir / "scale-report.json",
        )
        if scale_report["status"] != "passed":
            raise SkillBatchRegistrationError(
                "Skill scale report failed after registration.",
                code="post_install_scale_failed",
            )
    except (SkillBatchRegistrationError, SkillRegistryError, OSError) as exc:
        restore_backups(
            registry_path=registry_path,
            eval_path=eval_path,
            registry_backup=registry_backup,
            eval_backup=eval_backup,
            installed_paths=installed_paths,
            config_root=config_root,
        )
        if isinstance(exc, SkillBatchRegistrationError):
            raise
        raise SkillBatchRegistrationError(
            f"Skill batch registration failed and runtime files were restored: {exc}",
            code="registration_rollback_completed",
        ) from exc

    after_hashes = {
        "runtime/skills.json": sha256_file(registry_path),
        "runtime/skill_evals.json": sha256_file(eval_path),
    }
    for path in installed_paths:
        after_hashes[path.relative_to(config_root).as_posix()] = sha256_file(path)
    return {
        "installed_skills": installed_skills,
        "installed_eval_cases": eval_cases,
        "installed_paths": installed_paths,
        "backup_paths": {
            "runtime/skills.json": str(registry_backup),
            "runtime/skill_evals.json": str(eval_backup),
        },
        "before_hashes": before_hashes,
        "after_hashes": after_hashes,
    }


def rollback_instructions(install_result: dict[str, Any], *, config_root: Path) -> dict[str, Any]:
    installed_paths = [
        path.relative_to(config_root).as_posix()
        for path in install_result["installed_paths"]
        if isinstance(path, Path)
    ]
    return {
        "kind": "skill_batch_registration_rollback_instructions",
        "schema_version": SCHEMA_VERSION,
        "restore_backups": install_result["backup_paths"],
        "remove_installed_skill_files": installed_paths,
        "note": "Restore the two runtime JSON backups and remove installed skill files if the registered batch must be reverted.",
    }


def invoke_skill_batch_registration(request: SkillBatchRegistrationRequest) -> InvocationResult:
    validate_request(request)
    output_root = Path(request.output_root).resolve()
    config_root = Path(request.config_root).resolve()
    run_id = f"skill-batch-registration-{artifact_timestamp()}"
    run_dir = output_root / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, str] = {}
    approval = validate_approval(request.approval)
    request_artifact = {
        "kind": "skill_batch_registration_request",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "proposal_path": request.proposal_path,
        "proposal_run_id": request.proposal_run_id,
        "approval": approval,
        "metadata": request.metadata,
        "created_at": utc_now(),
    }
    write_json(run_dir / "request.json", request_artifact)
    artifacts["request"] = str(run_dir / "request.json")

    proposal_path = resolve_proposal_path(request)
    proposal = load_proposal(proposal_path)
    artifacts["proposal"] = str(proposal_path)
    batch_path = resolve_batch_path(proposal, proposal_path, output_root, config_root)
    artifacts["draft_batch_manifest"] = str(batch_path)
    manifest = read_batch_manifest(batch_path)
    validate_proposal_manifest_matches(proposal, manifest)
    artifact_checks = validate_expected_artifacts_are_existing(manifest, config_root=config_root)

    batch_report = build_skill_batch_report(
        config_root,
        batch_path,
        output_path=run_dir / "batch-validation-before-install.json",
    )
    artifacts["batch_validation_report"] = str(run_dir / "batch-validation-before-install.json")
    if batch_report["status"] != "passed":
        raise SkillBatchRegistrationError(
            "Skill batch validation failed before registration.",
            code="batch_validation_failed",
        )

    install_result = install_batch(
        manifest,
        config_root=config_root,
        output_root=output_root,
        run_dir=run_dir,
    )
    artifacts["skill_eval_report"] = str(run_dir / "skill-eval-report.json")
    artifacts["scale_report"] = str(run_dir / "scale-report.json")

    rollback = rollback_instructions(install_result, config_root=config_root)
    write_json(run_dir / "rollback-instructions.json", rollback)
    artifacts["rollback_instructions"] = str(run_dir / "rollback-instructions.json")

    installed_skill_ids = [skill["id"] for skill in install_result["installed_skills"]]
    installed_eval_case_ids = [case["id"] for case in install_result["installed_eval_cases"]]
    hash_proof = {
        "before": install_result["before_hashes"],
        "after": install_result["after_hashes"],
        "changed": sorted(
            key
            for key, after_hash in install_result["after_hashes"].items()
            if install_result["before_hashes"].get(key) != after_hash
        ),
    }
    summary = {
        "registration_status": "installed",
        "skill_count": len(installed_skill_ids),
        "eval_case_count": len(installed_eval_case_ids),
        "installed_skill_ids": installed_skill_ids,
        "installed_eval_case_ids": installed_eval_case_ids,
        "batch_validation_status": batch_report["status"],
        "runtime_registry_changed": True,
        "target_repository_changed": False,
        "next_action": "run_skill_evals_and_live_suite",
    }
    registration = {
        "kind": "skill_batch_registration",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": "installed",
        "summary": summary,
        "approval": approval,
        "proposal_run_id": proposal.get("run_id"),
        "proposal_path": str(proposal_path),
        "draft_batch_manifest": str(batch_path),
        "artifact_implementation_checks": artifact_checks,
        "hash_proof": hash_proof,
        "rollback_instructions": rollback,
        "created_at": utc_now(),
    }
    write_json(run_dir / "skill-batch-registration.json", registration)
    artifacts["skill_batch_registration"] = str(run_dir / "skill-batch-registration.json")

    run_state = {
        "kind": "skill_batch_registration_run_state",
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
        "kind": "skill_batch_registration_report",
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
