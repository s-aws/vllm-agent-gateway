"""EIG-3 breadth confidence closeout gate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.eig3_memory_lifecycle import (
    EIG3MemoryLifecycleConfig,
    run_eig3_memory_lifecycle_validation,
)
from vllm_agent_gateway.acceptance.eig3_output_surface_policy import (
    EIG3OutputSurfacePolicyConfig,
    run_eig3_output_surface_policy_validation,
)
from vllm_agent_gateway.acceptance.eig3_privacy_evalops import (
    EIG3PrivacyEvalOpsConfig,
    run_eig3_privacy_evalops,
)
from vllm_agent_gateway.acceptance.eig3_privacy_runtime_chat import (
    EIG3PrivacyRuntimeChatConfig,
    run_eig3_privacy_runtime_chat,
)
from vllm_agent_gateway.acceptance.eig3_sensitive_data import (
    EIG3SensitiveDataConfig,
    EIG3ValidationStatus,
    read_json_object,
    run_eig3_sensitive_data_validation,
    validation_error,
    write_json,
)
from vllm_agent_gateway.acceptance.v1 import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
)


SCHEMA_VERSION = 1
DEFAULT_POLICY_PATH = Path("runtime") / "eig3_breadth_closeout_policy.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "eig3-breadth-closeout"


@dataclass(frozen=True)
class EIG3BreadthCloseoutConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 180
    run_live_runtime: bool = True
    include_anythingllm: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"eig3-breadth-closeout-{utc_timestamp()}.json"


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = value if isinstance(value, Path) else Path(value)
    return path if path.is_absolute() else config_root / path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def object_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", f"schema_version must be {SCHEMA_VERSION}"))
    if policy.get("kind") != "eig3_breadth_closeout_policy":
        errors.append(validation_error("policy.kind", "kind must be eig3_breadth_closeout_policy"))
    if policy.get("phase") != 303:
        errors.append(validation_error("policy.phase", "phase must be 303"))
    if set(string_list(policy.get("required_milestones"))) != {"M32", "M33", "M34", "M35", "M36"}:
        errors.append(validation_error("policy.required_milestones", "required milestones must be M32-M36"))
    if set(policy.get("required_phases") or []) != {297, 298, 299, 300, 301, 302}:
        errors.append(validation_error("policy.required_phases", "required phases must be 297-302"))
    for field in ("required_docs", "required_runtime_files"):
        if not string_list(policy.get(field)):
            errors.append(validation_error(f"policy.{field}", f"{field} must be a non-empty string array"))
    return errors


def file_record(config_root: Path, path_value: str) -> dict[str, Any]:
    path = resolve_path(config_root, path_value)
    return {
        "path": path_value,
        "exists": path.is_file(),
        "sha256": sha256_file(path) if path.is_file() else None,
    }


def run_eig3_breadth_closeout(config: EIG3BreadthCloseoutConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    errors = validate_policy(policy)
    doc_records = [file_record(config_root, item) for item in string_list(policy.get("required_docs"))]
    runtime_records = [file_record(config_root, item) for item in string_list(policy.get("required_runtime_files"))]
    for item in doc_records:
        if item["exists"] is not True:
            errors.append(validation_error("docs.missing", f"required doc missing: {item['path']}"))
    for item in runtime_records:
        if item["exists"] is not True:
            errors.append(validation_error("runtime.missing", f"required runtime file missing: {item['path']}"))

    phase_reports = {
        "phase298": run_eig3_sensitive_data_validation(
            EIG3SensitiveDataConfig(
                config_root=config_root,
                output_path=output_path.parent / f"{output_path.stem}-phase298-validation.json",
            )
        ),
        "phase299": run_eig3_output_surface_policy_validation(
            EIG3OutputSurfacePolicyConfig(
                config_root=config_root,
                output_path=output_path.parent / f"{output_path.stem}-phase299-validation.json",
            )
        ),
        "phase300": run_eig3_memory_lifecycle_validation(
            EIG3MemoryLifecycleConfig(
                config_root=config_root,
                output_path=output_path.parent / f"{output_path.stem}-phase300-validation.json",
            )
        ),
        "phase301": run_eig3_privacy_evalops(
            EIG3PrivacyEvalOpsConfig(
                config_root=config_root,
                output_path=output_path.parent / f"{output_path.stem}-phase301-validation.json",
            )
        ),
        "phase302": run_eig3_privacy_runtime_chat(
            EIG3PrivacyRuntimeChatConfig(
                config_root=config_root,
                output_path=output_path.parent / f"{output_path.stem}-phase302-validation.json",
                workflow_router_gateway_base_url=config.workflow_router_gateway_base_url,
                anythingllm_api_base_url=config.anythingllm_api_base_url,
                workspace=config.workspace,
                api_key_env=config.api_key_env,
                timeout_seconds=config.timeout_seconds,
                run_live=config.run_live_runtime,
                include_anythingllm=config.include_anythingllm,
            )
        ),
    }
    for phase_id, report in phase_reports.items():
        if report.get("status") != EIG3ValidationStatus.PASSED.value:
            errors.append(validation_error(f"{phase_id}.status", f"{phase_id} report must pass"))
    status = EIG3ValidationStatus.PASSED.value if not errors else EIG3ValidationStatus.FAILED.value
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "eig3_breadth_closeout_report",
        "phase": 303,
        "status": status,
        "policy_path": str(policy_path),
        "summary": {
            "status": status,
            "required_doc_count": len(doc_records),
            "missing_doc_count": sum(1 for item in doc_records if item["exists"] is not True),
            "required_runtime_file_count": len(runtime_records),
            "missing_runtime_file_count": sum(1 for item in runtime_records if item["exists"] is not True),
            "phase_report_count": len(phase_reports),
            "failed_phase_report_count": sum(1 for item in phase_reports.values() if item.get("status") != EIG3ValidationStatus.PASSED.value),
            "validation_error_count": len(errors),
            "run_live_runtime": config.run_live_runtime,
            "include_anythingllm": config.include_anythingllm,
            "full_regression_required_before_phase_close": True,
            "phase303_closeout_ready": status == EIG3ValidationStatus.PASSED.value,
        },
        "docs": doc_records,
        "runtime_files": runtime_records,
        "phase_reports": {
            phase_id: {
                "kind": report.get("kind"),
                "phase": report.get("phase"),
                "status": report.get("status"),
                "summary": report.get("summary"),
                "report_path": report.get("report_path"),
            }
            for phase_id, report in phase_reports.items()
        },
        "validation_errors": errors,
        "report_path": str(output_path),
    }
    write_json(output_path, report)
    return report
