"""Phase 231 runtime recovery reliability rebaseline gate."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "runtime_recovery_reliability_rebaseline_policy"
EXPECTED_REPORT_KIND = "runtime_recovery_reliability_rebaseline_report"
EXPECTED_RESTART_KIND = "runtime_recovery_restart_evidence"
EXPECTED_PHASE = 231
EXPECTED_BACKLOG_ID = "P0-M13-231"
EXPECTED_MILESTONE_IDS = {"M13"}
DEFAULT_POLICY_PATH = Path("runtime") / "runtime_recovery_reliability_rebaseline_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "phase231"
DEFAULT_OUTPUT_PATH = DEFAULT_OUTPUT_DIR / "phase231-runtime-recovery-reliability-rebaseline-report.json"
DEFAULT_RESTART_EVIDENCE_PATH = DEFAULT_OUTPUT_DIR / "phase231-restart-evidence.json"
DEFAULT_POST_RESTART_OUTPUT_PATH = DEFAULT_OUTPUT_DIR / "phase231-post-restart-runtime-readiness-report.json"
DEFAULT_HEALTH_DRIFT_OUTPUT_PATH = DEFAULT_OUTPUT_DIR / "phase231-health-drift-report.json"
DEFAULT_DOCTOR_OUTPUT_PATH = DEFAULT_OUTPUT_DIR / "phase231-first-time-user-doctor.json"
DEFAULT_SESSION_RECOVERY_OUTPUT_PATH = DEFAULT_OUTPUT_DIR / "phase231-session-recovery-report.json"
DEFAULT_SMALL_REPO_OUTPUT_PATH = DEFAULT_OUTPUT_DIR / "phase231-small-repo-live-report.json"
DEFAULT_LARGE_CONTEXT_OUTPUT_PATH = DEFAULT_OUTPUT_DIR / "phase231-large-context-live-report.json"
DEFAULT_LARGE_CONTEXT_MARKDOWN_PATH = DEFAULT_OUTPUT_DIR / "phase231-large-context-live-report.md"
DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_MODEL_BASE_URL = "http://127.0.0.1:8000/v1"


class RuntimeRecoveryRebaselineStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class RuntimeRecoveryRebaselineDecision(str, Enum):
    READY_AFTER_RECOVERY = "ready_after_recovery"
    BLOCKED_AFTER_RECOVERY = "blocked_after_recovery"


@dataclass(frozen=True)
class RuntimeRecoveryRebaselineConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    restart_evidence_path: Path = DEFAULT_RESTART_EVIDENCE_PATH
    post_restart_output_path: Path = DEFAULT_POST_RESTART_OUTPUT_PATH
    health_drift_output_path: Path = DEFAULT_HEALTH_DRIFT_OUTPUT_PATH
    doctor_output_path: Path = DEFAULT_DOCTOR_OUTPUT_PATH
    session_recovery_output_path: Path = DEFAULT_SESSION_RECOVERY_OUTPUT_PATH
    small_repo_output_path: Path = DEFAULT_SMALL_REPO_OUTPUT_PATH
    large_context_output_path: Path = DEFAULT_LARGE_CONTEXT_OUTPUT_PATH
    large_context_markdown_path: Path = DEFAULT_LARGE_CONTEXT_MARKDOWN_PATH
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    timeout_seconds: int = 900
    restart_managed_stack: bool = False
    restart_vllm_container: str | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object at {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_hash(path: Path | None) -> str | None:
    return sha256_file(path) if path is not None and path.is_file() else None


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def validation_error(error_id: str, message: str, *, severity: str = "high") -> dict[str, str]:
    return {"id": error_id, "severity": severity, "message": message}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "phase must be 231"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be exactly M13"))
    if policy.get("required_decision") != RuntimeRecoveryRebaselineDecision.READY_AFTER_RECOVERY.value:
        errors.append(validation_error("policy.required_decision", "required_decision must be ready_after_recovery"))
    for key in ("required_source_reports", "required_surfaces", "small_repo_live_case_ids", "large_context_live_case_ids"):
        if not string_list(policy.get(key)):
            errors.append(validation_error(f"policy.{key}", f"{key} must be a non-empty list of strings"))
    requirements = dict_value(policy.get("restart_requirements"))
    expected_requirements = {
        "repo_managed_stack_restart_required": True,
        "vllm_restart_required_when_container_available": True,
        "anythingllm_restart_is_operator_owned": True,
        "anythingllm_new_session_required": True,
    }
    for key, expected in expected_requirements.items():
        if requirements.get(key) is not expected:
            errors.append(validation_error(f"policy.restart_requirements.{key}", f"{key} must be {expected}"))
    if policy.get("acceptance_marker") != "PHASE231 RUNTIME RECOVERY RELIABILITY REBASELINE PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 231"))
    return errors


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


def report_status_passed(report: dict[str, Any]) -> bool:
    return report.get("status") == RuntimeRecoveryRebaselineStatus.PASSED.value


def restart_component_status(restart_evidence: dict[str, Any], component: str) -> str:
    for item in object_list(restart_evidence.get("components")):
        if item.get("component") == component:
            return str(item.get("status") or "")
    return "missing"


def covered_small_repo_surfaces(small_repo_report: dict[str, Any]) -> set[str]:
    surfaces: set[str] = set()
    for case in object_list(small_repo_report.get("cases")):
        if case.get("status") != "passed":
            continue
        client = case.get("client")
        if client in {"gateway", "anythingllm"}:
            surfaces.add(f"small_repo.{client}")
    return surfaces


def covered_large_context_surfaces(large_context_report: dict[str, Any]) -> set[str]:
    surfaces: set[str] = set()
    for response in object_list(large_context_report.get("responses")):
        if response.get("status") != "passed":
            continue
        surface = response.get("surface")
        if surface in {"gateway", "anythingllm"}:
            surfaces.add(f"large_context.{surface}")
    return surfaces


def restart_surfaces(restart_evidence: dict[str, Any]) -> set[str]:
    surfaces: set[str] = set()
    if restart_component_status(restart_evidence, "managed_stack") == "passed":
        surfaces.add("restart.managed_stack")
    if restart_component_status(restart_evidence, "vllm_model") == "passed":
        surfaces.add("restart.vllm_model")
    return surfaces


def validate_restart_evidence(policy: dict[str, Any], restart_evidence: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if restart_evidence.get("kind") != EXPECTED_RESTART_KIND:
        errors.append(validation_error("restart.kind", f"restart evidence kind must be {EXPECTED_RESTART_KIND}"))
    if restart_evidence.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("restart.phase", "restart evidence phase must be 231"))
    if restart_evidence.get("status") != "passed":
        errors.append(validation_error("restart.status", "restart evidence must pass"))
    requirements = dict_value(policy.get("restart_requirements"))
    if requirements.get("repo_managed_stack_restart_required") is True and restart_component_status(restart_evidence, "managed_stack") != "passed":
        errors.append(validation_error("restart.managed_stack", "managed gateway/proxy/controller stack restart must pass"))
    if requirements.get("vllm_restart_required_when_container_available") is True:
        vllm_status = restart_component_status(restart_evidence, "vllm_model")
        if vllm_status != "passed":
            errors.append(validation_error("restart.vllm_model", "vLLM model restart must pass when the container is available"))
    return errors


def validate_post_restart_report(post_restart_report: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if post_restart_report.get("kind") != "post_restart_runtime_readiness_report":
        errors.append(validation_error("post_restart.kind", "post-restart readiness report kind mismatch"))
    if post_restart_report.get("status") != "passed":
        errors.append(validation_error("post_restart.status", "post-restart readiness must pass"))
    if post_restart_report.get("decision") != "ready_after_restart":
        errors.append(validation_error("post_restart.decision", "post-restart decision must be ready_after_restart"))
    summary = dict_value(post_restart_report.get("summary"))
    if summary.get("missing_required_surface_count") != 0:
        errors.append(validation_error("post_restart.missing_surfaces", "post-restart readiness must have zero missing surfaces"))
    return errors


def validate_small_repo_report(policy: dict[str, Any], small_repo_report: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if small_repo_report.get("kind") != "multi_repo_fixture_live_report":
        errors.append(validation_error("small_repo.kind", "small repo proof must be a multi_repo_fixture_live_report"))
    if small_repo_report.get("status") != "passed":
        errors.append(validation_error("small_repo.status", "small repo live proof must pass"))
    summary = dict_value(small_repo_report.get("summary"))
    clients = set(string_list(summary.get("clients")))
    if not {"gateway", "anythingllm"}.issubset(clients):
        errors.append(validation_error("small_repo.clients", "small repo proof must include gateway and AnythingLLM clients"))
    case_ids = {str(item.get("case_id") or "") for item in object_list(small_repo_report.get("cases")) if item.get("status") == "passed"}
    missing_cases = sorted(set(string_list(policy.get("small_repo_live_case_ids"))) - case_ids)
    if missing_cases:
        errors.append(validation_error("small_repo.case_ids", "missing small repo case(s): " + ", ".join(missing_cases)))
    return errors


def validate_large_context_report(policy: dict[str, Any], large_context_report: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if large_context_report.get("kind") != "large_context_usability_live_closeout_report":
        errors.append(validation_error("large_context.kind", "large context proof must be a large_context_usability_live_closeout_report"))
    if large_context_report.get("status") != "passed":
        errors.append(validation_error("large_context.status", "large context live proof must pass"))
    if large_context_report.get("live") is not True:
        errors.append(validation_error("large_context.live", "large context proof must be live"))
    summary = dict_value(large_context_report.get("summary"))
    if summary.get("failed_response_count") != 0:
        errors.append(validation_error("large_context.failed_responses", "large context failed_response_count must be zero"))
    response_case_ids = {
        str(item.get("case_id") or "")
        for item in object_list(large_context_report.get("responses"))
        if item.get("status") == "passed"
    }
    missing_cases = sorted(set(string_list(policy.get("large_context_live_case_ids"))) - response_case_ids)
    if missing_cases:
        errors.append(validation_error("large_context.case_ids", "missing large-context case(s): " + ", ".join(missing_cases)))
    surfaces = covered_large_context_surfaces(large_context_report)
    if not {"large_context.gateway", "large_context.anythingllm"}.issubset(surfaces):
        errors.append(validation_error("large_context.surfaces", "large context proof must include gateway and AnythingLLM surfaces"))
    return errors


def covered_surfaces(
    *,
    restart_evidence: dict[str, Any],
    post_restart_report: dict[str, Any],
    small_repo_report: dict[str, Any],
    large_context_report: dict[str, Any],
) -> set[str]:
    surfaces = set()
    surfaces.update(restart_surfaces(restart_evidence))
    if post_restart_report.get("status") == "passed":
        surfaces.add("post_restart.readiness")
    surfaces.update(covered_small_repo_surfaces(small_repo_report))
    surfaces.update(covered_large_context_surfaces(large_context_report))
    return surfaces


def build_runtime_recovery_rebaseline_report(
    *,
    policy: dict[str, Any],
    restart_evidence: dict[str, Any],
    post_restart_report: dict[str, Any],
    small_repo_report: dict[str, Any],
    large_context_report: dict[str, Any],
    policy_path: Path | None = None,
    restart_evidence_path: Path | None = None,
    post_restart_report_path: Path | None = None,
    small_repo_report_path: Path | None = None,
    large_context_report_path: Path | None = None,
) -> dict[str, Any]:
    errors = validate_policy(policy)
    errors.extend(validate_restart_evidence(policy, restart_evidence))
    errors.extend(validate_post_restart_report(post_restart_report))
    errors.extend(validate_small_repo_report(policy, small_repo_report))
    errors.extend(validate_large_context_report(policy, large_context_report))
    required_surfaces = set(string_list(policy.get("required_surfaces")))
    covered = covered_surfaces(
        restart_evidence=restart_evidence,
        post_restart_report=post_restart_report,
        small_repo_report=small_repo_report,
        large_context_report=large_context_report,
    )
    missing_surfaces = sorted(required_surfaces - covered)
    if missing_surfaces:
        errors.append(validation_error("required_surfaces.missing", "missing required surfaces: " + ", ".join(missing_surfaces)))
    status = RuntimeRecoveryRebaselineStatus.FAILED.value if errors else RuntimeRecoveryRebaselineStatus.PASSED.value
    decision = (
        RuntimeRecoveryRebaselineDecision.READY_AFTER_RECOVERY.value
        if status == RuntimeRecoveryRebaselineStatus.PASSED.value
        else RuntimeRecoveryRebaselineDecision.BLOCKED_AFTER_RECOVERY.value
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": sorted(EXPECTED_MILESTONE_IDS),
        "generated_at": utc_timestamp(),
        "status": status,
        "decision": decision,
        "policy_path": str(policy_path.resolve()) if policy_path else None,
        "policy_sha256": artifact_hash(policy_path),
        "source_artifacts": [
            source_artifact("restart_evidence", restart_evidence_path, restart_evidence),
            source_artifact("post_restart_runtime_readiness", post_restart_report_path, post_restart_report),
            source_artifact("small_repo_live_prompt", small_repo_report_path, small_repo_report),
            source_artifact("large_context_live_prompt", large_context_report_path, large_context_report),
        ],
        "required_surfaces": sorted(required_surfaces),
        "covered_surfaces": sorted(covered),
        "missing_required_surfaces": missing_surfaces,
        "validation_errors": errors,
        "summary": {
            "decision": decision,
            "required_surface_count": len(required_surfaces),
            "covered_surface_count": len(covered & required_surfaces),
            "missing_required_surface_count": len(missing_surfaces),
            "source_report_count": 4,
            "failed_source_report_count": sum(
                1
                for report in (restart_evidence, post_restart_report, small_repo_report, large_context_report)
                if report.get("status") != "passed"
            ),
            "small_repo_client_count": len(set(string_list(dict_value(small_repo_report.get("summary")).get("clients")))),
            "large_context_response_count": dict_value(large_context_report.get("summary")).get("response_count"),
            "validation_error_count": len(errors),
            "phase232_ready": not errors,
            "next_action": "work approved Phase 232 onboarding and release handoff refresh" if not errors else "repair runtime recovery proof",
        },
    }


def stable_report(value: dict[str, Any]) -> dict[str, Any]:
    stable = json.loads(json.dumps(value))
    stable.pop("generated_at", None)
    stable.pop("report_path", None)
    return stable


def validate_runtime_recovery_rebaseline_report(
    report: dict[str, Any],
    *,
    policy: dict[str, Any],
    restart_evidence: dict[str, Any],
    post_restart_report: dict[str, Any],
    small_repo_report: dict[str, Any],
    large_context_report: dict[str, Any],
    policy_path: Path | None = None,
    restart_evidence_path: Path | None = None,
    post_restart_report_path: Path | None = None,
    small_repo_report_path: Path | None = None,
    large_context_report_path: Path | None = None,
) -> list[str]:
    expected = build_runtime_recovery_rebaseline_report(
        policy=policy,
        restart_evidence=restart_evidence,
        post_restart_report=post_restart_report,
        small_repo_report=small_repo_report,
        large_context_report=large_context_report,
        policy_path=policy_path,
        restart_evidence_path=restart_evidence_path,
        post_restart_report_path=post_restart_report_path,
        small_repo_report_path=small_repo_report_path,
        large_context_report_path=large_context_report_path,
    )
    errors: list[str] = []
    if stable_report(report) != stable_report(expected):
        errors.append("report must match rebuilt runtime recovery rebaseline report")
    return errors


def tail_text(value: str, limit: int = 4000) -> str:
    return value[-limit:] if len(value) > limit else value


def run_command(command: list[str], *, cwd: Path, timeout_seconds: int, component: str) -> dict[str, Any]:
    started_at = iso_now()
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout_seconds, check=False)
    completed_at = iso_now()
    return {
        "component": component,
        "command": command,
        "started_at": started_at,
        "completed_at": completed_at,
        "returncode": result.returncode,
        "status": "passed" if result.returncode == 0 else "failed",
        "stdout_tail": tail_text(result.stdout),
        "stderr_tail": tail_text(result.stderr),
    }


def json_request(url: str, *, timeout_seconds: int) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(text)
            except json.JSONDecodeError:
                body = {"text": text}
            return response.status, body
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            body = {"error": text}
        return exc.code, body


def wait_for_model(model_base_url: str, *, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    url = model_base_url.rstrip("/") + "/models"
    last_error = ""
    attempts = 0
    while time.monotonic() < deadline:
        attempts += 1
        try:
            status, body = json_request(url, timeout_seconds=min(30, timeout_seconds))
            if status == 200:
                return {"status": "passed", "url": url, "http_status": status, "attempts": attempts, "body": body}
            last_error = f"HTTP {status}: {body}"
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(5)
    return {"status": "failed", "url": url, "attempts": attempts, "error": last_error}


def docker_state(container: str, *, cwd: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["docker", "inspect", container, "--format", "{{json .State}}"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return {"status": "unavailable", "returncode": result.returncode, "stderr_tail": tail_text(result.stderr)}
    try:
        state = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return {"status": "failed", "stdout_tail": tail_text(result.stdout), "stderr_tail": tail_text(result.stderr)}
    return {"status": "passed", "state": state}


def build_restart_evidence(config: RuntimeRecoveryRebaselineConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    commands: list[dict[str, Any]] = []
    components: list[dict[str, Any]] = []
    started_at = iso_now()

    if config.restart_vllm_container:
        before = docker_state(config.restart_vllm_container, cwd=config_root)
        command = run_command(
            ["docker", "restart", config.restart_vllm_container],
            cwd=config_root,
            timeout_seconds=config.timeout_seconds,
            component="vllm_model",
        )
        commands.append(command)
        readiness = wait_for_model(config.model_base_url, timeout_seconds=config.timeout_seconds)
        after = docker_state(config.restart_vllm_container, cwd=config_root)
        components.append(
            {
                "component": "vllm_model",
                "restart_mode": "docker_restart",
                "status": "passed" if command["status"] == "passed" and readiness["status"] == "passed" else "failed",
                "container": config.restart_vllm_container,
                "before": before,
                "after": after,
                "readiness": readiness,
            }
        )
    else:
        components.append(
            {
                "component": "vllm_model",
                "restart_mode": "not_requested",
                "status": "not_restarted",
                "reason": "Pass --restart-vllm-container to prove a model restart in Phase 231.",
            }
        )

    if config.restart_managed_stack:
        command = run_command(
            ["bash", "-lc", "./stop-agent-prompt-proxies.sh && ./start-agent-prompt-proxies.sh"],
            cwd=config_root,
            timeout_seconds=config.timeout_seconds,
            component="managed_stack",
        )
        commands.append(command)
        components.append(
            {
                "component": "managed_stack",
                "restart_mode": "repo_scripts",
                "status": command["status"],
                "script": "stop-agent-prompt-proxies.sh && start-agent-prompt-proxies.sh",
            }
        )
    else:
        components.append(
            {
                "component": "managed_stack",
                "restart_mode": "not_requested",
                "status": "not_restarted",
                "reason": "Pass --restart-managed-stack to prove gateway/proxy/controller restart in Phase 231.",
            }
        )

    failed_components = [item for item in components if item.get("status") != "passed"]
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_RESTART_KIND,
        "phase": EXPECTED_PHASE,
        "generated_at": utc_timestamp(),
        "started_at": started_at,
        "completed_at": iso_now(),
        "status": "failed" if failed_components else "passed",
        "components": components,
        "commands": commands,
        "summary": {
            "component_count": len(components),
            "failed_component_count": len(failed_components),
            "command_count": len(commands),
            "restarted_components": [item["component"] for item in components if item.get("status") == "passed"],
        },
    }
    restart_path = resolve_path(config_root, config.restart_evidence_path)
    write_json(restart_path, report)
    report["report_path"] = str(restart_path.resolve())
    write_json(restart_path, report)
    return report


def run_subprocess_report(command: list[str], *, cwd: Path, output_path: Path, timeout_seconds: int) -> dict[str, Any]:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout_seconds, check=False)
    if result.returncode != 0:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "subprocess_failure_report",
            "status": "failed",
            "command": command,
            "returncode": result.returncode,
            "stdout_tail": tail_text(result.stdout),
            "stderr_tail": tail_text(result.stderr),
            "summary": {"returncode": result.returncode},
        }
    return read_json(output_path)


def run_runtime_recovery_rebaseline(config: RuntimeRecoveryRebaselineConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    policy = read_json(policy_path)
    restart_evidence_path = resolve_path(config_root, config.restart_evidence_path)
    post_restart_output_path = resolve_path(config_root, config.post_restart_output_path)
    small_repo_output_path = resolve_path(config_root, config.small_repo_output_path)
    large_context_output_path = resolve_path(config_root, config.large_context_output_path)
    large_context_markdown_path = resolve_path(config_root, config.large_context_markdown_path)

    restart_evidence = build_restart_evidence(config)

    post_restart_report = run_subprocess_report(
        [
            sys.executable,
            "scripts/validate_post_restart_runtime_readiness.py",
            "--timeout-seconds",
            str(config.timeout_seconds),
            "--output-path",
            str(post_restart_output_path),
            "--health-drift-output-path",
            str(resolve_path(config_root, config.health_drift_output_path)),
            "--doctor-output-path",
            str(resolve_path(config_root, config.doctor_output_path)),
            "--session-recovery-output-path",
            str(resolve_path(config_root, config.session_recovery_output_path)),
            "--workflow-router-gateway-base-url",
            config.workflow_router_gateway_base_url,
            "--anythingllm-api-base-url",
            config.anythingllm_api_base_url,
            "--workspace",
            config.workspace,
            "--api-key-env",
            config.api_key_env,
        ],
        cwd=config_root,
        output_path=post_restart_output_path,
        timeout_seconds=config.timeout_seconds,
    )

    small_command = [
        sys.executable,
        "scripts/validate_multi_repo_fixtures_live.py",
        "--workflow-router-gateway-base-url",
        config.workflow_router_gateway_base_url,
        "--anythingllm-api-base-url",
        config.anythingllm_api_base_url,
        "--workspace",
        config.workspace,
        "--api-key-env",
        config.api_key_env,
        "--timeout-seconds",
        str(config.timeout_seconds),
        "--output-path",
        str(small_repo_output_path),
        "--live-anythingllm",
        "--port-health",
    ]
    for case_id in string_list(policy.get("small_repo_live_case_ids")):
        small_command.extend(["--case-id", case_id])
    small_repo_report = run_subprocess_report(
        small_command,
        cwd=config_root,
        output_path=small_repo_output_path,
        timeout_seconds=config.timeout_seconds,
    )

    large_command = [
        sys.executable,
        "scripts/validate_large_context_usability_live_closeout.py",
        "--live",
        "--allow-partial",
        "--output-path",
        str(large_context_output_path),
        "--markdown-output-path",
        str(large_context_markdown_path),
        "--workflow-router-gateway-base-url",
        config.workflow_router_gateway_base_url,
        "--anythingllm-api-base-url",
        config.anythingllm_api_base_url,
        "--workspace",
        config.workspace,
        "--api-key-env",
        config.api_key_env,
        "--timeout-seconds",
        str(config.timeout_seconds),
    ]
    for case_id in string_list(policy.get("large_context_live_case_ids")):
        large_command.extend(["--case-id", case_id])
    large_context_report = run_subprocess_report(
        large_command,
        cwd=config_root,
        output_path=large_context_output_path,
        timeout_seconds=config.timeout_seconds,
    )

    report = build_runtime_recovery_rebaseline_report(
        policy=policy,
        restart_evidence=restart_evidence,
        post_restart_report=post_restart_report,
        small_repo_report=small_repo_report,
        large_context_report=large_context_report,
        policy_path=policy_path,
        restart_evidence_path=restart_evidence_path,
        post_restart_report_path=post_restart_output_path,
        small_repo_report_path=small_repo_output_path,
        large_context_report_path=large_context_output_path,
    )
    validation_errors = validate_runtime_recovery_rebaseline_report(
        report,
        policy=policy,
        restart_evidence=restart_evidence,
        post_restart_report=post_restart_report,
        small_repo_report=small_repo_report,
        large_context_report=large_context_report,
        policy_path=policy_path,
        restart_evidence_path=restart_evidence_path,
        post_restart_report_path=post_restart_output_path,
        small_repo_report_path=small_repo_output_path,
        large_context_report_path=large_context_output_path,
    )
    if validation_errors:
        report["status"] = RuntimeRecoveryRebaselineStatus.FAILED.value
        report["decision"] = RuntimeRecoveryRebaselineDecision.BLOCKED_AFTER_RECOVERY.value
        report["validation_errors"].extend(validation_error("report.rebuild", item) for item in validation_errors)
        report["summary"]["decision"] = report["decision"]
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
        report["summary"]["phase232_ready"] = False
        report["summary"]["next_action"] = "repair runtime recovery proof"
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
