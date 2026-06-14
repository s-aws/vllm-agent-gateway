from __future__ import annotations

import hashlib
import http.client
import json
import re
import shutil
import subprocess
import sys
import threading
import time
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

import pytest

from vllm_agent_gateway import model_capability_routing
from vllm_agent_gateway.controller_service.server import (
    ControllerServiceConfig,
    append_data_model_lookup_answer,
    create_server,
    handle_workflow_router_chat_completion,
    infer_workflow_router_mode,
    prompt_case_id_from_text,
    service_response_from_result,
)
from vllm_agent_gateway.controllers.workflow_router import plan as workflow_router_plan
from vllm_agent_gateway.controllers.skill_update.update import SkillUpdateRequest, invoke_skill_update
from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus
from vllm_agent_gateway.skills.registry import load_skill_registry, parse_skill_frontmatter, select_skills_for_workflow


REPO_ROOT = Path(__file__).resolve().parents[2]
advanced_workflow = pytest.mark.advanced_workflow


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def write_model_capability_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    task_policy: dict[str, str],
    profile_status: str = "warning",
) -> Path:
    profile_path = tmp_path / "model-profile.json"
    profile = {
        "schema_version": 1,
        "kind": "model_capability_profile",
        "status": profile_status,
        "candidate": {"candidate_id": "test-profile", "candidate_model_base_url": "http://127.0.0.1:8000/v1"},
        "task_policy": {
            key: {"status": status, "required_evidence": [key]}
            for key, status in task_policy.items()
        },
    }
    write_json(profile_path, profile)
    policy_path = tmp_path / "model-capability-routing.json"
    write_json(
        policy_path,
        {
            "schema_version": 1,
            "kind": "model_capability_routing_policy",
            "enforcement_mode": "fail_closed",
            "default_profile_id": "test-profile",
            "profiles": [
                {
                    "profile_id": "test-profile",
                    "status": "active",
                    "profile_path": str(profile_path),
                    "candidate_model_base_url": "http://127.0.0.1:8000/v1",
                }
            ],
            "task_class_rules": {
                "read_only_l1": {
                    "task_policy_key": "read_only_l1",
                    "allowed_task_policy_statuses": ["approved"],
                },
                "draft_only_l1": {
                    "task_policy_key": "draft_only_l1",
                    "allowed_task_policy_statuses": ["approved"],
                },
                "approval_gated_l1": {
                    "task_policy_key": "approval_gated_l1",
                    "allowed_task_policy_statuses": ["conditional"],
                },
                "l2_read_only": {
                    "task_policy_key": "l2_read_only",
                    "allowed_task_policy_statuses": ["approved"],
                },
                "apply_prep": {
                    "task_policy_key": "apply_prep",
                    "allowed_task_policy_statuses": ["conditional"],
                },
                "real_apply": {
                    "task_policy_key": "real_apply",
                    "allowed_task_policy_statuses": [],
                },
            },
        },
    )
    monkeypatch.setattr(model_capability_routing, "MODEL_CAPABILITY_ROUTING_POLICY_PATH", policy_path)
    return policy_path


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


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_skill_registration_root(tmp_path: Path) -> Path:
    root = tmp_path / "skill-registration-root"
    shutil.copytree(REPO_ROOT / "runtime", root / "runtime")
    profile_source = REPO_ROOT / "runtime-state" / "model-capability-profiles" / "phase100-current-profile.json"
    profile_target = root / "runtime-state" / "model-capability-profiles" / "phase100-current-profile.json"
    profile_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(profile_source, profile_target)
    shutil.copytree(REPO_ROOT / ".qwen" / "skills", root / ".qwen" / "skills")
    shutil.copy2(REPO_ROOT / "README.skill-registry.md", root / "README.skill-registry.md")
    (root / "docs").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        REPO_ROOT / "docs" / "SKILL_LIBRARY_SCALING_PLAN.md",
        root / "docs" / "SKILL_LIBRARY_SCALING_PLAN.md",
    )
    shutil.copy2(
        REPO_ROOT / "docs" / "SKILL_SCALING_BATCH_D_PROPOSAL.md",
        root / "docs" / "SKILL_SCALING_BATCH_D_PROPOSAL.md",
    )
    return root


def skill_registration_approval(ref: str = "test-founder-approval") -> dict[str, Any]:
    return {
        "status": "approved_for_skill_registration",
        "scope": "skill_batch_registration",
        "runtime_registry_append": True,
        "skill_body_install": True,
        "approval_refs": [ref],
    }


def skill_eval_promotion_approval(ref: str = "test-founder-promotion-approval") -> dict[str, Any]:
    return {
        "status": "approved_for_skill_promotion",
        "scope": "skill_eval_promotion",
        "eval_status_update": True,
        "approval_refs": [ref],
    }


def skill_deprecation_approval(ref: str = "test-founder-deprecation-approval") -> dict[str, Any]:
    return {
        "status": "approved_for_skill_deprecation",
        "scope": "skill_deprecation",
        "eval_status_update": True,
        "runtime_registry_update": True,
        "approval_refs": [ref],
    }


def skill_update_approval(
    ref: str = "test-founder-update-approval",
    *,
    skill_body_update: bool = False,
    eval_case_update: bool = False,
) -> dict[str, Any]:
    return {
        "status": "approved_for_skill_update",
        "scope": "skill_update",
        "runtime_registry_update": True,
        "skill_metadata_update": True,
        "skill_body_update": skill_body_update,
        "eval_case_update": eval_case_update,
        "approval_refs": [ref],
    }


def skill_pack_install_approval(ref: str = "test-founder-pack-install-approval") -> dict[str, Any]:
    return {
        "status": "approved_for_skill_pack_install",
        "scope": "skill_pack_install",
        "runtime_registry_append": True,
        "skill_body_install": True,
        "approval_refs": [ref],
    }


def register_feature_flag_skill(host: str, port: int) -> tuple[dict[str, Any], dict[str, Any]]:
    proposal_status, proposal_body = request_json(
        host,
        port,
        "POST",
        "/v1/controller/skill-batch/proposals",
        {
            "workflow": "skill_batch.propose",
            "schema_version": 1,
            "user_request": "Propose a skill batch for feature flag lookup. Proposal only. Do not register.",
        },
    )
    assert proposal_status == 200
    assert proposal_body["summary"]["proposal_status"] == "ready"
    registration_status, registration_body = request_json(
        host,
        port,
        "POST",
        "/v1/controller/skill-batch/registrations",
        {
            "workflow": "skill_batch.register",
            "schema_version": 1,
            "proposal_path": proposal_body["artifacts"]["skill_batch_proposal"],
            "approval": skill_registration_approval(),
        },
    )
    assert registration_status == 200
    assert registration_body["summary"]["registration_status"] == "installed"
    return proposal_body, registration_body


PHASE40_BATCH_B_SKILL_IDS = [
    "background-job-locator",
    "pytest-fixture-locator",
    "api-reference-locator",
    "agent-invariant-locator",
]
PHASE40_BATCH_B_EVAL_CASE_IDS = [
    "phase40_background_job_lookup",
    "phase40_pytest_fixture_lookup",
    "phase40_api_reference_lookup",
    "phase40_agent_invariant_lookup",
]
PHASE50_BATCH_C_SKILL_IDS = [
    "auth-check-locator",
    "state-mutation-locator",
    "external-integration-locator",
    "error-handling-path-locator",
]
PHASE50_BATCH_C_EVAL_CASE_IDS = [
    "phase50_auth_check_lookup",
    "phase50_state_mutation_lookup",
    "phase50_external_integration_lookup",
    "phase50_error_handling_path_lookup",
]
PHASE61_BATCH_D_SKILL_IDS = [
    "handler-branch-tracer",
    "table-schema-isolator",
    "runtime-entrypoint-disambiguator",
    "change-boundary-summarizer",
]
PHASE61_BATCH_D_EVAL_CASE_IDS = [
    "phase61_handler_branch_trace",
    "phase61_table_schema_only",
    "phase61_runtime_entrypoint_disambiguation",
    "phase61_change_boundary_summary",
]


def remove_phase40_batch_b_entries(config_root: Path) -> None:
    remove_skill_entries(config_root, PHASE40_BATCH_B_SKILL_IDS, PHASE40_BATCH_B_EVAL_CASE_IDS)


def remove_phase50_batch_c_entries(config_root: Path) -> None:
    remove_skill_entries(config_root, PHASE50_BATCH_C_SKILL_IDS, PHASE50_BATCH_C_EVAL_CASE_IDS)


def remove_phase61_batch_d_entries(config_root: Path) -> None:
    remove_skill_entries(config_root, PHASE61_BATCH_D_SKILL_IDS, PHASE61_BATCH_D_EVAL_CASE_IDS)


def remove_skill_entries(config_root: Path, skill_ids: list[str], eval_case_ids: list[str]) -> None:
    skills_path = config_root / "runtime" / "skills.json"
    evals_path = config_root / "runtime" / "skill_evals.json"
    skills_manifest = json.loads(skills_path.read_text(encoding="utf-8"))
    evals_manifest = json.loads(evals_path.read_text(encoding="utf-8"))
    skill_id_set = set(skill_ids)
    eval_case_id_set = set(eval_case_ids)
    skills_manifest["skills"] = [item for item in skills_manifest["skills"] if item.get("id") not in skill_id_set]
    evals_manifest["cases"] = [item for item in evals_manifest["cases"] if item.get("id") not in eval_case_id_set]
    skills_path.write_text(json.dumps(skills_manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    evals_path.write_text(json.dumps(evals_manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    for skill_id in skill_ids:
        shutil.rmtree(config_root / ".qwen" / "skills" / skill_id, ignore_errors=True)


def skill_action(audit: dict[str, Any], skill_id: str) -> dict[str, Any]:
    queue = audit["action_queue"]
    for item in queue:
        if item["skill_id"] == skill_id:
            return item
    raise AssertionError(f"missing lifecycle queue item for {skill_id}")


def skill_metadata(config_root: Path, skill_id: str) -> dict[str, Any]:
    manifest = json.loads((config_root / "runtime" / "skills.json").read_text(encoding="utf-8"))
    return next(item for item in manifest["skills"] if item["id"] == skill_id)


def skill_eval_case(config_root: Path, case_id: str) -> dict[str, Any]:
    manifest = json.loads((config_root / "runtime" / "skill_evals.json").read_text(encoding="utf-8"))
    return next(item for item in manifest["cases"] if item["id"] == case_id)


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
    try:
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        data = response.read().decode("utf-8")
        return response.status, json.loads(data)
    finally:
        connection.close()


def request_raw(
    host: str,
    port: int,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> tuple[int, str, dict[str, str]]:
    connection = http.client.HTTPConnection(host, port, timeout=30)
    try:
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        data = response.read().decode("utf-8")
        return response.status, data, {key: value for key, value in response.getheaders()}
    finally:
        connection.close()


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
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(data)
                self.wfile.flush()
                self.close_connection = True

            def log_message(self, format: str, *args: object) -> None:
                return

        return Handler


class FakeRouterModelEndpoint:
    def __init__(self, selected_workflow: str):
        self.selected_workflow = selected_workflow
        self.requests: list[dict[str, Any]] = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}/v1"

    def __enter__(self) -> "FakeRouterModelEndpoint":
        self.thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _handler_class(self) -> type[BaseHTTPRequestHandler]:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                request = json.loads(self.rfile.read(length).decode("utf-8"))
                owner.requests.append(request)
                route = {
                    "selected_workflow": owner.selected_workflow,
                    "confidence": "high",
                    "reason": "fake model route",
                    "approval_required_before": ["implementation_prep", "repository_mutation"],
                }
                response = {"choices": [{"message": {"content": json.dumps(route)}}]}
                data = json.dumps(response).encode("utf-8")
                self.send_response(200)
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


FROZEN_INVARIANT_OLD = (
    "- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n"
    "  maps, dashboard references, follow-up claims, fill ledger ownership, and DB\n"
    "  local rows."
)
FROZEN_INVARIANT_NEW = (
    "- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n"
    "  maps, dashboard references, follow-up claims, fill ledger ownership, DB\n"
    "  local rows, and stealth manager placed-order index keys."
)
EXTERNAL_COINBASE_GITHUB_TARGET = Path("C:/coinbase_testing_repo_frozen_tmp.github")


def make_execution_planning_tree(tmp_path: Path) -> Path:
    target = tmp_path / "allowed" / "planning-target"
    target.mkdir(parents=True)
    write_text(
        target / "docs" / "agents" / "INVARIANTS.md",
        "# Invariants\n\n" + FROZEN_INVARIANT_OLD + "\n",
    )
    write_text(
        target / "core" / "stealth_order_manager.py",
        "class StealthOrderManager:\n"
        "    stealth_order_id = 'client_order_id'\n"
        "    placed_order_index_key = 'client_order_id index'\n"
        "\n"
        "    def find_stealth_order_by_placed_order_id(self, placed_order_id):\n"
        "        return self.placed_order_index_key\n",
    )
    write_text(
        target / "core" / "orderbook.py",
        "class OrderBookReadOnlyError(RuntimeError):\n"
        "    pass\n"
        "\n"
        "class OrderBook:\n"
        "    def __init__(self, read_only=False):\n"
        "        self._read_only = read_only\n"
        "\n"
        "    def _check_writable(self, op):\n"
        "        if self._read_only:\n"
        "            raise OrderBookReadOnlyError(\n"
        "                f\"OrderBook is read-only; refusing {op}()\"\n"
        "            )\n"
        "\n"
        "    def upsert_order(self, client_order_id, payload):\n"
        "        self._check_writable(\"upsert_order\")\n",
    )
    write_text(
        target / "business" / "lot_config.py",
        "DEFAULT_PROFIT_MARGIN_PCT = 0.5\n",
    )
    write_text(
        target / "tests" / "unit" / "test_order_id_and_followup_rules.py",
        "def test_find_stealth_order_by_placed_order_id_uses_client_order_id_index():\n"
        "    assert 'client_order_id index'\n",
    )
    write_text(
        target / "tests" / "unit" / "test_orderbook_v2.py",
        "import pytest\n"
        "from core.orderbook import OrderBook, OrderBookReadOnlyError\n"
        "\n"
        "def test_blank_orderbook_has_empty_state():\n"
        "    assert OrderBook()._read_only is False\n",
    )
    write_text(
        target / "tests" / "regression" / "test_order_id_regression.py",
        "def test_filled_order_lookup_uses_client_order_id_not_exchange_order_id():\n"
        "    assert 'client_order_id'\n",
    )
    write_text(
        target / "tests" / "test_lot_tracking_integration.py",
        "def test_existing_lot_tracking_marker():\n"
        "    assert 'lot tracking'\n",
    )
    return target


def make_execution_planning_repo(tmp_path: Path) -> Path:
    target = make_execution_planning_tree(tmp_path)
    run_command(["git", "init"], target)
    run_command(
        [
            "git",
            "add",
            "docs/agents/INVARIANTS.md",
            "business/lot_config.py",
            "core/orderbook.py",
            "core/stealth_order_manager.py",
            "tests/unit/test_order_id_and_followup_rules.py",
            "tests/unit/test_orderbook_v2.py",
            "tests/regression/test_order_id_regression.py",
            "tests/test_lot_tracking_integration.py",
        ],
        target,
    )
    return target


def make_python_service_fixture_repo(tmp_path: Path) -> Path:
    target = tmp_path / "allowed" / "python-service-fixture"
    shutil.copytree(REPO_ROOT / "tests" / "fixtures" / "generalization" / "python_service_fixture", target)
    return target


def execution_planning_payload(target: Path) -> dict[str, Any]:
    return {
        "workflow": "execution_planning.plan",
        "schema_version": 1,
        "target_root": str(target),
        "user_request": (
            "Prepare implementation packet candidates for an approved frozen-repo documentation clarification "
            "that client_order_id owns internal lookup paths, including StealthOrderManager placed-order index keys. "
            "Use draft mode only and do not mutate the frozen repository."
        ),
        "mode": "dry_run",
        "approval": {
            "status": "approved_for_packet_design",
            "scope": "packet_design_only",
            "apply_allowed": False,
            "approval_refs": ["test:approved packet design only"],
        },
        "context": {
            "entrypoint_hints": [
                {
                    "path": "docs/agents/INVARIANTS.md",
                    "symbol": None,
                    "reason": "Test documentation target.",
                }
            ],
            "allowed_context_tools": ["structure_index", "git_grep", "read_file", "manual"],
        },
        "packet_operations": [
            {
                "kind": "replace_text",
                "path": "docs/agents/INVARIANTS.md",
                "old": FROZEN_INVARIANT_OLD,
                "new": FROZEN_INVARIANT_NEW,
            }
        ],
        "budgets": {
            "max_context_requests": 5,
            "max_files": 10,
            "max_records": 50,
            "max_model_calls": 12,
            "max_output_tokens": 4600,
        },
    }


class FakeExecutionPlanningEndpoint:
    def __init__(
        self,
        *,
        include_verification_commands: bool = True,
        context_grep_query: str = "client_order_id index",
        invalid_json_once_for_skill: str | None = None,
        packet_operation_proposal_response: dict[str, Any] | None = None,
        context_plan_response: dict[str, Any] | None = None,
    ):
        self.include_verification_commands = include_verification_commands
        self.context_grep_query = context_grep_query
        self.invalid_json_once_for_skill = invalid_json_once_for_skill
        self.packet_operation_proposal_response = packet_operation_proposal_response
        self.context_plan_response = context_plan_response
        self.call_counts: dict[str, int] = {}
        self.skill_case_inputs: dict[str, list[dict[str, Any]]] = {}
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}/v1"

    def __enter__(self) -> "FakeExecutionPlanningEndpoint":
        self.thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _handler_class(self) -> type[BaseHTTPRequestHandler]:
        owner = self
        include_verification_commands = self.include_verification_commands
        context_grep_query = self.context_grep_query

        def response_for_skill(skill_name: str) -> dict[str, Any]:
            if skill_name == "request-triage":
                return {
                    "request_type": "documentation",
                    "requires_repo_context": True,
                    "requires_user_approval_before_write": True,
                    "suggested_next_skill": "scope-and-assumptions",
                    "reason": "Packet candidate creation is write-adjacent.",
                    "open_questions": [],
                }
            if skill_name == "scope-and-assumptions":
                return {
                    "problem": {
                        "statement": "The invariant documentation needs a bounded clarification.",
                        "discovered_by": "user",
                        "start_or_duration": "unknown",
                        "current_impact": "unknown",
                    },
                    "clarification": {
                        "available_data": ["User supplied a target document and operation."],
                        "needed_data": ["Bounded context and related tests."],
                        "priority": "unknown",
                        "additional_resources_required": [],
                        "containment": {"required": True, "status": "not_needed", "actions": []},
                    },
                    "goal": {
                        "future_state": "The documentation packet candidate is reviewable.",
                        "benefit": "The target repo remains unchanged.",
                        "desired_timeline": "unknown",
                        "success_criteria": ["Draft packet preview exists.", "No mutation occurs."],
                    },
                    "scope": {
                        "in_scope": ["Packet design only."],
                        "out_of_scope": ["Apply mode."],
                        "assumptions": [],
                        "approval_required_before": ["apply"],
                        "stop_conditions": [],
                    },
                    "next_step": {"suggested_skill": "entrypoint-finder", "reason": "Need entrypoint.", "open_questions": []},
                }
            if skill_name == "entrypoint-finder":
                return {
                    "anchors": [
                        {
                            "value": "docs/agents/INVARIANTS.md",
                            "kind": "file",
                            "source": "user",
                            "reason": "User supplied target.",
                        }
                    ],
                    "entrypoint_candidates": [
                        {
                            "path": "docs/agents/INVARIANTS.md",
                            "symbol": None,
                            "kind": "document",
                            "line_range": [1, 4],
                            "confidence": "high",
                            "basis": "user supplied target",
                            "needs_confirmation": [],
                        }
                    ],
                    "selected_entrypoint": {
                        "path": "docs/agents/INVARIANTS.md",
                        "symbol": None,
                        "confidence": "high",
                        "selection_reason": "User supplied target.",
                    },
                    "followup_context_needed": [
                        {
                            "purpose": "docs",
                            "suggested_tool": "read_file",
                            "query": "docs/agents/INVARIANTS.md",
                            "targets": ["docs/agents/INVARIANTS.md"],
                            "max_results": 25,
                            "reason": "Need exact invariant text.",
                        },
                        {
                            "purpose": "tests",
                            "suggested_tool": "git_grep",
                            "query": context_grep_query,
                            "max_results": 25,
                            "reason": "Need related tests.",
                        },
                    ],
                    "stop": {"required": False, "reason": None, "open_questions": []},
                }
            if skill_name == "context-plan-builder":
                if owner.context_plan_response is not None:
                    return owner.context_plan_response
                return {
                    "context_plan_id": "CTXPLAN-0001",
                    "entrypoint": {"path": "docs/agents/INVARIANTS.md", "symbol": None, "confidence": "high"},
                    "context_requests": [
                        {
                            "id": "CTX-0001",
                            "purpose": "docs",
                            "suggested_tool": "read_file",
                            "query": "docs/agents/INVARIANTS.md",
                            "targets": ["docs/agents/INVARIANTS.md"],
                            "max_results": 25,
                            "max_files": 1,
                            "required": True,
                            "reason": "Need exact text.",
                            "safety_constraints": ["read-only"],
                        },
                        {
                            "id": "CTX-0002",
                            "purpose": "tests",
                            "suggested_tool": "git_grep",
                            "query": context_grep_query,
                            "targets": [],
                            "max_results": 25,
                            "max_files": 5,
                            "required": True,
                            "reason": "Need test evidence.",
                            "safety_constraints": ["read-only"],
                        },
                    ],
                    "request_order": ["CTX-0001", "CTX-0002"],
                    "context_budget": {"max_requests": 5, "max_files": 10, "max_records": 50, "allow_broad_scan": False},
                    "excluded_context": [],
                    "next_step": {"suggested_skill": "impact-map-builder", "reason": "Context is bounded."},
                    "stop": {"required": False, "reason": None, "open_questions": []},
                }
            if skill_name == "impact-map-builder":
                return {
                    "impact_map_id": "IMPACT-0001",
                    "objective": "Prepare documentation packet candidate.",
                    "basis": {
                        "request_type": "documentation",
                        "entrypoint": {"path": "docs/agents/INVARIANTS.md", "symbol": None, "confidence": "high"},
                        "context_plan_id": "CTXPLAN-0001",
                        "context_result_refs": ["CTX-0001", "CTX-0002"],
                    },
                    "behavior_paths": [],
                    "affected_files": [
                        {
                            "path": "docs/agents/INVARIANTS.md",
                            "role": "entrypoint",
                            "reason": "Target doc.",
                            "confidence": "high",
                            "evidence_refs": ["CTX-0001"],
                        }
                    ],
                    "affected_symbols": [],
                    "dependencies": [],
                    "related_tests": [
                        {
                            "path": "tests/unit/test_order_id_and_followup_rules.py",
                            "test_name": "test_find_stealth_order_by_placed_order_id_uses_client_order_id_index",
                            "coverage_for": ["core/stealth_order_manager.py"],
                            "status": "existing",
                            "confidence": "high",
                            "evidence_refs": ["CTX-0002"],
                        }
                    ],
                    "duplicate_or_parallel_paths": [],
                    "risks": [],
                    "unknowns": [],
                    "next_step": {"suggested_skill": "execution-plan-writer", "reason": "Enough context."},
                    "stop": {"required": False, "reason": None, "open_questions": []},
                }
            if skill_name == "execution-plan-writer":
                return {
                    "plan_id": "EP-0001",
                    "plan_mode": "implementation_prep",
                    "objective": "Prepare documentation packet candidate.",
                    "basis": {
                        "request_type": "documentation",
                        "entrypoint": {"path": "docs/agents/INVARIANTS.md", "symbol": None, "confidence": "high"},
                        "source_refs": ["docs/agents/INVARIANTS.md"],
                        "assumptions": [],
                        "unknowns": [],
                    },
                    "preconditions": ["Packet design approved."],
                    "steps": [
                        {
                            "id": "STEP-0001",
                            "action": "design_packet",
                            "description": "Design documentation packet.",
                            "owner": "agent",
                            "target_files": ["docs/agents/INVARIANTS.md"],
                            "source_refs": ["docs/agents/INVARIANTS.md"],
                            "acceptance_criteria": ["Packet preview is exact."],
                            "blocked_by": [],
                            "approval_required_before": [],
                        }
                    ],
                    "approval_required": False,
                    "verification_strategy": [],
                    "containment": {"required": True, "actions": ["draft only"]},
                    "next_step": {"suggested_skill": "implementation-packet-designer", "reason": "Design packet."},
                    "stop": {"required": False, "reason": None, "open_questions": []},
                }
            if skill_name == "implementation-packet-designer":
                packet = {
                    "id": "IMP-0001",
                    "target_files": ["docs/agents/INVARIANTS.md"],
                    "allowed_operations": ["replace_text"],
                    "operation": {
                        "kind": "replace_text",
                        "path": "docs/agents/INVARIANTS.md",
                        "old": FROZEN_INVARIANT_OLD,
                        "new": FROZEN_INVARIANT_NEW,
                    },
                    "source_refs": [{"path": "docs/agents/INVARIANTS.md", "line_range": [1, 4]}],
                    "acceptance_criteria": ["Packet preview is exact."],
                    "max_context_tokens": 4000,
                }
                return {
                    "packet_set_id": "IMPSET-0001",
                    "source_plan_id": "EP-0001",
                    "approval": {
                        "status": "approved",
                        "approved_step_ids": ["STEP-0001"],
                        "approval_refs": ["test:approved packet design only"],
                    },
                    "workflow_compatibility": {
                        "target_workflow": "implementation.workflow",
                        "schema_version": 1,
                        "supported_operations": ["append_text", "replace_text", "create_file"],
                        "default_mode": "draft",
                        "apply_mode_allowed_by_this_skill": False,
                        "notes": [],
                    },
                    "packet_candidates": [{**packet, "source_step_id": "STEP-0001", "task": "Update invariant."}],
                    "blocked_packets": [],
                    "packet_file_preview": {"schema_version": 1, "packets": [packet], "verification_commands": []},
                    "next_step": {"suggested_skill": "verification-planner", "reason": "Plan verification."},
                    "stop": {"required": False, "reason": None, "open_questions": []},
                }
            if skill_name == "verification-planner":
                return {
                    "verification_plan_id": "VERIFY-0001",
                    "source_plan_id": "EP-0001",
                    "source_packet_set_id": "IMPSET-0001",
                    "basis": {
                        "target_files": ["docs/agents/INVARIANTS.md"],
                        "packet_ids": ["IMP-0001"],
                        "acceptance_criteria": ["Packet preview is exact."],
                        "related_tests": ["tests/unit/test_order_id_and_followup_rules.py"],
                        "risks": [],
                        "unknowns": [],
                    },
                    "verification_commands": (
                        [
                            {
                                "id": "verification-0001",
                                "command": ["python", "-m", "pytest", "tests/unit/test_order_id_and_followup_rules.py"],
                                "reason": "Relevant unit test.",
                                "associated_files": ["tests/unit/test_order_id_and_followup_rules.py"],
                                "timeout_seconds": 120,
                                "source_refs": ["tests/unit/test_order_id_and_followup_rules.py"],
                            }
                        ]
                        if include_verification_commands
                        else []
                    ),
                    "manual_checks": [],
                    "coverage_gaps": [],
                    "rejected_commands": [],
                    "next_step": {"suggested_skill": "feedback-capture", "reason": "Capture feedback."},
                    "stop": {"required": False, "reason": None, "open_questions": []},
                }
            if skill_name == "feedback-capture":
                return {
                    "workflow_id": "execution_planning.plan",
                    "run_id": "test-run",
                    "useful": [{"id": "USEFUL-0001", "observation": "Dry run completed.", "evidence_refs": []}],
                    "wrong": [],
                    "missing": [],
                    "too_slow_or_noisy": [],
                    "next_adjustments": [
                        {
                            "id": "ADJUST-0001",
                            "target": "controller",
                            "action": "Review packet.",
                            "owner": "founder",
                            "requires_approval_before_write": True,
                            "source_feedback_refs": ["USEFUL-0001"],
                        }
                    ],
                }
            raise AssertionError(f"Unexpected skill {skill_name}")

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                request = json.loads(self.rfile.read(length).decode("utf-8"))
                content = request["messages"][1]["content"]
                match = re.search(r"<skill_name>([^<]+)</skill_name>", content)
                if match is None:
                    if "Propose exact draft-only implementation packet operations" in content:
                        proposal_response = owner.packet_operation_proposal_response or {
                            "packet_operations": [
                                {
                                    "kind": "replace_text",
                                    "path": "core/stealth_order_manager.py",
                                    "old": "    placed_order_id_lookup = 'client_order_id index'",
                                    "new": (
                                        "    placed_order_id_lookup = 'client_order_id index'\n"
                                        "    placed_order_lookup_path = 'single manager index'"
                                    ),
                                }
                            ],
                            "blockers": [],
                            "rationale": "The old text is present in the supplied snippet.",
                        }
                        content = json.dumps(proposal_response)
                    else:
                        content = json.dumps(
                            {
                                "selected_workflow": "execution_planning.plan",
                                "confidence": "high",
                                "reason": "Implementation packet preparation should use execution planning.",
                                "approval_required_before": [],
                            }
                        )
                else:
                    skill_name = match.group(1)
                    owner.call_counts[skill_name] = owner.call_counts.get(skill_name, 0) + 1
                    marker = "Case input JSON:\n"
                    suffix = "\n\nReturn exactly one JSON object"
                    marker_index = content.find(marker)
                    suffix_index = content.find(suffix, marker_index)
                    if marker_index >= 0 and suffix_index > marker_index:
                        raw_case_input = content[marker_index + len(marker) : suffix_index]
                        parsed_case_input = json.loads(raw_case_input)
                        owner.skill_case_inputs.setdefault(skill_name, []).append(parsed_case_input)
                    if owner.invalid_json_once_for_skill == skill_name and owner.call_counts[skill_name] == 1:
                        content = '{"invalid_json": '
                    else:
                        content = json.dumps(response_for_skill(skill_name))
                response = {"choices": [{"message": {"content": content}}]}
                data = json.dumps(response).encode("utf-8")
                self.send_response(200)
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

        status, raw_body, headers = request_raw(host, port, "GET", "/health")
        body = json.loads(raw_body)
        assert status == 200
        assert headers["Connection"] == "close"
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
                "budgets": {"max_chunks": 1, "parallelism": 2},
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
        report = json.loads(Path(body["artifacts"]["json_report"]).read_text(encoding="utf-8"))
        assert report["parallelism"] == 2

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


def test_harness_adapter_uses_latest_message_envelope_when_history_contains_old_envelope(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    old_envelope = {
        "agentic_controller_request": {
            "workflow": "documenter.review",
            "target_root": str(tmp_path / "not-allowlisted"),
            "doc": "README.md",
            "dry_run": True,
        }
    }
    latest_envelope = {
        "agentic_controller_request": {
            "workflow": "documenter.review",
            "target_root": str(target),
            "doc": "README.md",
            "mode": "full",
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
                    {"role": "user", "content": json.dumps(old_envelope)},
                    {"role": "assistant", "content": "previous controller result"},
                    {"role": "user", "content": json.dumps(latest_envelope)},
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    assert compact["status"] == "completed"
    assert compact["workflow"] == "documenter.review"
    assert "json_report" in compact["artifacts"]


def test_harness_adapter_ignores_old_message_envelope_when_latest_message_is_normal_chat(tmp_path: Path) -> None:
    make_target_repo(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    old_envelope = {
        "agentic_controller_request": {
            "workflow": "documenter.review",
            "target_root": str(tmp_path / "not-allowlisted"),
            "doc": "README.md",
            "dry_run": True,
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
                    {"role": "user", "content": json.dumps(old_envelope)},
                    {"role": "assistant", "content": "previous controller result"},
                    {"role": "user", "content": "Normal skill validation prompt without a controller envelope."},
                ],
            },
        )

    assert status == 400
    assert body["error"]["code"] == "missing_controller_envelope"


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


def test_controller_service_runs_execution_planning_dry_run_and_preserves_target(tmp_path: Path) -> None:
    target = make_execution_planning_repo(tmp_path)
    original_text = (target / "docs" / "agents" / "INVARIANTS.md").read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeExecutionPlanningEndpoint(include_verification_commands=False) as endpoint:
        payload = {**execution_planning_payload(target), "role_base_url": endpoint.base_url}
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/execution-planning/plans",
                payload,
            )

            assert status == 200
            assert body["workflow"] == "execution_planning.plan"
            assert body["status"] == "completed"
            assert body["summary"]["packet_candidates"] == 1
            assert body["summary"]["packet_file_preview_packets"] == 1
            assert body["summary"]["repo_mutated"] is False
            assert body["non_mutation"]["changed_files"] == []
            assert "packet_preview" in body["artifacts"]
            assert "implementation_workflow_report" in body["artifacts"]
            assert Path(body["artifacts"]["packet_preview"]).exists()
            assert Path(body["artifacts"]["implementation_workflow_report"]).exists()
            assert body["tool_policy"]["workflow"] == "execution_planning.plan"
            assert body["tool_policy"]["role_id"] == "architect/default"
            assert body["tool_policy"]["model_visible_tool_ids"] == []

            status, run_body = request_json(host, port, "GET", f"/v1/controller/runs/{body['run_id']}")

    assert status == 200
    assert run_body["run_id"] == body["run_id"]
    assert (target / "docs" / "agents" / "INVARIANTS.md").read_text(encoding="utf-8") == original_text


def test_execution_planning_retries_once_after_invalid_skill_json(tmp_path: Path) -> None:
    target = make_execution_planning_repo(tmp_path)
    original_text = (target / "docs" / "agents" / "INVARIANTS.md").read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeExecutionPlanningEndpoint(
        include_verification_commands=False,
        invalid_json_once_for_skill="impact-map-builder",
    ) as endpoint:
        payload = {**execution_planning_payload(target), "role_base_url": endpoint.base_url}
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/execution-planning/plans",
                payload,
            )

    assert status == 200
    assert body["status"] == "completed"
    assert endpoint.call_counts["impact-map-builder"] == 2
    assert body["non_mutation"]["changed_files"] == []
    assert (target / "docs" / "agents" / "INVARIANTS.md").read_text(encoding="utf-8") == original_text


def test_execution_planning_lookup_falls_back_for_non_git_target_tree(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    original_text = (target / "docs" / "agents" / "INVARIANTS.md").read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeExecutionPlanningEndpoint() as endpoint:
        payload = {**execution_planning_payload(target), "role_base_url": endpoint.base_url}
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/execution-planning/plans",
                payload,
            )

    assert status == 200
    assert body["non_mutation"]["changed_files"] == []
    assert ["python", "-m", "pytest", "tests/unit/test_order_id_and_followup_rules.py"] in body["summary"]["verification_commands"]
    context_results = json.loads(Path(body["artifacts"]["context_results"]).read_text(encoding="utf-8"))
    grep_result = next(item for item in context_results["results"] if item["id"] == "CTX-0002")
    assert grep_result["source"] == "git_grep"
    assert any("tests/unit/test_order_id_and_followup_rules.py" in match for match in grep_result["matches"])
    test_discovery = next(item for item in context_results["results"] if item["id"] == "CTX-TEST-0001")
    assert test_discovery["source"] == "test_discovery"
    assert any(
        item["path"] == "tests/unit/test_order_id_and_followup_rules.py"
        for item in test_discovery["related_test_files"]
    )
    assert (target / "docs" / "agents" / "INVARIANTS.md").read_text(encoding="utf-8") == original_text


def test_execution_planning_compacts_model_context_before_impact_map_builder(tmp_path: Path) -> None:
    target = make_execution_planning_repo(tmp_path)
    original_text = (target / "docs" / "agents" / "INVARIANTS.md").read_text(encoding="utf-8")
    context_plan = {
        "context_plan_id": "CTXPLAN-COMPACT-0001",
        "entrypoint": {"path": "docs/agents/INVARIANTS.md", "symbol": None, "confidence": "high"},
        "context_requests": [
            {
                "id": "CTX-0001",
                "purpose": "docs",
                "suggested_tool": "read_file",
                "query": "docs/agents/INVARIANTS.md",
                "targets": ["docs/agents/INVARIANTS.md"],
                "max_results": 25,
                "max_files": 1,
                "required": True,
                "reason": "Need exact text.",
                "safety_constraints": ["read-only"],
            },
            {
                "id": "CTX-STRUCT-0001",
                "purpose": "structure",
                "suggested_tool": "structure_index",
                "targets": ["core/stealth_order_manager.py"],
                "max_results": 25,
                "max_files": 1,
                "required": True,
                "reason": "Need compact structural evidence.",
                "safety_constraints": ["read-only"],
            },
            {
                "id": "CTX-STRUCT-0002",
                "purpose": "duplicate_structure",
                "suggested_tool": "structure_index",
                "targets": ["core/stealth_order_manager.py"],
                "max_results": 25,
                "max_files": 1,
                "required": False,
                "reason": "Duplicate request should not be repeated in model input.",
                "safety_constraints": ["read-only"],
            },
            {
                "id": "CTX-0002",
                "purpose": "tests",
                "suggested_tool": "git_grep",
                "query": "client_order_id index",
                "targets": [],
                "max_results": 25,
                "max_files": 5,
                "required": True,
                "reason": "Need test evidence.",
                "safety_constraints": ["read-only"],
            },
        ],
        "request_order": ["CTX-0001", "CTX-STRUCT-0001", "CTX-STRUCT-0002", "CTX-0002"],
        "context_budget": {"max_requests": 5, "max_files": 10, "max_records": 50, "allow_broad_scan": False},
        "excluded_context": [],
        "next_step": {"suggested_skill": "impact-map-builder", "reason": "Context is bounded."},
        "stop": {"required": False, "reason": None, "open_questions": []},
    }
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeExecutionPlanningEndpoint(
        include_verification_commands=False,
        context_plan_response=context_plan,
    ) as endpoint:
        payload = {**execution_planning_payload(target), "role_base_url": endpoint.base_url}
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/execution-planning/plans",
                payload,
            )

    assert status == 200
    assert body["status"] == "completed"
    assert "context_results" in body["artifacts"]
    assert "context_results_for_model" in body["artifacts"]
    context_results = json.loads(Path(body["artifacts"]["context_results"]).read_text(encoding="utf-8"))
    compact_context = json.loads(Path(body["artifacts"]["context_results_for_model"]).read_text(encoding="utf-8"))

    full_structure_results = [item for item in context_results["results"] if item["source"] == "structure_index"]
    assert len(full_structure_results) == 2
    assert all("slice" in item for item in full_structure_results)
    compact_structure_results = [
        item for item in compact_context["results"] if item.get("source") == "structure_index"
    ]
    assert len(compact_structure_results) == 1
    assert "slice" not in compact_structure_results[0]
    assert "slice_summary" in compact_structure_results[0]
    assert compact_context["compaction"]["deduplicated_result_count"] == 1
    assert compact_context["compaction"]["compact_size_bytes"] < compact_context["compaction"]["original_size_bytes"]

    compact_packet_result = next(item for item in compact_context["results"] if item["id"] == "CTX-PACKET-0001")
    assert compact_packet_result["exact_text"] == FROZEN_INVARIANT_OLD
    assert compact_packet_result["operation"]["new"] == FROZEN_INVARIANT_NEW

    impact_input = endpoint.skill_case_inputs["impact-map-builder"][-1]
    assert impact_input["context_results"] == compact_context["results"]
    assert impact_input["context_compaction"] == compact_context["compaction"]
    assert all("slice" not in item for item in impact_input["context_results"] if isinstance(item, dict))
    assert (target / "docs" / "agents" / "INVARIANTS.md").read_text(encoding="utf-8") == original_text


def test_execution_planning_runs_against_git_enabled_frozen_coinbase_fixture(tmp_path: Path) -> None:
    target = EXTERNAL_COINBASE_GITHUB_TARGET
    if not target.exists():
        pytest.skip(f"External frozen Coinbase fixture is not present: {target}")
    git_top_level = run_command(["git", "rev-parse", "--show-toplevel"], target)
    if git_top_level.returncode != 0:
        pytest.skip(f"External frozen Coinbase fixture is not a Git worktree: {target}")
    assert Path(git_top_level.stdout.strip()).resolve() == target.resolve()

    invariant_path = target / "docs" / "agents" / "INVARIANTS.md"
    original_text = invariant_path.read_text(encoding="utf-8")
    assert FROZEN_INVARIANT_OLD in original_text
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(target,),
        port=0,
    )
    with FakeExecutionPlanningEndpoint(
        include_verification_commands=False,
        context_grep_query="StealthOrderManager",
    ) as endpoint:
        payload = {**execution_planning_payload(target), "role_base_url": endpoint.base_url}
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/execution-planning/plans",
                payload,
            )

    assert status == 200
    assert body["status"] == "completed"
    assert body["summary"]["packet_candidates"] == 1
    assert body["summary"]["repo_mutated"] is False
    assert body["non_mutation"]["changed_files"] == []
    assert any(
        command[:3] == ["python", "-m", "pytest"]
        and any(part.startswith("tests/") for part in command[3:])
        for command in body["summary"]["verification_commands"]
    )
    context_results = json.loads(Path(body["artifacts"]["context_results"]).read_text(encoding="utf-8"))
    grep_result = next(item for item in context_results["results"] if item["id"] == "CTX-0002")
    assert grep_result["source"] == "git_grep"
    assert any("StealthOrderManager" in match for match in grep_result["matches"])
    assert invariant_path.read_text(encoding="utf-8") == original_text


def test_harness_adapter_runs_execution_planning_with_top_level_envelope(tmp_path: Path) -> None:
    target = make_execution_planning_repo(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeExecutionPlanningEndpoint() as endpoint:
        payload = {**execution_planning_payload(target), "role_base_url": endpoint.base_url}
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/harness/chat/completions",
                {
                    "model": "agentic-controller",
                    "agentic_controller_request": payload,
                },
            )

    assert status == 200
    compact = body["agentic_controller_response"]
    assert compact["workflow"] == "execution_planning.plan"
    assert compact["status"] == "completed"
    assert compact["summary"]["packet_candidates"] == 1
    assert compact["non_mutation"]["changed_files"] == []
    assert "execution_planning.plan completed" in body["choices"][0]["message"]["content"]
    assert "Artifacts:" in body["choices"][0]["message"]["content"]


def test_execution_planning_rejects_apply_mode_before_model_calls(tmp_path: Path) -> None:
    target = make_execution_planning_repo(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    payload = execution_planning_payload(target)
    payload["approval"] = {
        "status": "approved_for_packet_design",
        "scope": "packet_design_only",
        "apply_allowed": True,
        "approval_refs": ["test:apply now"],
    }
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/execution-planning/plans",
            payload,
        )

    assert status == 400
    assert body["error"]["code"] == "apply_mode_not_supported"


def test_execution_planning_rejects_raw_codegraph_context(tmp_path: Path) -> None:
    target = make_execution_planning_repo(tmp_path)
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
            "/v1/controller/execution-planning/plans",
            {
                "workflow": "execution_planning.plan",
                "schema_version": 1,
                "target_root": str(target),
                "user_request": "Use raw CodeGraphContext Cypher to scan callers.",
                "mode": "investigation_only",
                "context": {"allowed_context_tools": ["raw_mcp_cypher", "codegraph_index_package"]},
            },
        )

    assert status == 400
    assert body["error"]["code"] == "raw_codegraph_not_allowed"


def code_context_lookup_payload(target: Path) -> dict[str, Any]:
    return {
        "workflow": "code_context.lookup",
        "schema_version": 1,
        "target_root": str(target),
        "query": "client_order_id index",
        "paths": ["core/stealth_order_manager.py"],
        "max_results": 5,
        "max_files": 2,
    }


def make_relationship_lookup_repo(tmp_path: Path) -> Path:
    target = tmp_path / "allowed" / "relationship-target"
    target.mkdir(parents=True)
    write_text(
        target / "core" / "service.py",
        "def place_order(order):\n"
        "    return order\n\n"
        "def internal_wrapper(order):\n"
        "    return place_order(order)\n",
    )
    write_text(
        target / "app" / "handler.py",
        "from core.service import place_order\n\n"
        "def handle(order):\n"
        "    return place_order(order)\n",
    )
    write_text(
        target / "tests" / "test_handler.py",
        "from app.handler import handle\n\n"
        "def test_handle_calls_place_order():\n"
        "    assert handle({'id': 1}) == {'id': 1}\n",
    )
    run_command(["git", "init"], target)
    run_command(["git", "add", "core/service.py", "app/handler.py", "tests/test_handler.py"], target)
    return target


def make_config_lookup_repo(tmp_path: Path) -> Path:
    target = tmp_path / "allowed" / "config-target"
    target.mkdir(parents=True)
    write_text(
        target / "configuration.py",
        "from os import getenv\n\n"
        "COINBASE_API_KEY = getenv('COINBASE_API_KEY')\n"
        "API_KEY_ALIAS = COINBASE_API_KEY\n",
    )
    write_text(
        target / "core" / "order_engine.py",
        "from configuration import COINBASE_API_KEY\n\n"
        "def api_key_for_engine():\n"
        "    return COINBASE_API_KEY\n",
    )
    write_text(target / "pyproject.toml", "[tool.pytest.ini_options]\npythonpath = ['.']\n")
    return target


def make_l1_expansion_repo(tmp_path: Path, *, initialize_git: bool = True) -> Path:
    target = tmp_path / "allowed" / "l1-expansion-target"
    target.mkdir(parents=True)
    write_text(
        target / "README.md",
        "# L1 Expansion Fixture\n\n"
        "Runtime entrypoint: `main.py`.\n\n"
        "The dashboard supports the `request_stealth_orders` WebSocket message.\n",
    )
    write_text(
        target / "agent.md",
        "# Agent Notes\n\n"
        "`request_stealth_orders` asks the dashboard to return a stealth order snapshot.\n",
    )
    write_text(
        target / "main.py",
        "\"\"\"Main entry point for the test trading engine.\"\"\"\n\n"
        "def main():\n"
        "    return 'started'\n\n"
        "if __name__ == \"__main__\":\n"
        "    main()\n",
    )
    write_text(
        target / "configuration.py",
        "from os import getenv\n\n"
        "from coinbase.rest import RESTClient\n\n"
        "API_KEY = getenv('COINBASE_API_KEY')\n"
        "API_SECRET = getenv('COINBASE_API_SECRET')\n\n"
        "def rest_client():\n"
        "    return RESTClient(api_key=API_KEY, api_secret=API_SECRET, rate_limit_headers=True)\n",
    )
    write_text(
        target / "dashboard_server.py",
        "import json\n\n"
        "from core.exceptions import WebSocketMessageError\n"
        "from logging_service import get_logger\n\n"
        "logger = get_logger('DashboardServer')\n\n"
        "async def handle_websocket_message(websocket, message, stealth_order_bridge):\n"
        "    data = json.loads(message)\n"
        "    msg_type = data.get('type')\n"
        "    if not msg_type:\n"
        "        raise WebSocketMessageError(\"Missing 'type' field in message\", raw_data=message)\n"
        "    logger.debug(f'[HANDLER] Received message type: {msg_type}')\n"
        "    if msg_type == 'request_stealth_orders':\n"
        "        await send_stealth_orders_snapshot(websocket, stealth_order_bridge)\n\n"
        "async def send_stealth_orders_snapshot(websocket, stealth_order_bridge):\n"
        "    orders = stealth_order_bridge.get_stealth_orders()\n"
        "    await websocket.send(json.dumps({'type': 'stealth_orders_snapshot', 'orders': orders}))\n",
    )
    write_text(
        target / "database" / "order.py",
        "def create_stealth_orders_table():\n"
        "    sql = \"\"\"\n"
        "    CREATE TABLE IF NOT EXISTS stealth_orders (\n"
        "        stealth_order_id UUID PRIMARY KEY,\n"
        "        parent_order_id UUID,\n"
        "        client_order_id TEXT,\n"
        "        status VARCHAR(20),\n"
        "        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n"
        "    );\n"
        "    \"\"\"\n"
        "    return sql\n"
        "\n"
        "def read_stealth_orders(conn):\n"
        "    return conn.execute(\n"
        "        \"SELECT stealth_order_id, client_order_id FROM stealth_orders WHERE status = ?\",\n"
        "        (\"HIDDEN\",),\n"
        "    ).fetchall()\n"
        "\n"
        "def write_stealth_order(conn, stealth_order_id, client_order_id):\n"
        "    return conn.execute(\n"
        "        \"INSERT INTO stealth_orders (stealth_order_id, client_order_id) VALUES (?, ?)\",\n"
        "        (stealth_order_id, client_order_id),\n"
        "    )\n",
    )
    write_text(
        target / "core" / "stealth_order_manager.py",
        "\"\"\"Stealth order lifecycle helpers for hidden order creation and lookup.\"\"\"\n\n"
        "import json\n"
        "from datetime import datetime\n\n"
        "from core.enums import StealthOrderStatus\n"
        "from database.order import create_stealth_orders_table\n\n"
        "class StealthOrderManager:\n"
        "    placed_order_index_key = 'client_order_id index'\n\n"
        "    def find_stealth_order_by_placed_order_id(self, placed_order_id):\n"
        "        return self.placed_order_index_key\n\n"
        "    def ensure_schema(self):\n"
        "        return create_stealth_orders_table()\n",
    )
    write_text(target / "core" / "exceptions.py", "class WebSocketMessageError(Exception):\n    pass\n")
    write_text(target / "core" / "enums.py", "class StealthOrderStatus:\n    HIDDEN = 'HIDDEN'\n")
    write_text(
        target / "tests" / "test_dashboard_handler.py",
        "def test_request_stealth_orders_handler_exists():\n"
        "    assert 'request_stealth_orders'\n"
        "\n"
        "def test_missing_type_field_message_is_stable():\n"
        "    assert \"Missing 'type' field in message\"\n",
    )
    write_text(
        target / "tests" / "unit" / "test_order_id_and_followup_rules.py",
        "def test_find_stealth_order_by_placed_order_id_uses_client_order_id_index():\n"
        "    assert 'placed_order_id'\n",
    )
    if initialize_git:
        run_command(["git", "init"], target)
        run_command(
            [
                "git",
                "add",
                "dashboard_server.py",
                "README.md",
                "agent.md",
                "main.py",
                "configuration.py",
                "database/order.py",
                "core/stealth_order_manager.py",
                "core/exceptions.py",
                "core/enums.py",
                "tests/test_dashboard_handler.py",
                "tests/unit/test_order_id_and_followup_rules.py",
            ],
            target,
        )
    return target


def test_code_context_lookup_returns_bounded_read_only_artifacts(tmp_path: Path) -> None:
    target = make_execution_planning_repo(tmp_path)
    original_text = (target / "core" / "stealth_order_manager.py").read_text(encoding="utf-8")
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
            "/v1/controller/code-context/lookups",
            code_context_lookup_payload(target),
        )

    assert status == 200
    assert body["workflow"] == "code_context.lookup"
    assert body["status"] == "completed"
    assert body["summary"]["grep_match_count"] >= 1
    assert body["tool_policy"]["workflow"] == "code_context.lookup"
    assert body["tool_policy"]["model_visible_tool_ids"] == []
    assert "lookup_results" in body["artifacts"]
    results = json.loads(Path(body["artifacts"]["lookup_results"]).read_text(encoding="utf-8"))
    assert results["query"] == "client_order_id index"
    assert any(match["path"].endswith("stealth_order_manager.py") for match in results["grep_matches"])
    assert results["file_snippets"][0]["path"] == "core/stealth_order_manager.py"
    assert (target / "core" / "stealth_order_manager.py").read_text(encoding="utf-8") == original_text


def test_code_context_lookup_returns_curated_relationship_artifacts(tmp_path: Path) -> None:
    target = make_relationship_lookup_repo(tmp_path)
    original_text = (target / "app" / "handler.py").read_text(encoding="utf-8")
    payload = {
        "workflow": "code_context.lookup",
        "schema_version": 1,
        "target_root": str(target),
        "query": "place_order",
        "paths": ["core/service.py", "app/handler.py"],
        "allowed_context_tools": ["structure_index", "git_grep", "read_file", "codegraph_context"],
        "relationship_queries": [
            {
                "kind": "callers",
                "symbol": "place_order",
                "max_results": 10,
            }
        ],
        "max_results": 10,
        "max_files": 3,
    }
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
            "/v1/controller/code-context/lookups",
            payload,
        )

    assert status == 200
    assert body["workflow"] == "code_context.lookup"
    assert body["status"] == "completed"
    assert body["summary"]["relationship_query_count"] == 1
    assert body["summary"]["relationship_result_count"] >= 2
    assert "relationship_results" in body["artifacts"]
    assert "codegraph_context" in body["tool_policy"]["controller_tool_ids"]
    results = json.loads(Path(body["artifacts"]["relationship_results"]).read_text(encoding="utf-8"))
    assert results["adapter"] == "curated_codegraph_context"
    matches = results["queries"][0]["matches"]
    assert any(match["source_path"] == "app/handler.py" and match["source_symbol"].endswith(".handle") for match in matches)
    assert any(
        match["source_path"] == "core/service.py" and match["source_symbol"].endswith(".internal_wrapper")
        for match in matches
    )
    assert (target / "app" / "handler.py").read_text(encoding="utf-8") == original_text


def test_code_context_lookup_rejects_relationship_queries_without_curated_tool(tmp_path: Path) -> None:
    target = make_relationship_lookup_repo(tmp_path)
    payload = {
        "workflow": "code_context.lookup",
        "schema_version": 1,
        "target_root": str(target),
        "query": "place_order",
        "allowed_context_tools": ["structure_index", "git_grep", "read_file"],
        "relationship_queries": [{"kind": "callers", "symbol": "place_order"}],
    }
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
            "/v1/controller/code-context/lookups",
            payload,
        )

    assert status == 400
    assert body["error"]["code"] == "relationship_tool_required"


def test_code_context_lookup_rejects_unsupported_relationship_kind(tmp_path: Path) -> None:
    target = make_relationship_lookup_repo(tmp_path)
    payload = {
        "workflow": "code_context.lookup",
        "schema_version": 1,
        "target_root": str(target),
        "query": "place_order",
        "allowed_context_tools": ["codegraph_context"],
        "relationship_queries": [{"kind": "neighbors", "symbol": "place_order"}],
    }
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
            "/v1/controller/code-context/lookups",
            payload,
        )

    assert status == 400
    assert body["error"]["code"] == "invalid_relationship_query"


def test_harness_adapter_runs_code_context_lookup_with_latest_message_envelope(tmp_path: Path) -> None:
    target = make_execution_planning_repo(tmp_path)
    old_payload = {
        "agentic_controller_request": {
            "workflow": "code_context.lookup",
            "target_root": str(tmp_path / "not-allowlisted"),
            "query": "client_order_id",
        }
    }
    latest_payload = {"agentic_controller_request": code_context_lookup_payload(target)}
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
                "messages": [
                    {"role": "user", "content": json.dumps(old_payload)},
                    {"role": "assistant", "content": "old run"},
                    {"role": "user", "content": json.dumps(latest_payload)},
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    assert compact["workflow"] == "code_context.lookup"
    assert compact["status"] == "completed"
    assert "lookup_results" in compact["artifacts"]
    assert "code_context.lookup completed" in body["choices"][0]["message"]["content"]


def test_code_context_lookup_rejects_raw_codegraph_context(tmp_path: Path) -> None:
    target = make_execution_planning_repo(tmp_path)
    payload = {
        **code_context_lookup_payload(target),
        "query": "Use raw CodeGraphContext Cypher to find all callers.",
        "allowed_context_tools": ["raw_mcp_cypher"],
    }
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
            "/v1/controller/code-context/lookups",
            payload,
        )

    assert status == 400
    assert body["error"]["code"] == "raw_codegraph_not_allowed"


def code_investigation_payload(target: Path) -> dict[str, Any]:
    return {
        "workflow": "code_investigation.plan",
        "schema_version": 1,
        "target_root": str(target),
        "user_request": (
            "Investigate whether client_order_id index lookup has one path before planning a refactor."
        ),
        "behavior": "client_order_id index lookup",
        "entrypoint_hints": [
            {
                "path": "core/stealth_order_manager.py",
                "symbol": "StealthOrderManager",
                "reason": "Known owner of the placed-order index behavior.",
            }
        ],
        "queries": ["client_order_id index"],
        "paths": ["core/stealth_order_manager.py"],
        "max_results": 10,
        "max_files": 5,
    }


def test_code_investigation_plan_returns_read_only_artifacts(tmp_path: Path) -> None:
    target = make_execution_planning_repo(tmp_path)
    source_path = target / "core" / "stealth_order_manager.py"
    original_text = source_path.read_text(encoding="utf-8")
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
            "/v1/controller/code-investigation/plans",
            code_investigation_payload(target),
        )

    assert status == 200
    assert body["workflow"] == "code_investigation.plan"
    assert body["status"] == "completed"
    assert body["summary"]["beginning_point_status"] == "hinted"
    assert body["summary"]["source_file_count"] >= 1
    assert body["summary"]["test_file_count"] >= 1
    assert body["tool_policy"]["workflow"] == "code_investigation.plan"
    assert body["tool_policy"]["model_visible_tool_ids"] == []
    assert "investigation_plan" in body["artifacts"]
    plan = json.loads(Path(body["artifacts"]["investigation_plan"]).read_text(encoding="utf-8"))
    assert plan["likely_beginning_point"]["path"] == "core/stealth_order_manager.py"
    assert plan["implementation_packet_seed"]["target_workflow"] == "implementation.workflow"
    assert plan["implementation_packet_seed"]["status"] == "not_ready_without_user_approval"
    assert any(item["path"].startswith("tests/") for item in plan["test_references"])
    assert plan["verification_plan"]["status"] == "ready"
    assert ["python", "-m", "pytest", "tests/unit/test_order_id_and_followup_rules.py"] in [
        item["command"] for item in plan["verification_plan"]["verification_commands"]
    ]
    assert source_path.read_text(encoding="utf-8") == original_text


def test_harness_adapter_runs_code_investigation_with_latest_message_envelope(tmp_path: Path) -> None:
    target = make_execution_planning_repo(tmp_path)
    old_payload = {
        "agentic_controller_request": {
            "workflow": "code_investigation.plan",
            "target_root": str(tmp_path / "not-allowlisted"),
            "user_request": "old request",
            "queries": ["old"],
        }
    }
    latest_payload = {"agentic_controller_request": code_investigation_payload(target)}
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
                "messages": [
                    {"role": "user", "content": json.dumps(old_payload)},
                    {"role": "assistant", "content": "old run"},
                    {"role": "user", "content": json.dumps(latest_payload)},
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    assert compact["workflow"] == "code_investigation.plan"
    assert compact["status"] == "completed"
    assert "investigation_plan" in compact["artifacts"]
    assert "code_investigation.plan completed" in body["choices"][0]["message"]["content"]


def test_code_investigation_rejects_raw_codegraph_context(tmp_path: Path) -> None:
    target = make_execution_planning_repo(tmp_path)
    payload = {
        **code_investigation_payload(target),
        "user_request": "Use raw CodeGraphContext Cypher to find all behavior paths.",
        "allowed_context_tools": ["raw_mcp_cypher"],
    }
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
            "/v1/controller/code-investigation/plans",
            payload,
        )

    assert status == 400
    assert body["error"]["code"] == "raw_codegraph_not_allowed"


def refactor_single_path_payload(target: Path) -> dict[str, Any]:
    return {
        "workflow": "refactor.single_path",
        "schema_version": 1,
        "target_root": str(target),
        "user_request": (
            "Investigate whether client_order_id invariant handling has one path before planning packet design."
        ),
        "behavior": "client_order_id invariant handling",
        "entrypoint_hints": [
            {
                "path": "docs/agents/INVARIANTS.md",
                "symbol": None,
                "reason": "Existing invariant is the behavior boundary for this test fixture.",
            }
        ],
        "queries": ["client_order_id"],
        "paths": ["docs/agents/INVARIANTS.md"],
        "max_results": 10,
        "max_files": 5,
    }


@advanced_workflow
def test_refactor_single_path_investigation_only_returns_approval_gate(tmp_path: Path) -> None:
    target = make_execution_planning_repo(tmp_path)
    original_text = (target / "docs" / "agents" / "INVARIANTS.md").read_text(encoding="utf-8")
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
            "/v1/controller/refactor/single-path",
            refactor_single_path_payload(target),
        )

    assert status == 200
    assert body["workflow"] == "refactor.single_path"
    assert body["status"] == "completed"
    assert body["summary"]["mode"] == "investigation_only"
    assert body["summary"]["refactor_status"] == "approval_required"
    assert body["tool_policy"]["workflow"] == "refactor.single_path"
    assert body["tool_policy"]["model_visible_tool_ids"] == []
    assert "investigation_investigation_plan" in body["artifacts"]
    assert "refactor_plan" in body["artifacts"]
    plan = json.loads(Path(body["artifacts"]["refactor_plan"]).read_text(encoding="utf-8"))
    assert plan["approval_gate"]["required_before_apply"] is True
    assert plan["execution_planning"] is None
    assert (target / "docs" / "agents" / "INVARIANTS.md").read_text(encoding="utf-8") == original_text


@advanced_workflow
def test_refactor_single_path_dry_run_delegates_to_execution_planning_without_mutation(tmp_path: Path) -> None:
    target = make_execution_planning_repo(tmp_path)
    original_text = (target / "docs" / "agents" / "INVARIANTS.md").read_text(encoding="utf-8")
    payload = {
        **refactor_single_path_payload(target),
        "mode": "dry_run",
        "approval": {
            "status": "approved_for_packet_design",
            "scope": "packet_design_only",
            "apply_allowed": False,
            "approval_refs": ["test:approved packet design only"],
        },
        "packet_operations": [
            {
                "kind": "replace_text",
                "path": "docs/agents/INVARIANTS.md",
                "old": FROZEN_INVARIANT_OLD,
                "new": FROZEN_INVARIANT_NEW,
            }
        ],
        "budgets": {
            "max_context_requests": 5,
            "max_files": 10,
            "max_records": 50,
            "max_model_calls": 12,
            "max_output_tokens": 4600,
        },
    }
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeExecutionPlanningEndpoint(context_grep_query="client_order_id") as endpoint:
        payload["role_base_url"] = endpoint.base_url
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/refactor/single-path",
                payload,
            )

    assert status == 200
    assert body["workflow"] == "refactor.single_path"
    assert body["summary"]["mode"] == "dry_run"
    assert body["summary"]["refactor_status"] == "draft_packet_ready"
    assert body["summary"]["execution_planning_run_id"].startswith("execution-planning-")
    assert "execution_planning_packet_preview" in body["artifacts"]
    assert "execution_planning_implementation_workflow_report" in body["artifacts"]
    assert (target / "docs" / "agents" / "INVARIANTS.md").read_text(encoding="utf-8") == original_text


@advanced_workflow
def test_harness_adapter_runs_refactor_single_path_with_latest_message_envelope(tmp_path: Path) -> None:
    target = make_execution_planning_repo(tmp_path)
    old_payload = {
        "agentic_controller_request": {
            "workflow": "refactor.single_path",
            "target_root": str(tmp_path / "not-allowlisted"),
            "user_request": "old request",
        }
    }
    latest_payload = {"agentic_controller_request": refactor_single_path_payload(target)}
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
                "messages": [
                    {"role": "user", "content": json.dumps(old_payload)},
                    {"role": "assistant", "content": "old run"},
                    {"role": "user", "content": json.dumps(latest_payload)},
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    assert compact["workflow"] == "refactor.single_path"
    assert compact["status"] == "completed"
    assert compact["summary"]["refactor_status"] == "approval_required"
    assert "refactor.single_path completed" in body["choices"][0]["message"]["content"]


@advanced_workflow
def test_refactor_single_path_dry_run_requires_packet_design_approval(tmp_path: Path) -> None:
    target = make_execution_planning_repo(tmp_path)
    payload = {
        **refactor_single_path_payload(target),
        "mode": "dry_run",
        "packet_operations": [
            {
                "kind": "replace_text",
                "path": "docs/agents/INVARIANTS.md",
                "old": FROZEN_INVARIANT_OLD,
                "new": FROZEN_INVARIANT_NEW,
            }
        ],
    }
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
            "/v1/controller/refactor/single-path",
            payload,
        )

    assert status == 400
    assert body["error"]["code"] == "missing_packet_design_approval"


def workflow_feedback_payload(target: Path, target_run_id: str, target_workflow: str = "code_context.lookup") -> dict[str, Any]:
    return {
        "workflow": "workflow_feedback.record",
        "schema_version": 1,
        "target_workflow": target_workflow,
        "target_run_id": target_run_id,
        "target_root": str(target),
        "feedback": {
            "useful": ["Beginning point and artifact links were easy to inspect."],
            "wrong": [],
            "missing": ["Add a clearer next command for the founder/tester."],
            "too_slow": [],
            "too_noisy": [],
            "notes": "Regression feedback from the controller workflow path.",
        },
        "tester": {"id": "founder", "surface": "regression"},
        "request_payload": {"source": "test_controller_service"},
        "artifact_refs": {},
    }


def test_workflow_feedback_record_links_existing_run_record(tmp_path: Path) -> None:
    target = make_execution_planning_repo(tmp_path)
    original_text = (target / "core" / "stealth_order_manager.py").read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, lookup = request_json(
            host,
            port,
            "POST",
            "/v1/controller/code-context/lookups",
            code_context_lookup_payload(target),
        )
        assert status == 200
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-feedback/records",
            workflow_feedback_payload(target, lookup["run_id"]),
        )
        status, run_body = request_json(host, port, "GET", f"/v1/controller/runs/{body['run_id']}")

    assert status == 200
    assert body["workflow"] == "workflow_feedback.record"
    assert body["status"] == "completed"
    assert body["summary"]["target_workflow"] == "code_context.lookup"
    assert body["summary"]["target_run_id"] == lookup["run_id"]
    assert body["summary"]["linked_run_found"] is True
    assert body["summary"]["feedback_counts"]["useful"] == 1
    assert body["summary"]["feedback_counts"]["missing"] == 1
    assert body["summary"]["classifications"] == ["useful", "missing"]
    assert body["summary"]["has_notes"] is True
    assert body["summary"]["semantic_status"] == "completed_no_failures"
    assert body["summary"]["next_action"]["kind"] == "prompt_or_artifact_gap_review"
    assert body["tool_policy"]["workflow"] == "workflow_feedback.record"
    assert body["tool_policy"]["controller_tool_ids"] == []
    assert body["tool_policy"]["model_visible_tool_ids"] == []
    assert "feedback_record" in body["artifacts"]
    record = json.loads(Path(body["artifacts"]["feedback_record"]).read_text(encoding="utf-8"))
    assert record["target_run_id"] == lookup["run_id"]
    assert record["linked_run"]["found"] is True
    assert record["linked_run"]["workflow"] == "code_context.lookup"
    assert record["feedback_context"]["target_run_found"] is True
    assert record["feedback_context"]["target_workflow"] == "code_context.lookup"
    assert record["feedback_context"]["prompt_case_status"] == "unknown"
    assert record["next_action"]["mutation_policy"] == "controller_artifacts_only"
    assert record["governed_decision"]["kind"] == "baseline_prompt_candidate"
    assert record["governed_decision"]["target_run_id"] == lookup["run_id"]
    assert record["governed_decision"]["feedback_run_id"] == body["run_id"]
    assert record["governed_decision"]["mutation_policy"] == "controller_artifacts_only"
    assert run_body["kind"] == "controller_run_record"
    assert run_body["workflow"] == "workflow_feedback.record"
    assert (target / "core" / "stealth_order_manager.py").read_text(encoding="utf-8") == original_text


def test_harness_adapter_runs_workflow_feedback_with_latest_message_envelope(tmp_path: Path) -> None:
    target = make_execution_planning_repo(tmp_path)
    old_payload = {
        "agentic_controller_request": {
            "workflow": "workflow_feedback.record",
            "target_workflow": "code_context.lookup",
            "target_run_id": "old-run",
            "target_root": str(tmp_path / "not-allowlisted"),
            "feedback": {"notes": "old feedback"},
        }
    }
    latest_payload = {
        "agentic_controller_request": workflow_feedback_payload(
            target,
            "manual-feedback-target-20260604T000000000000Z",
            target_workflow="refactor.single_path",
        )
    }
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
                "messages": [
                    {"role": "user", "content": json.dumps(old_payload)},
                    {"role": "assistant", "content": "old run"},
                    {"role": "user", "content": json.dumps(latest_payload)},
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    assert compact["workflow"] == "workflow_feedback.record"
    assert compact["status"] == "completed"
    assert compact["summary"]["target_workflow"] == "refactor.single_path"
    assert compact["summary"]["linked_run_found"] is False
    assert "feedback_record" in compact["artifacts"]
    assert "workflow_feedback.record completed" in body["choices"][0]["message"]["content"]


def test_workflow_feedback_rejects_missing_target_run_id(tmp_path: Path) -> None:
    target = make_execution_planning_repo(tmp_path)
    payload = workflow_feedback_payload(target, "feedback-target-20260604T000000000000Z")
    payload.pop("target_run_id")
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
            "/v1/controller/workflow-feedback/records",
            payload,
        )

    assert status == 400
    assert body["error"]["code"] == "missing_target_run_id"


def test_workflow_feedback_rejects_empty_feedback(tmp_path: Path) -> None:
    target = make_execution_planning_repo(tmp_path)
    payload = workflow_feedback_payload(target, "feedback-target-20260604T000000000000Z")
    payload["feedback"] = {
        "useful": [],
        "wrong": [],
        "missing": [],
        "too_slow": [],
        "too_noisy": [],
        "notes": "",
    }
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
            "/v1/controller/workflow-feedback/records",
            payload,
        )

    assert status == 400
    assert body["error"]["code"] == "empty_feedback"


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


def test_skill_batch_proposal_endpoint_returns_ready_artifacts_without_registry_mutation(tmp_path: Path) -> None:
    registry_paths = [REPO_ROOT / "runtime" / "skills.json", REPO_ROOT / "runtime" / "skill_evals.json"]
    before_hashes = {path: sha256_file(path) for path in registry_paths}
    output_root = tmp_path / "controller-output"
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=output_root,
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-batch/proposals",
            {
                "workflow": "skill_batch.propose",
                "schema_version": 1,
                "user_request": "Propose a skill batch for feature flag lookup. Proposal only. Do not register.",
            },
        )

    assert status == 200
    assert body["workflow"] == "skill_batch.propose"
    assert body["status"] == "completed"
    assert body["summary"]["proposal_status"] == "ready"
    assert body["summary"]["batch_validation_status"] == "passed"
    assert body["summary"]["do_not_admit_count"] == 0
    assert body["summary"]["runtime_registry_changed"] is False
    assert "skill_batch_proposal" in body["artifacts"]
    assert "draft_batch_manifest" in body["artifacts"]
    assert "batch_validation_report" in body["artifacts"]
    assert "scale_report" in body["artifacts"]

    proposal = json.loads(Path(body["artifacts"]["skill_batch_proposal"]).read_text(encoding="utf-8"))
    assert proposal["status"] == "ready"
    manifest = proposal["draft_batch_manifest"]
    assert manifest["skills"][0]["id"] == "feature-flag-locator"
    draft_skill_path = Path(manifest["skills"][0]["path"]).resolve()
    assert draft_skill_path.exists()
    assert str(draft_skill_path).startswith(str(output_root.resolve()))
    assert ".qwen" not in draft_skill_path.parts
    assert manifest["eval_cases"][0]["expected_artifacts"] == ["configuration_lookup"]
    assert {path: sha256_file(path) for path in registry_paths} == before_hashes


def test_skill_batch_proposal_endpoint_blocks_overlapping_semantic_intent(tmp_path: Path) -> None:
    registry_paths = [REPO_ROOT / "runtime" / "skills.json", REPO_ROOT / "runtime" / "skill_evals.json"]
    before_hashes = {path: sha256_file(path) for path in registry_paths}
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
            "/v1/controller/skill-batch/proposals",
            {
                "workflow": "skill_batch.propose",
                "schema_version": 1,
                "user_request": "Propose a duplicate code explanation skill batch. Proposal only. Do not register.",
            },
        )

    assert status == 200
    assert body["summary"]["proposal_status"] == "do_not_admit"
    assert body["summary"]["batch_validation_status"] == "failed"
    assert body["summary"]["do_not_admit_count"] == 1
    proposal = json.loads(Path(body["artifacts"]["skill_batch_proposal"]).read_text(encoding="utf-8"))
    assert proposal["status"] == "do_not_admit"
    do_not_admit_text = json.dumps(proposal["do_not_admit"], sort_keys=True)
    assert "overlapping semantic intent" in do_not_admit_text
    assert "do_not_register_until_errors_are_resolved" in do_not_admit_text
    assert {path: sha256_file(path) for path in registry_paths} == before_hashes


def test_workflow_router_mode_inference_uses_skill_batch_proposal_classifier() -> None:
    assert (
        infer_workflow_router_mode(
            "In /mnt/c/repo, propose a duplicate code explanation skill batch. "
            "Proposal only. Do not register or append runtime skills."
        )
        == "execute_read_only"
    )


def test_workflow_router_mode_inference_executes_common_read_only_coding_requests() -> None:
    prompts = [
        "In /mnt/c/repo, explain resolve_order_status in service/orders.py. Don't change files.",
        "In /mnt/c/repo, where is DEFAULT_PROFILE defined or used as configuration?",
        "In /mnt/c/repo, compare the placed_order_id lookup path with the client_order_id index path.",
        "In /mnt/c/repo, map the request flow for request_stealth_orders from dashboard message to snapshot.",
        "In /mnt/c/repo, identify the change surface for adjusting placed_order_id. Stop before implementation.",
    ]

    for prompt in prompts:
        assert infer_workflow_router_mode(prompt) == "execute_read_only"


def test_workflow_router_mode_inference_keeps_l1_implementation_requests_plan_only() -> None:
    prompts = [
        "In /mnt/c/repo, add a small unit test for resolve_order_status.",
        "In /mnt/c/repo, fix the failing test test_resolve_order_status.",
        "In /mnt/c/repo, change README.md line 3 to say Ready.",
    ]

    for prompt in prompts:
        assert infer_workflow_router_mode(prompt) == "plan_only"


def test_skill_batch_registration_endpoint_installs_approved_ready_proposal(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    output_root = tmp_path / "controller-output"
    registry_paths = [config_root / "runtime" / "skills.json", config_root / "runtime" / "skill_evals.json"]
    before_hashes = {path: sha256_file(path) for path in registry_paths}
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=output_root,
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        proposal_status, proposal_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-batch/proposals",
            {
                "workflow": "skill_batch.propose",
                "schema_version": 1,
                "user_request": "Propose a skill batch for feature flag lookup. Proposal only. Do not register.",
            },
        )
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-batch/registrations",
            {
                "workflow": "skill_batch.register",
                "schema_version": 1,
                "proposal_path": proposal_body["artifacts"]["skill_batch_proposal"],
                "approval": skill_registration_approval(),
            },
        )

    assert proposal_status == 200
    assert proposal_body["summary"]["proposal_status"] == "ready"
    assert status == 200
    assert body["workflow"] == "skill_batch.register"
    assert body["summary"]["registration_status"] == "installed"
    assert body["summary"]["installed_skill_ids"] == ["feature-flag-locator"]
    assert body["summary"]["installed_eval_case_ids"] == ["feature_flag_lookup"]
    assert body["summary"]["runtime_registry_changed"] is True
    assert body["summary"]["target_repository_changed"] is False
    assert "skill_batch_registration" in body["artifacts"]
    assert "rollback_instructions" in body["artifacts"]
    assert {path: sha256_file(path) for path in registry_paths} != before_hashes

    installed_skill_body = config_root / ".qwen" / "skills" / "feature-flag-locator" / "SKILL.md"
    assert installed_skill_body.exists()
    registry_manifest = json.loads((config_root / "runtime" / "skills.json").read_text(encoding="utf-8"))
    installed = [item for item in registry_manifest["skills"] if item["id"] == "feature-flag-locator"]
    assert installed[0]["path"] == ".qwen/skills/feature-flag-locator/SKILL.md"
    eval_manifest = json.loads((config_root / "runtime" / "skill_evals.json").read_text(encoding="utf-8"))
    assert any(item["id"] == "feature_flag_lookup" for item in eval_manifest["cases"])

    registry = load_skill_registry(config_root)
    selected = select_skills_for_workflow(
        registry,
        "code_investigation.plan",
        query_text="Find the feature flag definitions. Read only.",
        limit=10,
    )
    assert "feature-flag-locator" in selected

    registration = json.loads(Path(body["artifacts"]["skill_batch_registration"]).read_text(encoding="utf-8"))
    assert registration["hash_proof"]["changed"] == [
        ".qwen/skills/feature-flag-locator/SKILL.md",
        "runtime/skill_evals.json",
        "runtime/skills.json",
    ]


def test_skill_batch_registration_rejects_do_not_admit_proposal_without_mutation(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    registry_paths = [config_root / "runtime" / "skills.json", config_root / "runtime" / "skill_evals.json"]
    before_hashes = {path: sha256_file(path) for path in registry_paths}
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        proposal_status, proposal_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-batch/proposals",
            {
                "workflow": "skill_batch.propose",
                "schema_version": 1,
                "user_request": "Propose a duplicate code explanation skill batch. Proposal only. Do not register.",
            },
        )
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-batch/registrations",
            {
                "workflow": "skill_batch.register",
                "schema_version": 1,
                "proposal_path": proposal_body["artifacts"]["skill_batch_proposal"],
                "approval": skill_registration_approval(),
            },
        )

    assert proposal_status == 200
    assert proposal_body["summary"]["proposal_status"] == "do_not_admit"
    assert status == 422
    assert body["error"]["code"] == "proposal_not_ready"
    assert {path: sha256_file(path) for path in registry_paths} == before_hashes
    assert not (config_root / ".qwen" / "skills" / "duplicate-code-explanation").exists()


def test_skill_batch_registration_rejects_missing_approval_without_mutation(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    registry_paths = [config_root / "runtime" / "skills.json", config_root / "runtime" / "skill_evals.json"]
    before_hashes = {path: sha256_file(path) for path in registry_paths}
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        proposal_status, proposal_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-batch/proposals",
            {
                "workflow": "skill_batch.propose",
                "schema_version": 1,
                "user_request": "Propose a skill batch for feature flag lookup. Proposal only. Do not register.",
            },
        )
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-batch/registrations",
            {
                "workflow": "skill_batch.register",
                "schema_version": 1,
                "proposal_path": proposal_body["artifacts"]["skill_batch_proposal"],
                "approval": {"status": "not_approved"},
            },
        )

    assert proposal_status == 200
    assert status == 403
    assert body["error"]["code"] == "missing_registration_approval"
    assert {path: sha256_file(path) for path in registry_paths} == before_hashes
    assert not (config_root / ".qwen" / "skills" / "feature-flag-locator").exists()


def test_phase40_batch_b_proposal_register_promote_and_audit_lifecycle(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    remove_phase40_batch_b_entries(config_root)
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        proposal_status, proposal_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-batch/proposals",
            {
                "workflow": "skill_batch.propose",
                "schema_version": 1,
                "user_request": (
                    "Propose the Phase 40 Batch B controlled L1/L2 skill expansion. "
                    "Proposal only. Do not register."
                ),
            },
        )
        registration_status, registration_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-batch/registrations",
            {
                "workflow": "skill_batch.register",
                "schema_version": 1,
                "proposal_path": proposal_body["artifacts"]["skill_batch_proposal"],
                "approval": skill_registration_approval("phase40-batch-b-registration"),
            },
        )
        promotion_status, promotion_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-evals/promotions",
            {
                "workflow": "skill_eval.promote",
                "schema_version": 1,
                "registration_run_id": registration_body["run_id"],
                "approval": skill_eval_promotion_approval("phase40-batch-b-promotion"),
            },
        )
        audit_status, audit_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-lifecycle/audits",
            {
                "workflow": "skill_lifecycle.audit",
                "schema_version": 1,
            },
        )

    assert proposal_status == 200
    assert proposal_body["summary"]["proposal_status"] == "ready"
    assert proposal_body["summary"]["skill_count"] == 4
    manifest = json.loads(Path(proposal_body["artifacts"]["draft_batch_manifest"]).read_text(encoding="utf-8"))
    assert [item["id"] for item in manifest["skills"]] == PHASE40_BATCH_B_SKILL_IDS
    assert [item["id"] for item in manifest["eval_cases"]] == PHASE40_BATCH_B_EVAL_CASE_IDS

    assert registration_status == 200
    assert registration_body["summary"]["registration_status"] == "installed"
    assert registration_body["summary"]["installed_skill_ids"] == PHASE40_BATCH_B_SKILL_IDS
    assert registration_body["summary"]["installed_eval_case_ids"] == PHASE40_BATCH_B_EVAL_CASE_IDS

    assert promotion_status == 200
    assert promotion_body["summary"]["promotion_status"] == "promoted"
    assert promotion_body["summary"]["promoted_skill_ids"] == sorted(PHASE40_BATCH_B_SKILL_IDS)
    assert promotion_body["summary"]["eval_case_ids"] == sorted(PHASE40_BATCH_B_EVAL_CASE_IDS)
    assert promotion_body["summary"]["changed_runtime_files"] == ["runtime/skills.json"]

    assert audit_status == 200
    audit = json.loads(Path(audit_body["artifacts"]["skill_lifecycle_audit"]).read_text(encoding="utf-8"))
    for skill_id in PHASE40_BATCH_B_SKILL_IDS:
        assert skill_action(audit, skill_id)["action"] == "no_action"

    registry = load_skill_registry(config_root)
    selection_prompts = {
        "background-job-locator": "Find background jobs and sweepers. Read only.",
        "pytest-fixture-locator": "Find pytest fixture setup for stealth order manager. Read only.",
        "api-reference-locator": "Find API reference documentation for create order payloads. Read only.",
        "agent-invariant-locator": "Find agent invariant documentation for client_order_id tracking. Read only.",
    }
    for skill_id, prompt in selection_prompts.items():
        selected = select_skills_for_workflow(
            registry,
            "code_investigation.plan",
            query_text=prompt,
            limit=10,
        )
        assert skill_id in selected


def test_phase50_batch_c_proposal_register_promote_and_audit_lifecycle(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    remove_phase50_batch_c_entries(config_root)
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        proposal_status, proposal_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-batch/proposals",
            {
                "workflow": "skill_batch.propose",
                "schema_version": 1,
                "user_request": (
                    "Propose the Phase 50 Batch C controlled L1/L2 skill expansion. "
                    "Proposal only. Do not register."
                ),
            },
        )
        registration_status, registration_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-batch/registrations",
            {
                "workflow": "skill_batch.register",
                "schema_version": 1,
                "proposal_path": proposal_body["artifacts"]["skill_batch_proposal"],
                "approval": skill_registration_approval("phase50-batch-c-registration"),
            },
        )
        promotion_status, promotion_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-evals/promotions",
            {
                "workflow": "skill_eval.promote",
                "schema_version": 1,
                "registration_run_id": registration_body["run_id"],
                "approval": skill_eval_promotion_approval("phase50-batch-c-promotion"),
            },
        )
        audit_status, audit_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-lifecycle/audits",
            {
                "workflow": "skill_lifecycle.audit",
                "schema_version": 1,
            },
        )

    assert proposal_status == 200
    assert proposal_body["summary"]["proposal_status"] == "ready"
    assert proposal_body["summary"]["skill_count"] == 4
    manifest = json.loads(Path(proposal_body["artifacts"]["draft_batch_manifest"]).read_text(encoding="utf-8"))
    assert [item["id"] for item in manifest["skills"]] == PHASE50_BATCH_C_SKILL_IDS
    assert [item["id"] for item in manifest["eval_cases"]] == PHASE50_BATCH_C_EVAL_CASE_IDS

    assert registration_status == 200
    assert registration_body["summary"]["registration_status"] == "installed"
    assert registration_body["summary"]["installed_skill_ids"] == PHASE50_BATCH_C_SKILL_IDS
    assert registration_body["summary"]["installed_eval_case_ids"] == PHASE50_BATCH_C_EVAL_CASE_IDS

    assert promotion_status == 200
    assert promotion_body["summary"]["promotion_status"] == "promoted"
    assert promotion_body["summary"]["promoted_skill_ids"] == sorted(PHASE50_BATCH_C_SKILL_IDS)
    assert promotion_body["summary"]["eval_case_ids"] == sorted(PHASE50_BATCH_C_EVAL_CASE_IDS)
    assert promotion_body["summary"]["changed_runtime_files"] == ["runtime/skills.json"]

    assert audit_status == 200
    audit = json.loads(Path(audit_body["artifacts"]["skill_lifecycle_audit"]).read_text(encoding="utf-8"))
    for skill_id in PHASE50_BATCH_C_SKILL_IDS:
        assert skill_action(audit, skill_id)["action"] == "no_action"

    registry = load_skill_registry(config_root)
    selection_prompts = {
        "auth-check-locator": (
            "Find auth checks and permission guards for stealth order actions. "
            "Read only. Return guard files, evidence, and related tests."
        ),
        "state-mutation-locator": (
            "Find state mutation sites for placed_order_id indexing. "
            "Read only. Return mutation sites, evidence files, and related tests."
        ),
        "external-integration-locator": (
            "Find external integration points for Coinbase order placement. "
            "Read only. Return client files, request boundaries, and evidence gaps."
        ),
        "error-handling-path-locator": (
            "Find the error handling path for order placement failures. "
            "Read only. Return exception handlers, fallback logic, and related tests."
        ),
    }
    for skill_id, prompt in selection_prompts.items():
        selected = select_skills_for_workflow(
            registry,
            "code_investigation.plan",
            query_text=prompt,
            limit=5,
        )
        assert skill_id in selected


def test_phase61_batch_d_proposal_registers_draft_skills_without_promotion(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    remove_phase61_batch_d_entries(config_root)
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        proposal_status, proposal_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-batch/proposals",
            {
                "workflow": "skill_batch.propose",
                "schema_version": 1,
                "user_request": (
                    "Propose the Phase 61 Batch D field-evidence skill expansion. "
                    "Proposal only. Do not register."
                ),
            },
        )
        registration_status, registration_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-batch/registrations",
            {
                "workflow": "skill_batch.register",
                "schema_version": 1,
                "proposal_path": proposal_body["artifacts"]["skill_batch_proposal"],
                "approval": skill_registration_approval("phase61-batch-d-registration"),
            },
        )

    assert proposal_status == 200
    assert proposal_body["summary"]["proposal_status"] == "ready"
    assert proposal_body["summary"]["skill_count"] == 4
    manifest = json.loads(Path(proposal_body["artifacts"]["draft_batch_manifest"]).read_text(encoding="utf-8"))
    assert [item["id"] for item in manifest["skills"]] == PHASE61_BATCH_D_SKILL_IDS
    assert [item["id"] for item in manifest["eval_cases"]] == PHASE61_BATCH_D_EVAL_CASE_IDS
    assert "docs/SKILL_SCALING_BATCH_D_PROPOSAL.md" in manifest["doc_refs"]

    assert registration_status == 200
    assert registration_body["summary"]["registration_status"] == "installed"
    assert registration_body["summary"]["installed_skill_ids"] == PHASE61_BATCH_D_SKILL_IDS
    assert registration_body["summary"]["installed_eval_case_ids"] == PHASE61_BATCH_D_EVAL_CASE_IDS

    registry = load_skill_registry(config_root)
    eval_case_ids = {
        item["id"]
        for item in json.loads((config_root / "runtime" / "skill_evals.json").read_text(encoding="utf-8"))["cases"]
    }
    assert set(PHASE61_BATCH_D_EVAL_CASE_IDS) <= eval_case_ids
    for skill_id in PHASE61_BATCH_D_SKILL_IDS:
        assert registry[skill_id]["eval_status"] == "draft"
        assert registry[skill_id]["evals"]["localhost_8000"] == "not_run"
        assert (config_root / ".qwen" / "skills" / skill_id / "SKILL.md").is_file()

    selection_prompts = {
        "handler-branch-tracer": (
            "Follow the handler branch trace through the downstream snapshot function. "
            "Read only. Return flow steps and evidence refs."
        ),
        "table-schema-isolator": (
            "Find table schema only and schema field names for stealth orders. "
            "Read only. Exclude runtime fields."
        ),
        "runtime-entrypoint-disambiguator": (
            "Find the runtime entrypoint for the trading engine, not dashboard server. "
            "Read only. Return command and exclusions."
        ),
        "change-boundary-summarizer": (
            "Identify files to touch and files not to touch for a change boundary. "
            "Read only and stop before implementation."
        ),
    }
    for skill_id, prompt in selection_prompts.items():
        selected = select_skills_for_workflow(
            registry,
            "code_investigation.plan",
            query_text=prompt,
            limit=5,
        )
        assert skill_id in selected


def test_phase50_batch_c_prompt_families_route_and_select_skills_without_repo_reads(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
    cases = [
        (
            "auth-check-locator",
            "l1_auth_check_lookup_terms",
            "In this repo, find auth checks and permission guards for stealth order actions. "
            "Read only. Return guard files, evidence, and related tests.",
        ),
        (
            "state-mutation-locator",
            "l1_state_mutation_lookup_terms",
            "In this repo, find state mutation sites for placed_order_id indexing. "
            "Read only. Return mutation sites, evidence files, and related tests.",
        ),
        (
            "external-integration-locator",
            "l1_external_integration_lookup_terms",
            "In this repo, find external integration points for Coinbase order placement. "
            "Read only. Return client files, request boundaries, and evidence gaps.",
        ),
        (
            "error-handling-path-locator",
            "l1_error_handling_path_lookup_terms",
            "In this repo, find the error handling path for order placement failures. "
            "Read only. Return exception handlers, fallback logic, and related tests.",
        ),
    ]
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        results = [
            request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/plans",
                {
                    "workflow": "workflow_router.plan",
                    "target_root": str(target),
                    "user_request": prompt,
                    "mode": "plan_only",
                },
            )
            for _skill_id, _rule, prompt in cases
        ]

    for (skill_id, rule, _prompt), (status, body) in zip(cases, results, strict=True):
        assert status == 200
        assert body["summary"]["route_status"] == "ready"
        assert body["summary"]["selected_workflow"] == "code_investigation.plan"
        assert body["summary"]["target_repo_read"] is False
        decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
        assert decision["selected_workflow"] == "code_investigation.plan"
        assert skill_id in decision["selected_skills"]
        assert any(item.get("rule") == rule for item in decision["evidence"])
    assert sentinel.read_text(encoding="utf-8") == before


def test_skill_deprecation_endpoint_deprecates_one_skill_and_selector_excludes_it(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    output_root = tmp_path / "controller-output"
    skills_path = config_root / "runtime" / "skills.json"
    evals_path = config_root / "runtime" / "skill_evals.json"
    deprecated_body = config_root / ".qwen" / "skills" / "code-explanation-summarizer" / "SKILL.md"
    replacement_body = config_root / ".qwen" / "skills" / "behavior-existence-checker" / "SKILL.md"
    before_hashes = {
        "skills": sha256_file(skills_path),
        "evals": sha256_file(evals_path),
        "deprecated_body": sha256_file(deprecated_body),
        "replacement_body": sha256_file(replacement_body),
    }
    registry_before = load_skill_registry(config_root)
    selected_before = select_skills_for_workflow(
        registry_before,
        "code_investigation.plan",
        query_text="Explain what this function does, including inputs and outputs.",
        limit=10,
    )
    assert "code-explanation-summarizer" in selected_before

    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=output_root,
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-deprecations",
            {
                "workflow": "skill.deprecate",
                "schema_version": 1,
                "skill_id": "code-explanation-summarizer",
                "replacement_skill_id": "behavior-existence-checker",
                "reason": "Phase 42 controlled-copy regression proves approval-gated deprecation behavior.",
                "effective_date": "2026-06-05",
                "approval": skill_deprecation_approval(),
            },
        )
        audit_status, audit_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-lifecycle/audits",
            {
                "workflow": "skill_lifecycle.audit",
                "schema_version": 1,
                "skill_ids": ["code-explanation-summarizer"],
            },
        )

    assert status == 200
    assert body["workflow"] == "skill.deprecate"
    assert body["summary"]["deprecation_status"] == "deprecated"
    assert body["summary"]["skill_id"] == "code-explanation-summarizer"
    assert body["summary"]["replacement_skill_id"] == "behavior-existence-checker"
    assert body["summary"]["changed_runtime_files"] == ["runtime/skills.json"]
    assert body["summary"]["mutated_skill_count"] == 1
    assert body["summary"]["skill_body_deleted"] is False
    assert body["summary"]["selector_excludes_deprecated_skill"] is True
    assert body["summary"]["target_repository_changed"] is False
    assert "skill_deprecation" in body["artifacts"]
    assert "rollback_instructions" in body["artifacts"]

    assert sha256_file(skills_path) != before_hashes["skills"]
    assert sha256_file(evals_path) == before_hashes["evals"]
    assert sha256_file(deprecated_body) == before_hashes["deprecated_body"]
    assert sha256_file(replacement_body) == before_hashes["replacement_body"]

    registry_after = load_skill_registry(config_root)
    selected_after = select_skills_for_workflow(
        registry_after,
        "code_investigation.plan",
        query_text="Explain what this function does, including inputs and outputs.",
        limit=10,
    )
    assert "code-explanation-summarizer" not in selected_after
    deprecated_skill = registry_after["code-explanation-summarizer"]
    assert deprecated_skill["eval_status"] == "deprecated"
    assert deprecated_skill["deprecation"]["replaced_by"] == "behavior-existence-checker"

    deprecation_artifact = json.loads(Path(body["artifacts"]["skill_deprecation"]).read_text(encoding="utf-8"))
    assert deprecation_artifact["hash_proof"]["changed"] == ["runtime/skills.json"]
    assert deprecation_artifact["selector_exclusion_proof"]["deprecated_skill_selected"] is False

    assert audit_status == 200
    audit = json.loads(Path(audit_body["artifacts"]["skill_lifecycle_audit"]).read_text(encoding="utf-8"))
    lifecycle_item = skill_action(audit, "code-explanation-summarizer")
    assert lifecycle_item["eval_status"] == "deprecated"
    assert lifecycle_item["action"] == "no_action"


def test_skill_deprecation_rejects_missing_approval_without_mutation(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    skills_path = config_root / "runtime" / "skills.json"
    evals_path = config_root / "runtime" / "skill_evals.json"
    before_hashes = {path: sha256_file(path) for path in (skills_path, evals_path)}
    config = ControllerServiceConfig(
        config_root=config_root,
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
            "/v1/controller/skill-deprecations",
            {
                "workflow": "skill.deprecate",
                "schema_version": 1,
                "skill_id": "code-explanation-summarizer",
                "replacement_skill_id": "behavior-existence-checker",
                "reason": "This request intentionally lacks the required deprecation approval.",
                "effective_date": "2026-06-05",
                "approval": {"status": "not_approved"},
            },
        )

    assert status == 403
    assert body["error"]["code"] == "missing_deprecation_approval"
    assert {path: sha256_file(path) for path in (skills_path, evals_path)} == before_hashes


def test_skill_deprecation_rejects_broken_replacement_without_mutation(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    skills_path = config_root / "runtime" / "skills.json"
    evals_path = config_root / "runtime" / "skill_evals.json"
    before_hashes = {path: sha256_file(path) for path in (skills_path, evals_path)}
    config = ControllerServiceConfig(
        config_root=config_root,
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
            "/v1/controller/skill-deprecations",
            {
                "workflow": "skill.deprecate",
                "schema_version": 1,
                "skill_id": "code-explanation-summarizer",
                "replacement_skill_id": "missing-replacement-skill",
                "reason": "This request intentionally references a missing replacement skill.",
                "effective_date": "2026-06-05",
                "approval": skill_deprecation_approval(),
            },
        )

    assert status == 422
    assert body["error"]["code"] == "replacement_skill_not_registered"
    assert {path: sha256_file(path) for path in (skills_path, evals_path)} == before_hashes


def test_skill_deprecation_rejects_route_incompatible_replacement_without_mutation(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    skills_path = config_root / "runtime" / "skills.json"
    evals_path = config_root / "runtime" / "skill_evals.json"
    before_hashes = {path: sha256_file(path) for path in (skills_path, evals_path)}
    config = ControllerServiceConfig(
        config_root=config_root,
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
            "/v1/controller/skill-deprecations",
            {
                "workflow": "skill.deprecate",
                "schema_version": 1,
                "skill_id": "code-explanation-summarizer",
                "replacement_skill_id": "callers-usages-summarizer",
                "reason": "This request intentionally references a route-incompatible replacement skill.",
                "effective_date": "2026-06-05",
                "approval": skill_deprecation_approval(),
            },
        )

    assert status == 422
    assert body["error"]["code"] == "replacement_route_incompatible"
    assert {path: sha256_file(path) for path in (skills_path, evals_path)} == before_hashes


def test_skill_deprecation_harness_returns_chat_visible_summary(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    config = ControllerServiceConfig(
        config_root=config_root,
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
                "messages": [
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "agentic_controller_request": {
                                    "workflow": "skill.deprecate",
                                    "schema_version": 1,
                                    "skill_id": "code-explanation-summarizer",
                                    "replacement_skill_id": "behavior-existence-checker",
                                    "reason": "Harness regression proves deprecation returns chat-visible proof.",
                                    "effective_date": "2026-06-05",
                                    "approval": skill_deprecation_approval("harness-deprecation"),
                                }
                            }
                        ),
                    }
                ],
            },
        )

    assert status == 200
    content = body["choices"][0]["message"]["content"]
    assert "skill.deprecate" in content
    assert "deprecated" in content
    compact = body["agentic_controller_response"]
    assert compact["summary"]["deprecation_status"] == "deprecated"
    assert compact["summary"]["changed_runtime_files"] == ["runtime/skills.json"]


def test_skill_update_metadata_only_changes_one_skill_entry_and_bumps_patch_version(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    skills_path = config_root / "runtime" / "skills.json"
    evals_path = config_root / "runtime" / "skill_evals.json"
    body_path = config_root / "README.skill-registry.md"
    skill_body = config_root / ".qwen" / "skills" / "code-explanation-summarizer" / "SKILL.md"
    before_hashes = {
        "skills": sha256_file(skills_path),
        "evals": sha256_file(evals_path),
        "skill_body": sha256_file(skill_body),
        "docs": sha256_file(body_path),
    }
    before_skill = skill_metadata(config_root, "code-explanation-summarizer")
    config = ControllerServiceConfig(
        config_root=config_root,
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
            "/v1/controller/skill-updates",
            {
                "workflow": "skill.update",
                "schema_version": 1,
                "skill_id": "code-explanation-summarizer",
                "change_type": "metadata_only",
                "version_bump": "patch",
                "metadata_updates": {
                    "description": "Updated controlled-copy description for Phase 43 metadata-only regression proof."
                },
                "approval": skill_update_approval("phase43-metadata-only"),
            },
        )

    assert status == 200
    assert body["workflow"] == "skill.update"
    assert body["summary"]["update_status"] == "updated"
    assert body["summary"]["change_type"] == "metadata_only"
    assert body["summary"]["changed_files"] == ["runtime/skills.json"]
    assert body["summary"]["changed_skill_entry_count"] == 1
    assert body["summary"]["changed_eval_case_count"] == 0
    assert body["summary"]["current_version"] == before_skill["version"]
    assert body["summary"]["new_version"].endswith(".1")
    assert sha256_file(skills_path) != before_hashes["skills"]
    assert sha256_file(evals_path) == before_hashes["evals"]
    assert sha256_file(skill_body) == before_hashes["skill_body"]
    assert sha256_file(body_path) == before_hashes["docs"]
    after_skill = skill_metadata(config_root, "code-explanation-summarizer")
    assert after_skill["description"].startswith("Updated controlled-copy description")
    update_artifact = json.loads(Path(body["artifacts"]["skill_update"]).read_text(encoding="utf-8"))
    assert update_artifact["hash_proof"]["changed"] == ["runtime/skills.json"]
    assert "rollback_instructions" in body["artifacts"]


def test_skill_update_body_only_changes_one_skill_body_and_preserves_frontmatter(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    skill_id = "code-explanation-summarizer"
    skill_body = config_root / ".qwen" / "skills" / skill_id / "SKILL.md"
    skills_path = config_root / "runtime" / "skills.json"
    evals_path = config_root / "runtime" / "skill_evals.json"
    original_body = skill_body.read_text(encoding="utf-8")
    updated_body = original_body.rstrip() + "\n\nPhase 43 controlled-copy body update proof.\n"
    before_hashes = {
        "skills": sha256_file(skills_path),
        "evals": sha256_file(evals_path),
        "skill_body": sha256_file(skill_body),
    }
    config = ControllerServiceConfig(
        config_root=config_root,
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
            "/v1/controller/skill-updates",
            {
                "workflow": "skill.update",
                "schema_version": 1,
                "skill_id": skill_id,
                "change_type": "skill_body_only",
                "version_bump": "patch",
                "skill_body_text": updated_body,
                "approval": skill_update_approval("phase43-body-only", skill_body_update=True),
            },
        )

    assert status == 200
    expected_body_path = ".qwen/skills/code-explanation-summarizer/SKILL.md"
    assert body["summary"]["changed_files"] == [expected_body_path, "runtime/skills.json"]
    assert body["summary"]["changed_skill_entry_count"] == 1
    assert body["summary"]["changed_eval_case_count"] == 0
    assert sha256_file(skills_path) != before_hashes["skills"]
    assert sha256_file(evals_path) == before_hashes["evals"]
    assert sha256_file(skill_body) != before_hashes["skill_body"]
    assert skill_body.read_text(encoding="utf-8").endswith("Phase 43 controlled-copy body update proof.\n")


def test_skill_update_eval_case_only_changes_intended_eval_case(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    skill_id = "code-explanation-summarizer"
    case_id = skill_metadata(config_root, skill_id)["capability_contract"]["eval_case_ids"][0]
    before_case = skill_eval_case(config_root, case_id)
    skills_path = config_root / "runtime" / "skills.json"
    evals_path = config_root / "runtime" / "skill_evals.json"
    skill_body = config_root / ".qwen" / "skills" / skill_id / "SKILL.md"
    before_hashes = {
        "skills": sha256_file(skills_path),
        "evals": sha256_file(evals_path),
        "skill_body": sha256_file(skill_body),
    }
    config = ControllerServiceConfig(
        config_root=config_root,
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
            "/v1/controller/skill-updates",
            {
                "workflow": "skill.update",
                "schema_version": 1,
                "skill_id": skill_id,
                "change_type": "eval_case_only",
                "version_bump": "patch",
                "eval_case_updates": [
                    {
                        "id": case_id,
                        "updates": {
                            "natural_prompt": before_case["natural_prompt"]
                            + " Phase 43 controlled-copy eval update."
                        },
                    }
                ],
                "approval": skill_update_approval("phase43-eval-only", eval_case_update=True),
            },
        )

    assert status == 200
    assert body["summary"]["changed_files"] == ["runtime/skill_evals.json", "runtime/skills.json"]
    assert body["summary"]["changed_skill_entry_count"] == 1
    assert body["summary"]["changed_eval_case_count"] == 1
    assert body["summary"]["changed_eval_case_ids"] == [case_id]
    assert sha256_file(skills_path) != before_hashes["skills"]
    assert sha256_file(evals_path) != before_hashes["evals"]
    assert sha256_file(skill_body) == before_hashes["skill_body"]
    after_case = skill_eval_case(config_root, case_id)
    assert after_case["natural_prompt"].endswith("Phase 43 controlled-copy eval update.")


def test_skill_update_rollback_artifacts_restore_all_changed_files(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    skill_id = "code-explanation-summarizer"
    case_id = skill_metadata(config_root, skill_id)["capability_contract"]["eval_case_ids"][0]
    before_case = skill_eval_case(config_root, case_id)
    skills_path = config_root / "runtime" / "skills.json"
    evals_path = config_root / "runtime" / "skill_evals.json"
    skill_body = config_root / ".qwen" / "skills" / skill_id / "SKILL.md"
    original_body = skill_body.read_text(encoding="utf-8")
    before_hashes = {
        "runtime/skills.json": sha256_file(skills_path),
        "runtime/skill_evals.json": sha256_file(evals_path),
        ".qwen/skills/code-explanation-summarizer/SKILL.md": sha256_file(skill_body),
    }
    request = SkillUpdateRequest(
        config_root=config_root,
        output_root=tmp_path / "controller-output",
        skill_id=skill_id,
        change_type="combined",
        version_bump="minor",
        metadata_updates={"description": "Combined update rollback regression proof."},
        skill_body_text=original_body.rstrip() + "\n\nPhase 43 rollback body proof.\n",
        eval_case_updates=[
            {
                "id": case_id,
                "updates": {
                    "natural_prompt": before_case["natural_prompt"]
                    + " Phase 43 rollback eval proof."
                },
            }
        ],
        approval=skill_update_approval(
            "phase43-rollback",
            skill_body_update=True,
            eval_case_update=True,
        ),
    )
    result = invoke_skill_update(request)

    assert result.status == WorkflowStatus.COMPLETED
    assert result.report is not None
    assert set(result.report["summary"]["changed_files"]) == set(before_hashes)
    rollback = json.loads(Path(result.artifact_paths["rollback_instructions"]).read_text(encoding="utf-8"))
    for relative_path, backup_path in rollback["restore_backups"].items():
        if relative_path in before_hashes:
            shutil.copy2(backup_path, config_root / relative_path)

    assert {
        "runtime/skills.json": sha256_file(skills_path),
        "runtime/skill_evals.json": sha256_file(evals_path),
        ".qwen/skills/code-explanation-summarizer/SKILL.md": sha256_file(skill_body),
    } == before_hashes


def test_skill_update_rejects_route_key_change_without_deprecation_plan(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    skills_path = config_root / "runtime" / "skills.json"
    evals_path = config_root / "runtime" / "skill_evals.json"
    before_hashes = {path: sha256_file(path) for path in (skills_path, evals_path)}
    config = ControllerServiceConfig(
        config_root=config_root,
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
            "/v1/controller/skill-updates",
            {
                "workflow": "skill.update",
                "schema_version": 1,
                "skill_id": "code-explanation-summarizer",
                "change_type": "metadata_only",
                "version_bump": "major",
                "metadata_updates": {
                    "capability_contract": {
                        "route_key": "code.phase43_changed_explanation_route",
                    }
                },
                "approval": skill_update_approval("phase43-route-key-rejection"),
            },
        )

    assert status == 422
    assert body["error"]["code"] == "route_key_change_requires_deprecation_plan"
    assert {path: sha256_file(path) for path in (skills_path, evals_path)} == before_hashes


def test_skill_update_harness_returns_chat_visible_summary(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    config = ControllerServiceConfig(
        config_root=config_root,
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
                "messages": [
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "agentic_controller_request": {
                                    "workflow": "skill.update",
                                    "schema_version": 1,
                                    "skill_id": "code-explanation-summarizer",
                                    "change_type": "metadata_only",
                                    "version_bump": "patch",
                                    "metadata_updates": {
                                        "description": "Harness regression proves skill update chat-visible summary output."
                                    },
                                    "approval": skill_update_approval("harness-skill-update"),
                                }
                            }
                        ),
                    }
                ],
            },
        )

    assert status == 200
    content = body["choices"][0]["message"]["content"]
    assert "skill.update" in content
    assert "updated" in content
    compact = body["agentic_controller_response"]
    assert compact["summary"]["update_status"] == "updated"
    assert compact["summary"]["changed_files"] == ["runtime/skills.json"]


def test_skill_selection_explain_endpoint_selects_l1_skill_without_reading_body(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    skill_body = config_root / ".qwen" / "skills" / "code-explanation-summarizer" / "SKILL.md"
    skill_body.rename(skill_body.with_suffix(".bak"))
    config = ControllerServiceConfig(
        config_root=config_root,
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
            "/v1/controller/skill-selection/explanations",
            {
                "workflow": "skill.selection.explain",
                "schema_version": 1,
                "workflow_id": "code_investigation.plan",
                "user_request": "Explain what find_stealth_order_by_placed_order_id does, including inputs and outputs.",
            },
        )

    assert status == 200
    assert body["workflow"] == "skill.selection.explain"
    assert "code-explanation-summarizer" in body["summary"]["selected_skill_ids"]
    assert body["summary"]["selected_route_keys"]["code-explanation-summarizer"] == "code.explanation_summary"
    assert body["summary"]["body_reads_during_selection"] == 0
    artifact = json.loads(Path(body["artifacts"]["skill_selection_explanation"]).read_text(encoding="utf-8"))
    selected = {item["skill_id"]: item for item in artifact["selection"]["selected"]}
    assert selected["code-explanation-summarizer"]["trigger_hits"]


def test_skill_selection_explain_endpoint_reports_no_matching_skill(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    config = ControllerServiceConfig(
        config_root=config_root,
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
            "/v1/controller/skill-selection/explanations",
                {
                    "workflow": "skill.selection.explain",
                    "schema_version": 1,
                    "user_request": "Summarize a completely unrelated gardening request.",
                },
            )

    assert status == 200
    assert body["summary"]["selected_skill_ids"] == []
    artifact = json.loads(Path(body["artifacts"]["skill_selection_explanation"]).read_text(encoding="utf-8"))
    assert artifact["selection"]["blockers"][0]["reason"] == "unsupported"
    assert artifact["selection"]["filtered_count"] >= 1


def test_skill_selection_explain_endpoint_reports_deprecated_exclusion(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    registry_path = config_root / "runtime" / "skills.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for skill in registry["skills"]:
        if skill["id"] == "code-explanation-summarizer":
            skill["eval_status"] = "deprecated"
            skill["deprecation"] = {
                "replaced_by": "behavior-existence-checker",
                "reason": "Controlled-copy deprecation for selection explanation regression proof.",
                "effective_date": "2026-06-05",
            }
    registry_path.write_text(json.dumps(registry, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=config_root,
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
            "/v1/controller/skill-selection/explanations",
            {
                "workflow": "skill.selection.explain",
                "schema_version": 1,
                "workflow_id": "code_investigation.plan",
                "user_request": "Explain what find_stealth_order_by_placed_order_id does.",
            },
        )

    assert status == 200
    assert "code-explanation-summarizer" not in body["summary"]["selected_skill_ids"]
    assert body["summary"]["deprecated_exclusion_count"] == 1
    artifact = json.loads(Path(body["artifacts"]["skill_selection_explanation"]).read_text(encoding="utf-8"))
    deprecated_ids = [item["skill_id"] for item in artifact["selection"]["deprecated_exclusions"]]
    assert deprecated_ids == ["code-explanation-summarizer"]


def test_skill_selection_explain_harness_returns_format_a_and_json(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    request = {
        "workflow": "skill.selection.explain",
        "schema_version": 1,
        "workflow_id": "code_investigation.plan",
        "user_request": "Explain what find_stealth_order_by_placed_order_id does.",
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
                "messages": [{"role": "user", "content": json.dumps({"agentic_controller_request": request})}],
            },
        )
        json_status, json_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/harness/chat/completions",
            {
                "model": "agentic-controller",
                "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": json.dumps({"agentic_controller_request": request})}],
            },
        )

    assert status == 200
    content = body["choices"][0]["message"]["content"]
    assert "Skill Selection:" in content
    assert "code-explanation-summarizer" in content
    assert json_status == 200
    parsed = json.loads(json_body["choices"][0]["message"]["content"])
    assert parsed["workflow"] == "skill.selection.explain"
    assert "code-explanation-summarizer" in parsed["summary"]["selected_skill_ids"]


def test_workflow_router_chat_skill_selection_explain_returns_readable_summary(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    config = ControllerServiceConfig(
        config_root=config_root,
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Explain skill selection for: Explain what "
                            "find_stealth_order_by_placed_order_id does."
                        ),
                    }
                ],
            },
        )

    assert status == 200
    content = body["choices"][0]["message"]["content"]
    assert "Skill Selection:" in content
    assert "code-explanation-summarizer" in content
    compact = body["agentic_controller_response"]
    assert compact["workflow"] == "skill.selection.explain"


def test_skill_eval_promotion_endpoint_promotes_registered_draft_skill_only_in_skills_registry(
    tmp_path: Path,
) -> None:
    config_root = make_skill_registration_root(tmp_path)
    output_root = tmp_path / "controller-output"
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=output_root,
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        _proposal_body, registration_body = register_feature_flag_skill(host, port)
        registry_paths = [config_root / "runtime" / "skills.json", config_root / "runtime" / "skill_evals.json"]
        before_promotion_hashes = {path: sha256_file(path) for path in registry_paths}
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-evals/promotions",
            {
                "workflow": "skill_eval.promote",
                "schema_version": 1,
                "registration_run_id": registration_body["run_id"],
                "approval": skill_eval_promotion_approval(),
            },
        )

    assert status == 200
    assert body["workflow"] == "skill_eval.promote"
    assert body["summary"]["promotion_status"] == "promoted"
    assert body["summary"]["promoted_skill_ids"] == ["feature-flag-locator"]
    assert body["summary"]["eval_case_ids"] == ["feature_flag_lookup"]
    assert body["summary"]["changed_runtime_files"] == ["runtime/skills.json"]
    assert body["summary"]["runtime_registry_changed"] is True
    assert body["summary"]["target_repository_changed"] is False
    assert "skill_eval_promotion" in body["artifacts"]
    assert "rollback_instructions" in body["artifacts"]
    assert sha256_file(config_root / "runtime" / "skills.json") != before_promotion_hashes[
        config_root / "runtime" / "skills.json"
    ]
    assert sha256_file(config_root / "runtime" / "skill_evals.json") == before_promotion_hashes[
        config_root / "runtime" / "skill_evals.json"
    ]

    registry_manifest = json.loads((config_root / "runtime" / "skills.json").read_text(encoding="utf-8"))
    promoted = [item for item in registry_manifest["skills"] if item["id"] == "feature-flag-locator"][0]
    assert promoted["eval_status"] == "validated"
    assert promoted["evals"]["localhost_8000"] == "passed"
    assert promoted["evals"]["gateway_8300"] == "passed"
    assert promoted["evals"]["anythingllm"] == "passed"
    promotion = json.loads(Path(body["artifacts"]["skill_eval_promotion"]).read_text(encoding="utf-8"))
    assert promotion["hash_proof"]["changed"] == ["runtime/skills.json"]
    assert promotion["rollback_instructions"]["restore_backups"]["runtime/skills.json"]

    registry = load_skill_registry(config_root)
    selected = select_skills_for_workflow(
        registry,
        "code_investigation.plan",
        query_text="Find the feature flag definitions. Read only.",
        limit=10,
    )
    assert "feature-flag-locator" in selected


def test_skill_eval_promotion_harness_returns_chat_visible_promotion_summary(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        _proposal_body, registration_body = register_feature_flag_skill(host, port)
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/harness/chat/completions",
            {
                "model": "agentic-controller",
                "agentic_controller_request": {
                    "workflow": "skill_eval.promote",
                    "schema_version": 1,
                    "skill_ids": ["feature-flag-locator"],
                    "approval": skill_eval_promotion_approval(),
                },
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    assert compact["workflow"] == "skill_eval.promote"
    assert compact["summary"]["promotion_status"] == "promoted"
    content = body["choices"][0]["message"]["content"]
    assert "Promotion:" in content
    assert "- Promotion artifact: skill_eval_promotion" in content
    assert "- Promoted skills: feature-flag-locator" in content
    assert "- Changed runtime files: runtime/skills.json" in content


def test_skill_eval_promotion_rejects_missing_approval_without_mutation(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    registry_paths = [config_root / "runtime" / "skills.json", config_root / "runtime" / "skill_evals.json"]
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        _proposal_body, registration_body = register_feature_flag_skill(host, port)
        before_hashes = {path: sha256_file(path) for path in registry_paths}
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-evals/promotions",
            {
                "workflow": "skill_eval.promote",
                "schema_version": 1,
                "registration_run_id": registration_body["run_id"],
                "approval": {"status": "not_approved"},
            },
        )

    assert status == 403
    assert body["error"]["code"] == "missing_promotion_approval"
    assert {path: sha256_file(path) for path in registry_paths} == before_hashes


def test_skill_eval_promotion_rejects_already_validated_without_allow_repromotion(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    registry_paths = [config_root / "runtime" / "skills.json", config_root / "runtime" / "skill_evals.json"]
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        _proposal_body, registration_body = register_feature_flag_skill(host, port)
        first_status, first_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-evals/promotions",
            {
                "workflow": "skill_eval.promote",
                "schema_version": 1,
                "registration_run_id": registration_body["run_id"],
                "approval": skill_eval_promotion_approval("first-promotion"),
            },
        )
        before_second_hashes = {path: sha256_file(path) for path in registry_paths}
        second_status, second_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-evals/promotions",
            {
                "workflow": "skill_eval.promote",
                "schema_version": 1,
                "skill_ids": ["feature-flag-locator"],
                "approval": skill_eval_promotion_approval("second-promotion"),
            },
        )

    assert first_status == 200
    assert first_body["summary"]["promotion_status"] == "promoted"
    assert second_status == 422
    assert second_body["error"]["code"] == "skill_already_validated"
    assert {path: sha256_file(path) for path in registry_paths} == before_second_hashes


def test_skill_eval_promotion_rejects_missing_live_mapping_without_mutation(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    registry_paths = [config_root / "runtime" / "skills.json", config_root / "runtime" / "skill_evals.json"]
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        _proposal_body, registration_body = register_feature_flag_skill(host, port)
        eval_path = config_root / "runtime" / "skill_evals.json"
        eval_manifest = json.loads(eval_path.read_text(encoding="utf-8"))
        for item in eval_manifest["cases"]:
            if item["id"] == "feature_flag_lookup":
                item["live_suite"] = "workflow_router_l1_suite"
        eval_path.write_text(json.dumps(eval_manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        before_hashes = {path: sha256_file(path) for path in registry_paths}
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-evals/promotions",
            {
                "workflow": "skill_eval.promote",
                "schema_version": 1,
                "registration_run_id": registration_body["run_id"],
                "approval": skill_eval_promotion_approval(),
            },
        )

    assert status == 422
    assert body["error"]["code"] == "missing_live_mapping"
    assert {path: sha256_file(path) for path in registry_paths} == before_hashes


def test_skill_lifecycle_audit_endpoint_reports_current_registry_without_mutation(tmp_path: Path) -> None:
    registry_paths = [REPO_ROOT / "runtime" / "skills.json", REPO_ROOT / "runtime" / "skill_evals.json"]
    before_hashes = {path: sha256_file(path) for path in registry_paths}
    registry = load_skill_registry(REPO_ROOT)
    expected_status_counts = {
        status: sum(1 for skill in registry.values() if skill["eval_status"] == status)
        for status in ("draft", "validated", "deprecated", "unknown")
    }
    expected_lifecycle_status = "action_required" if expected_status_counts["draft"] else "passed"
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
            "/v1/controller/skill-lifecycle/audits",
            {
                "workflow": "skill_lifecycle.audit",
                "schema_version": 1,
            },
        )

    assert status == 200
    assert body["workflow"] == "skill_lifecycle.audit"
    assert body["summary"]["lifecycle_status"] == expected_lifecycle_status
    assert body["summary"]["status_counts"] == expected_status_counts
    assert body["summary"]["queue_counts"]["no_action"] >= expected_status_counts["validated"]
    if expected_status_counts["draft"]:
        assert (
            body["summary"]["queue_counts"]["promote"]
            + body["summary"]["queue_counts"]["keep_draft"]
        ) == expected_status_counts["draft"]
    assert body["summary"]["blocker_count"] == 0
    assert body["summary"]["runtime_registry_changed"] is False
    assert "skill_lifecycle_audit" in body["artifacts"]
    audit = json.loads(Path(body["artifacts"]["skill_lifecycle_audit"]).read_text(encoding="utf-8"))
    assert audit["groups"]["validated"]
    assert audit["hash_proof"]["changed"] == []
    assert {path: sha256_file(path) for path in registry_paths} == before_hashes


def test_skill_lifecycle_audit_harness_returns_chat_visible_summary(tmp_path: Path) -> None:
    expected_lifecycle_status = (
        "action_required"
        if any(skill["eval_status"] == "draft" for skill in load_skill_registry(REPO_ROOT).values())
        else "passed"
    )
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
                    "workflow": "skill_lifecycle.audit",
                    "schema_version": 1,
                },
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    assert compact["workflow"] == "skill_lifecycle.audit"
    assert compact["summary"]["lifecycle_status"] == expected_lifecycle_status
    content = body["choices"][0]["message"]["content"]
    assert "Lifecycle Audit:" in content
    assert "- Audit artifact: skill_lifecycle_audit" in content
    assert f"- Lifecycle status: {expected_lifecycle_status}" in content
    if expected_lifecycle_status == "passed":
        assert "- Queue: no action required" in content
    else:
        assert "- Queue:" in content


def test_workflow_router_chat_skill_lifecycle_audit_runs_without_target_path(tmp_path: Path) -> None:
    expected_lifecycle_status = (
        "action_required"
        if any(skill["eval_status"] == "draft" for skill in load_skill_registry(REPO_ROOT).values())
        else "passed"
    )
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": "Audit the skill lifecycle. Return counts, blockers, and next actions.",
                    }
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    assert compact["workflow"] == "skill_lifecycle.audit"
    assert compact["summary"]["lifecycle_status"] == expected_lifecycle_status
    content = body["choices"][0]["message"]["content"]
    assert "Lifecycle Audit:" in content
    assert "- Runtime registry changed: False" in content


def test_skill_lifecycle_audit_recommends_promote_for_registered_metadata_only_draft(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    registry_paths = [config_root / "runtime" / "skills.json", config_root / "runtime" / "skill_evals.json"]
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        register_feature_flag_skill(host, port)
        before_hashes = {path: sha256_file(path) for path in registry_paths}
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-lifecycle/audits",
            {
                "workflow": "skill_lifecycle.audit",
                "schema_version": 1,
                "skill_ids": ["feature-flag-locator"],
            },
        )

    assert status == 200
    assert body["summary"]["lifecycle_status"] == "action_required"
    audit = json.loads(Path(body["artifacts"]["skill_lifecycle_audit"]).read_text(encoding="utf-8"))
    item = skill_action(audit, "feature-flag-locator")
    assert item["eval_status"] == "draft"
    assert item["action"] == "promote"
    assert item["blockers"] == []
    assert {path: sha256_file(path) for path in registry_paths} == before_hashes


def test_skill_lifecycle_audit_recommends_keep_draft_for_missing_live_proof(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    registry_path = config_root / "runtime" / "skills.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for skill in registry["skills"]:
        if skill["id"] == "code-explanation-summarizer":
            skill["eval_status"] = "draft"
            skill["evals"]["localhost_8000"] = "not_run"
            skill["evals"]["gateway_8300"] = "not_run"
            skill["evals"]["anythingllm"] = "not_run"
    registry_path.write_text(json.dumps(registry, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    before_hashes = {
        path: sha256_file(path)
        for path in [config_root / "runtime" / "skills.json", config_root / "runtime" / "skill_evals.json"]
    }
    config = ControllerServiceConfig(
        config_root=config_root,
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
            "/v1/controller/skill-lifecycle/audits",
            {
                "workflow": "skill_lifecycle.audit",
                "schema_version": 1,
                "skill_ids": ["code-explanation-summarizer"],
            },
        )

    assert status == 200
    audit = json.loads(Path(body["artifacts"]["skill_lifecycle_audit"]).read_text(encoding="utf-8"))
    item = skill_action(audit, "code-explanation-summarizer")
    assert item["action"] == "keep_draft"
    assert {blocker["code"] for blocker in item["blockers"]} == {"missing_live_proof"}
    assert {
        path: sha256_file(path)
        for path in [config_root / "runtime" / "skills.json", config_root / "runtime" / "skill_evals.json"]
    } == before_hashes


def test_skill_lifecycle_audit_recommends_revise_for_missing_body_and_orphan_eval(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    registry_path = config_root / "runtime" / "skills.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for skill in registry["skills"]:
        if skill["id"] == "code-explanation-summarizer":
            skill["path"] = ".qwen/skills/code-explanation-summarizer/MISSING.md"
    registry_path.write_text(json.dumps(registry, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    eval_path = config_root / "runtime" / "skill_evals.json"
    eval_manifest = json.loads(eval_path.read_text(encoding="utf-8"))
    eval_manifest["cases"].append(
        {
            "id": "orphan_lifecycle_case",
            "prompt_family": "orphan",
            "natural_prompt": "In <repo>, orphan lifecycle case.",
            "expected_workflow": "code_investigation.plan",
            "expected_artifacts": ["investigation_plan"],
            "mutation_policy": "no_repository_mutation",
            "live_suite": "skill_registry_contract",
        }
    )
    eval_path.write_text(json.dumps(eval_manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=config_root,
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
            "/v1/controller/skill-lifecycle/audits",
            {
                "workflow": "skill_lifecycle.audit",
                "schema_version": 1,
                "skill_ids": ["code-explanation-summarizer"],
            },
        )

    assert status == 200
    assert body["summary"]["lifecycle_status"] == "blocked"
    audit = json.loads(Path(body["artifacts"]["skill_lifecycle_audit"]).read_text(encoding="utf-8"))
    item = skill_action(audit, "code-explanation-summarizer")
    assert item["action"] == "revise"
    blocker_codes = {blocker["code"] for blocker in item["blockers"]}
    assert "missing_skill_body" in blocker_codes
    assert "orphan_lifecycle_case" in audit["catalog_findings"]["orphan_eval_cases"]


def test_skill_lifecycle_audit_recommends_deprecate_for_semantic_overlap(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    registry_path = config_root / "runtime" / "skills.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    source = next(skill for skill in registry["skills"] if skill["id"] == "code-explanation-summarizer")
    duplicate = deepcopy(source)
    duplicate["id"] = "duplicate-code-explanation-summarizer"
    duplicate["path"] = ".qwen/skills/duplicate-code-explanation-summarizer/SKILL.md"
    duplicate["capability_contract"]["route_key"] = "code.duplicate_explanation_summary"
    registry["skills"].append(duplicate)
    registry_path.write_text(json.dumps(registry, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    write_text(
        config_root / ".qwen" / "skills" / "duplicate-code-explanation-summarizer" / "SKILL.md",
        "---\n"
        "name: duplicate-code-explanation-summarizer\n"
        "description: Duplicate code explanation skill used to test lifecycle semantic overlap detection.\n"
        "---\n\n"
        "# duplicate-code-explanation-summarizer\n",
    )
    config = ControllerServiceConfig(
        config_root=config_root,
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
            "/v1/controller/skill-lifecycle/audits",
            {
                "workflow": "skill_lifecycle.audit",
                "schema_version": 1,
                "skill_ids": ["duplicate-code-explanation-summarizer"],
            },
        )

    assert status == 200
    audit = json.loads(Path(body["artifacts"]["skill_lifecycle_audit"]).read_text(encoding="utf-8"))
    item = skill_action(audit, "duplicate-code-explanation-summarizer")
    assert item["action"] == "deprecate"
    assert audit["catalog_findings"]["semantic_conflicts"]


def test_workflow_router_chat_approved_skill_batch_registration_installs_from_prior_run(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    target = make_execution_planning_tree(tmp_path)
    output_root = tmp_path / "controller-output"
    sentinel = target / "core" / "stealth_order_manager.py"
    before_sentinel = sentinel.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=output_root,
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        proposal_status, proposal_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, propose a skill batch for feature flag lookup. "
                            "Proposal only. Do not register or append runtime skills."
                        ),
                    },
                ],
            },
        )
        proposal_run_id = proposal_body["agentic_controller_response"]["run_id"]
        registration_status, registration_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Approve and register the skill batch proposal from run {proposal_run_id}. "
                            "Install it into the skill registry."
                        ),
                    },
                ],
            },
        )

    assert proposal_status == 200
    assert proposal_body["agentic_controller_response"]["summary"]["selected_workflow"] == "skill_batch.propose"
    assert registration_status == 200
    compact = registration_body["agentic_controller_response"]
    assert compact["workflow"] == "skill_batch.register"
    assert compact["summary"]["registration_status"] == "installed"
    assert compact["summary"]["installed_skill_ids"] == ["feature-flag-locator"]
    content = registration_body["choices"][0]["message"]["content"]
    assert "Registration:" in content
    assert "- Registration artifact: skill_batch_registration" in content
    assert "- Installed skills: feature-flag-locator" in content
    assert "- Runtime registry changed: True" in content
    assert sentinel.read_text(encoding="utf-8") == before_sentinel


def test_workflow_router_chat_skill_batch_proposal_returns_chat_visible_summary(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    registry_paths = [REPO_ROOT / "runtime" / "skills.json", REPO_ROOT / "runtime" / "skill_evals.json"]
    before_hashes = {path: sha256_file(path) for path in registry_paths}
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, propose a skill batch for feature flag lookup. "
                            "Proposal only. Do not register or append runtime skills."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    assert compact["workflow"] == "workflow_router.plan"
    assert compact["summary"]["selected_workflow"] == "skill_batch.propose"
    assert compact["summary"]["downstream_workflow"] == "skill_batch.propose"
    assert compact["summary"]["downstream_status"] == "completed"
    assert compact["summary"]["next_action"] == "execute_read_only"
    assert "downstream_skill_batch_proposal" in compact["artifacts"]
    content = body["choices"][0]["message"]["content"]
    assert "Draft proposal:" in content
    assert "- Proposal artifact: skill_batch_proposal" in content
    assert "- Runtime registry changed: False" in content
    assert "- Skill IDs: feature-flag-locator" in content

    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["selected_workflow"] == "skill_batch.propose"
    assert any(item.get("rule") == "skill_batch_proposal_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    assert downstream["report"]["summary"]["proposal_status"] == "ready"
    proposal = json.loads(Path(compact["artifacts"]["downstream_skill_batch_proposal"]).read_text(encoding="utf-8"))
    draft_skill_path = Path(proposal["draft_batch_manifest"]["skills"][0]["path"]).resolve()
    assert draft_skill_path.exists()
    assert str(draft_skill_path).startswith(str(config.output_root.resolve()))
    assert sentinel.read_text(encoding="utf-8") == before
    assert {path: sha256_file(path) for path in registry_paths} == before_hashes


def test_workflow_router_chat_accepts_natural_language_and_uses_latest_user_message(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    old_target = tmp_path / "outside-old-target"
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": f"In {old_target}, investigate the wrong old request.",
                    },
                    {"role": "assistant", "content": "Previous result."},
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, find where the placed_order_id stealth lookup begins. "
                            "Read only. Return the entrypoint, evidence files, related tests, and confidence."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    assert body["object"] == "chat.completion"
    compact = body["agentic_controller_response"]
    assert compact["workflow"] == "workflow_router.plan"
    assert compact["status"] == "completed"
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_workflow"] == "code_investigation.plan"
    assert compact["summary"]["target_repo_read"] is True
    assert compact["summary"]["verification_command_count"] >= 1
    assert str(target.resolve()) in compact["summary"]["target_root"]
    assert str(old_target) not in compact["summary"]["target_root"]
    content = body["choices"][0]["message"]["content"]
    assert compact["output_format"] == "format_a"
    assert "I completed workflow_router.plan." in content
    assert "workflow_router.plan completed" in content
    assert "- selected_workflow: code_investigation.plan" in content
    assert "Skill Selection:" in content
    assert "- Why: Selected code_investigation.plan" in content
    assert "- Route rules: l1_find_behavior_start_terms" in content
    assert "- Confidence: medium" in content
    assert "- Coverage entries: L1-001" in content
    assert "- Skills:" in content
    assert "- Tools: structure_index; git_grep; read_file" in content
    assert "- Rejected candidates:" in content
    assert "- Grounded in: route_decision.evidence" in content
    assert "Answer:" in content
    assert "- Beginning point:" in content
    assert "- Related tests:" in content
    assert "- Recommended commands:" in content
    assert "- Entrypoints:" not in content
    assert "route_decision.selection_audit" in content
    assert "Artifacts:" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["controller_request_preview"]["behavior"] == "placed_order_id"
    assert decision["controller_request_preview"]["queries"][0] == "placed_order_id"
    audit = decision["selection_audit"]
    assert audit["selection_policy"]["minimum_confidence"] == "medium"
    assert audit["selection_policy"]["manual_skill_injection_required"] is False
    assert audit["selected"]["workflow_id"] == "code_investigation.plan"
    assert "meets_minimum_confidence:medium" in audit["selected"]["confidence_reasons"]
    assert "prompt_skill_coverage_match" in audit["selected"]["confidence_reasons"]
    assert audit["selected"]["coverage_entry_ids"] == ["L1-001"]
    assert audit["coverage_matches"][0]["route_rule"] == "l1_find_behavior_start_terms"
    assert audit["workflow_candidates"]["selected"][0]["workflow_id"] == "code_investigation.plan"
    assert audit["workflow_candidates"]["rejected_count"] >= 1
    assert audit["skill_candidates"]["selected"]
    assert audit["skill_candidates"]["body_reads_during_selection"] == 0
    assert audit["tool_candidates"]["selected"][0]["tool_id"] == "structure_index"
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    investigation_plan_path = downstream["artifact_paths"]["investigation_plan"]
    investigation_plan = json.loads(Path(investigation_plan_path).read_text(encoding="utf-8"))
    assert investigation_plan["likely_beginning_point"]["path"] == "core/stealth_order_manager.py"
    assert any(item["path"].startswith("tests/") for item in investigation_plan["related_tests"])
    commands = investigation_plan["verification_plan"]["verification_commands"]
    assert any(command["command"][0:3] == ["python", "-m", "pytest"] for command in commands)


def test_workflow_router_selection_audit_is_stable_across_repeated_runs(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    selections = []
    with RunningControllerService(config) as service:
        host, port = service.base_url
        for _index in range(3):
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/plans",
                {
                    "workflow": "workflow_router.plan",
                    "target_root": str(target),
                    "user_request": (
                        "Find tests related to placed_order_id stealth lookup. "
                        "Read only. Return test files, matching terms, and recommended test commands."
                    ),
                },
            )
            assert status == 200
            decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
            audit = decision["selection_audit"]
            selections.append(
                {
                    "selected_workflow": decision["selected_workflow"],
                    "selected_skills": decision["selected_skills"],
                    "selected_tools": decision["selected_tools"],
                    "route_rules": audit["selected"]["route_rules"],
                    "coverage_entry_ids": audit["selected"]["coverage_entry_ids"],
                    "workflow_rejected_count": audit["workflow_candidates"]["rejected_count"],
                    "skill_rejected_count": audit["skill_candidates"]["rejected_count"],
                    "tool_rejected_count": audit["tool_candidates"]["rejected_count"],
                }
            )

    assert selections[0] == selections[1] == selections[2]
    assert selections[0]["selected_workflow"] == "code_investigation.plan"
    assert "related-test-discovery" in selections[0]["selected_skills"]
    assert selections[0]["route_rules"] == ["l1_find_related_tests_terms"]
    assert selections[0]["coverage_entry_ids"] == ["L1-003"]


def test_workflow_router_chat_explicit_json_output_format_returns_json_content(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "output_format": "json",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, find where the placed_order_id stealth lookup begins. "
                            "Read only. Return the entrypoint, evidence files, related tests, and confidence."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    assert compact["output_format"] == "json"
    rendered = json.loads(body["choices"][0]["message"]["content"])
    assert rendered["output_format"] == "json"
    assert rendered["workflow"] == "workflow_router.plan"
    assert rendered["status"] == "completed"
    assert rendered["summary"]["selected_workflow"] == "code_investigation.plan"
    assert "route_decision" in rendered["artifacts"]
    assert rendered["selection_explanation"]["selected_workflow"] == "code_investigation.plan"
    assert "l1_find_behavior_start_terms" in rendered["selection_explanation"]["route_rules"]
    assert rendered["chat_contract"]["selection_explanation"]["selected_workflow"] == "code_investigation.plan"
    assert "Artifacts:" not in body["choices"][0]["message"]["content"]
    assert sentinel.read_text(encoding="utf-8") == before


def test_workflow_router_chat_natural_json_output_format_returns_json_content(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, find where the placed_order_id stealth lookup begins. "
                            "Read only. Return JSON with the entrypoint, evidence files, related tests, and confidence."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    assert compact["output_format"] == "json"
    rendered = json.loads(body["choices"][0]["message"]["content"])
    assert rendered["summary"]["selected_workflow"] == "code_investigation.plan"
    assert rendered["summary"]["target_repo_read"] is True
    assert rendered["selection_explanation"]["selected_workflow"] == "code_investigation.plan"
    assert "l1_find_behavior_start_terms" in rendered["selection_explanation"]["route_rules"]
    assert sentinel.read_text(encoding="utf-8") == before


def test_workflow_router_chat_response_format_json_object_returns_json_content(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, find where the placed_order_id stealth lookup begins. "
                            "Read only. Return the entrypoint, evidence files, related tests, and confidence."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    assert compact["output_format"] == "json"
    rendered = json.loads(body["choices"][0]["message"]["content"])
    assert rendered["run_id"] == compact["run_id"]
    assert rendered["summary"]["downstream_status"] == "completed"
    assert sentinel.read_text(encoding="utf-8") == before


def test_workflow_router_chat_l1_explain_code_returns_explanation_artifact(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, explain what find_stealth_order_by_placed_order_id does "
                            "in core/stealth_order_manager.py. Read only. Include key inputs, outputs, "
                            "side effects, and tests."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert compact["summary"]["target_repo_read"] is True
    assert "Answer:" in content
    assert "Skill Selection:" in content
    assert "- Route rules: l1_explain_code_terms" in content
    assert "code-explanation-summarizer" in content
    assert "- Target: StealthOrderManager.find_stealth_order_by_placed_order_id in core/stealth_order_manager.py" in content
    assert "- Inputs:" in content
    assert "placed_order_id (argument)" in content
    assert "- Outputs:" in content
    assert "self.placed_order_index_key" in content
    assert "- Related tests:" in content
    assert "tests/unit/test_order_id_and_followup_rules.py" in content
    assert "Artifacts:" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_explain_code_terms" for item in decision["evidence"])
    assert decision["controller_request_preview"]["paths"] == ["core/stealth_order_manager.py"]
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    explanation = json.loads(Path(downstream["artifact_paths"]["code_explanation"]).read_text(encoding="utf-8"))
    assert explanation["status"] == "ready"
    assert explanation["target"]["path"] == "core/stealth_order_manager.py"
    assert explanation["target"]["symbol"] == "StealthOrderManager.find_stealth_order_by_placed_order_id"
    assert any(item["name"] == "placed_order_id" for item in explanation["key_inputs"])
    assert any(item.get("value") == "self.placed_order_index_key" for item in explanation["outputs"])
    assert any(item["path"].startswith("tests/") for item in explanation["related_tests"])


def test_workflow_router_chat_l1_behavior_exists_returns_existence_artifact(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, check whether placed_order_id stealth lookup already exists. "
                            "Read only. Return evidence for yes, no, or unknown."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert compact["summary"]["target_repo_read"] is True
    assert "Answer:" in content
    assert "- Result: yes (confidence: medium)" in content
    assert "- Evidence files:" in content
    assert "core/stealth_order_manager.py" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_behavior_exists_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    existence = json.loads(Path(downstream["artifact_paths"]["behavior_existence"]).read_text(encoding="utf-8"))
    assert existence["status"] == "exists"
    assert existence["answer"] == "yes"
    assert any(item["path"] == "core/stealth_order_manager.py" for item in existence["evidence_files"])
    assert any(item["path"].startswith("tests/") for item in existence["related_tests"])


def test_workflow_router_chat_l1_callers_usages_returns_grouped_usage_artifact(tmp_path: Path) -> None:
    target = make_relationship_lookup_repo(tmp_path)
    sentinel = target / "app" / "handler.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, find callers/usages of place_order. "
                            "Read only. Group by file and explain each usage briefly."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "code_context.lookup"
    assert compact["summary"]["downstream_status"] == "completed"
    assert compact["summary"]["target_repo_read"] is True
    assert "Answer:" in content
    assert "- Target: place_order" in content
    assert "- Usage count:" in content
    assert "app/handler.py" in content
    assert "core/service.py" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_callers_usages_terms" for item in decision["evidence"])
    assert decision["controller_request_preview"]["relationship_queries"] == [
        {"kind": "callers", "symbol": "place_order", "max_results": 25}
    ]
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    usage = json.loads(Path(downstream["artifact_paths"]["usage_summary"]).read_text(encoding="utf-8"))
    assert usage["status"] == "ready"
    assert usage["target"] == "place_order"
    grouped_paths = {group["path"] for group in usage["groups"]}
    assert "app/handler.py" in grouped_paths
    assert "core/service.py" in grouped_paths
    assert any(
        item.get("source_symbol", "").endswith(".handle")
        for group in usage["groups"]
        for item in group["usages"]
    )


def test_workflow_router_chat_l1_configuration_lookup_returns_config_artifact(tmp_path: Path) -> None:
    target = make_config_lookup_repo(tmp_path)
    sentinel = target / "configuration.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, find where COINBASE_API_KEY environment variable is defined or used. "
                            "Read only. Return files, references, and likely runtime effect."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert compact["summary"]["target_repo_read"] is True
    assert "Answer:" in content
    assert "- Target: COINBASE_API_KEY" in content
    assert "- References:" in content
    assert "configuration.py" in content
    assert "Runtime effect:" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_configuration_lookup_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    lookup = json.loads(Path(downstream["artifact_paths"]["configuration_lookup"]).read_text(encoding="utf-8"))
    assert lookup["status"] == "ready"
    assert lookup["target"] == "COINBASE_API_KEY"
    assert any(group["path"] == "configuration.py" for group in lookup["groups"])
    assert any(
        reference["role"] == "environment_read" and reference.get("current_value") == "not_visible_environment"
        for group in lookup["groups"]
        for reference in group["references"]
    )


def test_workflow_router_chat_l1_endpoint_route_lookup_returns_handler_artifact(tmp_path: Path) -> None:
    target = make_l1_expansion_repo(tmp_path)
    sentinel = target / "dashboard_server.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, find the WebSocket handler for \"request_stealth_orders\". "
                            "Read only. Return handler files, source refs, and related tests."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "Answer:" in content
    assert "- Target: request_stealth_orders" in content
    assert "- Handler files:" in content
    assert "dashboard_server.py" in content
    assert "websocket_message_handler" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_endpoint_route_lookup_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    lookup = json.loads(Path(downstream["artifact_paths"]["endpoint_route_lookup"]).read_text(encoding="utf-8"))
    assert lookup["status"] == "ready"
    assert lookup["handlers"][0]["path"] == "dashboard_server.py"


def test_workflow_router_chat_l1_message_source_lookup_returns_source_artifact(tmp_path: Path) -> None:
    target = make_l1_expansion_repo(tmp_path)
    sentinel = target / "dashboard_server.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, locate the source of error message "
                            "\"Missing 'type' field in message\". Read only. Return file, line, and role."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert "Answer:" in content
    assert "- Target message: Missing 'type' field in message" in content
    assert "- Sources:" in content
    assert "dashboard_server.py" in content
    assert "raised_exception" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_message_source_lookup_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    lookup = json.loads(Path(downstream["artifact_paths"]["message_source_lookup"]).read_text(encoding="utf-8"))
    assert lookup["status"] == "ready"
    assert lookup["sources"][0]["role"] == "raised_exception"


def test_workflow_router_chat_l1_module_summary_returns_module_artifact(tmp_path: Path) -> None:
    target = make_l1_expansion_repo(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, summarize module core/stealth_order_manager.py. "
                            "Read only. Return responsibilities, definitions, related tests, and source refs."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert "Answer:" in content
    assert "- Target module: core/stealth_order_manager.py" in content
    assert "- Responsibilities:" in content
    assert "StealthOrderManager.find_stealth_order_by_placed_order_id" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_module_summary_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    summary = json.loads(Path(downstream["artifact_paths"]["module_summary"]).read_text(encoding="utf-8"))
    assert summary["status"] == "ready"
    assert summary["target"]["path"] == "core/stealth_order_manager.py"
    assert summary["definition_count"] >= 2


def test_workflow_router_chat_l1_data_model_lookup_returns_schema_artifact(tmp_path: Path) -> None:
    target = make_l1_expansion_repo(tmp_path)
    sentinel = target / "database" / "order.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, find the database schema fields for stealth_orders. "
                            "Read only. Return model files, fields, and source refs."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert "Answer:" in content
    assert "- Target model/schema: stealth_orders" in content
    assert "- Fields:" in content
    assert "stealth_order_id" in content
    assert "database/order.py" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_data_model_lookup_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    lookup = json.loads(Path(downstream["artifact_paths"]["data_model_lookup"]).read_text(encoding="utf-8"))
    assert lookup["status"] == "ready"
    assert lookup["model_files"][0] == "database/order.py"
    assert any(field["name"] == "stealth_order_id" for field in lookup["fields"])
    assert any(ref["path"] == "database/order.py" for ref in lookup["source_refs"])


def test_data_model_lookup_answer_keeps_schema_fields_visible() -> None:
    lines: list[str] = []
    artifact = {
        "kind": "data_model_lookup",
        "target": "stealth_orders",
        "fields": [
            {"name": f"field_{index}", "definition": "TEXT", "path": "database/order.py", "line": index}
            for index in range(1, 8)
        ],
        "model_files": ["database/order.py"],
        "model_symbols": [
            {"name": "OrderRecord", "kind": "class", "path": "database/order.py", "line": 7},
            {"name": "ORDERS_TABLE_SCHEMA", "kind": "assignment", "path": "database/order.py", "line": 14},
        ],
        "source_refs": [{"path": "database/order.py", "line": 1}],
        "mutation_policy": "read_only_no_source_mutation",
    }

    assert append_data_model_lookup_answer(lines, artifact)
    answer = "\n".join(lines)

    assert "field_1: TEXT (database/order.py:1)" in answer
    assert "field_7: TEXT (database/order.py:7)" in answer
    assert "OrderRecord (class) at database/order.py:7" in answer
    assert "ORDERS_TABLE_SCHEMA (assignment) at database/order.py:14" in answer
    assert "+2 more" not in answer


def test_workflow_router_chat_l1_persisted_schema_prompt_uses_schema_isolator(tmp_path: Path) -> None:
    target = make_l1_expansion_repo(tmp_path)
    sentinel = target / "database" / "order.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, find only the persisted stealth_orders table schema. "
                            "Read only. Return schema field names, model files, and source refs. "
                            "Exclude runtime dictionary fields."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert "table-schema-isolator" in content
    assert "- Target model/schema: stealth_orders" in content
    assert "- Fields:" in content
    assert "stealth_order_id" in content
    assert "database/order.py" in content
    assert "__delete_all_database_tables__.py" not in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    lookup = json.loads(Path(downstream["artifact_paths"]["data_model_lookup"]).read_text(encoding="utf-8"))
    assert lookup["status"] == "ready"
    assert lookup["target"] == "stealth_orders"
    assert lookup["model_files"] == ["database/order.py"]


def test_workflow_router_chat_l1_dependency_lookup_returns_import_artifact(tmp_path: Path) -> None:
    target = make_l1_expansion_repo(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, find imports/dependencies for core/stealth_order_manager.py. "
                            "Read only. Return imports, source refs, and whether files were mutated."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_context.lookup"
    assert "Answer:" in content
    assert "- Target: core/stealth_order_manager.py" in content
    assert "- Imports:" in content
    assert "database.order.create_stealth_orders_table" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_dependency_import_lookup_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    lookup = json.loads(Path(downstream["artifact_paths"]["dependency_lookup"]).read_text(encoding="utf-8"))
    assert lookup["status"] == "ready"
    assert any(item.get("module") == "database.order" for item in lookup["imports"])


def test_workflow_router_chat_l1_coverage_gap_summary_returns_artifact(tmp_path: Path) -> None:
    target = make_l1_expansion_repo(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, identify test coverage gaps for placed_order_id stealth lookup. "
                            "Read only. Return covered tests, uncovered source files, verification commands, and gaps."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert "Answer:" in content
    assert "- Target: placed_order_id" in content
    assert "- Coverage gaps:" in content
    assert "- Related tests:" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_coverage_gap_summary_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    summary = json.loads(Path(downstream["artifact_paths"]["coverage_gap_summary"]).read_text(encoding="utf-8"))
    assert summary["status"] == "ready"
    assert summary["target"] == "placed_order_id"
    assert summary["coverage_gaps"]
    assert any(command.get("command") for command in summary["verification_commands"])


def test_workflow_router_chat_l1_documentation_lookup_returns_artifact(tmp_path: Path) -> None:
    target = make_l1_expansion_repo(tmp_path)
    sentinel = target / "agent.md"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, find documentation for request_stealth_orders dashboard behavior. "
                            "Read only. Return documentation files, source refs, and gaps."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert "Answer:" in content
    assert "- Target: request_stealth_orders" in content
    assert "- Documentation files:" in content
    assert "agent.md" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_documentation_lookup_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    lookup = json.loads(Path(downstream["artifact_paths"]["documentation_lookup"]).read_text(encoding="utf-8"))
    assert lookup["status"] == "ready"
    assert any(item["path"] == "agent.md" for item in lookup["documentation_files"])


def test_workflow_router_chat_l1_cli_entrypoint_lookup_returns_artifact(tmp_path: Path) -> None:
    target = make_l1_expansion_repo(tmp_path)
    sentinel = target / "main.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, locate the CLI/script entrypoint main.py for running the trading engine. "
                            "Read only. Return entrypoint files, command, and source refs."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert "Answer:" in content
    assert "- Target entrypoint: main.py" in content
    assert "- Entrypoints:" in content
    assert "python main.py" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_cli_entrypoint_lookup_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    lookup = json.loads(Path(downstream["artifact_paths"]["cli_entrypoint_lookup"]).read_text(encoding="utf-8"))
    assert lookup["status"] == "ready"
    assert any(item["path"] == "main.py" and item["kind"] == "python_main_guard" for item in lookup["entrypoints"])


def test_workflow_router_chat_l1_configuration_effect_summary_returns_artifact(tmp_path: Path) -> None:
    target = make_l1_expansion_repo(tmp_path)
    sentinel = target / "configuration.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, explain the runtime effect of COINBASE_API_KEY in configuration.py. "
                            "Read only. Return references, effect, and source refs."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert "Answer:" in content
    assert "- Target config: COINBASE_API_KEY" in content
    assert "- Runtime effect:" in content
    assert "configuration.py" in content
    assert "API_KEY" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_configuration_effect_summary_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    summary = json.loads(Path(downstream["artifact_paths"]["configuration_effect_summary"]).read_text(encoding="utf-8"))
    assert summary["status"] == "ready"
    assert summary["target"] == "COINBASE_API_KEY"
    assert any(effect["effect"] == "environment_read" for effect in summary["runtime_effects"])
    assert any(effect["effect"] == "client_configuration_input" for effect in summary["runtime_effects"])


def test_workflow_router_chat_l1_local_change_summary_handles_non_git(tmp_path: Path) -> None:
    target = make_l1_expansion_repo(tmp_path, initialize_git=False)
    sentinel = target / "README.md"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, find recent or local changes. "
                            "Read only. Return git status, recent commits, changed files, and unsupported gaps."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert "Answer:" in content
    assert "- Local change status: limited_non_git" in content
    assert "- Git status: not_available_non_git_target" in content
    assert "- Recent commits: not available" in content
    assert "git_history_unavailable" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_local_change_summary_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    summary = json.loads(Path(downstream["artifact_paths"]["local_change_summary"]).read_text(encoding="utf-8"))
    assert summary["status"] == "limited_non_git"
    assert summary["git_status"] == "not_available_non_git_target"
    assert summary["recent_commits"] == []
    assert summary["gaps"][0]["gap"] == "git_history_unavailable"


def test_workflow_router_chat_l1_test_failure_summary_returns_summary_artifact(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
    failure_text = (
        "FAILED tests/unit/test_order_id_and_followup_rules.py::"
        "test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - "
        "AssertionError: expected client_order_id index\n"
        "E   AssertionError: expected client_order_id index\n"
    )
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, summarize this pasted test failure. Do not edit files. "
                            "Return what failed, likely cause, and next bounded inspection step.\n"
                            f"{failure_text}"
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert compact["summary"]["target_repo_read"] is True
    assert "Answer:" in content
    assert "- Failed tests:" in content
    assert "tests/unit/test_order_id_and_followup_rules.py" in content
    assert "- Primary error: AssertionError:" in content
    assert "- Likely cause:" in content
    assert "- Next steps:" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_test_failure_summary_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    summary = json.loads(Path(downstream["artifact_paths"]["test_failure_summary"]).read_text(encoding="utf-8"))
    assert summary["status"] == "ready"
    assert summary["primary_error"]["type"] == "AssertionError"
    assert summary["failed_tests"][0]["path"] == "tests/unit/test_order_id_and_followup_rules.py"
    assert "Inspect the failing test body" in summary["next_inspection_steps"][0]["step"]


def test_workflow_router_chat_l2_failing_test_investigation_returns_root_cause_plan(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
    failure_text = (
        "FAILED tests/unit/test_order_id_and_followup_rules.py::"
        "test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - "
        "AssertionError: expected client_order_id index\n"
        "E   AssertionError: expected client_order_id index\n"
    )
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, diagnose why this pytest failure is happening. "
                            "Do not edit files. Return root cause, smallest safe fix plan, and verification command.\n"
                            f"{failure_text}"
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert compact["summary"]["target_repo_read"] is True
    assert "Answer:" in content
    assert "- Root cause hypothesis:" in content
    assert "- Smallest safe fix plan:" in content
    assert "- Verification:" in content
    assert "python -m pytest tests/unit/test_order_id_and_followup_rules.py::" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l2_failing_test_investigation_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    summary = json.loads(Path(downstream["artifact_paths"]["test_failure_summary"]).read_text(encoding="utf-8"))
    assert summary["status"] == "ready"
    assert summary["mutation_policy"] == "read_only_no_source_mutation"
    assert summary["root_cause_hypothesis"]["confidence"] in {"low", "medium"}
    assert summary["smallest_safe_fix_plan"]
    assert summary["verification_commands"][0]["command"][-1].endswith(
        "::test_find_stealth_order_by_placed_order_id_uses_client_order_id_index"
    )


def test_workflow_router_chat_phase117_full_defect_diagnosis_returns_inline_summary(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
    failure_text = (
        "FAILED tests/unit/test_order_id_and_followup_rules.py::"
        "test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - "
        "AssertionError: expected client_order_id index\n"
        "E   AssertionError: expected client_order_id index\n"
    )
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, diagnose why this pytest failure is happening. Do not edit files. "
                            "Return reproduction steps, likely root cause, confidence, smallest useful test, "
                            "broader regression test, observability evidence, and missing data.\n"
                            f"{failure_text}"
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert "Defect Diagnosis:" in content
    assert "- Observed failure:" in content
    assert "- Likely root cause:" in content
    assert "- Reproduction steps:" in content
    assert "- Smallest test:" in content
    assert "- Broader regression test:" in content
    assert "- Observability evidence:" in content
    assert "- Missing data:" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    artifact = json.loads(Path(downstream["artifact_paths"]["defect_diagnosis_summary"]).read_text(encoding="utf-8"))
    assert artifact["status"] == "ready"
    assert artifact["mutation_policy"] == "read_only_no_source_mutation"
    assert artifact["likely_root_cause"]["confidence"] in {"low", "medium"}
    assert artifact["test_levels"]
    assert artifact["observability_evidence"]


def test_workflow_router_chat_phase117_insufficient_evidence_returns_missing_data(tmp_path: Path) -> None:
    target = make_python_service_fixture_repo(tmp_path)
    sentinel = target / "service" / "orders.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, diagnose this bug report: orders sometimes show the wrong status. "
                            "Read only. Explain what evidence is insufficient, what reproduction data you need, "
                            "the smallest useful test to start with, and when not to claim a root cause."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert "Defect Diagnosis:" in content
    assert "not diagnosable" in content.lower() or "insufficient" in content.lower()
    assert "- Missing data:" in content
    assert "- Smallest test:" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    artifact = json.loads(Path(downstream["artifact_paths"]["defect_diagnosis_summary"]).read_text(encoding="utf-8"))
    assert artifact["likely_root_cause"]["confidence"] == "low"
    assert any(item.get("gap") for item in artifact["missing_data"])


def test_workflow_router_chat_l2_multi_file_behavior_investigation_returns_usage_plan(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, investigate how placed_order_id stealth lookup flows across source files. "
                            "Read only. Return the beginning point, participating files, callers/usages, related tests, "
                            "risks, and the smallest verification commands."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert compact["summary"]["target_repo_read"] is True
    assert "downstream_multi_file_behavior_investigation" in compact["artifacts"]
    assert "Answer:" in content
    assert "- Beginning point:" in content
    assert "- Participating files:" in content
    assert "core/stealth_order_manager.py" in content
    assert "- Callers/usages:" in content
    assert "- Related tests:" in content
    assert "- Risks:" in content
    assert "- Verification:" in content
    assert "python -m pytest" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l2_multi_file_behavior_investigation_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    investigation = json.loads(Path(downstream["artifact_paths"]["multi_file_behavior_investigation"]).read_text(encoding="utf-8"))
    assert investigation["status"] == "ready"
    assert investigation["mutation_policy"] == "read_only_no_source_mutation"
    assert investigation["beginning_point"]["path"] == "core/stealth_order_manager.py"
    assert any(item["path"] == "core/stealth_order_manager.py" for item in investigation["usage_evidence"])
    assert any(item["path"] == "tests/unit/test_order_id_and_followup_rules.py" for item in investigation["related_tests"])
    assert investigation["verification_commands"]


def test_workflow_router_chat_l2_dependency_impact_summary_returns_impact_plan(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, summarize the dependency impact if placed_order_id stealth lookup behavior changes. "
                            "Read only. Return impacted source files, callers/usages, related tests, risk level, "
                            "and recommended validation commands."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert compact["summary"]["target_repo_read"] is True
    assert "downstream_dependency_impact_summary" in compact["artifacts"]
    assert "Answer:" in content
    assert "- Impacted files:" in content
    assert "core/stealth_order_manager.py" in content
    assert "- Callers/usages:" in content
    assert "- Related tests:" in content
    assert "- Risk level:" in content
    assert "- Verification:" in content
    assert "python -m pytest" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l2_dependency_impact_summary_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    impact = json.loads(Path(downstream["artifact_paths"]["dependency_impact_summary"]).read_text(encoding="utf-8"))
    assert impact["status"] == "ready"
    assert impact["mutation_policy"] == "read_only_no_source_mutation"
    assert impact["risk_level"] in {"low", "medium"}
    assert any(item["path"] == "core/stealth_order_manager.py" for item in impact["impacted_files"])
    assert any(item["path"] == "tests/unit/test_order_id_and_followup_rules.py" for item in impact["related_tests"])
    assert impact["verification_commands"]


def test_workflow_router_chat_l2_test_selection_returns_command_tiers(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, choose the smallest, medium, and broad validation commands "
                            "for placed_order_id stealth lookup. Read only. Explain why each command is relevant, "
                            "what risk it covers, and what gaps remain."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert compact["summary"]["target_repo_read"] is True
    assert "downstream_test_selection_plan" in compact["artifacts"]
    assert "Answer:" in content
    assert "- Related tests:" in content
    assert "direct evidence" in content
    assert "high confidence" in content
    assert "- Smallest command:" in content
    assert "- Medium command:" in content
    assert "- Broad command:" in content
    assert "- Rationale:" in content
    assert "- Covered risks:" in content
    assert "- Confidence:" in content
    assert "- Gaps:" in content
    assert "python -m pytest" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l2_test_selection_terms" for item in decision["evidence"])
    skill_evidence = [
        item
        for item in decision["evidence"]
        if item.get("source") == "skill_registry" and item.get("selection_basis") == "capability_contract_shortlist"
    ]
    assert skill_evidence
    assert skill_evidence[0]["capability_route_keys"]["request-triage"] == "planning.request_triage"
    assert skill_evidence[0]["capability_route_keys"]["context-plan-builder"] == "context.plan_builder"
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    selection = json.loads(Path(downstream["artifact_paths"]["test_selection_plan"]).read_text(encoding="utf-8"))
    assert selection["status"] == "ready"
    assert selection["mutation_policy"] == "read_only_no_source_mutation"
    assert selection["related_tests"][0]["confidence"] == "high"
    assert selection["related_tests"][0]["evidence_kind"] == "direct"
    assert selection["related_tests"][0]["source_refs"]
    tiers = {tier["tier"]: tier for tier in selection["command_tiers"]}
    assert {"smallest", "medium", "broad"} <= set(tiers)
    assert tiers["smallest"]["commands"][0]["command"][:3] == ["python", "-m", "pytest"]
    assert selection["confidence"] == "medium"


def test_workflow_router_chat_l2_test_selection_honestly_reports_no_bounded_tests(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, choose the smallest, medium, and broad validation commands "
                            "for resolve_payment_timeout. Read only. Explain why each command is relevant, "
                            "what risk it covers, and what gaps remain."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "downstream_test_selection_plan" in compact["artifacts"]
    assert "- Related tests: none found in bounded evidence" in content
    assert "- Confidence: low" in content
    assert "verification_tests_not_found" in content
    assert "Source mutation: false" in content
    assert "python -m pytest tests/unit/test_order_id_and_followup_rules.py" not in content
    assert sentinel.read_text(encoding="utf-8") == before
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    selection = json.loads(Path(downstream["artifact_paths"]["test_selection_plan"]).read_text(encoding="utf-8"))
    assert selection["status"] == "not_ready_no_related_tests"
    assert selection["related_tests"] == []
    assert selection["command_tiers"] == []


def test_workflow_router_chat_l2_runtime_error_diagnosis_returns_artifact(tmp_path: Path) -> None:
    target = make_l1_expansion_repo(tmp_path)
    sentinel = target / "dashboard_server.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, diagnose this runtime stack trace for request_stealth_orders dashboard behavior. "
                            "Read only. Return observed error, likely cause, evidence files, next inspection steps, risks, gaps, "
                            "and verification commands.\n"
                            "Traceback (most recent call last):\n"
                            "  File \"dashboard_server.py\", line 10, in handle_websocket_message\n"
                            "core.exceptions.WebSocketMessageError: Missing 'type' field in message"
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "downstream_runtime_error_diagnosis" in compact["artifacts"]
    assert "Answer:" in content
    assert "- Observed error:" in content
    assert "WebSocketMessageError" in content
    assert "- Likely cause:" in content
    assert "- Evidence files:" in content
    assert "dashboard_server.py" in content
    assert "- Next inspection:" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l2_runtime_error_diagnosis_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    diagnosis = json.loads(Path(downstream["artifact_paths"]["runtime_error_diagnosis"]).read_text(encoding="utf-8"))
    assert diagnosis["status"] == "ready"
    assert diagnosis["observed_error"]["type"] == "WebSocketMessageError"
    assert diagnosis["traceback_frame"]["path"] == "dashboard_server.py"
    assert diagnosis["mutation_policy"] == "read_only_no_source_mutation"


def test_workflow_router_chat_l2_request_flow_map_returns_artifact(tmp_path: Path) -> None:
    target = make_l1_expansion_repo(tmp_path)
    sentinel = target / "dashboard_server.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, map the request/data flow for request_stealth_orders from dashboard message "
                            "to stealth order snapshot. Read only. Return flow steps, participating files, risks, gaps, "
                            "and verification commands."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "downstream_request_flow_map" in compact["artifacts"]
    assert "- Target flow:" in content
    assert "request_stealth_orders" in content
    assert "- Flow steps:" in content
    assert "dashboard_server.py" in content
    assert "- Participating files:" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l2_request_flow_map_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    flow = json.loads(Path(downstream["artifact_paths"]["request_flow_map"]).read_text(encoding="utf-8"))
    assert flow["status"] == "ready"
    assert flow["flow_steps"]
    assert any(step["path"] == "dashboard_server.py" for step in flow["flow_steps"])
    assert flow["mutation_policy"] == "read_only_no_source_mutation"


def test_workflow_router_chat_handler_branch_prompt_returns_flow_evidence(tmp_path: Path) -> None:
    target = make_l1_expansion_repo(tmp_path)
    sentinel = target / "dashboard_server.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, follow the request_stealth_orders handler branch through the snapshot "
                            "function. Read only. Return handler file, source refs, and related tests."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "downstream_request_flow_map" in compact["artifacts"]
    assert "- Target: request_stealth_orders" in content
    assert "- Handler files:" in content
    assert "dashboard_server.py" in content
    assert "request_stealth_orders" in content
    assert "send_stealth_orders_snapshot" in content
    assert "- Related tests:" in content
    assert "- Source refs:" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l2_request_flow_map_terms" for item in decision["evidence"])
    assert "handler-branch-tracer" in decision["selected_skills"]
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    flow = json.loads(Path(downstream["artifact_paths"]["request_flow_map"]).read_text(encoding="utf-8"))
    assert flow["status"] == "ready"
    assert flow["target"] == "request_stealth_orders"
    assert flow["handler_files"]
    assert any(step["role"] == "handler_branch" for step in flow["flow_steps"])
    assert any(step["role"] == "downstream_snapshot_function" for step in flow["flow_steps"])
    assert flow["source_refs"]
    assert flow["mutation_policy"] == "read_only_no_source_mutation"


def test_workflow_router_chat_l2_code_path_comparison_returns_artifact(tmp_path: Path) -> None:
    target = make_l1_expansion_repo(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, compare the placed_order_id stealth lookup path with the client_order_id index path. "
                            "Read only. Return candidate paths, evidence, risks, recommended path if supported, gaps, "
                            "and verification commands."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "downstream_code_path_comparison" in compact["artifacts"]
    assert "- Comparison target:" in content
    assert "- Candidate paths:" in content
    assert "client_order_id" in content
    assert "- Recommended path:" in content
    assert "- Risks:" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l2_code_path_comparison_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    comparison = json.loads(Path(downstream["artifact_paths"]["code_path_comparison"]).read_text(encoding="utf-8"))
    assert comparison["status"] == "ready"
    assert {item["name"] for item in comparison["candidate_paths"]} >= {
        "placed_order_id stealth lookup path",
        "client_order_id index path",
    }
    assert comparison["mutation_policy"] == "read_only_no_source_mutation"


def test_workflow_router_chat_l2_change_surface_summary_returns_artifact(tmp_path: Path) -> None:
    target = make_l1_expansion_repo(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, identify the minimal safe change surface for changing placed_order_id stealth lookup behavior. "
                            "Read only. Return files that would need review, related tests, risk level, gaps, and verification commands. "
                            "Stop before implementation."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "downstream_change_surface_summary" in compact["artifacts"]
    assert "- Change surface files:" in content
    assert "core/stealth_order_manager.py" in content
    assert "- Risk level:" in content
    assert "- Implementation status: not_ready_without_approval" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l2_change_surface_summary_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    surface = json.loads(Path(downstream["artifact_paths"]["change_surface_summary"]).read_text(encoding="utf-8"))
    assert surface["status"] == "ready"
    assert surface["implementation_status"] == "not_ready_without_approval"
    assert any(item["path"] == "core/stealth_order_manager.py" for item in surface["change_surface_files"])
    assert surface["mutation_policy"] == "read_only_no_source_mutation"


def test_workflow_router_chat_l2_change_surface_summary_handles_files_to_touch_prompt(tmp_path: Path) -> None:
    target = make_l1_expansion_repo(tmp_path)
    write_text(
        target / "core" / "order_engine.py",
        "def handle_fill(manager, placed_order_id):\n"
        "    return manager.find_stealth_order_by_placed_order_id(placed_order_id)\n",
    )
    run_command(["git", "add", "core/order_engine.py"], target)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, identify files to touch and files not to touch for a minimal safe "
                            "placed_order_id stealth lookup change. Read only and stop before implementation."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "downstream_change_surface_summary" in compact["artifacts"]
    assert "- Change surface files:" in content
    assert "- Files to touch:" in content
    assert "core/stealth_order_manager.py" in content
    assert "- Files not to touch:" in content
    assert "core/order_engine.py" in content
    assert "- Risk level:" in content
    assert "- Implementation status: not_ready_without_approval" in content
    assert "parallel_lookup_path_regression" in content
    assert "fixture_mutation_risk" in content
    assert "- Verification:" in content
    assert "grep -RInE" in content
    assert "python -m pytest tests/regression/ -v" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    surface = json.loads(Path(downstream["artifact_paths"]["change_surface_summary"]).read_text(encoding="utf-8"))
    assert surface["status"] == "ready"
    assert surface["implementation_status"] == "not_ready_without_approval"
    assert any(item["path"] == "core/stealth_order_manager.py" for item in surface["files_to_touch"])
    assert any(item["path"] == "core/order_engine.py" for item in surface["files_not_to_touch"])
    assert {item["risk"] for item in surface["risks"]} >= {
        "parallel_lookup_path_regression",
        "lookup_semantics_regression",
        "fixture_mutation_risk",
    }
    command_keys = {tuple(item["command"]) for item in surface["verification_commands"]}
    assert (
        "grep",
        "-RInE",
        "find_stealth_order_by_placed_order_id|_placed_order_index|placed_order_id",
        "core",
        "tests",
    ) in command_keys
    assert ("python", "-m", "pytest", "tests/regression/", "-v") in command_keys
    assert surface["unknowns"] == []
    assert surface["mutation_policy"] == "read_only_no_source_mutation"


def test_workflow_router_chat_l2_change_surface_summary_handles_non_git_doc_heavy_fixture(tmp_path: Path) -> None:
    target = make_l1_expansion_repo(tmp_path, initialize_git=False)
    write_text(
        target / "ID_USAGE_ANALYSIS.md",
        "\n".join(f"placed_order_id documentation reference {index}" for index in range(40)) + "\n",
    )
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, identify the minimal safe change surface for changing placed_order_id stealth lookup behavior. "
                            "Read only. Return files that would need review, related tests, risk level, gaps, and verification commands. "
                            "Stop before implementation."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "Answer:" in content
    assert "- Change surface files:" in content
    assert "core/stealth_order_manager.py" in content
    assert "non_git_text_search_fallback" in content
    assert "fallback_or_warning_present; fallback_or_warning_present" not in content
    assert sentinel.read_text(encoding="utf-8") == before
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    surface = json.loads(Path(downstream["artifact_paths"]["change_surface_summary"]).read_text(encoding="utf-8"))
    assert any(item["path"] == "core/stealth_order_manager.py" for item in surface["change_surface_files"])
    assert [item["gap"] for item in surface["gaps"]].count("non_git_text_search_fallback") == 1
    assert "fallback_or_warning_present" not in {item["gap"] for item in surface["gaps"]}
    evidence = json.loads(Path(downstream["artifact_paths"]["investigation_evidence"]).read_text(encoding="utf-8"))
    assert evidence["queries"][0] == "placed_order_id"
    assert any(match["path"] == "core/stealth_order_manager.py" for match in evidence["grep_matches"])


def test_workflow_router_chat_l2_ci_log_triage_returns_artifact(tmp_path: Path) -> None:
    target = make_l1_expansion_repo(tmp_path)
    sentinel = target / "tests" / "unit" / "test_order_id_and_followup_rules.py"
    before = sentinel.read_text(encoding="utf-8")
    ci_log = (
        "Run python -m pytest tests/unit/test_order_id_and_followup_rules.py\n"
        "FAILED tests/unit/test_order_id_and_followup_rules.py::"
        "test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - "
        "AssertionError: expected client_order_id index\n"
        "E   AssertionError: expected client_order_id index\n"
        "Error: Process completed with exit code 1.\n"
    )
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, summarize this failing CI log and identify the first failing command, "
                            "likely cause, and next local command. Read only.\n"
                            f"{ci_log}"
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "downstream_ci_failure_summary" in compact["artifacts"]
    assert "- First failing command:" in content
    assert "python -m pytest tests/unit/test_order_id_and_followup_rules.py" in content
    assert "- Likely cause:" in content
    assert "- Next local command:" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l2_ci_log_triage_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    summary = json.loads(Path(downstream["artifact_paths"]["ci_failure_summary"]).read_text(encoding="utf-8"))
    assert summary["status"] == "ready"
    assert summary["first_failing_command"]["command"] == "python -m pytest tests/unit/test_order_id_and_followup_rules.py"
    assert summary["next_local_command"]["command"][:3] == ["python", "-m", "pytest"]
    assert summary["mutation_policy"] == "read_only_no_source_mutation"


def test_workflow_router_chat_l2_table_read_write_lookup_returns_artifact(tmp_path: Path) -> None:
    target = make_l1_expansion_repo(tmp_path)
    sentinel = target / "database" / "order.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, find where database table stealth_orders is defined, read, and written. "
                            "Read only. Return definition sites, read sites, write sites, gaps, and source refs."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "downstream_table_read_write_lookup" in compact["artifacts"]
    assert "- Target table: stealth_orders" in content
    assert "- Access counts:" in content
    assert "- Definition sites:" in content
    assert "- Read sites:" in content
    assert "- Write sites:" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l2_table_read_write_lookup_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    lookup = json.loads(Path(downstream["artifact_paths"]["table_read_write_lookup"]).read_text(encoding="utf-8"))
    assert lookup["status"] == "ready"
    assert lookup["target_table"] == "stealth_orders"
    assert lookup["access_summary"]["definition_count"] >= 1
    assert lookup["access_summary"]["read_count"] >= 1
    assert lookup["access_summary"]["write_count"] >= 1
    assert lookup["mutation_policy"] == "read_only_no_source_mutation"


def test_workflow_router_chat_l2_runtime_reproduction_checklist_returns_artifact(tmp_path: Path) -> None:
    target = make_l1_expansion_repo(tmp_path)
    sentinel = target / "dashboard_server.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, turn this runtime stack trace into a minimal reproduction checklist. "
                            "Read only. Return observed error, reproduction steps, related tests, gaps, and next local command.\n"
                            "Traceback (most recent call last):\n"
                            "  File \"dashboard_server.py\", line 10, in handle_websocket_message\n"
                            "core.exceptions.WebSocketMessageError: Missing 'type' field in message"
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "downstream_reproduction_checklist" in compact["artifacts"]
    assert "- Observed error:" in content
    assert "WebSocketMessageError" in content
    assert "- Reproduction checklist:" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l2_runtime_reproduction_checklist_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    checklist = json.loads(Path(downstream["artifact_paths"]["reproduction_checklist"]).read_text(encoding="utf-8"))
    assert checklist["status"] == "ready"
    assert checklist["observed_error"]["type"] == "WebSocketMessageError"
    assert checklist["traceback_frame"]["path"] == "dashboard_server.py"
    assert len(checklist["minimal_reproduction_checklist"]) == 4
    assert checklist["mutation_policy"] == "read_only_no_source_mutation"


def test_workflow_router_chat_l2_user_facing_message_test_target_returns_artifact(tmp_path: Path) -> None:
    target = make_l1_expansion_repo(tmp_path)
    sentinel = target / "dashboard_server.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, check if error message \"Missing 'type' field in message\" is user-facing "
                            "and where it should be tested. Read only. Return source, user-facing status, test targets, "
                            "and verification command."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "downstream_message_source_lookup" in compact["artifacts"]
    assert "- Target message: Missing 'type' field in message" in content
    assert "- Sources:" in content
    assert "- User-facing:" in content
    assert "- Test targets:" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l2_user_facing_message_test_target_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    lookup = json.loads(Path(downstream["artifact_paths"]["message_source_lookup"]).read_text(encoding="utf-8"))
    assert lookup["status"] == "ready"
    assert lookup["source_count"] >= 1
    assert lookup["user_facing_assessment"]["status"] in {"unknown", "not_proven_user_facing"}
    assert lookup["user_facing_assessment"]["recommended_test_targets"]
    assert lookup["mutation_policy"] == "read_only_no_source_mutation"


def test_phase99_batch_e_mutation_prompts_do_not_match_read_only_routes() -> None:
    cases = [
        (
            "fix this failing ci log by editing the code and applying the smallest patch",
            workflow_router_plan.is_l2_ci_log_triage_request,
            "l2_ci_log_triage_terms",
        ),
        (
            "add a write path for database table stealth_orders and implement the mutation",
            workflow_router_plan.is_l2_table_read_write_lookup_request,
            "l2_table_read_write_lookup_terms",
        ),
        (
            "turn this stack trace into a fix and apply the runtime error patch",
            workflow_router_plan.is_l2_runtime_reproduction_checklist_request,
            "l2_runtime_reproduction_checklist_terms",
        ),
        (
            "update test for this user-facing error message and apply the assertion change",
            workflow_router_plan.is_l2_user_facing_message_test_target_request,
            "l2_user_facing_message_test_target_terms",
        ),
    ]

    for prompt, predicate, forbidden_rule in cases:
        lowered = prompt.lower()
        assert predicate(lowered) is False
        _workflow, _reason, evidence = workflow_router_plan.workflow_kind_for_request(prompt)
        route_rules = {item.get("rule") for item in evidence if isinstance(item, dict)}
        assert forbidden_rule not in route_rules


def test_workflow_router_chat_l1_small_text_edit_drafts_packet_without_mutation(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "docs" / "agents" / "INVARIANTS.md"
    before = sentinel.read_text(encoding="utf-8")
    anchor = "- Use `client_order_id` for internal tracking, parent/child linkage, orderbook"
    added = "- L1-010 draft proof: route small documentation edits through packet dry-run."
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeExecutionPlanningEndpoint() as endpoint:
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"In {target}, draft a small documentation edit to docs/agents/INVARIANTS.md. "
                                f"After \"{anchor}\" add \"{added}\". Do not mutate files. "
                                "Return the exact file, proposed change, safety checks, and verification command."
                            ),
                        },
                    ],
                },
            )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "execution_planning.plan"
    assert compact["summary"]["downstream_workflow"] == "execution_planning.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "small_text_edit_proposal" in compact["artifacts"]
    assert "downstream_implementation_workflow_report" in compact["artifacts"]
    assert "Draft proposal:" in content
    assert "small_text_edit_proposal" in content
    assert "docs/agents/INVARIANTS.md" in content
    assert "replace_text" in content
    assert "Verification:" in content
    assert "git diff -- docs/agents/INVARIANTS.md" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before

    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_small_text_edit_terms" for item in decision["evidence"])
    assert decision["small_text_edit"]["status"] == "ready"
    proposal = json.loads(Path(compact["artifacts"]["small_text_edit_proposal"]).read_text(encoding="utf-8"))
    assert proposal["status"] == "ready"
    assert proposal["packet_operations"] == [
        {
            "kind": "replace_text",
            "path": "docs/agents/INVARIANTS.md",
            "old": anchor,
            "new": anchor + "\n" + added,
        }
    ]
    assert any(item["check"] == "anchor_line_unique" and item["status"] == "passed" for item in proposal["safety_checks"])


def test_workflow_router_chat_l1_small_text_edit_appends_note_without_anchor(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "docs" / "agents" / "INVARIANTS.md"
    before = sentinel.read_text(encoding="utf-8")
    note = "- the stealth manager placed-order index is the authoritative lookup key."
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeExecutionPlanningEndpoint() as endpoint:
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"In {target}, draft a small documentation edit to docs/agents/INVARIANTS.md "
                                "that adds a note saying the stealth manager placed-order index is the authoritative lookup key. "
                                "Do not mutate files. Show exact proposed change and verification command."
                            ),
                        },
                    ],
                },
            )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["selected_workflow"] == "execution_planning.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "Draft proposal:" in content
    assert "append_text" in content
    assert "docs/agents/INVARIANTS.md" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before
    proposal = json.loads(Path(compact["artifacts"]["small_text_edit_proposal"]).read_text(encoding="utf-8"))
    prefix = "" if before.endswith("\n") else "\n"
    assert proposal["status"] == "ready"
    assert proposal["packet_operations"] == [
        {
            "kind": "append_text",
            "path": "docs/agents/INVARIANTS.md",
            "content": prefix + note + "\n",
        }
    ]
    assert any(item["check"] == "insert_text_absent" and item["status"] == "passed" for item in proposal["safety_checks"])


def test_workflow_router_chat_l1_small_text_edit_without_draft_requests_approval(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "docs" / "agents" / "INVARIANTS.md"
    before = sentinel.read_text(encoding="utf-8")
    anchor = "- Use `client_order_id` for internal tracking, parent/child linkage, orderbook"
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeRouterModelEndpoint("execution_planning.plan") as endpoint:
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"In {target}, make a small documentation edit to docs/agents/INVARIANTS.md. "
                            f"After \"{anchor}\" add "
                            "\"- L1-010 draft proof: route small documentation edits through packet dry-run.\"."
                            ),
                        },
                    ],
                },
            )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "execution_planning.plan"
    assert compact["summary"]["next_action"] == "request_approval"
    assert compact["summary"]["approval_state_status"] == "waiting_for_approval"
    assert compact["summary"]["approval_type"] == "packet_design"
    assert compact["summary"]["target_repo_read"] is False
    assert "approval_state" in compact["artifacts"]
    assert "downstream_result" not in compact["artifacts"]
    assert "Approval:" in content
    assert "- State: waiting_for_approval" in content
    assert "- Type: packet_design" in content
    approval_state = json.loads(Path(compact["artifacts"]["approval_state"]).read_text(encoding="utf-8"))
    assert approval_state["status"] == "waiting_for_approval"
    assert approval_state["approval_type"] == "packet_design"
    assert approval_state["expected_approval"]["status"] == "approved_for_packet_design"
    assert approval_state["next_action"] == "request_approval"
    assert sentinel.read_text(encoding="utf-8") == before


def test_workflow_router_chat_approval_continuation_current_l1_flow_consumes_source_run(
    tmp_path: Path,
) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "docs" / "agents" / "INVARIANTS.md"
    before = sentinel.read_text(encoding="utf-8")
    anchor = "- Use `client_order_id` for internal tracking, parent/child linkage, orderbook"
    note = "- Phase 97 approval continuation proof: source run identity controls packet prep."
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    packet_operations = [
        {
            "kind": "replace_text",
            "path": "docs/agents/INVARIANTS.md",
            "old": FROZEN_INVARIANT_OLD,
            "new": FROZEN_INVARIANT_NEW,
        }
    ]
    initial = handle_workflow_router_chat_completion(
        {
            "model": "agentic-workflow-router",
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"In {target}, make a small documentation edit to docs/agents/INVARIANTS.md. "
                        f"After \"{anchor}\" add \"{note}\"."
                    ),
                },
            ],
        },
        config,
    )
    source_run_id = initial["agentic_controller_response"]["run_id"]
    continuation = handle_workflow_router_chat_completion(
        {
            "model": "agentic-workflow-router",
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Approve packet design for run {source_run_id}. "
                        f"Use packet operations: {json.dumps(packet_operations, ensure_ascii=True)}"
                    ),
                }
            ],
        },
        config,
    )

    compact = continuation["agentic_controller_response"]
    content = continuation["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "execution_planning.plan"
    assert compact["summary"]["approval_state_status"] == "finished"
    assert compact["summary"]["approval_type"] == "packet_design"
    assert compact["summary"]["source_changed"] is False
    assert "Approval:" in content
    assert "- State: finished" in content
    assert "- Type: packet_design" in content
    assert "downstream_implementation_workflow_report" in compact["artifacts"]
    downstream_state = json.loads(Path(compact["artifacts"]["downstream_run_state"]).read_text(encoding="utf-8"))
    assert downstream_state["summary"]["deterministic_path"] == "approval_continuation_packet_prep"
    source_record = json.loads((config.run_registry_root / f"{source_run_id}.json").read_text(encoding="utf-8"))
    assert source_record["approval_continuation"]["status"] == "consumed"
    assert source_record["approval_continuation"]["continuation_run_id"] == compact["run_id"]
    assert sentinel.read_text(encoding="utf-8") == before


def test_workflow_router_chat_approval_continuation_rejects_target_mismatch_current_l1_flow(
    tmp_path: Path,
) -> None:
    target = make_execution_planning_tree(tmp_path)
    other_target = tmp_path / "allowed" / "other-target"
    other_target.mkdir(parents=True)
    sentinel = target / "docs" / "agents" / "INVARIANTS.md"
    before = sentinel.read_text(encoding="utf-8")
    anchor = "- Use `client_order_id` for internal tracking, parent/child linkage, orderbook"
    note = "- Phase 97 approval continuation proof: reject mismatched target roots."
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    packet_operations = [
        {
            "kind": "replace_text",
            "path": "docs/agents/INVARIANTS.md",
            "old": FROZEN_INVARIANT_OLD,
            "new": FROZEN_INVARIANT_NEW,
        }
    ]
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, initial = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, make a small documentation edit to docs/agents/INVARIANTS.md. "
                            f"After \"{anchor}\" add \"{note}\"."
                        ),
                    },
                ],
            },
        )
        assert status == 200
        source_run_id = initial["agentic_controller_response"]["run_id"]
        status, mismatch = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {other_target}, approve packet design for run {source_run_id}. "
                            f"Use packet operations: {json.dumps(packet_operations, ensure_ascii=True)}"
                        ),
                    }
                ],
            },
        )

    assert status == 409
    assert mismatch["error"]["code"] == "approval_scope_changed"
    source_record = json.loads((config.run_registry_root / f"{source_run_id}.json").read_text(encoding="utf-8"))
    assert "approval_continuation" not in source_record
    assert sentinel.read_text(encoding="utf-8") == before


def test_workflow_router_chat_approval_continuation_rejects_source_apply_scope_change(
    tmp_path: Path,
) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "docs" / "agents" / "INVARIANTS.md"
    before = sentinel.read_text(encoding="utf-8")
    anchor = "- Use `client_order_id` for internal tracking, parent/child linkage, orderbook"
    note = "- Phase 97 approval continuation proof: reject source apply scope changes."
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    packet_operations = [
        {
            "kind": "replace_text",
            "path": "docs/agents/INVARIANTS.md",
            "old": FROZEN_INVARIANT_OLD,
            "new": FROZEN_INVARIANT_NEW,
        }
    ]
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, initial = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, make a small documentation edit to docs/agents/INVARIANTS.md. "
                            f"After \"{anchor}\" add \"{note}\"."
                        ),
                    },
                ],
            },
        )
        assert status == 200
        source_run_id = initial["agentic_controller_response"]["run_id"]
        status, changed_scope = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Approve packet design for run {source_run_id} and apply the change to source now. "
                            f"Use packet operations: {json.dumps(packet_operations, ensure_ascii=True)}"
                        ),
                    }
                ],
            },
        )

    assert status == 409
    assert changed_scope["error"]["code"] == "approval_scope_changed"
    source_record = json.loads((config.run_registry_root / f"{source_run_id}.json").read_text(encoding="utf-8"))
    assert "approval_continuation" not in source_record
    assert sentinel.read_text(encoding="utf-8") == before


def test_workflow_router_chat_l1_small_unit_test_drafts_packet_without_mutation(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "tests" / "unit" / "test_order_id_and_followup_rules.py"
    sentinel.write_text(
        "from core.stealth_order_manager import StealthOrderManager\n\n"
        + sentinel.read_text(encoding="utf-8")
        + "\n\ndef test_sync_exchange_order_id_does_not_overwrite_existing_audit_id():\n"
        "    assert 'sync_exchange_order_id exchange_order_id'\n",
        encoding="utf-8",
    )
    before = sentinel.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeExecutionPlanningEndpoint() as endpoint:
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"In {target}, add a small unit test for "
                                "sync_exchange_order_id_for_placed_order setting exchange_order_id when it is missing. "
                                "Draft only. Show the proposed test file and verification command before applying."
                            ),
                        },
                    ],
                },
            )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "execution_planning.plan"
    assert compact["summary"]["downstream_workflow"] == "execution_planning.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert compact["summary"]["approval_state_status"] == "finished"
    assert compact["summary"]["approval_type"] == "packet_design"
    assert "small_unit_test_proposal" in compact["artifacts"]
    assert "downstream_implementation_workflow_report" in compact["artifacts"]
    assert "approval_state" in compact["artifacts"]
    assert "Draft proposal:" in content
    assert "Approval:" in content
    assert "- State: finished" in content
    assert "small_unit_test_proposal" in content
    assert "tests/unit/test_order_id_and_followup_rules.py" in content
    assert "append_text" in content
    assert "test_sync_exchange_order_id_sets_missing_audit_id_and_anchor_state" in content
    assert "Verification:" in content
    assert "python -m pytest tests/unit/test_order_id_and_followup_rules.py" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before

    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_small_unit_test_terms" for item in decision["evidence"])
    assert decision["small_unit_test"]["status"] == "ready"
    proposal = json.loads(Path(compact["artifacts"]["small_unit_test_proposal"]).read_text(encoding="utf-8"))
    assert proposal["status"] == "ready"
    assert proposal["packet_operations"][0]["kind"] == "append_text"
    assert proposal["packet_operations"][0]["path"] == "tests/unit/test_order_id_and_followup_rules.py"
    assert "test_sync_exchange_order_id_sets_missing_audit_id_and_anchor_state" in proposal["packet_operations"][0]["content"]
    assert any(item["check"] == "existing_related_test_file" and item["status"] == "passed" for item in proposal["safety_checks"])
    downstream_state = json.loads(Path(compact["artifacts"]["downstream_run_state"]).read_text(encoding="utf-8"))
    assert downstream_state["summary"]["deterministic_path"] == "l1_small_unit_test"
    approval_state = json.loads(Path(compact["artifacts"]["approval_state"]).read_text(encoding="utf-8"))
    assert approval_state["status"] == "finished"
    assert approval_state["approval_type"] == "packet_design"
    assert downstream_state["summary"]["repo_mutated"] is False


def test_workflow_router_chat_l1_small_unit_test_without_draft_requests_approval(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "tests" / "unit" / "test_order_id_and_followup_rules.py"
    before = sentinel.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeRouterModelEndpoint("execution_planning.plan") as endpoint:
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"In {target}, add a small unit test for "
                                "sync_exchange_order_id_for_placed_order setting exchange_order_id when it is missing."
                            ),
                        },
                    ],
                },
            )

    assert status == 200
    compact = body["agentic_controller_response"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "execution_planning.plan"
    assert compact["summary"]["next_action"] == "request_approval"
    assert compact["summary"]["target_repo_read"] is False
    assert "downstream_result" not in compact["artifacts"]
    assert sentinel.read_text(encoding="utf-8") == before


def test_workflow_router_chat_d1_config_default_test_drafts_packet_without_mutation(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    source = target / "business" / "lot_config.py"
    test_file = target / "tests" / "test_lot_tracking_integration.py"
    before_source = source.read_text(encoding="utf-8")
    before_test = test_file.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeExecutionPlanningEndpoint() as endpoint:
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"In {target}, draft a small unit test in tests/test_lot_tracking_integration.py "
                                "proving config default DEFAULT_PROFIT_MARGIN_PCT in business/lot_config.py "
                                "defaults to 0.5. Draft only. Show the proposed test file, safety checks, "
                                "and verification command before applying."
                            ),
                        },
                    ],
                },
            )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "execution_planning.plan"
    assert "Draft proposal:" in content
    assert "small_unit_test_proposal" in content
    assert "tests/test_lot_tracking_integration.py" in content
    assert "test_default_profit_margin_pct_config_default" in content
    assert "python -m pytest tests/test_lot_tracking_integration.py" in content
    assert "Source mutation: false" in content
    assert source.read_text(encoding="utf-8") == before_source
    assert test_file.read_text(encoding="utf-8") == before_test

    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "d1_config_default_test_terms" for item in decision["evidence"])
    assert decision["small_unit_test"]["status"] == "ready"
    assert decision["small_unit_test"]["subkind"] == "config_default_test"
    proposal = json.loads(Path(compact["artifacts"]["small_unit_test_proposal"]).read_text(encoding="utf-8"))
    assert proposal["status"] == "ready"
    assert proposal["subkind"] == "config_default_test"
    assert proposal["packet_operations"][0]["kind"] == "append_text"
    assert "from business.lot_config import DEFAULT_PROFIT_MARGIN_PCT" in proposal["packet_operations"][0]["content"]
    assert any(item["check"] == "config_default_assignment_found" for item in proposal["safety_checks"])


def test_workflow_router_chat_d1_message_assertion_test_drafts_packet_without_mutation(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    source = target / "core" / "orderbook.py"
    test_file = target / "tests" / "unit" / "test_orderbook_v2.py"
    before_source = source.read_text(encoding="utf-8")
    before_test = test_file.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeExecutionPlanningEndpoint() as endpoint:
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"In {target}, draft a small unit test in tests/unit/test_orderbook_v2.py "
                                "asserting exact error message \"OrderBook is read-only; refusing upsert_order()\" "
                                "from core/orderbook.py. Draft only. Show the proposed test file, safety checks, "
                                "and verification command before applying."
                            ),
                        },
                    ],
                },
            )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "execution_planning.plan"
    assert "Draft proposal:" in content
    assert "small_unit_test_proposal" in content
    assert "tests/unit/test_orderbook_v2.py" in content
    assert "test_orderbook_read_only_error_message_names_blocked_operation" in content
    assert "OrderBook is read-only; refusing upsert_order()" in content
    assert "python -m pytest tests/unit/test_orderbook_v2.py" in content
    assert "Source mutation: false" in content
    assert source.read_text(encoding="utf-8") == before_source
    assert test_file.read_text(encoding="utf-8") == before_test

    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "d1_message_assertion_test_terms" for item in decision["evidence"])
    assert decision["small_unit_test"]["status"] == "ready"
    assert decision["small_unit_test"]["subkind"] == "message_assertion_test"
    proposal = json.loads(Path(compact["artifacts"]["small_unit_test_proposal"]).read_text(encoding="utf-8"))
    assert proposal["status"] == "ready"
    assert proposal["subkind"] == "message_assertion_test"
    assert proposal["packet_operations"][0]["kind"] == "append_text"
    assert "OrderBookReadOnlyError" in proposal["packet_operations"][0]["content"]
    assert any(item["check"] == "message_template_found" for item in proposal["safety_checks"])


def test_workflow_router_chat_d1_test_assertion_update_drafts_packet_without_mutation(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    test_file = target / "tests" / "unit" / "test_order_id_and_followup_rules.py"
    old_assertion = 'assert call_kwargs["reveal_pricing_policy"] == "top_of_book"'
    new_assertion = 'assert call_kwargs["reveal_pricing_policy"] == "top_of_book"  # inherited from root parent'
    test_file.write_text(
        test_file.read_text(encoding="utf-8")
        + "\n\ndef test_create_follow_up_inherits_policy():\n"
        "    call_kwargs = {\"reveal_pricing_policy\": \"top_of_book\"}\n"
        f"    {old_assertion}\n",
        encoding="utf-8",
    )
    before = test_file.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeExecutionPlanningEndpoint() as endpoint:
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"In {target}, draft a small test assertion update in "
                                "tests/unit/test_order_id_and_followup_rules.py. Replace the assertion "
                                f"`{old_assertion}` with `{new_assertion}`. Draft only. Do not mutate files. "
                                "Show the proposed change, safety checks, and verification command."
                            ),
                        },
                    ],
                },
            )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "execution_planning.plan"
    assert "Draft proposal:" in content
    assert "small_unit_test_proposal" in content
    assert "tests/unit/test_order_id_and_followup_rules.py" in content
    assert "replace_text" in content
    assert "inherited from root parent" in content
    assert "python -m pytest tests/unit/test_order_id_and_followup_rules.py" in content
    assert "Source mutation: false" in content
    assert test_file.read_text(encoding="utf-8") == before

    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "d1_test_assertion_update_terms" for item in decision["evidence"])
    assert decision["small_unit_test"]["status"] == "ready"
    assert decision["small_unit_test"]["subkind"] == "test_assertion_update"
    proposal = json.loads(Path(compact["artifacts"]["small_unit_test_proposal"]).read_text(encoding="utf-8"))
    assert proposal["status"] == "ready"
    assert proposal["subkind"] == "test_assertion_update"
    assert proposal["packet_operations"][0]["kind"] == "replace_text"
    assert proposal["packet_operations"][0]["old"] == old_assertion
    assert proposal["packet_operations"][0]["new"] == new_assertion
    assert any(item["check"] == "old_assertion_unique" for item in proposal["safety_checks"])


def test_workflow_router_chat_l1_simple_failing_test_fix_drafts_packet_without_mutation(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    old = "            placed_order_id: The order ID placed on the exchange"
    new = "            placed_order_id: The client_order_id placed on the exchange"
    large_padding = "\n".join(f"# deterministic padding for real fixture scale {index:04d}" for index in range(2600))
    sentinel.write_text(
        "class StealthOrderManager:\n"
        "    def find_stealth_order_by_placed_order_id(self, placed_order_id):\n"
        "        \"\"\"Find stealth order that revealed the given placed_order_id.\n"
        "\n"
        "        Args:\n"
        f"{old}\n"
        "        \"\"\"\n"
        "        return self.placed_order_index_key\n"
        + large_padding
        + "\n",
        encoding="utf-8",
    )
    assert sentinel.stat().st_size > 100_000
    before = sentinel.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeExecutionPlanningEndpoint() as endpoint:
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"In {target}, inspect this failing test and propose the smallest fix. "
                                "Draft only; do not apply until approved.\n"
                                "FAILED tests/unit/test_order_id_and_followup_rules.py::"
                                "test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - "
                                "AssertionError: expected find_stealth_order_by_placed_order_id docstring to mention client_order_id"
                            ),
                        },
                    ],
                },
            )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "execution_planning.plan"
    assert compact["summary"]["downstream_workflow"] == "execution_planning.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "simple_test_fix_proposal" in compact["artifacts"]
    assert "downstream_implementation_workflow_report" in compact["artifacts"]
    assert "Draft proposal:" in content
    assert "simple_test_fix_proposal" in content
    assert "core/stealth_order_manager.py" in content
    assert "replace_text" in content
    assert "client_order_id" in content
    assert "Verification:" in content
    assert "python -m pytest tests/unit/test_order_id_and_followup_rules.py::" in content
    assert "Source mutation: false" in content
    assert sentinel.read_text(encoding="utf-8") == before

    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_simple_failing_test_fix_terms" for item in decision["evidence"])
    assert decision["simple_test_fix"]["status"] == "ready"
    proposal = json.loads(Path(compact["artifacts"]["simple_test_fix_proposal"]).read_text(encoding="utf-8"))
    assert proposal["status"] == "ready"
    assert proposal["packet_operations"] == [{"kind": "replace_text", "path": "core/stealth_order_manager.py", "old": old, "new": new}]
    assert any(item["check"] == "old_text_unique" and item["status"] == "passed" for item in proposal["safety_checks"])
    downstream_state = json.loads(Path(compact["artifacts"]["downstream_run_state"]).read_text(encoding="utf-8"))
    assert downstream_state["summary"]["deterministic_path"] == "l1_simple_failing_test_fix"
    assert downstream_state["summary"]["repo_mutated"] is False


def test_workflow_router_chat_l1_simple_failing_test_fix_without_draft_requests_approval(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeRouterModelEndpoint("execution_planning.plan") as endpoint:
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"In {target}, fix this failing test.\n"
                                "FAILED tests/unit/test_order_id_and_followup_rules.py::"
                                "test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - "
                                "AssertionError: expected find_stealth_order_by_placed_order_id docstring to mention client_order_id"
                            ),
                        },
                    ],
                },
            )

    assert status == 200
    compact = body["agentic_controller_response"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "execution_planning.plan"
    assert compact["summary"]["next_action"] == "request_approval"
    assert compact["summary"]["target_repo_read"] is False
    assert "downstream_result" not in compact["artifacts"]
    assert sentinel.read_text(encoding="utf-8") == before


def test_workflow_router_chat_approved_investigation_packet_prep_uses_generic_seed(
    tmp_path: Path,
) -> None:
    target = make_execution_planning_tree(tmp_path)
    source = target / "core" / "stealth_order_manager.py"
    write_text(
        source,
        "class StealthOrderManager:\n"
        "    placed_order_id_lookup = 'client_order_id index'\n",
    )
    before = source.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, initial = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, identify the minimal safe change surface for "
                            "placed_order_id_lookup. Read only. Return files that would need review, "
                            "related tests, risks, and verification commands. Stop before implementation."
                        ),
                    }
                ],
            },
        )
        assert status == 200
        initial_compact = initial["agentic_controller_response"]
        assert initial_compact["summary"]["selected_workflow"] == "code_investigation.plan"
        assert initial_compact["summary"]["downstream_status"] == "completed"
        assert "downstream_investigation_plan" in initial_compact["artifacts"]
        initial_run_id = initial_compact["run_id"]

        with FakeExecutionPlanningEndpoint() as endpoint:
            status, followup = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"For run {initial_run_id}, approved investigation. Implementation objective: "
                                "add a placed_order_lookup_path marker beside placed_order_id_lookup in "
                                "core/stealth_order_manager.py. Prepare exact packet operations for "
                                "implementation prep. Draft only; do not mutate files."
                            ),
                        }
                    ],
                },
            )

    assert status == 200
    compact = followup["agentic_controller_response"]
    content = followup["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "execution_planning.plan"
    assert compact["summary"]["downstream_workflow"] == "execution_planning.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "packet_operation_proposal" in compact["artifacts"]
    assert "downstream_implementation_workflow_report" in compact["artifacts"]
    assert "Draft proposal:" in content
    assert "Source mutation: false" in content
    assert source.read_text(encoding="utf-8") == before

    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["packet_objective"]["status"] == "accepted"
    assert decision["packet_operation_proposal"]["source_artifact_key"] == "downstream_investigation_plan"
    proposal = json.loads(Path(compact["artifacts"]["packet_operation_proposal"]).read_text(encoding="utf-8"))
    assert proposal["status"] == "ready"
    assert proposal["source_artifact_key"] == "downstream_investigation_plan"
    assert proposal["packet_operations"] == [
        {
            "kind": "replace_text",
            "path": "core/stealth_order_manager.py",
            "old": "    placed_order_id_lookup = 'client_order_id index'",
            "new": (
                "    placed_order_id_lookup = 'client_order_id index'\n"
                "    placed_order_lookup_path = 'single manager index'"
            ),
        }
    ]
    proposal_request = json.loads(
        Path(compact["artifacts"]["packet_operation_proposal_request"]).read_text(encoding="utf-8")
    )
    assert proposal_request["source_artifact_key"] == "downstream_investigation_plan"


def test_workflow_router_chat_l1_related_tests_returns_test_commands(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, find tests related to placed_order_id stealth lookup. "
                            "Read only. Return test files, matching terms, and recommended test commands."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert compact["summary"]["verification_command_count"] >= 1
    assert "Answer:" in content
    assert "- Related tests:" in content
    assert "tests/unit/test_order_id_and_followup_rules.py" in content
    assert "- Recommended commands:" in content
    assert "python -m pytest tests/unit/test_order_id_and_followup_rules.py" in content
    assert sentinel.read_text(encoding="utf-8") == before
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    investigation_plan = json.loads(Path(downstream["artifact_paths"]["investigation_plan"]).read_text(encoding="utf-8"))
    assert any(item["path"].startswith("tests/") for item in investigation_plan["related_tests"])
    commands = [item["command"] for item in investigation_plan["verification_plan"]["verification_commands"]]
    assert ["python", "-m", "pytest", "tests/unit/test_order_id_and_followup_rules.py"] in commands


def test_workflow_router_chat_l1_safe_test_command_returns_bounded_command(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, recommend the smallest test command for placed_order_id stealth lookup. "
                            "Read only. Explain why that command is relevant."
                        ),
                    },
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert compact["summary"]["verification_command_count"] >= 1
    assert "Answer:" in content
    assert "- Recommended commands:" in content
    assert "python -m pytest tests/unit/test_order_id_and_followup_rules.py" in content
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_safe_test_command_terms" for item in decision["evidence"])
    downstream = json.loads(Path(compact["artifacts"]["downstream_result"]).read_text(encoding="utf-8"))
    investigation_plan = json.loads(Path(downstream["artifact_paths"]["investigation_plan"]).read_text(encoding="utf-8"))
    commands = [item["command"] for item in investigation_plan["verification_plan"]["verification_commands"]]
    assert ["python", "-m", "pytest", "tests/unit/test_order_id_and_followup_rules.py"] in commands
    assert all(command[:3] == ["python", "-m", "pytest"] and len(command) == 4 for command in commands)


def test_workflow_router_chat_streams_final_response_for_anythingllm_ui(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, text, headers = request_raw(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "stream": True,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, find where the placed_order_id stealth lookup begins. "
                            "Read only. Return the entrypoint, evidence files, related tests, and confidence."
                        ),
                    }
                ],
            },
        )

    assert status == 200
    assert headers["Content-Type"].startswith("text/event-stream")
    events = []
    for block in text.strip().split("\n\n"):
        assert block.startswith("data: ")
        payload = block[len("data: ") :]
        events.append(payload if payload == "[DONE]" else json.loads(payload))
    assert events[-1] == "[DONE]"
    first = events[0]
    assert first["object"] == "chat.completion.chunk"
    assert "workflow_router.plan completed" in first["choices"][0]["delta"]["content"]
    compact = first["agentic_controller_response"]
    assert compact["workflow"] == "workflow_router.plan"
    assert compact["status"] == "completed"
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "route_decision" in compact["artifacts"]
    assert sentinel.read_text(encoding="utf-8") == before


def test_workflow_router_chat_streams_json_response_format_for_anythingllm_ui(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, text, headers = request_raw(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "stream": True,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, find where the placed_order_id stealth lookup begins. "
                            "Read only. Return the entrypoint, evidence files, related tests, and confidence."
                        ),
                    }
                ],
            },
        )

    assert status == 200
    assert headers["Content-Type"].startswith("text/event-stream")
    first_payload = text.strip().split("\n\n")[0]
    assert first_payload.startswith("data: ")
    first = json.loads(first_payload[len("data: ") :])
    compact = first["agentic_controller_response"]
    assert compact["output_format"] == "json"
    rendered = json.loads(first["choices"][0]["delta"]["content"])
    assert rendered["output_format"] == "json"
    assert rendered["summary"]["selected_workflow"] == "code_investigation.plan"
    assert sentinel.read_text(encoding="utf-8") == before


def test_workflow_router_chat_guides_natural_language_without_target_path(tmp_path: Path) -> None:
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [{"role": "user", "content": "Find where the placed_order_id stealth lookup begins."}],
            },
        )

    assert status == 200
    content = body["choices"][0]["message"]["content"]
    assert "missing_target_root_for_coding_request" in content
    assert "Selected workflow: none" in content
    assert "I did not start a repository workflow" in content
    assert body["agentic_controller_response"]["summary"]["selected_workflow"] == "none"


@advanced_workflow
def test_workflow_router_chat_approval_continuation_blocks_without_packet_operations(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, refactor the placed_order_id stealth lookup so there is only one code path. "
                            "Start from the logic beginning point and investigate first."
                        ),
                    }
                ],
            },
        )
        assert status == 200
        run_id = body["agentic_controller_response"]["run_id"]
        status, continuation = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": f"Approve packet design for run {run_id}. Proceed with implementation prep.",
                    }
                ],
            },
        )

    assert status == 200
    compact = continuation["agentic_controller_response"]
    assert compact["workflow"] == "workflow_router.plan"
    assert compact["summary"]["route_status"] == "blocked"
    assert compact["summary"]["selected_workflow"] == "execution_planning.plan"
    assert compact["summary"]["target_root"] == str(target.resolve())
    assert "downstream_result" not in compact["artifacts"]
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(blocker["reason"] == "missing_packet_operations" for blocker in decision["blockers"])


@advanced_workflow
def test_workflow_router_chat_approval_continuation_runs_implementation_prep_with_packet_operations(
    tmp_path: Path,
) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "docs" / "agents" / "INVARIANTS.md"
    before = sentinel.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeExecutionPlanningEndpoint() as endpoint:
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"In {target}, refactor the placed_order_id stealth lookup so there is only one code path. "
                                "Start from the logic beginning point and investigate first."
                            ),
                        }
                    ],
                },
            )
            assert status == 200
            run_id = body["agentic_controller_response"]["run_id"]
            packet_operations = [
                {
                    "kind": "replace_text",
                    "path": "docs/agents/INVARIANTS.md",
                    "old": FROZEN_INVARIANT_OLD,
                    "new": FROZEN_INVARIANT_NEW,
                }
            ]
            status, continuation = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"Approve packet design for run {run_id}. "
                                f"Use packet operations: {json.dumps(packet_operations, ensure_ascii=True)}"
                            ),
                        }
                    ],
                },
            )

    assert status == 200
    compact = continuation["agentic_controller_response"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "execution_planning.plan"
    assert compact["summary"]["downstream_workflow"] == "execution_planning.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "downstream_implementation_workflow_report" in compact["artifacts"]
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["controller_request_preview"]["packet_operations"] == packet_operations


@advanced_workflow
def test_workflow_router_chat_approval_continuation_rejects_duplicate_approval(
    tmp_path: Path,
) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "docs" / "agents" / "INVARIANTS.md"
    before = sentinel.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeExecutionPlanningEndpoint() as endpoint:
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, initial = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"In {target}, refactor the placed_order_id stealth lookup so there is only one code path. "
                                "Start from the logic beginning point and investigate first."
                            ),
                        }
                    ],
                },
            )
            assert status == 200
            run_id = initial["agentic_controller_response"]["run_id"]
            packet_operations = [
                {
                    "kind": "replace_text",
                    "path": "docs/agents/INVARIANTS.md",
                    "old": FROZEN_INVARIANT_OLD,
                    "new": FROZEN_INVARIANT_NEW,
                }
            ]
            approval_message = (
                f"Approve packet design for run {run_id}. "
                f"Use packet operations: {json.dumps(packet_operations, ensure_ascii=True)}"
            )
            status, continuation = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [{"role": "user", "content": approval_message}],
                },
            )
            assert status == 200
            status, duplicate = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [{"role": "user", "content": approval_message}],
                },
            )

    assert continuation["agentic_controller_response"]["summary"]["approval_state_status"] == "finished"
    assert status == 409
    assert duplicate["error"]["code"] == "approval_already_consumed"
    source_record = json.loads((config.run_registry_root / f"{run_id}.json").read_text(encoding="utf-8"))
    assert source_record["approval_continuation"]["status"] == "consumed"
    assert sentinel.read_text(encoding="utf-8") == before


@advanced_workflow
def test_workflow_router_chat_approval_continuation_rejects_denied_approval(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, initial = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, refactor the placed_order_id stealth lookup so there is only one code path. "
                            "Start from the logic beginning point and investigate first."
                        ),
                    }
                ],
            },
        )
        assert status == 200
        run_id = initial["agentic_controller_response"]["run_id"]
        status, denied = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [{"role": "user", "content": f"Deny packet design approval for run {run_id}."}],
            },
        )
        status_after_deny, retry = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [{"role": "user", "content": f"Approve packet design for run {run_id}."}],
            },
        )

    assert status == 409
    assert denied["error"]["code"] == "approval_denied"
    assert status_after_deny == 409
    assert retry["error"]["code"] == "approval_denied"
    source_record = json.loads((config.run_registry_root / f"{run_id}.json").read_text(encoding="utf-8"))
    assert source_record["approval_continuation"]["status"] == "denied"


@advanced_workflow
def test_workflow_router_chat_approval_continuation_rejects_expired_approval(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, initial = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, refactor the placed_order_id stealth lookup so there is only one code path. "
                            "Start from the logic beginning point and investigate first."
                        ),
                    }
                ],
            },
        )
        assert status == 200
        run_id = initial["agentic_controller_response"]["run_id"]
        record_path = config.run_registry_root / f"{run_id}.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["updated_at"] = "2000-01-01T00:00:00Z"
        record_path.write_text(json.dumps(record, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        status, expired = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [{"role": "user", "content": f"Approve packet design for run {run_id}."}],
            },
        )

    assert status == 409
    assert expired["error"]["code"] == "approval_expired"


@advanced_workflow
def test_workflow_router_chat_approval_continuation_rejects_wrong_run_state(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, initial = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, find tests related to placed_order_id stealth lookup. "
                            "Read only. Return test files, matching terms, and recommended test commands."
                        ),
                    }
                ],
            },
        )
        assert status == 200
        run_id = initial["agentic_controller_response"]["run_id"]
        status, wrong_run = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [{"role": "user", "content": f"Approve packet design for run {run_id}."}],
            },
        )

    assert status == 409
    assert wrong_run["error"]["code"] == "approval_not_pending"


@advanced_workflow
def test_workflow_router_chat_approval_continuation_can_generate_packet_operations_from_prior_run(
    tmp_path: Path,
) -> None:
    target = make_execution_planning_tree(tmp_path)
    source = target / "core" / "stealth_order_manager.py"
    write_text(
        source,
        "class StealthOrderManager:\n"
        "    stealth_order_id = 'client_order_id'\n"
        "    placed_order_id_lookup = 'client_order_id index'\n",
    )
    before = source.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeExecutionPlanningEndpoint() as endpoint:
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"In {target}, refactor the placed_order_id stealth lookup so there is only one code path. "
                                "Start from the logic beginning point and investigate first."
                            ),
                        }
                    ],
                },
            )
            assert status == 200
            run_id = body["agentic_controller_response"]["run_id"]
            status, continuation = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Approve packet design for run {run_id}. Proceed with implementation prep.",
                        }
                    ],
                },
            )

    assert status == 200
    compact = continuation["agentic_controller_response"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "execution_planning.plan"
    assert compact["summary"]["downstream_workflow"] == "execution_planning.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "packet_operation_proposal" in compact["artifacts"]
    assert "downstream_implementation_workflow_report" in compact["artifacts"]
    assert source.read_text(encoding="utf-8") == before
    proposal = json.loads(Path(compact["artifacts"]["packet_operation_proposal"]).read_text(encoding="utf-8"))
    assert proposal["status"] == "ready"
    assert proposal["packet_operations"] == [
        {
            "kind": "replace_text",
            "path": "core/stealth_order_manager.py",
            "old": "    placed_order_id_lookup = 'client_order_id index'",
            "new": (
                "    placed_order_id_lookup = 'client_order_id index'\n"
                "    placed_order_lookup_path = 'single manager index'"
            ),
        }
    ]


@advanced_workflow
def test_workflow_router_chat_generated_packet_block_requests_packet_objective(
    tmp_path: Path,
) -> None:
    target = make_execution_planning_tree(tmp_path)
    source = target / "core" / "stealth_order_manager.py"
    write_text(
        source,
        "class StealthOrderManager:\n"
        "    stealth_order_id = 'client_order_id'\n"
        "    placed_order_id_lookup = 'client_order_id index'\n",
    )
    before = source.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    empty_proposal = {
        "packet_operations": [],
        "blockers": [{"reason": "No isolated replacement is safe from the supplied snippets."}],
        "rationale": "The investigation is not specific enough to select an authoritative path.",
    }
    with FakeExecutionPlanningEndpoint(packet_operation_proposal_response=empty_proposal) as endpoint:
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"In {target}, refactor the placed_order_id stealth lookup so there is only one code path. "
                                "Start from the logic beginning point and investigate first."
                            ),
                        }
                    ],
                },
            )
            assert status == 200
            run_id = body["agentic_controller_response"]["run_id"]
            status, continuation = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Approve packet design for run {run_id}. Proceed with implementation prep.",
                        }
                    ],
                },
            )

    assert status == 200
    compact = continuation["agentic_controller_response"]
    assert compact["summary"]["route_status"] == "blocked"
    assert compact["summary"]["selected_workflow"] == "execution_planning.plan"
    assert compact["summary"]["next_action"] == "request_packet_objective"
    assert "packet_operation_proposal" in compact["artifacts"]
    assert "downstream_implementation_workflow_report" not in compact["artifacts"]
    assert source.read_text(encoding="utf-8") == before
    proposal = json.loads(Path(compact["artifacts"]["packet_operation_proposal"]).read_text(encoding="utf-8"))
    assert proposal["status"] == "blocked"
    assert proposal["model_blockers"] == empty_proposal["blockers"]
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["next_action"] == "request_packet_objective"
    clarification = decision["packet_objective_clarification"]
    assert clarification["status"] == "needs_packet_objective"
    assert "Which concrete behavior should change?" in clarification["questions"]


@advanced_workflow
def test_workflow_router_chat_packet_objective_followup_generates_dry_run(
    tmp_path: Path,
) -> None:
    target = make_execution_planning_tree(tmp_path)
    source = target / "core" / "stealth_order_manager.py"
    write_text(
        source,
        "class StealthOrderManager:\n"
        "    stealth_order_id = 'client_order_id'\n"
        "    placed_order_id_lookup = 'client_order_id index'\n",
    )
    before = source.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    empty_proposal = {
        "packet_operations": [],
        "blockers": [{"reason": "No isolated replacement is safe from the supplied snippets."}],
        "rationale": "The investigation is not specific enough to select an authoritative path.",
    }
    objective_text = (
        "make core/stealth_order_manager.py the authoritative placed_order_id lookup path "
        "and add a draft-only marker for the single manager index"
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        with FakeExecutionPlanningEndpoint(packet_operation_proposal_response=empty_proposal) as endpoint:
            status, initial = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"In {target}, refactor the placed_order_id stealth lookup so there is only one code path. "
                                "Start from the logic beginning point and investigate first."
                            ),
                        }
                    ],
                },
            )
            assert status == 200
            initial_run_id = initial["agentic_controller_response"]["run_id"]
            status, blocked = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Approve packet design for run {initial_run_id}. Proceed with implementation prep.",
                        }
                    ],
                },
            )
        assert status == 200
        blocked_run_id = blocked["agentic_controller_response"]["run_id"]
        with FakeExecutionPlanningEndpoint() as endpoint:
            status, objective = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"For run {blocked_run_id}, packet objective: {objective_text}. Draft only.",
                        }
                    ],
                },
            )

    assert status == 200
    compact = objective["agentic_controller_response"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "execution_planning.plan"
    assert compact["summary"]["downstream_workflow"] == "execution_planning.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "packet_operation_proposal" in compact["artifacts"]
    assert "downstream_implementation_workflow_report" in compact["artifacts"]
    assert source.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["packet_objective"]["status"] == "accepted"
    assert objective_text in decision["packet_objective"]["objective"]
    assert decision["packet_operation_proposal"]["approved_run_id"] == initial_run_id
    proposal_request = json.loads(
        Path(compact["artifacts"]["packet_operation_proposal_request"]).read_text(encoding="utf-8")
    )
    assert objective_text in proposal_request["packet_objective"]


@advanced_workflow
def test_workflow_router_chat_packet_objective_followup_records_no_change_needed(
    tmp_path: Path,
) -> None:
    target = make_execution_planning_tree(tmp_path)
    source = target / "core" / "stealth_order_manager.py"
    write_text(
        source,
        "class StealthOrderManager:\n"
        "    def __init__(self):\n"
        "        self._placed_order_index = {}\n"
        "\n"
        "    def find_stealth_order_by_placed_order_id(self, placed_order_id):\n"
        "        return self._placed_order_index.get(placed_order_id)\n"
        "\n"
        "    def record_reveal(self, placed_order_id, order):\n"
        "        self._placed_order_index[placed_order_id] = order\n",
    )
    before = source.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    empty_proposal = {
        "packet_operations": [],
        "blockers": [{"reason": "No isolated replacement is safe from the supplied snippets."}],
        "rationale": "The investigation is not specific enough to select an authoritative path.",
    }
    no_change_proposal = {
        "packet_operations": [
            {
                "kind": "replace_text",
                "path": "core/stealth_order_manager.py",
                "old": "        self._placed_order_index[placed_order_id] = order",
                "new": "        self._placed_order_index[placed_order_id] = order",
            }
        ],
        "blockers": [
            {
                "reason": (
                    "core/stealth_order_manager.py is already the authoritative "
                    "placed_order_id lookup path; no changes are required."
                )
            }
        ],
        "rationale": "No replacement operations are needed because the manager already owns the index.",
    }
    with RunningControllerService(config) as service:
        host, port = service.base_url
        with FakeExecutionPlanningEndpoint(packet_operation_proposal_response=empty_proposal) as endpoint:
            status, initial = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"In {target}, refactor the placed_order_id stealth lookup so there is only one code path. "
                                "Start from the logic beginning point and investigate first."
                            ),
                        }
                    ],
                },
            )
            assert status == 200
            initial_run_id = initial["agentic_controller_response"]["run_id"]
            status, blocked = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Approve packet design for run {initial_run_id}. Proceed with implementation prep.",
                        }
                    ],
                },
            )
        assert status == 200
        blocked_run_id = blocked["agentic_controller_response"]["run_id"]
        with FakeExecutionPlanningEndpoint(packet_operation_proposal_response=no_change_proposal) as endpoint:
            status, objective = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"For run {blocked_run_id}, packet objective: make core/stealth_order_manager.py "
                                "the authoritative placed_order_id lookup path. Draft only."
                            ),
                        }
                    ],
                },
            )

    assert status == 200
    compact = objective["agentic_controller_response"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["next_action"] == "none"
    assert compact["summary"]["packet_objective_outcome_status"] == "no_change_needed"
    assert "downstream_implementation_workflow_report" not in compact["artifacts"]
    assert source.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    outcome = decision["packet_objective_outcome"]
    assert outcome["status"] == "no_change_needed"
    assert outcome["proposal_validation_failures"] == {"noop_operation": 1}
    assert outcome["evidence_refs"]
    assert isinstance(outcome["verification_commands"], list)
    proposal = json.loads(Path(compact["artifacts"]["packet_operation_proposal"]).read_text(encoding="utf-8"))
    assert proposal["status"] == "not_required"
    assert proposal["packet_objective_outcome"]["status"] == "no_change_needed"


@advanced_workflow
def test_workflow_router_chat_packet_objective_followup_noop_without_evidence_requests_narrowed_objective(
    tmp_path: Path,
) -> None:
    target = make_execution_planning_tree(tmp_path)
    source = target / "core" / "stealth_order_manager.py"
    write_text(
        source,
        "class StealthOrderManager:\n"
        "    placed_order_id_lookup = 'client_order_id index'\n",
    )
    before = source.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    empty_proposal = {
        "packet_operations": [],
        "blockers": [{"reason": "No isolated replacement is safe from the supplied snippets."}],
        "rationale": "The investigation is not specific enough to select an authoritative path.",
    }
    unsupported_noop = {
        "packet_operations": [
            {
                "kind": "replace_text",
                "path": "core/stealth_order_manager.py",
                "old": "    placed_order_id_lookup = 'client_order_id index'",
                "new": "    placed_order_id_lookup = 'client_order_id index'",
            }
        ],
        "blockers": [{"reason": "core/missing_lookup.py is already authoritative; no changes are required."}],
        "rationale": "No changes are required.",
    }
    with RunningControllerService(config) as service:
        host, port = service.base_url
        with FakeExecutionPlanningEndpoint(packet_operation_proposal_response=empty_proposal) as endpoint:
            status, initial = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"In {target}, refactor the placed_order_id stealth lookup so there is only one code path. "
                                "Start from the logic beginning point and investigate first."
                            ),
                        }
                    ],
                },
            )
            assert status == 200
            initial_run_id = initial["agentic_controller_response"]["run_id"]
            status, blocked = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Approve packet design for run {initial_run_id}. Proceed with implementation prep.",
                        }
                    ],
                },
            )
        assert status == 200
        blocked_run_id = blocked["agentic_controller_response"]["run_id"]
        with FakeExecutionPlanningEndpoint(packet_operation_proposal_response=unsupported_noop) as endpoint:
            status, objective = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"For run {blocked_run_id}, packet objective: make core/missing_lookup.py "
                                "the authoritative placed_order_id lookup path. Draft only."
                            ),
                        }
                    ],
                },
            )

    assert status == 200
    compact = objective["agentic_controller_response"]
    assert compact["summary"]["route_status"] == "blocked"
    assert compact["summary"]["next_action"] == "request_narrowed_edit_objective"
    assert compact["summary"]["packet_objective_outcome_status"] == "needs_narrowed_edit_objective"
    assert "downstream_implementation_workflow_report" not in compact["artifacts"]
    assert source.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    outcome = decision["packet_objective_outcome"]
    assert outcome["status"] == "needs_narrowed_edit_objective"
    assert outcome["proposal_validation_failures"] == {"noop_operation": 1}
    assert outcome["evidence_refs"] == []


@advanced_workflow
def test_workflow_router_chat_narrowed_edit_followup_generates_dry_run(
    tmp_path: Path,
) -> None:
    target = make_execution_planning_tree(tmp_path)
    source = target / "core" / "stealth_order_manager.py"
    write_text(
        source,
        "class StealthOrderManager:\n"
        "    placed_order_id_lookup = 'client_order_id index'\n",
    )
    before = source.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    empty_proposal = {
        "packet_operations": [],
        "blockers": [{"reason": "No isolated replacement is safe from the supplied snippets."}],
        "rationale": "The investigation is not specific enough to select an authoritative path.",
    }
    unsupported_noop = {
        "packet_operations": [
            {
                "kind": "replace_text",
                "path": "core/stealth_order_manager.py",
                "old": "    placed_order_id_lookup = 'client_order_id index'",
                "new": "    placed_order_id_lookup = 'client_order_id index'",
            }
        ],
        "blockers": [{"reason": "core/missing_lookup.py is already authoritative; no changes are required."}],
        "rationale": "No changes are required.",
    }
    packet_objective = "make core/missing_lookup.py the authoritative placed_order_id lookup path"
    narrowed_objective = (
        "change core/stealth_order_manager.py by adding a placed_order_lookup_path marker "
        "beside placed_order_id_lookup for all order_engine callers"
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        with FakeExecutionPlanningEndpoint(packet_operation_proposal_response=empty_proposal) as endpoint:
            status, initial = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"In {target}, refactor the placed_order_id stealth lookup so there is only one code path. "
                                "Start from the logic beginning point and investigate first."
                            ),
                        }
                    ],
                },
            )
            assert status == 200
            initial_run_id = initial["agentic_controller_response"]["run_id"]
            status, blocked = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Approve packet design for run {initial_run_id}. Proceed with implementation prep.",
                        }
                    ],
                },
            )
        assert status == 200
        blocked_run_id = blocked["agentic_controller_response"]["run_id"]
        with FakeExecutionPlanningEndpoint(packet_operation_proposal_response=unsupported_noop) as endpoint:
            status, packet_response = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"For run {blocked_run_id}, packet objective: {packet_objective}. Draft only.",
                        }
                    ],
                },
            )
        assert status == 200
        packet_run_id = packet_response["agentic_controller_response"]["run_id"]
        packet_summary = packet_response["agentic_controller_response"]["summary"]
        assert packet_summary["next_action"] == "request_narrowed_edit_objective"
        with FakeExecutionPlanningEndpoint() as endpoint:
            status, narrowed = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"For run {packet_run_id}, narrowed edit objective: {narrowed_objective}. Draft only.",
                        }
                    ],
                },
            )

    assert status == 200
    compact = narrowed["agentic_controller_response"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "execution_planning.plan"
    assert compact["summary"]["downstream_workflow"] == "execution_planning.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert compact["summary"]["narrowed_edit_objective_status"] == "accepted"
    assert "packet_operation_proposal" in compact["artifacts"]
    assert "downstream_implementation_workflow_report" in compact["artifacts"]
    assert source.read_text(encoding="utf-8") == before
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["packet_objective"]["objective"].startswith(packet_objective)
    assert decision["narrowed_edit_objective"] == {
        "status": "accepted",
        "objective": f"{narrowed_objective}. Draft only.",
    }
    assert decision["packet_operation_proposal"]["approved_run_id"] == initial_run_id
    proposal_request = json.loads(
        Path(compact["artifacts"]["packet_operation_proposal_request"]).read_text(encoding="utf-8")
    )
    assert proposal_request["packet_objective"].startswith(packet_objective)
    assert narrowed_objective in proposal_request["narrowed_edit_objective"]


@advanced_workflow
def test_workflow_router_chat_natural_feedback_links_initial_and_continuation_runs(
    tmp_path: Path,
) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "docs" / "agents" / "INVARIANTS.md"
    before = sentinel.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeExecutionPlanningEndpoint() as endpoint:
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, initial = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"In {target}, refactor the placed_order_id stealth lookup so there is only one code path. "
                                "Start from the logic beginning point and investigate first."
                            ),
                        }
                    ],
                },
            )
            assert status == 200
            initial_run_id = initial["agentic_controller_response"]["run_id"]
            packet_operations = [
                {
                    "kind": "replace_text",
                    "path": "docs/agents/INVARIANTS.md",
                    "old": FROZEN_INVARIANT_OLD,
                    "new": FROZEN_INVARIANT_NEW,
                }
            ]
            status, continuation = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "role_base_url": endpoint.base_url,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"Approve packet design for run {initial_run_id}. "
                                f"Use packet operations: {json.dumps(packet_operations, ensure_ascii=True)}"
                            ),
                        }
                    ],
                },
            )
            assert status == 200
            continuation_run_id = continuation["agentic_controller_response"]["run_id"]
            status, feedback = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/chat/completions",
                {
                    "model": "agentic-workflow-router",
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"Record feedback for original run {initial_run_id} and continuation run "
                                f"{continuation_run_id}: useful: the route returned artifacts. "
                                "missing: generate exact packet operations automatically from the approved investigation."
                            ),
                        }
                    ],
                },
            )

    assert status == 200
    compact = feedback["agentic_controller_response"]
    assert compact["workflow"] == "workflow_feedback.record"
    assert compact["status"] == "completed"
    assert compact["summary"]["target_workflow"] == "workflow_router.plan"
    assert compact["summary"]["target_run_id"] == continuation_run_id
    assert compact["summary"]["target_root"] == str(target.resolve())
    assert compact["summary"]["linked_run_found"] is True
    assert compact["summary"]["feedback_counts"]["useful"] == 1
    assert compact["summary"]["feedback_counts"]["missing"] == 1
    assert "feedback_record" in compact["artifacts"]
    record = json.loads(Path(compact["artifacts"]["feedback_record"]).read_text(encoding="utf-8"))
    assert record["artifact_refs"]["mentioned_run_ids"] == [initial_run_id, continuation_run_id]
    assert record["artifact_refs"]["related_run_ids"] == [initial_run_id]
    assert sentinel.read_text(encoding="utf-8") == before


def test_workflow_router_chat_natural_feedback_records_route_skill_and_next_action(
    tmp_path: Path,
) -> None:
    target = make_l1_expansion_repo(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, initial = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, explain what find_stealth_order_by_placed_order_id does in "
                            "core/stealth_order_manager.py. Read only. Include key inputs, outputs, side effects, and tests."
                        ),
                    }
                ],
            },
        )
        assert status == 200
        initial_run_id = initial["agentic_controller_response"]["run_id"]
        status, feedback = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Record feedback for run {initial_run_id}: wrong: the answer missed one side effect. "
                            "missing: include the related test name. confusing: the artifact list was too prominent."
                        ),
                    }
                ],
            },
        )

    assert status == 200
    compact = feedback["agentic_controller_response"]
    assert compact["workflow"] == "workflow_feedback.record"
    assert compact["summary"]["target_run_id"] == initial_run_id
    assert compact["summary"]["classifications"] == ["wrong", "missing", "confusing"]
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert "code-explanation-summarizer" in compact["summary"]["selected_skills"]
    assert compact["summary"]["semantic_status"] == "completed_no_failures"
    assert compact["summary"]["next_action"]["kind"] == "semantic_gate_update"
    assert compact["summary"]["next_action"]["target_skill"] == "code-explanation-summarizer"
    record = json.loads(Path(compact["artifacts"]["feedback_record"]).read_text(encoding="utf-8"))
    assert record["feedback_context"]["route_rules"] == ["l1_explain_code_terms"]
    assert "route_decision" in record["feedback_context"]["artifact_keys"]
    assert "code_explanation" in record["feedback_context"]["downstream_artifact_keys"]
    assert record["feedback_context"]["prompt_case_status"] == "unknown"
    assert record["next_action"]["mutation_policy"] == "controller_artifacts_only"
    assert record["governed_decision"]["kind"] == "repair_followup"
    assert record["governed_decision"]["target_run_id"] == initial_run_id
    assert record["governed_decision"]["feedback_run_id"] == compact["run_id"]
    assert sentinel.read_text(encoding="utf-8") == before


def test_prompt_case_id_from_feedback_text_strips_sentence_punctuation() -> None:
    assert (
        prompt_case_id_from_text("Record feedback for run workflow-router-test. prompt case: FL125-001.")
        == "FL125-001"
    )
    assert prompt_case_id_from_text("case_id: FL125-002; useful: clear") == "FL125-002"


def test_workflow_router_chat_natural_feedback_missing_none_stays_positive(
    tmp_path: Path,
) -> None:
    target = make_l1_expansion_repo(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, initial = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, explain what find_stealth_order_by_placed_order_id does in "
                            "core/stealth_order_manager.py. Read only. Include key inputs, outputs, side effects, and tests."
                        ),
                    }
                ],
            },
        )
        assert status == 200
        initial_run_id = initial["agentic_controller_response"]["run_id"]
        status, feedback = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Record feedback for run {initial_run_id}: useful: inline answer was chat visible. "
                            "missing: none for V1 acceptance."
                        ),
                    }
                ],
            },
        )

    assert status == 200
    compact = feedback["agentic_controller_response"]
    assert compact["workflow"] == "workflow_feedback.record"
    assert compact["summary"]["target_run_id"] == initial_run_id
    assert compact["summary"]["feedback_counts"]["useful"] == 1
    assert compact["summary"]["feedback_counts"]["missing"] == 0
    assert compact["summary"]["classifications"] == ["useful"]
    assert compact["summary"]["next_action"]["kind"] == "keep_current_route"
    record = json.loads(Path(compact["artifacts"]["feedback_record"]).read_text(encoding="utf-8"))
    assert record["feedback"]["missing"] == []
    assert sentinel.read_text(encoding="utf-8") == before


def test_workflow_router_plan_routes_l1_behavior_start_without_repo_reads(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "In this repo, find where the placed_order_id stealth lookup begins. "
                    "Read only. Return the entrypoint, evidence files, related tests, and confidence."
                ),
                "mode": "plan_only",
            },
        )

    assert status == 200
    assert body["workflow"] == "workflow_router.plan"
    assert body["status"] == "completed"
    assert body["summary"]["route_status"] == "ready"
    assert body["summary"]["selected_workflow"] == "code_investigation.plan"
    assert body["summary"]["next_action"] == "execute_read_only"
    assert body["summary"]["target_repo_read"] is False
    assert body["tool_policy"]["controller_tool_ids"] == []
    assert body["tool_policy"]["model_visible_tool_ids"] == []

    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["status"] == "ready"
    assert decision["selected_workflow"] == "code_investigation.plan"
    assert decision["selected_tools"] == ["structure_index", "git_grep", "read_file"]
    assert any(item.get("rule") == "l1_find_behavior_start_terms" for item in decision["evidence"])
    assert decision["controller_request_preview"]["include_tests"] is True
    assert decision["controller_request_preview"]["target_root"] == str(target.resolve())
    assert "implementation_prep" in decision["approval_required_before"]
    assert "repository_mutation" in decision["approval_required_before"]


def test_workflow_router_plan_routes_l1_explain_code_without_repo_reads(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "In this repo, explain what find_stealth_order_by_placed_order_id does "
                    "in core/stealth_order_manager.py. Read only. Include key inputs, outputs, "
                    "side effects, and tests."
                ),
                "mode": "plan_only",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "ready"
    assert body["summary"]["selected_workflow"] == "code_investigation.plan"
    assert body["summary"]["next_action"] == "execute_read_only"
    assert body["summary"]["target_repo_read"] is False

    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["selected_workflow"] == "code_investigation.plan"
    assert decision["selected_tools"] == ["structure_index", "git_grep", "read_file"]
    assert any(item.get("rule") == "l1_explain_code_terms" for item in decision["evidence"])
    assert decision["controller_request_preview"]["include_tests"] is True
    assert decision["controller_request_preview"]["queries"][0] == "find_stealth_order_by_placed_order_id"
    assert decision["controller_request_preview"]["paths"] == ["core/stealth_order_manager.py"]


def test_workflow_router_plan_routes_l1_behavior_exists_without_repo_reads(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "In this repo, check whether placed_order_id stealth lookup already exists. "
                    "Read only. Return evidence for yes, no, or unknown."
                ),
                "mode": "plan_only",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "ready"
    assert body["summary"]["selected_workflow"] == "code_investigation.plan"
    assert body["summary"]["next_action"] == "execute_read_only"
    assert body["summary"]["target_repo_read"] is False

    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["selected_workflow"] == "code_investigation.plan"
    assert decision["selected_tools"] == ["structure_index", "git_grep", "read_file"]
    assert any(item.get("rule") == "l1_behavior_exists_terms" for item in decision["evidence"])
    assert decision["controller_request_preview"]["include_tests"] is True
    assert decision["controller_request_preview"]["queries"][0] == "placed_order_id"


def test_workflow_router_plan_routes_l1_callers_usages_without_repo_reads(tmp_path: Path) -> None:
    target = make_relationship_lookup_repo(tmp_path)
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "In this repo, find callers/usages of place_order. "
                    "Read only. Group by file and explain each usage briefly."
                ),
                "mode": "plan_only",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "ready"
    assert body["summary"]["selected_workflow"] == "code_context.lookup"
    assert body["summary"]["next_action"] == "execute_read_only"
    assert body["summary"]["target_repo_read"] is False

    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["selected_workflow"] == "code_context.lookup"
    assert decision["selected_tools"] == ["structure_index", "git_grep", "read_file", "codegraph_context"]
    assert any(item.get("rule") == "l1_callers_usages_terms" for item in decision["evidence"])
    assert decision["controller_request_preview"]["query"] == "place_order"
    assert decision["controller_request_preview"]["relationship_queries"] == [
        {"kind": "callers", "symbol": "place_order", "max_results": 25}
    ]


def test_workflow_router_plan_routes_l1_configuration_lookup_without_repo_reads(tmp_path: Path) -> None:
    target = make_config_lookup_repo(tmp_path)
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "In this repo, find where COINBASE_API_KEY environment variable is defined or used. "
                    "Read only. Return files, references, and likely runtime effect."
                ),
                "mode": "plan_only",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "ready"
    assert body["summary"]["selected_workflow"] == "code_investigation.plan"
    assert body["summary"]["next_action"] == "execute_read_only"
    assert body["summary"]["target_repo_read"] is False

    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["selected_workflow"] == "code_investigation.plan"
    assert decision["selected_tools"] == ["structure_index", "git_grep", "read_file"]
    assert any(item.get("rule") == "l1_configuration_lookup_terms" for item in decision["evidence"])
    assert decision["controller_request_preview"]["include_tests"] is True
    assert decision["controller_request_preview"]["queries"][0] == "COINBASE_API_KEY"


def test_workflow_router_plan_routes_l1_configuration_lookup_from_env_identifier_without_env_phrase(
    tmp_path: Path,
) -> None:
    target = make_config_lookup_repo(tmp_path)
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "In this repo, find where COINBASE_API_KEY is defined or used. "
                    "Read only. Return files, references, and likely runtime effect."
                ),
                "mode": "plan_only",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "ready"
    assert body["summary"]["selected_workflow"] == "code_investigation.plan"
    assert body["summary"]["target_repo_read"] is False

    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_configuration_lookup_terms" for item in decision["evidence"])
    assert decision["controller_request_preview"]["queries"][0] == "COINBASE_API_KEY"


def test_workflow_router_plan_routes_l1_test_failure_summary_without_repo_reads(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    failure_text = (
        "FAILED tests/unit/test_order_id_and_followup_rules.py::"
        "test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - "
        "AssertionError: expected client_order_id index"
    )
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "Summarize this pasted test failure. Do not edit files. Return what failed, "
                    f"likely cause, and next bounded inspection step.\n{failure_text}"
                ),
                "mode": "plan_only",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "ready"
    assert body["summary"]["selected_workflow"] == "code_investigation.plan"
    assert body["summary"]["next_action"] == "execute_read_only"
    assert body["summary"]["target_repo_read"] is False

    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["selected_workflow"] == "code_investigation.plan"
    assert decision["selected_tools"] == ["structure_index", "git_grep", "read_file"]
    assert any(item.get("rule") == "l1_test_failure_summary_terms" for item in decision["evidence"])
    assert decision["controller_request_preview"]["include_tests"] is True


def test_workflow_router_plan_routes_l1_small_text_edit_without_repo_reads(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "Draft a small documentation edit to docs/agents/INVARIANTS.md. "
                    "After \"- Use one code path per behavior.\" add "
                    "\"- L1-010 draft proof: route small documentation edits through packet dry-run.\". "
                    "Do not mutate files."
                ),
                "mode": "plan_only",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "ready"
    assert body["summary"]["selected_workflow"] == "execution_planning.plan"
    assert body["summary"]["next_action"] == "request_approval"
    assert body["summary"]["target_repo_read"] is False
    assert "downstream_result" not in body["artifacts"]

    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_small_text_edit_terms" for item in decision["evidence"])
    assert decision["controller_request_preview"]["mode"] == "investigation_only"


def test_workflow_router_plan_routes_l1_small_unit_test_without_repo_reads(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "In this repo, add a small unit test for "
                    "sync_exchange_order_id_for_placed_order setting exchange_order_id when it is missing. "
                    "Draft only. Show the proposed test file and verification command before applying."
                ),
                "mode": "plan_only",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "ready"
    assert body["summary"]["selected_workflow"] == "execution_planning.plan"
    assert body["summary"]["next_action"] == "request_approval"
    assert body["summary"]["target_repo_read"] is False
    assert "downstream_result" not in body["artifacts"]

    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_small_unit_test_terms" for item in decision["evidence"])
    assert decision["controller_request_preview"]["mode"] == "investigation_only"


def test_workflow_router_plan_routes_phase34_d1_prompts_without_repo_reads(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    cases = [
        (
            "In this repo, draft a small unit test in tests/test_lot_tracking_integration.py "
            "proving config default DEFAULT_PROFIT_MARGIN_PCT in business/lot_config.py defaults to 0.5. Draft only.",
            "d1_config_default_test_terms",
        ),
        (
            "In this repo, draft a small unit test in tests/unit/test_orderbook_v2.py "
            "asserting exact error message \"OrderBook is read-only; refusing upsert_order()\" from core/orderbook.py. "
            "Draft only.",
            "d1_message_assertion_test_terms",
        ),
        (
            "In this repo, draft a small test assertion update in tests/unit/test_order_id_and_followup_rules.py. "
            "Replace the assertion `assert call_kwargs[\"reveal_pricing_policy\"] == \"top_of_book\"` with "
            "`assert call_kwargs[\"reveal_pricing_policy\"] == \"top_of_book\"  # inherited from root parent`. Draft only.",
            "d1_test_assertion_update_terms",
        ),
    ]
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        host, port = service.base_url
        for user_request, expected_rule in cases:
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/plans",
                {
                    "workflow": "workflow_router.plan",
                    "target_root": str(target),
                    "user_request": user_request,
                    "mode": "plan_only",
                },
            )

            assert status == 200
            assert body["summary"]["route_status"] == "ready"
            assert body["summary"]["selected_workflow"] == "execution_planning.plan"
            assert body["summary"]["next_action"] == "request_approval"
            assert body["summary"]["target_repo_read"] is False

            decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
            assert any(item.get("rule") == expected_rule for item in decision["evidence"])
            assert decision["controller_request_preview"]["mode"] == "investigation_only"


def test_workflow_router_plan_routes_l1_simple_failing_test_fix_without_repo_reads(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "Inspect this failing test and propose the smallest fix. Draft only; do not apply until approved.\n"
                    "FAILED tests/unit/test_order_id_and_followup_rules.py::"
                    "test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - "
                    "AssertionError: expected find_stealth_order_by_placed_order_id docstring to mention client_order_id"
                ),
                "mode": "plan_only",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "ready"
    assert body["summary"]["selected_workflow"] == "execution_planning.plan"
    assert body["summary"]["next_action"] == "request_approval"
    assert body["summary"]["target_repo_read"] is False
    assert "downstream_result" not in body["artifacts"]

    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_simple_failing_test_fix_terms" for item in decision["evidence"])
    assert decision["controller_request_preview"]["mode"] == "investigation_only"


def test_workflow_router_plan_routes_l1_related_tests_without_repo_reads(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "In this repo, find tests related to placed_order_id stealth lookup. "
                    "Read only. Return test files, matching terms, and recommended test commands."
                ),
                "mode": "plan_only",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "ready"
    assert body["summary"]["selected_workflow"] == "code_investigation.plan"
    assert body["summary"]["next_action"] == "execute_read_only"
    assert body["summary"]["target_repo_read"] is False

    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["selected_workflow"] == "code_investigation.plan"
    assert decision["selected_tools"] == ["structure_index", "git_grep", "read_file"]
    assert any(item.get("rule") == "l1_find_related_tests_terms" for item in decision["evidence"])
    assert decision["controller_request_preview"]["include_tests"] is True
    assert decision["controller_request_preview"]["queries"][0] == "placed_order_id"


def test_workflow_router_plan_routes_l1_safe_test_command_without_repo_reads(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "In this repo, recommend the smallest test command for placed_order_id stealth lookup. "
                    "Read only. Explain why that command is relevant."
                ),
                "mode": "plan_only",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "ready"
    assert body["summary"]["selected_workflow"] == "code_investigation.plan"
    assert body["summary"]["next_action"] == "execute_read_only"
    assert body["summary"]["target_repo_read"] is False

    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["selected_workflow"] == "code_investigation.plan"
    assert decision["selected_tools"] == ["structure_index", "git_grep", "read_file"]
    assert any(item.get("rule") == "l1_safe_test_command_terms" for item in decision["evidence"])
    assert decision["controller_request_preview"]["include_tests"] is True
    assert decision["controller_request_preview"]["queries"][0] == "placed_order_id"


def context_source_ids(decision: dict[str, Any]) -> list[str]:
    audit = decision.get("context_source_audit")
    assert isinstance(audit, dict)
    selected = audit.get("selected_source_ids")
    assert isinstance(selected, list)
    return [item for item in selected if isinstance(item, str)]


def assert_context_sources(decision: dict[str, Any], expected: set[str]) -> None:
    selected = set(context_source_ids(decision))
    assert expected <= selected
    audit = decision["context_source_audit"]
    assert audit["selection_policy"]["manual_tool_request_required"] is False
    assert audit["selection_policy"]["unsupported_layout_fails_closed"] is True
    assert audit["layout"]["status"] == "supported"
    assert audit["layout"]["supported_file_count"] > 0
    assert audit["budget"]["max_selected_sources"] == 5
    assert audit["evidence_files"]
    preview = decision.get("controller_request_preview")
    if isinstance(preview, dict) and preview:
        assert set(preview["context_sources"]) == selected


def test_workflow_router_context_source_audit_selects_behavior_context_sources(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "In this repo, find where the placed_order_id stealth lookup begins. "
                    "Read only. Return the entrypoint, evidence files, related tests, and confidence."
                ),
                "mode": "plan_only",
            },
        )

    assert status == 200
    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert_context_sources(decision, {"ast_index", "text_search", "test_lookup"})
    assert body["summary"]["selected_context_sources"] == context_source_ids(decision)
    assert body["summary"]["context_layout_status"] == "supported"
    assert "context_source_audit" in body["artifacts"]


def test_workflow_router_context_source_audit_selects_config_lookup(tmp_path: Path) -> None:
    target = make_config_lookup_repo(tmp_path)
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "In this repo, find where COINBASE_API_KEY environment variable is defined or used. "
                    "Read only. Return files, references, and likely runtime effect."
                ),
                "mode": "plan_only",
            },
        )

    assert status == 200
    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert_context_sources(decision, {"ast_index", "text_search", "config_lookup"})
    selected_config = [
        item
        for item in decision["context_source_audit"]["selected"]
        if item.get("source_id") == "config_lookup"
    ][0]
    assert "configuration_or_environment_request" in selected_config["reasons"]


def test_workflow_router_context_source_audit_selects_curated_relationship_lookup(tmp_path: Path) -> None:
    target = make_relationship_lookup_repo(tmp_path)
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "In this repo, find callers/usages of place_order. "
                    "Read only. Group by file and explain each usage briefly."
                ),
                "mode": "plan_only",
            },
        )

    assert status == 200
    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert_context_sources(decision, {"ast_index", "text_search", "curated_relationship_lookup"})
    assert "codegraph_context" in decision["context_source_audit"]["selected"][-1]["tool_ids"]


def test_workflow_router_context_source_audit_blocks_unsupported_layout(tmp_path: Path) -> None:
    target = tmp_path / "allowed" / "empty-layout"
    target.mkdir(parents=True)
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": "In this repo, explain what place_order does. Read only.",
                "mode": "plan_only",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "blocked"
    assert body["summary"]["context_layout_status"] == "unsupported_no_supported_files"
    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["controller_request_preview"] == {}
    assert decision["blockers"][0]["reason"] == "unsupported_repository_layout"
    assert decision["context_source_audit"]["layout"]["status"] == "unsupported_no_supported_files"
    assert any("unsupported_repository_layout" in gap for gap in decision["context_source_audit"]["gaps"])


def test_workflow_router_chat_response_includes_context_source_summary(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, explain what find_stealth_order_by_placed_order_id does in "
                            "core/stealth_order_manager.py. Read only. Include key inputs, outputs, side effects, and tests."
                        ),
                    }
                ],
            },
        )

    assert status == 200
    content = body["choices"][0]["message"]["content"]
    assert "Context Sources:" in content
    assert "ast_index" in content
    assert "text_search" in content
    assert "route_decision.context_source_audit" in content
    compact = body["agentic_controller_response"]
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["context_source_audit"]["selected_source_ids"]


def test_workflow_router_plan_records_model_router_observation(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeRouterModelEndpoint("code_investigation.plan") as endpoint:
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/plans",
                {
                    "workflow": "workflow_router.plan",
                    "target_root": str(target),
                    "user_request": (
                        "In this repo, find where the placed_order_id stealth lookup begins."
                    ),
                    "role_base_url": endpoint.base_url,
                },
            )

    assert status == 200
    assert body["summary"]["route_status"] == "ready"
    assert body["summary"]["selected_workflow"] == "code_investigation.plan"
    assert body["summary"]["model_router_status"] == "accepted"
    assert len(endpoint.requests) == 1
    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(
        item.get("source") == "model_router" and item.get("status") == "accepted"
        for item in decision["evidence"]
    )
    assert decision["model_capability_routing"]["status"] in {"approved", "conditional"}
    assert decision["model_capability_routing"]["task_class"] == "read_only_l1"
    assert any(item.get("source") == "model_capability_routing" for item in decision["evidence"])


def test_workflow_router_plan_blocks_read_only_l1_when_model_profile_not_approved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = make_execution_planning_tree(tmp_path)
    write_model_capability_policy(
        tmp_path,
        monkeypatch,
        task_policy={
            "read_only_l1": "not_approved",
            "draft_only_l1": "approved",
            "approval_gated_l1": "conditional",
            "l2_read_only": "approved",
            "apply_prep": "conditional",
            "real_apply": "not_approved",
        },
    )
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": "In this repo, find where the placed_order_id stealth lookup begins.",
                "budgets": {"max_model_calls": 3, "max_selected_skills": 5, "max_selected_tools": 5},
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "blocked"
    assert body["summary"]["selected_workflow"] == "code_investigation.plan"
    assert body["summary"]["model_router_status"] == "not_requested"
    assert body["summary"]["model_capability_status"] == "blocked"
    assert body["summary"]["model_capability_task_class"] == "read_only_l1"
    assert body["summary"]["downstream_workflow"] is None
    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["controller_request_preview"] == {}
    assert decision["selected_skills"] == []
    assert decision["selected_tools"] == []
    assert decision["model_capability_routing"]["task_policy_status"] == "not_approved"
    assert decision["blockers"][0]["reason"] == "model_capability_task_not_approved"


def test_workflow_router_plan_blocks_apply_prep_when_model_profile_not_approved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "docs" / "agents" / "INVARIANTS.md"
    before = sentinel.read_text(encoding="utf-8")
    write_model_capability_policy(
        tmp_path,
        monkeypatch,
        task_policy={
            "read_only_l1": "approved",
            "draft_only_l1": "approved",
            "approval_gated_l1": "conditional",
            "l2_read_only": "approved",
            "apply_prep": "not_approved",
            "real_apply": "not_approved",
        },
    )
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": "Use the approved implementation packet to apply to a disposable copy only.",
                "mode": "apply_disposable_copy",
                "approval": {
                    "status": "approved_for_disposable_apply",
                    "scope": "workflow_router_disposable_copy",
                    "apply_allowed": True,
                    "approval_refs": ["test:disposable only"],
                },
                "packet_operations": [
                    {
                        "kind": "replace_text",
                        "path": "docs/agents/INVARIANTS.md",
                        "old": FROZEN_INVARIANT_OLD,
                        "new": FROZEN_INVARIANT_NEW,
                    }
                ],
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "blocked"
    assert body["summary"]["model_capability_status"] == "blocked"
    assert body["summary"]["model_capability_task_class"] == "apply_prep"
    assert body["summary"]["downstream_workflow"] is None
    assert "disposable_mutation_proof" not in body["artifacts"]
    assert sentinel.read_text(encoding="utf-8") == before
    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["controller_request_preview"] == {}
    assert decision["model_capability_routing"]["task_policy_status"] == "not_approved"
    assert decision["blockers"][0]["reason"] == "model_capability_task_not_approved"


def test_workflow_router_plan_model_router_cannot_override_deterministic_unsupported(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeRouterModelEndpoint("code_investigation.plan") as endpoint:
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/plans",
                {
                    "workflow": "workflow_router.plan",
                    "target_root": str(target),
                    "user_request": "Write a sonnet about build systems.",
                    "role_base_url": endpoint.base_url,
                },
            )

    assert status == 200
    assert body["summary"]["route_status"] == "unsupported"
    assert body["summary"]["selected_workflow"] is None
    assert body["summary"]["model_router_status"] == "accepted"
    assert len(endpoint.requests) == 1
    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["selected_workflow"] is None
    assert decision["controller_request_preview"] == {}
    assert any(
        item.get("source") == "model_router"
        and item.get("decision_authority") == "advisory_rejected_by_deterministic_router"
        for item in decision["evidence"]
    )
    audit = decision["selection_audit"]
    assert audit["selected"]["workflow_id"] is None
    assert audit["selected"]["confidence"] == "low"
    assert "blocked:unsupported" in audit["selected"]["confidence_reasons"]


def test_workflow_router_plan_blocks_when_selection_confidence_below_configured_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(workflow_router_plan, "SELECTION_MIN_CONFIDENCE", "high")
    target = make_execution_planning_tree(tmp_path)
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "Find tests related to placed_order_id stealth lookup. "
                    "Read only. Return test files and recommended commands."
                ),
                "budgets": {"max_model_calls": 0, "max_selected_skills": 5, "max_selected_tools": 5},
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "blocked"
    assert body["summary"]["selected_workflow"] == "code_investigation.plan"
    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["status"] == "blocked"
    assert decision["controller_request_preview"] == {}
    assert decision["blockers"][0]["reason"] == "low_selection_confidence"
    audit = decision["selection_audit"]
    assert audit["selection_policy"]["minimum_confidence"] == "high"
    assert "below_minimum_confidence:high" in audit["selected"]["confidence_reasons"]


def test_workflow_router_plan_blocks_ambiguous_request(tmp_path: Path) -> None:
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": "fix it",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "blocked"
    assert body["summary"]["selected_workflow"] is None
    assert body["summary"]["next_action"] == "ask_blocking_question"
    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["blockers"][0]["reason"] == "ambiguous"
    assert decision["controller_request_preview"] == {}
    audit = decision["selection_audit"]
    assert audit["selected"]["workflow_id"] is None
    assert audit["selected"]["confidence"] == "low"
    assert "blocked:ambiguous" in audit["selected"]["confidence_reasons"]
    assert audit["workflow_candidates"]["rejected_count"] >= 1


def test_workflow_router_plan_blocks_approval_bypass_request(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": "Apply this code change immediately and skip approval.",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "blocked"
    assert body["summary"]["selected_workflow"] is None
    assert body["summary"]["next_action"] == "request_approval"
    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["blockers"][0]["reason"] == "blocked_approval_bypass"
    assert decision["selected_tools"] == []
    audit = decision["selection_audit"]
    assert audit["selected"]["workflow_id"] is None
    assert "blocked:blocked_approval_bypass" in audit["selected"]["confidence_reasons"]
    assert audit["selection_policy"]["low_confidence_fails_closed"] is True


def test_workflow_router_plan_selection_audit_fails_closed_for_unsupported_request(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": "Write a sonnet about build systems.",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "unsupported"
    assert body["summary"]["selected_workflow"] is None
    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["blockers"][0]["reason"] == "unsupported"
    audit = decision["selection_audit"]
    assert audit["selected"]["workflow_id"] is None
    assert audit["selected"]["confidence"] == "low"
    assert "blocked:unsupported" in audit["selected"]["confidence_reasons"]


def test_workflow_router_plan_selection_audit_fails_closed_for_conflicting_mutation_request(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "Read only: find where placed_order_id lookup begins, then apply the fix immediately without approval."
                ),
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "blocked"
    assert body["summary"]["selected_workflow"] is None
    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["blockers"][0]["reason"] == "blocked_approval_bypass"
    audit = decision["selection_audit"]
    assert audit["selected"]["workflow_id"] is None
    assert "blocked:blocked_approval_bypass" in audit["selected"]["confidence_reasons"]
    assert audit["workflow_candidates"]["rejected_count"] >= 1


def test_workflow_router_execute_read_only_runs_l1_behavior_start_without_mutation(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "Find where the placed_order_id stealth lookup begins. "
                    "Read only. Return the entrypoint, evidence files, related tests, and confidence."
                ),
                "mode": "execute_read_only",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "ready"
    assert body["summary"]["selected_workflow"] == "code_investigation.plan"
    assert body["summary"]["downstream_workflow"] == "code_investigation.plan"
    assert body["summary"]["downstream_status"] == "completed"
    assert body["summary"]["target_repo_read"] is True
    assert "downstream_result" in body["artifacts"]
    assert "downstream_investigation_plan" in body["artifacts"]
    assert sentinel.read_text(encoding="utf-8") == before

    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["downstream"]["workflow"] == "code_investigation.plan"
    assert set(decision["downstream"]["tool_policy"]["controller_tool_ids"]) == {
        "git_grep",
        "read_file",
        "structure_index",
    }


def test_workflow_router_execute_read_only_runs_l1_explain_code_without_mutation(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "Explain what find_stealth_order_by_placed_order_id does in "
                    "core/stealth_order_manager.py. Read only. Include key inputs, outputs, "
                    "side effects, and tests."
                ),
                "mode": "execute_read_only",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "ready"
    assert body["summary"]["selected_workflow"] == "code_investigation.plan"
    assert body["summary"]["downstream_workflow"] == "code_investigation.plan"
    assert body["summary"]["downstream_status"] == "completed"
    assert body["summary"]["target_repo_read"] is True
    assert "downstream_code_explanation" in body["artifacts"]
    assert sentinel.read_text(encoding="utf-8") == before

    explanation = json.loads(Path(body["artifacts"]["downstream_code_explanation"]).read_text(encoding="utf-8"))
    assert explanation["status"] == "ready"
    assert explanation["target"]["symbol"] == "StealthOrderManager.find_stealth_order_by_placed_order_id"
    assert any(item.get("value") == "self.placed_order_index_key" for item in explanation["outputs"])
    assert any(item["path"] == "tests/unit/test_order_id_and_followup_rules.py" for item in explanation["related_tests"])


def test_workflow_router_routes_l2_code_quality_issue_language_to_code_investigation() -> None:
    workflow, status, evidence = workflow_router_plan.workflow_kind_for_request(
        "In /mnt/c/repo, review service/orders.py for naming clarity, function boundaries, "
        "and simple code-quality issues. Read only. If no meaningful issue is supported, "
        "say that and explain why."
    )

    assert workflow == "code_investigation.plan"
    assert status == "ready"
    assert any(item.get("rule") == "l2_code_quality_review_terms" for item in evidence)


def test_workflow_router_routes_l2_engineering_judgment_language_to_code_investigation() -> None:
    workflow, status, evidence = workflow_router_plan.workflow_kind_for_request(
        "In /mnt/c/repo, give read-only review feedback before implementation on whether to hardcode "
        "API_BASE_URL. Include evidence, alternatives, tradeoffs, risks, validation steps, confidence, "
        "and rejected preference claims."
    )

    assert workflow == "code_investigation.plan"
    assert status == "ready"
    assert any(item.get("rule") == "l2_engineering_judgment_terms" for item in evidence)
    assert not any(item.get("rule") == "feedback_terms" for item in evidence)


def test_workflow_router_chat_returns_inline_engineering_judgment_without_mutation(tmp_path: Path) -> None:
    target = make_python_service_fixture_repo(tmp_path)
    tracked_paths = [
        "service/api.py",
        "service/orders.py",
        "tests/test_orders.py",
    ]
    before_hashes = {rel_path: sha256_file(target / rel_path) for rel_path in tracked_paths}
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, give read-only review feedback on this proposal before implementation: "
                            "change service/api.py paid coercion from bool(message.get(\"paid\", False)) "
                            "to message.get(\"paid\") == True. Include correctness, maintainability, testability, "
                            "system impact, alternatives, rejected preference claims, validation steps, and evidence refs."
                        ),
                    }
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "downstream_engineering_judgment_review" in compact["artifacts"]
    assert "Engineering Judgment:" in content
    assert "Recommendation:" in content
    assert "Do not apply the paid == True proposal" in content
    assert "Tradeoffs:" in content
    assert "Validation:" in content
    assert "Unknowns:" in content
    assert "Rejected claims" in content
    assert "service/api.py:11" in content
    assert "service/orders.py:4" in content
    assert "Source mutation: false" in content
    assert {rel_path: sha256_file(target / rel_path) for rel_path in tracked_paths} == before_hashes

    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    review = json.loads(Path(compact["artifacts"]["downstream_engineering_judgment_review"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l2_engineering_judgment_terms" for item in decision["evidence"])
    assert review["kind"] == "engineering_judgment_review"
    assert review["status"] == "ready"
    assert review["review_mode"] == "review_feedback"
    assert review["mutation_policy"] == "read_only_no_source_mutation"
    assert review["direct_assessment"]["decision"] == "reject_proposal_until_input_contract_and_tests_exist"
    assert review["risks_and_blockers"]
    assert review["validation_steps"]


def test_workflow_router_chat_returns_inline_code_quality_review_without_mutation(tmp_path: Path) -> None:
    target = make_python_service_fixture_repo(tmp_path)
    tracked_paths = [
        "service/api.py",
        "service/orders.py",
        "tests/test_orders.py",
    ]
    before_hashes = {rel_path: sha256_file(target / rel_path) for rel_path in tracked_paths}
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, self-review this proposed patch before implementation: "
                            "in service/api.py, change `paid = bool(message.get(\"paid\", False))` "
                            "to `paid = message.get(\"paid\") == True`. Read only. Identify correctness, "
                            "maintainability, naming/style, and test risks with evidence refs and a recommendation."
                        ),
                    }
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "downstream_code_quality_review" in compact["artifacts"]
    assert "Code Quality Review:" in content
    assert "CQ-PATCH-001" in content
    assert "Recommendation: do_not_apply_without_contract_and_tests" in content
    assert "service/api.py:11" in content
    assert "service/orders.py:4" in content
    assert "Rejected false positives" in content
    assert "Source mutation: false" in content
    assert {rel_path: sha256_file(target / rel_path) for rel_path in tracked_paths} == before_hashes

    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    review = json.loads(Path(compact["artifacts"]["downstream_code_quality_review"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l2_code_quality_review_terms" for item in decision["evidence"])
    assert review["kind"] == "code_quality_review"
    assert review["status"] == "ready"
    assert review["review_mode"] == "proposed_patch_self_review"
    assert review["mutation_policy"] == "read_only_no_source_mutation"
    assert review["findings"][0]["id"] == "CQ-PATCH-001"


def test_workflow_router_chat_returns_no_finding_code_quality_review_without_mutation(tmp_path: Path) -> None:
    target = make_python_service_fixture_repo(tmp_path)
    tracked_paths = [
        "service/api.py",
        "service/orders.py",
        "tests/test_orders.py",
    ]
    before_hashes = {rel_path: sha256_file(target / rel_path) for rel_path in tracked_paths}
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
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"In {target}, review service/orders.py specifically for duplicated logic. "
                            "Read only. Do not invent issues; if duplication is not supported, "
                            "return no finding with evidence."
                        ),
                    }
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert compact["summary"]["downstream_status"] == "completed"
    assert "downstream_code_quality_review" in compact["artifacts"]
    assert "Code Quality Review:" in content
    assert "Findings: none supported" in content
    assert "No meaningful duplication" in content
    assert "Rejected false positives" in content
    assert "service/orders.py:4" in content
    assert "Source mutation: false" in content
    assert {rel_path: sha256_file(target / rel_path) for rel_path in tracked_paths} == before_hashes

    review = json.loads(Path(compact["artifacts"]["downstream_code_quality_review"]).read_text(encoding="utf-8"))
    assert review["kind"] == "code_quality_review"
    assert review["status"] == "no_supported_findings"
    assert review["findings"] == []
    assert review["mutation_policy"] == "read_only_no_source_mutation"
    assert review["rejected_false_positives"]


def test_workflow_router_execute_read_only_runs_l1_behavior_exists_without_mutation(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "Check whether placed_order_id stealth lookup already exists. "
                    "Read only. Return evidence for yes, no, or unknown."
                ),
                "mode": "execute_read_only",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "ready"
    assert body["summary"]["selected_workflow"] == "code_investigation.plan"
    assert body["summary"]["downstream_workflow"] == "code_investigation.plan"
    assert body["summary"]["downstream_status"] == "completed"
    assert body["summary"]["target_repo_read"] is True
    assert "downstream_behavior_existence" in body["artifacts"]
    assert sentinel.read_text(encoding="utf-8") == before

    existence = json.loads(Path(body["artifacts"]["downstream_behavior_existence"]).read_text(encoding="utf-8"))
    assert existence["status"] == "exists"
    assert existence["answer"] == "yes"
    assert any(item["path"] == "core/stealth_order_manager.py" for item in existence["evidence_files"])
    assert existence["source_refs"]


def test_workflow_router_execute_read_only_runs_l1_callers_usages_without_mutation(tmp_path: Path) -> None:
    target = make_relationship_lookup_repo(tmp_path)
    sentinel = target / "app" / "handler.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "Find callers/usages of place_order. "
                    "Read only. Group by file and explain each usage briefly."
                ),
                "mode": "execute_read_only",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "ready"
    assert body["summary"]["selected_workflow"] == "code_context.lookup"
    assert body["summary"]["downstream_workflow"] == "code_context.lookup"
    assert body["summary"]["downstream_status"] == "completed"
    assert body["summary"]["target_repo_read"] is True
    assert "downstream_usage_summary" in body["artifacts"]
    assert sentinel.read_text(encoding="utf-8") == before

    usage = json.loads(Path(body["artifacts"]["downstream_usage_summary"]).read_text(encoding="utf-8"))
    assert usage["status"] == "ready"
    assert usage["usage_count"] >= 2
    assert any(group["path"] == "app/handler.py" for group in usage["groups"])
    assert any(group["path"] == "core/service.py" for group in usage["groups"])


def test_workflow_router_execute_read_only_runs_l1_configuration_lookup_without_mutation(tmp_path: Path) -> None:
    target = make_config_lookup_repo(tmp_path)
    sentinel = target / "configuration.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "Find where COINBASE_API_KEY environment variable is defined or used. "
                    "Read only. Return files, references, and likely runtime effect."
                ),
                "mode": "execute_read_only",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "ready"
    assert body["summary"]["selected_workflow"] == "code_investigation.plan"
    assert body["summary"]["downstream_workflow"] == "code_investigation.plan"
    assert body["summary"]["downstream_status"] == "completed"
    assert body["summary"]["target_repo_read"] is True
    assert "downstream_configuration_lookup" in body["artifacts"]
    assert sentinel.read_text(encoding="utf-8") == before

    lookup = json.loads(Path(body["artifacts"]["downstream_configuration_lookup"]).read_text(encoding="utf-8"))
    assert lookup["status"] == "ready"
    assert lookup["reference_count"] >= 2
    assert any(group["path"] == "configuration.py" for group in lookup["groups"])
    assert any(group["path"] == "core/order_engine.py" for group in lookup["groups"])


def test_workflow_router_execute_read_only_runs_l1_test_failure_summary_without_mutation(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
    failure_text = (
        "FAILED tests/unit/test_order_id_and_followup_rules.py::"
        "test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - "
        "AssertionError: expected client_order_id index\n"
        "E   AssertionError: expected client_order_id index"
    )
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "Summarize this pasted test failure. Do not edit files. Return what failed, "
                    f"likely cause, and next bounded inspection step.\n{failure_text}"
                ),
                "mode": "execute_read_only",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "ready"
    assert body["summary"]["selected_workflow"] == "code_investigation.plan"
    assert body["summary"]["downstream_workflow"] == "code_investigation.plan"
    assert body["summary"]["downstream_status"] == "completed"
    assert body["summary"]["target_repo_read"] is True
    assert "downstream_test_failure_summary" in body["artifacts"]
    assert sentinel.read_text(encoding="utf-8") == before

    summary = json.loads(Path(body["artifacts"]["downstream_test_failure_summary"]).read_text(encoding="utf-8"))
    assert summary["status"] == "ready"
    assert summary["primary_error"]["type"] == "AssertionError"
    assert summary["failed_tests"][0]["test_name"].startswith("test_find_stealth_order_by_placed_order_id")


def test_workflow_router_execute_read_only_runs_l1_related_tests_without_mutation(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "Find tests related to placed_order_id stealth lookup. "
                    "Read only. Return test files, matching terms, and recommended test commands."
                ),
                "mode": "execute_read_only",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "ready"
    assert body["summary"]["selected_workflow"] == "code_investigation.plan"
    assert body["summary"]["downstream_workflow"] == "code_investigation.plan"
    assert body["summary"]["downstream_status"] == "completed"
    assert body["summary"]["target_repo_read"] is True
    assert body["summary"]["verification_command_count"] >= 1
    assert "downstream_investigation_plan" in body["artifacts"]
    assert sentinel.read_text(encoding="utf-8") == before

    plan = json.loads(Path(body["artifacts"]["downstream_investigation_plan"]).read_text(encoding="utf-8"))
    related_paths = [item["path"] for item in plan["related_tests"]]
    assert "tests/unit/test_order_id_and_followup_rules.py" in related_paths
    assert any("placed_order_id" in term for item in plan["related_tests"] for term in item["matched_terms"])
    commands = [item["command"] for item in plan["verification_plan"]["verification_commands"]]
    assert ["python", "-m", "pytest", "tests/unit/test_order_id_and_followup_rules.py"] in commands


def test_workflow_router_execute_read_only_runs_l1_safe_test_command_without_mutation(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "core" / "stealth_order_manager.py"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": (
                    "Recommend the smallest test command for placed_order_id stealth lookup. "
                    "Read only. Explain why that command is relevant."
                ),
                "mode": "execute_read_only",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "ready"
    assert body["summary"]["selected_workflow"] == "code_investigation.plan"
    assert body["summary"]["downstream_workflow"] == "code_investigation.plan"
    assert body["summary"]["downstream_status"] == "completed"
    assert body["summary"]["target_repo_read"] is True
    assert body["summary"]["verification_command_count"] >= 1
    assert "downstream_investigation_plan" in body["artifacts"]
    assert sentinel.read_text(encoding="utf-8") == before

    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(item.get("rule") == "l1_safe_test_command_terms" for item in decision["evidence"])
    plan = json.loads(Path(body["artifacts"]["downstream_investigation_plan"]).read_text(encoding="utf-8"))
    commands = plan["verification_plan"]["verification_commands"]
    assert any(
        item["command"] == ["python", "-m", "pytest", "tests/unit/test_order_id_and_followup_rules.py"]
        and item["source_refs"]
        for item in commands
    )
    assert all(item["command"][:3] == ["python", "-m", "pytest"] and len(item["command"]) == 4 for item in commands)


@advanced_workflow
def test_workflow_router_execute_read_only_blocks_implementation_prep_route(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": "Create an implementation plan for the placed_order_id stealth lookup.",
                "mode": "execute_read_only",
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "blocked"
    assert body["summary"]["selected_workflow"] == "execution_planning.plan"
    assert body["summary"]["downstream_workflow"] is None
    assert body["summary"]["next_action"] == "request_approval"
    assert "downstream_result" not in body["artifacts"]
    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["blockers"][0]["reason"] == "read_only_workflow_required"


@advanced_workflow
def test_workflow_router_implementation_prep_delegates_to_execution_planning_dry_run_without_mutation(
    tmp_path: Path,
) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "docs" / "agents" / "INVARIANTS.md"
    before = sentinel.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeExecutionPlanningEndpoint() as endpoint:
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/plans",
                {
                    "workflow": "workflow_router.plan",
                    "target_root": str(target),
                    "user_request": (
                        "Prepare implementation packet candidates for an approved documentation clarification "
                        "that client_order_id owns internal lookup paths."
                    ),
                    "mode": "implementation_prep",
                    "approval": {
                        "status": "approved_for_packet_design",
                        "scope": "packet_design_only",
                        "apply_allowed": False,
                        "approval_refs": ["test:approved packet design only"],
                    },
                    "packet_operations": [
                        {
                            "kind": "replace_text",
                            "path": "docs/agents/INVARIANTS.md",
                            "old": FROZEN_INVARIANT_OLD,
                            "new": FROZEN_INVARIANT_NEW,
                        }
                    ],
                    "role_base_url": endpoint.base_url,
                    "execution_budgets": {
                        "max_context_requests": 5,
                        "max_files": 10,
                        "max_records": 50,
                        "max_model_calls": 12,
                        "max_output_tokens": 4600,
                    },
                },
            )

    assert status == 200
    assert body["summary"]["route_status"] == "ready"
    assert body["summary"]["selected_workflow"] == "execution_planning.plan"
    assert body["summary"]["next_action"] == "none"
    assert body["summary"]["downstream_workflow"] == "execution_planning.plan"
    assert body["summary"]["downstream_status"] == "completed"
    assert "downstream_implementation_workflow_report" in body["artifacts"]
    assert sentinel.read_text(encoding="utf-8") == before

    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["implementation_prep"]["workflow"] == "execution_planning.plan"
    assert decision["implementation_prep"]["mode"] == "dry_run"
    assert decision["implementation_prep"]["apply_allowed"] is False


@advanced_workflow
def test_workflow_router_implementation_prep_records_downstream_failure_without_losing_route_decision(
    tmp_path: Path,
) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "docs" / "agents" / "INVARIANTS.md"
    before = sentinel.read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with FakeExecutionPlanningEndpoint() as endpoint:
        with RunningControllerService(config) as service:
            host, port = service.base_url
            status, body = request_json(
                host,
                port,
                "POST",
                "/v1/controller/workflow-router/plans",
                {
                    "workflow": "workflow_router.plan",
                    "target_root": str(target),
                    "user_request": (
                        "Prepare implementation packet candidates for an approved documentation clarification "
                        "that client_order_id owns internal lookup paths."
                    ),
                    "mode": "implementation_prep",
                    "approval": {
                        "status": "approved_for_packet_design",
                        "scope": "packet_design_only",
                        "apply_allowed": False,
                        "approval_refs": ["test:approved packet design only"],
                    },
                    "packet_operations": [
                        {
                            "kind": "replace_text",
                            "path": "docs/agents/INVARIANTS.md",
                            "old": FROZEN_INVARIANT_OLD,
                            "new": FROZEN_INVARIANT_NEW,
                        }
                    ],
                    "role_base_url": endpoint.base_url,
                    "execution_budgets": {
                        "max_context_requests": 5,
                        "max_files": 10,
                        "max_records": 50,
                        "max_model_calls": 1,
                        "max_output_tokens": 4600,
                    },
                },
            )

    assert status == 200
    assert body["summary"]["route_status"] == "blocked"
    assert body["summary"]["selected_workflow"] == "execution_planning.plan"
    assert body["summary"]["next_action"] == "retry_execution_planning"
    assert body["summary"]["downstream_workflow"] == "execution_planning.plan"
    assert body["summary"]["downstream_status"] == "failed"
    assert "route_decision" in body["artifacts"]
    assert sentinel.read_text(encoding="utf-8") == before

    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["implementation_prep"]["workflow"] == "execution_planning.plan"
    assert decision["implementation_prep"]["status"] == "failed"
    assert decision["implementation_prep"]["failed_skill"] == "scope-and-assumptions"
    assert decision["implementation_prep"]["retry_guidance"] == "Increase max_model_calls or reduce the requested skill chain."
    assert decision["blockers"][0]["reason"] == "downstream_implementation_prep_failed"
    assert decision["blockers"][0]["failed_skill"] == "scope-and-assumptions"
    assert decision["blockers"][0]["artifact_key"] == "scope_and_assumptions"


@advanced_workflow
def test_workflow_router_implementation_prep_blocks_missing_approval_before_packet_creation(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": "Prepare implementation packet candidates for the placed_order_id lookup.",
                "mode": "implementation_prep",
                "packet_operations": [
                    {
                        "kind": "replace_text",
                        "path": "docs/agents/INVARIANTS.md",
                        "old": FROZEN_INVARIANT_OLD,
                        "new": FROZEN_INVARIANT_NEW,
                    }
                ],
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "blocked"
    assert body["summary"]["selected_workflow"] == "execution_planning.plan"
    assert body["summary"]["downstream_workflow"] is None
    assert "downstream_result" not in body["artifacts"]
    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["blockers"][0]["reason"] == "missing_packet_design_approval"


@advanced_workflow
def test_workflow_router_apply_disposable_copy_mutates_copy_only(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
    sentinel = target / "docs" / "agents" / "INVARIANTS.md"
    before = sentinel.read_text(encoding="utf-8")
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": "Apply approved packet operations to a disposable copy for mutation proof.",
                "mode": "apply_disposable_copy",
                "approval": {
                    "status": "approved_for_disposable_apply",
                    "apply_allowed": True,
                    "apply_scope": "disposable_copy_only",
                    "approval_refs": ["test:approved disposable copy apply only"],
                },
                "packet_operations": [
                    {
                        "kind": "replace_text",
                        "path": "docs/agents/INVARIANTS.md",
                        "old": FROZEN_INVARIANT_OLD,
                        "new": FROZEN_INVARIANT_NEW,
                    }
                ],
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "ready"
    assert body["summary"]["downstream_workflow"] == "implementation.workflow"
    assert body["summary"]["downstream_status"] == "completed"
    assert body["summary"]["source_changed"] is False
    assert body["summary"]["disposable_copy_changed"] is True
    assert sentinel.read_text(encoding="utf-8") == before

    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    proof = decision["disposable_apply"]["mutation_proof"]
    copy_root = Path(proof["disposable_copy_root"])
    assert proof["source_changed"] == {}
    assert proof["copy_changed"]["docs/agents/INVARIANTS.md"]["before"] != proof["copy_changed"]["docs/agents/INVARIANTS.md"]["after"]
    assert proof["rollback"]["status"] == "restored"
    assert Path(proof["rollback"]["artifact"]).exists()
    assert (copy_root / "docs" / "agents" / "INVARIANTS.md").read_text(encoding="utf-8") == before


@advanced_workflow
def test_workflow_router_apply_disposable_copy_blocks_without_disposable_approval(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": "Apply approved packet operations to a disposable copy for mutation proof.",
                "mode": "apply_disposable_copy",
                "approval": {
                    "status": "approved_for_packet_design",
                    "apply_allowed": False,
                },
                "packet_operations": [
                    {
                        "kind": "replace_text",
                        "path": "docs/agents/INVARIANTS.md",
                        "old": FROZEN_INVARIANT_OLD,
                        "new": FROZEN_INVARIANT_NEW,
                    }
                ],
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "blocked"
    assert body["summary"]["downstream_workflow"] is None
    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["blockers"][0]["reason"] == "missing_disposable_apply_approval"


def test_workflow_router_plan_rejects_target_outside_allowlist(tmp_path: Path) -> None:
    target = tmp_path / "outside"
    target.mkdir()
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
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "target_root": str(target),
                "user_request": "Investigate this repo.",
            },
        )

    assert status == 403
    assert body["error"]["code"] == "target_root_not_allowed"


def test_harness_adapter_accepts_workflow_router_envelope(tmp_path: Path) -> None:
    target = make_execution_planning_tree(tmp_path)
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
                    "workflow": "workflow_router.plan",
                    "target_root": str(target),
                    "user_request": "Investigate where placed_order_id stealth lookup begins.",
                    "mode": "plan_only",
                },
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    assert compact["workflow"] == "workflow_router.plan"
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "code_investigation.plan"
    assert "workflow_router.plan completed" in body["choices"][0]["message"]["content"]


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


def phase46_pack_skill_body(skill_id: str, description: str) -> str:
    return (
        "---\n"
        f"name: {skill_id}\n"
        f"description: {description}\n"
        "---\n"
        "\n"
        f"# {skill_id}\n"
        "\n"
        "Use this skill only when registry metadata selects this exact prompt family.\n"
        "Keep the workflow read-only and cite bounded repository evidence.\n"
    )


def phase46_pack_skill(
    *,
    skill_id: str,
    source_path: Path,
    route_key: str,
    eval_case_id: str,
    trigger: str,
    task_type: str,
) -> dict[str, Any]:
    return {
        "id": skill_id,
        "path": str(source_path),
        "version": "0.1.0",
        "owner": "agentic_agents",
        "description": f"Phase 46 governed pack skill for {trigger} requests.",
        "compatibility": ["agent-skills-frontmatter", "openai-compatible-chat", "qwen-local"],
        "safety_level": "read_only_planning",
        "allowed_tools": [],
        "workflows": ["code_investigation.plan"],
        "triggers": [trigger],
        "workflow_priorities": {"code_investigation.plan": 1000},
        "capability_contract": {
            "route_key": route_key,
            "task_types": [task_type],
            "input_artifacts": ["natural_user_request"],
            "output_artifacts": ["investigation_plan"],
            "approval_boundary": "none",
            "mutation_policy": "no_repository_mutation",
            "eval_case_ids": [eval_case_id],
        },
        "problem_solving_steps": [4],
        "eval_status": "draft",
        "evals": {
            "fixtures": ["clear_request", "ambiguous_request"],
            "localhost_8000": "not_run",
            "gateway_8300": "not_run",
            "anythingllm": "not_run",
        },
        "failure_record_refs": ["docs/SKILL_LIBRARY_SCALING_PLAN.md#approved-phase-46-skill-pack-export-import-and-namespace-governance"],
    }


def phase46_pack_eval(eval_case_id: str, prompt_family: str, natural_prompt: str) -> dict[str, Any]:
    return {
        "id": eval_case_id,
        "prompt_family": prompt_family,
        "natural_prompt": natural_prompt,
        "expected_workflow": "code_investigation.plan",
        "expected_artifacts": ["investigation_plan"],
        "mutation_policy": "no_repository_mutation",
        "live_suite": "skill_registry_contract",
    }


def write_phase46_pack(output_root: Path, *, duplicate_route: bool = False, namespace_not_owned: bool = False) -> Path:
    pack_root = output_root / "phase46-pack-source"
    alpha_id = "phase46-alpha-pack-locator"
    beta_id = "phase46-beta-pack-locator"
    alpha_body = pack_root / "skills" / alpha_id / "SKILL.md"
    beta_body = pack_root / "skills" / beta_id / "SKILL.md"
    write_text(alpha_body, phase46_pack_skill_body(alpha_id, "Phase 46 alpha pack locator skill."))
    write_text(beta_body, phase46_pack_skill_body(beta_id, "Phase 46 beta pack locator skill."))
    alpha_route = "code.phase46_alpha_pack_lookup"
    beta_route = alpha_route if duplicate_route else "docs.phase46_beta_pack_lookup"
    if namespace_not_owned:
        beta_route = "test.phase46_beta_pack_lookup"
    manifest = {
        "schema_version": 1,
        "kind": "skill_pack_manifest",
        "id": "phase46-governed-pack",
        "version": "0.1.0",
        "owner": "agentic_agents",
        "description": "Phase 46 governed pack used to validate controlled registry installation.",
        "namespaces": ["code"] if namespace_not_owned else ["code", "docs"],
        "compatibility": ["agent-skills-frontmatter", "openai-compatible-chat", "qwen-local"],
        "docs": ["README.skill-registry.md", "docs/SKILL_LIBRARY_SCALING_PLAN.md"],
        "skills": [
            phase46_pack_skill(
                skill_id=alpha_id,
                source_path=alpha_body,
                route_key=alpha_route,
                eval_case_id="phase46_alpha_pack_lookup",
                trigger="phase46 alpha pack lookup",
                task_type="phase46_alpha_pack_lookup",
            ),
            phase46_pack_skill(
                skill_id=beta_id,
                source_path=beta_body,
                route_key=beta_route,
                eval_case_id="phase46_beta_pack_lookup",
                trigger="phase46 beta pack lookup",
                task_type="phase46_beta_pack_lookup",
            ),
        ],
        "eval_cases": [
            phase46_pack_eval(
                "phase46_alpha_pack_lookup",
                "phase46-alpha-pack",
                "In <repo>, run the phase46 alpha pack lookup. Read only.",
            ),
            phase46_pack_eval(
                "phase46_beta_pack_lookup",
                "phase46-beta-pack",
                "In <repo>, run the phase46 beta pack lookup. Read only.",
            ),
        ],
    }
    pack_path = pack_root / "pack.json"
    pack_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return pack_path


def test_skill_pack_validate_and_install_adds_multiple_skills_with_selector_proof(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    output_root = tmp_path / ".agentic_controller"
    pack_path = write_phase46_pack(output_root)
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=output_root,
        allowed_target_roots=(config_root,),
        port=0,
    )

    with RunningControllerService(config) as service:
        host, port = service.base_url
        validate_status, validate_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-packs/validations",
            {
                "workflow": "skill_pack.validate",
                "schema_version": 1,
                "pack_path": str(pack_path),
            },
        )
        assert validate_status == 200
        assert validate_body["workflow"] == "skill_pack.validate"
        assert validate_body["summary"]["validation_status"] == "passed"
        assert validate_body["summary"]["skill_count"] == 2

        install_status, install_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-packs/installations",
            {
                "workflow": "skill_pack.install",
                "schema_version": 1,
                "pack_path": str(pack_path),
                "approval": skill_pack_install_approval(),
            },
        )
        assert install_status == 200
        assert install_body["workflow"] == "skill_pack.install"
        assert install_body["summary"]["install_status"] == "installed"
        assert install_body["summary"]["installed_skill_ids"] == [
            "phase46-alpha-pack-locator",
            "phase46-beta-pack-locator",
        ]

        selection_status, selection_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-selection/explanations",
            {
                "workflow": "skill.selection.explain",
                "schema_version": 1,
                "workflow_id": "code_investigation.plan",
                "user_request": "In the repo, perform a phase46 alpha pack lookup. Read only.",
            },
        )
        assert selection_status == 200
        selected_ids = selection_body["summary"]["selected_skill_ids"]
        assert "phase46-alpha-pack-locator" in selected_ids
        assert selection_body["summary"]["body_reads_during_selection"] == 0

    registry = load_skill_registry(config_root)
    selected = select_skills_for_workflow(
        registry,
        "code_investigation.plan",
        query_text="In the repo, perform a phase46 alpha pack lookup. Read only.",
        limit=5,
    )
    assert "phase46-alpha-pack-locator" in selected


def test_skill_pack_install_rejects_duplicate_route_key_without_mutation(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    output_root = tmp_path / ".agentic_controller"
    pack_path = write_phase46_pack(output_root, duplicate_route=True)
    before_skills = sha256_file(config_root / "runtime" / "skills.json")
    before_evals = sha256_file(config_root / "runtime" / "skill_evals.json")
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=output_root,
        allowed_target_roots=(config_root,),
        port=0,
    )

    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-packs/installations",
            {
                "workflow": "skill_pack.install",
                "schema_version": 1,
                "pack_path": str(pack_path),
                "approval": skill_pack_install_approval("duplicate-route-pack"),
            },
        )

    assert status == 422
    assert body["error"]["code"] == "skill_pack_validation_failed"
    assert "Duplicate skill batch route_key" in body["error"]["message"]
    assert sha256_file(config_root / "runtime" / "skills.json") == before_skills
    assert sha256_file(config_root / "runtime" / "skill_evals.json") == before_evals
    assert not (config_root / ".qwen" / "skills" / "phase46-alpha-pack-locator").exists()
    assert not (config_root / ".qwen" / "skills" / "phase46-beta-pack-locator").exists()


def test_skill_pack_install_rejects_namespace_not_owned_without_mutation(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    output_root = tmp_path / ".agentic_controller"
    pack_path = write_phase46_pack(output_root, namespace_not_owned=True)
    before_skills = sha256_file(config_root / "runtime" / "skills.json")
    before_evals = sha256_file(config_root / "runtime" / "skill_evals.json")
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=output_root,
        allowed_target_roots=(config_root,),
        port=0,
    )

    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-packs/installations",
            {
                "workflow": "skill_pack.install",
                "schema_version": 1,
                "pack_path": str(pack_path),
                "approval": skill_pack_install_approval("namespace-pack"),
            },
        )

    assert status == 422
    assert body["error"]["code"] == "skill_pack_validation_failed"
    assert "not owned by pack" in body["error"]["message"]
    assert sha256_file(config_root / "runtime" / "skills.json") == before_skills
    assert sha256_file(config_root / "runtime" / "skill_evals.json") == before_evals
    assert not (config_root / ".qwen" / "skills" / "phase46-alpha-pack-locator").exists()
    assert not (config_root / ".qwen" / "skills" / "phase46-beta-pack-locator").exists()


def phase47_scaffold_spec(
    *,
    skill_id: str = "phase47-fixture-locator",
    route_key: str = "code.phase47_fixture_lookup",
    task_types: list[str] | None = None,
    trigger_terms: list[str] | None = None,
    output_artifact: str = "investigation_plan",
) -> dict[str, Any]:
    return {
        "skill_id": skill_id,
        "description": "Locate bounded fixture evidence for a deterministic Phase 47 scaffold prompt family.",
        "prompt_family": "phase47-fixture-lookup",
        "natural_prompt": "In <repo>, find the Phase 47 fixture evidence. Read only.",
        "workflow_id": "code_investigation.plan",
        "route_key": route_key,
        "trigger_terms": trigger_terms or ["phase47 fixture lookup"],
        "task_types": task_types or ["phase47_fixture_lookup"],
        "output_artifact": output_artifact,
        "live_suite": "skill_registry_contract",
        "docs": ["README.skill-registry.md", "docs/SKILL_LIBRARY_SCALING_PLAN.md"],
        "problem_solving_steps": [4],
    }


def test_skill_scaffold_generates_valid_batch_manifest_and_frontmatter(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    before_skills = sha256_file(config_root / "runtime" / "skills.json")
    before_evals = sha256_file(config_root / "runtime" / "skill_evals.json")
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / ".agentic_controller",
        allowed_target_roots=(config_root,),
        port=0,
    )

    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-scaffolds",
            {
                "workflow": "skill.scaffold",
                "schema_version": 1,
                "prompt_family_spec": phase47_scaffold_spec(),
            },
        )

    assert status == 200
    assert body["workflow"] == "skill.scaffold"
    assert body["summary"]["scaffold_status"] == "ready"
    assert body["summary"]["batch_validation_status"] == "passed"
    scaffold = json.loads(Path(body["artifacts"]["skill_scaffold"]).read_text(encoding="utf-8"))
    manifest = scaffold["draft_batch_manifest"]
    assert manifest["kind"] == "skill_batch_manifest"
    assert manifest["skills"][0]["id"] == "phase47-fixture-locator"
    assert manifest["eval_cases"][0]["live_suite"] == "skill_registry_contract"
    frontmatter = parse_skill_frontmatter(Path(body["artifacts"]["draft_skill_body"]))
    assert frontmatter["name"] == "phase47-fixture-locator"
    batch_report = json.loads(Path(body["artifacts"]["batch_validation_report"]).read_text(encoding="utf-8"))
    assert batch_report["status"] == "passed"
    checklist = json.loads(Path(body["artifacts"]["validation_checklist"]).read_text(encoding="utf-8"))
    assert {item["id"]: item["status"] for item in checklist["checks"]}["runtime_registry_mutation"] == "not_mutated"
    assert sha256_file(config_root / "runtime" / "skills.json") == before_skills
    assert sha256_file(config_root / "runtime" / "skill_evals.json") == before_evals


def test_skill_scaffold_authoring_factory_generates_sidecars_without_promotion(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    before_skills = sha256_file(config_root / "runtime" / "skills.json")
    before_evals = sha256_file(config_root / "runtime" / "skill_evals.json")
    before_coverage = sha256_file(config_root / "runtime" / "prompt_skill_coverage.json")
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / ".agentic_controller",
        allowed_target_roots=(config_root,),
        port=0,
    )
    spec = phase47_scaffold_spec(
        skill_id="phase80-factory-locator",
        route_key="code.phase80_factory_lookup",
        task_types=["phase80_factory_lookup"],
        trigger_terms=["phase80 factory lookup"],
        output_artifact="investigation_plan",
    )
    spec.update(
        {
            "coverage_id": "PHASE80-FACTORY-LOOKUP",
            "level": "L1",
            "route_rule": "l1_find_behavior_start_terms",
            "tool_ids": ["git_grep", "read_file"],
        }
    )

    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-scaffolds",
            {
                "workflow": "skill.scaffold",
                "schema_version": 1,
                "prompt_family_spec": spec,
            },
        )

    assert status == 200
    assert body["summary"]["scaffold_status"] == "ready"
    assert body["summary"]["authoring_factory_status"] == "draft_sidecars_generated"
    assert body["summary"]["promotion_state"] == "not_promoted_by_scaffold"
    expected_artifacts = {
        "prompt_coverage_entry",
        "eval_skeleton",
        "docs_stub",
        "docs_example_stub",
        "regression_test_skeleton",
        "authoring_factory_report",
    }
    assert expected_artifacts <= set(body["artifacts"])

    coverage_entry = json.loads(Path(body["artifacts"]["prompt_coverage_entry"]).read_text(encoding="utf-8"))
    assert coverage_entry["id"] == "PHASE80-FACTORY-LOOKUP"
    assert coverage_entry["status"] == "planned"
    assert coverage_entry["skill_ids"] == ["phase80-factory-locator"]
    assert coverage_entry["tool_ids"] == ["git_grep", "read_file"]
    assert coverage_entry["promotion_state"] == "not_promoted_by_scaffold"

    eval_skeleton = json.loads(Path(body["artifacts"]["eval_skeleton"]).read_text(encoding="utf-8"))
    assert eval_skeleton["kind"] == "skill_eval_skeleton"
    assert {gate["id"] for gate in eval_skeleton["required_gates"]} == {
        "routing",
        "artifact_contract",
        "natural_language_chat_output",
        "prompt_coverage",
    }
    assert all(gate["status"] == "not_run" for gate in eval_skeleton["required_gates"])

    test_skeleton = Path(body["artifacts"]["regression_test_skeleton"]).read_text(encoding="utf-8")
    assert "test_phase80_factory_locator_routes_to_expected_workflow" in test_skeleton
    assert "test_phase80_factory_locator_emits_expected_artifact_contract" in test_skeleton
    assert "test_phase80_factory_locator_chat_output_is_user_visible" in test_skeleton
    assert "test_phase80_factory_locator_prompt_coverage_entry_is_implemented" in test_skeleton
    assert test_skeleton.count("pytest.fail") == 4

    docs_stub = Path(body["artifacts"]["docs_stub"]).read_text(encoding="utf-8")
    assert "not shipped documentation until the skill" in docs_stub
    factory_report = json.loads(Path(body["artifacts"]["authoring_factory_report"]).read_text(encoding="utf-8"))
    assert factory_report["kind"] == "skill_authoring_factory_report"
    assert factory_report["promotion_state"] == "not_promoted_by_scaffold"
    assert {item["id"]: item["status"] for item in factory_report["checks"]}["test_skeleton"] == "fail_closed"
    checklist = json.loads(Path(body["artifacts"]["validation_checklist"]).read_text(encoding="utf-8"))
    checklist_statuses = {item["id"]: item["status"] for item in checklist["checks"]}
    assert checklist_statuses["authoring_factory_sidecars"] == "generated"
    assert checklist_statuses["promotion_gate"] == "blocked_until_eval_gates_pass"

    assert sha256_file(config_root / "runtime" / "skills.json") == before_skills
    assert sha256_file(config_root / "runtime" / "skill_evals.json") == before_evals
    assert sha256_file(config_root / "runtime" / "prompt_skill_coverage.json") == before_coverage
    assert not (config_root / ".qwen" / "skills" / "phase80-factory-locator").exists()


def test_skill_scaffold_returns_do_not_admit_for_overlapping_intent(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / ".agentic_controller",
        allowed_target_roots=(config_root,),
        port=0,
    )
    spec = phase47_scaffold_spec(
        skill_id="phase47-duplicate-explanation",
        route_key="code.phase47_duplicate_explanation",
        task_types=["code_explanation"],
        trigger_terms=["explain"],
        output_artifact="code_explanation",
    )

    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-scaffolds",
            {
                "workflow": "skill.scaffold",
                "schema_version": 1,
                "prompt_family_spec": spec,
            },
        )

    assert status == 200
    assert body["summary"]["scaffold_status"] == "do_not_admit"
    assert body["summary"]["do_not_admit_count"] == 1
    scaffold = json.loads(Path(body["artifacts"]["skill_scaffold"]).read_text(encoding="utf-8"))
    errors = scaffold["do_not_admit"][0]["errors"]
    assert any("overlapping semantic intent" in error for error in errors)


def test_skill_scaffold_requires_explicit_known_output_artifact(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / ".agentic_controller",
        allowed_target_roots=(config_root,),
        port=0,
    )
    spec = phase47_scaffold_spec()
    del spec["output_artifact"]

    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/skill-scaffolds",
            {
                "workflow": "skill.scaffold",
                "schema_version": 1,
                "prompt_family_spec": spec,
            },
        )

    assert status == 400
    assert body["error"]["code"] == "missing_prompt_family_spec_field"


def test_workflow_router_chat_natural_skill_scaffold_routes_without_manual_skill_injection(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    before_skills = sha256_file(config_root / "runtime" / "skills.json")
    before_evals = sha256_file(config_root / "runtime" / "skill_evals.json")
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / ".agentic_controller",
        allowed_target_roots=(config_root,),
        port=0,
    )
    prompt = "\n".join(
        [
            "Scaffold a skill for a deterministic L1 prompt family.",
            "skill_id: phase49-log-locator",
            "description: Locate bounded log evidence for Phase 49 natural scaffold testing.",
            "prompt_family: phase49-log-lookup",
            "natural_prompt: In <repo>, find Phase 49 log evidence. Read only.",
            "workflow_id: code_investigation.plan",
            "route_key: code.phase49_log_lookup",
            "trigger_terms: phase49 log lookup, log evidence",
            "task_types: phase49_log_lookup",
            "output_artifact: investigation_plan",
            "live_suite: skill_registry_contract",
        ]
    )

    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [{"role": "user", "content": prompt}],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["workflow"] == "skill.scaffold"
    assert compact["summary"]["scaffold_status"] == "ready"
    assert compact["summary"]["skill_id"] == "phase49-log-locator"
    assert "Skill Scaffold:" in content
    assert "phase49-log-locator" in content
    assert "Authoring factory: draft_sidecars_generated" in content
    assert "Factory sidecars: prompt_coverage_entry" in content
    route_decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert route_decision["selected_workflow"] == "skill.scaffold"
    assert route_decision["approval_required"] is False
    assert sha256_file(config_root / "runtime" / "skills.json") == before_skills
    assert sha256_file(config_root / "runtime" / "skill_evals.json") == before_evals


def test_workflow_router_chat_natural_skill_pack_validation_supports_json_output(tmp_path: Path) -> None:
    config_root = make_skill_registration_root(tmp_path)
    output_root = tmp_path / ".agentic_controller"
    pack_path = write_phase46_pack(output_root)
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=output_root,
        allowed_target_roots=(config_root,),
        port=0,
    )

    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": f"Validate this skill pack.\npack_path: {pack_path}\nReturn output as JSON.",
                    }
                ],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    rendered = json.loads(body["choices"][0]["message"]["content"])
    assert compact["output_format"] == "json"
    assert rendered["workflow"] == "skill_pack.validate"
    assert rendered["summary"]["validation_status"] == "passed"
    route_decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert route_decision["selected_workflow"] == "skill_pack.validate"


def test_workflow_router_chat_natural_skill_pack_install_requires_then_accepts_approval_continuation(
    tmp_path: Path,
) -> None:
    config_root = make_skill_registration_root(tmp_path)
    output_root = tmp_path / ".agentic_controller"
    pack_path = write_phase46_pack(output_root)
    skills_path = config_root / "runtime" / "skills.json"
    evals_path = config_root / "runtime" / "skill_evals.json"
    before_hashes = {path: sha256_file(path) for path in (skills_path, evals_path)}
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=output_root,
        allowed_target_roots=(config_root,),
        port=0,
    )

    with RunningControllerService(config) as service:
        host, port = service.base_url
        missing_status, missing_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [{"role": "user", "content": f"Install this skill pack.\npack_path: {pack_path}"}],
            },
        )
        missing_compact = missing_body["agentic_controller_response"]
        assert missing_status == 200
        assert missing_compact["workflow"] == "skill_pack.install"
        assert missing_compact["status"] == "approval_required"
        assert missing_compact["summary"]["required_approval"]["status"] == "approved_for_skill_pack_install"
        assert {path: sha256_file(path) for path in (skills_path, evals_path)} == before_hashes

        approved_status, approved_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": f"Approved for skill pack install run_id {missing_compact['run_id']}",
                    }
                ],
            },
        )

    assert approved_status == 200
    compact = approved_body["agentic_controller_response"]
    content = approved_body["choices"][0]["message"]["content"]
    assert compact["workflow"] == "skill_pack.install"
    assert compact["summary"]["install_status"] == "installed"
    assert "phase46-alpha-pack-locator" in compact["summary"]["installed_skill_ids"]
    assert "install_status: installed" in content
    assert sha256_file(skills_path) != before_hashes[skills_path]
    assert sha256_file(evals_path) != before_hashes[evals_path]
    route_decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    approval_proof = json.loads(Path(compact["artifacts"]["approval_proof"]).read_text(encoding="utf-8"))
    assert route_decision["selected_workflow"] == "skill_pack.install"
    assert approval_proof["approval"]["approval_refs"] == [
        f"natural_skill_pack_install:{missing_compact['run_id']}"
    ]


def test_workflow_router_chat_natural_skill_update_requires_then_accepts_approval_continuation(
    tmp_path: Path,
) -> None:
    config_root = make_skill_registration_root(tmp_path)
    output_root = tmp_path / ".agentic_controller"
    skills_path = config_root / "runtime" / "skills.json"
    evals_path = config_root / "runtime" / "skill_evals.json"
    skill_body = config_root / ".qwen" / "skills" / "code-explanation-summarizer" / "SKILL.md"
    before_hashes = {path: sha256_file(path) for path in (skills_path, evals_path, skill_body)}
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=output_root,
        allowed_target_roots=(config_root,),
        port=0,
    )
    update_prompt = "\n".join(
        [
            "Update skill metadata for controlled-copy testing.",
            "skill_id: code-explanation-summarizer",
            "change_type: metadata_only",
            "version_bump: patch",
            'metadata_updates: {"description": "Phase 49 natural metadata update proof."}',
        ]
    )

    with RunningControllerService(config) as service:
        host, port = service.base_url
        missing_status, missing_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [{"role": "user", "content": update_prompt}],
            },
        )
        missing_compact = missing_body["agentic_controller_response"]
        assert missing_status == 200
        assert missing_compact["workflow"] == "skill.update"
        assert missing_compact["status"] == "approval_required"
        assert missing_compact["summary"]["required_approval"]["status"] == "approved_for_skill_update"
        assert {path: sha256_file(path) for path in (skills_path, evals_path, skill_body)} == before_hashes

        approved_status, approved_body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": f"Approved for skill update run_id {missing_compact['run_id']}",
                    }
                ],
            },
        )

    assert approved_status == 200
    compact = approved_body["agentic_controller_response"]
    assert compact["workflow"] == "skill.update"
    assert compact["summary"]["update_status"] == "updated"
    assert compact["summary"]["changed_files"] == ["runtime/skills.json"]
    assert sha256_file(skills_path) != before_hashes[skills_path]
    assert sha256_file(evals_path) == before_hashes[evals_path]
    assert sha256_file(skill_body) == before_hashes[skill_body]
    route_decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    approval_proof = json.loads(Path(compact["artifacts"]["approval_proof"]).read_text(encoding="utf-8"))
    assert route_decision["selected_workflow"] == "skill.update"
    assert approval_proof["approval"]["skill_metadata_update"] is True


def test_workflow_router_chat_natural_skill_deprecation_requires_explicit_approval_without_mutation(
    tmp_path: Path,
) -> None:
    config_root = make_skill_registration_root(tmp_path)
    skills_path = config_root / "runtime" / "skills.json"
    evals_path = config_root / "runtime" / "skill_evals.json"
    before_hashes = {path: sha256_file(path) for path in (skills_path, evals_path)}
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / ".agentic_controller",
        allowed_target_roots=(config_root,),
        port=0,
    )
    prompt = "\n".join(
        [
            "Deprecate a skill through the lifecycle gate.",
            "skill_id: code-explanation-summarizer",
            "replacement_skill_id: behavior-existence-checker",
            "reason: Phase 49 natural deprecation request proves approval is required before mutation.",
            "effective_date: 2026-06-05",
        ]
    )

    with RunningControllerService(config) as service:
        host, port = service.base_url
        status, body = request_json(
            host,
            port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [{"role": "user", "content": prompt}],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    content = body["choices"][0]["message"]["content"]
    assert compact["workflow"] == "skill.deprecate"
    assert compact["status"] == "approval_required"
    assert compact["summary"]["required_approval"]["status"] == "approved_for_skill_deprecation"
    assert "missing_explicit_approval" in content
    assert {path: sha256_file(path) for path in (skills_path, evals_path)} == before_hashes
    route_decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    requirement = json.loads(Path(compact["artifacts"]["approval_requirement"]).read_text(encoding="utf-8"))
    assert route_decision["selected_workflow"] == "skill.deprecate"
    assert route_decision["approval_required"] is True
    assert requirement["proposed_request"]["skill_id"] == "code-explanation-summarizer"
