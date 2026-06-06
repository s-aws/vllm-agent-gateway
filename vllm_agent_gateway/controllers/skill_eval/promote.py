"""Approval-gated registered skill eval promotion workflow."""

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
from vllm_agent_gateway.skills.evals import (
    MANUAL_ARTIFACT_IDS,
    SKILL_EVALS_PATH,
    live_mapping_for_case,
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


WORKFLOW_ID = "skill_eval.promote"
DEFAULT_OUTPUT_DIR = "skill-eval-promotions"
DEFAULT_REQUIRED_TARGET_ROOTS = {
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
}
PROMOTION_EVAL_FIELDS = ("localhost_8000", "gateway_8300", "anythingllm")


class SkillEvalPromotionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "skill_eval_promotion_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class SkillEvalPromotionRequest:
    config_root: Path | str = "."
    output_root: Path | str = ".agentic_controller"
    workflow: str = WORKFLOW_ID
    schema_version: int = SCHEMA_VERSION
    skill_ids: list[str] | None = None
    registration_run_id: str | None = None
    approval: dict[str, Any] = field(default_factory=dict)
    proof: dict[str, Any] = field(default_factory=dict)
    allow_repromotion: bool = False
    role_id: str = "architect/default"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        config_root: Path,
        output_root: Path,
    ) -> "SkillEvalPromotionRequest":
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
        raise SkillEvalPromotionError(
            f"{label} is outside allowed promotion roots: {resolved}. Allowed roots: {allowed}",
            code="promotion_path_not_allowed",
            status=HTTPStatus.FORBIDDEN,
        )
    return resolved


def string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise SkillEvalPromotionError(f"{label} must be a non-empty list of strings.")
    return list(value)


def validate_approval(approval: Any) -> dict[str, Any]:
    if not isinstance(approval, dict):
        raise SkillEvalPromotionError(
            "approval must be a JSON object.",
            code="missing_promotion_approval",
            status=HTTPStatus.BAD_REQUEST,
        )
    if approval.get("status") != "approved_for_skill_promotion":
        raise SkillEvalPromotionError(
            "skill_eval.promote requires approval.status=approved_for_skill_promotion.",
            code="missing_promotion_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    scope = approval.get("scope")
    scopes = set(scope) if isinstance(scope, list) else {scope} if isinstance(scope, str) else set()
    if "skill_eval_promotion" not in scopes:
        raise SkillEvalPromotionError(
            "skill_eval.promote requires approval.scope=skill_eval_promotion.",
            code="invalid_promotion_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    if approval.get("eval_status_update") is not True:
        raise SkillEvalPromotionError(
            "skill_eval.promote requires approval.eval_status_update=true.",
            code="invalid_promotion_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    approval_refs = string_list(approval.get("approval_refs"), "approval.approval_refs")
    return {
        "status": approval["status"],
        "scope": sorted(scopes),
        "eval_status_update": True,
        "approval_refs": approval_refs,
    }


def validate_request(request: SkillEvalPromotionRequest) -> None:
    if request.workflow != WORKFLOW_ID:
        raise SkillEvalPromotionError("workflow must be skill_eval.promote.", code="unsupported_workflow")
    if request.schema_version != SCHEMA_VERSION:
        raise SkillEvalPromotionError("schema_version must be 1.", code="unsupported_schema_version")
    if bool(request.skill_ids) == bool(request.registration_run_id):
        raise SkillEvalPromotionError(
            "Exactly one of skill_ids or registration_run_id is required.",
            code="missing_skill_reference",
            status=HTTPStatus.BAD_REQUEST,
        )
    if request.skill_ids is not None:
        string_list(request.skill_ids, "skill_ids")
    validate_approval(request.approval)
    if request.proof is not None and not isinstance(request.proof, dict):
        raise SkillEvalPromotionError("proof must be a JSON object.", code="invalid_promotion_proof")


def registration_path_candidates(output_root: Path, run_id: str) -> list[Path]:
    candidates = [output_root / "skill-batch-registrations" / run_id / "skill-batch-registration.json"]
    workflow_router_root = output_root / "workflow-router"
    if workflow_router_root.exists():
        candidates.extend(workflow_router_root.glob(f"*/skill-batch-registrations/{run_id}/skill-batch-registration.json"))
    return candidates


def load_registration_artifact(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SkillEvalPromotionError(f"Missing registration artifact: {path}", code="registration_not_found") from exc
    except json.JSONDecodeError as exc:
        raise SkillEvalPromotionError(f"Invalid registration artifact JSON: {exc}", code="invalid_registration") from exc
    if not isinstance(value, dict):
        raise SkillEvalPromotionError("Registration artifact must contain a JSON object.", code="invalid_registration")
    if value.get("kind") != "skill_batch_registration":
        raise SkillEvalPromotionError(
            "Registration artifact kind must be skill_batch_registration.",
            code="invalid_registration",
        )
    if value.get("status") != "installed":
        raise SkillEvalPromotionError("Only installed skill-batch registrations can be promoted.", code="registration_not_ready")
    return value


def resolve_registration_artifact(request: SkillEvalPromotionRequest) -> Path:
    assert request.registration_run_id is not None
    output_root = Path(request.output_root).resolve()
    config_root = Path(request.config_root).resolve()
    for candidate in registration_path_candidates(output_root, request.registration_run_id):
        if candidate.is_file():
            return require_under_any(candidate, (output_root, config_root), "registration_run_id")
    raise SkillEvalPromotionError(
        f"Could not find skill-batch registration artifact for registration_run_id={request.registration_run_id}.",
        code="registration_not_found",
        status=HTTPStatus.NOT_FOUND,
    )


def normalize_skill_ids(request: SkillEvalPromotionRequest) -> tuple[list[str], str | None]:
    if request.skill_ids is not None:
        return sorted(set(string_list(request.skill_ids, "skill_ids"))), None
    registration_path = resolve_registration_artifact(request)
    registration = load_registration_artifact(registration_path)
    summary = registration.get("summary") if isinstance(registration.get("summary"), dict) else {}
    skill_ids = string_list(summary.get("installed_skill_ids"), "registration.summary.installed_skill_ids")
    return sorted(set(skill_ids)), str(registration_path)


def collect_proof_artifact_paths(value: Any, *, key: str | None = None) -> list[str]:
    path_keys = {"artifact_path", "report_path", "proof_path", "proof_artifact", "log_path", "path"}
    paths: list[str] = []
    if isinstance(value, dict):
        for item_key, item_value in value.items():
            if item_key in path_keys and isinstance(item_value, str) and item_value.strip():
                paths.append(item_value)
            else:
                paths.extend(collect_proof_artifact_paths(item_value, key=item_key))
    elif isinstance(value, list):
        for item in value:
            paths.extend(collect_proof_artifact_paths(item, key=key))
    return paths


def validate_proof_artifact_paths(
    proof: dict[str, Any],
    *,
    output_root: Path,
    config_root: Path,
) -> list[str]:
    validated: list[str] = []
    for path_value in collect_proof_artifact_paths(proof):
        candidate = Path(path_value)
        path = candidate if candidate.is_absolute() else output_root / candidate
        resolved = require_under_any(path, (output_root, config_root), "proof artifact path")
        if not resolved.is_file():
            raise SkillEvalPromotionError(
                f"Promotion proof artifact does not exist: {resolved}",
                code="missing_promotion_proof_artifact",
            )
        validated.append(str(resolved))
    return sorted(set(validated))


def live_run_matches_mapping(run: dict[str, Any], mapping: dict[str, Any]) -> bool:
    if run.get("status") != "passed":
        return False
    if run.get("suite") != mapping.get("live_suite") and run.get("live_suite") != mapping.get("live_suite"):
        return False
    mapped_case = mapping.get("case_id")
    case_ids = run.get("case_ids") if isinstance(run.get("case_ids"), list) else []
    if run.get("case_id") != mapped_case and mapped_case not in case_ids:
        return False
    target_roots = set(run.get("target_roots")) if isinstance(run.get("target_roots"), list) else set()
    if not DEFAULT_REQUIRED_TARGET_ROOTS.issubset(target_roots):
        return False
    if run.get("anythingllm") is True:
        return True
    return run.get("live_target") == "gateway_and_anythingllm"


def proof_satisfies_live_mapping(proof: dict[str, Any], mapping: dict[str, Any]) -> bool:
    live_runs = proof.get("live_suite_runs")
    if not isinstance(live_runs, list):
        return False
    return any(isinstance(item, dict) and live_run_matches_mapping(item, mapping) for item in live_runs)


def known_output_artifacts(config_root: Path, registry: dict[str, dict[str, Any]]) -> set[str]:
    workflows_manifest = read_json_object(config_root / "runtime" / "workflows.json", "workflow registry")
    return workflow_result_artifacts(workflows_manifest) | skill_output_artifacts(registry) | MANUAL_ARTIFACT_IDS


def load_eval_cases(config_root: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json_object(config_root / SKILL_EVALS_PATH, "skill eval catalog")
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise SkillEvalPromotionError("runtime/skill_evals.json must contain a cases list.", code="invalid_skill_evals")
    values: dict[str, dict[str, Any]] = {}
    for item in cases:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            values[item["id"]] = item
    return values


def raw_skill_map(registry_manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    skills = registry_manifest.get("skills")
    if not isinstance(skills, list):
        raise SkillEvalPromotionError("runtime/skills.json must contain a skills list.", code="invalid_skill_registry")
    values: dict[str, dict[str, Any]] = {}
    for item in skills:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            values[item["id"]] = item
    return values


def validate_promotion_candidates(
    *,
    config_root: Path,
    output_root: Path,
    skill_ids: list[str],
    proof: dict[str, Any],
    allow_repromotion: bool,
) -> dict[str, Any]:
    registry_manifest = read_json_object(config_root / SKILL_REGISTRY_PATH, "skill registry")
    registry = load_skill_registry(config_root)
    raw_skills = raw_skill_map(registry_manifest)
    eval_cases = load_eval_cases(config_root)
    known_artifacts = known_output_artifacts(config_root, registry)
    proof_artifact_paths = validate_proof_artifact_paths(proof, output_root=output_root, config_root=config_root)

    checks: list[dict[str, Any]] = []
    eval_case_ids: set[str] = set()
    for skill_id in skill_ids:
        if skill_id not in raw_skills:
            raise SkillEvalPromotionError(f"Requested skill is not registered: {skill_id}", code="skill_not_registered")
        if skill_id not in registry:
            raise SkillEvalPromotionError(f"Requested skill failed registry validation: {skill_id}", code="invalid_skill")
        raw_status = raw_skills[skill_id].get("eval_status")
        if raw_status == "deprecated":
            raise SkillEvalPromotionError(f"Refusing to promote deprecated skill: {skill_id}", code="skill_deprecated")
        if raw_status == "validated" and not allow_repromotion:
            raise SkillEvalPromotionError(
                f"Refusing to promote already validated skill without allow_repromotion=true: {skill_id}",
                code="skill_already_validated",
            )
        if raw_status not in {"draft", "validated"}:
            raise SkillEvalPromotionError(f"Skill {skill_id} must be draft or validated before promotion.", code="invalid_skill")

        skill = registry[skill_id]
        contract = skill["capability_contract"]
        case_ids = contract["eval_case_ids"]
        if not case_ids:
            raise SkillEvalPromotionError(f"Skill {skill_id} has no eval case ids.", code="missing_eval_case")
        for case_id in case_ids:
            case = eval_cases.get(case_id)
            if case is None:
                raise SkillEvalPromotionError(
                    f"Skill {skill_id} references missing eval case: {case_id}",
                    code="missing_eval_case",
                )
            unknown_artifacts = sorted(
                artifact for artifact in case.get("expected_artifacts", []) if artifact not in known_artifacts
            )
            if unknown_artifacts:
                raise SkillEvalPromotionError(
                    f"Skill {skill_id} eval case {case_id} references unknown artifact(s): "
                    f"{', '.join(unknown_artifacts)}",
                    code="unimplemented_output_artifact",
                )
            mapping = live_mapping_for_case(case)
            if mapping.get("status") == "not_mapped":
                raise SkillEvalPromotionError(
                    f"Skill {skill_id} eval case {case_id} is missing live-suite mapping.",
                    code="missing_live_mapping",
                )
            if mapping.get("status") not in {"metadata_only", "mapped"}:
                raise SkillEvalPromotionError(
                    f"Skill {skill_id} eval case {case_id} has unsupported live mapping status.",
                    code="missing_live_mapping",
                )
            if mapping.get("status") == "mapped" and not proof_satisfies_live_mapping(proof, mapping):
                raise SkillEvalPromotionError(
                    f"Skill {skill_id} eval case {case_id} requires passed gateway and AnythingLLM live proof.",
                    code="missing_live_proof",
                )
            eval_case_ids.add(case_id)
            checks.append(
                {
                    "skill_id": skill_id,
                    "eval_case_id": case_id,
                    "route_key": contract["route_key"],
                    "workflows": skill["workflows"],
                    "mutation_policy": contract["mutation_policy"],
                    "expected_artifacts": case.get("expected_artifacts", []),
                    "live_mapping": mapping,
                    "status": "passed",
                }
            )

    return {
        "registry_manifest": registry_manifest,
        "candidate_checks": checks,
        "eval_case_ids": sorted(eval_case_ids),
        "proof_artifact_paths": proof_artifact_paths,
    }


def restore_backups(*, registry_path: Path, eval_path: Path, registry_backup: Path, eval_backup: Path) -> None:
    shutil.copy2(registry_backup, registry_path)
    shutil.copy2(eval_backup, eval_path)


def promote_runtime_registry(
    *,
    config_root: Path,
    registry_manifest: dict[str, Any],
    skill_ids: list[str],
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

    updated = deepcopy(registry_manifest)
    requested = set(skill_ids)
    for item in updated["skills"]:
        if not isinstance(item, dict) or item.get("id") not in requested:
            continue
        item["eval_status"] = "validated"
        evals = item.get("evals")
        if not isinstance(evals, dict):
            evals = {}
            item["evals"] = evals
        for field in PROMOTION_EVAL_FIELDS:
            evals[field] = "passed"

    try:
        atomic_write_json(registry_path, updated)
        validate_skill_registry_manifest(read_json_object(registry_path, "skill registry"), config_root)
    except (OSError, SkillRegistryError) as exc:
        restore_backups(registry_path=registry_path, eval_path=eval_path, registry_backup=registry_backup, eval_backup=eval_backup)
        raise SkillEvalPromotionError(
            f"Skill eval promotion failed and runtime files were restored: {exc}",
            code="promotion_rollback_completed",
        ) from exc

    after_hashes = {
        "runtime/skills.json": sha256_file(registry_path),
        "runtime/skill_evals.json": sha256_file(eval_path),
    }
    return {
        "backup_paths": {
            "runtime/skills.json": str(registry_backup),
            "runtime/skill_evals.json": str(eval_backup),
        },
        "before_hashes": before_hashes,
        "after_hashes": after_hashes,
    }


def rollback_instructions(promotion_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "skill_eval_promotion_rollback_instructions",
        "schema_version": SCHEMA_VERSION,
        "restore_backups": promotion_result["backup_paths"],
        "note": "Restore runtime/skills.json from the recorded backup if this promotion must be reverted. "
        "runtime/skill_evals.json was backed up for proof but must not have changed during promotion.",
    }


def invoke_skill_eval_promotion(request: SkillEvalPromotionRequest) -> InvocationResult:
    validate_request(request)
    output_root = Path(request.output_root).resolve()
    config_root = Path(request.config_root).resolve()
    run_id = f"skill-eval-promotion-{artifact_timestamp()}"
    run_dir = output_root / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, str] = {}
    approval = validate_approval(request.approval)
    skill_ids, registration_path = normalize_skill_ids(request)
    request_artifact = {
        "kind": "skill_eval_promotion_request",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "skill_ids": skill_ids,
        "registration_run_id": request.registration_run_id,
        "registration_path": registration_path,
        "approval": approval,
        "allow_repromotion": request.allow_repromotion,
        "metadata": request.metadata,
        "created_at": utc_now(),
    }
    write_json(run_dir / "request.json", request_artifact)
    artifacts["request"] = str(run_dir / "request.json")
    if registration_path:
        artifacts["skill_batch_registration"] = registration_path

    proof = request.proof if isinstance(request.proof, dict) else {}
    validation = validate_promotion_candidates(
        config_root=config_root,
        output_root=output_root,
        skill_ids=skill_ids,
        proof=proof,
        allow_repromotion=request.allow_repromotion,
    )
    eval_case_ids = validation["eval_case_ids"]
    proof_plan = {
        "kind": "skill_eval_promotion_proof_plan",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "skill_ids": skill_ids,
        "eval_case_ids": eval_case_ids,
        "candidate_checks": validation["candidate_checks"],
        "proof_artifact_paths": validation["proof_artifact_paths"],
        "target_repository_changed": False,
        "status": "passed",
        "created_at": utc_now(),
    }
    write_json(run_dir / "promotion-proof-plan.json", proof_plan)
    artifacts["promotion_proof_plan"] = str(run_dir / "promotion-proof-plan.json")

    pre_eval_report = run_skill_eval_catalog(
        config_root,
        output_path=run_dir / "skill-eval-report-before-promotion.json",
        case_ids=eval_case_ids,
    )
    artifacts["skill_eval_report_before"] = str(run_dir / "skill-eval-report-before-promotion.json")
    if pre_eval_report["status"] != "passed":
        raise SkillEvalPromotionError(
            "Skill eval catalog failed before promotion.",
            code="promotion_eval_failed",
        )
    pre_scale_report = build_skill_scale_report(
        config_root,
        output_path=run_dir / "scale-report-before-promotion.json",
    )
    artifacts["scale_report_before"] = str(run_dir / "scale-report-before-promotion.json")
    if pre_scale_report["status"] != "passed":
        raise SkillEvalPromotionError(
            "Skill scale report failed before promotion.",
            code="promotion_scale_failed",
        )

    promotion_result = promote_runtime_registry(
        config_root=config_root,
        registry_manifest=validation["registry_manifest"],
        skill_ids=skill_ids,
        run_dir=run_dir,
    )

    post_eval_report = run_skill_eval_catalog(
        config_root,
        output_path=run_dir / "skill-eval-report-after-promotion.json",
        case_ids=eval_case_ids,
    )
    artifacts["skill_eval_report_after"] = str(run_dir / "skill-eval-report-after-promotion.json")
    post_scale_report = build_skill_scale_report(
        config_root,
        output_path=run_dir / "scale-report-after-promotion.json",
    )
    artifacts["scale_report_after"] = str(run_dir / "scale-report-after-promotion.json")
    if post_eval_report["status"] != "passed" or post_scale_report["status"] != "passed":
        restore_backups(
            registry_path=config_root / SKILL_REGISTRY_PATH,
            eval_path=config_root / SKILL_EVALS_PATH,
            registry_backup=Path(promotion_result["backup_paths"]["runtime/skills.json"]),
            eval_backup=Path(promotion_result["backup_paths"]["runtime/skill_evals.json"]),
        )
        raise SkillEvalPromotionError(
            "Post-promotion validation failed and runtime files were restored.",
            code="promotion_rollback_completed",
        )

    rollback = rollback_instructions(promotion_result)
    write_json(run_dir / "rollback-instructions.json", rollback)
    artifacts["rollback_instructions"] = str(run_dir / "rollback-instructions.json")

    hash_proof = {
        "before": promotion_result["before_hashes"],
        "after": promotion_result["after_hashes"],
        "changed": sorted(
            key
            for key, after_hash in promotion_result["after_hashes"].items()
            if promotion_result["before_hashes"].get(key) != after_hash
        ),
    }
    changed_runtime_files = [item for item in hash_proof["changed"] if item.startswith("runtime/")]
    if "runtime/skill_evals.json" in changed_runtime_files:
        restore_backups(
            registry_path=config_root / SKILL_REGISTRY_PATH,
            eval_path=config_root / SKILL_EVALS_PATH,
            registry_backup=Path(promotion_result["backup_paths"]["runtime/skills.json"]),
            eval_backup=Path(promotion_result["backup_paths"]["runtime/skill_evals.json"]),
        )
        raise SkillEvalPromotionError(
            "Promotion attempted to mutate runtime/skill_evals.json; runtime files were restored.",
            code="skill_evals_mutation_forbidden",
        )

    summary = {
        "promotion_status": "promoted",
        "skill_count": len(skill_ids),
        "eval_case_count": len(eval_case_ids),
        "promoted_skill_ids": skill_ids,
        "eval_case_ids": eval_case_ids,
        "metadata_eval_status": post_eval_report["status"],
        "scale_report_status": post_scale_report["status"],
        "runtime_registry_changed": "runtime/skills.json" in changed_runtime_files,
        "changed_runtime_files": changed_runtime_files,
        "target_repository_changed": False,
        "next_action": "use_promoted_skill_or_run_lifecycle_audit",
    }
    promotion = {
        "kind": "skill_eval_promotion",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": "promoted",
        "summary": summary,
        "approval": approval,
        "registration_path": registration_path,
        "promotion_proof_plan": proof_plan,
        "hash_proof": hash_proof,
        "rollback_instructions": rollback,
        "created_at": utc_now(),
    }
    write_json(run_dir / "skill-eval-promotion.json", promotion)
    artifacts["skill_eval_promotion"] = str(run_dir / "skill-eval-promotion.json")

    run_state = {
        "kind": "skill_eval_promotion_run_state",
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
        "kind": "skill_eval_promotion_report",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "summary": summary,
        "promotion": promotion,
        "warnings": [],
        "artifacts": artifacts,
    }
    return InvocationResult(
        workflow=WORKFLOW_ID,
        status=WorkflowStatus.COMPLETED,
        artifact_paths=artifacts,
        summary_text=f"{WORKFLOW_ID} completed with promotion_status=promoted",
        failures=[],
        resume_key={"schema_version": SCHEMA_VERSION, "run_state": str(run_dir / "run-state.json")},
        report=report,
        run_id=run_id,
    )
