"""AnythingLLM Desktop UI E2E validation helpers."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.run_inspector import mnt_path_to_windows


DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_REPORT_DIR = Path("runtime-state") / "anythingllm-ui"
DEFAULT_TARGET_ROOTS = (
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
)
DEFAULT_MARKERS = (
    "workflow_router.plan completed",
    "selected_workflow: code_investigation.plan",
    "run_id:",
    "Answer:",
)
WATCHED_RELATIVE_PATHS = (
    "README.md",
    "agent.md",
    "configuration.py",
    "dashboard_server.py",
    "main.py",
    "business/lot_config.py",
    "core/orderbook.py",
    "core/stealth_order_manager.py",
    "database/order.py",
    "docs/agents/INVARIANTS.md",
    "tests/test_dashboard_handler.py",
    "tests/test_lot_tracking_integration.py",
    "tests/unit/test_order_id_and_followup_rules.py",
    "tests/unit/test_orderbook_v2.py",
)


class AnythingLLMUiE2EStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class AnythingLLMUiE2EConfig:
    config_root: Path
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    target_roots: tuple[str, ...] = DEFAULT_TARGET_ROOTS
    output_path: Path | None = None
    ui_dist_root: Path | None = None
    app_asar_path: Path | None = None
    extract_root: Path | None = None
    refresh_extract: bool = False
    npx_command: str | None = None
    browser_channel: str = "chrome"
    timeout_seconds: int = 420
    static_port: int | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"anythingllm-ui-e2e-{utc_timestamp()}.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def json_request(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_seconds: int = 30,
) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
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
            body = {"text": text}
        return exc.code, body


def host_path(path_value: str) -> Path:
    converted = mnt_path_to_windows(path_value)
    if converted is not None:
        return converted
    return Path(path_value)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def watched_hashes(target_root: str) -> dict[str, str]:
    root = host_path(target_root)
    hashes: dict[str, str] = {}
    for relative_path in WATCHED_RELATIVE_PATHS:
        path = root / relative_path
        if path.exists():
            hashes[relative_path] = sha256_file(path)
    if not hashes:
        raise RuntimeError(f"{target_root} did not contain watched validation files on host path {root}")
    return hashes


def git_status(target_root: str) -> str | None:
    root = host_path(target_root)
    if not (root / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "-C", str(root), "status", "--short"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def fixture_state(target_roots: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    return {
        target_root: {
            "host_path": str(host_path(target_root)),
            "hashes": watched_hashes(target_root),
            "git_status": git_status(target_root),
        }
        for target_root in sorted(set(target_roots))
    }


def anythingllm_preflight(config: AnythingLLMUiE2EConfig, api_key: str) -> dict[str, Any]:
    api_root = config.anythingllm_api_base_url.rstrip("/")
    ping_status, ping_body = json_request(f"{api_root}/api/ping", timeout_seconds=min(30, config.timeout_seconds))
    workspaces_status, workspaces_body = json_request(
        f"{api_root}/api/v1/workspaces",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=min(30, config.timeout_seconds),
    )
    workspaces = workspaces_body.get("workspaces") if isinstance(workspaces_body, dict) else []
    slugs = [item.get("slug") for item in workspaces if isinstance(item, dict)]
    return {
        "status": AnythingLLMUiE2EStatus.PASSED.value
        if ping_status == 200 and workspaces_status == 200 and config.workspace in slugs
        else AnythingLLMUiE2EStatus.FAILED.value,
        "ping_status": ping_status,
        "workspace_status": workspaces_status,
        "workspace": config.workspace,
        "workspace_found": config.workspace in slugs,
        "workspace_slugs": slugs,
        "ping": ping_body,
    }


def default_app_asar_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return Path("C:/Users") / os.environ.get("USERNAME", "") / "AppData/Local/Programs/AnythingLLM/resources/app.asar"
    return Path(local_app_data) / "Programs" / "AnythingLLM" / "resources" / "app.asar"


def find_npx_command(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    for candidate in ("npx.cmd", "npx"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise RuntimeError("npx was not found; install Node.js/npm or pass --npx-command")


def resolve_ui_dist_root(config: AnythingLLMUiE2EConfig) -> Path:
    if config.ui_dist_root is not None:
        dist_root = config.ui_dist_root
        if not (dist_root / "index.html").exists():
            raise RuntimeError(f"ui dist root does not contain index.html: {dist_root}")
        return dist_root

    extract_root = config.extract_root or (config.config_root / DEFAULT_REPORT_DIR / "asar-dist")
    dist_root = extract_root / "dist"
    if not config.refresh_extract and (dist_root / "index.html").exists():
        return dist_root

    app_asar = config.app_asar_path or default_app_asar_path()
    if not app_asar.exists():
        raise RuntimeError(f"AnythingLLM app.asar was not found: {app_asar}")
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["NODE_OPTIONS"] = "--use-system-ca"
    command = [find_npx_command(config.npx_command), "--yes", "asar", "extract", str(app_asar), str(extract_root)]
    result = subprocess.run(command, check=False, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(
            "failed to extract AnythingLLM app.asar: "
            + json.dumps({"command": command, "stdout": result.stdout[-1000:], "stderr": result.stderr[-1000:]})
        )
    if not (dist_root / "index.html").exists():
        raise RuntimeError(f"extracted AnythingLLM UI did not contain dist/index.html under {extract_root}")
    return dist_root


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_http(url: str, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            status, _body = json_request(url, timeout_seconds=2)
            if status == 200:
                return
        except Exception as exc:  # pragma: no cover - diagnostic detail only
            last_error = exc
        time.sleep(1)
    raise RuntimeError(f"static UI server did not become ready at {url}: {last_error}")


def start_static_server(dist_root: Path, *, port: int, npx_command: str) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["NODE_OPTIONS"] = "--use-system-ca"
    command = [
        npx_command,
        "--yes",
        "http-server",
        str(dist_root),
        "-p",
        str(port),
        "-a",
        "127.0.0.1",
        "--cors",
        "-c-1",
        "--silent",
    ]
    return subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def api_base_for_ui(anythingllm_api_base_url: str) -> str:
    return anythingllm_api_base_url.rstrip("/") + "/api"


def build_electron_require_shim(api_base_url: str) -> str:
    api_base = json.dumps(api_base_for_ui(api_base_url))
    return f"""
(() => {{
  const API_BASE = {api_base};
  const listeners = new Map();
  const emit = (channel, payload) => setTimeout(() => {{
    (listeners.get(channel) || []).forEach((handler) => handler({{}}, payload));
  }}, 0);
  const ipcRenderer = {{
    on(channel, handler) {{
      const list = listeners.get(channel) || [];
      list.push(handler);
      listeners.set(channel, list);
      if (channel === "backend-server-online") {{
        emit(channel, {{
          API_BASE,
          APP_VERSION: "phase71-browser-e2e",
          APP_PLATFORM: "browser",
          APP_ARCH: "x64"
        }});
      }}
      return this;
    }},
    once(channel, handler) {{
      const wrap = (...args) => {{
        this.removeListener(channel, wrap);
        handler(...args);
      }};
      return this.on(channel, wrap);
    }},
    off(channel, handler) {{ return this.removeListener(channel, handler); }},
    removeListener(channel, handler) {{
      const list = listeners.get(channel) || [];
      listeners.set(channel, list.filter((item) => item !== handler));
      return this;
    }},
    removeAllListeners(channel) {{
      if (channel) listeners.delete(channel); else listeners.clear();
      return this;
    }},
    send() {{ return undefined; }},
    sendSync(channel) {{
      if (channel === "electron-store-get-data") {{
        return {{ defaultCwd: ".", appVersion: "phase71-browser-e2e" }};
      }}
      return null;
    }},
    invoke() {{ return Promise.resolve(null); }},
    emit(channel, ...args) {{
      (listeners.get(channel) || []).forEach((handler) => handler({{}}, ...args));
      return true;
    }},
    addListener(channel, handler) {{ return this.on(channel, handler); }},
    eventNames() {{ return Array.from(listeners.keys()); }},
    listenerCount(channel) {{ return (listeners.get(channel) || []).length; }},
    listeners(channel) {{ return listeners.get(channel) || []; }},
    getMaxListeners() {{ return 100; }},
    setMaxListeners() {{ return this; }},
    prependListener(channel, handler) {{ return this.on(channel, handler); }},
    prependOnceListener(channel, handler) {{ return this.once(channel, handler); }},
    rawListeners(channel) {{ return listeners.get(channel) || []; }},
    postMessage() {{}},
    sendTo() {{}},
    sendToHost() {{}}
  }};
  const electron = {{
    ipcRenderer,
    webFrame: {{ setZoomFactor() {{}} }},
    shell: {{ openExternal() {{}} }},
    clipboard: {{}},
    contextBridge: {{}},
    crashReporter: {{}},
    nativeImage: {{}},
    app: {{}},
    nativeTheme: {{}},
    screen: {{}},
    session: {{}},
    dialog: {{}}
  }};
  window.require = (name) => name === "electron" ? electron : {{}};
}})();
"""


def build_auth_init_script(api_key: str) -> str:
    token = json.dumps(api_key)
    return f"""
(() => {{
  localStorage.setItem("anythingllm_authToken", {token} || "x");
  localStorage.setItem("anythingllm_authTimestamp", String(Date.now()));
  localStorage.setItem("anythingllm_user", JSON.stringify({{ id: 1, username: "phase71-e2e" }}));
}})();
"""


def tracking_tag(target_root: str) -> str:
    digest = hashlib.sha1(f"{target_root}-{time.time_ns()}".encode("utf-8")).hexdigest()[:12]
    return f"phase71-ui-e2e-{digest}"


def prompt_for_target(target_root: str, tag: str) -> str:
    return (
        f"In {target_root}, find where the placed_order_id stealth lookup begins. "
        "Read only. Return the entrypoint, evidence files, related tests, and confidence. "
        f"Tracking tag: {tag}"
    )


def segment_after_new_tag(text: str, tag: str, minimum_index: int) -> str:
    start_at = max(0, minimum_index - 1000)
    index = text.find(tag, start_at)
    if index < 0:
        return ""
    return text[index + len(tag) :]


def marker_hits(text: str, markers: tuple[str, ...] = DEFAULT_MARKERS) -> dict[str, bool]:
    return {marker: marker in text for marker in markers}


def ui_case_passed(case: dict[str, Any], markers: tuple[str, ...] = DEFAULT_MARKERS) -> bool:
    hits = case.get("marker_hits_after_tag")
    if not isinstance(hits, dict):
        return False
    return all(bool(hits.get(marker)) for marker in markers) and bool(case.get("stream_chat_seen"))


def non_ignored_request_failures(failures: list[dict[str, str]]) -> list[dict[str, str]]:
    ignored_suffixes = ("/api/system/logo?theme=system",)
    return [item for item in failures if not any(item.get("url", "").endswith(suffix) for suffix in ignored_suffixes)]


def ignored_request_failures(failures: list[dict[str, str]]) -> list[dict[str, str]]:
    ignored_suffixes = ("/api/system/logo?theme=system",)
    return [item for item in failures if any(item.get("url", "").endswith(suffix) for suffix in ignored_suffixes)]


def body_text(page: Any) -> str:
    return page.evaluate("document.body ? document.body.innerText : ''") or ""


def request_failure_text(request: Any) -> str:
    try:
        failure = request.failure
        if callable(failure):
            failure = failure()
        if isinstance(failure, dict):
            return str(failure.get("errorText", ""))
        return str(failure)
    except Exception as exc:  # pragma: no cover - diagnostic detail only
        return f"failure-capture-error:{exc}"


def run_browser_case(
    *,
    page: Any,
    workspace: str,
    target_root: str,
    tag: str,
    static_origin: str,
    screenshot_dir: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    prompt = prompt_for_target(target_root, tag)
    ui_url = f"{static_origin}/#/workspace/{workspace}"
    page.goto(ui_url, wait_until="load", timeout=60_000)
    page.wait_for_selector("textarea", timeout=60_000)
    initial_text = body_text(page)
    before_screenshot = screenshot_dir / f"{tag}-before.png"
    after_screenshot = screenshot_dir / f"{tag}-after.png"
    page.screenshot(path=str(before_screenshot), full_page=True)

    textarea = page.locator("textarea").first
    textarea.fill(prompt)
    response_start_index = len(page.context._phase71_responses)  # type: ignore[attr-defined]
    textarea.press("Enter")
    time.sleep(2)
    if tag not in body_text(page)[len(initial_text) :]:
        textarea.fill(prompt)
        textarea.press("Control+Enter")
        time.sleep(2)

    deadline = time.time() + timeout_seconds
    snapshots: list[dict[str, Any]] = []
    latest_segment = ""
    latest_hits = marker_hits("")
    while time.time() < deadline:
        text = body_text(page)
        latest_segment = segment_after_new_tag(text, tag, len(initial_text))
        latest_hits = marker_hits(latest_segment)
        snapshots.append(
            {
                "elapsed_seconds": int(timeout_seconds - max(0, deadline - time.time())),
                "segment_length": len(latest_segment),
                "marker_hits_after_tag": latest_hits,
                "segment_tail": latest_segment[-1200:],
            }
        )
        responses = page.context._phase71_responses[response_start_index:]  # type: ignore[attr-defined]
        stream_chat_seen = any(
            str(item.get("url", "")).endswith(f"/api/workspace/{workspace}/stream-chat")
            and int(item.get("status", 0)) == 200
            for item in responses
        )
        if all(latest_hits.values()) and stream_chat_seen:
            break
        time.sleep(5)

    page.screenshot(path=str(after_screenshot), full_page=True)
    responses = page.context._phase71_responses[response_start_index:]  # type: ignore[attr-defined]
    stream_chat_seen = any(
        str(item.get("url", "")).endswith(f"/api/workspace/{workspace}/stream-chat")
        and int(item.get("status", 0)) == 200
        for item in responses
    )
    result = {
        "target_root": target_root,
        "tracking_tag": tag,
        "prompt": prompt,
        "status": AnythingLLMUiE2EStatus.PASSED.value
        if all(latest_hits.values()) and stream_chat_seen
        else AnythingLLMUiE2EStatus.FAILED.value,
        "marker_hits_after_tag": latest_hits,
        "stream_chat_seen": stream_chat_seen,
        "stream_chat_response_count": sum(1 for item in responses if "/stream-chat" in str(item.get("url", ""))),
        "segment_after_tag_tail": latest_segment[-8000:],
        "snapshots_tail": snapshots[-8:],
        "before_screenshot": str(before_screenshot.resolve()),
        "after_screenshot": str(after_screenshot.resolve()),
    }
    return result


def run_browser_validation(
    *,
    config: AnythingLLMUiE2EConfig,
    dist_root: Path,
    api_key: str,
    port: int,
    screenshot_dir: Path,
) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError("Python Playwright is not installed; run `pip install playwright`") from exc

    screenshot_dir.mkdir(parents=True, exist_ok=True)
    static_origin = f"http://127.0.0.1:{port}"
    cases: list[dict[str, Any]] = []
    console_messages: list[dict[str, str]] = []
    page_errors: list[str] = []
    request_failures: list[dict[str, str]] = []
    responses: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=config.browser_channel, headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context._phase71_responses = responses  # type: ignore[attr-defined]
        context.add_init_script(build_electron_require_shim(config.anythingllm_api_base_url))
        context.add_init_script(build_auth_init_script(api_key))
        page = context.new_page()
        page.on(
            "console",
            lambda message: console_messages.append({"type": message.type, "text": message.text[:1000]}),
        )
        page.on("pageerror", lambda exc: page_errors.append(str(exc)[:1200]))
        page.on(
            "requestfailed",
            lambda request: request_failures.append(
                {"url": request.url, "failure": request_failure_text(request)}
            ),
        )
        page.on(
            "response",
            lambda response: responses.append(
                {
                    "url": response.url,
                    "status": response.status,
                    "content_type": response.headers.get("content-type", ""),
                }
            )
            if (str(port) in response.url or "3001" in response.url)
            else None,
        )

        for target_root in config.target_roots:
            cases.append(
                run_browser_case(
                    page=page,
                    workspace=config.workspace,
                    target_root=target_root,
                    tag=tracking_tag(target_root),
                    static_origin=static_origin,
                    screenshot_dir=screenshot_dir,
                    timeout_seconds=config.timeout_seconds,
                )
            )
        browser.close()

    ignored_failures = ignored_request_failures(request_failures)
    unexpected_failures = non_ignored_request_failures(request_failures)
    return {
        "status": AnythingLLMUiE2EStatus.PASSED.value
        if all(ui_case_passed(case) for case in cases) and not page_errors and not unexpected_failures
        else AnythingLLMUiE2EStatus.FAILED.value,
        "static_origin": static_origin,
        "ui_dist_root": str(dist_root.resolve()),
        "cases": cases,
        "console_tail": console_messages[-20:],
        "page_errors": page_errors,
        "request_failures": request_failures,
        "ignored_request_failures": ignored_failures,
        "non_ignored_request_failures": unexpected_failures,
        "response_count": len(responses),
        "responses_tail": responses[-30:],
    }


def run_anythingllm_ui_e2e(config: AnythingLLMUiE2EConfig) -> dict[str, Any]:
    output_path = config.output_path or default_report_path(config.config_root)
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "anythingllm_ui_e2e_report",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": AnythingLLMUiE2EStatus.FAILED.value,
        "config": {
            "anythingllm_api_base_url": config.anythingllm_api_base_url,
            "workspace": config.workspace,
            "target_roots": list(config.target_roots),
            "browser_channel": config.browser_channel,
            "timeout_seconds": config.timeout_seconds,
        },
        "anythingllm_preflight": {},
        "fixture_state_before": {},
        "fixture_state_after": {},
        "ui": {},
        "errors": [],
    }
    server: subprocess.Popen[str] | None = None
    try:
        api_key = os.environ.get(config.api_key_env)
        if not api_key:
            raise RuntimeError(f"{config.api_key_env} is required for AnythingLLM UI E2E")
        report["fixture_state_before"] = fixture_state(config.target_roots)
        report["anythingllm_preflight"] = anythingllm_preflight(config, api_key)
        if report["anythingllm_preflight"].get("status") != AnythingLLMUiE2EStatus.PASSED.value:
            raise RuntimeError("AnythingLLM preflight failed")

        dist_root = resolve_ui_dist_root(config)
        port = config.static_port or free_port()
        npx_command = find_npx_command(config.npx_command)
        server = start_static_server(dist_root, port=port, npx_command=npx_command)
        wait_for_http(f"http://127.0.0.1:{port}/", timeout_seconds=30)

        mimetypes.add_type("application/javascript", ".js")
        screenshot_dir = output_path.parent / output_path.stem
        report["ui"] = run_browser_validation(
            config=config,
            dist_root=dist_root,
            api_key=api_key,
            port=port,
            screenshot_dir=screenshot_dir,
        )
        report["fixture_state_after"] = fixture_state(config.target_roots)
        fixture_unchanged = report["fixture_state_before"] == report["fixture_state_after"]
        report["fixture_unchanged"] = fixture_unchanged
        if not fixture_unchanged:
            report["errors"].append("protected fixture state changed")
        if report["ui"].get("status") != AnythingLLMUiE2EStatus.PASSED.value:
            report["errors"].append("AnythingLLM browser UI validation failed")
        report["status"] = (
            AnythingLLMUiE2EStatus.PASSED.value
            if not report["errors"] and fixture_unchanged
            else AnythingLLMUiE2EStatus.FAILED.value
        )
    except Exception as exc:
        report["errors"].append(str(exc))
        report["status"] = AnythingLLMUiE2EStatus.FAILED.value
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
        report["report_path"] = str(output_path.resolve())
        write_json(output_path, report)
    return report
