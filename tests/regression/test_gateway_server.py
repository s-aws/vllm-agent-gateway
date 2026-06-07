from __future__ import annotations

import http.client
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from vllm_agent_gateway.gateway.server import (
    GatewayConfig,
    GatewayControllerRouting,
    GatewayServer,
)


class RecordingEndpoint:
    def __init__(self, response_for_request: Callable[[str, dict[str, Any]], dict[str, Any] | tuple[int, dict[str, Any]]]):
        self.response_for_request = response_for_request
        self.requests: list[dict[str, Any]] = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
        self.server.owner = self  # type: ignore[attr-defined]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def __enter__(self) -> "RecordingEndpoint":
        self.thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _handler_class(self) -> type[BaseHTTPRequestHandler]:
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length)
                payload = json.loads(raw.decode("utf-8")) if raw else {}
                owner = self.server.owner  # type: ignore[attr-defined]
                owner.requests.append({"method": "POST", "path": self.path, "body": payload})
                response = owner.response_for_request(self.path, payload)
                status = 200
                if isinstance(response, tuple):
                    status, response = response
                data = json.dumps(response).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(data)
                self.wfile.flush()
                self.close_connection = True

            def log_message(self, format: str, *args: object) -> None:
                return

        return Handler


class RunningGateway:
    def __init__(self, config: GatewayConfig):
        self.server = GatewayServer((config.host, 0), config)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> tuple[str, int]:
        host, port = self.server.server_address
        return str(host), int(port)

    def __enter__(self) -> "RunningGateway":
        self.thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def gateway_config(
    target_base_url: str,
    *,
    controller_routing: GatewayControllerRouting = GatewayControllerRouting.EXPLICIT_ENVELOPE,
    controller_harness_url: str | None = None,
) -> GatewayConfig:
    return GatewayConfig(
        host="127.0.0.1",
        port=0,
        target_base_url=target_base_url,
        controller_routing=controller_routing,
        controller_harness_url=controller_harness_url,
        model_limit=65536,
        target_input_limit=24000,
        safety_buffer=1000,
        default_max_output=4000,
        min_available_output=512,
        tokenizer_timeout=5,
    )


def request_json(host: str, port: int, path: str, body: dict[str, Any]) -> tuple[int, dict[str, Any], dict[str, str]]:
    connection = http.client.HTTPConnection(host, port, timeout=30)
    payload = json.dumps(body).encode("utf-8")
    connection.request("POST", path, body=payload, headers={"Content-Type": "application/json"})
    response = connection.getresponse()
    data = response.read().decode("utf-8")
    headers = {key: value for key, value in response.getheaders()}
    connection.close()
    return response.status, json.loads(data), headers


def model_response(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    if path == "/tokenize":
        return {"tokens": [1, 2, 3]}
    return {"route": "model", "choices": [{"message": {"content": "model-ok"}}], "seen": payload}


def controller_response(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "route": "controller",
        "agentic_controller_response": {
            "run_id": "execution-planning-test",
            "status": "completed",
            "artifacts": {"run_state": "/tmp/run-state.json"},
        },
        "seen_path": path,
        "seen": payload,
    }


def controller_envelope() -> dict[str, Any]:
    return {
        "workflow": "execution_planning.plan",
        "schema_version": 1,
        "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp",
        "user_request": "Plan only.",
        "mode": "investigation_only",
    }


def test_gateway_routes_ordinary_chat_to_model_with_controller_routing_enabled() -> None:
    with RecordingEndpoint(model_response) as model, RecordingEndpoint(controller_response) as controller:
        with RunningGateway(
            gateway_config(
                model.base_url,
                controller_harness_url=controller.base_url + "/v1/controller/harness/chat/completions",
            )
        ) as gateway:
            host, port = gateway.base_url
            status, body, headers = request_json(
                host,
                port,
                "/v1/chat/completions",
                {"model": "local-model", "messages": [{"role": "user", "content": "hello"}]},
            )

    assert status == 200
    assert body["route"] == "model"
    assert headers["X-LLM-Gateway"] == "budgeted"
    assert [request["path"] for request in model.requests] == ["/tokenize", "/v1/chat/completions"]
    assert controller.requests == []


def test_gateway_accepts_no_v1_chat_alias_for_ordinary_model_chat() -> None:
    with RecordingEndpoint(model_response) as model, RecordingEndpoint(controller_response) as controller:
        with RunningGateway(
            gateway_config(
                model.base_url,
                controller_harness_url=controller.base_url + "/v1/controller/harness/chat/completions",
            )
        ) as gateway:
            host, port = gateway.base_url
            status, body, headers = request_json(
                host,
                port,
                "/chat/completions",
                {"model": "local-model", "messages": [{"role": "user", "content": "hello"}]},
            )

    assert status == 200
    assert body["route"] == "model"
    assert headers["X-LLM-Gateway"] == "budgeted"
    assert [request["path"] for request in model.requests] == ["/tokenize", "/v1/chat/completions"]
    assert controller.requests == []


def test_gateway_routes_top_level_controller_envelope_to_harness_without_model_fallback() -> None:
    with RecordingEndpoint(model_response) as model, RecordingEndpoint(controller_response) as controller:
        harness_url = controller.base_url + "/v1/controller/harness/chat/completions"
        with RunningGateway(gateway_config(model.base_url, controller_harness_url=harness_url)) as gateway:
            host, port = gateway.base_url
            status, body, headers = request_json(
                host,
                port,
                "/v1/chat/completions",
                {"model": "agentic-controller", "agentic_controller_request": controller_envelope()},
            )

    assert status == 200
    assert body["route"] == "controller"
    assert body["agentic_controller_response"]["run_id"] == "execution-planning-test"
    assert headers["X-LLM-Gateway"] == "controller-routed"
    assert model.requests == []
    assert [request["path"] for request in controller.requests] == ["/v1/controller/harness/chat/completions"]
    assert controller.requests[0]["body"]["agentic_controller_request"]["workflow"] == "execution_planning.plan"


def test_gateway_accepts_no_v1_chat_alias_for_controller_envelope() -> None:
    with RecordingEndpoint(model_response) as model, RecordingEndpoint(controller_response) as controller:
        harness_url = controller.base_url + "/v1/controller/harness/chat/completions"
        with RunningGateway(gateway_config(model.base_url, controller_harness_url=harness_url)) as gateway:
            host, port = gateway.base_url
            status, body, headers = request_json(
                host,
                port,
                "/chat/completions",
                {"model": "agentic-controller", "agentic_controller_request": controller_envelope()},
            )

    assert status == 200
    assert body["route"] == "controller"
    assert headers["X-LLM-Gateway"] == "controller-routed"
    assert model.requests == []
    assert [request["path"] for request in controller.requests] == ["/v1/controller/harness/chat/completions"]


def test_gateway_routes_message_content_controller_envelope_to_harness() -> None:
    with RecordingEndpoint(model_response) as model, RecordingEndpoint(controller_response) as controller:
        harness_url = controller.base_url + "/v1/controller/harness/chat/completions"
        with RunningGateway(gateway_config(model.base_url, controller_harness_url=harness_url)) as gateway:
            host, port = gateway.base_url
            status, body, _headers = request_json(
                host,
                port,
                "/v1/chat/completions",
                {
                    "model": "agentic-controller",
                    "messages": [
                        {
                            "role": "user",
                            "content": json.dumps({"agentic_controller_request": controller_envelope()}),
                        }
                    ],
                },
            )

    assert status == 200
    assert body["route"] == "controller"
    assert model.requests == []
    assert controller.requests[0]["body"]["messages"][0]["role"] == "user"


def test_gateway_uses_latest_message_controller_envelope_when_history_contains_old_envelope() -> None:
    old_envelope = {**controller_envelope(), "target_root": "/mnt/c/old-frozen-target"}
    latest_envelope = {**controller_envelope(), "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github"}
    with RecordingEndpoint(model_response) as model, RecordingEndpoint(controller_response) as controller:
        harness_url = controller.base_url + "/v1/controller/harness/chat/completions"
        with RunningGateway(gateway_config(model.base_url, controller_harness_url=harness_url)) as gateway:
            host, port = gateway.base_url
            status, body, headers = request_json(
                host,
                port,
                "/v1/chat/completions",
                {
                    "model": "agentic-controller",
                    "messages": [
                        {
                            "role": "user",
                            "content": json.dumps({"agentic_controller_request": old_envelope}),
                        },
                        {"role": "assistant", "content": "previous controller result"},
                        {
                            "role": "user",
                            "content": json.dumps({"agentic_controller_request": latest_envelope}),
                        },
                    ],
                },
            )

    assert status == 200
    assert body["route"] == "controller"
    assert headers["X-LLM-Gateway"] == "controller-routed"
    assert model.requests == []
    assert [request["path"] for request in controller.requests] == ["/v1/controller/harness/chat/completions"]


def test_gateway_ignores_old_message_controller_envelope_when_latest_message_is_normal_chat() -> None:
    old_envelope = {**controller_envelope(), "target_root": "/mnt/c/old-frozen-target"}
    with RecordingEndpoint(model_response) as model, RecordingEndpoint(controller_response) as controller:
        harness_url = controller.base_url + "/v1/controller/harness/chat/completions"
        with RunningGateway(gateway_config(model.base_url, controller_harness_url=harness_url)) as gateway:
            host, port = gateway.base_url
            status, body, headers = request_json(
                host,
                port,
                "/v1/chat/completions",
                {
                    "model": "agentic-controller",
                    "messages": [
                        {
                            "role": "user",
                            "content": json.dumps({"agentic_controller_request": old_envelope}),
                        },
                        {"role": "assistant", "content": "previous controller result"},
                        {"role": "user", "content": "Return exactly one JSON object for this skill smoke."},
                    ],
                },
            )

    assert status == 200
    assert body["route"] == "model"
    assert "X-LLM-Gateway" not in headers or headers["X-LLM-Gateway"] != "controller-routed"
    assert controller.requests == []
    assert [request["path"] for request in model.requests] == ["/tokenize", "/v1/chat/completions"]


def test_gateway_workflow_router_mode_routes_natural_chat_without_model_fallback() -> None:
    with RecordingEndpoint(model_response) as model, RecordingEndpoint(controller_response) as controller:
        router_url = controller.base_url + "/v1/controller/workflow-router/chat/completions"
        with RunningGateway(
            gateway_config(
                model.base_url,
                controller_routing=GatewayControllerRouting.WORKFLOW_ROUTER,
                controller_harness_url=router_url,
            )
        ) as gateway:
            host, port = gateway.base_url
            status, body, headers = request_json(
                host,
                port,
                "/v1/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find where the "
                                "placed_order_id stealth lookup begins. Read only."
                            ),
                        }
                    ],
                },
            )

    assert status == 200
    assert body["route"] == "controller"
    assert headers["X-LLM-Gateway"] == "workflow-router-routed"
    assert model.requests == []
    assert [request["path"] for request in controller.requests] == ["/v1/controller/workflow-router/chat/completions"]
    assert controller.requests[0]["body"]["messages"][0]["content"].startswith("In /mnt/c/")


def test_gateway_workflow_router_mode_converts_controller_approval_error_to_chat() -> None:
    def approval_error(path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return (
            409,
            {
                "error": {
                    "code": "approval_scope_changed",
                    "message": "Approval continuation target path must match the referenced run target_root.",
                }
            },
        )

    with RecordingEndpoint(model_response) as model, RecordingEndpoint(approval_error) as controller:
        router_url = controller.base_url + "/v1/controller/workflow-router/chat/completions"
        with RunningGateway(
            gateway_config(
                model.base_url,
                controller_routing=GatewayControllerRouting.WORKFLOW_ROUTER,
                controller_harness_url=router_url,
            )
        ) as gateway:
            host, port = gateway.base_url
            status, body, headers = request_json(
                host,
                port,
                "/v1/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Approve packet design for run workflow-router-20260607T000000000000Z.",
                        }
                    ],
                },
            )

    assert status == 200
    assert headers["X-LLM-Gateway"] == "workflow-router-routed"
    assert model.requests == []
    content = body["choices"][0]["message"]["content"]
    assert "workflow_router.plan failed" in content
    assert "approval_scope_changed" in content
    assert "Approval:" in content
    assert "- State: failed" in content
    assert body["agentic_controller_response"]["summary"]["error_code"] == "approval_scope_changed"


def test_gateway_workflow_router_mode_rejects_missing_controller_route_without_model_fallback() -> None:
    with RecordingEndpoint(model_response) as model:
        with RunningGateway(
            gateway_config(
                model.base_url,
                controller_routing=GatewayControllerRouting.WORKFLOW_ROUTER,
                controller_harness_url=None,
            )
        ) as gateway:
            host, port = gateway.base_url
            status, body, _headers = request_json(
                host,
                port,
                "/v1/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "messages": [{"role": "user", "content": "In /mnt/c/repo, investigate this."}],
                },
            )

    assert status == 503
    assert body["error"]["code"] == "workflow_router_route_unavailable"
    assert model.requests == []


def test_gateway_rejects_controller_envelope_when_routing_disabled_without_model_fallback() -> None:
    with RecordingEndpoint(model_response) as model, RecordingEndpoint(controller_response) as controller:
        with RunningGateway(
            gateway_config(
                model.base_url,
                controller_routing=GatewayControllerRouting.OFF,
                controller_harness_url=controller.base_url + "/v1/controller/harness/chat/completions",
            )
        ) as gateway:
            host, port = gateway.base_url
            status, body, _headers = request_json(
                host,
                port,
                "/v1/chat/completions",
                {"model": "agentic-controller", "agentic_controller_request": controller_envelope()},
            )

    assert status == 503
    assert body["error"]["code"] == "controller_route_disabled"
    assert model.requests == []
    assert controller.requests == []


def test_gateway_rejects_controller_envelope_when_harness_url_missing_without_model_fallback() -> None:
    with RecordingEndpoint(model_response) as model, RecordingEndpoint(controller_response) as controller:
        with RunningGateway(
            gateway_config(
                model.base_url,
                controller_routing=GatewayControllerRouting.EXPLICIT_ENVELOPE,
                controller_harness_url=None,
            )
        ) as gateway:
            host, port = gateway.base_url
            status, body, _headers = request_json(
                host,
                port,
                "/v1/chat/completions",
                {"model": "agentic-controller", "agentic_controller_request": controller_envelope()},
            )

    assert status == 503
    assert body["error"]["code"] == "controller_route_unavailable"
    assert model.requests == []
    assert controller.requests == []


def test_gateway_rejects_multiple_controller_envelopes_without_forwarding() -> None:
    with RecordingEndpoint(model_response) as model, RecordingEndpoint(controller_response) as controller:
        with RunningGateway(
            gateway_config(
                model.base_url,
                controller_harness_url=controller.base_url + "/v1/controller/harness/chat/completions",
            )
        ) as gateway:
            host, port = gateway.base_url
            status, body, _headers = request_json(
                host,
                port,
                "/v1/chat/completions",
                {
                    "model": "agentic-controller",
                    "agentic_controller_request": controller_envelope(),
                    "messages": [
                        {
                            "role": "user",
                            "content": json.dumps({"agentic_controller_request": controller_envelope()}),
                        }
                    ],
                },
            )

    assert status == 400
    assert body["error"]["code"] == "multiple_controller_envelopes"
    assert model.requests == []
    assert controller.requests == []
