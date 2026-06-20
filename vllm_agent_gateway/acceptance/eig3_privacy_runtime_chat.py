"""EIG-3 privacy runtime chat proof."""

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

from vllm_agent_gateway.acceptance.eig3_privacy_evalops import (
    EIG3PrivacyEvalOpsConfig,
    case_leaks_raw_source,
    fixture_lookup,
    memory_lookup,
    run_eig3_privacy_evalops,
)
from vllm_agent_gateway.acceptance.eig3_sensitive_data import (
    EIG3ValidationStatus,
    read_json_object,
    string_list,
    validation_error,
    write_json,
)
from vllm_agent_gateway.acceptance.v1 import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
)


SCHEMA_VERSION = 1
DEFAULT_CASES_PATH = Path("runtime") / "eig3_privacy_runtime_chat_cases.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "eig3-privacy-runtime-chat"


class EIG3PrivacyRuntimeSurface(str, Enum):
    WORKFLOW_ROUTER_GATEWAY = "workflow_router_gateway"
    ANYTHINGLLM = "anythingllm"


class EIG3PrivacyRuntimeOutputFormat(str, Enum):
    FORMAT_A = "format_a"
    JSON = "json"


@dataclass(frozen=True)
class EIG3PrivacyRuntimeChatConfig:
    config_root: Path
    cases_path: Path = DEFAULT_CASES_PATH
    output_path: Path | None = None
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 120
    run_live: bool = True
    include_anythingllm: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"eig3-privacy-runtime-chat-{utc_timestamp()}.json"


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = value if isinstance(value, Path) else Path(value)
    return path if path.is_absolute() else config_root / path


def object_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


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


def validate_cases_shape(cases_pack: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if cases_pack.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("cases.schema_version", f"schema_version must be {SCHEMA_VERSION}"))
    if cases_pack.get("kind") != "eig3_privacy_runtime_chat_cases":
        errors.append(validation_error("cases.kind", "kind must be eig3_privacy_runtime_chat_cases"))
    if cases_pack.get("phase") != 302:
        errors.append(validation_error("cases.phase", "phase must be 302"))
    if cases_pack.get("synthetic_only") is not True:
        errors.append(validation_error("cases.synthetic_only", "cases must be synthetic_only=true"))
    if not object_list(cases_pack.get("cases")):
        errors.append(validation_error("cases.cases", "cases must be a non-empty object array"))
    for field in ("source_evalops_pack", "source_fixture_pack", "source_memory_lifecycle_pack"):
        if not isinstance(cases_pack.get(field), str) or not cases_pack[field].strip():
            errors.append(validation_error(f"cases.{field}", f"{field} must be a non-empty string"))
    return errors


def validate_case_shape(case: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    case_id = str(case.get("id") or "unknown")
    required = {
        "id",
        "archetype",
        "fixture_ids",
        "memory_record_ids",
        "prompt",
        "output_format",
        "expected_route_status",
        "required_markers",
        "forbidden_markers",
    }
    missing = sorted(required - set(case))
    if missing:
        errors.append(validation_error("case.missing_fields", "case is missing fields: " + ", ".join(missing), fixture_id=case_id))
        return errors
    if not isinstance(case["id"], str) or not case["id"].strip():
        errors.append(validation_error("case.id", "case id must be a non-empty string", fixture_id=case_id))
    if not string_list(case["fixture_ids"]):
        errors.append(validation_error("case.fixture_ids", "fixture_ids must be a non-empty string array", fixture_id=case_id))
    if not isinstance(case["memory_record_ids"], list):
        errors.append(validation_error("case.memory_record_ids", "memory_record_ids must be an array", fixture_id=case_id))
    if not isinstance(case["prompt"], str) or not case["prompt"].strip():
        errors.append(validation_error("case.prompt", "prompt must be a non-empty string", fixture_id=case_id))
    if case["output_format"] not in {item.value for item in EIG3PrivacyRuntimeOutputFormat}:
        errors.append(validation_error("case.output_format", "output_format is unsupported", fixture_id=case_id))
    if not string_list(case["required_markers"]):
        errors.append(validation_error("case.required_markers", "required_markers must be non-empty", fixture_id=case_id))
    if not isinstance(case["forbidden_markers"], list):
        errors.append(validation_error("case.forbidden_markers", "forbidden_markers must be an array", fixture_id=case_id))
    return errors


def parsed_json_response(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def summary_from_format_a_text(text: str) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    in_summary = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == "Summary:":
            in_summary = True
            continue
        if in_summary and not line:
            continue
        if in_summary and not line.startswith("- "):
            break
        if not in_summary or ": " not in line:
            continue
        key, value = line[2:].split(": ", 1)
        summary[key.strip()] = value.strip()
    return summary


def response_summary(text: str, body: dict[str, Any], output_format: str) -> dict[str, Any]:
    controller = body.get("agentic_controller_response") if isinstance(body.get("agentic_controller_response"), dict) else {}
    summary = controller.get("summary") if isinstance(controller.get("summary"), dict) else {}
    if summary:
        return summary
    if output_format == EIG3PrivacyRuntimeOutputFormat.JSON.value:
        parsed = parsed_json_response(text)
        if parsed and isinstance(parsed.get("summary"), dict):
            return parsed["summary"]
    return summary_from_format_a_text(text)


def classify_case_response(
    *,
    case: dict[str, Any],
    surface: str,
    http_status: int,
    body: dict[str, Any],
    fixtures: dict[str, dict[str, Any]],
    memory_records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    text = text_response(body)
    findings: list[dict[str, str]] = []
    case_id = str(case.get("id") or "unknown")
    output_format = str(case.get("output_format") or EIG3PrivacyRuntimeOutputFormat.FORMAT_A.value)
    if http_status != 200:
        findings.append(validation_error("response.http_status", f"HTTP status was {http_status}", fixture_id=case_id))
    if not text.strip():
        findings.append(validation_error("response.text", "response text is empty", fixture_id=case_id))
    visible_lower = text.lower()
    for marker in string_list(case.get("required_markers")):
        if marker.lower() not in visible_lower:
            findings.append(validation_error("response.required_marker", f"missing marker: {marker}", fixture_id=case_id))
    for marker in string_list(case.get("forbidden_markers")):
        if marker.lower() in visible_lower:
            findings.append(validation_error("response.forbidden_marker", f"forbidden marker present: {marker}", fixture_id=case_id))
    summary = response_summary(text, body, output_format)
    expected_route = str(case.get("expected_route_status") or "")
    if summary.get("route_status") != expected_route:
        findings.append(validation_error("response.route_status", f"route_status must be {expected_route}", fixture_id=case_id))
    if summary.get("selected_workflow") not in {"none", None}:
        findings.append(validation_error("response.selected_workflow", "selected_workflow must be none", fixture_id=case_id))
    if output_format == EIG3PrivacyRuntimeOutputFormat.JSON.value:
        parsed = parsed_json_response(text)
        if parsed is None:
            findings.append(validation_error("response.json", "JSON output case must return valid JSON", fixture_id=case_id))
        elif parsed.get("output_format") != EIG3PrivacyRuntimeOutputFormat.JSON.value:
            findings.append(validation_error("response.json.output_format", "JSON output must preserve output_format=json", fixture_id=case_id))
    if case_leaks_raw_source(
        {
            "fixture_ids": case.get("fixture_ids"),
            "memory_record_ids": case.get("memory_record_ids"),
            "prompt": "",
            "blind_baseline": {"safe_answer": ""},
            "local_stack_results": [{"output_summary": text}],
        },
        fixtures,
        memory_records,
    ):
        findings.append(validation_error("response.raw_source_leak", "response leaked raw fixture or memory source content", fixture_id=case_id))
    return {
        "case_id": case_id,
        "surface": surface,
        "status": EIG3ValidationStatus.PASSED.value if not findings else EIG3ValidationStatus.FAILED.value,
        "http_status": http_status,
        "output_format": output_format,
        "text_sample": text[:1200],
        "route_status": summary.get("route_status"),
        "selected_workflow": summary.get("selected_workflow"),
        "finding_count": len(findings),
        "findings": findings,
    }


def gateway_case(
    config: EIG3PrivacyRuntimeChatConfig,
    case: dict[str, Any],
    fixtures: dict[str, dict[str, Any]],
    memory_records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": "agentic-workflow-router",
        "messages": [{"role": "user", "content": case["prompt"]}],
    }
    if case.get("output_format") == EIG3PrivacyRuntimeOutputFormat.JSON.value:
        payload["output_format"] = EIG3PrivacyRuntimeOutputFormat.JSON.value
    status, body = json_request(
        f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload=payload,
        timeout_seconds=config.timeout_seconds,
    )
    return classify_case_response(
        case=case,
        surface=EIG3PrivacyRuntimeSurface.WORKFLOW_ROUTER_GATEWAY.value,
        http_status=status,
        body=body,
        fixtures=fixtures,
        memory_records=memory_records,
    )


def anythingllm_case(
    config: EIG3PrivacyRuntimeChatConfig,
    case: dict[str, Any],
    fixtures: dict[str, dict[str, Any]],
    memory_records: dict[str, dict[str, Any]],
    api_key: str,
) -> dict[str, Any]:
    status, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={
            "message": case["prompt"],
            "mode": "chat",
            "sessionId": f"eig3-privacy-runtime-{case['id']}-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=config.timeout_seconds,
    )
    return classify_case_response(
        case=case,
        surface=EIG3PrivacyRuntimeSurface.ANYTHINGLLM.value,
        http_status=status,
        body=body,
        fixtures=fixtures,
        memory_records=memory_records,
    )


def anythingllm_preflight(config: EIG3PrivacyRuntimeChatConfig, api_key: str) -> dict[str, Any]:
    ping_status, ping_body = json_request(f"{config.anythingllm_api_base_url.rstrip('/')}/api/ping", timeout_seconds=30)
    workspace_status, workspace_body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspaces",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=30,
    )
    workspaces = workspace_body.get("workspaces") if isinstance(workspace_body, dict) else []
    if not isinstance(workspaces, list):
        workspaces = []
    slugs = [item.get("slug") for item in workspaces if isinstance(item, dict)]
    return {
        "status": EIG3ValidationStatus.PASSED.value
        if ping_status == 200 and workspace_status == 200 and config.workspace in slugs
        else EIG3ValidationStatus.FAILED.value,
        "ping_status": ping_status,
        "workspace_status": workspace_status,
        "workspace": config.workspace,
        "workspace_found": config.workspace in slugs,
        "ping": ping_body,
    }


def run_eig3_privacy_runtime_chat(config: EIG3PrivacyRuntimeChatConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    cases_path = resolve_path(config_root, config.cases_path)
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    errors: list[dict[str, str]] = []
    cases_pack = read_json_object(cases_path)
    errors.extend(validate_cases_shape(cases_pack))
    evalops_report = run_eig3_privacy_evalops(
        EIG3PrivacyEvalOpsConfig(
            config_root=config_root,
            pack_path=Path(str(cases_pack.get("source_evalops_pack") or "runtime/eig3_privacy_evalops_prompt_pack.json")),
            output_path=output_path.parent / f"{output_path.stem}-phase301-validation.json",
        )
    )
    if evalops_report.get("status") != EIG3ValidationStatus.PASSED.value:
        errors.append(validation_error("prerequisite.phase301", "Phase 301 privacy EvalOps must pass before runtime chat proof"))
    fixture_pack = read_json_object(resolve_path(config_root, str(cases_pack.get("source_fixture_pack") or "runtime/eig3_sensitive_data_fixtures.json")))
    memory_pack = read_json_object(resolve_path(config_root, str(cases_pack.get("source_memory_lifecycle_pack") or "runtime/eig3_memory_lifecycle_fixtures.json")))
    fixtures = fixture_lookup(fixture_pack)
    memory_records = memory_lookup(memory_pack)
    shaped_cases: list[dict[str, Any]] = []
    case_results: list[dict[str, Any]] = []
    for case in object_list(cases_pack.get("cases")):
        shape_errors = validate_case_shape(case)
        errors.extend(shape_errors)
        if not shape_errors:
            shaped_cases.append(case)
    anythingllm_preflight_result: dict[str, Any] = {"status": "skipped"}
    api_key = os.environ.get(config.api_key_env)
    if config.run_live and config.include_anythingllm:
        if not api_key:
            errors.append(validation_error("anythingllm.api_key", f"{config.api_key_env} is required for AnythingLLM proof"))
        else:
            anythingllm_preflight_result = anythingllm_preflight(config, api_key)
            if anythingllm_preflight_result.get("status") != EIG3ValidationStatus.PASSED.value:
                errors.append(validation_error("anythingllm.preflight", "AnythingLLM preflight failed"))
    if config.run_live:
        for case in shaped_cases:
            gateway_result = gateway_case(config, case, fixtures, memory_records)
            case_results.append(gateway_result)
            errors.extend(gateway_result["findings"])
            if config.include_anythingllm and api_key and anythingllm_preflight_result.get("status") == EIG3ValidationStatus.PASSED.value:
                anythingllm_result = anythingllm_case(config, case, fixtures, memory_records, api_key)
                case_results.append(anythingllm_result)
                errors.extend(anythingllm_result["findings"])
    status = EIG3ValidationStatus.PASSED.value if not errors else EIG3ValidationStatus.FAILED.value
    surfaces = sorted({str(item.get("surface")) for item in case_results})
    summary = {
        "status": status,
        "case_count": len(shaped_cases),
        "result_count": len(case_results),
        "surface_count": len(surfaces),
        "surfaces": surfaces,
        "failed_result_count": sum(1 for item in case_results if item.get("status") != EIG3ValidationStatus.PASSED.value),
        "validation_error_count": len(errors),
        "run_live": config.run_live,
        "include_anythingllm": config.include_anythingllm,
        "phase303_ready": status == EIG3ValidationStatus.PASSED.value,
        "phase301_report_path": evalops_report.get("report_path"),
        "anythingllm_preflight_status": anythingllm_preflight_result.get("status"),
        "raw_source_content_retained_in_report": False,
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "eig3_privacy_runtime_chat_report",
        "phase": 302,
        "status": status,
        "cases_path": str(cases_path),
        "summary": summary,
        "anythingllm_preflight": anythingllm_preflight_result,
        "case_results": case_results,
        "validation_errors": errors,
        "report_path": str(output_path),
    }
    write_json(output_path, report)
    return report
