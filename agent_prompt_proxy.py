#!/usr/bin/env python3
"""Small OpenAI-compatible prompt-injection proxy for local vLLM agents."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import signal
import sys
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


DEFAULT_ROLES = {
    8101: ("reviewer/code", "reviewer", "code", "roles/reviewer/code.md", "REVIEWER"),
    8102: ("tester/code", "tester", "code", "roles/tester/code.md", "TESTER"),
    8201: ("architect/default", "architect", "default", "roles/architect/default.md", "ARCHITECT"),
    8202: ("dispatcher/default", "dispatcher", "default", "roles/dispatcher/default.md", "DISPATCHER"),
    8203: ("implementer/default", "implementer", "default", "roles/implementer/default.md", "IMPLEMENTER"),
    8204: ("researcher/default", "researcher", "default", "roles/researcher/default.md", "RESEARCHER"),
    8205: ("documenter/default", "documenter", "default", "roles/documenter/default.md", "DOCUMENTER"),
}

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


@dataclass(frozen=True)
class RoleDefinition:
    port: int
    role_file: Path
    role_name: str
    role: str
    subrole: str
    expected_role: str


@dataclass(frozen=True)
class ProxyConfig:
    host: str
    target_base_url: str
    bootstrap_file: Path
    role_file: Path
    role_name: str
    role: str
    subrole: str
    expected_role: str


def _safe_stdout(message: str) -> None:
    try:
        sys.stdout.write(message)
        sys.stdout.flush()
    except OSError:
        pass


def _read_prompt(prompt_file: Path, label: str) -> str:
    try:
        content = prompt_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return (
            f"Required {label} prompt file is missing: {prompt_file}. "
            "Stop and report this configuration error before doing other work."
        )
    if not content:
        return (
            f"Required {label} prompt file is empty: {prompt_file}. "
            "Stop and report this configuration error before doing other work."
        )
    return content


def _build_prompt(config: ProxyConfig) -> str:
    bootstrap = _read_prompt(config.bootstrap_file, "bootstrap")
    role = _read_prompt(config.role_file, "role")
    return f"Bootstrap instructions:\n{bootstrap}\n\nRole instructions:\n{role}"


def _as_string(value: Any, field: str) -> str:
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"Manifest field '{field}' must be a non-empty string.")


def _as_int(value: Any, field: str) -> int:
    if isinstance(value, int):
        return value
    raise ValueError(f"Manifest field '{field}' must be an integer.")


def _role_path(prompt_dir: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return prompt_dir / path


def _fallback_roles(prompt_dir: Path) -> list[RoleDefinition]:
    definitions: list[RoleDefinition] = []
    for port, (role_name, role, subrole, filename, expected_role) in DEFAULT_ROLES.items():
        definitions.append(
            RoleDefinition(
                port=port,
                role_file=prompt_dir / filename,
                role_name=role_name,
                role=role,
                subrole=subrole,
                expected_role=expected_role,
            )
        )
    return definitions


def _load_role_definitions(prompt_dir: Path, manifest_path: Path) -> list[RoleDefinition]:
    if not manifest_path.exists():
        return _fallback_roles(prompt_dir)

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid role manifest JSON: {manifest_path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError(f"Role manifest must contain a JSON object: {manifest_path}")
    raw_roles = manifest.get("roles")
    if not isinstance(raw_roles, list) or not raw_roles:
        raise ValueError(f"Role manifest must contain a non-empty roles list: {manifest_path}")

    definitions: list[RoleDefinition] = []
    seen_ports: set[int] = set()
    for index, raw_role in enumerate(raw_roles):
        if not isinstance(raw_role, dict):
            raise ValueError(f"Manifest role at index {index} must be an object.")
        port = _as_int(raw_role.get("port"), f"roles[{index}].port")
        if port in seen_ports:
            raise ValueError(f"Duplicate role port in manifest: {port}")
        seen_ports.add(port)

        role = _as_string(raw_role.get("role"), f"roles[{index}].role")
        subrole = _as_string(raw_role.get("subrole", "default"), f"roles[{index}].subrole")
        role_name = _as_string(raw_role.get("id", f"{role}/{subrole}"), f"roles[{index}].id")
        expected_role = _as_string(raw_role.get("expected_role", role.upper()), f"roles[{index}].expected_role")
        role_file = _role_path(prompt_dir, _as_string(raw_role.get("prompt_file"), f"roles[{index}].prompt_file"))

        definitions.append(
            RoleDefinition(
                port=port,
                role_file=role_file,
                role_name=role_name,
                role=role,
                subrole=subrole,
                expected_role=expected_role,
            )
        )
    return definitions


def _text_preview(value: Any, limit: int = 1000) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=True)
    if len(text) <= limit:
        return text
    return text[-limit:]


def _debug_logging_enabled() -> bool:
    return os.environ.get("AGENT_PROMPT_PROXY_DEBUG") == "1"


def _debug_log(config: ProxyConfig, path: str, body: dict[str, Any], changed: bool, prompt: str) -> None:
    if not _debug_logging_enabled():
        return
    if urlsplit(path).path != "/v1/messages":
        return
    messages = body.get("messages")
    if isinstance(messages, list):
        roles = [item.get("role") if isinstance(item, dict) else type(item).__name__ for item in messages]
    else:
        roles = []
    system = body.get("system")
    entry = {
        "path": path,
        "role_name": config.role_name,
        "changed": changed,
        "keys": sorted(body.keys()),
        "system_type": type(system).__name__,
        "system_contains_prompt": prompt in _text_preview(system, limit=200000),
        "system_contains_tester": "Tester" in _text_preview(system, limit=200000),
        "system_contains_claude_code": "Claude Code" in _text_preview(system, limit=200000),
        "system_tail": _text_preview(system),
        "message_count": len(messages) if isinstance(messages, list) else None,
        "message_roles": roles[-10:],
    }
    configured_log_path = os.environ.get("AGENT_PROMPT_PROXY_DEBUG_LOG")
    log_path = Path(configured_log_path) if configured_log_path else config.role_file.parent / "agent-prompt-proxy.debug.jsonl"
    if not log_path.is_absolute():
        log_path = config.role_file.parent / log_path
    try:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
    except OSError:
        pass


def _prepend_text(existing: Any, prefix: str) -> str:
    if existing is None:
        return prefix
    if isinstance(existing, str):
        if existing.startswith(prefix):
            return existing
        return f"{prefix}\n\n{existing}"
    return f"{prefix}\n\n{json.dumps(existing, ensure_ascii=True)}"


def _append_text(existing: Any, suffix: str) -> str:
    if existing is None:
        return suffix
    if isinstance(existing, str):
        if existing.endswith(suffix):
            return existing
        return f"{existing}\n\n{suffix}"
    return f"{json.dumps(existing, ensure_ascii=True)}\n\n{suffix}"


def _append_to_content(content: Any, suffix: str) -> Any:
    if isinstance(content, str):
        return _append_text(content, suffix)
    if isinstance(content, list):
        return [
            *content,
            {
                "type": "text",
                "text": suffix,
            },
        ]
    return _append_text(content, suffix)


def _append_to_last_user_message(body: dict[str, Any], suffix: str) -> bool:
    messages = body.get("messages")
    if not isinstance(messages, list):
        return False
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        updated = dict(message)
        updated["content"] = _append_to_content(updated.get("content", ""), suffix)
        messages[index] = updated
        body["messages"] = messages
        return True
    messages.append({"role": "user", "content": suffix})
    body["messages"] = messages
    return True


def _inject_chat_messages(body: dict[str, Any], prompt: str) -> bool:
    messages = body.get("messages")
    if not isinstance(messages, list):
        return False

    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        messages[0] = dict(messages[0])
        messages[0]["content"] = _prepend_text(messages[0].get("content"), prompt)
    else:
        messages.insert(0, {"role": "system", "content": prompt})
    body["messages"] = messages
    return True


def _inject_responses(body: dict[str, Any], prompt: str) -> bool:
    body["instructions"] = _prepend_text(body.get("instructions"), prompt)
    return True


def _inject_completions(body: dict[str, Any], prompt: str) -> bool:
    value = body.get("prompt")
    if isinstance(value, str):
        body["prompt"] = _prepend_text(value, prompt)
        return True
    if isinstance(value, list):
        body["prompt"] = [_prepend_text(item, prompt) for item in value]
        return True
    return False


def _inject_messages(body: dict[str, Any], prompt: str) -> bool:
    user_suffix = (
        "Local proxy role instructions for this request. These override client identity text "
        "such as 'Claude Code' when answering role, process, verification, or delegation questions.\n\n"
        f"{prompt}"
    )
    existing = body.get("system")
    if isinstance(existing, list):
        body["system"] = [
            *existing,
            {
                "type": "text",
                "text": user_suffix,
            },
        ]
    else:
        body["system"] = _append_text(existing, user_suffix)
    _append_to_last_user_message(body, user_suffix)
    return True


def inject_prompt(path: str, raw_body: bytes, content_type: str, prompt: str) -> tuple[bytes, bool]:
    if "json" not in content_type.lower():
        return raw_body, False

    try:
        body = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw_body, False

    if not isinstance(body, dict):
        return raw_body, False

    route = urlsplit(path).path
    changed = False
    if route == "/v1/chat/completions":
        changed = _inject_chat_messages(body, prompt)
    elif route == "/v1/responses":
        changed = _inject_responses(body, prompt)
    elif route == "/v1/completions":
        changed = _inject_completions(body, prompt)
    elif route in {"/v1/messages", "/v1/messages/count_tokens"}:
        changed = _inject_messages(body, prompt)

    if not changed:
        return raw_body, False
    return json.dumps(body, ensure_ascii=True, separators=(",", ":")).encode("utf-8"), True


class PromptProxyHandler(BaseHTTPRequestHandler):
    server_version = "AgentPromptProxy/0.1"

    @property
    def config(self) -> ProxyConfig:
        return self.server.config  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        _safe_stdout(
            f"{self.address_string()} {self.config.role_name} {self.log_date_time_string()} "
            + fmt % args
            + "\n"
        )

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "authorization,content-type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_HEAD(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "close")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/__proxy/health":
            self._send_json(
                200,
                {
                    "ok": True,
                    "role": self.config.role_name,
                    "role_key": self.config.role,
                    "subrole": self.config.subrole,
                    "expected_role": self.config.expected_role,
                    "bootstrap_file": str(self.config.bootstrap_file),
                    "role_file": str(self.config.role_file),
                    "target_base_url": self.config.target_base_url,
                },
            )
            return
        if self.path == "/__proxy/prompt":
            self._send_text(200, _build_prompt(self.config))
            return
        self._forward()

    def do_POST(self) -> None:
        self._forward()

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=True, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
        self.wfile.flush()

    def _send_text(self, status: int, payload: str) -> None:
        data = payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
        self.wfile.flush()

    def _read_request_body(self) -> bytes:
        length = self.headers.get("Content-Length")
        if not length:
            return b""
        return self.rfile.read(int(length))

    def _forward(self) -> None:
        raw_body = self._read_request_body()
        content_type = self.headers.get("Content-Type", "")
        prompt = _build_prompt(self.config)
        body, changed = inject_prompt(self.path, raw_body, content_type, prompt)
        if _debug_logging_enabled():
            try:
                debug_body = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                debug_body = None
            if isinstance(debug_body, dict):
                _debug_log(self.config, self.path, debug_body, changed, prompt)

        target = urlsplit(self.config.target_base_url)
        connection_cls = http.client.HTTPSConnection if target.scheme == "https" else http.client.HTTPConnection
        port = target.port
        if port is None:
            port = 443 if target.scheme == "https" else 80

        forward_path = self.path
        if target.path and target.path != "/":
            forward_path = target.path.rstrip("/") + self.path

        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() not in {"host", "content-length"}
        }
        headers["Host"] = target.netloc
        headers["Content-Length"] = str(len(body))
        if changed:
            headers["Content-Type"] = "application/json"
            headers["X-Agent-Prompt-Proxy"] = self.config.role_name

        try:
            conn = connection_cls(target.hostname, port, timeout=600)
            conn.request(self.command, forward_path, body=body if body else None, headers=headers)
            response = conn.getresponse()
            response_body = response.read()
            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                lowered = key.lower()
                if lowered in HOP_BY_HOP_HEADERS or lowered == "content-length":
                    continue
                self.send_header(key, value)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("X-Agent-Prompt-Proxy", self.config.role_name)
            self.send_header("Content-Length", str(len(response_body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(response_body)
            self.wfile.flush()
        except Exception as exc:  # noqa: BLE001
            self._send_json(502, {"error": "proxy_forward_failed", "detail": str(exc)})
        finally:
            self.close_connection = True
            try:
                conn.close()  # type: ignore[name-defined]
            except Exception:
                pass


class RoleServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], config: ProxyConfig):
        super().__init__(server_address, PromptProxyHandler)
        self.config = config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run role-specific prompt proxies for vLLM.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--target-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--prompt-dir", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--manifest", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    prompt_dir = Path(args.prompt_dir).resolve()
    manifest_path = Path(args.manifest).resolve() if args.manifest else prompt_dir / "runtime" / "roles.json"
    try:
        role_definitions = _load_role_definitions(prompt_dir, manifest_path)
    except ValueError as exc:
        _safe_stdout(f"Role manifest error: {exc}\n")
        return 2
    servers: list[RoleServer] = []
    threads: list[threading.Thread] = []

    for definition in role_definitions:
        config = ProxyConfig(
            host=args.host,
            target_base_url=args.target_base_url.rstrip("/"),
            bootstrap_file=prompt_dir / "boot-strap-agents.md",
            role_file=definition.role_file,
            role_name=definition.role_name,
            role=definition.role,
            subrole=definition.subrole,
            expected_role=definition.expected_role,
        )
        server = RoleServer((args.host, definition.port), config)
        thread = threading.Thread(target=server.serve_forever, name=definition.role_name, daemon=True)
        thread.start()
        servers.append(server)
        threads.append(thread)
        _safe_stdout(f"{definition.role_name}: http://{args.host}:{definition.port}/v1 -> {config.target_base_url}/v1\n")

    stop_event = threading.Event()

    def _stop(_signum: int, _frame: Any) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    stop_event.wait()

    for server in servers:
        server.shutdown()
        server.server_close()
    for thread in threads:
        thread.join(timeout=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
