#!/usr/bin/env python3
"""Validate natural-language workflow-router clients through gateway and AnythingLLM."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_TARGET_ROOTS = [
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
]
INVARIANT_REL = "docs/agents/INVARIANTS.md"


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
            body = json.loads(response.read().decode("utf-8"))
            return response.status, body
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(body_text)
        except json.JSONDecodeError:
            body = {"error": {"message": body_text, "code": "invalid_json_error_body"}}
        return exc.code, body


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def target_hash(target_root: str) -> str:
    path = Path(target_root) / INVARIANT_REL
    if not path.exists():
        raise RuntimeError(f"target is missing required validation file: {path}")
    return file_digest(path)


def invariant_replace_operation(target_root: str) -> dict[str, Any]:
    path = Path(target_root) / INVARIANT_REL
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    old_lines: list[str] = []
    for index, line in enumerate(lines):
        if line.startswith("- Use `client_order_id` for internal tracking"):
            old_lines.append(line)
            for continuation in lines[index + 1 :]:
                if continuation.startswith("  "):
                    old_lines.append(continuation)
                    continue
                break
            break
    if not old_lines:
        raise RuntimeError(f"could not find invariant block in {path}")
    old = "\n".join(old_lines)
    new = old + "\n  natural approval continuation dry-run proof only."
    return {"kind": "replace_text", "path": INVARIANT_REL, "old": old, "new": new}


def natural_request(target_root: str) -> str:
    return (
        f"In {target_root}, refactor the placed_order_id stealth lookup so there is only one code path. "
        "Start from the logic beginning point, investigate first, create an implementation plan, "
        "wait for approval before implementation prep, and provide verification commands."
    )


def require_workflow_router_response(response: dict[str, Any], target_root: str, label: str) -> dict[str, Any]:
    compact = response.get("agentic_controller_response")
    if not isinstance(compact, dict):
        raise RuntimeError(f"{label} did not include agentic_controller_response for {target_root}")
    if compact.get("workflow") != "workflow_router.plan":
        raise RuntimeError(f"{label} returned unexpected workflow: {compact.get('workflow')!r}")
    if compact.get("status") != "completed":
        raise RuntimeError(f"{label} did not complete: {compact.get('status')!r}")
    summary = compact.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError(f"{label} did not include a summary object")
    expected = {
        "route_status": "ready",
        "selected_workflow": "refactor.single_path",
        "downstream_workflow": "refactor.single_path",
        "downstream_status": "completed",
        "target_repo_read": True,
    }
    wrong = {
        key: {"expected": expected_value, "actual": summary.get(key)}
        for key, expected_value in expected.items()
        if summary.get(key) != expected_value
    }
    if wrong:
        raise RuntimeError(f"{label} summary mismatch for {target_root}: {wrong!r}")
    verification_count = summary.get("verification_command_count")
    if not isinstance(verification_count, int) or verification_count < 1:
        raise RuntimeError(
            f"{label} did not report evidence-backed verification commands for {target_root}: "
            f"{verification_count!r}"
        )
    if str(Path(target_root).resolve()) not in str(summary.get("target_root")):
        raise RuntimeError(f"{label} summary target_root did not match {target_root}: {summary.get('target_root')!r}")
    artifacts = compact.get("artifacts")
    if not isinstance(artifacts, dict) or "route_decision" not in artifacts:
        raise RuntimeError(f"{label} did not include route_decision artifact")
    if "downstream_refactor_plan" not in artifacts:
        raise RuntimeError(f"{label} did not include downstream_refactor_plan artifact")
    return compact


def require_approval_continuation_response(
    response: dict[str, Any],
    target_root: str,
    label: str,
    *,
    expect_generated_packet_operations: bool = False,
    allow_generated_packet_block: bool = False,
) -> dict[str, Any]:
    compact = response.get("agentic_controller_response")
    if not isinstance(compact, dict):
        raise RuntimeError(f"{label} did not include agentic_controller_response for {target_root}")
    summary = compact.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError(f"{label} did not include a summary object")
    expected = {"selected_workflow": "execution_planning.plan"}
    if not (expect_generated_packet_operations and allow_generated_packet_block):
        expected.update(
            {
                "route_status": "ready",
                "downstream_workflow": "execution_planning.plan",
                "downstream_status": "completed",
            }
        )
    wrong = {
        key: {"expected": expected_value, "actual": summary.get(key)}
        for key, expected_value in expected.items()
        if summary.get(key) != expected_value
    }
    if wrong:
        raise RuntimeError(f"{label} continuation summary mismatch for {target_root}: {wrong!r}")
    artifacts = compact.get("artifacts")
    if not isinstance(artifacts, dict):
        raise RuntimeError(f"{label} continuation did not include artifacts")
    route_status = summary.get("route_status")
    if route_status == "blocked" and expect_generated_packet_operations and allow_generated_packet_block:
        if summary.get("next_action") != "request_packet_objective":
            raise RuntimeError(
                f"{label} blocked generated continuation did not request packet objective for {target_root}: "
                f"{summary.get('next_action')!r}"
            )
        if "packet_operation_proposal" not in artifacts:
            raise RuntimeError(f"{label} blocked generated continuation did not include packet_operation_proposal")
        return compact
    if "downstream_implementation_workflow_report" not in artifacts:
        raise RuntimeError(f"{label} continuation did not include downstream_implementation_workflow_report")
    if expect_generated_packet_operations and "packet_operation_proposal" not in artifacts:
        raise RuntimeError(f"{label} continuation did not include packet_operation_proposal")
    return compact


def require_packet_objective_followup_response(
    response: dict[str, Any],
    target_root: str,
    label: str,
    *,
    allow_packet_objective_block: bool,
) -> dict[str, Any]:
    compact = response.get("agentic_controller_response")
    if not isinstance(compact, dict):
        raise RuntimeError(f"{label} did not include agentic_controller_response for {target_root}")
    summary = compact.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError(f"{label} did not include a summary object")
    if summary.get("selected_workflow") != "execution_planning.plan":
        raise RuntimeError(
            f"{label} selected unexpected workflow for {target_root}: {summary.get('selected_workflow')!r}"
        )
    artifacts = compact.get("artifacts")
    if not isinstance(artifacts, dict) or "packet_operation_proposal" not in artifacts:
        raise RuntimeError(f"{label} did not include packet_operation_proposal for {target_root}")
    route_status = summary.get("route_status")
    if route_status == "blocked":
        if not allow_packet_objective_block:
            raise RuntimeError(f"{label} blocked for {target_root}: {summary!r}")
        if summary.get("next_action") not in {"request_packet_objective", "request_narrowed_edit_objective"}:
            raise RuntimeError(
                f"{label} blocked without packet objective next action for {target_root}: "
                f"{summary.get('next_action')!r}"
            )
        return compact
    if route_status == "ready" and summary.get("packet_objective_outcome_status") == "no_change_needed":
        return compact
    expected = {
        "route_status": "ready",
        "downstream_workflow": "execution_planning.plan",
        "downstream_status": "completed",
    }
    wrong = {
        key: {"expected": expected_value, "actual": summary.get(key)}
        for key, expected_value in expected.items()
        if summary.get(key) != expected_value
    }
    if wrong:
        raise RuntimeError(f"{label} packet-objective summary mismatch for {target_root}: {wrong!r}")
    if "downstream_implementation_workflow_report" not in artifacts:
        raise RuntimeError(f"{label} did not include downstream_implementation_workflow_report")
    return compact


def generated_narrowed_edit_objective() -> str:
    return (
        "change core/stealth_order_manager.py by replacing the comment above "
        "self._placed_order_index[placed_order_id] = order so it explicitly says "
        "Authoritative placed_order_id lookup source for all order_engine callers"
    )


def narrowed_edit_message(source_run_id: str, target_root: str, *, include_exact_operations: bool) -> str:
    objective = generated_narrowed_edit_objective()
    if not include_exact_operations:
        return f"For run {source_run_id}, narrowed edit objective: {objective}. Draft only."
    operation = invariant_replace_operation(target_root)
    return (
        f"For run {source_run_id}, narrowed edit objective: change {INVARIANT_REL} by adding the "
        "natural narrowed-edit dry-run proof line. Draft only. "
        f"Use packet operations: {json.dumps([operation], ensure_ascii=True)}"
    )


def require_narrowed_edit_followup_response(
    response: dict[str, Any],
    target_root: str,
    label: str,
    *,
    expect_generated_operations: bool,
    allow_generated_block: bool,
) -> dict[str, Any]:
    compact = response.get("agentic_controller_response")
    if not isinstance(compact, dict):
        raise RuntimeError(f"{label} did not include agentic_controller_response for {target_root}")
    summary = compact.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError(f"{label} did not include a summary object")
    expected = {
        "selected_workflow": "execution_planning.plan",
        "narrowed_edit_objective_status": "accepted",
    }
    if not (expect_generated_operations and allow_generated_block):
        expected.update(
            {
                "route_status": "ready",
                "downstream_workflow": "execution_planning.plan",
                "downstream_status": "completed",
            }
        )
    wrong = {
        key: {"expected": expected_value, "actual": summary.get(key)}
        for key, expected_value in expected.items()
        if summary.get(key) != expected_value
    }
    if wrong:
        raise RuntimeError(f"{label} narrowed-edit summary mismatch for {target_root}: {wrong!r}")
    artifacts = compact.get("artifacts")
    if not isinstance(artifacts, dict):
        raise RuntimeError(f"{label} did not include artifacts")
    if expect_generated_operations and "packet_operation_proposal" not in artifacts:
        raise RuntimeError(f"{label} did not include packet_operation_proposal")
    if summary.get("route_status") == "blocked":
        if not allow_generated_block:
            raise RuntimeError(f"{label} blocked for {target_root}: {summary!r}")
        allowed_next_actions = {"request_narrowed_edit_objective"}
        if expect_generated_operations:
            allowed_next_actions.add("retry_execution_planning")
        if summary.get("next_action") not in allowed_next_actions:
            raise RuntimeError(
                f"{label} blocked without an allowed generated-operation next action for {target_root}: "
                f"{summary.get('next_action')!r}"
            )
        if summary.get("next_action") == "retry_execution_planning":
            if summary.get("downstream_workflow") != "execution_planning.plan":
                raise RuntimeError(
                    f"{label} retry did not preserve downstream workflow for {target_root}: {summary!r}"
                )
            if summary.get("downstream_status") != "failed":
                raise RuntimeError(f"{label} retry did not mark downstream failed for {target_root}: {summary!r}")
        return compact
    if "downstream_implementation_workflow_report" not in artifacts:
        raise RuntimeError(f"{label} did not include downstream_implementation_workflow_report")
    return compact


def feedback_message(initial_run_id: str, continuation_run_id: str | None) -> str:
    if continuation_run_id:
        return (
            f"Record feedback for original run {initial_run_id} and continuation run {continuation_run_id}: "
            "useful: the route returned inspectable artifacts and preserved the frozen repository. "
            "missing: generate exact packet operations automatically from the approved investigation."
        )
    return (
        f"Record feedback for run {initial_run_id}: "
        "useful: the route returned inspectable artifacts and preserved the frozen repository. "
        "missing: generate exact packet operations automatically from the approved investigation."
    )


def require_feedback_response(
    response: dict[str, Any],
    target_root: str,
    label: str,
    target_run_id: str,
) -> dict[str, Any]:
    compact = response.get("agentic_controller_response")
    if not isinstance(compact, dict):
        raise RuntimeError(f"{label} did not include agentic_controller_response for {target_root}")
    if compact.get("workflow") != "workflow_feedback.record":
        raise RuntimeError(f"{label} returned unexpected workflow: {compact.get('workflow')!r}")
    if compact.get("status") != "completed":
        raise RuntimeError(f"{label} did not complete: {compact.get('status')!r}")
    summary = compact.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError(f"{label} did not include a summary object")
    if summary.get("target_run_id") != target_run_id:
        raise RuntimeError(
            f"{label} target_run_id mismatch for {target_root}: "
            f"expected {target_run_id!r}, got {summary.get('target_run_id')!r}"
        )
    if summary.get("linked_run_found") is not True:
        raise RuntimeError(f"{label} did not link to stored run record for {target_root}")
    counts = summary.get("feedback_counts")
    if not isinstance(counts, dict) or counts.get("useful", 0) < 1 or counts.get("missing", 0) < 1:
        raise RuntimeError(f"{label} did not capture useful and missing feedback for {target_root}: {counts!r}")
    artifacts = compact.get("artifacts")
    if not isinstance(artifacts, dict) or "feedback_record" not in artifacts:
        raise RuntimeError(f"{label} did not include feedback_record artifact")
    return compact


def text_response(value: dict[str, Any]) -> str:
    for key in ("textResponse", "response", "message"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return item
    choices = value.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
    raise RuntimeError("response did not contain text content")


def require_anythingllm_text(body: dict[str, Any], target_root: str) -> str:
    text = text_response(body)
    required_markers = [
        "workflow_router.plan",
        "run_id:",
        "Artifacts:",
        "refactor.single_path",
        "downstream_workflow",
        "verification_command_count",
    ]
    missing = [marker for marker in required_markers if marker not in text]
    if missing:
        raise RuntimeError(
            "AnythingLLM natural route missing controller markers "
            f"{missing}; point the workspace at the workflow-router gateway."
        )
    if target_root not in text:
        raise RuntimeError(f"AnythingLLM natural route response did not mention target root {target_root}")
    return text


def require_anythingllm_continuation_text(
    body: dict[str, Any],
    target_root: str,
    *,
    expect_generated_packet_operations: bool = False,
    allow_generated_packet_block: bool = False,
) -> str:
    text = text_response(body)
    required_markers = [
        "workflow_router.plan",
        "run_id:",
        "execution_planning.plan",
    ]
    if not (expect_generated_packet_operations and allow_generated_packet_block):
        required_markers.append("downstream_implementation_workflow_report")
    if expect_generated_packet_operations:
        required_markers.append("packet_operation_proposal")
        if allow_generated_packet_block:
            required_markers.append("request_packet_objective")
    missing = [marker for marker in required_markers if marker not in text]
    if missing:
        raise RuntimeError(f"AnythingLLM continuation missing markers {missing} for {target_root}")
    return text


def require_anythingllm_packet_objective_text(body: dict[str, Any], target_root: str) -> str:
    text = text_response(body)
    required_markers = [
        "workflow_router.plan",
        "run_id:",
        "execution_planning.plan",
        "packet_operation_proposal",
    ]
    missing = [marker for marker in required_markers if marker not in text]
    if missing:
        raise RuntimeError(f"AnythingLLM packet-objective follow-up missing markers {missing} for {target_root}")
    acceptable_outcomes = [
        "downstream_implementation_workflow_report",
        "request_packet_objective",
        "request_narrowed_edit_objective",
        "no_change_needed",
    ]
    if not any(marker in text for marker in acceptable_outcomes):
        raise RuntimeError(
            "AnythingLLM packet-objective follow-up did not show a draft report, no-change outcome, "
            f"or packet-objective blocker for {target_root}"
        )
    return text


def require_anythingllm_narrowed_edit_text(
    body: dict[str, Any],
    target_root: str,
    *,
    expect_generated_operations: bool,
    allow_generated_block: bool,
) -> str:
    text = text_response(body)
    required_markers = [
        "workflow_router.plan",
        "run_id:",
        "execution_planning.plan",
        "narrowed_edit_objective_status",
    ]
    if expect_generated_operations:
        required_markers.append("packet_operation_proposal")
    if not (expect_generated_operations and allow_generated_block):
        required_markers.append("downstream_implementation_workflow_report")
    missing = [marker for marker in required_markers if marker not in text]
    if missing:
        raise RuntimeError(f"AnythingLLM narrowed-edit follow-up missing markers {missing} for {target_root}")
    if expect_generated_operations and allow_generated_block:
        acceptable_outcomes = [
            "downstream_implementation_workflow_report",
            "request_narrowed_edit_objective",
            "retry_execution_planning",
        ]
        if not any(marker in text for marker in acceptable_outcomes):
            raise RuntimeError(
                "AnythingLLM generated narrowed-edit follow-up did not show a draft report, "
                f"narrowed-objective request, or execution-planning retry for {target_root}"
            )
    return text


def require_anythingllm_feedback_text(body: dict[str, Any], target_root: str) -> str:
    text = text_response(body)
    required_markers = [
        "workflow_feedback.record",
        "run_id:",
        "target_run_id",
        "linked_run_found",
        "feedback_record",
    ]
    missing = [marker for marker in required_markers if marker not in text]
    if missing:
        raise RuntimeError(f"AnythingLLM feedback missing markers {missing} for {target_root}")
    return text


def validate_gateway_natural(args: argparse.Namespace, target_root: str) -> dict[str, Any]:
    before = target_hash(target_root)
    status, body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "messages": [
                {
                    "role": "user",
                    "content": "In /mnt/c/not-the-current-target, investigate stale chat history.",
                },
                {"role": "assistant", "content": "Previous route result."},
                {"role": "user", "content": natural_request(target_root)},
            ],
        },
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"gateway natural route returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    compact = require_workflow_router_response(body, target_root, "gateway natural route")
    after = target_hash(target_root)
    if before != after:
        raise RuntimeError(f"gateway natural route mutated selected frozen file for {target_root}")
    print(f"WORKFLOW ROUTER NATURAL GATEWAY PASS target={target_root} run_id={compact.get('run_id')}")
    result = {"target_root": target_root, "run_id": compact.get("run_id")}
    continuation_run_id = None
    if args.include_approval_continuation:
        operation = invariant_replace_operation(target_root)
        continuation_message = (
            f"Approve packet design for run {compact.get('run_id')}. Proceed with implementation prep."
            if args.generated_packet_continuation
            else (
                f"Approve packet design for run {compact.get('run_id')}. "
                f"Use packet operations: {json.dumps([operation], ensure_ascii=True)}"
            )
        )
        continuation_before = target_hash(target_root)
        status, continuation_body = json_request(
            f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
            payload={
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": continuation_message,
                    }
                ],
            },
            timeout_seconds=args.timeout_seconds,
        )
        if status != 200:
            raise RuntimeError(
                f"gateway continuation returned HTTP {status}: {json.dumps(continuation_body, ensure_ascii=True)}"
            )
        continuation = require_approval_continuation_response(
            continuation_body,
            target_root,
            "gateway natural approval continuation",
            expect_generated_packet_operations=args.generated_packet_continuation,
            allow_generated_packet_block=args.allow_generated_packet_block,
        )
        continuation_after = target_hash(target_root)
        if continuation_before != continuation_after:
            raise RuntimeError(f"gateway continuation mutated selected frozen file for {target_root}")
        continuation_run_id = continuation.get("run_id")
        result["continuation_run_id"] = continuation_run_id
        print(
            "WORKFLOW ROUTER NATURAL GATEWAY CONTINUATION PASS "
            f"target={target_root} run_id={continuation.get('run_id')}"
        )
    if args.include_packet_objective_followup:
        if not continuation_run_id:
            raise RuntimeError(f"gateway did not expose continuation run_id for packet objective on {target_root}")
        objective_message = (
            f"For run {continuation_run_id}, packet objective: make core/stealth_order_manager.py "
            "the authoritative placed_order_id lookup path. Draft only."
        )
        objective_before = target_hash(target_root)
        status, objective_body = json_request(
            f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
            payload={
                "model": "agentic-workflow-router",
                "messages": [{"role": "user", "content": objective_message}],
            },
            timeout_seconds=args.timeout_seconds,
        )
        if status != 200:
            raise RuntimeError(f"gateway packet objective returned HTTP {status}: {json.dumps(objective_body, ensure_ascii=True)}")
        objective = require_packet_objective_followup_response(
            objective_body,
            target_root,
            "gateway natural packet objective",
            allow_packet_objective_block=args.allow_packet_objective_block,
        )
        objective_after = target_hash(target_root)
        if objective_before != objective_after:
            raise RuntimeError(f"gateway packet objective mutated selected frozen file for {target_root}")
        objective_run_id = objective.get("run_id")
        result["packet_objective_run_id"] = objective_run_id
        continuation_run_id = objective_run_id if isinstance(objective_run_id, str) else continuation_run_id
        print(
            "WORKFLOW ROUTER NATURAL GATEWAY PACKET OBJECTIVE PASS "
            f"target={target_root} run_id={objective_run_id or 'unknown'}"
        )
    if args.include_narrowed_edit_followup:
        if not continuation_run_id:
            raise RuntimeError(f"gateway did not expose source run_id for narrowed edit on {target_root}")
        narrowed_before = target_hash(target_root)
        status, narrowed_body = json_request(
            f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
            payload={
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": narrowed_edit_message(
                            continuation_run_id,
                            target_root,
                            include_exact_operations=not args.generated_narrowed_edit_followup,
                        ),
                    }
                ],
            },
            timeout_seconds=args.timeout_seconds,
        )
        if status != 200:
            raise RuntimeError(f"gateway narrowed edit returned HTTP {status}: {json.dumps(narrowed_body, ensure_ascii=True)}")
        narrowed = require_narrowed_edit_followup_response(
            narrowed_body,
            target_root,
            "gateway natural narrowed edit",
            expect_generated_operations=args.generated_narrowed_edit_followup,
            allow_generated_block=args.allow_generated_narrowed_edit_block,
        )
        narrowed_after = target_hash(target_root)
        if narrowed_before != narrowed_after:
            raise RuntimeError(f"gateway narrowed edit mutated selected frozen file for {target_root}")
        narrowed_run_id = narrowed.get("run_id")
        result["narrowed_edit_run_id"] = narrowed_run_id
        continuation_run_id = narrowed_run_id if isinstance(narrowed_run_id, str) else continuation_run_id
        print(
            "WORKFLOW ROUTER NATURAL GATEWAY NARROWED EDIT PASS "
            f"target={target_root} run_id={narrowed_run_id or 'unknown'}"
        )
    if args.include_feedback_record:
        if not isinstance(result.get("run_id"), str) or not result["run_id"]:
            raise RuntimeError(f"gateway did not expose run_id for feedback on {target_root}")
        target_run_id = continuation_run_id or result["run_id"]
        feedback_before = target_hash(target_root)
        status, feedback_body = json_request(
            f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
            payload={
                "model": "agentic-workflow-router",
                "messages": [
                    {
                        "role": "user",
                        "content": feedback_message(result["run_id"], continuation_run_id),
                    }
                ],
            },
            timeout_seconds=args.timeout_seconds,
        )
        if status != 200:
            raise RuntimeError(f"gateway feedback returned HTTP {status}: {json.dumps(feedback_body, ensure_ascii=True)}")
        feedback = require_feedback_response(feedback_body, target_root, "gateway natural feedback", target_run_id)
        feedback_after = target_hash(target_root)
        if feedback_before != feedback_after:
            raise RuntimeError(f"gateway feedback mutated selected frozen file for {target_root}")
        result["feedback_run_id"] = feedback.get("run_id")
        print(
            "WORKFLOW ROUTER NATURAL GATEWAY FEEDBACK PASS "
            f"target={target_root} run_id={feedback.get('run_id')}"
        )
    return result


def validate_anythingllm_natural(args: argparse.Namespace, target_root: str, api_key: str) -> dict[str, Any]:
    before = target_hash(target_root)
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload={
            "message": natural_request(target_root),
            "mode": "chat",
            "sessionId": f"workflow-router-natural-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"AnythingLLM natural route returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = require_anythingllm_text(body, target_root)
    after = target_hash(target_root)
    if before != after:
        raise RuntimeError(f"AnythingLLM natural route mutated selected frozen file for {target_root}")
    run_id = None
    marker = "run_id:"
    if marker in text:
        run_id = text.split(marker, 1)[1].strip().split()[0]
    print(f"WORKFLOW ROUTER NATURAL ANYTHINGLLM PASS target={target_root} run_id={run_id or 'unknown'}")
    result = {"target_root": target_root, "run_id": run_id}
    continuation_run_id = None
    if args.include_approval_continuation:
        if not run_id:
            raise RuntimeError(f"AnythingLLM did not expose a run_id for approval continuation on {target_root}")
        operation = invariant_replace_operation(target_root)
        continuation_message = (
            f"Approve packet design for run {run_id}. Proceed with implementation prep."
            if args.generated_packet_continuation
            else (
                f"Approve packet design for run {run_id}. "
                f"Use packet operations: {json.dumps([operation], ensure_ascii=True)}"
            )
        )
        continuation_before = target_hash(target_root)
        status, continuation_body = json_request(
            f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
            payload={
                "message": continuation_message,
                "mode": "chat",
                "sessionId": f"workflow-router-continuation-{uuid.uuid4().hex}",
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout_seconds=args.timeout_seconds,
        )
        if status != 200:
            raise RuntimeError(
                f"AnythingLLM continuation returned HTTP {status}: {json.dumps(continuation_body, ensure_ascii=True)}"
            )
        continuation_text = require_anythingllm_continuation_text(
            continuation_body,
            target_root,
            expect_generated_packet_operations=args.generated_packet_continuation,
            allow_generated_packet_block=args.allow_generated_packet_block,
        )
        continuation_after = target_hash(target_root)
        if continuation_before != continuation_after:
            raise RuntimeError(f"AnythingLLM continuation mutated selected frozen file for {target_root}")
        continuation_run_id = None
        if marker in continuation_text:
            continuation_run_id = continuation_text.split(marker, 1)[1].strip().split()[0]
        result["continuation_run_id"] = continuation_run_id
        print(
            "WORKFLOW ROUTER NATURAL ANYTHINGLLM CONTINUATION PASS "
            f"target={target_root} run_id={continuation_run_id or 'unknown'}"
        )
    if args.include_packet_objective_followup:
        if not continuation_run_id:
            raise RuntimeError(f"AnythingLLM did not expose continuation run_id for packet objective on {target_root}")
        objective_message = (
            f"For run {continuation_run_id}, packet objective: make core/stealth_order_manager.py "
            "the authoritative placed_order_id lookup path. Draft only."
        )
        objective_before = target_hash(target_root)
        status, objective_body = json_request(
            f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
            payload={
                "message": objective_message,
                "mode": "chat",
                "sessionId": f"workflow-router-objective-{uuid.uuid4().hex}",
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout_seconds=args.timeout_seconds,
        )
        if status != 200:
            raise RuntimeError(
                f"AnythingLLM packet objective returned HTTP {status}: {json.dumps(objective_body, ensure_ascii=True)}"
            )
        objective_text = require_anythingllm_packet_objective_text(objective_body, target_root)
        objective_after = target_hash(target_root)
        if objective_before != objective_after:
            raise RuntimeError(f"AnythingLLM packet objective mutated selected frozen file for {target_root}")
        objective_run_id = None
        if marker in objective_text:
            objective_run_id = objective_text.split(marker, 1)[1].strip().split()[0]
        result["packet_objective_run_id"] = objective_run_id
        continuation_run_id = objective_run_id or continuation_run_id
        print(
            "WORKFLOW ROUTER NATURAL ANYTHINGLLM PACKET OBJECTIVE PASS "
            f"target={target_root} run_id={objective_run_id or 'unknown'}"
        )
    if args.include_narrowed_edit_followup:
        if not continuation_run_id:
            raise RuntimeError(f"AnythingLLM did not expose source run_id for narrowed edit on {target_root}")
        narrowed_before = target_hash(target_root)
        status, narrowed_body = json_request(
            f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
            payload={
                "message": narrowed_edit_message(
                    continuation_run_id,
                    target_root,
                    include_exact_operations=not args.generated_narrowed_edit_followup,
                ),
                "mode": "chat",
                "sessionId": f"workflow-router-narrowed-{uuid.uuid4().hex}",
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout_seconds=args.timeout_seconds,
        )
        if status != 200:
            raise RuntimeError(
                f"AnythingLLM narrowed edit returned HTTP {status}: {json.dumps(narrowed_body, ensure_ascii=True)}"
            )
        narrowed_text = require_anythingllm_narrowed_edit_text(
            narrowed_body,
            target_root,
            expect_generated_operations=args.generated_narrowed_edit_followup,
            allow_generated_block=args.allow_generated_narrowed_edit_block,
        )
        narrowed_after = target_hash(target_root)
        if narrowed_before != narrowed_after:
            raise RuntimeError(f"AnythingLLM narrowed edit mutated selected frozen file for {target_root}")
        narrowed_run_id = None
        if marker in narrowed_text:
            narrowed_run_id = narrowed_text.split(marker, 1)[1].strip().split()[0]
        result["narrowed_edit_run_id"] = narrowed_run_id
        continuation_run_id = narrowed_run_id or continuation_run_id
        print(
            "WORKFLOW ROUTER NATURAL ANYTHINGLLM NARROWED EDIT PASS "
            f"target={target_root} run_id={narrowed_run_id or 'unknown'}"
        )
    if args.include_feedback_record:
        if not run_id:
            raise RuntimeError(f"AnythingLLM did not expose a run_id for feedback on {target_root}")
        feedback_before = target_hash(target_root)
        status, feedback_body = json_request(
            f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
            payload={
                "message": feedback_message(run_id, continuation_run_id),
                "mode": "chat",
                "sessionId": f"workflow-router-feedback-{uuid.uuid4().hex}",
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout_seconds=args.timeout_seconds,
        )
        if status != 200:
            raise RuntimeError(f"AnythingLLM feedback returned HTTP {status}: {json.dumps(feedback_body, ensure_ascii=True)}")
        feedback_text = require_anythingllm_feedback_text(feedback_body, target_root)
        feedback_after = target_hash(target_root)
        if feedback_before != feedback_after:
            raise RuntimeError(f"AnythingLLM feedback mutated selected frozen file for {target_root}")
        feedback_run_id = None
        if marker in feedback_text:
            feedback_run_id = feedback_text.split(marker, 1)[1].strip().split()[0]
        result["feedback_run_id"] = feedback_run_id
        print(
            "WORKFLOW ROUTER NATURAL ANYTHINGLLM FEEDBACK PASS "
            f"target={target_root} run_id={feedback_run_id or 'unknown'}"
        )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--target-root", action="append", default=[])
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--skip-anythingllm", action="store_true")
    parser.add_argument("--include-approval-continuation", action="store_true")
    parser.add_argument("--include-feedback-record", action="store_true")
    parser.add_argument("--generated-packet-continuation", action="store_true")
    parser.add_argument("--allow-generated-packet-block", action="store_true")
    parser.add_argument("--include-packet-objective-followup", action="store_true")
    parser.add_argument("--allow-packet-objective-block", action="store_true")
    parser.add_argument("--include-narrowed-edit-followup", action="store_true")
    parser.add_argument("--generated-narrowed-edit-followup", action="store_true")
    parser.add_argument("--allow-generated-narrowed-edit-block", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.include_packet_objective_followup and not args.generated_packet_continuation:
        raise RuntimeError("--include-packet-objective-followup requires --generated-packet-continuation")
    if args.include_packet_objective_followup and not args.allow_generated_packet_block:
        raise RuntimeError("--include-packet-objective-followup requires --allow-generated-packet-block")
    if args.include_narrowed_edit_followup and not args.include_packet_objective_followup:
        raise RuntimeError("--include-narrowed-edit-followup requires --include-packet-objective-followup")
    if args.generated_narrowed_edit_followup and not args.include_narrowed_edit_followup:
        raise RuntimeError("--generated-narrowed-edit-followup requires --include-narrowed-edit-followup")
    target_roots = args.target_root or list(DEFAULT_TARGET_ROOTS)
    summary: dict[str, Any] = {"gateway": [], "anythingllm": [], "target_roots": target_roots}
    for target_root in target_roots:
        summary["gateway"].append(validate_gateway_natural(args, target_root))
    if args.skip_anythingllm:
        print("SKIP AnythingLLM natural route validation")
    else:
        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            raise RuntimeError(f"{args.api_key_env} is required unless --skip-anythingllm is set")
        for target_root in target_roots:
            summary["anythingllm"].append(validate_anythingllm_natural(args, target_root, api_key))
    print("WORKFLOW ROUTER NATURAL SUMMARY " + json.dumps(summary, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
