"""First-time user setup doctor for local workflow testing."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.v1 import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    HEALTH_TARGETS,
)
from vllm_agent_gateway.fixtures.manager import (
    DEFAULT_MANIFEST_PATH,
    fixture_entries,
    fixture_snapshot,
    load_fixture_manifest,
    resolve_path,
)


DEFAULT_MODEL_BASE_URL = "http://127.0.0.1:8000/v1"
DEFAULT_LLM_GATEWAY_BASE_URL = "http://127.0.0.1:8300/v1"
DEFAULT_REPORT_DIR = Path("runtime-state") / "first-time-user-doctor"
DEFAULT_ROLES_PATH = Path("runtime") / "roles.json"
STACK_RESTART_COMMAND = "./stop-agent-prompt-proxies.sh && ./start-agent-prompt-proxies.sh"


class DoctorStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


class DoctorRequestDiagnostic(str, Enum):
    HEADERS_WITHOUT_BODY_TIMEOUT = "headers_without_body_timeout"
    INVALID_JSON_BODY = "invalid_json_body"
    UNREACHABLE_PORT = "unreachable_port"


class DoctorRequestError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        diagnostic_kind: DoctorRequestDiagnostic,
        stage: str,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.diagnostic_kind = diagnostic_kind.value
        self.stage = stage
        self.http_status = http_status


@dataclass(frozen=True)
class FirstTimeUserDoctorConfig:
    config_root: Path
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
    output_path: Path | None = None
    timeout_seconds: int = 30


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"first-time-user-doctor-{utc_timestamp()}.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def check(
    check_id: str,
    status: DoctorStatus,
    message: str,
    *,
    category: str,
    details: dict[str, Any] | None = None,
    next_action: str = "",
) -> dict[str, Any]:
    return {
        "id": check_id,
        "category": category,
        "status": status.value,
        "message": message,
        "details": details or {},
        "next_action": next_action,
    }


def wsl_path(path: Path) -> str:
    value = str(path).replace("\\", "/")
    drive_match = re.match(r"^(?P<drive>[A-Za-z]):/(?P<rest>.+)$", value)
    if drive_match:
        return f"/mnt/{drive_match.group('drive').lower()}/{drive_match.group('rest')}"
    return value


def api_key_bridge_details(config: FirstTimeUserDoctorConfig) -> dict[str, str]:
    cwd = wsl_path(config.config_root.resolve())
    env_name = config.api_key_env
    return {
        "windows_env_var": env_name,
        "wsl_env_bridge_required": "true",
        "powershell_wsl_env_example": (
            f"$key=$env:{env_name}; if (-not $key) {{ throw '{env_name} is not set in Windows environment' }}; "
            f"wsl.exe --cd {cwd} -- env \"{env_name}=$key\" "
            "python3 scripts/validate_post_restart_runtime_readiness.py"
        ),
        "bash_export_example": (
            f"export {env_name}=\"$(powershell.exe -NoProfile -Command "
            f"'[Console]::Out.Write([Environment]::GetEnvironmentVariable(\"{env_name}\",\"User\"))')\""
        ),
    }


def request_failure_next_action(exc: BaseException, fallback: str) -> str:
    if isinstance(exc, DoctorRequestError) and exc.diagnostic_kind == DoctorRequestDiagnostic.HEADERS_WITHOUT_BODY_TIMEOUT.value:
        return (
            "Retry the same validation from WSL/Bash. If Bash also times out waiting for body bytes, "
            f"restart the local gateway stack with `{STACK_RESTART_COMMAND}` and inspect upstream logs."
        )
    return fallback


def port_recovery_details(target: dict[str, Any]) -> dict[str, Any]:
    if target.get("name") == "model":
        return {
            "recovery_command": "Start vLLM manually using the command in VLLM_AGENT_HOST.md, then rerun the readiness validator.",
            "runtime_boundary": "vllm",
        }
    return {
        "recovery_command": STACK_RESTART_COMMAND,
        "runtime_boundary": "bash_gateway_stack",
    }


def port_next_action(target: dict[str, Any]) -> str:
    if target.get("name") == "model":
        return "Start vLLM manually using VLLM_AGENT_HOST.md, then restart the gateway stack from Bash."
    return f"Restart the local gateway/controller/proxy stack from Bash with `{STACK_RESTART_COMMAND}`."


def failed_check(check_id: str, message: str, *, category: str, details: dict[str, Any] | None = None, next_action: str) -> dict[str, Any]:
    return check(check_id, DoctorStatus.FAILED, message, category=category, details=details, next_action=next_action)


def origin_url(base_url: str) -> str:
    value = base_url.rstrip("/")
    if value.endswith("/v1"):
        value = value[:-3]
    return value.rstrip("/")


def openai_base_url(base_url: str) -> str:
    value = base_url.rstrip("/")
    return value if value.endswith("/v1") else value + "/v1"


def normalize_url(value: object) -> str:
    return str(value or "").rstrip("/")


def urls_match(left: object, right: object, *, strip_v1: bool = False) -> bool:
    left_value = normalize_url(left)
    right_value = normalize_url(right)
    if strip_v1:
        left_value = origin_url(left_value)
        right_value = origin_url(right_value)
    return left_value == right_value


def path_identities(raw: object) -> set[str]:
    if not isinstance(raw, str) or not raw.strip():
        return set()
    value = raw.strip().replace("\\", "/").rstrip("/")
    identities = {value.lower()}
    drive_match = re.match(r"^(?P<drive>[A-Za-z]):/(?P<rest>.+)$", value)
    if drive_match:
        drive = drive_match.group("drive").lower()
        if drive == "c":
            identities.add(f"/mnt/c/{drive_match.group('rest')}".lower())
    if value.lower().startswith("/mnt/c/"):
        identities.add(("C:/" + value[len("/mnt/c/") :]).lower())
    return identities


def contains_path(roots: list[str], expected: str) -> bool:
    expected_ids = path_identities(expected)
    for root in roots:
        for root_id in path_identities(root):
            normalized_root = root_id.rstrip("/")
            if not normalized_root:
                continue
            for expected_id in expected_ids:
                normalized_expected = expected_id.rstrip("/")
                if normalized_expected == normalized_root or normalized_expected.startswith(normalized_root + "/"):
                    return True
    return False


def find_key(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = find_key(child, key)
            if found is not None:
                return found
    if isinstance(value, list):
        for child in value:
            found = find_key(child, key)
            if found is not None:
                return found
    return None


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
        response = urllib.request.urlopen(request, timeout=timeout_seconds)
    except urllib.error.HTTPError as exc:
        try:
            body_text = exc.read().decode("utf-8", errors="replace")
        except (TimeoutError, socket.timeout) as body_exc:
            raise DoctorRequestError(
                f"headers received with HTTP {exc.code}, but response body timed out: {body_exc}",
                diagnostic_kind=DoctorRequestDiagnostic.HEADERS_WITHOUT_BODY_TIMEOUT,
                stage="body_read",
                http_status=exc.code,
            ) from body_exc
        try:
            body = json.loads(body_text)
        except json.JSONDecodeError:
            body = {"error": {"message": body_text, "code": "invalid_json_error_body"}}
        return exc.code, body
    except (TimeoutError, socket.timeout) as exc:
        raise DoctorRequestError(
            f"connection timed out before response headers: {exc}",
            diagnostic_kind=DoctorRequestDiagnostic.UNREACHABLE_PORT,
            stage="open",
        ) from exc
    except urllib.error.URLError as exc:
        raise DoctorRequestError(
            f"connection failed before response headers: {exc}",
            diagnostic_kind=DoctorRequestDiagnostic.UNREACHABLE_PORT,
            stage="open",
        ) from exc

    with response:
        status = int(response.status)
        try:
            body_text = response.read().decode("utf-8")
        except (TimeoutError, socket.timeout) as exc:
            raise DoctorRequestError(
                f"headers received with HTTP {status}, but response body timed out: {exc}",
                diagnostic_kind=DoctorRequestDiagnostic.HEADERS_WITHOUT_BODY_TIMEOUT,
                stage="body_read",
                http_status=status,
            ) from exc
        try:
            return status, json.loads(body_text)
        except json.JSONDecodeError as exc:
            raise DoctorRequestError(
                f"response body was not valid JSON after HTTP {status}: {exc}",
                diagnostic_kind=DoctorRequestDiagnostic.INVALID_JSON_BODY,
                stage="json_parse",
                http_status=status,
            ) from exc


def exception_details(exc: BaseException) -> dict[str, Any]:
    if isinstance(exc, DoctorRequestError):
        details: dict[str, Any] = {
            "diagnostic_kind": exc.diagnostic_kind,
            "stage": exc.stage,
        }
        if exc.http_status is not None:
            details["http_status"] = exc.http_status
        return details
    return {}


def run_get_json(url: str, *, headers: dict[str, str] | None, timeout_seconds: int) -> tuple[int, dict[str, Any]]:
    return json_request(url, headers=headers, timeout_seconds=timeout_seconds)


def port_health_checks(config: FirstTimeUserDoctorConfig) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for target in HEALTH_TARGETS:
        url = f"http://127.0.0.1:{target['port']}{target['path']}"
        try:
            status, body = run_get_json(url, headers=None, timeout_seconds=config.timeout_seconds)
            passed = status == 200
            checks.append(
                check(
                    f"port.{target['name']}",
                    DoctorStatus.PASSED if passed else DoctorStatus.FAILED,
                    f"{target['name']} returned HTTP {status}.",
                    category="port_health",
                    details={**target, "url": url, "http_status": status, "body_keys": sorted(body.keys()), **port_recovery_details(target)},
                    next_action="" if passed else port_next_action(target),
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                failed_check(
                    f"port.{target['name']}",
                    f"{target['name']} health check failed: {type(exc).__name__}: {exc}",
                    category="port_health",
                    details={**target, "url": url, **exception_details(exc), **port_recovery_details(target)},
                    next_action=request_failure_next_action(exc, port_next_action(target)),
                )
            )
    return checks


def gateway_config_checks(config: FirstTimeUserDoctorConfig) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    gateways = (
        {
            "id": "llm_gateway",
            "base_url": config.llm_gateway_base_url,
            "expected_routing": "explicit_envelope",
            "expected_controller_path": "/v1/controller/harness/chat/completions",
        },
        {
            "id": "workflow_router_gateway",
            "base_url": config.workflow_router_gateway_base_url,
            "expected_routing": "workflow_router",
            "expected_controller_path": "/v1/controller/workflow-router/chat/completions",
        },
    )
    for item in gateways:
        url = f"{origin_url(item['base_url'])}/__gateway/health"
        try:
            status, body = run_get_json(url, headers=None, timeout_seconds=config.timeout_seconds)
            if status != 200:
                checks.append(
                    failed_check(
                        f"gateway.{item['id']}",
                        f"{item['id']} internal health returned HTTP {status}.",
                        category="gateway_config",
                        details={"url": url, "http_status": status, "body": body},
                        next_action="Restart the gateway stack from Bash and inspect runtime-state gateway logs.",
                    )
                )
                continue
            target_ok = urls_match(body.get("target_base_url"), config.model_base_url, strip_v1=True)
            routing_ok = body.get("controller_routing") == item["expected_routing"]
            harness_url = str(body.get("controller_harness_url") or "")
            controller_ok = (
                harness_url.startswith(origin_url(config.controller_base_url))
                and harness_url.endswith(str(item["expected_controller_path"]))
            )
            passed = target_ok and routing_ok and controller_ok
            checks.append(
                check(
                    f"gateway.{item['id']}",
                    DoctorStatus.PASSED if passed else DoctorStatus.FAILED,
                    f"{item['id']} gateway configuration {'matches' if passed else 'does not match'} expected routing.",
                    category="gateway_config",
                    details={
                        "url": url,
                        "http_status": status,
                        "target_base_url": body.get("target_base_url"),
                        "expected_model_base_url": config.model_base_url,
                        "controller_routing": body.get("controller_routing"),
                        "expected_controller_routing": item["expected_routing"],
                        "controller_harness_url": body.get("controller_harness_url"),
                    },
                    next_action="" if passed else "Restart with start-agent-prompt-proxies.sh and the documented controller/gateway environment.",
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                failed_check(
                    f"gateway.{item['id']}",
                    f"{item['id']} internal health failed: {type(exc).__name__}: {exc}",
                    category="gateway_config",
                    details={"url": url, **exception_details(exc)},
                    next_action="Restart the gateway stack from Bash and inspect runtime-state gateway logs.",
                )
            )
    return checks


def load_roles(config: FirstTimeUserDoctorConfig) -> list[dict[str, Any]]:
    roles_path = config.roles_path if config.roles_path.is_absolute() else config.config_root / config.roles_path
    value = json.loads(roles_path.read_text(encoding="utf-8"))
    roles = value.get("roles") if isinstance(value, dict) else []
    return [item for item in roles if isinstance(item, dict)]


def role_proxy_checks(config: FirstTimeUserDoctorConfig) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    try:
        roles = load_roles(config)
    except Exception as exc:  # noqa: BLE001
        return [
            failed_check(
                "roles.manifest",
                f"Role manifest could not be loaded: {type(exc).__name__}: {exc}",
                category="role_proxy",
                next_action="Check runtime/roles.json before starting role prompt proxies.",
            )
        ]
    for role in roles:
        role_id = str(role.get("id") or "unknown")
        port = role.get("port")
        url = f"http://127.0.0.1:{port}/__proxy/health"
        if not isinstance(port, int):
            checks.append(
                failed_check(
                    f"role.{role_id}",
                    "Role entry has no integer port.",
                    category="role_proxy",
                    details={"role": role},
                    next_action="Fix runtime/roles.json.",
                )
            )
            continue
        try:
            status, body = run_get_json(url, headers=None, timeout_seconds=config.timeout_seconds)
            passed = status == 200 and body.get("role_key") == role.get("role") and body.get("subrole") == role.get("subrole")
            checks.append(
                check(
                    f"role.{role_id}",
                    DoctorStatus.PASSED if passed else DoctorStatus.FAILED,
                    f"{role_id} proxy {'matches' if passed else 'does not match'} runtime role metadata.",
                    category="role_proxy",
                    details={"url": url, "http_status": status, "body": body},
                    next_action="" if passed else "Restart role prompt proxies from Bash and inspect runtime-state proxy logs.",
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                failed_check(
                    f"role.{role_id}",
                    f"{role_id} proxy health failed: {type(exc).__name__}: {exc}",
                    category="role_proxy",
                    details={"url": url, **exception_details(exc)},
                    next_action="Restart role prompt proxies from Bash and inspect runtime-state proxy logs.",
                )
            )
    return checks


def controller_checks(config: FirstTimeUserDoctorConfig) -> list[dict[str, Any]]:
    url = f"{origin_url(config.controller_base_url)}/health"
    try:
        status, body = run_get_json(url, headers=None, timeout_seconds=config.timeout_seconds)
    except Exception as exc:  # noqa: BLE001
        return [
            failed_check(
                "controller.health",
                f"Controller health failed: {type(exc).__name__}: {exc}",
                category="controller",
                details={"url": url, **exception_details(exc)},
                next_action="Restart the controller with start-agent-prompt-proxies.sh from Bash.",
            )
        ]
    checks: list[dict[str, Any]] = []
    base_passed = status == 200 and body.get("kind") == "controller_service" and body.get("status") == "ok"
    checks.append(
        check(
            "controller.health",
            DoctorStatus.PASSED if base_passed else DoctorStatus.FAILED,
            "Controller health endpoint is reachable." if base_passed else "Controller health endpoint is not valid.",
            category="controller",
            details={"url": url, "http_status": status, "body": body},
            next_action="" if base_passed else "Restart the controller with start-agent-prompt-proxies.sh from Bash.",
        )
    )
    raw_roots = body.get("allowed_target_roots") if isinstance(body.get("allowed_target_roots"), list) else []
    allowed_roots = [str(root) for root in raw_roots]
    expected_roots = [str(config.config_root.resolve()), *config.target_roots]
    missing = [root for root in expected_roots if not contains_path(allowed_roots, root)]
    passed = not missing
    checks.append(
        check(
            "controller.allowed_roots",
            DoctorStatus.PASSED if passed else DoctorStatus.FAILED,
            "Controller allowed roots include the project and target fixtures."
            if passed
            else "Controller allowed roots are missing required project or fixture roots.",
            category="controller",
            details={"allowed_target_roots": allowed_roots, "expected_roots": expected_roots, "missing_roots": missing},
            next_action="" if passed else "Restart with CONTROLLER_ALLOWED_TARGET_ROOTS containing the project and both frozen fixtures.",
        )
    )
    return checks


def anythingllm_checks(config: FirstTimeUserDoctorConfig) -> list[dict[str, Any]]:
    api_key = os.environ.get(config.api_key_env)
    checks: list[dict[str, Any]] = []
    key_present = bool(api_key)
    checks.append(
        check(
                    "anythingllm.api_key",
                    DoctorStatus.PASSED if key_present else DoctorStatus.FAILED,
                    f"{config.api_key_env} is available." if key_present else f"{config.api_key_env} is missing.",
                    category="anythingllm",
                    details={"api_key_env": config.api_key_env, "api_key_available": key_present, **api_key_bridge_details(config)},
                    next_action="" if key_present else "Inject the Windows AnythingLLM API key into WSL with the `wsl.exe -- env` command shown in details.",
                )
            )
    if not api_key:
        for check_id in ("anythingllm.ping", "anythingllm.workspace", "anythingllm.target_url"):
            checks.append(
                check(
                    check_id,
                    DoctorStatus.SKIPPED,
                    "Skipped because the AnythingLLM API key is missing.",
                    category="anythingllm",
                    details=api_key_bridge_details(config),
                    next_action="Inject ANYTHINGLLM_API_KEY into WSL and rerun the readiness validator.",
                )
            )
        return checks
    api_root = config.anythingllm_api_base_url.rstrip("/")
    try:
        ping_status, ping_body = run_get_json(f"{api_root}/api/ping", headers=None, timeout_seconds=config.timeout_seconds)
        checks.append(
            check(
                "anythingllm.ping",
                DoctorStatus.PASSED if ping_status == 200 else DoctorStatus.FAILED,
                f"AnythingLLM ping returned HTTP {ping_status}.",
                category="anythingllm",
                details={"url": f"{api_root}/api/ping", "http_status": ping_status, "body": ping_body},
                next_action="" if ping_status == 200 else "Start AnythingLLM or correct --anythingllm-api-base-url.",
            )
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            failed_check(
                "anythingllm.ping",
                f"AnythingLLM ping failed: {type(exc).__name__}: {exc}",
                category="anythingllm",
                details={"url": f"{api_root}/api/ping", **exception_details(exc)},
                next_action="Start AnythingLLM or correct --anythingllm-api-base-url.",
            )
        )
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        workspace_status, workspace_body = run_get_json(
            f"{api_root}/api/v1/workspaces",
            headers=headers,
            timeout_seconds=config.timeout_seconds,
        )
        raw_workspaces = workspace_body.get("workspaces") if isinstance(workspace_body, dict) else []
        workspaces = raw_workspaces if isinstance(raw_workspaces, list) else []
        slugs = [str(item.get("slug")) for item in workspaces if isinstance(item, dict) and item.get("slug")]
        found = config.workspace in slugs
        workspace_message = (
            f"AnythingLLM workspace {config.workspace!r} {'was found' if found else 'was not found'}."
            if workspace_status == 200
            else f"AnythingLLM workspace lookup returned HTTP {workspace_status}."
        )
        workspace_next_action = (
            ""
            if found
            else "Create the workspace or pass --workspace with an existing AnythingLLM workspace slug."
            if workspace_status == 200
            else "Start AnythingLLM or correct --anythingllm-api-base-url."
        )
        checks.append(
            check(
                "anythingllm.workspace",
                DoctorStatus.PASSED if workspace_status == 200 and found else DoctorStatus.FAILED,
                workspace_message,
                category="anythingllm",
                details={
                    "url": f"{api_root}/api/v1/workspaces",
                    "http_status": workspace_status,
                    "workspace": config.workspace,
                    "workspace_found": found,
                    "workspace_slugs": slugs,
                },
                next_action=workspace_next_action,
            )
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            failed_check(
                "anythingllm.workspace",
                f"AnythingLLM workspace lookup failed: {type(exc).__name__}: {exc}",
                category="anythingllm",
                details={"url": f"{api_root}/api/v1/workspaces", **exception_details(exc)},
                next_action="Check ANYTHINGLLM_API_KEY and the AnythingLLM API base URL.",
            )
        )
    try:
        system_status, system_body = run_get_json(
            f"{api_root}/api/v1/system",
            headers=headers,
            timeout_seconds=config.timeout_seconds,
        )
        configured = find_key(system_body, "GenericOpenAiBasePath")
        if not isinstance(configured, str):
            checks.append(
                check(
                    "anythingllm.target_url",
                    DoctorStatus.WARNING,
                    "AnythingLLM system response did not expose GenericOpenAiBasePath.",
                    category="anythingllm",
                    details={"url": f"{api_root}/api/v1/system", "http_status": system_status},
                    next_action="Manually confirm AnythingLLM points at http://127.0.0.1:8500/v1 before prompt testing.",
                )
            )
        else:
            passed = urls_match(configured, config.expected_anythingllm_llm_base_url)
            checks.append(
                check(
                    "anythingllm.target_url",
                    DoctorStatus.PASSED if system_status == 200 and passed else DoctorStatus.FAILED,
                    "AnythingLLM points at the workflow-router gateway."
                    if passed
                    else "AnythingLLM does not point at the workflow-router gateway.",
                    category="anythingllm",
                    details={
                        "url": f"{api_root}/api/v1/system",
                        "http_status": system_status,
                        "GenericOpenAiBasePath": configured,
                        "expected": config.expected_anythingllm_llm_base_url,
                    },
                    next_action="" if passed else "Set AnythingLLM Generic OpenAI base URL to http://127.0.0.1:8500/v1.",
                )
            )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            failed_check(
                "anythingllm.target_url",
                f"AnythingLLM system lookup failed: {type(exc).__name__}: {exc}",
                category="anythingllm",
                details={"url": f"{api_root}/api/v1/system", **exception_details(exc)},
                next_action="Check ANYTHINGLLM_API_KEY and the AnythingLLM API base URL.",
            )
        )
    return checks


def fixture_checks(config: FirstTimeUserDoctorConfig) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    try:
        manifest = load_fixture_manifest(config.config_root, config.manifest_path)
        entries = fixture_entries(config.config_root, manifest)
    except Exception as exc:  # noqa: BLE001
        return [
            failed_check(
                "fixtures.manifest",
                f"Fixture manifest failed validation: {type(exc).__name__}: {exc}",
                category="fixtures",
                next_action="Fix runtime/fixtures.json before running live validation.",
            )
        ]
    checks.append(
        check(
            "fixtures.manifest",
            DoctorStatus.PASSED,
            "Fixture manifest is valid.",
            category="fixtures",
            details={"manifest_path": str(config.manifest_path), "fixture_count": len(entries)},
        )
    )
    entry_by_identity: dict[str, Any] = {}
    for entry in entries:
        for identity in path_identities(str(entry.source_path)):
            entry_by_identity[identity] = entry
    for raw_root in config.target_roots:
        resolved = resolve_path(config.config_root, raw_root)
        root_id = next((identity for identity in path_identities(str(resolved)) if identity in entry_by_identity), None)
        entry = entry_by_identity.get(root_id or "")
        if entry is None:
            checks.append(
                failed_check(
                    f"fixtures.{raw_root}",
                    "Target root is not represented in runtime/fixtures.json.",
                    category="fixtures",
                    details={"target_root": raw_root, "resolved": str(resolved)},
                    next_action="Add the target root to runtime/fixtures.json before using it in acceptance tests.",
                )
            )
            continue
        try:
            snapshot = fixture_snapshot(entry)
            git_status = snapshot.get("git_status")
            git_clean = True if git_status is None else bool(git_status.get("clean"))
            eol_only_dirty = False if git_clean or git_status is None else git_diff_ignoring_eol_is_clean(entry.source_path)
            watched_ok = bool(snapshot.get("watched_hashes"))
            status = DoctorStatus.PASSED if watched_ok and git_clean else DoctorStatus.FAILED
            if watched_ok and eol_only_dirty:
                status = DoctorStatus.WARNING
            checks.append(
                check(
                    f"fixtures.{entry.fixture_id}",
                    status,
                    fixture_status_message(entry.fixture_id, git_status=git_status, eol_only_dirty=eol_only_dirty),
                    category="fixtures",
                    details={
                        "target_root": raw_root,
                        "fixture_id": entry.fixture_id,
                        "source_path": str(entry.source_path),
                        "watched_hash_count": len(snapshot.get("watched_hashes") or {}),
                        "git_status": git_status,
                        "git_eol_only_dirty": eol_only_dirty,
                    },
                    next_action=fixture_next_action(git_status=git_status, eol_only_dirty=eol_only_dirty, watched_ok=watched_ok),
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                failed_check(
                    f"fixtures.{entry.fixture_id}",
                    f"Fixture snapshot failed: {type(exc).__name__}: {exc}",
                    category="fixtures",
                    details={"target_root": raw_root, "fixture_id": entry.fixture_id},
                    next_action="Inspect the fixture path and watched files before running live validation.",
                )
            )
    return checks


def git_diff_ignoring_eol_is_clean(root: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root), "diff", "--ignore-space-at-eol", "--quiet"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def fixture_status_message(fixture_id: str, *, git_status: object, eol_only_dirty: bool) -> str:
    if git_status is None:
        return f"Fixture {fixture_id} is present with watched hashes."
    if eol_only_dirty:
        return f"Fixture {fixture_id} has watched hashes and only line-ending git noise from Bash."
    if isinstance(git_status, dict) and git_status.get("clean"):
        return f"Fixture {fixture_id} is present with watched hashes and clean git status."
    return f"Fixture {fixture_id} has watched hashes but Bash git status is dirty."


def fixture_next_action(*, git_status: object, eol_only_dirty: bool, watched_ok: bool) -> str:
    if not watched_ok:
        return "Restore the fixture watched files before running AnythingLLM tests."
    if eol_only_dirty:
        return "Line-ending-only dirtiness is not blocking; align Git line-ending settings if Bash-clean status is required."
    if isinstance(git_status, dict) and not git_status.get("clean"):
        return "Restore the frozen fixture before running AnythingLLM tests."
    return ""


def status_counts(checks: list[dict[str, Any]]) -> dict[str, int]:
    counts = {status.value: 0 for status in DoctorStatus}
    for item in checks:
        status = str(item.get("status") or DoctorStatus.FAILED.value)
        counts[status] = counts.get(status, 0) + 1
    return counts


def category_counts(checks: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in checks:
        category = str(item.get("category") or "unknown")
        counts[category] = counts.get(category, 0) + 1
    return counts


def run_first_time_user_doctor(config: FirstTimeUserDoctorConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root)
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "first_time_user_doctor_report",
        "status": DoctorStatus.FAILED.value,
        "created_at": utc_timestamp(),
        "config": {
            "model_base_url": config.model_base_url,
            "llm_gateway_base_url": config.llm_gateway_base_url,
            "workflow_router_gateway_base_url": config.workflow_router_gateway_base_url,
            "controller_base_url": config.controller_base_url,
            "anythingllm_api_base_url": config.anythingllm_api_base_url,
            "workspace": config.workspace,
            "expected_anythingllm_llm_base_url": config.expected_anythingllm_llm_base_url,
            "api_key_env": config.api_key_env,
            "target_roots": list(config.target_roots),
            "manifest_path": str(config.manifest_path),
            "roles_path": str(config.roles_path),
            "timeout_seconds": config.timeout_seconds,
        },
        "checks": [],
        "summary": {},
        "errors": [],
    }
    checks: list[dict[str, Any]] = []
    try:
        checks.extend(port_health_checks(config))
        checks.extend(gateway_config_checks(config))
        checks.extend(role_proxy_checks(config))
        checks.extend(controller_checks(config))
        checks.extend(anythingllm_checks(config))
        checks.extend(fixture_checks(config))
        report["checks"] = checks
        counts = status_counts(checks)
        report["summary"] = {
            "check_count": len(checks),
            "status_counts": counts,
            "category_counts": category_counts(checks),
            "failed_check_ids": [item["id"] for item in checks if item.get("status") == DoctorStatus.FAILED.value],
            "warning_check_ids": [item["id"] for item in checks if item.get("status") == DoctorStatus.WARNING.value],
        }
        report["status"] = DoctorStatus.PASSED.value if counts.get(DoctorStatus.FAILED.value, 0) == 0 else DoctorStatus.FAILED.value
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"{type(exc).__name__}: {exc}")
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
