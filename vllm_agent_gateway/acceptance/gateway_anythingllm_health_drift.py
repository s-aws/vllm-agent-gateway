"""Health drift guard for gateway and AnythingLLM setup diagnostics."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from vllm_agent_gateway.acceptance.first_time_user_doctor import (
    DEFAULT_LLM_GATEWAY_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_ROLES_PATH,
    FirstTimeUserDoctorConfig,
    run_first_time_user_doctor,
)
from vllm_agent_gateway.acceptance.v1 import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    HEALTH_TARGETS,
)
from vllm_agent_gateway.fixtures.manager import DEFAULT_MANIFEST_PATH


SCHEMA_VERSION = 1
EXPECTED_REPORT_KIND = "gateway_anythingllm_health_drift_report"
EXPECTED_DOCTOR_KIND = "first_time_user_doctor_report"
EXPECTED_PHASE = 141
EXPECTED_BACKLOG_ID = "P0-BB-020"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "gateway-anythingllm-health-drift" / "phase141"
REQUIRED_CATEGORIES = {"anythingllm", "controller", "gateway_config", "port_health", "role_proxy"}


class HealthDriftGateStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class HealthDriftKind(str, Enum):
    NONE = "none"
    AUTH_FAILURE = "auth_failure"
    HEADERS_WITHOUT_BODY_TIMEOUT = "headers_without_body_timeout"
    UNCLASSIFIED_FAILURE = "unclassified_failure"
    UNEXPECTED_RESPONSE = "unexpected_response"
    UNREACHABLE_PORT = "unreachable_port"
    WRONG_BACKEND_TARGET = "wrong_backend_target"


@dataclass(frozen=True)
class GatewayAnythingLLMHealthDriftConfig:
    config_root: Path
    output_path: Path | None = None
    doctor_output_path: Path | None = None
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    llm_gateway_base_url: str = DEFAULT_LLM_GATEWAY_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    expected_anythingllm_llm_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    target_roots: tuple[str, ...] = tuple(DEFAULT_TARGET_ROOTS)
    manifest_path: Path = DEFAULT_MANIFEST_PATH
    roles_path: Path = DEFAULT_ROLES_PATH
    timeout_seconds: int = 30


DoctorRunner = Callable[[FirstTimeUserDoctorConfig], dict[str, Any]]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"gateway-anythingllm-health-drift-{utc_timestamp()}.json"


def default_doctor_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"first-time-user-doctor-{utc_timestamp()}.json"


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_hash(path: Path | None) -> str | None:
    return sha256_file(path) if path is not None and path.is_file() else None


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def expected_port_check_ids() -> set[str]:
    return {f"port.{target['name']}" for target in HEALTH_TARGETS}


def normalize_text(value: object) -> str:
    return str(value or "").strip().lower()


def details(check: dict[str, Any]) -> dict[str, Any]:
    value = check.get("details")
    return value if isinstance(value, dict) else {}


def check_status(check: dict[str, Any]) -> str:
    return str(check.get("status") or "")


def check_id(check: dict[str, Any]) -> str:
    return str(check.get("id") or "<missing>")


def check_category(check: dict[str, Any]) -> str:
    return str(check.get("category") or "unknown")


def http_status(check: dict[str, Any]) -> int | None:
    value = details(check).get("http_status")
    return value if isinstance(value, int) else None


def is_failed_or_warning(check: dict[str, Any]) -> bool:
    return check_status(check) in {"failed", "warning", "skipped"}


def contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def classify_drift_kind(check: dict[str, Any]) -> HealthDriftKind:
    if not is_failed_or_warning(check):
        return HealthDriftKind.NONE

    cid = check_id(check)
    category = check_category(check)
    status_code = http_status(check)
    diagnostic_kind = str(details(check).get("diagnostic_kind") or "")
    message = normalize_text(check.get("message"))
    next_action = normalize_text(check.get("next_action"))
    detail_text = normalize_text(json.dumps(details(check), ensure_ascii=True, sort_keys=True))
    combined = " ".join([message, next_action, detail_text])

    if diagnostic_kind == HealthDriftKind.HEADERS_WITHOUT_BODY_TIMEOUT.value:
        return HealthDriftKind.HEADERS_WITHOUT_BODY_TIMEOUT
    if diagnostic_kind == HealthDriftKind.UNREACHABLE_PORT.value:
        return HealthDriftKind.UNREACHABLE_PORT
    if diagnostic_kind == "invalid_json_body":
        return HealthDriftKind.UNEXPECTED_RESPONSE
    if cid == "anythingllm.api_key":
        return HealthDriftKind.AUTH_FAILURE
    if category == "anythingllm" and (
        status_code in {401, 403}
        or contains_any(combined, ("unauthorized", "forbidden", "invalid api key", "api key", "bearer"))
    ):
        return HealthDriftKind.AUTH_FAILURE
    if contains_any(
        combined,
        (
            "headers without body",
            "headers-without-body",
            "waiting for body bytes",
            "body bytes",
            "read timed out",
            "response body timed out",
        ),
    ):
        return HealthDriftKind.HEADERS_WITHOUT_BODY_TIMEOUT
    if cid == "anythingllm.target_url":
        return HealthDriftKind.WRONG_BACKEND_TARGET
    if category == "gateway_config" and (
        "target_base_url" in details(check)
        or "controller_routing" in details(check)
        or "controller_harness_url" in details(check)
    ):
        return HealthDriftKind.WRONG_BACKEND_TARGET
    if cid.startswith("port.") and (
        status_code is None
        or contains_any(
            combined,
            (
                "connectionrefused",
                "connection refused",
                "failed to establish",
                "actively refused",
                "unreachable",
                "cannot connect",
                "name or service not known",
                "errno 111",
                "errno 10061",
            ),
        )
    ):
        return HealthDriftKind.UNREACHABLE_PORT
    if status_code == 200:
        return HealthDriftKind.UNEXPECTED_RESPONSE
    if status_code is not None and status_code != 200:
        return HealthDriftKind.UNEXPECTED_RESPONSE
    return HealthDriftKind.UNCLASSIFIED_FAILURE


def finding_for_check(check: dict[str, Any]) -> dict[str, Any] | None:
    if check_category(check) not in REQUIRED_CATEGORIES:
        return None
    kind = classify_drift_kind(check)
    if kind == HealthDriftKind.NONE:
        return None
    detail = details(check)
    return {
        "check_id": check_id(check),
        "category": check_category(check),
        "status": check_status(check),
        "kind": kind.value,
        "message": str(check.get("message") or ""),
        "next_action": str(check.get("next_action") or default_next_action(kind)),
        "url": detail.get("url"),
        "http_status": detail.get("http_status"),
    }


def default_next_action(kind: HealthDriftKind) -> str:
    if kind == HealthDriftKind.UNREACHABLE_PORT:
        return "Restart the local model, gateway, controller, and role proxy stack from Bash."
    if kind == HealthDriftKind.HEADERS_WITHOUT_BODY_TIMEOUT:
        return "Retry from Bash and inspect the upstream service logs for a response-body hang."
    if kind == HealthDriftKind.WRONG_BACKEND_TARGET:
        return "Restart with the documented gateway/controller targets and point AnythingLLM at http://127.0.0.1:8500/v1."
    if kind == HealthDriftKind.AUTH_FAILURE:
        return "Refresh ANYTHINGLLM_API_KEY and verify it is exported into the validation environment."
    return "Inspect the doctor check details and correct the failing local harness component."


def kind_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts = {kind.value: 0 for kind in HealthDriftKind if kind != HealthDriftKind.NONE}
    for item in findings:
        kind = str(item.get("kind") or HealthDriftKind.UNCLASSIFIED_FAILURE.value)
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def validate_doctor_shape(doctor_report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if doctor_report.get("kind") != EXPECTED_DOCTOR_KIND:
        errors.append(f"doctor_report.kind must be {EXPECTED_DOCTOR_KIND}")
    checks = object_list(doctor_report.get("checks"))
    summary = doctor_report.get("summary") if isinstance(doctor_report.get("summary"), dict) else {}
    if summary.get("check_count") != len(checks):
        errors.append("doctor_report.summary.check_count must match checks length")

    failed_ids = sorted(check_id(item) for item in checks if check_status(item) == "failed")
    if sorted(summary.get("failed_check_ids") or []) != failed_ids:
        errors.append("doctor_report.summary.failed_check_ids must match failed checks")
    warning_ids = sorted(check_id(item) for item in checks if check_status(item) == "warning")
    if sorted(summary.get("warning_check_ids") or []) != warning_ids:
        errors.append("doctor_report.summary.warning_check_ids must match warning checks")

    categories = {check_category(item) for item in checks}
    missing_categories = sorted(REQUIRED_CATEGORIES - categories)
    if missing_categories:
        errors.append("doctor_report.checks missing required categories: " + ", ".join(missing_categories))

    check_ids = {check_id(item) for item in checks}
    missing_ports = sorted(expected_port_check_ids() - check_ids)
    if missing_ports:
        errors.append("doctor_report.checks missing featured port checks: " + ", ".join(missing_ports))
    return errors


def build_gateway_anythingllm_health_drift_report(
    *,
    doctor_report: dict[str, Any],
    doctor_report_path: Path | None = None,
) -> dict[str, Any]:
    checks = object_list(doctor_report.get("checks"))
    findings = [item for item in (finding_for_check(check) for check in checks) if item is not None]
    errors = validate_doctor_shape(doctor_report)
    categories = sorted({check_category(item) for item in checks})
    missing_categories = sorted(REQUIRED_CATEGORIES - set(categories))
    port_check_ids = sorted(check_id(item) for item in checks if check_id(item).startswith("port."))
    missing_port_check_ids = sorted(expected_port_check_ids() - set(port_check_ids))
    counts = kind_counts(findings)
    unclassified_count = counts.get(HealthDriftKind.UNCLASSIFIED_FAILURE.value, 0)
    if unclassified_count:
        errors.append("health drift findings include unclassified failures")
    status = HealthDriftGateStatus.FAILED.value if findings or errors else HealthDriftGateStatus.PASSED.value
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": status,
        "generated_at": utc_timestamp(),
        "doctor_report_path": str(doctor_report_path) if doctor_report_path else None,
        "doctor_report_sha256": artifact_hash(doctor_report_path) if doctor_report_path else None,
        "doctor_status": doctor_report.get("status"),
        "doctor_summary": doctor_report.get("summary"),
        "checked_categories": categories,
        "missing_required_categories": missing_categories,
        "port_check_ids": port_check_ids,
        "missing_port_check_ids": missing_port_check_ids,
        "findings": findings,
        "summary": {
            "check_count": len(checks),
            "failed_check_count": sum(1 for item in checks if check_status(item) == "failed"),
            "warning_check_count": sum(1 for item in checks if check_status(item) == "warning"),
            "skipped_check_count": sum(1 for item in checks if check_status(item) == "skipped"),
            "finding_count": len(findings),
            "kind_counts": counts,
            "unclassified_finding_count": unclassified_count,
        },
        "errors": errors,
    }


def validate_gateway_anythingllm_health_drift_report(
    report: dict[str, Any],
    *,
    doctor_report: dict[str, Any],
    doctor_report_path: Path | None = None,
) -> list[str]:
    expected = build_gateway_anythingllm_health_drift_report(
        doctor_report=doctor_report,
        doctor_report_path=doctor_report_path,
    )
    errors: list[str] = []
    for key in (
        "schema_version",
        "kind",
        "phase",
        "priority_backlog_id",
        "status",
        "doctor_report_path",
        "doctor_report_sha256",
        "doctor_status",
        "doctor_summary",
        "checked_categories",
        "missing_required_categories",
        "port_check_ids",
        "missing_port_check_ids",
        "findings",
        "summary",
        "errors",
    ):
        if report.get(key) != expected.get(key):
            errors.append(f"report.{key} must match rebuilt gateway/AnythingLLM health drift report")
    return errors


def doctor_config_from_guard_config(config: GatewayAnythingLLMHealthDriftConfig) -> FirstTimeUserDoctorConfig:
    config_root = config.config_root.resolve()
    doctor_output_path = config.doctor_output_path or default_doctor_report_path(config_root)
    if not doctor_output_path.is_absolute():
        doctor_output_path = config_root / doctor_output_path
    return FirstTimeUserDoctorConfig(
        config_root=config_root,
        model_base_url=config.model_base_url,
        llm_gateway_base_url=config.llm_gateway_base_url,
        workflow_router_gateway_base_url=config.workflow_router_gateway_base_url,
        controller_base_url=config.controller_base_url,
        anythingllm_api_base_url=config.anythingllm_api_base_url,
        workspace=config.workspace,
        expected_anythingllm_llm_base_url=config.expected_anythingllm_llm_base_url,
        api_key_env=config.api_key_env,
        target_roots=config.target_roots,
        manifest_path=config.manifest_path,
        roles_path=config.roles_path,
        output_path=doctor_output_path,
        timeout_seconds=config.timeout_seconds,
    )


def run_gateway_anythingllm_health_drift_guard(
    config: GatewayAnythingLLMHealthDriftConfig,
    *,
    doctor_runner: DoctorRunner = run_first_time_user_doctor,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    doctor_config = doctor_config_from_guard_config(config)
    doctor_report = doctor_runner(doctor_config)
    doctor_report_path_value = doctor_report.get("report_path") or str(doctor_config.output_path or "")
    doctor_report_path = resolve_path(config_root, doctor_report_path_value) if doctor_report_path_value else None
    report = build_gateway_anythingllm_health_drift_report(
        doctor_report=doctor_report,
        doctor_report_path=doctor_report_path,
    )
    validation_errors = validate_gateway_anythingllm_health_drift_report(
        report,
        doctor_report=doctor_report,
        doctor_report_path=doctor_report_path,
    )
    if validation_errors:
        report["status"] = HealthDriftGateStatus.FAILED.value
        report["errors"] = list(report.get("errors") or []) + validation_errors
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
