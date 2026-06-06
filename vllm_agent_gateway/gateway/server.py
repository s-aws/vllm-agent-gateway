#!/usr/bin/env python3
"""Strict context-budget gateway for local vLLM agent traffic."""

from __future__ import annotations

import argparse
import http.client
import json
import math
import signal
import sys
import threading
from dataclasses import dataclass
from enum import Enum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from vllm_agent_gateway.controller_envelope import (
    ControllerEnvelopeError,
    select_latest_controller_envelope,
)


BUDGETED_ROUTES = {
    "/v1/chat/completions",
    "/v1/completions",
    "/v1/responses",
    "/v1/messages",
}

COUNT_ROUTES = {
    "/v1/messages/count_tokens",
}

OPENAI_ROUTE_ALIASES = {
    "/chat/completions": "/v1/chat/completions",
    "/completions": "/v1/completions",
    "/responses": "/v1/responses",
    "/messages": "/v1/messages",
    "/messages/count_tokens": "/v1/messages/count_tokens",
    "/models": "/v1/models",
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

PROMPT_SCHEMA_KEYS = {
    "function_call",
    "functions",
    "guided_choice",
    "guided_json",
    "guided_regex",
    "response_format",
    "tool_choice",
    "tools",
}


class GatewayControllerRouting(str, Enum):
    OFF = "off"
    EXPLICIT_ENVELOPE = "explicit_envelope"
    WORKFLOW_ROUTER = "workflow_router"


@dataclass(frozen=True)
class GatewayConfig:
    host: str
    port: int
    target_base_url: str
    controller_routing: GatewayControllerRouting
    controller_harness_url: str | None
    model_limit: int
    target_input_limit: int
    safety_buffer: int
    default_max_output: int
    min_available_output: int
    tokenizer_timeout: int


@dataclass(frozen=True)
class TokenCount:
    input_tokens: int
    source: str


def _safe_stdout(message: str) -> None:
    try:
        sys.stdout.write(message)
        sys.stdout.flush()
    except OSError:
        pass


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def _parse_json_body(raw_body: bytes) -> dict[str, Any] | None:
    try:
        body = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(body, dict):
        return None
    return body


def _target_parts(target_base_url: str) -> tuple[Any, type[http.client.HTTPConnection], int]:
    target = urlsplit(target_base_url)
    connection_cls = http.client.HTTPSConnection if target.scheme == "https" else http.client.HTTPConnection
    port = target.port
    if port is None:
        port = 443 if target.scheme == "https" else 80
    return target, connection_cls, port


def _forward_path(target_base_url: str, request_path: str) -> str:
    target = urlsplit(target_base_url)
    base_path = target.path.rstrip("/")
    if not base_path:
        return request_path
    if request_path == base_path or request_path.startswith(base_path + "/"):
        return request_path
    return base_path + request_path


def _canonical_route(path: str) -> str:
    return OPENAI_ROUTE_ALIASES.get(path, path)


def _canonical_request_path(request_path: str) -> str:
    parsed = urlsplit(request_path)
    path = _canonical_route(parsed.path)
    if parsed.query:
        path = path + "?" + parsed.query
    return path


def _path_from_url(target_url: str) -> str:
    target = urlsplit(target_url)
    path = target.path or "/"
    if target.query:
        path = path + "?" + target.query
    return path


def _tokenize_path(target_base_url: str) -> str:
    target = urlsplit(target_base_url)
    base_path = target.path.rstrip("/")
    if not base_path or base_path == "/v1":
        return "/tokenize"
    return base_path + "/tokenize"


def _content_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(part for part in (_content_to_text(item) for item in value) if part)
    if isinstance(value, dict):
        for key in ("text", "input_text", "content"):
            text = value.get(key)
            if isinstance(text, str):
                return text
            if isinstance(text, (list, dict)):
                return _content_to_text(text)
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return str(value)


def _rough_token_estimate(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text.encode("utf-8")) / 3))


def _model_part(body: dict[str, Any]) -> dict[str, Any]:
    model = body.get("model")
    if isinstance(model, str) and model:
        return {"model": model}
    return {}


def _normalize_message(message: Any) -> dict[str, str] | None:
    if not isinstance(message, dict):
        return None
    role = message.get("role")
    if not isinstance(role, str) or not role:
        role = "user"
    return {"role": role, "content": _content_to_text(message.get("content", ""))}


def _anthropic_messages_as_chat(body: dict[str, Any]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    system = body.get("system")
    if system is not None:
        messages.append({"role": "system", "content": _content_to_text(system)})
    raw_messages = body.get("messages")
    if isinstance(raw_messages, list):
        for raw_message in raw_messages:
            message = _normalize_message(raw_message)
            if message is not None:
                messages.append(message)
    return messages


def _route_input_text(route: str, body: dict[str, Any]) -> str:
    if route == "/v1/chat/completions":
        messages = body.get("messages")
        if isinstance(messages, list):
            return "\n".join(_content_to_text(message) for message in messages)
    if route in {"/v1/messages", "/v1/messages/count_tokens"}:
        return "\n".join(message["content"] for message in _anthropic_messages_as_chat(body))
    if route == "/v1/completions":
        prompt = body.get("prompt")
        if isinstance(prompt, list):
            return "\n".join(_content_to_text(item) for item in prompt)
        return _content_to_text(prompt)
    if route == "/v1/responses":
        return "\n".join(
            part
            for part in (
                _content_to_text(body.get("instructions")),
                _content_to_text(body.get("input")),
            )
            if part
        )
    return json.dumps(body, ensure_ascii=True, sort_keys=True)


def _schema_overhead_tokens(body: dict[str, Any]) -> int:
    parts = []
    for key in sorted(PROMPT_SCHEMA_KEYS):
        if key in body:
            parts.append(json.dumps({key: body[key]}, ensure_ascii=True, sort_keys=True))
    return _rough_token_estimate("\n".join(parts))


def _tool_names(body: dict[str, Any]) -> list[str]:
    raw_tools = body.get("tools")
    if not isinstance(raw_tools, list):
        return []
    names: list[str] = []
    for raw_tool in raw_tools:
        if not isinstance(raw_tool, dict):
            continue
        name = raw_tool.get("name")
        if not isinstance(name, str):
            function = raw_tool.get("function")
            if isinstance(function, dict):
                name = function.get("name")
        if isinstance(name, str) and name:
            names.append(name)
    return names


def _call_tokenize(config: GatewayConfig, payload: dict[str, Any]) -> int | None:
    target, connection_cls, port = _target_parts(config.target_base_url)
    data = _json_bytes(payload)
    conn: http.client.HTTPConnection | None = None
    try:
        conn = connection_cls(target.hostname, port, timeout=config.tokenizer_timeout)
        conn.request(
            "POST",
            _tokenize_path(config.target_base_url),
            body=data,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(data)),
            },
        )
        response = conn.getresponse()
        response_body = response.read()
    except Exception:
        return None
    finally:
        if conn is not None:
            conn.close()

    if response.status != 200:
        return None
    parsed = _parse_json_body(response_body)
    if parsed is None:
        return None
    count = parsed.get("count")
    if isinstance(count, int) and count >= 0:
        return count
    tokens = parsed.get("tokens")
    if isinstance(tokens, list):
        return len(tokens)
    return None


def _tokenize_count(config: GatewayConfig, route: str, body: dict[str, Any]) -> int | None:
    model = _model_part(body)
    if route == "/v1/chat/completions":
        messages = body.get("messages")
        if isinstance(messages, list):
            return _call_tokenize(config, {**model, "messages": messages})
    if route in {"/v1/messages", "/v1/messages/count_tokens"}:
        messages = _anthropic_messages_as_chat(body)
        if messages:
            return _call_tokenize(config, {**model, "messages": messages})
    if route == "/v1/completions":
        prompt = body.get("prompt")
        if isinstance(prompt, list):
            counts = []
            for item in prompt:
                count = _call_tokenize(config, {**model, "prompt": _content_to_text(item)})
                if count is None:
                    return None
                counts.append(count)
            return sum(counts)
        return _call_tokenize(config, {**model, "prompt": _content_to_text(prompt)})
    if route == "/v1/responses":
        text = _route_input_text(route, body)
        if text:
            return _call_tokenize(config, {**model, "prompt": text})
    return None


def count_input_tokens(config: GatewayConfig, route: str, body: dict[str, Any]) -> TokenCount:
    tokenize_count = _tokenize_count(config, route, body)
    overhead = _schema_overhead_tokens(body)
    if tokenize_count is not None:
        return TokenCount(max(1, tokenize_count + overhead), "vllm_tokenize")
    fallback_text = _route_input_text(route, body)
    fallback = _rough_token_estimate(fallback_text) + overhead
    return TokenCount(max(1, fallback), "gateway_rough_estimate")


def _requested_output_tokens(route: str, body: dict[str, Any]) -> int | None:
    fields = {
        "/v1/chat/completions": ("max_completion_tokens", "max_tokens"),
        "/v1/completions": ("max_tokens",),
        "/v1/messages": ("max_tokens",),
        "/v1/responses": ("max_output_tokens", "max_tokens"),
    }.get(route, ())
    for field in fields:
        value = body.get(field)
        if isinstance(value, int) and value > 0:
            return value
    return None


def _set_output_tokens(route: str, body: dict[str, Any], max_output_tokens: int) -> str:
    if route == "/v1/chat/completions":
        if "max_completion_tokens" in body:
            body["max_completion_tokens"] = max_output_tokens
            return "max_completion_tokens"
        body["max_tokens"] = max_output_tokens
        return "max_tokens"
    if route == "/v1/responses":
        if "max_tokens" in body and "max_output_tokens" not in body:
            body["max_tokens"] = max_output_tokens
            return "max_tokens"
        body["max_output_tokens"] = max_output_tokens
        return "max_output_tokens"
    body["max_tokens"] = max_output_tokens
    return "max_tokens"


def _budget_error(
    code: str,
    message: str,
    config: GatewayConfig,
    token_count: TokenCount | None = None,
    available_output: int | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "message": message,
        "type": "context_budget_error",
        "code": code,
        "model_limit": config.model_limit,
        "target_input_limit": config.target_input_limit,
        "safety_buffer": config.safety_buffer,
    }
    if token_count is not None:
        error["input_tokens"] = token_count.input_tokens
        error["token_count_source"] = token_count.source
    if available_output is not None:
        error["available_output_tokens"] = available_output
    return {"error": error}


class GatewayHandler(BaseHTTPRequestHandler):
    server_version = "LLMGateway/0.1"

    @property
    def config(self) -> GatewayConfig:
        return self.server.config  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        _safe_stdout(f"{self.address_string()} gateway {self.log_date_time_string()} " + fmt % args + "\n")

    def _log_budget_event(self, action: str, route: str, **fields: Any) -> None:
        parts = [f"budget action={action}", f"route={route}"]
        for key, value in fields.items():
            parts.append(f"{key}={value}")
        _safe_stdout(" ".join(parts) + "\n")

    def _tool_log_fields(self, body: dict[str, Any]) -> dict[str, Any]:
        names = _tool_names(body)
        return {
            "tool_count": len(names),
            "tool_names": ",".join(names) if names else "-",
        }

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "authorization,content-type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_HEAD(self) -> None:
        if urlsplit(self.path).path == "/__gateway/health":
            self.send_response(200)
            self.send_header("Connection", "close")
            self.end_headers()
            return
        self._forward()

    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/__gateway/health":
            self._send_json(
                200,
                {
                    "ok": True,
                    "target_base_url": self.config.target_base_url,
                    "controller_routing": self.config.controller_routing.value,
                    "controller_harness_url": self.config.controller_harness_url,
                    "model_limit": self.config.model_limit,
                    "target_input_limit": self.config.target_input_limit,
                    "safety_buffer": self.config.safety_buffer,
                    "default_max_output": self.config.default_max_output,
                    "min_available_output": self.config.min_available_output,
                },
            )
            return
        self._forward()

    def do_POST(self) -> None:
        route = _canonical_route(urlsplit(self.path).path)
        upstream_path = _canonical_request_path(self.path)
        if route in COUNT_ROUTES:
            self._handle_count_tokens(route)
            return
        if route in BUDGETED_ROUTES:
            self._handle_budgeted_forward(route, upstream_path)
            return
        self._forward()

    def _send_json(self, status: int, payload: dict[str, Any], extra_headers: dict[str, str] | None = None) -> None:
        data = json.dumps(payload, ensure_ascii=True, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "close")
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)
        self.wfile.flush()

    def _read_request_body(self) -> bytes:
        length = self.headers.get("Content-Length")
        if not length:
            return b""
        return self.rfile.read(int(length))

    def _handle_count_tokens(self, route: str) -> None:
        raw_body = self._read_request_body()
        body = _parse_json_body(raw_body)
        if body is None:
            self._send_json(400, {"error": {"message": "Expected a JSON object.", "code": "invalid_json"}})
            return
        token_count = count_input_tokens(self.config, route, body)
        self._log_budget_event(
            "count",
            route,
            raw_bytes=len(raw_body),
            input_tokens=token_count.input_tokens,
            source=token_count.source,
            **self._tool_log_fields(body),
        )
        self._send_json(
            200,
            {"input_tokens": token_count.input_tokens},
            extra_headers={
                "X-LLM-Gateway": "counted",
                "X-LLM-Gateway-Input-Tokens": str(token_count.input_tokens),
                "X-LLM-Gateway-Token-Source": token_count.source,
                "X-LLM-Gateway-Target-Input-Limit": str(self.config.target_input_limit),
            },
        )

    def _handle_budgeted_forward(self, route: str, upstream_path: str) -> None:
        raw_body = self._read_request_body()
        body = _parse_json_body(raw_body)
        if body is None:
            self._forward_with_body(raw_body, request_path=upstream_path)
            return
        if route == "/v1/chat/completions":
            if self.config.controller_routing == GatewayControllerRouting.WORKFLOW_ROUTER:
                self._handle_workflow_router_route(raw_body)
                return
            if self._handle_controller_envelope_route(raw_body, body):
                return

        token_count = count_input_tokens(self.config, route, body)
        if token_count.input_tokens > self.config.target_input_limit:
            self._log_budget_event(
                "reject",
                route,
                code="input_budget_exceeded",
                raw_bytes=len(raw_body),
                input_tokens=token_count.input_tokens,
                source=token_count.source,
                target_input_limit=self.config.target_input_limit,
                **self._tool_log_fields(body),
            )
            self._send_json(
                422,
                _budget_error(
                    "input_budget_exceeded",
                    "Request input exceeds the gateway target input budget. Delegate a smaller task or summarize explicitly before retrying.",
                    self.config,
                    token_count,
                ),
            )
            return

        available_output = self.config.model_limit - token_count.input_tokens - self.config.safety_buffer
        if available_output < self.config.min_available_output:
            self._log_budget_event(
                "reject",
                route,
                code="insufficient_output_budget",
                raw_bytes=len(raw_body),
                input_tokens=token_count.input_tokens,
                source=token_count.source,
                available_output=available_output,
                **self._tool_log_fields(body),
            )
            self._send_json(
                422,
                _budget_error(
                    "insufficient_output_budget",
                    "Request leaves too little safe output budget after input and safety buffer.",
                    self.config,
                    token_count,
                    available_output,
                ),
            )
            return

        requested_output = _requested_output_tokens(route, body)
        output_limit = min(
            self.config.default_max_output,
            available_output,
            requested_output if requested_output is not None else self.config.default_max_output,
        )
        output_field = _set_output_tokens(route, body, output_limit)
        self._log_budget_event(
            "forward",
            route,
            raw_bytes=len(raw_body),
            input_tokens=token_count.input_tokens,
            source=token_count.source,
            available_output=available_output,
            max_output_tokens=output_limit,
            **self._tool_log_fields(body),
        )
        body_bytes = _json_bytes(body)
        self._forward_with_body(
            body_bytes,
            request_path=upstream_path,
            extra_request_headers={
                "Content-Type": "application/json",
                "X-LLM-Gateway": "budgeted",
                "X-LLM-Gateway-Input-Tokens": str(token_count.input_tokens),
                "X-LLM-Gateway-Token-Source": token_count.source,
                "X-LLM-Gateway-Output-Field": output_field,
                "X-LLM-Gateway-Max-Output-Tokens": str(output_limit),
            },
            extra_response_headers={
                "X-LLM-Gateway": "budgeted",
                "X-LLM-Gateway-Input-Tokens": str(token_count.input_tokens),
                "X-LLM-Gateway-Token-Source": token_count.source,
                "X-LLM-Gateway-Max-Output-Tokens": str(output_limit),
            },
        )

    def _handle_workflow_router_route(self, raw_body: bytes) -> None:
        if not self.config.controller_harness_url:
            self._send_json(
                503,
                {
                    "error": {
                        "message": "Workflow-router gateway mode is enabled, but the controller route is unavailable.",
                        "type": "controller_routing_error",
                        "code": "workflow_router_route_unavailable",
                    }
                },
            )
            return
        _safe_stdout("workflow-router-route action=forward\n")
        self._forward_with_body_to_url(
            raw_body,
            self.config.controller_harness_url,
            _path_from_url(self.config.controller_harness_url),
            extra_request_headers={
                "Content-Type": "application/json",
                "X-LLM-Gateway": "workflow-router-routed",
            },
            extra_response_headers={"X-LLM-Gateway": "workflow-router-routed"},
        )

    def _handle_controller_envelope_route(self, raw_body: bytes, body: dict[str, Any]) -> bool:
        try:
            envelope = select_latest_controller_envelope(body)
        except ControllerEnvelopeError as exc:
            self._send_json(
                400,
                {
                    "error": {
                        "message": str(exc),
                        "type": "controller_routing_error",
                        "code": exc.code,
                    }
                },
            )
            return True
        if envelope is None:
            return False
        if self.config.controller_routing == GatewayControllerRouting.OFF:
            self._send_json(
                503,
                {
                    "error": {
                        "message": (
                            "Request contains agentic_controller_request, but gateway controller routing is disabled."
                        ),
                        "type": "controller_routing_error",
                        "code": "controller_route_disabled",
                    }
                },
            )
            return True
        if not self.config.controller_harness_url:
            self._send_json(
                503,
                {
                    "error": {
                        "message": (
                            "Request contains agentic_controller_request, but gateway controller routing is unavailable."
                        ),
                        "type": "controller_routing_error",
                        "code": "controller_route_unavailable",
                    }
                },
            )
            return True
        workflow = envelope.get("workflow") if isinstance(envelope.get("workflow"), str) else "unknown"
        _safe_stdout(f"controller-route action=forward workflow={workflow}\n")
        self._forward_with_body_to_url(
            raw_body,
            self.config.controller_harness_url,
            _path_from_url(self.config.controller_harness_url),
            extra_request_headers={
                "Content-Type": "application/json",
                "X-LLM-Gateway": "controller-routed",
            },
            extra_response_headers={"X-LLM-Gateway": "controller-routed"},
        )
        return True

    def _forward(self) -> None:
        self._forward_with_body(self._read_request_body())

    def _forward_with_body(
        self,
        body: bytes,
        request_path: str | None = None,
        extra_request_headers: dict[str, str] | None = None,
        extra_response_headers: dict[str, str] | None = None,
    ) -> None:
        upstream_path = request_path if request_path is not None else _canonical_request_path(self.path)
        self._forward_with_body_to_url(
            body,
            self.config.target_base_url,
            _forward_path(self.config.target_base_url, upstream_path),
            extra_request_headers=extra_request_headers,
            extra_response_headers=extra_response_headers,
        )

    def _forward_with_body_to_url(
        self,
        body: bytes,
        target_url: str,
        request_path: str,
        extra_request_headers: dict[str, str] | None = None,
        extra_response_headers: dict[str, str] | None = None,
    ) -> None:
        target, connection_cls, port = _target_parts(target_url)
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() not in {"host", "content-length"}
        }
        headers["Host"] = target.netloc
        headers["Content-Length"] = str(len(body))
        if extra_request_headers:
            headers.update(extra_request_headers)

        conn: http.client.HTTPConnection | None = None
        try:
            conn = connection_cls(target.hostname, port, timeout=600)
            conn.request(
                self.command,
                request_path,
                body=body if body else None,
                headers=headers,
            )
            response = conn.getresponse()
            response_body = response.read()
            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                lowered = key.lower()
                if lowered in HOP_BY_HOP_HEADERS or lowered == "content-length":
                    continue
                self.send_header(key, value)
            self.send_header("Access-Control-Allow-Origin", "*")
            if extra_response_headers:
                for key, value in extra_response_headers.items():
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(response_body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(response_body)
            self.wfile.flush()
        except Exception as exc:  # noqa: BLE001
            self._send_json(502, {"error": {"message": str(exc), "code": "gateway_forward_failed"}})
        finally:
            self.close_connection = True
            if conn is not None:
                conn.close()


class GatewayServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], config: GatewayConfig):
        super().__init__(server_address, GatewayHandler)
        self.config = config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a strict context-budget gateway for local vLLM.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8300)
    parser.add_argument("--target-base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--controller-routing",
        choices=[item.value for item in GatewayControllerRouting],
        default=GatewayControllerRouting.OFF.value,
    )
    parser.add_argument("--controller-harness-url")
    parser.add_argument("--model-limit", type=int, default=65536)
    parser.add_argument("--target-input-limit", type=int, default=24000)
    parser.add_argument("--safety-buffer", type=int, default=1000)
    parser.add_argument("--default-max-output", type=int, default=4000)
    parser.add_argument("--min-available-output", type=int, default=512)
    parser.add_argument("--tokenizer-timeout", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = GatewayConfig(
        host=args.host,
        port=args.port,
        target_base_url=args.target_base_url.rstrip("/"),
        controller_routing=GatewayControllerRouting(args.controller_routing),
        controller_harness_url=args.controller_harness_url.rstrip("/") if args.controller_harness_url else None,
        model_limit=args.model_limit,
        target_input_limit=args.target_input_limit,
        safety_buffer=args.safety_buffer,
        default_max_output=args.default_max_output,
        min_available_output=args.min_available_output,
        tokenizer_timeout=args.tokenizer_timeout,
    )
    server = GatewayServer((config.host, config.port), config)
    _safe_stdout(
        f"llm-gateway: http://{config.host}:{config.port} -> {config.target_base_url} "
        f"(target_input_limit={config.target_input_limit}, default_max_output={config.default_max_output}, "
        f"controller_routing={config.controller_routing.value})\n"
    )

    stop_event = threading.Event()

    def _stop(_signum: int, _frame: Any) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    thread = threading.Thread(target=server.serve_forever, name="llm-gateway", daemon=True)
    thread.start()
    stop_event.wait()
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
