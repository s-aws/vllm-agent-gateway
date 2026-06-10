"""AnythingLLM session recovery and greeting smoke validation."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.controller_service.server import (
    ControllerServiceConfig,
    handle_workflow_router_chat_completion,
)


SCHEMA_VERSION = 1
EXPECTED_REPORT_KIND = "anythingllm_session_recovery_report"
EXPECTED_PHASE = 140
EXPECTED_BACKLOG_ID = "P0-BB-020"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "anythingllm-session-recovery" / "phase140"
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
FORBIDDEN_REPOSITORY_WORKFLOW_MARKERS = (
    "Selected workflow: code_investigation.plan",
    "Selected workflow: code_context.lookup",
    "Selected workflow: task.decompose",
    "selected_workflow: code_investigation.plan",
    "selected_workflow: code_context.lookup",
    "selected_workflow: task.decompose",
    "code_investigation.plan completed",
    "code_context.lookup completed",
    "task.decompose completed",
    "Artifacts:",
)
REQUIRED_GREETING_MARKERS = (
    "general_chat_no_target",
    "Selected workflow: none",
    "include an allowed target_root path",
)


class AnythingLLMSessionRecoveryStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class AnythingLLMSessionRecoveryConfig:
    config_root: Path
    output_path: Path | None = None
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 120
    include_live_anythingllm: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"anythingllm-session-recovery-{utc_timestamp()}.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def json_request(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: int,
) -> tuple[int, dict[str, Any]]:
    request_headers = dict(headers or {})
    data = None
    method = "GET"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body_text = response.read().decode("utf-8")
            try:
                body = json.loads(body_text)
            except json.JSONDecodeError:
                body = {"text": body_text}
            return response.status, body
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(body_text)
        except json.JSONDecodeError:
            body = {"error": {"message": body_text, "code": "invalid_json_error_body"}}
        return exc.code, body


def text_response(body: dict[str, Any]) -> str:
    for key in ("textResponse", "response", "message", "text"):
        value = body.get(key)
        if isinstance(value, str):
            return value
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
    return ""


def classify_greeting_text(text: str, *, http_status: int | None = 200) -> tuple[str, list[dict[str, str]]]:
    findings: list[dict[str, str]] = []
    if http_status != 200:
        findings.append({"severity": "blocker", "code": "http_status_not_ok", "message": f"HTTP status was {http_status}."})
    if not text.strip():
        findings.append({"severity": "blocker", "code": "missing_text", "message": "Greeting response text is empty."})
    if len(text) > 2500:
        findings.append({"severity": "blocker", "code": "unbounded_text", "message": "Greeting response is too long."})
    for marker in REQUIRED_GREETING_MARKERS:
        if marker not in text:
            findings.append(
                {
                    "severity": "blocker",
                    "code": "missing_greeting_marker",
                    "message": f"Greeting response is missing marker {marker}.",
                }
            )
    for marker in FORBIDDEN_REPOSITORY_WORKFLOW_MARKERS:
        if marker in text:
            findings.append(
                {
                    "severity": "blocker",
                    "code": "repository_workflow_triggered",
                    "message": f"Greeting response included repository workflow marker {marker}.",
                }
            )
    return ("passed" if not findings else "failed"), findings


def direct_greeting_case(config: AnythingLLMSessionRecoveryConfig, *, case_id: str, messages: list[dict[str, str]]) -> dict[str, Any]:
    service_config = ControllerServiceConfig(
        config_root=config.config_root,
        output_root=config.config_root / DEFAULT_OUTPUT_DIR / "direct-controller-artifacts",
        allowed_target_roots=(),
        port=0,
    )
    body = handle_workflow_router_chat_completion(
        {"model": "agentic-workflow-router", "messages": messages},
        service_config,
    )
    text = text_response(body)
    status, findings = classify_greeting_text(text)
    return {
        "case_id": case_id,
        "surface": "direct_controller",
        "status": status,
        "http_status": 200,
        "text_sample": text[:1200],
        "finding_count": len(findings),
        "findings": findings,
    }


def anythingllm_preflight(config: AnythingLLMSessionRecoveryConfig, api_key: str) -> dict[str, Any]:
    base_url = config.anythingllm_api_base_url.rstrip("/")
    ping_status, ping_body = json_request(f"{base_url}/api/ping", timeout_seconds=min(30, config.timeout_seconds))
    workspace_status, workspace_body = json_request(
        f"{base_url}/api/v1/workspaces",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=min(30, config.timeout_seconds),
    )
    workspaces = workspace_body.get("workspaces") if isinstance(workspace_body, dict) else []
    slugs = [item.get("slug") for item in workspaces if isinstance(item, dict)]
    return {
        "status": "passed" if ping_status == 200 and workspace_status == 200 and config.workspace in slugs else "failed",
        "ping_status": ping_status,
        "workspace_status": workspace_status,
        "workspace": config.workspace,
        "workspace_found": config.workspace in slugs,
        "ping": ping_body,
    }


def anythingllm_greeting_case(
    config: AnythingLLMSessionRecoveryConfig,
    *,
    api_key: str,
    case_id: str,
    message: str,
    session_id: str,
) -> dict[str, Any]:
    status_code, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={"message": message, "mode": "chat", "sessionId": session_id},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=config.timeout_seconds,
    )
    text = text_response(body)
    status, findings = classify_greeting_text(text, http_status=status_code)
    return {
        "case_id": case_id,
        "surface": "anythingllm",
        "status": status,
        "http_status": status_code,
        "session_id": session_id,
        "text_sample": text[:1200],
        "finding_count": len(findings),
        "findings": findings,
    }


def build_report_from_cases(
    *,
    cases: list[dict[str, Any]],
    anythingllm_preflight_result: dict[str, Any] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    current_errors = list(errors or [])
    if anythingllm_preflight_result and anythingllm_preflight_result.get("status") != "passed":
        current_errors.append("AnythingLLM preflight failed")
    failed = sum(1 for case in cases if case.get("status") != "passed")
    blocker_findings = sum(
        1
        for case in cases
        for finding in case.get("findings", [])
        if isinstance(finding, dict) and finding.get("severity") == "blocker"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": AnythingLLMSessionRecoveryStatus.PASSED.value
        if failed == 0 and blocker_findings == 0 and not current_errors
        else AnythingLLMSessionRecoveryStatus.FAILED.value,
        "generated_at": utc_timestamp(),
        "anythingllm_preflight": anythingllm_preflight_result or {},
        "cases": cases,
        "summary": {
            "case_count": len(cases),
            "passed_case_count": len(cases) - failed,
            "failed_case_count": failed,
            "blocker_finding_count": blocker_findings,
            "direct_controller_case_count": sum(1 for case in cases if case.get("surface") == "direct_controller"),
            "anythingllm_case_count": sum(1 for case in cases if case.get("surface") == "anythingllm"),
        },
        "errors": current_errors,
    }


def validate_anythingllm_session_recovery_report(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append("report.schema_version must be 1")
    if report.get("kind") != EXPECTED_REPORT_KIND:
        errors.append(f"report.kind must be {EXPECTED_REPORT_KIND}")
    if report.get("phase") != EXPECTED_PHASE:
        errors.append("report.phase must be 140")
    if report.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"report.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    cases = report.get("cases") if isinstance(report.get("cases"), list) else []
    rebuilt = build_report_from_cases(
        cases=[case for case in cases if isinstance(case, dict)],
        anythingllm_preflight_result=report.get("anythingllm_preflight")
        if isinstance(report.get("anythingllm_preflight"), dict)
        else {},
        errors=report.get("errors") if isinstance(report.get("errors"), list) else [],
    )
    for key in ("status", "summary"):
        if report.get(key) != rebuilt.get(key):
            errors.append(f"report.{key} must match rebuilt AnythingLLM session recovery report")
    if not any(isinstance(case, dict) and case.get("surface") == "direct_controller" for case in cases):
        errors.append("report must include at least one direct_controller case")
    if report.get("anythingllm_preflight") and not any(
        isinstance(case, dict) and case.get("surface") == "anythingllm" for case in cases
    ):
        errors.append("report must include AnythingLLM cases when preflight is present")
    return errors


def run_anythingllm_session_recovery(config: AnythingLLMSessionRecoveryConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    cases = [
        direct_greeting_case(config, case_id="DIRECT-HI", messages=[{"role": "user", "content": "hi"}]),
        direct_greeting_case(
            config,
            case_id="DIRECT-STALE-HISTORY-HI",
            messages=[
                {
                    "role": "user",
                    "content": (
                        "In /mnt/c/coinbase_testing_repo_frozen_tmp.github, explain what "
                        "find_stealth_order_by_placed_order_id does. Read only."
                    ),
                },
                {"role": "assistant", "content": "prior run_id: workflow-router-old"},
                {"role": "user", "content": "hi"},
            ],
        ),
    ]
    preflight: dict[str, Any] = {}
    errors: list[str] = []
    if config.include_live_anythingllm:
        api_key = os.environ.get(config.api_key_env)
        if not api_key:
            errors.append(f"{config.api_key_env} is required for live AnythingLLM validation")
        else:
            preflight = anythingllm_preflight(config, api_key)
            session_id = f"phase140-greeting-{uuid.uuid4().hex}"
            if preflight.get("status") == "passed":
                cases.append(
                    anythingllm_greeting_case(
                        config,
                        api_key=api_key,
                        case_id="ANYTHINGLLM-HI",
                        message="hi",
                        session_id=session_id,
                    )
                )
                cases.append(
                    anythingllm_greeting_case(
                        config,
                        api_key=api_key,
                        case_id="ANYTHINGLLM-HELLO-SAME-SESSION",
                        message="hello there",
                        session_id=session_id,
                    )
                )
    report = build_report_from_cases(cases=cases, anythingllm_preflight_result=preflight, errors=errors)
    validation_errors = validate_anythingllm_session_recovery_report(report)
    if validation_errors:
        report["status"] = AnythingLLMSessionRecoveryStatus.FAILED.value
        report["errors"] = report["errors"] + validation_errors
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    write_json(output_path, report)
    return report
