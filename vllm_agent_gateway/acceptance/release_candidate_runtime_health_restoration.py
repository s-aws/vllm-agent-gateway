"""Phase 245 release-candidate runtime health restoration gate."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "release_candidate_runtime_health_restoration_policy"
EXPECTED_REPORT_KIND = "release_candidate_runtime_health_restoration_report"
EXPECTED_PHASE = 245
EXPECTED_BACKLOG_ID = "P0-M13-245"
EXPECTED_MILESTONE_IDS = {"M13", "M14"}
DEFAULT_POLICY_PATH = Path("runtime") / "release_candidate_runtime_health_restoration_policy.json"
DEFAULT_OUTPUT_PATH = (
    Path("runtime-state")
    / "release-candidate-runtime-health-restoration"
    / "phase245"
    / "phase245-release-candidate-runtime-health-restoration-report.json"
)
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_MODEL = "Qwen3-Coder-30B-A3B-Instruct"


class RuntimeHealthRestorationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class RuntimeHealthRestorationDecision(str, Enum):
    RESTORED = "runtime_health_restored"
    BLOCKED = "runtime_health_blocked"


@dataclass(frozen=True)
class ReleaseCandidateRuntimeHealthRestorationConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    anythingllm_workflow_router_base_url: str | None = None
    workspace: str = DEFAULT_WORKSPACE
    model: str = DEFAULT_MODEL
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 180
    health_timeout_seconds: int = 15


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def read_json_object(path: Path) -> dict[str, Any]:
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


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def string_group_list(value: object) -> list[list[str]]:
    groups: list[list[str]] = []
    if not isinstance(value, list):
        return groups
    for item in value:
        if isinstance(item, list):
            group = [marker for marker in item if isinstance(marker, str) and marker.strip()]
            if group:
                groups.append(group)
    return groups


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validation_error(error_id: str, message: str, *, source: str = "policy", severity: str = "high") -> dict[str, str]:
    return {"id": error_id, "message": message, "source": source, "severity": severity}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "phase must be 245"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be exactly M13 and M14"))
    if policy.get("required_decision") != RuntimeHealthRestorationDecision.RESTORED.value:
        errors.append(validation_error("policy.required_decision", "required_decision must be runtime_health_restored"))
    anythingllm = dict_value(policy.get("required_anythingllm"))
    expected_anythingllm = {
        "api_base_url": DEFAULT_ANYTHINGLLM_API_BASE_URL,
        "workflow_router_base_url": DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
        "workspace": DEFAULT_WORKSPACE,
        "model": DEFAULT_MODEL,
    }
    for key, expected in expected_anythingllm.items():
        if anythingllm.get(key) != expected:
            errors.append(validation_error(f"policy.required_anythingllm.{key}", f"{key} must be {expected}"))
    if len(object_list(policy.get("required_runtime_health"))) < 10:
        errors.append(validation_error("policy.required_runtime_health", "full runtime health probe list is required"))
    for item in object_list(policy.get("required_runtime_health")):
        probe_id = str(item.get("id") or "unknown")
        if not isinstance(item.get("url"), str) or not item["url"].startswith("http://127.0.0.1:"):
            errors.append(validation_error(f"policy.required_runtime_health.{probe_id}.url", "localhost URL is required"))
        if item.get("required") is not True:
            errors.append(validation_error(f"policy.required_runtime_health.{probe_id}.required", "probe must be required"))
    prompt = dict_value(policy.get("workflow_router_prompt"))
    for key in ("gateway_model", "message", "target_root"):
        if not isinstance(prompt.get(key), str) or not prompt[key].strip():
            errors.append(validation_error(f"policy.workflow_router_prompt.{key}", f"{key} is required"))
    if "read only" not in str(prompt.get("message", "")).lower():
        errors.append(validation_error("policy.workflow_router_prompt.message", "minimal prompt must declare read-only intent"))
    if not string_group_list(policy.get("required_case_markers")):
        errors.append(validation_error("policy.required_case_markers", "required case marker groups are required"))
    if len(string_list(policy.get("protected_fixture_roots"))) < 2:
        errors.append(validation_error("policy.protected_fixture_roots", "both frozen fixture roots are required"))
    if not string_list(policy.get("watched_relative_paths")):
        errors.append(validation_error("policy.watched_relative_paths", "watched fixture files are required"))
    if policy.get("acceptance_marker") != "PHASE245 RELEASE CANDIDATE RUNTIME HEALTH RESTORATION PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 245"))
    return errors


def probe_url(url: str, timeout_seconds: int) -> dict[str, Any]:
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(2048).decode("utf-8", errors="replace")
            return {
                "url": url,
                "status_code": response.status,
                "passed": 200 <= response.status < 400,
                "body_sample": body[:500],
            }
    except urllib.error.HTTPError as exc:
        body = exc.read(2048).decode("utf-8", errors="replace")
        return {"url": url, "status_code": exc.code, "passed": 200 <= exc.code < 400, "error": str(exc), "body_sample": body[:500]}
    except Exception as exc:  # noqa: BLE001
        return {"url": url, "status_code": None, "passed": False, "error": f"{type(exc).__name__}: {exc}"}


def runtime_health(policy: dict[str, Any], timeout_seconds: int) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for item in object_list(policy.get("required_runtime_health")):
        probe_id = str(item.get("id"))
        url = str(item.get("url"))
        result = {"id": probe_id, **probe_url(url, timeout_seconds)}
        results.append(result)
        if item.get("required") is True and result.get("passed") is not True:
            errors.append(validation_error(f"runtime_health.{probe_id}", f"required runtime probe failed: {url}", source="runtime_health"))
    return results, errors


def json_request(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: int,
    method: str = "POST",
) -> tuple[int, dict[str, Any]]:
    request_headers = dict(headers or {})
    data = None
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(text) if text else {}
            except json.JSONDecodeError:
                parsed = {"text": text}
            return response.status, parsed if isinstance(parsed, dict) else {"value": parsed}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = {"error": {"message": text, "code": "invalid_json_error_body"}}
        return exc.code, parsed if isinstance(parsed, dict) else {"value": parsed}
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": {"message": f"{type(exc).__name__}: {exc}", "code": "request_error"}}


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


def run_id_from_text(text: str) -> str | None:
    match = re.search(r"\brun_id:\s*([A-Za-z0-9_.:-]+)", text)
    return match.group(1) if match else None


def missing_marker_groups(text: str, groups: list[list[str]]) -> list[list[str]]:
    return [group for group in groups if not any(marker in text for marker in group)]


def classify_chat_case(
    *,
    case_id: str,
    surface: str,
    status_code: int,
    body: dict[str, Any],
    required_marker_groups: list[list[str]],
) -> dict[str, Any]:
    text = text_response(body)
    missing = missing_marker_groups(text, required_marker_groups)
    parsed_run_id = run_id_from_text(text)
    findings: list[dict[str, str]] = []
    if status_code != 200:
        findings.append({"severity": "blocker", "code": "http_status_not_ok", "message": f"HTTP status was {status_code}."})
    if not text.strip():
        findings.append({"severity": "blocker", "code": "missing_text", "message": "Response text was empty."})
    if missing:
        findings.append(
            {
                "severity": "blocker",
                "code": "missing_required_marker_group",
                "message": "Missing required marker group(s): " + json.dumps(missing, ensure_ascii=True),
            }
        )
    if not parsed_run_id:
        findings.append({"severity": "blocker", "code": "missing_run_id", "message": "Response text did not include a workflow run_id."})
    return {
        "case_id": case_id,
        "surface": surface,
        "status": RuntimeHealthRestorationStatus.PASSED.value if not findings else RuntimeHealthRestorationStatus.FAILED.value,
        "http_status": status_code,
        "parsed_run_id": parsed_run_id,
        "text_sample": text[:4000],
        "text_length": len(text),
        "finding_count": len(findings),
        "findings": findings,
    }


def gateway_case(config: ReleaseCandidateRuntimeHealthRestorationConfig, policy: dict[str, Any]) -> dict[str, Any]:
    prompt = dict_value(policy.get("workflow_router_prompt"))
    status_code, body = json_request(
        f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": prompt.get("gateway_model", "agentic-workflow-router"),
            "messages": [{"role": "user", "content": str(prompt.get("message", ""))}],
            "stream": False,
        },
        timeout_seconds=config.timeout_seconds,
    )
    return classify_chat_case(
        case_id="PHASE245-GATEWAY-MINIMAL-READONLY",
        surface="workflow_router_gateway",
        status_code=status_code,
        body=body,
        required_marker_groups=string_group_list(policy.get("required_case_markers")),
    )


def anythingllm_case(
    config: ReleaseCandidateRuntimeHealthRestorationConfig,
    policy: dict[str, Any],
    *,
    api_key: str,
) -> dict[str, Any]:
    prompt = dict_value(policy.get("workflow_router_prompt"))
    status_code, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={
            "message": str(prompt.get("message", "")),
            "mode": "chat",
            "sessionId": f"phase245-runtime-health-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=config.timeout_seconds,
    )
    return classify_chat_case(
        case_id="PHASE245-ANYTHINGLLM-MINIMAL-READONLY",
        surface="anythingllm_api",
        status_code=status_code,
        body=body,
        required_marker_groups=string_group_list(policy.get("required_case_markers")),
    )


def anythingllm_target_settings(
    config: ReleaseCandidateRuntimeHealthRestorationConfig,
    policy: dict[str, Any],
    *,
    api_key: str,
) -> dict[str, Any]:
    required = dict_value(policy.get("required_anythingllm"))
    expected_workflow_router_base_url = (
        config.anythingllm_workflow_router_base_url
        if config.anythingllm_workflow_router_base_url
        else required.get("workflow_router_base_url")
    )
    status_code, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/system",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=min(30, config.timeout_seconds),
        method="GET",
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
        "generic_openai_base_path": actual["generic_openai_base_path"] == expected_workflow_router_base_url,
    }
    effective_required = {**required, "workflow_router_base_url": expected_workflow_router_base_url}
    return {
        "status": RuntimeHealthRestorationStatus.PASSED.value if all(checks.values()) else RuntimeHealthRestorationStatus.FAILED.value,
        "http_status": status_code,
        "actual": actual,
        "required": effective_required,
        "policy_required": required,
        "checks": checks,
    }


def git_status(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    result = subprocess.run(["git", "-C", str(root), "status", "--short"], check=True, capture_output=True, text=True)
    return result.stdout


def fixture_snapshot(policy: dict[str, Any]) -> dict[str, Any]:
    roots: dict[str, Any] = {}
    watched_relatives = string_list(policy.get("watched_relative_paths"))
    for raw_root in string_list(policy.get("protected_fixture_roots")):
        root = Path(raw_root)
        root_record: dict[str, Any] = {
            "exists": root.exists(),
            "git_status": None,
            "files": {},
        }
        if root.exists():
            root_record["git_status"] = git_status(root)
            for relative in watched_relatives:
                path = root / relative
                if path.is_file():
                    root_record["files"][relative] = {"exists": True, "sha256": sha256_file(path)}
                else:
                    root_record["files"][relative] = {"exists": False, "sha256": None}
        roots[raw_root] = root_record
    return roots


def fixture_errors(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for root, record in snapshot.items():
        if not isinstance(record, dict) or record.get("exists") is not True:
            errors.append(validation_error(f"fixture.{root}.missing", "protected fixture root is missing", source="fixture"))
            continue
        files = record.get("files")
        if not isinstance(files, dict) or not any(isinstance(item, dict) and item.get("exists") for item in files.values()):
            errors.append(validation_error(f"fixture.{root}.no_watched_files", "protected fixture has no watched files", source="fixture"))
    return errors


def build_report(
    *,
    config_root: Path,
    policy_path: Path,
    policy: dict[str, Any],
    policy_errors: list[dict[str, str]],
    health_results: list[dict[str, Any]],
    health_errors: list[dict[str, str]],
    target_settings: dict[str, Any],
    cases: list[dict[str, Any]],
    fixture_before: dict[str, Any],
    fixture_after: dict[str, Any],
    api_key_error: dict[str, str] | None,
) -> dict[str, Any]:
    fixture_unchanged = fixture_before == fixture_after
    fixture_check_errors = fixture_errors(fixture_before)
    fixture_mutation_errors = [] if fixture_unchanged else [validation_error("fixture.unchanged", "protected fixture state changed", source="fixture")]
    target_errors = (
        []
        if target_settings.get("status") == RuntimeHealthRestorationStatus.PASSED.value
        else [validation_error("anythingllm.target_settings", "AnythingLLM target settings did not match required workflow-router gateway", source="anythingllm")]
    )
    case_errors = [
        validation_error(f"case.{case.get('case_id')}", "minimal read-only chat case failed", source=str(case.get("surface")))
        for case in cases
        if case.get("status") != RuntimeHealthRestorationStatus.PASSED.value
    ]
    blockers = [
        *policy_errors,
        *health_errors,
        *(target_errors if api_key_error is None else []),
        *case_errors,
        *fixture_check_errors,
        *fixture_mutation_errors,
    ]
    if api_key_error is not None:
        blockers.append(api_key_error)
    decision = (
        RuntimeHealthRestorationDecision.RESTORED.value
        if not blockers
        else RuntimeHealthRestorationDecision.BLOCKED.value
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": sorted(EXPECTED_MILESTONE_IDS),
        "generated_at": utc_timestamp(),
        "config_root": str(config_root),
        "policy_path": str(policy_path),
        "policy_sha256": sha256_file(policy_path) if policy_path.is_file() else None,
        "status": RuntimeHealthRestorationStatus.PASSED.value
        if decision == RuntimeHealthRestorationDecision.RESTORED.value
        else RuntimeHealthRestorationStatus.FAILED.value,
        "decision": decision,
        "runtime_health": health_results,
        "anythingllm_target_settings": target_settings,
        "cases": cases,
        "fixture_state_before": fixture_before,
        "fixture_state_after": fixture_after,
        "fixture_unchanged": fixture_unchanged,
        "blockers": blockers,
        "summary": {
            "runtime_health_probe_count": len(health_results),
            "runtime_health_blocker_count": len(health_errors),
            "case_count": len(cases),
            "passed_case_count": sum(1 for case in cases if case.get("status") == RuntimeHealthRestorationStatus.PASSED.value),
            "target_settings_status": target_settings.get("status"),
            "fixture_unchanged": fixture_unchanged,
            "blocker_count": len(blockers),
            "phase246_ready": decision == RuntimeHealthRestorationDecision.RESTORED.value,
        },
    }


def validate_release_candidate_runtime_health_restoration(
    config: ReleaseCandidateRuntimeHealthRestorationConfig,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    policy = read_json_object(policy_path)
    policy_errors = validate_policy(policy)

    fixture_before = fixture_snapshot(policy)
    health_results, health_errors = runtime_health(policy, config.health_timeout_seconds)

    api_key = os.environ.get(config.api_key_env, "")
    api_key_error = None
    if not api_key:
        api_key_error = validation_error(config.api_key_env, f"{config.api_key_env} is required for AnythingLLM validation", source="anythingllm")
    target_settings = (
        anythingllm_target_settings(config, policy, api_key=api_key)
        if api_key
        else {"status": RuntimeHealthRestorationStatus.FAILED.value, "errors": [f"{config.api_key_env} missing"]}
    )
    cases = [gateway_case(config, policy)]
    if api_key:
        cases.append(anythingllm_case(config, policy, api_key=api_key))

    fixture_after = fixture_snapshot(policy)
    report = build_report(
        config_root=config_root,
        policy_path=policy_path,
        policy=policy,
        policy_errors=policy_errors,
        health_results=health_results,
        health_errors=health_errors,
        target_settings=target_settings,
        cases=cases,
        fixture_before=fixture_before,
        fixture_after=fixture_after,
        api_key_error=api_key_error,
    )
    write_json(output_path, report)
    return report
