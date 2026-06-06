#!/usr/bin/env python3
"""Validate the L2 workflow-router prompt suite through gateway and AnythingLLM."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_TARGET_ROOTS = [
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
]
WATCHED_RELATIVE_PATHS = [
    "agent.md",
    "configuration.py",
    "dashboard_server.py",
    "core/stealth_order_manager.py",
    "database/order.py",
    "docs/agents/INVARIANTS.md",
    "tests/test_dashboard_handler.py",
    "tests/unit/test_order_id_and_followup_rules.py",
]


@dataclass(frozen=True)
class L2Case:
    case_id: str
    name: str
    selected_workflow: str
    downstream_workflow: str
    artifact_keys: tuple[str, ...]
    markers: tuple[str, ...]
    prompt_template: str

    def prompt(self, target_root: str) -> str:
        return self.prompt_template.format(target_root=target_root)


L2_CASES: tuple[L2Case, ...] = (
    L2Case(
        case_id="L2-001",
        name="Diagnose Failing Test And Recommend Safe Fix Plan",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_test_failure_summary",),
        markers=(
            "Answer:",
            "Failed tests:",
            "Root cause hypothesis:",
            "Smallest safe fix plan:",
            "Verification:",
            "python -m pytest tests/unit/test_order_id_and_followup_rules.py::",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, diagnose why this pytest failure is happening. "
            "Do not edit files. Return root cause, smallest safe fix plan, and verification command.\n"
            "FAILED tests/unit/test_order_id_and_followup_rules.py::"
            "test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - "
            "AssertionError: expected client_order_id index\n"
            "E   AssertionError: expected client_order_id index"
        ),
    ),
    L2Case(
        case_id="L2-002",
        name="Investigate Multi-File Behavior",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_multi_file_behavior_investigation",),
        markers=(
            "Answer:",
            "Beginning point:",
            "Participating files:",
            "core/",
            "Callers/usages:",
            "Related tests:",
            "Risks:",
            "Verification:",
            "python -m pytest",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, investigate how placed_order_id stealth lookup flows across source files. "
            "Read only. Return the beginning point, participating files, callers/usages, related tests, "
            "risks, and the smallest verification commands."
        ),
    ),
    L2Case(
        case_id="L2-003",
        name="Summarize Dependency Impact",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_dependency_impact_summary",),
        markers=(
            "Answer:",
            "Impacted files:",
            "core/",
            "Callers/usages:",
            "Related tests:",
            "Risk level:",
            "Verification:",
            "python -m pytest",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, summarize the dependency impact if placed_order_id stealth lookup behavior changes. "
            "Read only. Return impacted source files, callers/usages, related tests, risk level, "
            "and recommended validation commands."
        ),
    ),
    L2Case(
        case_id="L2-005",
        name="Test Selection With Rationale",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_test_selection_plan",),
        markers=(
            "Answer:",
            "Smallest command:",
            "Medium command:",
            "Broad command:",
            "Rationale:",
            "Covered risks:",
            "Confidence:",
            "Gaps:",
            "python -m pytest",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, choose the smallest, medium, and broad validation commands "
            "for placed_order_id stealth lookup. Read only. Explain why each command is relevant, "
            "what risk it covers, and what gaps remain."
        ),
    ),
    L2Case(
        case_id="L2-006",
        name="Diagnose Runtime Error Or Stack Trace",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_runtime_error_diagnosis",),
        markers=(
            "Answer:",
            "Observed error:",
            "WebSocketMessageError",
            "Likely cause:",
            "Evidence files:",
            "dashboard_server.py",
            "Next inspection:",
            "Verification:",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, diagnose this runtime stack trace for request_stealth_orders dashboard behavior. "
            "Read only. Return observed error, likely cause, evidence files, next inspection steps, risks, gaps, "
            "and verification commands.\n"
            "Traceback (most recent call last):\n"
            "  File \"dashboard_server.py\", line 10, in handle_websocket_message\n"
            "core.exceptions.WebSocketMessageError: Missing 'type' field in message"
        ),
    ),
    L2Case(
        case_id="L2-007",
        name="Map Request Or Data Flow",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_request_flow_map",),
        markers=(
            "Answer:",
            "Target flow:",
            "request_stealth_orders",
            "Flow steps:",
            "dashboard_server.py",
            "Participating files:",
            "Verification:",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, map the request/data flow for request_stealth_orders from dashboard message "
            "to stealth order snapshot. Read only. Return flow steps, participating files, risks, gaps, "
            "and verification commands."
        ),
    ),
    L2Case(
        case_id="L2-008",
        name="Compare Two Candidate Code Paths",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_code_path_comparison",),
        markers=(
            "Answer:",
            "Comparison target:",
            "placed_order_id",
            "Candidate paths:",
            "client_order_id",
            "Recommended path:",
            "Risks:",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, compare the placed_order_id stealth lookup path with the client_order_id index path. "
            "Read only. Return candidate paths, evidence, risks, recommended path if supported, gaps, "
            "and verification commands."
        ),
    ),
    L2Case(
        case_id="L2-009",
        name="Identify Minimal Safe Change Surface",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_change_surface_summary",),
        markers=(
            "Answer:",
            "Change surface files:",
            "core/stealth_order_manager.py",
            "Risk level:",
            "Implementation status: not_ready_without_approval",
            "Verification:",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, identify the minimal safe change surface for changing placed_order_id stealth lookup behavior. "
            "Read only. Return files that would need review, related tests, risk level, gaps, and verification commands. "
            "Stop before implementation."
        ),
    ),
)


def selected_cases(case_ids: list[str] | None) -> tuple[L2Case, ...]:
    if not case_ids:
        return L2_CASES
    allowed = {case_id.upper() for case_id in case_ids}
    cases = tuple(case for case in L2_CASES if case.case_id.upper() in allowed)
    missing = sorted(allowed - {case.case_id.upper() for case in cases})
    if missing:
        raise RuntimeError(f"unknown L2 case id(s): {', '.join(missing)}")
    return cases


def json_request(
    url: str,
    *,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout_seconds: int,
) -> tuple[int, dict[str, Any]]:
    request_headers = dict(headers or {})
    request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=True).encode("utf-8"),
        headers=request_headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(body_text)
        except json.JSONDecodeError:
            body = {"error": {"message": body_text, "code": "invalid_json_error_body"}}
        return exc.code, body


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


def git_status(target_root: str) -> str | None:
    root = Path(target_root)
    if not (root / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "-C", target_root, "status", "--short"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


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


def require_text_markers(text: str, markers: tuple[str, ...], *, label: str, target_root: str, case: L2Case) -> None:
    common_markers = (
        "I completed workflow_router.plan.",
        "workflow_router.plan completed",
        "run_id: workflow-router-",
        "Result:",
        "- Selected workflow:",
        "- Selected skills:",
        "- Selected tools:",
        "- Next action:",
        "- Verification:",
        f"selected_workflow: {case.selected_workflow}",
        "Artifacts:",
    )
    missing = [marker for marker in (*common_markers, *markers) if marker not in text]
    if missing:
        raise RuntimeError(
            f"{label} missing markers for {case.case_id} on {target_root}: "
            f"{json.dumps(missing, ensure_ascii=True)}"
        )


def require_gateway_response(body: dict[str, Any], target_root: str, case: L2Case) -> str:
    compact = body.get("agentic_controller_response")
    if not isinstance(compact, dict):
        raise RuntimeError(f"gateway response did not include agentic_controller_response for {case.case_id} on {target_root}")
    if compact.get("workflow") != "workflow_router.plan":
        raise RuntimeError(f"gateway returned unexpected workflow for {case.case_id}: {compact.get('workflow')!r}")
    if compact.get("status") != "completed":
        raise RuntimeError(f"gateway did not complete {case.case_id}: {compact.get('status')!r}")
    summary = compact.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError(f"gateway response did not include summary for {case.case_id} on {target_root}")
    expected = {
        "route_status": "ready",
        "selected_workflow": case.selected_workflow,
        "downstream_workflow": case.downstream_workflow,
        "downstream_status": "completed",
    }
    wrong = {
        key: {"expected": expected_value, "actual": summary.get(key)}
        for key, expected_value in expected.items()
        if summary.get(key) != expected_value
    }
    if wrong:
        raise RuntimeError(
            f"gateway response summary mismatch for {case.case_id} on {target_root}: "
            f"{json.dumps(wrong, sort_keys=True)}"
        )
    artifacts = compact.get("artifacts")
    if not isinstance(artifacts, dict):
        raise RuntimeError(f"gateway response did not include artifacts for {case.case_id} on {target_root}")
    missing_artifacts = [key for key in case.artifact_keys if key not in artifacts]
    if missing_artifacts:
        raise RuntimeError(
            f"gateway response missing artifacts for {case.case_id} on {target_root}: "
            f"{json.dumps(missing_artifacts, ensure_ascii=True)}"
        )
    text = text_response(body)
    require_text_markers(text, case.markers, label="gateway", target_root=target_root, case=case)
    return text


def validate_unchanged(target_root: str, before_hashes: dict[str, str], before_status: str | None, label: str) -> None:
    after_hashes = watched_hashes(target_root)
    if after_hashes != before_hashes:
        raise RuntimeError(f"{label} mutated watched files for {target_root}")
    after_status = git_status(target_root)
    if before_status is not None and after_status != before_status:
        raise RuntimeError(f"{label} changed git status for {target_root}: {after_status!r}")


def validate_gateway(args: argparse.Namespace, target_root: str, case: L2Case) -> dict[str, str]:
    before_hashes = watched_hashes(target_root)
    before_status = git_status(target_root)
    status, body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": case.prompt(target_root)}],
        },
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(
            f"gateway returned HTTP {status} for {case.case_id} on {target_root}: "
            f"{json.dumps(body, ensure_ascii=True)}"
        )
    text = require_gateway_response(body, target_root, case)
    validate_unchanged(target_root, before_hashes, before_status, f"gateway {case.case_id}")
    run_id = run_id_from_text(text)
    print(f"L2 SUITE GATEWAY PASS case={case.case_id} target={target_root} run_id={run_id}")
    return {"case_id": case.case_id, "target_root": target_root, "run_id": run_id}


def validate_anythingllm(args: argparse.Namespace, target_root: str, case: L2Case, api_key: str) -> dict[str, str]:
    before_hashes = watched_hashes(target_root)
    before_status = git_status(target_root)
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload={
            "message": case.prompt(target_root),
            "mode": "chat",
            "sessionId": f"workflow-router-l2-{case.case_id.lower()}-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(
            f"AnythingLLM returned HTTP {status} for {case.case_id} on {target_root}: "
            f"{json.dumps(body, ensure_ascii=True)}"
        )
    text = text_response(body)
    require_text_markers(text, case.markers, label="AnythingLLM", target_root=target_root, case=case)
    validate_unchanged(target_root, before_hashes, before_status, f"AnythingLLM {case.case_id}")
    run_id = run_id_from_text(text)
    print(f"L2 SUITE ANYTHINGLLM PASS case={case.case_id} target={target_root} run_id={run_id}")
    return {"case_id": case.case_id, "target_root": target_root, "run_id": run_id}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--skip-anythingllm", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_roots = args.target_roots or DEFAULT_TARGET_ROOTS
    cases = selected_cases(args.case_ids)
    summary: dict[str, Any] = {
        "gateway": [],
        "anythingllm": [],
        "target_roots": target_roots,
        "case_ids": [case.case_id for case in cases],
    }
    for target_root in target_roots:
        for case in cases:
            summary["gateway"].append(validate_gateway(args, target_root, case))
    if not args.skip_anythingllm:
        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            raise RuntimeError(f"{args.api_key_env} is required unless --skip-anythingllm is set")
        for target_root in target_roots:
            for case in cases:
                summary["anythingllm"].append(validate_anythingllm(args, target_root, case, api_key))
    print("L2 SUITE SUMMARY")
    print(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
