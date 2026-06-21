"""EIG-1/EIG-2 breadth confidence closeout gate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.eig1_connector_breadth import (
    EIG1ConnectorBreadthConfig,
    read_json_object,
    run_eig1_connector_breadth_validation,
    validation_error,
)
from vllm_agent_gateway.acceptance.eig1_connector_release_gate_breadth import (
    EIG1ConnectorReleaseGateBreadthConfig,
    run_eig1_connector_release_gate_breadth,
)
from vllm_agent_gateway.acceptance.eig1_protocol_auth_schema_matrix import (
    EIG1ProtocolAuthSchemaConfig,
    run_eig1_protocol_auth_schema_validation,
)
from vllm_agent_gateway.acceptance.eig1_registry_lifecycle_breadth import (
    EIG1RegistryLifecycleBreadthConfig,
    run_eig1_registry_lifecycle_breadth,
)
from vllm_agent_gateway.acceptance.eig2_actor_scope_breadth import (
    EIG2ActorScopeBreadthConfig,
    run_eig2_actor_scope_breadth_validation,
)
from vllm_agent_gateway.acceptance.eig2_approval_replay_breadth import (
    EIG2ApprovalReplayBreadthConfig,
    run_eig2_approval_replay_breadth_validation,
)
from vllm_agent_gateway.acceptance.eig_runtime_breadth_chat import (
    EIGRuntimeBreadthChatConfig,
    run_eig_runtime_breadth_chat_validation,
)


SCHEMA_VERSION = 1
DEFAULT_POLICY_PATH = Path("runtime") / "eig_breadth_closeout_policy.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "eig-breadth-closeout"


@dataclass(frozen=True)
class EIGBreadthCloseoutConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    workflow_router_gateway_base_url: str | None = None
    run_live_runtime: bool = False
    include_anythingllm: bool = False
    anythingllm_api_base_url: str = "http://127.0.0.1:3001"
    anythingllm_workspace: str = "my-workspace"
    anythingllm_api_key_env: str = "ANYTHINGLLM_API_KEY"
    controller_base_url: str = "http://127.0.0.1:8400"
    timeout_seconds: int = 120


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"eig-breadth-closeout-{utc_timestamp()}.json"


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
    return [item for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []


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
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != "eig_breadth_closeout_policy":
        errors.append(validation_error("policy.kind", "kind must be eig_breadth_closeout_policy"))
    if policy.get("phase") != 296:
        errors.append(validation_error("policy.phase", "phase must be 296"))
    if set(string_list(policy.get("required_milestones"))) != {"M26", "M27", "M28", "M29", "M30", "M31"}:
        errors.append(validation_error("policy.required_milestones", "required milestones must be M26-M31"))
    if set(policy.get("required_phases") or []) != {288, 289, 290, 291, 292, 293, 294, 295}:
        errors.append(validation_error("policy.required_phases", "required phases must be 288-295"))
    for field in ("required_docs", "required_runtime_files", "required_status_coverage"):
        if not string_list(policy.get(field)):
            errors.append(validation_error(f"policy.{field}", f"{field} must be a non-empty string array"))
    boundary = policy.get("scope_boundary")
    if not isinstance(boundary, dict):
        errors.append(validation_error("policy.scope_boundary", "scope_boundary must be an object"))
    else:
        for key in (
            "real_external_connector_execution",
            "raw_mcp_allowed",
            "direct_model_tool_access_allowed",
            "runtime_registry_mutation_allowed",
            "target_repository_mutation_allowed",
            "arbitrary_natural_connector_calls_allowed",
        ):
            if boundary.get(key) is not False:
                errors.append(validation_error(f"policy.scope_boundary.{key}", f"{key} must be false"))
    return errors


def compact_phase_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": report.get("kind"),
        "status": report.get("status"),
        "summary": report.get("summary"),
        "report_path": report.get("report_path"),
    }


def coverage_status(phase_reports: dict[str, dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
    eig1 = phase_reports.get("phase289", {})
    eig1_summary = eig1.get("summary") if isinstance(eig1.get("summary"), dict) else {}
    protocol = phase_reports.get("phase290", {})
    release = phase_reports.get("phase291", {})
    lifecycle = phase_reports.get("phase292", {})
    actor = phase_reports.get("phase293", {})
    replay = phase_reports.get("phase294", {})
    chat = phase_reports.get("phase295", {})
    chat_summary = chat.get("summary") if isinstance(chat.get("summary"), dict) else {}
    actual = {
        "work_tracking_stub": eig1_summary.get("archetype_count", 0) >= 3,
        "knowledge_lookup_stub": eig1_summary.get("archetype_count", 0) >= 3,
        "business_record_stub": eig1_summary.get("archetype_count", 0) >= 3,
        "read_operation": eig1_summary.get("read_operation_class_covered") is True,
        "write_dry_run_operation": eig1_summary.get("write_operation_class_covered") is True,
        "positive_invocation": eig1_summary.get("positive_invocation_count", 0) >= 6,
        "negative_control": eig1_summary.get("negative_control_count", 0) >= 6,
        "protocol_auth_schema_matrix": protocol.get("status") == "passed",
        "release_gate": release.get("status") == "passed",
        "registry_lifecycle": lifecycle.get("status") == "passed",
        "actor_scope": actor.get("status") == "passed",
        "approval_replay": replay.get("status") == "passed",
        "natural_language_chat": chat_summary.get("passed_case_count") == chat_summary.get("case_count") == 3,
    }
    required = string_list(policy.get("required_status_coverage"))
    missing = sorted(item for item in required if actual.get(item) is not True)
    return {"coverage": actual, "missing": missing}


def run_phase_reports(config: EIGBreadthCloseoutConfig, output_path: Path) -> dict[str, dict[str, Any]]:
    config_root = config.config_root.resolve()
    report_dir = output_path.parent
    reports = {
        "phase289": run_eig1_connector_breadth_validation(
            EIG1ConnectorBreadthConfig(
                config_root=config_root,
                output_path=report_dir / f"{output_path.stem}-phase289-validation.json",
            )
        ),
        "phase290": run_eig1_protocol_auth_schema_validation(
            EIG1ProtocolAuthSchemaConfig(
                config_root=config_root,
                output_path=report_dir / f"{output_path.stem}-phase290-validation.json",
            )
        ),
        "phase291": run_eig1_connector_release_gate_breadth(
            EIG1ConnectorReleaseGateBreadthConfig(
                config_root=config_root,
                output_path=report_dir / f"{output_path.stem}-phase291-validation.json",
            )
        ),
        "phase292": run_eig1_registry_lifecycle_breadth(
            EIG1RegistryLifecycleBreadthConfig(
                config_root=config_root,
                output_path=report_dir / f"{output_path.stem}-phase292-validation.json",
            )
        ),
        "phase293": run_eig2_actor_scope_breadth_validation(
            EIG2ActorScopeBreadthConfig(
                config_root=config_root,
                output_path=report_dir / f"{output_path.stem}-phase293-validation.json",
            )
        ),
        "phase294": run_eig2_approval_replay_breadth_validation(
            EIG2ApprovalReplayBreadthConfig(
                config_root=config_root,
                output_path=report_dir / f"{output_path.stem}-phase294-validation.json",
            )
        ),
        "phase295": run_eig_runtime_breadth_chat_validation(
            EIGRuntimeBreadthChatConfig(
                config_root=config_root,
                output_path=report_dir / f"{output_path.stem}-phase295-validation.json",
                controller_output_root=report_dir / "controller-artifacts-phase295",
                base_url=config.workflow_router_gateway_base_url if config.run_live_runtime else None,
                timeout_seconds=config.timeout_seconds,
            )
        ),
    }
    if config.include_anythingllm:
        reports["phase295_anythingllm"] = run_eig_runtime_breadth_chat_validation(
            EIGRuntimeBreadthChatConfig(
                config_root=config_root,
                output_path=report_dir / f"{output_path.stem}-phase295-anythingllm-validation.json",
                controller_output_root=report_dir / "controller-artifacts-phase295-anythingllm",
                anythingllm_api_base_url=config.anythingllm_api_base_url,
                anythingllm_workspace=config.anythingllm_workspace,
                anythingllm_api_key_env=config.anythingllm_api_key_env,
                controller_base_url=config.controller_base_url,
                timeout_seconds=config.timeout_seconds,
            )
        )
    return reports


def run_eig_breadth_closeout(config: EIGBreadthCloseoutConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root)
    output_path = resolve_path(config_root, output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    errors = validate_policy(policy)
    docs = [file_record(config_root, item) for item in string_list(policy.get("required_docs"))]
    runtime_files = [file_record(config_root, item) for item in string_list(policy.get("required_runtime_files"))]
    for item in docs:
        if item["exists"] is not True:
            errors.append(validation_error("docs.missing", f"required doc missing: {item['path']}"))
    for item in runtime_files:
        if item["exists"] is not True:
            errors.append(validation_error("runtime.missing", f"required runtime file missing: {item['path']}"))
    source_connector_hash = sha256_file(config_root / "runtime" / "connectors.json")
    phase_reports = run_phase_reports(config, output_path)
    for phase_id, report in phase_reports.items():
        if report.get("status") != "passed":
            errors.append(validation_error(f"{phase_id}.status", f"{phase_id} report must pass"))
    coverage = coverage_status(phase_reports, policy)
    for item in coverage["missing"]:
        errors.append(validation_error("coverage.missing", f"missing required coverage: {item}"))
    source_connector_registry_changed = sha256_file(config_root / "runtime" / "connectors.json") != source_connector_hash
    if source_connector_registry_changed:
        errors.append(validation_error("runtime.connectors_mutated", "source runtime/connectors.json changed during closeout"))
    status = "failed" if errors else "passed"
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "eig_breadth_closeout_report",
        "phase": 296,
        "status": status,
        "policy_path": str(policy_path),
        "summary": {
            "status": status,
            "required_doc_count": len(docs),
            "missing_doc_count": sum(1 for item in docs if item["exists"] is not True),
            "required_runtime_file_count": len(runtime_files),
            "missing_runtime_file_count": sum(1 for item in runtime_files if item["exists"] is not True),
            "phase_report_count": len(phase_reports),
            "failed_phase_report_count": sum(1 for item in phase_reports.values() if item.get("status") != "passed"),
            "coverage_missing_count": len(coverage["missing"]),
            "validation_error_count": len(errors),
            "source_connector_registry_changed": source_connector_registry_changed,
            "run_live_runtime": config.run_live_runtime,
            "include_anythingllm": config.include_anythingllm,
            "full_regression_required_before_phase_close": True,
            "phase296_closeout_ready": status == "passed",
        },
        "docs": docs,
        "runtime_files": runtime_files,
        "coverage": coverage,
        "phase_reports": {phase_id: compact_phase_report(report) for phase_id, report in phase_reports.items()},
        "validation_errors": errors,
        "report_path": str(output_path),
    }
    output_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
