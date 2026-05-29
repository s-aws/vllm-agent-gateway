from __future__ import annotations

import http.client
import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from vllm_agent_gateway.controller_service.server import (
    ControllerServiceConfig,
    create_server,
    service_response_from_result,
)
from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus


REPO_ROOT = Path(__file__).resolve().parents[2]


def run_command(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_target_repo(tmp_path: Path) -> Path:
    target = tmp_path / "allowed" / "target"
    target.mkdir(parents=True)
    write_text(
        target / "README.md",
        "\n".join(
            [
                "# Project",
                "",
                "Install with Docker.",
                "Configuration lives in docs/config.md.",
                "",
            ]
        ),
    )
    write_text(target / "docs" / "config.md", "# Config\n\nSet runtime ports.\n")
    write_text(target / "UNTRACKED.md", "# Bootstrap\n\nUntracked first-run docs.\n")
    run_command(["git", "init"], target)
    run_command(["git", "add", "README.md", "docs/config.md"], target)
    return target


def make_multi_chunk_repo(tmp_path: Path) -> Path:
    target = make_target_repo(tmp_path)
    write_text(
        target / "README.md",
        "# Project\n\n" + "\n".join(f"Documentation line {index} with runtime configuration ports." for index in range(80)),
    )
    run_command(["git", "add", "README.md"], target)
    return target


def test_controller_service_result_response_bounds_summary_and_failures() -> None:
    response = service_response_from_result(
        InvocationResult(
            workflow="documenter.review",
            status=WorkflowStatus.FAILED,
            summary_text="x" * 5000,
            failures=[{"index": index} for index in range(60)],
        )
    )

    assert len(response["summary"]) <= 4000
    assert response["summary"].endswith("...")
    assert len(response["failures"]) == 51
    assert response["failures"][-1]["failure"] == "failures_truncated"


class RunningControllerService:
    def __init__(self, config: ControllerServiceConfig):
        self.server = create_server(config)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> tuple[str, int]:
        host, port = self.server.server_address
        return str(host), int(port)

    def __enter__(self) -> "RunningControllerService":
        self.thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def request_json(host: str, port: int, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    connection = http.client.HTTPConnection(host, port, timeout=30)
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    connection.request(method, path, body=payload, headers=headers)
    response = connection.getresponse()
    data = response.read().decode("utf-8")
    connection.close()
    return response.status, json.loads(data)


class FakeEndpoint:
    def __init__(self, response_for_packet: Callable[[dict[str, Any]], dict[str, Any]], delay_seconds: float = 0.0):
        self.response_for_packet = response_for_packet
        self.delay_seconds = delay_seconds
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}/v1"

    def __enter__(self) -> "FakeEndpoint":
        self.thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _handler_class(self) -> type[BaseHTTPRequestHandler]:
        response_for_packet = self.response_for_packet
        delay_seconds = self.delay_seconds

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                if delay_seconds:
                    time.sleep(delay_seconds)
                length = int(self.headers.get("Content-Length", "0"))
                request = json.loads(self.rfile.read(length).decode("utf-8"))
                content = request["messages"][0]["content"]
                packet = json.loads(content[content.find("{") :])
                result = response_for_packet(packet)
                response = {"choices": [{"message": {"content": json.dumps(result)}}]}
                data = json.dumps(response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format: str, *args: object) -> None:
                return

        return Handler


def default_documenter_result(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": packet["chunk_id"],
        "facts_found": [],
        "criteria_satisfied": [],
        "criteria_remaining": packet.get("criteria_remaining", []),
        "doc_gaps": [],
        "followup_files": [],
        "confidence": "medium",
    }


def poll_run(host: str, port: int, run_id: str, terminal_statuses: set[str], timeout_seconds: float = 10.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_body: dict[str, Any] = {}
    while time.monotonic() < deadline:
        status, body = request_json(host, port, "GET", f"/v1/controller/runs/{run_id}")
        assert status == 200
        last_body = body
        if body.get("status") in terminal_statuses:
            return body
        time.sleep(0.05)
    raise AssertionError(f"Run {run_id} did not reach {terminal_statuses}; last body={last_body}")


def test_controller_service_health_and_direct_chat_rejection(tmp_path: Path) -> None:
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url

        status, body = request_json(host, port, "GET", "/health")
        assert status == 200
        assert body["status"] == "ok"
        assert body["kind"] == "controller_service"

        status, body = request_json(host, port, "POST", "/v1/chat/completions", {"messages": []})
        assert status == 404
        assert body["error"]["code"] == "not_found"


def test_controller_service_rejects_target_roots_outside_allowlist(tmp_path: Path) -> None:
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        outside = tmp_path / "outside" / "repo"

        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/documenter/reviews",
            {"workflow": "documenter.review", "target_root": str(outside), "dry_run": True},
        )

    assert status == 403
    assert body["error"]["code"] == "target_root_not_allowed"
    assert not (config.output_root / ".agentic_reports").exists()


def test_controller_service_runs_documenter_review_and_persists_status(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/documenter/reviews",
            {
                "workflow": "documenter.review",
                "target_root": str(target),
                "seed_doc": "README.md",
                "mode": "full",
                "document_scope": "all",
                "review_scope": "manifest",
                "dry_run": True,
                "budgets": {"max_chunks": 1},
            },
        )

        assert status == 200
        assert body["workflow"] == "documenter.review"
        assert body["status"] == "completed"
        assert body["run_id"]
        assert "json_report" in body["artifacts"]
        assert "run_state" in body["artifacts"]
        assert "document_manifest" in body["artifacts"]
        assert "review_plan" in body["artifacts"]
        assert Path(body["artifacts"]["json_report"]).exists()

        status, run_body = request_json(host, port, "GET", f"/v1/controller/runs/{body['run_id']}")

    assert status == 200
    assert run_body["kind"] == "controller_run_record"
    assert run_body["run_id"] == body["run_id"]
    assert run_body["artifacts"]["json_report"] == body["artifacts"]["json_report"]
    assert body["review_summary"]["seed_doc_id"] == "README.md"


def test_controller_service_records_resolved_workflow_tool_policy(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/documenter/reviews",
            {
                "workflow": "documenter.review",
                "target_root": str(target),
                "doc": "README.md",
                "mode": "full",
                "document_scope": "all",
                "review_scope": "manifest",
                "dry_run": True,
                "budgets": {"max_chunks": 1},
            },
        )

        assert status == 200
        policy = body["tool_policy"]
        assert policy["kind"] == "controller_tool_policy"
        assert policy["workflow"] == "documenter.review"
        assert policy["role_id"] == "documenter/default"
        assert policy["controller_tool_ids"] == ["git_ls_files", "read_file", "scan_files"]
        assert policy["model_visible_tool_ids"] == []
        assert policy["denied_tool_ids"] == []
        assert policy["controller_tool_schema_count"] == 3
        assert policy["model_visible_tool_schema_count"] == 0
        assert [action["tool_id"] for action in policy["controller_actions"]] == [
            "git_ls_files",
            "read_file",
            "scan_files",
        ]
        assert policy["controller_actions"][0]["result_artifacts"] == [
            "document_manifest",
            "review_plan",
            "json_report",
        ]

        status, run_body = request_json(host, port, "GET", f"/v1/controller/runs/{body['run_id']}")

    assert status == 200
    assert run_body["tool_policy"]["controller_tool_ids"] == ["git_ls_files", "read_file", "scan_files"]


def test_controller_service_rejects_role_not_allowed_by_workflow_tool_policy(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/documenter/reviews",
            {
                "workflow": "documenter.review",
                "target_root": str(target),
                "doc": "README.md",
                "mode": "full",
                "role_id": "architect/default",
                "dry_run": True,
            },
        )

    assert status == 422
    assert body["error"]["code"] == "tool_policy_denied"
    assert "architect/default" in body["error"]["message"]
    assert not (config.output_root / ".agentic_reports").exists()


def test_controller_service_rejects_denied_model_visible_tool_ids(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/documenter/reviews",
            {
                "workflow": "documenter.review",
                "target_root": str(target),
                "doc": "README.md",
                "mode": "full",
                "model_visible_tool_ids": ["read_file"],
                "dry_run": True,
            },
        )

    assert status == 422
    assert body["error"]["code"] == "tool_policy_denied"
    assert "read_file" in body["error"]["message"]
    assert not (config.output_root / ".agentic_reports").exists()


def test_controller_service_rejects_unsupported_budget_before_workflow(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/documenter/reviews",
            {
                "workflow": "documenter.review",
                "target_root": str(target),
                "dry_run": True,
                "budgets": {"max_elapsed_seconds": 30},
            },
        )

    assert status == 400
    assert body["error"]["code"] == "bad_request"
    assert "max_elapsed_seconds" in body["error"]["message"]
    assert not (config.output_root / ".agentic_reports").exists()


def test_controller_service_rejects_conflicting_seed_aliases(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/documenter/reviews",
            {
                "workflow": "documenter.review",
                "target_root": str(target),
                "seed_doc": "README.md",
                "doc": "docs/config.md",
                "dry_run": True,
            },
        )

    assert status == 400
    assert body["error"]["code"] == "bad_request"
    assert "must not specify different values" in body["error"]["message"]
    assert not (config.output_root / ".agentic_reports").exists()


def test_harness_adapter_runs_documenter_with_explicit_openai_style_envelope(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    envelope = {
        "agentic_controller_request": {
            "workflow": "documenter.review",
            "target_root": str(target),
            "doc": "README.md",
            "mode": "full",
            "document_scope": "all",
            "review_scope": "manifest",
            "dry_run": True,
            "budgets": {"max_chunks": 1},
        }
    }
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/harness/chat/completions",
            {
                "model": "agentic-controller",
                "messages": [
                    {
                        "role": "user",
                        "content": json.dumps(envelope),
                    }
                ],
            },
        )

        assert status == 200
        assert body["object"] == "chat.completion"
        assert body["choices"][0]["message"]["role"] == "assistant"
        assert "documenter.review completed" in body["choices"][0]["message"]["content"]
        compact = body["agentic_controller_response"]
        assert compact["status"] == "completed"
        assert compact["workflow"] == "documenter.review"
        assert compact["run_lookup"] == f"/v1/controller/runs/{compact['run_id']}"
        assert "json_report" in compact["artifacts"]
        assert Path(compact["artifacts"]["json_report"]).exists()

        status, run_body = request_json(host, port, "GET", compact["run_lookup"])

    assert status == 200
    assert run_body["run_id"] == compact["run_id"]


def test_harness_adapter_accepts_top_level_controller_envelope(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/harness/chat/completions",
            {
                "model": "agentic-controller",
                "agentic_controller_request": {
                    "workflow": "documenter.review",
                    "target_root": str(target),
                    "doc": "README.md",
                    "mode": "full",
                    "dry_run": True,
                    "budgets": {"max_chunks": 1},
                },
            },
        )

    assert status == 200
    assert body["agentic_controller_response"]["status"] == "completed"
    assert body["choices"][0]["finish_reason"] == "stop"


def test_controller_service_async_documenter_run_is_pollable(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/documenter/reviews",
            {
                "workflow": "documenter.review",
                "target_root": str(target),
                "doc": "README.md",
                "mode": "full",
                "dry_run": True,
                "async": True,
                "budgets": {"max_chunks": 1},
            },
        )

        assert status == 202
        assert body["status"] == "running"
        final = poll_run(host, port, body["run_id"], {"completed"})

    assert final["status"] == "completed"
    assert final["lifecycle"]["async"] is True
    assert "json_report" in final["artifacts"]
    assert "report" not in final


def test_controller_service_resume_from_paused_run_state(tmp_path: Path) -> None:
    target = make_multi_chunk_repo(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, paused = request_json(
            host,
            port,
            "POST",
            "/v1/controller/documenter/reviews",
            {
                "workflow": "documenter.review",
                "target_root": str(target),
                "doc": "README.md",
                "mode": "full",
                "dry_run": True,
                "chunk_token_limit": 128,
                "budgets": {"stop_after_chunks": 1},
            },
        )

        assert status == 200
        assert paused["status"] == "paused"
        state_path = paused["artifacts"]["run_state"]
        assert Path(state_path).exists()

        status, completed = request_json(
            host,
            port,
            "POST",
            "/v1/controller/documenter/reviews",
            {
                "workflow": "documenter.review",
                "target_root": str(target),
                "doc": "README.md",
                "mode": "full",
                "dry_run": True,
                "chunk_token_limit": 128,
                "resume": state_path,
            },
        )

    assert status == 200
    assert completed["status"] == "completed"
    assert completed["run_id"] == paused["run_id"]
    assert completed["artifacts"]["run_state"] == state_path


def test_controller_service_cancel_stops_async_run_after_current_packet(tmp_path: Path) -> None:
    target = make_multi_chunk_repo(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeEndpoint(default_documenter_result, delay_seconds=0.25) as endpoint:
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/documenter/reviews",
                {
                    "workflow": "documenter.review",
                    "target_root": str(target),
                    "doc": "README.md",
                    "mode": "review",
                    "role_base_url": endpoint.base_url,
                    "chunk_token_limit": 128,
                    "async": True,
                },
            )
            assert status == 202
            run_id = body["run_id"]

            status, cancel_body = request_json(host, port, "POST", f"/v1/controller/runs/{run_id}/cancel", {})
            assert status == 200
            assert cancel_body["status"] == "cancel_requested"

            final = poll_run(host, port, run_id, {"canceled"})

    assert final["status"] == "canceled"
    assert final["lifecycle"]["cancel_requested"] is True
    assert final["failures"][0]["reason"] == "controller_service_stop_requested"


def test_controller_service_cleanup_removes_terminal_run_records_only(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/documenter/reviews",
            {
                "workflow": "documenter.review",
                "target_root": str(target),
                "doc": "README.md",
                "mode": "full",
                "dry_run": True,
                "budgets": {"max_chunks": 1},
            },
        )
        assert status == 200
        run_id = body["run_id"]

        status, cleanup = request_json(
            host,
            port,
            "POST",
            "/v1/controller/runs/cleanup",
            {"max_age_seconds": 0, "statuses": ["completed"]},
        )
        assert status == 200
        assert run_id in cleanup["deleted_run_ids"]

        status, missing = request_json(host, port, "GET", f"/v1/controller/runs/{run_id}")

    assert status == 404
    assert missing["error"]["code"] == "run_not_found"


def test_documenter_service_example_script_runs_tracked_and_harness_cases(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    script = REPO_ROOT / "scripts" / "run_documenter_service_example.py"
    with RunningControllerService(config) as service:
        host, port = service.base_url
        controller_url = f"http://{host}:{port}"
        tracked = subprocess.run(
            [
                sys.executable,
                str(script),
                "--controller-url",
                controller_url,
                "--target-root",
                str(target),
                "--case",
                "tracked",
                "--max-chunks",
                "1",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        harness = subprocess.run(
            [
                sys.executable,
                str(script),
                "--controller-url",
                controller_url,
                "--target-root",
                str(target),
                "--case",
                "harness",
                "--seed-doc",
                "README.md",
                "--max-chunks",
                "1",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )

    assert tracked.returncode == 0, tracked.stderr
    tracked_body = json.loads(tracked.stdout)
    assert tracked_body["status"] == "completed"
    assert tracked_body["review_summary"]["review_scope"] == "manifest"
    assert tracked_body["review_summary"]["reviewed_file_count"] >= 1
    assert "json_report" in tracked_body["artifacts"]

    assert harness.returncode == 0, harness.stderr
    harness_body = json.loads(harness.stdout)
    compact = harness_body["agentic_controller_response"]
    assert compact["status"] == "completed"
    assert compact["review_summary"]["review_scope"] == "seed"
    assert "reviewed_files:" in harness_body["choices"][0]["message"]["content"]
    assert "Artifacts:" in harness_body["choices"][0]["message"]["content"]


def test_harness_adapter_rejects_natural_language_without_controller_envelope(tmp_path: Path) -> None:
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/harness/chat/completions",
            {
                "model": "agentic-controller",
                "messages": [{"role": "user", "content": "Review all documentation in this repo."}],
            },
        )

    assert status == 400
    assert body["error"]["code"] == "missing_controller_envelope"
    assert "Natural-language chat text is not a workflow request" in body["error"]["message"]
    assert not (config.output_root / ".agentic_reports").exists()


def test_harness_adapter_rejects_streaming_before_workflow(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/harness/chat/completions",
            {
                "model": "agentic-controller",
                "stream": True,
                "agentic_controller_request": {
                    "workflow": "documenter.review",
                    "target_root": str(target),
                    "dry_run": True,
                },
            },
        )

    assert status == 400
    assert body["error"]["code"] == "stream_not_supported"
    assert not (config.output_root / ".agentic_reports").exists()
