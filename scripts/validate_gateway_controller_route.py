#!/usr/bin/env python3
"""Validate explicit controller-envelope routing through the gateway and AnythingLLM."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_GATEWAY_BASE_URL = "http://127.0.0.1:8300/v1"
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_TARGET_ROOTS = [
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
]
INVARIANT_REL = "docs/agents/INVARIANTS.md"
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
SUPPORTED_MODES = {"investigation_only", "dry_run", "workflow_router_apply_disposable_copy"}


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
    digest.update(path.read_bytes())
    return digest.hexdigest()


def target_hashes(target_root: str) -> dict[str, str]:
    target = Path(target_root)
    invariant = target / INVARIANT_REL
    if not invariant.exists():
        raise RuntimeError(f"target is missing required validation file: {invariant}")
    return {INVARIANT_REL: file_digest(invariant)}


def build_envelope(target_root: str, mode: str) -> dict[str, Any]:
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"unsupported mode: {mode}")
    if mode == "workflow_router_apply_disposable_copy":
        return {
            "workflow": "workflow_router.plan",
            "schema_version": 1,
            "target_root": target_root,
            "user_request": (
                "Apply approved packet operations to a disposable copy for mutation proof that "
                "client_order_id owns internal lookup paths."
            ),
            "mode": "apply_disposable_copy",
            "approval": {
                "status": "approved_for_disposable_apply",
                "apply_allowed": True,
                "apply_scope": "disposable_copy_only",
                "approval_refs": ["client-route-validator:approved disposable copy apply only"],
            },
            "packet_operations": [
                {
                    "kind": "replace_text",
                    "path": INVARIANT_REL,
                    "old": FROZEN_INVARIANT_OLD,
                    "new": FROZEN_INVARIANT_NEW,
                }
            ],
            "budgets": {
                "max_model_calls": 3,
                "max_selected_skills": 5,
                "max_selected_tools": 5,
            },
        }
    envelope: dict[str, Any] = {
        "workflow": "execution_planning.plan",
        "schema_version": 1,
        "target_root": target_root,
        "user_request": (
            "Create a read-only execution plan for investigating the frozen repository invariant file. "
            "Do not design packets and do not mutate the repository."
        ),
        "mode": mode,
        "context": {
            "entrypoint_hints": [
                {
                    "path": INVARIANT_REL,
                    "symbol": None,
                    "reason": "Frozen validation entrypoint for client_order_id invariant behavior.",
                }
            ],
            "allowed_context_tools": ["structure_index", "git_grep", "read_file", "manual"],
        },
        "budgets": {
            "max_context_requests": 3,
            "max_files": 5,
            "max_records": 25,
            "max_model_calls": 8,
            "max_output_tokens": 3600,
            "timeout_seconds": 600,
        },
    }
    if mode == "dry_run":
        envelope["user_request"] = (
            "Prepare implementation packet candidates for an approved frozen-repo documentation clarification "
            "that client_order_id owns internal lookup paths, including StealthOrderManager placed-order index keys. "
            "Use draft mode only and do not mutate the frozen repository."
        )
        envelope["approval"] = {
            "status": "approved_for_packet_design",
            "scope": "packet_design_only",
            "apply_allowed": False,
            "approval_refs": ["founder:approved packet design only for frozen documentation dry run"],
        }
        envelope["packet_operations"] = [
            {
                "kind": "replace_text",
                "path": INVARIANT_REL,
                "old": FROZEN_INVARIANT_OLD,
                "new": FROZEN_INVARIANT_NEW,
            }
        ]
        envelope["budgets"] = {
            "max_context_requests": 5,
            "max_files": 10,
            "max_records": 50,
            "max_model_calls": 12,
            "max_output_tokens": 4600,
            "timeout_seconds": 600,
        }
        envelope["feedback"] = {
            "tester_feedback": (
                "Confirm the routed controller workflow produces a bounded draft packet preview and preserves "
                "the frozen target repository."
            )
        }
    return envelope


def openai_payload(envelope: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": "agentic-controller",
        "messages": [
            {
                "role": "user",
                "content": json.dumps({"agentic_controller_request": envelope}, ensure_ascii=True),
            }
        ],
    }


def require_direct_controller_response(body: dict[str, Any], target_root: str, mode: str) -> dict[str, Any]:
    response = body.get("agentic_controller_response")
    if not isinstance(response, dict):
        raise RuntimeError("gateway response did not include agentic_controller_response")
    expected_workflow = "workflow_router.plan" if mode == "workflow_router_apply_disposable_copy" else "execution_planning.plan"
    if response.get("workflow") != expected_workflow:
        raise RuntimeError(f"unexpected workflow in controller response: {response.get('workflow')!r}")
    if response.get("status") != "completed":
        raise RuntimeError(f"controller response status was not completed: {response.get('status')!r}")
    artifacts = response.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise RuntimeError("controller response did not include bounded artifact paths")
    run_id = response.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise RuntimeError("controller response did not include run_id")
    non_mutation = response.get("non_mutation")
    if isinstance(non_mutation, dict) and non_mutation.get("changed_files"):
        raise RuntimeError(f"controller response recorded mutated files: {non_mutation.get('changed_files')!r}")
    summary = response.get("summary")
    if mode == "workflow_router_apply_disposable_copy":
        if not isinstance(summary, dict):
            raise RuntimeError("workflow_router response did not include a summary object")
        expected = {
            "route_status": "ready",
            "selected_workflow": "execution_planning.plan",
            "downstream_workflow": "implementation.workflow",
            "downstream_status": "completed",
            "source_changed": False,
            "disposable_copy_changed": True,
        }
        wrong = {
            key: {"expected": expected_value, "actual": summary.get(key)}
            for key, expected_value in expected.items()
            if summary.get(key) != expected_value
        }
        if wrong:
            raise RuntimeError(f"workflow_router disposable apply summary mismatch: {wrong!r}")
        required_artifacts = {"route_decision", "downstream_result"}
        missing = sorted(required_artifacts - set(artifacts))
        if missing:
            raise RuntimeError(f"workflow_router response was missing artifact(s): {', '.join(missing)}")
        print(f"GATEWAY ROUTE PASS mode={mode} target={target_root} run_id={run_id}")
        return response
    if mode == "dry_run":
        required_artifacts = {
            "implementation_packet_candidates",
            "packet_preview",
            "verification_plan",
            "implementation_workflow_report",
        }
        missing = sorted(required_artifacts - set(artifacts))
        if missing:
            raise RuntimeError(f"dry_run response was missing artifact(s): {', '.join(missing)}")
    print(f"GATEWAY ROUTE PASS mode={mode} target={target_root} run_id={run_id}")
    return response


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


def run_id_from_text(text: str) -> str | None:
    match = re.search(r"run_id:\s*([A-Za-z0-9_.:-]+)", text)
    return match.group(1) if match else None


def require_anythingllm_controller_text(body: dict[str, Any], target_root: str, mode: str) -> dict[str, str | None]:
    text = text_response(body)
    required_markers = ["execution_planning.plan", "run_id:", "Artifacts:"]
    if mode == "dry_run":
        required_markers.extend(["packet_preview", "implementation_workflow_report"])
    elif mode == "workflow_router_apply_disposable_copy":
        required_markers = [
            "workflow_router.plan",
            "run_id:",
            "Artifacts:",
            "implementation.workflow",
            "disposable_copy_changed",
            "route_decision",
            "downstream_result",
        ]
    missing = [marker for marker in required_markers if marker not in text]
    if missing:
        raise RuntimeError(
            "AnythingLLM response did not contain controller markers "
            f"{missing}; this usually means the workspace is not using the routed gateway."
        )
    run_id = run_id_from_text(text)
    print(f"ANYTHINGLLM ROUTE PASS mode={mode} target={target_root} run_id={run_id or 'unknown'}")
    return {"run_id": run_id, "text": text}


def validate_gateway_route(args: argparse.Namespace, target_root: str, mode: str) -> dict[str, Any]:
    before = target_hashes(target_root)
    status, body = json_request(
        f"{args.gateway_base_url.rstrip('/')}/chat/completions",
        payload=openai_payload(build_envelope(target_root, mode)),
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"gateway route returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    response = require_direct_controller_response(body, target_root, mode)
    after = target_hashes(target_root)
    if before != after:
        raise RuntimeError(f"gateway route mutated selected frozen files for {target_root}")
    return response


def validate_anythingllm_route(args: argparse.Namespace, target_root: str, api_key: str, mode: str) -> dict[str, str | None]:
    before = target_hashes(target_root)
    envelope_text = json.dumps({"agentic_controller_request": build_envelope(target_root, mode)}, ensure_ascii=True)
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload={"message": envelope_text, "mode": "chat"},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"AnythingLLM route returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    result = require_anythingllm_controller_text(body, target_root, mode)
    after = target_hashes(target_root)
    if before != after:
        raise RuntimeError(f"AnythingLLM route mutated selected frozen files for {target_root}")
    return result


def resolve_modes(raw_modes: list[str]) -> list[str]:
    modes = raw_modes or ["investigation_only"]
    resolved: list[str] = []
    for mode in modes:
        if mode == "both":
            candidates = ["investigation_only", "dry_run"]
        else:
            candidates = [mode]
        for candidate in candidates:
            if candidate not in resolved:
                resolved.append(candidate)
    return resolved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-base-url", default=DEFAULT_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--target-root", action="append", default=[])
    parser.add_argument(
        "--mode",
        action="append",
        choices=["investigation_only", "dry_run", "workflow_router_apply_disposable_copy", "both"],
        default=[],
        help="Validation mode to run. May be supplied multiple times. Default: investigation_only.",
    )
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--skip-anythingllm", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_roots = args.target_root or DEFAULT_TARGET_ROOTS
    modes = resolve_modes(args.mode)
    summary: dict[str, Any] = {"gateway": [], "anythingllm": [], "modes": modes, "target_roots": target_roots}
    for mode in modes:
        for target_root in target_roots:
            response = validate_gateway_route(args, target_root, mode)
            summary["gateway"].append({"mode": mode, "target_root": target_root, "run_id": response.get("run_id")})
    if args.skip_anythingllm:
        print("SKIP AnythingLLM route validation")
        print("SUMMARY " + json.dumps(summary, ensure_ascii=True, sort_keys=True))
        return 0
    api_key = os.environ.get("ANYTHINGLLM_API_KEY")
    if not api_key:
        raise RuntimeError("ANYTHINGLLM_API_KEY is required unless --skip-anythingllm is set")
    for mode in modes:
        for target_root in target_roots:
            result = validate_anythingllm_route(args, target_root, api_key, mode)
            summary["anythingllm"].append({"mode": mode, "target_root": target_root, "run_id": result.get("run_id")})
    print("SUMMARY " + json.dumps(summary, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
