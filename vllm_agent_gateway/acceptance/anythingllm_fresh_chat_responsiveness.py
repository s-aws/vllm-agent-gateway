"""Phase 237 fresh AnythingLLM chat responsiveness gate."""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.anythingllm_session_recovery import (
    classify_greeting_text,
    text_response,
)
from vllm_agent_gateway.anythingllm_ui_e2e import fixture_state


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "anythingllm_fresh_chat_responsiveness_policy"
EXPECTED_REPORT_KIND = "anythingllm_fresh_chat_responsiveness_report"
EXPECTED_PHASE = 237
EXPECTED_BACKLOG_ID = "P0-M14-237"
DEFAULT_POLICY_PATH = Path("runtime") / "anythingllm_fresh_chat_responsiveness_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "anythingllm-fresh-chat-responsiveness" / "phase237"
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_MODEL = "Qwen3-Coder-30B-A3B-Instruct"
DEFAULT_TARGET_ROOTS = (
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
)
CODE_EXPLANATION_PROMPT = (
    "In /mnt/c/coinbase_testing_repo_frozen_tmp.github, explain what "
    "find_stealth_order_by_placed_order_id does in core/stealth_order_manager.py. "
    "Read only. Include key inputs, outputs, side effects, and tests."
)
GREETING_MESSAGE = "hi"

CODING_REQUIRED_MARKER_GROUPS = (
    ("workflow_router.plan completed",),
    ("selected_workflow: code_investigation.plan", "Selected workflow: code_investigation.plan"),
    ("StealthOrderManager.find_stealth_order_by_placed_order_id", "find_stealth_order_by_placed_order_id"),
    ("Inputs:",),
    ("Outputs:",),
    ("Side effects:",),
    ("Related tests:",),
    ("Source mutation: false",),
)
CODING_FORBIDDEN_MARKERS = (
    "Source mutation: true",
    "selected_workflow: task.decompose",
    "Selected workflow: task.decompose",
    "route_status: general_chat_no_target",
    "Selected workflow: none",
)


class FreshChatStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class FreshChatDecision(str, Enum):
    RESPONSIVE = "fresh_chat_responsive"
    BLOCKED = "fresh_chat_blocked"


@dataclass(frozen=True)
class AnythingLLMFreshChatResponsivenessConfig:
    config_root: Path
    output_path: Path | None = None
    policy_path: Path = DEFAULT_POLICY_PATH
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    model: str = DEFAULT_MODEL
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    target_roots: tuple[str, ...] = DEFAULT_TARGET_ROOTS
    ui_report_path: Path | None = None
    timeout_seconds: int = 180


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"anythingllm-fresh-chat-responsiveness-{utc_timestamp()}.json"


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object at {path}")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
            body_text = response.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(body_text)
            except json.JSONDecodeError:
                body = {"text": body_text}
            return response.status, body if isinstance(body, dict) else {"value": body}
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(body_text)
        except json.JSONDecodeError:
            body = {"error": {"message": body_text, "code": "invalid_json_error_body"}}
        return exc.code, body if isinstance(body, dict) else {"value": body}
    except urllib.error.URLError as exc:
        return 0, {"error": {"message": str(exc), "code": "url_error"}}
    except TimeoutError as exc:
        return 0, {"error": {"message": str(exc), "code": "timeout"}}


def run_id_from_text(text: str) -> str | None:
    match = re.search(r"\brun_id:\s*([A-Za-z0-9_.:-]+)", text)
    return match.group(1) if match else None


def load_policy(config_root: Path, policy_path: Path) -> dict[str, Any]:
    return read_json(resolve_path(config_root, policy_path))


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 237")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if policy.get("required_decision") != FreshChatDecision.RESPONSIVE.value:
        errors.append("policy.required_decision must be fresh_chat_responsive")
    anythingllm = policy.get("required_anythingllm") if isinstance(policy.get("required_anythingllm"), dict) else {}
    if anythingllm.get("api_base_url") != DEFAULT_ANYTHINGLLM_API_BASE_URL:
        errors.append("policy.required_anythingllm.api_base_url must be http://127.0.0.1:3001")
    if anythingllm.get("workflow_router_base_url") != DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL:
        errors.append("policy.required_anythingllm.workflow_router_base_url must be http://127.0.0.1:8500/v1")
    if anythingllm.get("workspace") != DEFAULT_WORKSPACE:
        errors.append("policy.required_anythingllm.workspace must be my-workspace")
    if anythingllm.get("model") != DEFAULT_MODEL:
        errors.append(f"policy.required_anythingllm.model must be {DEFAULT_MODEL}")
    required_cases = policy.get("required_cases")
    if not isinstance(required_cases, list) or not all(isinstance(item, str) for item in required_cases):
        errors.append("policy.required_cases must be a list of strings")
    required_ui_cases = policy.get("required_ui_case_ids")
    if not isinstance(required_ui_cases, list) or not all(isinstance(item, str) for item in required_ui_cases):
        errors.append("policy.required_ui_case_ids must be a list of strings")
    if policy.get("acceptance_marker") != "ANYTHINGLLM FRESH CHAT RESPONSIVENESS PASS":
        errors.append("policy.acceptance_marker must be ANYTHINGLLM FRESH CHAT RESPONSIVENESS PASS")
    return errors


def classify_coding_text(text: str, *, http_status: int | None = 200) -> tuple[str, list[dict[str, str]]]:
    findings: list[dict[str, str]] = []
    if http_status != 200:
        findings.append({"severity": "blocker", "code": "http_status_not_ok", "message": f"HTTP status was {http_status}."})
    if not text.strip():
        findings.append({"severity": "blocker", "code": "missing_text", "message": "Coding response text is empty."})
    if len(text) > 20000:
        findings.append({"severity": "blocker", "code": "unbounded_text", "message": "Coding response is too long."})
    for group in CODING_REQUIRED_MARKER_GROUPS:
        if not any(marker in text for marker in group):
            findings.append(
                {
                    "severity": "blocker",
                    "code": "missing_coding_marker",
                    "message": "Coding response is missing one of: " + ", ".join(group),
                }
            )
    for marker in CODING_FORBIDDEN_MARKERS:
        if marker in text:
            findings.append(
                {
                    "severity": "blocker",
                    "code": "forbidden_coding_marker",
                    "message": f"Coding response included forbidden marker {marker}.",
                }
            )
    return ("passed" if not findings else "failed"), findings


def classify_case_text(case_kind: str, text: str, *, http_status: int | None = 200) -> tuple[str, list[dict[str, str]]]:
    if case_kind == "greeting":
        return classify_greeting_text(text, http_status=http_status)
    if case_kind == "coding":
        return classify_coding_text(text, http_status=http_status)
    return "failed", [{"severity": "blocker", "code": "unknown_case_kind", "message": f"Unknown case kind {case_kind}."}]


def gateway_case(
    config: AnythingLLMFreshChatResponsivenessConfig,
    *,
    case_id: str,
    message: str,
    case_kind: str,
) -> dict[str, Any]:
    status_code, body = json_request(
        f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": config.model,
            "messages": [{"role": "user", "content": message}],
            "stream": False,
        },
        timeout_seconds=config.timeout_seconds,
    )
    text = text_response(body)
    status, findings = classify_case_text(case_kind, text, http_status=status_code)
    return {
        "case_id": case_id,
        "surface": "workflow_router_gateway",
        "case_kind": case_kind,
        "status": status,
        "http_status": status_code,
        "parsed_run_id": run_id_from_text(text),
        "text_sample": text[:2000],
        "text_length": len(text),
        "finding_count": len(findings),
        "findings": findings,
    }


def anythingllm_case(
    config: AnythingLLMFreshChatResponsivenessConfig,
    *,
    api_key: str,
    case_id: str,
    message: str,
    case_kind: str,
    session_id: str,
) -> dict[str, Any]:
    status_code, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={"message": message, "mode": "chat", "sessionId": session_id},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=config.timeout_seconds,
    )
    text = text_response(body)
    status, findings = classify_case_text(case_kind, text, http_status=status_code)
    return {
        "case_id": case_id,
        "surface": "anythingllm_api",
        "case_kind": case_kind,
        "status": status,
        "http_status": status_code,
        "session_id": session_id,
        "parsed_run_id": run_id_from_text(text),
        "text_sample": text[:2000],
        "text_length": len(text),
        "finding_count": len(findings),
        "findings": findings,
    }


def anythingllm_target_settings(
    config: AnythingLLMFreshChatResponsivenessConfig,
    *,
    api_key: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    required = policy.get("required_anythingllm") if isinstance(policy.get("required_anythingllm"), dict) else {}
    status_code, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/system",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=min(30, config.timeout_seconds),
    )
    settings = body.get("settings") if isinstance(body.get("settings"), dict) else {}
    actual = {
        "api_base_url": config.anythingllm_api_base_url,
        "workspace": config.workspace,
        "provider": settings.get("LLMProvider"),
        "model": settings.get("LLMModel"),
        "generic_openai_base_path": settings.get("GenericOpenAiBasePath"),
    }
    checks = {
        "http_status": status_code == 200,
        "api_base_url": actual["api_base_url"] == required.get("api_base_url"),
        "workspace": actual["workspace"] == required.get("workspace"),
        "provider": actual["provider"] == required.get("provider"),
        "model": actual["model"] == required.get("model"),
        "generic_openai_base_path": actual["generic_openai_base_path"] == required.get("workflow_router_base_url"),
    }
    return {
        "status": FreshChatStatus.PASSED.value if all(checks.values()) else FreshChatStatus.FAILED.value,
        "http_status": status_code,
        "actual": actual,
        "required": required,
        "checks": checks,
    }


def summarize_ui_report(path: Path | None, required_case_ids: list[str]) -> dict[str, Any]:
    if path is None:
        return {
            "status": FreshChatStatus.FAILED.value,
            "path": None,
            "errors": ["ui_report_path is required for Phase 237 UI /stream-chat proof"],
        }
    report = read_json(path)
    cases = report.get("ui", {}).get("cases") if isinstance(report.get("ui"), dict) else []
    case_by_id = {case.get("case_id"): case for case in cases if isinstance(case, dict)}
    missing = [case_id for case_id in required_case_ids if case_id not in case_by_id]
    failed = [
        case_id
        for case_id in required_case_ids
        if isinstance(case_by_id.get(case_id), dict) and case_by_id[case_id].get("status") != FreshChatStatus.PASSED.value
    ]
    fixture_unchanged = report.get("fixture_unchanged") is True
    status = (
        FreshChatStatus.PASSED.value
        if report.get("status") == FreshChatStatus.PASSED.value and not missing and not failed and fixture_unchanged
        else FreshChatStatus.FAILED.value
    )
    return {
        "status": status,
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "report_status": report.get("status"),
        "required_case_ids": required_case_ids,
        "missing_case_ids": missing,
        "failed_case_ids": failed,
        "fixture_unchanged": fixture_unchanged,
        "case_summaries": [
            {
                "case_id": case_id,
                "status": case_by_id.get(case_id, {}).get("status") if isinstance(case_by_id.get(case_id), dict) else None,
                "stream_chat_seen": case_by_id.get(case_id, {}).get("stream_chat_seen")
                if isinstance(case_by_id.get(case_id), dict)
                else None,
                "parsed_run_id": case_by_id.get(case_id, {}).get("parsed_run_id")
                if isinstance(case_by_id.get(case_id), dict)
                else None,
            }
            for case_id in required_case_ids
        ],
    }


def build_report(
    *,
    policy: dict[str, Any],
    target_settings: dict[str, Any],
    cases: list[dict[str, Any]],
    ui_report: dict[str, Any],
    fixture_before: dict[str, Any],
    fixture_after: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    failed_cases = [case for case in cases if case.get("status") != FreshChatStatus.PASSED.value]
    blocker_findings = [
        finding
        for case in cases
        for finding in case.get("findings", [])
        if isinstance(finding, dict) and finding.get("severity") == "blocker"
    ]
    required_cases = policy.get("required_cases") if isinstance(policy.get("required_cases"), list) else []
    case_ids = {case.get("case_id") for case in cases}
    missing_required_cases = [case_id for case_id in required_cases if case_id not in case_ids]
    fixture_unchanged = fixture_before == fixture_after
    decision = (
        FreshChatDecision.RESPONSIVE.value
        if (
            not errors
            and not failed_cases
            and not blocker_findings
            and not missing_required_cases
            and target_settings.get("status") == FreshChatStatus.PASSED.value
            and ui_report.get("status") == FreshChatStatus.PASSED.value
            and fixture_unchanged
        )
        else FreshChatDecision.BLOCKED.value
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": FreshChatStatus.PASSED.value if decision == FreshChatDecision.RESPONSIVE.value else FreshChatStatus.FAILED.value,
        "decision": decision,
        "generated_at": utc_timestamp(),
        "target_settings": target_settings,
        "cases": cases,
        "ui_report": ui_report,
        "fixture_state_before": fixture_before,
        "fixture_state_after": fixture_after,
        "fixture_unchanged": fixture_unchanged,
        "summary": {
            "case_count": len(cases),
            "passed_case_count": len(cases) - len(failed_cases),
            "failed_case_count": len(failed_cases),
            "blocker_finding_count": len(blocker_findings),
            "missing_required_case_count": len(missing_required_cases),
            "workflow_router_gateway_case_count": sum(1 for case in cases if case.get("surface") == "workflow_router_gateway"),
            "anythingllm_api_case_count": sum(1 for case in cases if case.get("surface") == "anythingllm_api"),
            "target_settings_status": target_settings.get("status"),
            "ui_report_status": ui_report.get("status"),
            "fixture_unchanged": fixture_unchanged,
        },
        "errors": errors + [f"missing required case {case_id}" for case_id in missing_required_cases],
    }


def validate_report(report: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append("report.schema_version must be 1")
    if report.get("kind") != EXPECTED_REPORT_KIND:
        errors.append(f"report.kind must be {EXPECTED_REPORT_KIND}")
    if report.get("phase") != EXPECTED_PHASE:
        errors.append("report.phase must be 237")
    if report.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"report.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    required_cases = policy.get("required_cases") if isinstance(policy.get("required_cases"), list) else []
    cases = report.get("cases") if isinstance(report.get("cases"), list) else []
    case_by_id = {case.get("case_id"): case for case in cases if isinstance(case, dict)}
    for case_id in required_cases:
        case = case_by_id.get(case_id)
        if not isinstance(case, dict):
            errors.append(f"report missing required case {case_id}")
        elif case.get("status") != FreshChatStatus.PASSED.value:
            errors.append(f"required case {case_id} did not pass")
        elif not case.get("parsed_run_id"):
            errors.append(f"required case {case_id} missing parsed_run_id")
    if report.get("target_settings", {}).get("status") != FreshChatStatus.PASSED.value:
        errors.append("report.target_settings must pass")
    if report.get("ui_report", {}).get("status") != FreshChatStatus.PASSED.value:
        errors.append("report.ui_report must pass")
    if report.get("fixture_unchanged") is not True:
        errors.append("report.fixture_unchanged must be true")
    rebuilt = build_report(
        policy=policy,
        target_settings=report.get("target_settings") if isinstance(report.get("target_settings"), dict) else {},
        cases=[case for case in cases if isinstance(case, dict)],
        ui_report=report.get("ui_report") if isinstance(report.get("ui_report"), dict) else {},
        fixture_before=report.get("fixture_state_before") if isinstance(report.get("fixture_state_before"), dict) else {},
        fixture_after=report.get("fixture_state_after") if isinstance(report.get("fixture_state_after"), dict) else {},
        errors=report.get("errors") if isinstance(report.get("errors"), list) else [],
    )
    for key in ("status", "decision", "summary"):
        if report.get(key) != rebuilt.get(key):
            errors.append(f"report.{key} must match rebuilt Phase 237 report")
    if report.get("decision") != policy.get("required_decision"):
        errors.append("report.decision must match policy.required_decision")
    return errors


def run_anythingllm_fresh_chat_responsiveness(config: AnythingLLMFreshChatResponsivenessConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy = load_policy(config_root, config.policy_path)
    errors = validate_policy(policy)
    api_key = os.environ.get(config.api_key_env)
    if not api_key:
        errors.append(f"{config.api_key_env} is required for live AnythingLLM validation")
        api_key = ""
    fixture_before = fixture_state(config.target_roots)
    target_settings = (
        anythingllm_target_settings(config, api_key=api_key, policy=policy)
        if api_key
        else {"status": FreshChatStatus.FAILED.value, "errors": [f"{config.api_key_env} missing"]}
    )
    cases = [
        gateway_case(config, case_id="GATEWAY-HI", message=GREETING_MESSAGE, case_kind="greeting"),
        gateway_case(config, case_id="GATEWAY-CODE-EXPLANATION", message=CODE_EXPLANATION_PROMPT, case_kind="coding"),
    ]
    if api_key:
        cases.extend(
            [
                anythingllm_case(
                    config,
                    api_key=api_key,
                    case_id="ANYTHINGLLM-HI",
                    message=GREETING_MESSAGE,
                    case_kind="greeting",
                    session_id=f"phase237-hi-{uuid.uuid4().hex}",
                ),
                anythingllm_case(
                    config,
                    api_key=api_key,
                    case_id="ANYTHINGLLM-CODE-EXPLANATION",
                    message=CODE_EXPLANATION_PROMPT,
                    case_kind="coding",
                    session_id=f"phase237-code-{uuid.uuid4().hex}",
                ),
            ]
        )
    ui_report = summarize_ui_report(
        resolve_path(config_root, config.ui_report_path) if config.ui_report_path else None,
        [str(item) for item in policy.get("required_ui_case_ids", [])],
    )
    fixture_after = fixture_state(config.target_roots)
    report = build_report(
        policy=policy,
        target_settings=target_settings,
        cases=cases,
        ui_report=ui_report,
        fixture_before=fixture_before,
        fixture_after=fixture_after,
        errors=errors,
    )
    validation_errors = validate_report(report, policy)
    if validation_errors:
        report["status"] = FreshChatStatus.FAILED.value
        report["decision"] = FreshChatDecision.BLOCKED.value
        report["errors"] = report["errors"] + validation_errors
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    write_json(output_path, report)
    return report
