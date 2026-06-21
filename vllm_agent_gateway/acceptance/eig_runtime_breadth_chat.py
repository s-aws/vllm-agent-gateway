"""Phase 295 EIG runtime breadth chat-quality validation."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vllm_agent_gateway.controller_service.server import (
    ControllerServiceConfig,
    handle_workflow_router_chat_completion,
    json_bytes,
)


SCHEMA_VERSION = 1
DEFAULT_CASES_PATH = Path("runtime") / "eig_runtime_breadth_chat_cases.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "acceptance" / "eig-runtime-breadth-chat-report.json"


@dataclass(frozen=True)
class EIGRuntimeBreadthChatConfig:
    config_root: Path
    cases_path: Path = DEFAULT_CASES_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    controller_output_root: Path = Path("runtime-state") / "controller-artifacts" / "eig-runtime-breadth-chat"
    base_url: str | None = None
    anythingllm_api_base_url: str | None = None
    anythingllm_workspace: str = "my-workspace"
    anythingllm_api_key_env: str = "ANYTHINGLLM_API_KEY"
    controller_base_url: str = "http://127.0.0.1:8400"
    model: str = "agentic-workflow-router"
    timeout_seconds: int = 60


def resolve_path(config_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else config_root / path


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def object_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def string_items(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def chat_payload(prompt: str, model: str) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }


def direct_chat_response(config: EIGRuntimeBreadthChatConfig, prompt: str) -> dict[str, Any]:
    service_config = ControllerServiceConfig(
        config_root=config.config_root,
        output_root=resolve_path(config.config_root, config.controller_output_root),
        allowed_target_roots=(config.config_root,),
        port=0,
    )
    return handle_workflow_router_chat_completion(chat_payload(prompt, config.model), service_config)


def live_chat_response(config: EIGRuntimeBreadthChatConfig, prompt: str) -> dict[str, Any]:
    if not config.base_url:
        raise ValueError("base_url is required for live chat validation")
    base = config.base_url.rstrip("/")
    url = f"{base}/chat/completions" if base.endswith("/v1") else f"{base}/v1/chat/completions"
    body = json.dumps(chat_payload(prompt, config.model), ensure_ascii=True).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {error_body}") from exc
    if not isinstance(value, dict):
        raise ValueError("chat response must be a JSON object")
    return value


RUN_ID_RE = re.compile(r"\b(?:connector-invocation|workflow-router(?:-general)?)-[0-9T]+Z\b")


def anythingllm_text_response(body: dict[str, Any]) -> str:
    for key in ("textResponse", "text", "response", "message"):
        value = body.get(key)
        if isinstance(value, str):
            return value
    choices = body.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message") if isinstance(choices[0].get("message"), dict) else {}
        content = message.get("content")
        if isinstance(content, str):
            return content
    return json.dumps(body, ensure_ascii=True, sort_keys=True)


def run_id_from_text(text: str) -> str | None:
    matches = RUN_ID_RE.findall(text)
    return matches[-1] if matches else None


def controller_run_record(config: EIGRuntimeBreadthChatConfig, run_id: str) -> dict[str, Any]:
    url = f"{config.controller_base_url.rstrip('/')}/v1/controller/runs/{run_id}"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            value = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def anythingllm_chat_response(config: EIGRuntimeBreadthChatConfig, prompt: str) -> dict[str, Any]:
    if not config.anythingllm_api_base_url:
        raise ValueError("anythingllm_api_base_url is required for AnythingLLM validation")
    api_key = os.environ.get(config.anythingllm_api_key_env)
    if not api_key:
        raise RuntimeError(f"{config.anythingllm_api_key_env} is required for AnythingLLM validation")
    url = f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.anythingllm_workspace}/chat"
    payload = {
        "message": prompt,
        "mode": "chat",
        "sessionId": f"eig-runtime-breadth-chat-{uuid.uuid4().hex}",
    }
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {error_body}") from exc
    if not isinstance(value, dict):
        raise ValueError("AnythingLLM chat response must be a JSON object")
    text = anythingllm_text_response(value)
    run_id = run_id_from_text(text)
    record = controller_run_record(config, run_id) if run_id else {}
    return {
        "choices": [{"message": {"content": text}}],
        "agentic_controller_response": record,
        "anythingllm_response": value,
    }


def response_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first.get("message"), dict) else {}
    content = message.get("content")
    return content if isinstance(content, str) else ""


def controller_response(response: dict[str, Any]) -> dict[str, Any]:
    compact = response.get("agentic_controller_response")
    return compact if isinstance(compact, dict) else {}


def read_artifact(path_value: Any) -> dict[str, Any]:
    if not isinstance(path_value, str):
        return {}
    try:
        value = json.loads(Path(path_value).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def case_errors(
    case: dict[str, Any],
    response: dict[str, Any],
    *,
    source_connectors_hash: str,
    connectors_path: Path,
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    compact = controller_response(response)
    content = response_content(response)
    summary = compact.get("summary") if isinstance(compact.get("summary"), dict) else {}
    artifacts = compact.get("artifacts") if isinstance(compact.get("artifacts"), dict) else {}
    connector_artifact = read_artifact(artifacts.get("connector_invocation"))
    route_decision = read_artifact(artifacts.get("route_decision"))
    audit = connector_artifact.get("audit") if isinstance(connector_artifact.get("audit"), dict) else {}
    expected_workflow = case.get("expected_workflow")
    expected_connector = case.get("expected_connector_id")
    expected_operation = case.get("expected_operation_id")
    expected_scopes = string_items(case.get("expected_required_scopes"))
    if compact.get("workflow") != expected_workflow:
        errors.append({"code": "workflow_mismatch", "message": f"expected {expected_workflow}, got {compact.get('workflow')}"})
    if compact.get("status") != "completed":
        errors.append({"code": "status_not_completed", "message": f"status={compact.get('status')}"})
    if summary.get("connector_id") != expected_connector:
        errors.append({"code": "connector_mismatch", "message": f"expected {expected_connector}, got {summary.get('connector_id')}"})
    if summary.get("operation_id") != expected_operation:
        errors.append({"code": "operation_mismatch", "message": f"expected {expected_operation}, got {summary.get('operation_id')}"})
    if summary.get("required_scopes") != expected_scopes:
        errors.append({"code": "required_scope_mismatch", "message": f"expected {expected_scopes}, got {summary.get('required_scopes')}"})
    if summary.get("authorization_status") != "allowed":
        errors.append({"code": "authorization_not_allowed", "message": f"authorization_status={summary.get('authorization_status')}"})
    if summary.get("runtime_registry_changed") is not False:
        errors.append({"code": "runtime_registry_mutation_reported", "message": "runtime_registry_changed must be false"})
    if summary.get("target_repository_changed") is not False:
        errors.append({"code": "target_repository_mutation_reported", "message": "target_repository_changed must be false"})
    required_content = [
        "Connector Result:",
        f"- Connector: {expected_connector}.{expected_operation}",
        "- Authorization: allowed",
        "- Audit: decision=allowed",
        "- Runtime registry mutation: false",
        "- Target repository mutation: false",
        *string_items(case.get("expected_result_fragments")),
    ]
    for fragment in required_content:
        if fragment not in content:
            errors.append({"code": "missing_chat_fragment", "message": fragment})
    if route_decision.get("selected_workflow") != expected_workflow:
        errors.append({"code": "route_decision_mismatch", "message": f"selected_workflow={route_decision.get('selected_workflow')}"})
    if audit.get("raw_auth_subject_stored") is not False:
        errors.append({"code": "raw_auth_subject_stored", "message": "audit must not store raw auth subject"})
    if audit.get("raw_arguments_stored") is not False:
        errors.append({"code": "raw_arguments_stored", "message": "audit must not store raw arguments"})
    current_hash = file_sha256(connectors_path)
    if current_hash != source_connectors_hash:
        errors.append({"code": "source_connector_registry_changed", "message": "runtime/connectors.json changed during validation"})
    return errors


def file_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_case(config: EIGRuntimeBreadthChatConfig, case: dict[str, Any], source_connectors_hash: str) -> dict[str, Any]:
    prompt = case.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return {"case_id": case.get("id"), "status": "failed", "errors": [{"code": "missing_prompt", "message": "prompt is required"}]}
    if config.anythingllm_api_base_url:
        response = anythingllm_chat_response(config, prompt)
    elif config.base_url:
        response = live_chat_response(config, prompt)
    else:
        response = direct_chat_response(config, prompt)
    errors = case_errors(
        case,
        response,
        source_connectors_hash=source_connectors_hash,
        connectors_path=config.config_root / "runtime" / "connectors.json",
    )
    compact = controller_response(response)
    return {
        "case_id": case.get("id"),
        "status": "failed" if errors else "passed",
        "workflow": compact.get("workflow"),
        "run_id": compact.get("run_id"),
        "artifact_keys": sorted((compact.get("artifacts") or {}).keys()) if isinstance(compact.get("artifacts"), dict) else [],
        "errors": errors,
    }


def run_eig_runtime_breadth_chat_validation(config: EIGRuntimeBreadthChatConfig) -> dict[str, Any]:
    cases_path = resolve_path(config.config_root, config.cases_path)
    output_path = resolve_path(config.config_root, config.output_path)
    pack = read_json_object(cases_path)
    cases = object_items(pack.get("cases"))
    connectors_hash = file_sha256(config.config_root / "runtime" / "connectors.json")
    results = [validate_case(config, case, connectors_hash) for case in cases]
    failed = [item for item in results if item.get("status") != "passed"]
    report = {
        "kind": "eig_runtime_breadth_chat_report",
        "schema_version": SCHEMA_VERSION,
        "status": "failed" if failed else "passed",
        "report_path": str(output_path),
        "mode": "anythingllm" if config.anythingllm_api_base_url else "live" if config.base_url else "direct",
        "base_url": config.base_url,
        "anythingllm_api_base_url": config.anythingllm_api_base_url,
        "anythingllm_workspace": config.anythingllm_workspace if config.anythingllm_api_base_url else None,
        "cases_path": str(cases_path),
        "summary": {
            "case_count": len(results),
            "passed_case_count": len(results) - len(failed),
            "failed_case_count": len(failed),
            "source_connector_registry_changed": file_sha256(config.config_root / "runtime" / "connectors.json") != connectors_hash,
            "phase296_ready": not failed,
        },
        "case_results": results,
        "blind_baseline_contract": pack.get("blind_baseline_contract") if isinstance(pack.get("blind_baseline_contract"), dict) else {},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(json_bytes(report))
    return report
