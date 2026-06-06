"""Skill-pack packaging policy validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.skills.packs import REQUIRED_PACK_FIELDS
from vllm_agent_gateway.skills.registry import ROUTE_KEY_NAMESPACES, SCHEMA_VERSION, SEMVER_RE, STRICT_ROUTE_NAMESPACE_RULES


DEFAULT_POLICY_PATH = Path("runtime") / "skill_pack_policy.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "skill-packaging-policy"
REQUIRED_POLICY_FIELDS = {
    "schema_version",
    "kind",
    "policy_id",
    "version",
    "owner",
    "status",
    "description",
    "layout",
    "manifest_contract",
    "namespace_ownership",
    "dependency_policy",
    "versioning",
    "import_export",
    "retirement",
    "validation",
}


class SkillPackPolicyStatus(str, Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


@dataclass(frozen=True)
class SkillPackPolicyConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"skill-packaging-policy-{utc_timestamp()}.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"policy root must be an object: {path}")
    return value


def resolve_policy_path(config: SkillPackPolicyConfig) -> Path:
    path = config.policy_path
    return path if path.is_absolute() else config.config_root / path


def string_list(value: Any, label: str, errors: list[str], *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        errors.append(f"{label} must be a {'list' if allow_empty else 'non-empty list'} of strings")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{label}[{index}] must be a non-empty string")
        else:
            result.append(item)
    return result


def object_field(value: dict[str, Any], key: str, errors: list[str]) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        errors.append(f"{key} must be an object")
        return {}
    return item


def validate_packaging_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_POLICY_FIELDS - set(policy))
    if missing:
        errors.append("policy missing field(s): " + ", ".join(missing))
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if policy.get("kind") != "skill_pack_policy":
        errors.append("kind must be skill_pack_policy")
    if not isinstance(policy.get("policy_id"), str) or not policy["policy_id"].strip():
        errors.append("policy_id must be a non-empty string")
    version = policy.get("version")
    if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
        errors.append("version must be semantic version x.y.z")
    if policy.get("status") not in {item.value for item in SkillPackPolicyStatus}:
        errors.append("status must be active, deprecated, or retired")
    if not isinstance(policy.get("owner"), str) or not policy["owner"].strip():
        errors.append("owner must be a non-empty string")
    if not isinstance(policy.get("description"), str) or len(policy["description"].strip()) < 40:
        errors.append("description must explain the packaging policy")

    layout = object_field(policy, "layout", errors)
    if layout.get("manifest_filename") != "pack.json":
        errors.append("layout.manifest_filename must be pack.json")
    if layout.get("skill_body_path_template") != "skills/{skill_id}/SKILL.md":
        errors.append("layout.skill_body_path_template must be skills/{skill_id}/SKILL.md")
    registry_targets = string_list(layout.get("registry_targets"), "layout.registry_targets", errors)
    for required_target in ("runtime/skills.json", "runtime/skill_evals.json", ".qwen/skills"):
        if required_target not in registry_targets:
            errors.append(f"layout.registry_targets must include {required_target}")

    manifest_contract = object_field(policy, "manifest_contract", errors)
    if manifest_contract.get("kind") != "skill_pack_manifest":
        errors.append("manifest_contract.kind must be skill_pack_manifest")
    required_fields = set(string_list(manifest_contract.get("required_fields"), "manifest_contract.required_fields", errors))
    if required_fields != REQUIRED_PACK_FIELDS:
        missing_fields = sorted(REQUIRED_PACK_FIELDS - required_fields)
        extra_fields = sorted(required_fields - REQUIRED_PACK_FIELDS)
        errors.append(
            "manifest_contract.required_fields must match skill pack validator fields"
            + (f"; missing={missing_fields}" if missing_fields else "")
            + (f"; extra={extra_fields}" if extra_fields else "")
        )
    if manifest_contract.get("skill_status_on_import") != "draft":
        errors.append("manifest_contract.skill_status_on_import must be draft")
    if manifest_contract.get("validation_workflow") != "skill_pack.validate":
        errors.append("manifest_contract.validation_workflow must be skill_pack.validate")
    if manifest_contract.get("install_workflow") != "skill_pack.install":
        errors.append("manifest_contract.install_workflow must be skill_pack.install")

    namespace = object_field(policy, "namespace_ownership", errors)
    allowed_namespaces = set(string_list(namespace.get("allowed_route_namespaces"), "namespace_ownership.allowed_route_namespaces", errors))
    if allowed_namespaces != ROUTE_KEY_NAMESPACES:
        errors.append("namespace_ownership.allowed_route_namespaces must match registry route namespaces")
    if namespace.get("pack_namespaces_must_cover_skill_route_keys") is not True:
        errors.append("namespace_ownership.pack_namespaces_must_cover_skill_route_keys must be true")
    if namespace.get("pack_owner_must_match_skill_owner") is not True:
        errors.append("namespace_ownership.pack_owner_must_match_skill_owner must be true")
    strict_rules = namespace.get("strict_namespace_rules")
    if not isinstance(strict_rules, dict):
        errors.append("namespace_ownership.strict_namespace_rules must be an object")
    else:
        expected_strict = {
            key: {
                **value,
                "workflows": sorted(value["workflows"]),
            }
            for key, value in STRICT_ROUTE_NAMESPACE_RULES.items()
        }
        observed_strict = {}
        for key, value in strict_rules.items():
            if isinstance(value, dict):
                observed_strict[key] = {**value, "workflows": sorted(value.get("workflows") or [])}
        if observed_strict != expected_strict:
            errors.append("namespace_ownership.strict_namespace_rules must match registry strict namespace rules")

    dependency = object_field(policy, "dependency_policy", errors)
    if dependency.get("runtime_dependency_mode") != "metadata_and_existing_controller_capabilities_only":
        errors.append("dependency_policy.runtime_dependency_mode must use existing controller capabilities only")
    disallowed = set(string_list(dependency.get("disallowed_dependency_types"), "dependency_policy.disallowed_dependency_types", errors))
    for required_disallowed in ("new_python_packages", "new_external_services", "model_fine_tuning_requirement"):
        if required_disallowed not in disallowed:
            errors.append(f"dependency_policy.disallowed_dependency_types must include {required_disallowed}")

    versioning = object_field(policy, "versioning", errors)
    if versioning.get("semver_required") is not True:
        errors.append("versioning.semver_required must be true")
    bump_rules = versioning.get("version_bump_rules")
    if not isinstance(bump_rules, dict):
        errors.append("versioning.version_bump_rules must be an object")
    else:
        for key in ("metadata_only", "new_skill_or_eval_case", "route_key_or_namespace_change", "workflow_or_tool_dependency_change"):
            if key not in bump_rules:
                errors.append(f"versioning.version_bump_rules must include {key}")
        if bump_rules.get("route_key_or_namespace_change") != "major":
            errors.append("route key or namespace changes must require a major version bump")

    import_export = object_field(policy, "import_export", errors)
    if import_export.get("export_artifact_kind") != "skill_pack_manifest":
        errors.append("import_export.export_artifact_kind must be skill_pack_manifest")
    if import_export.get("install_requires_approval_status") != "approved_for_skill_pack_install":
        errors.append("import_export.install_requires_approval_status must be approved_for_skill_pack_install")
    if import_export.get("install_requires_validation_rerun") is not True:
        errors.append("import_export.install_requires_validation_rerun must be true")
    if import_export.get("uninstall_supported") is not False:
        errors.append("import_export.uninstall_supported must be false until a roadmap phase adds uninstall")

    retirement = object_field(policy, "retirement", errors)
    if retirement.get("preferred_operation") != "skill.deprecate":
        errors.append("retirement.preferred_operation must be skill.deprecate")
    if retirement.get("deprecated_skill_requires_replacement") is not True:
        errors.append("retirement.deprecated_skill_requires_replacement must be true")
    if retirement.get("uninstall_policy") != "not_supported_until_explicit_roadmap_phase":
        errors.append("retirement.uninstall_policy must block uninstall until a roadmap phase adds it")

    validation = object_field(policy, "validation", errors)
    docs = string_list(validation.get("docs"), "validation.docs", errors)
    for doc_ref in docs:
        if not (doc_ref.startswith("README") or doc_ref.startswith("docs/")):
            errors.append(f"validation.docs contains unsupported doc path: {doc_ref}")
    return errors


def run_skill_packaging_policy(config: SkillPackPolicyConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root)
    policy_path = resolve_policy_path(config)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "skill_packaging_policy_report",
        "status": "failed",
        "created_at": utc_timestamp(),
        "policy_path": str(policy_path),
        "policy_id": "",
        "policy_version": "",
        "summary": {},
        "errors": [],
    }
    try:
        policy = read_json(policy_path)
        report["policy_id"] = policy.get("policy_id", "")
        report["policy_version"] = policy.get("version", "")
        errors = validate_packaging_policy(policy)
        report["errors"] = errors
        namespace = policy.get("namespace_ownership") if isinstance(policy.get("namespace_ownership"), dict) else {}
        manifest_contract = policy.get("manifest_contract") if isinstance(policy.get("manifest_contract"), dict) else {}
        report["summary"] = {
            "allowed_namespace_count": len(namespace.get("allowed_route_namespaces") or []),
            "strict_namespace_count": len(namespace.get("strict_namespace_rules") or {}),
            "manifest_required_field_count": len(manifest_contract.get("required_fields") or []),
            "doc_count": len(policy.get("validation", {}).get("docs") or {}) if isinstance(policy.get("validation"), dict) else 0,
        }
        report["status"] = "passed" if not errors else "failed"
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"{type(exc).__name__}: {exc}")
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
