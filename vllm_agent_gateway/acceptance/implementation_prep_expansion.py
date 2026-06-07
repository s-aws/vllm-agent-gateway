"""Phase 96 implementation-prep expansion validation."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from vllm_agent_gateway.controller_service.server import chat_completion_response
from vllm_agent_gateway.controllers.workflow_router import plan as workflow_router_plan


SCHEMA_VERSION = 1
DEFAULT_CASES_PATH = Path("runtime") / "implementation_prep_expansion_cases.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "implementation-prep-expansion"
DEFAULT_MODEL_BASE_URL = "http://127.0.0.1:8000/v1"
DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_CONTROLLER_BASE_URL = "http://127.0.0.1:8400"
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_TARGET_ROOTS = (
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
)
WATCHED_RELATIVE_PATHS = (
    "README.md",
    "core/stealth_order_manager.py",
    "tests/unit/test_order_id_and_followup_rules.py",
    "tests/regression/test_order_id_regression.py",
)
TREE_DIGEST_EXCLUDED_DIRS = {".git"}


class ImplementationPrepExpansionStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ImplementationPrepExpansionConfig:
    config_root: Path
    cases_path: Path = DEFAULT_CASES_PATH
    output_path: Path | None = None
    target_roots: tuple[str, ...] = DEFAULT_TARGET_ROOTS
    include_direct: bool = True
    include_gateway: bool = False
    include_anythingllm: bool = False
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 900


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"implementation-prep-expansion-{utc_timestamp()}.json"


def resolve_path(config_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else config_root / path


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object at {path}")
    return value


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def check(
    check_id: str,
    status: ImplementationPrepExpansionStatus,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    next_action: str = "",
) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": status.value,
        "message": message,
        "details": details or {},
        "next_action": next_action,
    }


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
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            body = {"error": {"message": text, "code": "invalid_json_error_body"}}
        return exc.code, body


def text_response(body: dict[str, Any]) -> str:
    for key in ("textResponse", "response", "message"):
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
    raise RuntimeError("response did not include assistant text")


def run_id_from_text(text: str) -> str:
    marker = "run_id:"
    if marker not in text:
        return "unknown"
    return text.split(marker, 1)[1].strip().split()[0]


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def watched_hashes(target_root: str) -> dict[str, str]:
    root = Path(target_root)
    hashes: dict[str, str] = {}
    for relative_path in WATCHED_RELATIVE_PATHS:
        path = root / relative_path
        if path.exists():
            hashes[relative_path] = digest_file(path)
    if not hashes:
        raise RuntimeError(f"{target_root} did not contain any watched validation files")
    return hashes


def tree_digest(target_root: str) -> dict[str, Any]:
    root = Path(target_root)
    digest = hashlib.sha256()
    file_count = 0
    total_bytes = 0
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if any(part in TREE_DIGEST_EXCLUDED_DIRS for part in path.relative_to(root).parts):
            continue
        file_digest = digest_file(path)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_digest.encode("ascii"))
        digest.update(b"\0")
        file_count += 1
        total_bytes += path.stat().st_size
    return {"file_count": file_count, "total_bytes": total_bytes, "sha256": digest.hexdigest()}


def git_status(target_root: str) -> str | None:
    root = Path(target_root)
    if not (root / ".git").exists():
        return None
    result = subprocess.run(["git", "-C", target_root, "status", "--short"], check=True, capture_output=True, text=True)
    return result.stdout


def fixture_state(target_root: str) -> dict[str, Any]:
    return {"hashes": watched_hashes(target_root), "tree_digest": tree_digest(target_root), "git_status": git_status(target_root)}


def assert_fixture_state_unchanged(before: dict[str, Any] | None, target_root: str, label: str) -> dict[str, Any] | None:
    if before is None:
        return None
    after = fixture_state(target_root)
    if after != before:
        raise RuntimeError(f"{label} changed protected fixture state for {target_root}")
    return after


def is_protected_target(config: ImplementationPrepExpansionConfig, target_root: str) -> bool:
    resolved = str(Path(target_root).resolve())
    return any(str(Path(root).resolve()) == resolved for root in config.target_roots)


def protected_fixture_state(config: ImplementationPrepExpansionConfig, target_root: str) -> dict[str, Any] | None:
    return fixture_state(target_root) if is_protected_target(config, target_root) else None


def create_direct_fixture(config: ImplementationPrepExpansionConfig) -> str:
    root = config.config_root / DEFAULT_REPORT_DIR / "fixtures" / f"direct-{utc_timestamp()}"
    write_text(root / "README.md", "# Phase 96 direct fixture\n")
    write_text(
        root / "core" / "stealth_order_manager.py",
        "class StealthOrderManager:\n"
        "    def find_stealth_order_by_placed_order_id(self, placed_order_id):\n"
        "        return self._placed_order_index.get(placed_order_id)\n",
    )
    write_text(
        root / "tests" / "unit" / "test_order_id_and_followup_rules.py",
        "def test_find_stealth_order_by_placed_order_id_uses_index():\n"
        "    assert 'placed_order_id'\n",
    )
    return str(root)


def prompt_for_case(case: dict[str, Any], target_root: str) -> str:
    template = case.get("prompt_template")
    if not isinstance(template, str):
        raise RuntimeError(f"{case.get('case_id')} missing prompt_template")
    return template.format(target_root=target_root)


def initial_prompt_for_case(case: dict[str, Any], target_root: str) -> str:
    template = case.get("initial_prompt_template")
    if not isinstance(template, str):
        raise RuntimeError(f"{case.get('case_id')} missing initial_prompt_template")
    return template.format(target_root=target_root)


def followup_prompt_for_case(case: dict[str, Any], run_id: str) -> str:
    template = case.get("followup_prompt_template")
    if not isinstance(template, str):
        raise RuntimeError(f"{case.get('case_id')} missing followup_prompt_template")
    return template.format(run_id=run_id)


class FakeRoleEndpoint:
    def __init__(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}/v1"

    def __enter__(self) -> "FakeRoleEndpoint":
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
                request = json.loads(self.rfile.read(length).decode("utf-8"))
                content = "\n".join(
                    message.get("content", "")
                    for message in request.get("messages", [])
                    if isinstance(message, dict)
                )
                if "Propose exact draft-only implementation packet operations" in content:
                    response_content = json.dumps(
                        {
                            "packet_operations": [
                                {
                                    "kind": "replace_text",
                                    "path": "core/stealth_order_manager.py",
                                    "old": "    def find_stealth_order_by_placed_order_id(self, placed_order_id):",
                                    "new": (
                                        "    def find_stealth_order_by_placed_order_id(self, placed_order_id):\n"
                                        "        # phase 96 draft-only packet proposal marker"
                                    ),
                                }
                            ],
                            "blockers": [],
                            "rationale": "The old text is present in the supplied snippet.",
                        }
                    )
                else:
                    response_content = json.dumps(
                        {
                            "selected_workflow": "execution_planning.plan",
                            "confidence": "high",
                            "reason": "fake endpoint route",
                            "approval_required_before": [],
                        }
                    )
                data = json.dumps({"choices": [{"message": {"content": response_content}}]}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format: str, *args: object) -> None:
                return

        return Handler


def persist_direct_run_record(output_root: Path, result: Any) -> None:
    report = result.report if isinstance(result.report, dict) else {}
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    record = {
        "kind": "controller_run_record",
        "run_id": result.run_id,
        "workflow": result.workflow,
        "status": result.status.value,
        "summary": summary,
        "artifacts": result.artifact_paths,
        "created_at": utc_timestamp(),
        "updated_at": utc_timestamp(),
    }
    write_json(output_root / "controller-runs" / f"{result.run_id}.json", record)


def direct_result_response(result: Any) -> dict[str, Any]:
    report = result.report if isinstance(result.report, dict) else {}
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    warnings = report.get("warnings") if isinstance(report.get("warnings"), list) else []
    response = {
        "workflow": result.workflow,
        "status": result.status.value,
        "run_id": result.run_id,
        "summary": summary,
        "artifacts": result.artifact_paths,
        "warning_count": len(warnings),
        "warnings": warnings,
        "failure_count": len(result.failures),
        "failures": result.failures,
    }
    return chat_completion_response({"model": "agentic-workflow-router"}, response)


def run_direct_case(
    config: ImplementationPrepExpansionConfig,
    case: dict[str, Any],
    target_root: str,
) -> tuple[dict[str, Any], str, str]:
    output_root = config.config_root / DEFAULT_REPORT_DIR / "direct-artifacts" / case["case_id"].lower()
    with FakeRoleEndpoint() as endpoint:
        if case.get("kind") == "approved_investigation_packet_prep":
            initial = workflow_router_plan.invoke_workflow_router_plan(
                workflow_router_plan.WorkflowRouterPlanRequest(
                    config_root=config.config_root,
                    target_root=target_root,
                    output_root=output_root,
                    user_request=initial_prompt_for_case(case, target_root),
                    mode="execute_read_only",
                    budgets={"max_model_calls": 0, "max_selected_skills": 5, "max_selected_tools": 5},
                )
            )
            persist_direct_run_record(output_root, initial)
            request = workflow_router_plan.WorkflowRouterPlanRequest(
                config_root=config.config_root,
                target_root=target_root,
                output_root=output_root,
                user_request=(
                    "Prepare implementation packet candidates from an approved read-only investigation. "
                    "Implementation objective: add a draft-only marker beside find_stealth_order_by_placed_order_id "
                    "in core/stealth_order_manager.py. Use draft mode only and do not mutate source files."
                ),
                mode="implementation_prep",
                approval={
                    "status": "approved_for_packet_design",
                    "scope": "packet_design_only",
                    "apply_allowed": False,
                    "approval_refs": [f"direct_approved_investigation:{initial.run_id}"],
                },
                context={
                    "bounded_context": [
                        {
                            "source": "workflow_router_natural_approved_investigation_packet_prep",
                            "approved_run_id": initial.run_id,
                            "packet_objective": (
                                "add a draft-only marker beside find_stealth_order_by_placed_order_id "
                                "in core/stealth_order_manager.py"
                            ),
                        }
                    ]
                },
                role_base_url=endpoint.base_url,
                execution_budgets={
                    "max_context_requests": 5,
                    "max_files": 10,
                    "max_records": 50,
                    "max_model_calls": 12,
                    "max_output_tokens": 4600,
                },
            )
        else:
            user_request = prompt_for_case(case, target_root)
            instruction = workflow_router_plan.extract_small_text_edit_instruction(user_request)
            if instruction is None:
                raise RuntimeError(f"{case['case_id']} did not produce a small text edit instruction")
            request = workflow_router_plan.WorkflowRouterPlanRequest(
                config_root=config.config_root,
                target_root=target_root,
                output_root=output_root,
                user_request=(
                    f"{user_request} Use draft mode only, do not mutate the target repository, "
                    "and produce exact packet operations only from the named target file."
                ),
                mode="implementation_prep",
                approval={
                    "status": "approved_for_packet_design",
                    "scope": "draft_text_edit_packet_design_only",
                    "apply_allowed": False,
                    "approval_refs": ["phase96_direct_small_text"],
                },
                context={
                    "allowed_context_tools": ["structure_index", "git_grep", "read_file", "manual"],
                    "bounded_context": [
                        {
                            "source": "workflow_router_natural_small_text_edit",
                            "small_text_edit": instruction,
                        }
                    ],
                },
                role_base_url=endpoint.base_url,
                execution_budgets={
                    "max_context_requests": 5,
                    "max_files": 10,
                    "max_records": 50,
                    "max_model_calls": 12,
                    "max_output_tokens": 4600,
                },
            )
        result = workflow_router_plan.invoke_workflow_router_plan(request)
    body = direct_result_response(result)
    text = text_response(body)
    record = body.get("agentic_controller_response")
    if not isinstance(record, dict):
        raise RuntimeError("direct workflow-router response did not include controller response")
    return record, text, result.run_id


def controller_run_record(config: ImplementationPrepExpansionConfig, run_id: str) -> dict[str, Any]:
    status, body = json_request(
        f"{config.controller_base_url.rstrip('/')}/v1/controller/runs/{run_id}",
        timeout_seconds=config.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"controller run lookup returned HTTP {status} for {run_id}: {json.dumps(body, ensure_ascii=True)}")
    return body


def gateway_chat(config: ImplementationPrepExpansionConfig, message: str) -> tuple[dict[str, Any], str, str]:
    status, body = json_request(
        f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": message}],
            "role_base_url": config.model_base_url,
            "budgets": {"max_model_calls": 3, "max_selected_skills": 5, "max_selected_tools": 5},
        },
        timeout_seconds=config.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"gateway returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    run_id = run_id_from_text(text)
    if run_id == "unknown":
        raise RuntimeError("gateway response did not include a workflow-router run_id")
    record = controller_run_record(config, run_id)
    return record, text, run_id


def anythingllm_chat(
    config: ImplementationPrepExpansionConfig,
    message: str,
    *,
    api_key: str,
    session_prefix: str,
) -> tuple[dict[str, Any], str, str]:
    status, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={
            "message": message,
            "mode": "chat",
            "sessionId": f"{session_prefix}-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=config.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"AnythingLLM returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    run_id = run_id_from_text(text)
    if run_id == "unknown":
        raise RuntimeError("AnythingLLM response did not include a workflow-router run_id")
    record = controller_run_record(config, run_id)
    return record, text, run_id


def artifact_json(record: dict[str, Any], key: str) -> dict[str, Any]:
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    path = artifacts.get(key)
    if not isinstance(path, str):
        raise RuntimeError(f"run record missing artifact {key}")
    return read_json_object(Path(path))


def optional_artifact_json(record: dict[str, Any], key: str) -> dict[str, Any] | None:
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    path = artifacts.get(key)
    if not isinstance(path, str):
        return None
    try:
        return read_json_object(Path(path))
    except (OSError, RuntimeError, json.JSONDecodeError):
        return None


def command_texts(commands: object) -> list[str]:
    values: list[str] = []
    if not isinstance(commands, list):
        return values
    for command in commands:
        if isinstance(command, dict):
            raw = command.get("command")
        else:
            raw = command
        if isinstance(raw, list) and all(isinstance(part, str) for part in raw):
            values.append(" ".join(raw))
        elif isinstance(raw, str):
            values.append(raw)
    return values


def operation_targets(operations: object) -> list[dict[str, Any]]:
    if not isinstance(operations, list):
        return []
    targets: list[dict[str, Any]] = []
    for operation in operations:
        if not isinstance(operation, dict):
            continue
        targets.append(
            {
                "kind": operation.get("kind"),
                "path": operation.get("path"),
                "old_length": len(operation.get("old")) if isinstance(operation.get("old"), str) else None,
                "new_length": len(operation.get("new")) if isinstance(operation.get("new"), str) else None,
                "content_length": len(operation.get("content")) if isinstance(operation.get("content"), str) else None,
            }
        )
    return targets


def run_proof_details(
    *,
    record: dict[str, Any],
    case: dict[str, Any],
    text: str,
    run_id: str,
    decision: dict[str, Any],
    fixture_before: dict[str, Any] | None,
    fixture_after: dict[str, Any] | None,
) -> dict[str, Any]:
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    summary = record.get("summary") if isinstance(record.get("summary"), dict) else {}
    proposal_key = case.get("expected_proposal_artifact")
    proposal = optional_artifact_json(record, proposal_key) if isinstance(proposal_key, str) else None
    downstream_run_state = optional_artifact_json(record, "downstream_run_state") or {}
    downstream_summary = (
        downstream_run_state.get("summary") if isinstance(downstream_run_state.get("summary"), dict) else {}
    )
    downstream_verification_plan = optional_artifact_json(record, "downstream_verification_plan") or {}
    proposal_commands = command_texts(proposal.get("verification_commands") if isinstance(proposal, dict) else None)
    downstream_commands = command_texts(downstream_verification_plan.get("verification_commands"))
    operations = proposal.get("packet_operations") if isinstance(proposal, dict) else []
    return {
        "case_id": case["case_id"],
        "run_id": run_id,
        "route_status": decision.get("status"),
        "selected_workflow": decision.get("selected_workflow"),
        "next_action": decision.get("next_action"),
        "summary_source_changed": summary.get("source_changed"),
        "downstream_repo_mutated": downstream_summary.get("repo_mutated"),
        "downstream_verification_command_count": downstream_summary.get("verification_command_count"),
        "proposal_artifact_key": proposal_key,
        "proposal_status": proposal.get("status") if isinstance(proposal, dict) else None,
        "proposal_operation_targets": operation_targets(operations),
        "proposal_verification_commands": proposal_commands,
        "downstream_verification_commands": downstream_commands,
        "implementation_workflow_report": artifacts.get("downstream_implementation_workflow_report"),
        "downstream_run_state": artifacts.get("downstream_run_state"),
        "route_decision": artifacts.get("route_decision"),
        "artifact_paths": artifacts,
        "chat_excerpt": text[:2000],
        "fixture_state_before": fixture_before,
        "fixture_state_after": fixture_after,
        "fixture_state_unchanged": fixture_before == fixture_after if fixture_before is not None else None,
    }


def assert_chat_markers(text: str, case: dict[str, Any], label: str) -> None:
    missing = [
        marker
        for marker in ["workflow_router.plan", "run_id: workflow-router-", "Draft proposal:", "Source mutation: false"]
        + string_list(case.get("required_chat_markers"))
        if marker not in text
    ]
    if missing:
        raise RuntimeError(f"{label} missing chat markers for {case['case_id']}: {missing}")


def assert_record_matches_case(record: dict[str, Any], case: dict[str, Any], text: str, label: str) -> dict[str, Any]:
    assert_chat_markers(text, case, label)
    decision = artifact_json(record, "route_decision")
    if decision.get("status") != case.get("expected_route_status"):
        raise RuntimeError(f"{label} route status mismatch: {decision.get('status')}")
    if decision.get("selected_workflow") != case.get("expected_selected_workflow"):
        raise RuntimeError(f"{label} workflow mismatch: {decision.get('selected_workflow')}")
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    proposal_key = case.get("expected_proposal_artifact")
    if not isinstance(proposal_key, str) or proposal_key not in artifacts:
        raise RuntimeError(f"{label} missing proposal artifact {proposal_key}")
    if "downstream_implementation_workflow_report" not in artifacts:
        raise RuntimeError(f"{label} missing downstream implementation workflow report")
    proposal = artifact_json(record, proposal_key)
    if proposal.get("status") != "ready":
        raise RuntimeError(f"{label} proposal status mismatch: {proposal.get('status')}")
    operations = proposal.get("packet_operations")
    if not isinstance(operations, list) or not operations:
        raise RuntimeError(f"{label} proposal did not include packet operations")
    verification_plan = optional_artifact_json(record, "downstream_verification_plan") or {}
    verification_commands = command_texts(proposal.get("verification_commands")) + command_texts(
        verification_plan.get("verification_commands")
    )
    if not verification_commands:
        raise RuntimeError(f"{label} did not include proposal or downstream verification commands")
    operation_kinds = [operation.get("kind") for operation in operations if isinstance(operation, dict)]
    for expected_kind in string_list(case.get("expected_operation_kinds")):
        if expected_kind not in operation_kinds:
            raise RuntimeError(f"{label} missing operation kind {expected_kind}: {operation_kinds}")
    expected_source_artifact_key = case.get("expected_source_artifact_key")
    if isinstance(expected_source_artifact_key, str) and proposal.get("source_artifact_key") != expected_source_artifact_key:
        raise RuntimeError(f"{label} source artifact mismatch: {proposal.get('source_artifact_key')}")
    summary = record.get("summary") if isinstance(record.get("summary"), dict) else {}
    if summary.get("source_changed") is not False:
        raise RuntimeError(f"{label} did not prove source_changed=false")
    run_state = artifact_json(record, "downstream_run_state")
    if run_state.get("summary", {}).get("repo_mutated") is not False:
        raise RuntimeError(f"{label} downstream run_state did not prove repo_mutated=false")
    return decision


def run_live_case(
    config: ImplementationPrepExpansionConfig,
    case: dict[str, Any],
    target_root: str,
    *,
    surface: str,
    api_key: str | None = None,
) -> tuple[dict[str, Any], str, str]:
    if case.get("kind") == "approved_investigation_packet_prep":
        initial_message = initial_prompt_for_case(case, target_root)
        if surface == "gateway":
            initial_record, _initial_text, initial_run_id = gateway_chat(config, initial_message)
        else:
            assert api_key is not None
            initial_record, _initial_text, initial_run_id = anythingllm_chat(
                config,
                initial_message,
                api_key=api_key,
                session_prefix=f"phase96-initial-{case['case_id'].lower()}",
            )
        artifacts = initial_record.get("artifacts") if isinstance(initial_record.get("artifacts"), dict) else {}
        if "downstream_investigation_plan" not in artifacts:
            raise RuntimeError(f"{surface} initial run missing downstream_investigation_plan")
        message = followup_prompt_for_case(case, initial_run_id)
    else:
        message = prompt_for_case(case, target_root)
    if surface == "gateway":
        return gateway_chat(config, message)
    assert api_key is not None
    return anythingllm_chat(config, message, api_key=api_key, session_prefix=f"phase96-{case['case_id'].lower()}")


def validate_catalog(catalog: dict[str, Any], *, cases_path: Path) -> list[dict[str, Any]]:
    errors: list[str] = []
    if catalog.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if catalog.get("kind") != "implementation_prep_expansion_cases":
        errors.append("kind must be implementation_prep_expansion_cases")
    if catalog.get("phase") != 96:
        errors.append("phase must be 96")
    cases = object_list(catalog.get("cases"))
    if len(cases) < 2:
        errors.append("cases must include at least two Phase 96 prompt families")
    for case in cases:
        for key in ("case_id", "kind", "expected_route_status", "expected_selected_workflow", "expected_proposal_artifact"):
            if not isinstance(case.get(key), str) or not case.get(key):
                errors.append(f"{case.get('case_id', '<missing>')}.{key} must be a non-empty string")
        if case.get("kind") == "approved_investigation_packet_prep":
            for key in ("initial_prompt_template", "followup_prompt_template"):
                if "{run_id}" not in str(case.get(key)) and key == "followup_prompt_template":
                    errors.append(f"{case.get('case_id')}.{key} must include {{run_id}}")
                if key == "initial_prompt_template" and "{target_root}" not in str(case.get(key)):
                    errors.append(f"{case.get('case_id')}.{key} must include {{target_root}}")
        elif "{target_root}" not in str(case.get("prompt_template")):
            errors.append(f"{case.get('case_id')}.prompt_template must include {{target_root}}")
        if case.get("mutation_policy") != "draft_only_no_source_mutation":
            errors.append(f"{case.get('case_id')}.mutation_policy must be draft_only_no_source_mutation")
    return [
        check(
            "catalog.contract",
            ImplementationPrepExpansionStatus.FAILED if errors else ImplementationPrepExpansionStatus.PASSED,
            "Implementation-prep expansion case catalog is valid." if not errors else "Catalog validation failed.",
            details={"cases_path": str(cases_path), "case_count": len(cases), "errors": errors},
            next_action="" if not errors else "Fix runtime/implementation_prep_expansion_cases.json.",
        )
    ]


def run_case_check(
    *,
    config: ImplementationPrepExpansionConfig,
    label: str,
    case: dict[str, Any],
    target_root: str,
    runner: Any,
) -> dict[str, Any]:
    before = protected_fixture_state(config, target_root)
    try:
        record_or_decision, text, run_id = runner()
        if "artifacts" in record_or_decision:
            decision = assert_record_matches_case(record_or_decision, case, text, label)
            after = assert_fixture_state_unchanged(before, target_root, f"{label} {case['case_id']}")
            details = run_proof_details(
                record=record_or_decision,
                case=case,
                text=text,
                run_id=run_id,
                decision=decision,
                fixture_before=before,
                fixture_after=after,
            )
        else:
            decision = record_or_decision
            assert_chat_markers(text, case, label)
            after = assert_fixture_state_unchanged(before, target_root, f"{label} {case['case_id']}")
            details = {
                "case_id": case["case_id"],
                "target_root": target_root,
                "run_id": run_id,
                "selected_workflow": decision.get("selected_workflow"),
                "route_status": decision.get("status"),
                "chat_excerpt": text[:2000],
                "fixture_state_before": before,
                "fixture_state_after": after,
                "fixture_state_unchanged": before == after if before is not None else None,
            }
        details["target_root"] = target_root
        details["surface"] = label
        return check(
            f"{label}.{case['case_id']}.{Path(target_root).name}",
            ImplementationPrepExpansionStatus.PASSED,
            f"{label} implementation-prep case passed for {case['case_id']} on {target_root}.",
            details=details,
        )
    except Exception as exc:  # noqa: BLE001 - acceptance reports should classify all failures
        return check(
            f"{label}.{case.get('case_id', 'unknown')}.{Path(target_root).name}",
            ImplementationPrepExpansionStatus.FAILED,
            f"{label} implementation prep failed: {type(exc).__name__}: {exc}",
            details={"case_id": case.get("case_id"), "target_root": target_root},
            next_action="Inspect route_decision, proposal artifact, downstream run_state, chat text, and fixture hashes.",
        )


def runtime_surface_checks(config: ImplementationPrepExpansionConfig, api_key: str | None) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    probes: list[tuple[str, str, dict[str, str] | None]] = [
        ("runtime.model_8000", f"{config.model_base_url.rstrip('/')}/models", None),
        ("runtime.workflow_router_gateway_8500", f"{config.workflow_router_gateway_base_url.rstrip('/')}/models", None),
        ("runtime.controller_8400", f"{config.controller_base_url.rstrip('/')}/health", None),
    ]
    if config.include_anythingllm and api_key:
        probes.append(
            (
                "runtime.anythingllm_workspaces",
                f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspaces",
                {"Authorization": f"Bearer {api_key}"},
            )
        )
    for check_id, url, headers in probes:
        try:
            status, body = json_request(url, headers=headers, timeout_seconds=min(config.timeout_seconds, 30))
            passed = status == 200
            details: dict[str, Any] = {"url": url, "http_status": status}
            if check_id == "runtime.controller_8400" and isinstance(body, dict):
                details["controller_status"] = body.get("status")
                details["allowed_target_roots"] = body.get("allowed_target_roots")
            elif check_id == "runtime.anythingllm_workspaces":
                workspaces = body.get("workspaces") if isinstance(body, dict) else body
                slugs: list[str] = []
                if isinstance(workspaces, list):
                    for workspace in workspaces:
                        if isinstance(workspace, dict) and isinstance(workspace.get("slug"), str):
                            slugs.append(workspace["slug"])
                details["workspace"] = config.workspace
                details["workspace_found"] = config.workspace in slugs
                passed = passed and details["workspace_found"]
            checks.append(
                check(
                    check_id,
                    ImplementationPrepExpansionStatus.PASSED if passed else ImplementationPrepExpansionStatus.FAILED,
                    f"Runtime surface {check_id} is reachable." if passed else f"Runtime surface {check_id} failed.",
                    details=details,
                    next_action="" if passed else "Restart the Bash-hosted controller/gateway stack and rerun validation.",
                )
            )
        except Exception as exc:  # noqa: BLE001 - classify runtime proof failures in report
            checks.append(
                check(
                    check_id,
                    ImplementationPrepExpansionStatus.FAILED,
                    f"Runtime surface {check_id} failed: {type(exc).__name__}: {exc}",
                    details={"url": url},
                    next_action="Restart the Bash-hosted controller/gateway stack and rerun validation.",
                )
            )
    return checks


def validate_implementation_prep_expansion(config: ImplementationPrepExpansionConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    cases_path = resolve_path(config_root, config.cases_path)
    output_path = config.output_path or default_report_path(config_root)
    catalog = read_json_object(cases_path)
    cases = object_list(catalog.get("cases"))
    direct_target = create_direct_fixture(ImplementationPrepExpansionConfig(**{**config.__dict__, "config_root": config_root}))
    checks: list[dict[str, Any]] = []
    api_key = os.environ.get(config.api_key_env) if config.include_anythingllm else None
    checks.extend(validate_catalog(catalog, cases_path=cases_path))
    if config.include_gateway or config.include_anythingllm:
        checks.extend(runtime_surface_checks(config, api_key))
    if config.include_direct:
        for case in cases:
            checks.append(
                run_case_check(
                    config=config,
                    label="direct",
                    case=case,
                    target_root=direct_target,
                    runner=lambda case=case: run_direct_case(config, case, direct_target),
                )
            )
    if config.include_gateway:
        for case in cases:
            for target_root in config.target_roots:
                checks.append(
                    run_case_check(
                        config=config,
                        label="gateway",
                        case=case,
                        target_root=target_root,
                        runner=lambda case=case, target_root=target_root: run_live_case(
                            config,
                            case,
                            target_root,
                            surface="gateway",
                        ),
                )
            )
    if config.include_anythingllm:
        if not api_key:
            checks.append(
                check(
                    "anythingllm.api_key",
                    ImplementationPrepExpansionStatus.FAILED,
                    f"{config.api_key_env} is not set.",
                    next_action="Export the AnythingLLM API key before live AnythingLLM validation.",
                )
            )
        else:
            for case in cases:
                for target_root in config.target_roots:
                    checks.append(
                        run_case_check(
                            config=config,
                            label="AnythingLLM",
                            case=case,
                            target_root=target_root,
                            runner=lambda case=case, target_root=target_root: run_live_case(
                                config,
                                case,
                                target_root,
                                surface="anythingllm",
                                api_key=api_key,
                            ),
                        )
                    )
    failed = [item for item in checks if item["status"] == ImplementationPrepExpansionStatus.FAILED.value]
    report = {
        "kind": "implementation_prep_expansion_report",
        "schema_version": SCHEMA_VERSION,
        "phase": 96,
        "status": "failed" if failed else "passed",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "config_root": str(config_root),
        "cases_path": str(cases_path),
        "report_path": str(output_path),
        "target_roots": list(config.target_roots),
        "generated_fixtures": {"direct": direct_target},
        "checks": checks,
        "summary": {
            "case_count": len(cases),
            "check_count": len(checks),
            "failed_check_ids": [item["id"] for item in failed],
            "direct_enabled": config.include_direct,
            "gateway_enabled": config.include_gateway,
            "anythingllm_enabled": config.include_anythingllm,
        },
    }
    write_json(output_path, report)
    return report
