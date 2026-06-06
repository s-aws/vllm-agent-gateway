"""Skill pack validation and namespace governance."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.skills.batches import validate_skill_batch_manifest
from vllm_agent_gateway.skills.registry import (
    ROUTE_KEY_NAMESPACES,
    SCHEMA_VERSION,
    SEMVER_RE,
    SKILL_REGISTRY_PATH,
    SkillRegistryError,
    read_json_object,
    route_key_namespace,
    validate_doc_refs,
    validate_skill_registry_manifest,
)


DEFAULT_REPORT_DIR = Path("runtime-state") / "skill-packs"
REQUIRED_PACK_FIELDS = {
    "schema_version",
    "kind",
    "id",
    "version",
    "owner",
    "description",
    "namespaces",
    "compatibility",
    "docs",
    "skills",
    "eval_cases",
}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path, pack_id: str) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"{pack_id}-{utc_timestamp()}.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_pack_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SkillRegistryError(f"Missing skill pack manifest: {path}", code="missing_skill_pack") from exc
    except json.JSONDecodeError as exc:
        raise SkillRegistryError(f"Invalid skill pack manifest: {exc}") from exc
    if not isinstance(value, dict):
        raise SkillRegistryError("Skill pack manifest must contain a JSON object.")
    return value


def pack_id_from_manifest(manifest: dict[str, Any]) -> str:
    pack_id = manifest.get("id")
    if isinstance(pack_id, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]*", pack_id):
        return pack_id
    return "skill-pack"


def validate_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise SkillRegistryError(f"{label} must be a non-empty list of strings.")
    return list(value)


def validate_pack_header(manifest: dict[str, Any], config_root: Path) -> dict[str, Any]:
    missing = sorted(REQUIRED_PACK_FIELDS - set(manifest))
    if missing:
        raise SkillRegistryError(f"Skill pack manifest is missing field(s): {', '.join(missing)}")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise SkillRegistryError("Skill pack manifest schema_version must be 1.")
    if manifest.get("kind") != "skill_pack_manifest":
        raise SkillRegistryError("Skill pack manifest kind must be skill_pack_manifest.")
    pack_id = manifest["id"]
    if not isinstance(pack_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", pack_id):
        raise SkillRegistryError("Skill pack manifest id is invalid.")
    version = manifest["version"]
    if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
        raise SkillRegistryError("Skill pack manifest version must be semantic version x.y.z.")
    owner = manifest["owner"]
    if not isinstance(owner, str) or not owner.strip():
        raise SkillRegistryError("Skill pack manifest owner must be a non-empty string.")
    description = manifest["description"]
    if not isinstance(description, str) or len(description.strip()) < 20:
        raise SkillRegistryError("Skill pack manifest description must be a descriptive string.")
    namespaces = validate_string_list(manifest["namespaces"], "skill_pack.namespaces")
    duplicate_namespaces = sorted({item for item in namespaces if namespaces.count(item) > 1})
    if duplicate_namespaces:
        raise SkillRegistryError(f"Skill pack manifest has duplicate namespace(s): {', '.join(duplicate_namespaces)}")
    unsupported_namespaces = sorted(set(namespaces) - ROUTE_KEY_NAMESPACES)
    if unsupported_namespaces:
        raise SkillRegistryError(
            f"Skill pack manifest has unsupported namespace(s): {', '.join(unsupported_namespaces)}"
        )
    compatibility = validate_string_list(manifest["compatibility"], "skill_pack.compatibility")
    docs = validate_doc_refs(config_root, manifest["docs"])
    skills = manifest["skills"]
    if not isinstance(skills, list) or not skills:
        raise SkillRegistryError("Skill pack manifest skills must be a non-empty list.")
    eval_cases = manifest["eval_cases"]
    if not isinstance(eval_cases, list) or not eval_cases:
        raise SkillRegistryError("Skill pack manifest eval_cases must be a non-empty list.")
    return {
        "id": pack_id,
        "version": version,
        "owner": owner,
        "description": description,
        "namespaces": namespaces,
        "compatibility": compatibility,
        "docs": docs,
        "skills": skills,
        "eval_cases": eval_cases,
    }


def skill_pack_to_batch_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "skill_batch_manifest",
        "id": manifest["id"],
        "description": manifest["description"],
        "doc_refs": manifest["docs"],
        "skills": manifest["skills"],
        "eval_cases": manifest["eval_cases"],
    }


def skill_route_namespace(raw_skill: dict[str, Any]) -> str | None:
    contract = raw_skill.get("capability_contract")
    if not isinstance(contract, dict):
        return None
    route_key = contract.get("route_key")
    if not isinstance(route_key, str) or not route_key:
        return None
    return route_key_namespace(route_key)


def validate_pack_skill_governance(
    *,
    pack_id: str,
    owner: str,
    namespaces: list[str],
    skills: list[Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    declared_namespaces = set(namespaces)
    pack_skill_ids = {
        raw_skill.get("id")
        for raw_skill in skills
        if isinstance(raw_skill, dict) and isinstance(raw_skill.get("id"), str)
    }
    route_namespace_counts: dict[str, int] = {}
    for raw_skill in skills:
        if not isinstance(raw_skill, dict):
            raise SkillRegistryError("Skill pack skills must contain objects.")
        skill_id = raw_skill.get("id")
        if raw_skill.get("owner") != owner:
            raise SkillRegistryError(f"Skill pack skill {skill_id or '<unknown>'} owner must match pack owner.")
        namespace = skill_route_namespace(raw_skill)
        if namespace is None:
            continue
        route_namespace_counts[namespace] = route_namespace_counts.get(namespace, 0) + 1
        if namespace not in declared_namespaces:
            raise SkillRegistryError(
                f"Skill pack skill {skill_id or '<unknown>'} uses route namespace {namespace!r} "
                f"that is not owned by pack {pack_id}."
            )
        eval_status = raw_skill.get("eval_status")
        if eval_status == "deprecated":
            deprecation = raw_skill.get("deprecation")
            replacement = deprecation.get("replaced_by") if isinstance(deprecation, dict) else None
            existing_skill_ids = {
                item.get("id")
                for item in registry.get("skills", [])
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            }
            if not isinstance(replacement, str) or replacement not in existing_skill_ids | pack_skill_ids:
                raise SkillRegistryError(
                    f"Skill pack skill {skill_id or '<unknown>'} has deprecated replacement gap."
                )
    for item in registry.get("skills", []):
        if not isinstance(item, dict):
            continue
        existing_owner = item.get("owner")
        existing_namespace = skill_route_namespace(item)
        if (
            isinstance(existing_owner, str)
            and existing_owner != owner
            and existing_namespace in declared_namespaces
            and item.get("eval_status") != "deprecated"
        ):
            raise SkillRegistryError(
                f"Skill pack namespace collision: {existing_namespace!r} is already used by owner {existing_owner!r}."
            )
    return {"route_namespace_counts": dict(sorted(route_namespace_counts.items()))}


def validate_skill_pack_manifest(manifest: dict[str, Any], config_root: Path) -> dict[str, Any]:
    config_root = config_root.resolve()
    header = validate_pack_header(manifest, config_root)
    registry = read_json_object(config_root / SKILL_REGISTRY_PATH, "skill registry")
    validate_skill_registry_manifest(registry, config_root)
    governance = validate_pack_skill_governance(
        pack_id=header["id"],
        owner=header["owner"],
        namespaces=header["namespaces"],
        skills=header["skills"],
        registry=registry,
    )
    batch_validation = validate_skill_batch_manifest(skill_pack_to_batch_manifest(manifest), config_root)
    return {
        "status": "ready",
        "schema_version": SCHEMA_VERSION,
        "kind": "skill_pack_validation",
        "pack_id": header["id"],
        "pack_version": header["version"],
        "owner": header["owner"],
        "namespaces": header["namespaces"],
        "compatibility": header["compatibility"],
        "docs": header["docs"],
        "summary": {
            **batch_validation["summary"],
            **governance,
            "namespace_count": len(header["namespaces"]),
        },
        "entries": batch_validation["entries"],
        "eval_cases": batch_validation["eval_cases"],
        "runtime_behavior_changed": False,
        "next_action": "review_then_install_pack_with_approval",
    }


def build_skill_pack_report(
    config_root: Path,
    pack_path: Path,
    *,
    output_path: Path | None = None,
) -> dict[str, Any]:
    config_root = config_root.resolve()
    manifest_path = pack_path if pack_path.is_absolute() else config_root / pack_path
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "skill_pack_validation_report",
        "status": "failed",
        "config_root": str(config_root),
        "pack_path": str(manifest_path.resolve()),
        "pack_id": "skill-pack",
        "pack_version": None,
        "owner": None,
        "namespaces": [],
        "summary": {
            "skill_count": 0,
            "eval_case_count": 0,
            "route_key_count": 0,
            "live_suite_counts": {},
            "route_namespace_counts": {},
            "namespace_count": 0,
        },
        "entries": [],
        "eval_cases": [],
        "errors": [],
    }
    try:
        manifest = read_pack_manifest(manifest_path)
        report["pack_id"] = pack_id_from_manifest(manifest)
        validation = validate_skill_pack_manifest(manifest, config_root)
        report.update(validation)
        report["status"] = "passed"
    except (SkillRegistryError, OSError) as exc:
        report["errors"].append(str(exc))
    path = output_path or default_report_path(config_root, str(report["pack_id"]))
    write_json(path, report)
    report["report_path"] = str(path.resolve())
    write_json(path, report)
    return report
