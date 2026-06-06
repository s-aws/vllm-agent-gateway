"""Approval-gated skill update workflow."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from copy import deepcopy
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus
from vllm_agent_gateway.skills.evals import SKILL_EVALS_PATH, run_skill_eval_catalog
from vllm_agent_gateway.skills.registry import (
    SCHEMA_VERSION,
    SKILL_REGISTRY_PATH,
    SkillRegistryError,
    load_skill_registry,
    parse_skill_frontmatter,
    read_json_object,
    validate_eval_case_item,
    validate_skill_registry_manifest,
)
from vllm_agent_gateway.skills.scale import build_skill_scale_report
from vllm_agent_gateway.skills.selector_scale import build_skill_selector_scale_report


WORKFLOW_ID = "skill.update"
DEFAULT_OUTPUT_DIR = "skill-updates"
CHANGE_TYPES = {"metadata_only", "skill_body_only", "eval_case_only", "combined"}
VERSION_BUMPS = {"patch", "minor", "major"}
DISALLOWED_METADATA_FIELDS = {"id", "path", "version", "eval_status", "deprecation"}
ROUTE_KEY_PATH = ("capability_contract", "route_key")


class SkillUpdateError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "skill_update_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class SkillUpdateRequest:
    config_root: Path | str = "."
    output_root: Path | str = ".agentic_controller"
    workflow: str = WORKFLOW_ID
    schema_version: int = SCHEMA_VERSION
    skill_id: str | None = None
    change_type: str | None = None
    version_bump: str | None = None
    metadata_updates: dict[str, Any] = field(default_factory=dict)
    skill_body_text: str | None = None
    eval_case_updates: list[dict[str, Any]] = field(default_factory=list)
    deprecation_plan_ref: str | None = None
    approval: dict[str, Any] = field(default_factory=dict)
    proof: dict[str, Any] = field(default_factory=dict)
    role_id: str = "architect/default"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        config_root: Path,
        output_root: Path,
    ) -> "SkillUpdateRequest":
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


def atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{artifact_timestamp()}.tmp")
    temp_path.write_text(value, encoding="utf-8")
    temp_path.replace(path)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def string_field(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SkillUpdateError(f"{label} must be a non-empty string.")
    return value.strip()


def string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise SkillUpdateError(f"{label} must be a non-empty list of strings.")
    return list(value)


def parse_semver(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise SkillUpdateError(f"Invalid semantic version: {value}", code="invalid_skill_version")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def bumped_version(current: str, bump: str) -> str:
    major, minor, patch = parse_semver(current)
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "major":
        return f"{major + 1}.0.0"
    raise SkillUpdateError(f"Unsupported version_bump: {bump}", code="unsupported_version_bump")


def validate_approval(approval: Any, *, categories: set[str]) -> dict[str, Any]:
    if not isinstance(approval, dict):
        raise SkillUpdateError(
            "approval must be a JSON object.",
            code="missing_skill_update_approval",
            status=HTTPStatus.BAD_REQUEST,
        )
    if approval.get("status") != "approved_for_skill_update":
        raise SkillUpdateError(
            "skill.update requires approval.status=approved_for_skill_update.",
            code="missing_skill_update_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    scope = approval.get("scope")
    scopes = set(scope) if isinstance(scope, list) else {scope} if isinstance(scope, str) else set()
    if "skill_update" not in scopes:
        raise SkillUpdateError(
            "skill.update requires approval.scope=skill_update.",
            code="invalid_skill_update_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    if approval.get("runtime_registry_update") is not True:
        raise SkillUpdateError(
            "skill.update requires approval.runtime_registry_update=true.",
            code="invalid_skill_update_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    if "body" in categories and approval.get("skill_body_update") is not True:
        raise SkillUpdateError(
            "skill.update requires approval.skill_body_update=true for skill body changes.",
            code="invalid_skill_update_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    if "eval_case" in categories and approval.get("eval_case_update") is not True:
        raise SkillUpdateError(
            "skill.update requires approval.eval_case_update=true for eval case changes.",
            code="invalid_skill_update_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    if approval.get("skill_metadata_update") is not True:
        raise SkillUpdateError(
            "skill.update requires approval.skill_metadata_update=true because every update bumps skill metadata version.",
            code="invalid_skill_update_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    approval_refs = string_list(approval.get("approval_refs"), "approval.approval_refs")
    return {
        "status": approval["status"],
        "scope": sorted(scopes),
        "runtime_registry_update": True,
        "skill_metadata_update": approval.get("skill_metadata_update") is True,
        "skill_body_update": approval.get("skill_body_update") is True,
        "eval_case_update": approval.get("eval_case_update") is True,
        "approval_refs": approval_refs,
    }


def update_categories(request: SkillUpdateRequest) -> set[str]:
    categories: set[str] = set()
    if request.metadata_updates:
        categories.add("metadata")
    if request.skill_body_text is not None:
        categories.add("body")
    if request.eval_case_updates:
        categories.add("eval_case")
    return categories


def validate_change_type(change_type: str, categories: set[str]) -> None:
    expected: dict[str, set[str]] = {
        "metadata_only": {"metadata"},
        "skill_body_only": {"body"},
        "eval_case_only": {"eval_case"},
    }
    if change_type in expected and categories != expected[change_type]:
        raise SkillUpdateError(
            f"change_type={change_type} does not match supplied update categories: {sorted(categories)}",
            code="change_type_mismatch",
        )
    if change_type == "combined" and len(categories) < 2:
        raise SkillUpdateError(
            "change_type=combined requires at least two update categories.",
            code="change_type_mismatch",
        )


def validate_request(request: SkillUpdateRequest) -> set[str]:
    if request.workflow != WORKFLOW_ID:
        raise SkillUpdateError("workflow must be skill.update.", code="unsupported_workflow")
    if request.schema_version != SCHEMA_VERSION:
        raise SkillUpdateError("schema_version must be 1.", code="unsupported_schema_version")
    string_field(request.skill_id, "skill_id")
    change_type = string_field(request.change_type, "change_type")
    if change_type not in CHANGE_TYPES:
        raise SkillUpdateError(f"Unsupported change_type: {change_type}", code="unsupported_change_type")
    version_bump = string_field(request.version_bump, "version_bump")
    if version_bump not in VERSION_BUMPS:
        raise SkillUpdateError(f"Unsupported version_bump: {version_bump}", code="unsupported_version_bump")
    if request.metadata_updates is not None and not isinstance(request.metadata_updates, dict):
        raise SkillUpdateError("metadata_updates must be a JSON object.", code="invalid_metadata_updates")
    if request.skill_body_text is not None and not isinstance(request.skill_body_text, str):
        raise SkillUpdateError("skill_body_text must be a string.", code="invalid_skill_body_text")
    if request.eval_case_updates is not None and not isinstance(request.eval_case_updates, list):
        raise SkillUpdateError("eval_case_updates must be a list.", code="invalid_eval_case_updates")
    for item in request.eval_case_updates:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("updates"), dict):
            raise SkillUpdateError(
                "Each eval_case_updates entry must include id and updates object.",
                code="invalid_eval_case_updates",
            )
    categories = update_categories(request)
    if not categories:
        raise SkillUpdateError("skill.update requires at least one update category.", code="missing_update")
    validate_change_type(change_type, categories)
    validate_approval(request.approval, categories=categories)
    if request.proof is not None and not isinstance(request.proof, dict):
        raise SkillUpdateError("proof must be a JSON object.", code="invalid_skill_update_proof")
    if request.metadata is not None and not isinstance(request.metadata, dict):
        raise SkillUpdateError("metadata must be a JSON object.", code="invalid_metadata")
    return categories


def deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    value = deepcopy(base)
    for key, update_value in updates.items():
        if isinstance(update_value, dict) and isinstance(value.get(key), dict):
            value[key] = deep_merge(value[key], update_value)
        else:
            value[key] = deepcopy(update_value)
    return value


def value_at_path(value: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def metadata_updates_change_route_key(skill: dict[str, Any], updates: dict[str, Any]) -> bool:
    if "capability_contract" not in updates:
        return False
    proposed = deep_merge(skill, updates)
    return value_at_path(skill, ROUTE_KEY_PATH) != value_at_path(proposed, ROUTE_KEY_PATH)


def validate_metadata_updates(
    skill: dict[str, Any],
    updates: dict[str, Any],
    *,
    deprecation_plan_ref: str | None,
) -> None:
    disallowed = sorted(set(updates) & DISALLOWED_METADATA_FIELDS)
    if disallowed:
        raise SkillUpdateError(
            f"metadata_updates contains managed field(s): {', '.join(disallowed)}",
            code="managed_metadata_field_update",
        )
    if metadata_updates_change_route_key(skill, updates) and not deprecation_plan_ref:
        raise SkillUpdateError(
            "Route-key changes require deprecation_plan_ref.",
            code="route_key_change_requires_deprecation_plan",
        )


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def validate_deprecation_plan_ref(path_value: str | None, *, output_root: Path, config_root: Path) -> str | None:
    if not path_value:
        return None
    raw = Path(path_value)
    candidate = raw if raw.is_absolute() else output_root / raw
    resolved = candidate.resolve()
    if not (is_under(resolved, output_root) or is_under(resolved, config_root)):
        raise SkillUpdateError(
            f"deprecation_plan_ref is outside allowed roots: {resolved}",
            code="deprecation_plan_ref_not_allowed",
            status=HTTPStatus.FORBIDDEN,
        )
    if not resolved.is_file():
        raise SkillUpdateError(
            f"deprecation_plan_ref does not exist: {resolved}",
            code="missing_deprecation_plan_ref",
        )
    return str(resolved)


def load_eval_manifest(config_root: Path) -> dict[str, Any]:
    manifest = read_json_object(config_root / SKILL_EVALS_PATH, "skill eval catalog")
    if not isinstance(manifest.get("cases"), list):
        raise SkillUpdateError("runtime/skill_evals.json must contain a cases list.", code="invalid_skill_evals")
    return manifest


def raw_skill_map(registry_manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    skills = registry_manifest.get("skills")
    if not isinstance(skills, list):
        raise SkillUpdateError("runtime/skills.json must contain a skills list.", code="invalid_skill_registry")
    values: dict[str, dict[str, Any]] = {}
    for item in skills:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            values[item["id"]] = item
    return values


def eval_cases_by_id(eval_manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["id"]: item
        for item in eval_manifest.get("cases", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def expected_version_bump(change_type: str, route_key_change: bool) -> str:
    if route_key_change:
        return "major"
    if change_type == "combined":
        return "minor"
    return "patch"


def validate_update_candidate(
    *,
    config_root: Path,
    output_root: Path,
    request: SkillUpdateRequest,
) -> dict[str, Any]:
    assert request.skill_id is not None
    assert request.change_type is not None
    assert request.version_bump is not None
    registry_manifest = read_json_object(config_root / SKILL_REGISTRY_PATH, "skill registry")
    registry = load_skill_registry(config_root)
    raw_skills = raw_skill_map(registry_manifest)
    eval_manifest = load_eval_manifest(config_root)
    if request.skill_id not in raw_skills:
        raise SkillUpdateError(f"Requested skill is not registered: {request.skill_id}", code="skill_not_registered")
    if request.skill_id not in registry:
        raise SkillUpdateError(f"Requested skill failed registry validation: {request.skill_id}", code="invalid_skill")
    raw_skill = raw_skills[request.skill_id]
    if raw_skill.get("eval_status") != "validated":
        raise SkillUpdateError(
            f"skill.update currently supports validated skills only: {request.skill_id}",
            code="skill_not_validated",
        )
    validate_metadata_updates(
        raw_skill,
        request.metadata_updates,
        deprecation_plan_ref=request.deprecation_plan_ref,
    )
    route_key_change = metadata_updates_change_route_key(raw_skill, request.metadata_updates)
    deprecation_plan_ref = validate_deprecation_plan_ref(
        request.deprecation_plan_ref,
        output_root=output_root,
        config_root=config_root,
    )
    required_bump = expected_version_bump(request.change_type, route_key_change)
    if request.version_bump != required_bump:
        raise SkillUpdateError(
            f"change_type={request.change_type} requires version_bump={required_bump}.",
            code="invalid_version_bump_for_change_type",
        )
    current_version = string_field(raw_skill.get("version"), "skill.version")
    new_version = bumped_version(current_version, request.version_bump)
    eval_case_ids = {case_id for case_id in raw_skill["capability_contract"]["eval_case_ids"]}
    requested_eval_case_ids = [item["id"] for item in request.eval_case_updates]
    unknown_eval_cases = sorted(set(requested_eval_case_ids) - set(eval_cases_by_id(eval_manifest)))
    if unknown_eval_cases:
        raise SkillUpdateError(
            f"eval_case_updates references unknown eval case(s): {', '.join(unknown_eval_cases)}",
            code="missing_eval_case",
        )
    unrelated_eval_cases = sorted(set(requested_eval_case_ids) - eval_case_ids)
    if unrelated_eval_cases:
        raise SkillUpdateError(
            f"eval_case_updates must target eval cases owned by {request.skill_id}: {', '.join(unrelated_eval_cases)}",
            code="eval_case_not_owned_by_skill",
        )
    if request.skill_body_text is not None:
        skill_path = config_root / raw_skill["path"]
        if not skill_path.is_file():
            raise SkillUpdateError(f"Skill body path does not exist: {skill_path}", code="missing_skill_body")
        temp_body = output_root / DEFAULT_OUTPUT_DIR / f"frontmatter-check-{artifact_timestamp()}.md"
        atomic_write_text(temp_body, request.skill_body_text)
        try:
            frontmatter = parse_skill_frontmatter(temp_body)
        finally:
            temp_body.unlink(missing_ok=True)
        if frontmatter["name"] != request.skill_id:
            raise SkillUpdateError(
                "skill_body_text frontmatter name must match skill_id.",
                code="skill_body_frontmatter_mismatch",
            )
    return {
        "registry_manifest": registry_manifest,
        "eval_manifest": eval_manifest,
        "current_version": current_version,
        "new_version": new_version,
        "route_key_change": route_key_change,
        "deprecation_plan_ref": deprecation_plan_ref,
        "updated_eval_case_ids": sorted(set(requested_eval_case_ids)),
    }


def restore_backups(backups: dict[str, str], config_root: Path) -> None:
    for relative_path, backup_path in backups.items():
        shutil.copy2(Path(backup_path), config_root / relative_path)


def changed_hash_keys(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(key for key, after_hash in after.items() if before.get(key) != after_hash)


def count_changed_skill_entries(before: dict[str, Any], after: dict[str, Any]) -> int:
    before_items = {item.get("id"): item for item in before.get("skills", []) if isinstance(item, dict)}
    after_items = {item.get("id"): item for item in after.get("skills", []) if isinstance(item, dict)}
    return sum(1 for skill_id, item in after_items.items() if before_items.get(skill_id) != item)


def count_changed_eval_cases(before: dict[str, Any], after: dict[str, Any]) -> tuple[int, list[str]]:
    before_items = {item.get("id"): item for item in before.get("cases", []) if isinstance(item, dict)}
    after_items = {item.get("id"): item for item in after.get("cases", []) if isinstance(item, dict)}
    changed = sorted(case_id for case_id, item in after_items.items() if before_items.get(case_id) != item)
    return len(changed), changed


def apply_eval_case_updates(eval_manifest: dict[str, Any], updates: list[dict[str, Any]]) -> dict[str, Any]:
    updated = deepcopy(eval_manifest)
    update_map = {item["id"]: item["updates"] for item in updates}
    for case in updated["cases"]:
        case_id = case.get("id")
        if case_id not in update_map:
            continue
        case_updates = update_map[case_id]
        if "id" in case_updates:
            raise SkillUpdateError("eval case id cannot be changed by skill.update.", code="managed_eval_case_field_update")
        merged = deep_merge(case, case_updates)
        case.clear()
        case.update(merged)
    return updated


def apply_skill_update(
    *,
    config_root: Path,
    request: SkillUpdateRequest,
    validation: dict[str, Any],
    run_dir: Path,
) -> dict[str, Any]:
    assert request.skill_id is not None
    registry_path = config_root / SKILL_REGISTRY_PATH
    eval_path = config_root / SKILL_EVALS_PATH
    raw_skill = raw_skill_map(validation["registry_manifest"])[request.skill_id]
    skill_body_relative_path = raw_skill["path"]
    skill_body_path = config_root / skill_body_relative_path
    backup_dir = run_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    backups: dict[str, str] = {
        "runtime/skills.json": str(backup_dir / "skills.before.json"),
        "runtime/skill_evals.json": str(backup_dir / "skill-evals.before.json"),
    }
    shutil.copy2(registry_path, backups["runtime/skills.json"])
    shutil.copy2(eval_path, backups["runtime/skill_evals.json"])
    if request.skill_body_text is not None:
        backups[skill_body_relative_path] = str(backup_dir / "SKILL.before.md")
        shutil.copy2(skill_body_path, backups[skill_body_relative_path])

    before_hashes = {
        "runtime/skills.json": sha256_file(registry_path),
        "runtime/skill_evals.json": sha256_file(eval_path),
    }
    if request.skill_body_text is not None:
        before_hashes[skill_body_relative_path] = sha256_file(skill_body_path)

    updated_registry = deepcopy(validation["registry_manifest"])
    for item in updated_registry["skills"]:
        if not isinstance(item, dict) or item.get("id") != request.skill_id:
            continue
        merged = deep_merge(item, request.metadata_updates)
        merged["version"] = validation["new_version"]
        item.clear()
        item.update(merged)

    updated_eval_manifest = apply_eval_case_updates(validation["eval_manifest"], request.eval_case_updates)

    try:
        atomic_write_json(registry_path, updated_registry)
        if request.eval_case_updates:
            atomic_write_json(eval_path, updated_eval_manifest)
        if request.skill_body_text is not None:
            atomic_write_text(skill_body_path, request.skill_body_text)
        validate_skill_registry_manifest(read_json_object(registry_path, "skill registry"), config_root)
        for case in updated_eval_manifest["cases"]:
            if isinstance(case, dict):
                validate_eval_case_item(case)
    except (OSError, SkillRegistryError, SkillUpdateError) as exc:
        restore_backups(backups, config_root)
        raise SkillUpdateError(
            f"Skill update failed and changed files were restored: {exc}",
            code="skill_update_rollback_completed",
        ) from exc

    after_hashes = {
        "runtime/skills.json": sha256_file(registry_path),
        "runtime/skill_evals.json": sha256_file(eval_path),
    }
    if request.skill_body_text is not None:
        after_hashes[skill_body_relative_path] = sha256_file(skill_body_path)

    changed_skill_entry_count = count_changed_skill_entries(validation["registry_manifest"], updated_registry)
    changed_eval_case_count, changed_eval_case_ids = count_changed_eval_cases(validation["eval_manifest"], updated_eval_manifest)
    return {
        "backup_paths": backups,
        "before_hashes": before_hashes,
        "after_hashes": after_hashes,
        "changed_files": changed_hash_keys(before_hashes, after_hashes),
        "changed_skill_entry_count": changed_skill_entry_count,
        "changed_eval_case_count": changed_eval_case_count,
        "changed_eval_case_ids": changed_eval_case_ids,
    }


def rollback_instructions(update_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "skill_update_rollback_instructions",
        "schema_version": SCHEMA_VERSION,
        "restore_backups": update_result["backup_paths"],
        "note": "Restore each changed file from its recorded backup if this skill update must be reverted.",
    }


def invoke_skill_update(request: SkillUpdateRequest) -> InvocationResult:
    categories = validate_request(request)
    output_root = Path(request.output_root).resolve()
    config_root = Path(request.config_root).resolve()
    run_id = f"skill-update-{artifact_timestamp()}"
    run_dir = output_root / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    assert request.skill_id is not None
    assert request.change_type is not None
    assert request.version_bump is not None

    artifacts: dict[str, str] = {}
    approval = validate_approval(request.approval, categories=categories)
    validation = validate_update_candidate(config_root=config_root, output_root=output_root, request=request)

    request_artifact = {
        "kind": "skill_update_request",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "skill_id": request.skill_id,
        "change_type": request.change_type,
        "version_bump": request.version_bump,
        "current_version": validation["current_version"],
        "new_version": validation["new_version"],
        "categories": sorted(categories),
        "approval": approval,
        "metadata": request.metadata,
        "created_at": utc_now(),
    }
    write_json(run_dir / "request.json", request_artifact)
    artifacts["request"] = str(run_dir / "request.json")

    update_plan = {
        "kind": "skill_update_plan",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "skill_id": request.skill_id,
        "change_type": request.change_type,
        "categories": sorted(categories),
        "current_version": validation["current_version"],
        "new_version": validation["new_version"],
        "route_key_change": validation["route_key_change"],
        "deprecation_plan_ref": validation["deprecation_plan_ref"],
        "updated_eval_case_ids": validation["updated_eval_case_ids"],
        "status": "passed",
        "created_at": utc_now(),
    }
    write_json(run_dir / "skill-update-plan.json", update_plan)
    artifacts["skill_update_plan"] = str(run_dir / "skill-update-plan.json")

    pre_eval_report = run_skill_eval_catalog(config_root, output_path=run_dir / "skill-eval-report-before-update.json")
    artifacts["skill_eval_report_before"] = str(run_dir / "skill-eval-report-before-update.json")
    pre_scale_report = build_skill_scale_report(config_root, output_path=run_dir / "scale-report-before-update.json")
    artifacts["scale_report_before"] = str(run_dir / "scale-report-before-update.json")
    if pre_eval_report["status"] != "passed":
        raise SkillUpdateError("Skill eval catalog failed before update.", code="skill_update_eval_failed")
    if pre_scale_report["status"] != "passed":
        raise SkillUpdateError("Skill scale report failed before update.", code="skill_update_scale_failed")

    update_result = apply_skill_update(config_root=config_root, request=request, validation=validation, run_dir=run_dir)
    post_eval_report = run_skill_eval_catalog(config_root, output_path=run_dir / "skill-eval-report-after-update.json")
    artifacts["skill_eval_report_after"] = str(run_dir / "skill-eval-report-after-update.json")
    post_scale_report = build_skill_scale_report(config_root, output_path=run_dir / "scale-report-after-update.json")
    artifacts["scale_report_after"] = str(run_dir / "scale-report-after-update.json")
    selector_scale_report = build_skill_selector_scale_report(
        config_root,
        output_path=run_dir / "selector-scale-report-after-update.json",
    )
    artifacts["selector_scale_report_after"] = str(run_dir / "selector-scale-report-after-update.json")
    if (
        post_eval_report["status"] != "passed"
        or post_scale_report["status"] != "passed"
        or selector_scale_report["status"] != "passed"
    ):
        restore_backups(update_result["backup_paths"], config_root)
        raise SkillUpdateError(
            "Post-update validation failed and changed files were restored.",
            code="skill_update_rollback_completed",
        )

    expected_changed_files = {"runtime/skills.json"}
    if "eval_case" in categories:
        expected_changed_files.add("runtime/skill_evals.json")
    if "body" in categories:
        raw_skill = raw_skill_map(validation["registry_manifest"])[request.skill_id]
        expected_changed_files.add(raw_skill["path"])
    unexpected = sorted(set(update_result["changed_files"]) - expected_changed_files)
    if unexpected:
        restore_backups(update_result["backup_paths"], config_root)
        raise SkillUpdateError(
            "skill.update changed unexpected file(s): " + ", ".join(unexpected),
            code="unexpected_skill_update_mutation",
        )
    if update_result["changed_skill_entry_count"] != 1:
        restore_backups(update_result["backup_paths"], config_root)
        raise SkillUpdateError(
            f"skill.update expected one changed skill entry, found {update_result['changed_skill_entry_count']}.",
            code="unexpected_skill_update_mutation",
        )
    if update_result["changed_eval_case_count"] != len(validation["updated_eval_case_ids"]):
        restore_backups(update_result["backup_paths"], config_root)
        raise SkillUpdateError(
            "skill.update changed an unexpected number of eval cases.",
            code="unexpected_skill_update_mutation",
        )

    rollback = rollback_instructions(update_result)
    write_json(run_dir / "rollback-instructions.json", rollback)
    artifacts["rollback_instructions"] = str(run_dir / "rollback-instructions.json")
    hash_proof = {
        "before": update_result["before_hashes"],
        "after": update_result["after_hashes"],
        "changed": update_result["changed_files"],
    }
    summary = {
        "update_status": "updated",
        "skill_id": request.skill_id,
        "change_type": request.change_type,
        "categories": sorted(categories),
        "current_version": validation["current_version"],
        "new_version": validation["new_version"],
        "changed_files": update_result["changed_files"],
        "changed_skill_entry_count": update_result["changed_skill_entry_count"],
        "changed_eval_case_count": update_result["changed_eval_case_count"],
        "changed_eval_case_ids": update_result["changed_eval_case_ids"],
        "metadata_eval_status": post_eval_report["status"],
        "scale_report_status": post_scale_report["status"],
        "selector_scale_report_status": selector_scale_report["status"],
        "target_repository_changed": False,
        "next_action": "run_lifecycle_audit_or_restore_backup_if_needed",
    }
    update = {
        "kind": "skill_update",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": "updated",
        "summary": summary,
        "approval": approval,
        "update_plan": update_plan,
        "hash_proof": hash_proof,
        "rollback_instructions": rollback,
        "created_at": utc_now(),
    }
    write_json(run_dir / "skill-update.json", update)
    artifacts["skill_update"] = str(run_dir / "skill-update.json")

    run_state = {
        "kind": "skill_update_run_state",
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
        "kind": "skill_update_report",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "summary": summary,
        "update": update,
        "warnings": [],
        "artifacts": artifacts,
    }
    return InvocationResult(
        workflow=WORKFLOW_ID,
        status=WorkflowStatus.COMPLETED,
        artifact_paths=artifacts,
        summary_text=f"{WORKFLOW_ID} completed with update_status=updated",
        failures=[],
        resume_key={"schema_version": SCHEMA_VERSION, "run_state": str(run_dir / "run-state.json")},
        report=report,
        run_id=run_id,
    )
