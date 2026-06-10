"""Post-restart runtime readiness gate for founder testing."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from vllm_agent_gateway.acceptance.anythingllm_session_recovery import (
    AnythingLLMSessionRecoveryConfig,
    run_anythingllm_session_recovery,
)
from vllm_agent_gateway.acceptance.first_time_user_doctor import (
    DEFAULT_LLM_GATEWAY_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_ROLES_PATH,
)
from vllm_agent_gateway.acceptance.gateway_anythingllm_health_drift import (
    GatewayAnythingLLMHealthDriftConfig,
    run_gateway_anythingllm_health_drift_guard,
)
from vllm_agent_gateway.acceptance.v1 import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
)
from vllm_agent_gateway.fixtures.manager import DEFAULT_MANIFEST_PATH


SCHEMA_VERSION = 1
EXPECTED_REPORT_KIND = "post_restart_runtime_readiness_report"
EXPECTED_POLICY_KIND = "post_restart_runtime_readiness_policy"
EXPECTED_PHASE = 163
EXPECTED_BACKLOG_ID = "P0-BB-027"
DEFAULT_POLICY_PATH = Path("runtime") / "post_restart_runtime_readiness_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "post-restart-runtime-readiness" / "phase163"


class PostRestartRuntimeReadinessStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class PostRestartRuntimeReadinessDecision(str, Enum):
    READY_AFTER_RESTART = "ready_after_restart"
    BLOCKED_AFTER_RESTART = "blocked_after_restart"


@dataclass(frozen=True)
class PostRestartRuntimeReadinessConfig:
    config_root: Path
    output_path: Path | None = None
    health_drift_output_path: Path | None = None
    doctor_output_path: Path | None = None
    session_recovery_output_path: Path | None = None
    policy_path: Path = DEFAULT_POLICY_PATH
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
    timeout_seconds: int = 120


HealthDriftRunner = Callable[[GatewayAnythingLLMHealthDriftConfig], dict[str, Any]]
SessionRecoveryRunner = Callable[[AnythingLLMSessionRecoveryConfig], dict[str, Any]]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"post-restart-runtime-readiness-{utc_timestamp()}.json"


def default_health_drift_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / "gateway-anythingllm-health-drift.json"


def default_doctor_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / "first-time-user-doctor.json"


def default_session_recovery_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / "anythingllm-session-recovery.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_hash(path: Path | None) -> str | None:
    return sha256_file(path) if path is not None and path.is_file() else None


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def object_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def load_policy(config_root: Path, policy_path: Path) -> dict[str, Any]:
    path = resolve_path(config_root, policy_path)
    return read_json(path)


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 163")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if policy.get("required_decision") != PostRestartRuntimeReadinessDecision.READY_AFTER_RESTART.value:
        errors.append("policy.required_decision must be ready_after_restart")
    required_sources = policy.get("required_source_reports")
    if not isinstance(required_sources, list) or not all(isinstance(item, str) for item in required_sources):
        errors.append("policy.required_source_reports must be a list of strings")
    required_surfaces = policy.get("required_surfaces")
    if not isinstance(required_surfaces, list) or not all(isinstance(item, str) for item in required_surfaces):
        errors.append("policy.required_surfaces must be a list of strings")
    if policy.get("acceptance_marker") != "POST RESTART RUNTIME READINESS PASS":
        errors.append("policy.acceptance_marker must be POST RESTART RUNTIME READINESS PASS")
    return errors


def check_ids(doctor_report: dict[str, Any], *, status: str | None = None) -> set[str]:
    checks = object_list(doctor_report.get("checks"))
    if status is None:
        return {str(item.get("id") or "") for item in checks}
    return {str(item.get("id") or "") for item in checks if item.get("status") == status}


def session_surfaces(session_report: dict[str, Any]) -> set[str]:
    cases = object_list(session_report.get("cases"))
    surfaces: set[str] = set()
    if any(item.get("surface") == "direct_controller" and item.get("status") == "passed" for item in cases):
        surfaces.add("session.direct_controller")
    if any(item.get("surface") == "anythingllm" and item.get("status") == "passed" for item in cases):
        surfaces.add("session.anythingllm")
    return surfaces


def covered_surfaces(doctor_report: dict[str, Any], session_report: dict[str, Any]) -> set[str]:
    return check_ids(doctor_report, status="passed") | session_surfaces(session_report)


def source_artifact(name: str, path: Path | None, report: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "path": str(path.resolve()) if path else None,
        "sha256": artifact_hash(path),
        "kind": report.get("kind"),
        "phase": report.get("phase"),
        "status": report.get("status"),
        "summary": report.get("summary"),
    }


def validate_source_reports(
    *,
    policy: dict[str, Any],
    doctor_report: dict[str, Any],
    health_drift_report: dict[str, Any],
    session_recovery_report: dict[str, Any],
    doctor_report_path: Path | None,
) -> list[str]:
    errors: list[str] = []
    required_source_reports = set(policy.get("required_source_reports") or [])
    source_kinds = {
        str(doctor_report.get("kind") or ""),
        str(health_drift_report.get("kind") or ""),
        str(session_recovery_report.get("kind") or ""),
    }
    missing_source_reports = sorted(required_source_reports - source_kinds)
    if missing_source_reports:
        errors.append("missing required source reports: " + ", ".join(missing_source_reports))

    if doctor_report.get("status") != "passed":
        errors.append("first-time user doctor did not pass")
    if health_drift_report.get("status") != "passed":
        errors.append("gateway/AnythingLLM health drift guard did not pass")
    if session_recovery_report.get("status") != "passed":
        errors.append("AnythingLLM session recovery did not pass")

    health_summary = object_dict(health_drift_report.get("summary"))
    if health_summary.get("finding_count") != 0:
        errors.append("gateway/AnythingLLM health drift findings must be zero")
    if health_summary.get("failed_check_count") != 0:
        errors.append("health drift source failed_check_count must be zero")

    doctor_summary = object_dict(doctor_report.get("summary"))
    failed_check_ids = doctor_summary.get("failed_check_ids")
    if failed_check_ids:
        errors.append("first-time user doctor failed checks: " + ", ".join(str(item) for item in failed_check_ids))
    allowed_warning_ids = set(policy.get("allowed_warning_check_ids") or [])
    unexpected_warning_ids = sorted(check_ids(doctor_report, status="warning") - allowed_warning_ids)
    if unexpected_warning_ids:
        errors.append("unexpected doctor warnings: " + ", ".join(unexpected_warning_ids))

    session_summary = object_dict(session_recovery_report.get("summary"))
    if session_summary.get("failed_case_count") != 0:
        errors.append("session recovery failed cases must be zero")
    if session_summary.get("blocker_finding_count") != 0:
        errors.append("session recovery blocker findings must be zero")
    if int(session_summary.get("direct_controller_case_count") or 0) < 1:
        errors.append("session recovery must include a direct_controller case")
    if int(session_summary.get("anythingllm_case_count") or 0) < 1:
        errors.append("session recovery must include a live AnythingLLM case")
    if object_dict(session_recovery_report.get("anythingllm_preflight")).get("status") != "passed":
        errors.append("AnythingLLM preflight must pass")

    health_doctor_path = health_drift_report.get("doctor_report_path")
    if doctor_report_path and health_doctor_path and str(doctor_report_path.resolve()) != str(resolve_path(doctor_report_path.parent, health_doctor_path).resolve()):
        errors.append("health drift doctor_report_path does not match the source doctor report")
    return errors


def build_post_restart_runtime_readiness_report(
    *,
    policy: dict[str, Any],
    doctor_report: dict[str, Any],
    health_drift_report: dict[str, Any],
    session_recovery_report: dict[str, Any],
    policy_path: Path | None = None,
    doctor_report_path: Path | None = None,
    health_drift_report_path: Path | None = None,
    session_recovery_report_path: Path | None = None,
) -> dict[str, Any]:
    errors = validate_policy(policy)
    errors.extend(
        validate_source_reports(
            policy=policy,
            doctor_report=doctor_report,
            health_drift_report=health_drift_report,
            session_recovery_report=session_recovery_report,
            doctor_report_path=doctor_report_path,
        )
    )
    required_surfaces = set(policy.get("required_surfaces") or [])
    covered = covered_surfaces(doctor_report, session_recovery_report)
    missing_surfaces = sorted(required_surfaces - covered)
    if missing_surfaces:
        errors.append("missing required restart surfaces: " + ", ".join(missing_surfaces))

    status = PostRestartRuntimeReadinessStatus.FAILED.value if errors else PostRestartRuntimeReadinessStatus.PASSED.value
    decision = (
        PostRestartRuntimeReadinessDecision.READY_AFTER_RESTART.value
        if status == PostRestartRuntimeReadinessStatus.PASSED.value
        else PostRestartRuntimeReadinessDecision.BLOCKED_AFTER_RESTART.value
    )
    next_action = (
        "continue founder testing on the stable path; work approved Phase 177 Priority 0 repair next"
        if not errors
        else "fix restart readiness findings before founder testing"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": status,
        "decision": decision,
        "generated_at": utc_timestamp(),
        "policy_path": str(policy_path.resolve()) if policy_path else None,
        "policy_sha256": artifact_hash(policy_path),
        "source_artifacts": [
            source_artifact("first_time_user_doctor", doctor_report_path, doctor_report),
            source_artifact("gateway_anythingllm_health_drift", health_drift_report_path, health_drift_report),
            source_artifact("anythingllm_session_recovery", session_recovery_report_path, session_recovery_report),
        ],
        "required_surfaces": sorted(required_surfaces),
        "covered_surfaces": sorted(covered),
        "missing_required_surfaces": missing_surfaces,
        "summary": {
            "decision": decision,
            "required_surface_count": len(required_surfaces),
            "covered_surface_count": len(covered & required_surfaces),
            "missing_required_surface_count": len(missing_surfaces),
            "source_report_count": 3,
            "failed_source_report_count": sum(
                1
                for report in (doctor_report, health_drift_report, session_recovery_report)
                if report.get("status") != "passed"
            ),
            "health_drift_finding_count": object_dict(health_drift_report.get("summary")).get("finding_count"),
            "session_recovery_blocker_finding_count": object_dict(session_recovery_report.get("summary")).get(
                "blocker_finding_count"
            ),
            "validation_error_count": len(errors),
            "next_action": next_action,
        },
        "errors": errors,
    }


def validate_post_restart_runtime_readiness_report(
    report: dict[str, Any],
    *,
    policy: dict[str, Any],
    doctor_report: dict[str, Any],
    health_drift_report: dict[str, Any],
    session_recovery_report: dict[str, Any],
    policy_path: Path | None = None,
    doctor_report_path: Path | None = None,
    health_drift_report_path: Path | None = None,
    session_recovery_report_path: Path | None = None,
) -> list[str]:
    expected = build_post_restart_runtime_readiness_report(
        policy=policy,
        doctor_report=doctor_report,
        health_drift_report=health_drift_report,
        session_recovery_report=session_recovery_report,
        policy_path=policy_path,
        doctor_report_path=doctor_report_path,
        health_drift_report_path=health_drift_report_path,
        session_recovery_report_path=session_recovery_report_path,
    )
    errors: list[str] = []
    for key in (
        "schema_version",
        "kind",
        "phase",
        "priority_backlog_id",
        "status",
        "decision",
        "policy_path",
        "policy_sha256",
        "source_artifacts",
        "required_surfaces",
        "covered_surfaces",
        "missing_required_surfaces",
        "summary",
        "errors",
    ):
        if report.get(key) != expected.get(key):
            errors.append(f"report.{key} must match rebuilt post-restart runtime readiness report")
    return errors


def health_drift_config_from_readiness_config(config: PostRestartRuntimeReadinessConfig) -> GatewayAnythingLLMHealthDriftConfig:
    config_root = config.config_root.resolve()
    return GatewayAnythingLLMHealthDriftConfig(
        config_root=config_root,
        output_path=config.health_drift_output_path or default_health_drift_report_path(config_root),
        doctor_output_path=config.doctor_output_path or default_doctor_report_path(config_root),
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
        timeout_seconds=config.timeout_seconds,
    )


def session_recovery_config_from_readiness_config(
    config: PostRestartRuntimeReadinessConfig,
) -> AnythingLLMSessionRecoveryConfig:
    config_root = config.config_root.resolve()
    return AnythingLLMSessionRecoveryConfig(
        config_root=config_root,
        output_path=config.session_recovery_output_path or default_session_recovery_report_path(config_root),
        anythingllm_api_base_url=config.anythingllm_api_base_url,
        workspace=config.workspace,
        api_key_env=config.api_key_env,
        timeout_seconds=config.timeout_seconds,
        include_live_anythingllm=True,
    )


def run_post_restart_runtime_readiness(
    config: PostRestartRuntimeReadinessConfig,
    *,
    health_drift_runner: HealthDriftRunner = run_gateway_anythingllm_health_drift_guard,
    session_recovery_runner: SessionRecoveryRunner = run_anythingllm_session_recovery,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json(policy_path)

    health_config = health_drift_config_from_readiness_config(config)
    health_drift_report = health_drift_runner(health_config)
    health_drift_report_path = resolve_path(config_root, health_drift_report.get("report_path") or health_config.output_path)
    doctor_report_path = resolve_path(
        config_root,
        health_drift_report.get("doctor_report_path") or health_config.doctor_output_path,
    )
    doctor_report = read_json(doctor_report_path)

    session_config = session_recovery_config_from_readiness_config(config)
    session_recovery_report = session_recovery_runner(session_config)
    session_recovery_report_path = resolve_path(config_root, session_config.output_path or default_session_recovery_report_path(config_root))

    report = build_post_restart_runtime_readiness_report(
        policy=policy,
        doctor_report=doctor_report,
        health_drift_report=health_drift_report,
        session_recovery_report=session_recovery_report,
        policy_path=policy_path,
        doctor_report_path=doctor_report_path,
        health_drift_report_path=health_drift_report_path,
        session_recovery_report_path=session_recovery_report_path,
    )
    validation_errors = validate_post_restart_runtime_readiness_report(
        report,
        policy=policy,
        doctor_report=doctor_report,
        health_drift_report=health_drift_report,
        session_recovery_report=session_recovery_report,
        policy_path=policy_path,
        doctor_report_path=doctor_report_path,
        health_drift_report_path=health_drift_report_path,
        session_recovery_report_path=session_recovery_report_path,
    )
    if validation_errors:
        report["status"] = PostRestartRuntimeReadinessStatus.FAILED.value
        report["decision"] = PostRestartRuntimeReadinessDecision.BLOCKED_AFTER_RESTART.value
        report["errors"] = list(report.get("errors") or []) + validation_errors
        report["summary"]["decision"] = report["decision"]
        report["summary"]["validation_error_count"] = len(report["errors"])
        report["summary"]["next_action"] = "fix restart readiness findings before founder testing"

    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
