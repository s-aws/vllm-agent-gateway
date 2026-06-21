"""EIG stable handoff integration gate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.eig1_connector_breadth import (
    read_json_object,
    validation_error,
)


SCHEMA_VERSION = 1
DEFAULT_POLICY_PATH = Path("runtime") / "eig_stable_handoff_integration_policy.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "eig-stable-handoff-integration"


@dataclass(frozen=True)
class EIGStableHandoffIntegrationConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"eig-stable-handoff-integration-{utc_timestamp()}.json"


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = value if isinstance(value, Path) else Path(value)
    return path if path.is_absolute() else config_root / path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def string_map(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    return {str(key): string_list(item) for key, item in value.items()}


def file_record(config_root: Path, path_value: str) -> dict[str, Any]:
    path = resolve_path(config_root, path_value)
    return {
        "path": path_value,
        "exists": path.is_file(),
        "sha256": sha256_file(path) if path.is_file() else None,
    }


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", f"schema_version must be {SCHEMA_VERSION}"))
    if policy.get("kind") != "eig_stable_handoff_integration_policy":
        errors.append(
            validation_error("policy.kind", "kind must be eig_stable_handoff_integration_policy")
        )
    if policy.get("phase") != 304:
        errors.append(validation_error("policy.phase", "phase must be 304"))
    for field in ("required_docs", "required_runtime_files", "required_scripts", "required_milestones"):
        if not string_list(policy.get(field)):
            errors.append(validation_error(f"policy.{field}", f"{field} must be a non-empty string array"))
    if not string_map(policy.get("required_markers")):
        errors.append(validation_error("policy.required_markers", "required_markers must be a non-empty object"))
    boundary = policy.get("scope_boundary")
    if not isinstance(boundary, dict):
        errors.append(validation_error("policy.scope_boundary", "scope_boundary must be an object"))
    else:
        for key in (
            "arbitrary_natural_connector_calls_shipped",
            "persistent_hidden_memory_shipped",
            "production_oauth_token_exchange_shipped",
            "raw_mcp_access_shipped",
            "real_external_connector_execution_shipped",
            "real_sensitive_data_ingestion_shipped",
        ):
            if boundary.get(key) is not False:
                errors.append(validation_error(f"policy.scope_boundary.{key}", f"{key} must be false"))
    return errors


def marker_report(config_root: Path, marker_map: dict[str, list[str]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path_value, markers in sorted(marker_map.items()):
        path = resolve_path(config_root, path_value)
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        for marker in markers:
            results.append(
                {
                    "path": path_value,
                    "marker": marker,
                    "present": marker in text,
                }
            )
    return results


def run_eig_stable_handoff_integration(
    config: EIGStableHandoffIntegrationConfig,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root)
    output_path = resolve_path(config_root, output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    errors = validate_policy(policy)

    doc_records = [file_record(config_root, item) for item in string_list(policy.get("required_docs"))]
    runtime_records = [file_record(config_root, item) for item in string_list(policy.get("required_runtime_files"))]
    script_records = [file_record(config_root, item) for item in string_list(policy.get("required_scripts"))]
    for item in doc_records:
        if item["exists"] is not True:
            errors.append(validation_error("docs.missing", f"required doc missing: {item['path']}"))
    for item in runtime_records:
        if item["exists"] is not True:
            errors.append(validation_error("runtime.missing", f"required runtime file missing: {item['path']}"))
    for item in script_records:
        if item["exists"] is not True:
            errors.append(validation_error("scripts.missing", f"required script missing: {item['path']}"))

    markers = marker_report(config_root, string_map(policy.get("required_markers")))
    for marker in markers:
        if marker["present"] is not True:
            errors.append(
                validation_error(
                    "docs.marker_missing",
                    f"required marker missing from {marker['path']}: {marker['marker']}",
                )
            )

    status = "passed" if not errors else "failed"
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "eig_stable_handoff_integration_report",
        "phase": 304,
        "status": status,
        "policy_path": str(policy_path),
        "summary": {
            "status": status,
            "required_doc_count": len(doc_records),
            "missing_doc_count": sum(1 for item in doc_records if item["exists"] is not True),
            "required_runtime_file_count": len(runtime_records),
            "missing_runtime_file_count": sum(1 for item in runtime_records if item["exists"] is not True),
            "required_script_count": len(script_records),
            "missing_script_count": sum(1 for item in script_records if item["exists"] is not True),
            "marker_count": len(markers),
            "missing_marker_count": sum(1 for item in markers if item["present"] is not True),
            "validation_error_count": len(errors),
            "phase305_ready": status == "passed",
        },
        "docs": doc_records,
        "runtime_files": runtime_records,
        "scripts": script_records,
        "markers": markers,
        "scope_boundary": policy.get("scope_boundary"),
        "validation_errors": errors,
        "report_path": str(output_path),
    }
    output_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
