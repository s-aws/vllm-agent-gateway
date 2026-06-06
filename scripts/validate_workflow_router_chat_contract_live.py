#!/usr/bin/env python3
"""Validate Phase 52 chat response contract through gateway and AnythingLLM."""

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
    "core/stealth_order_manager.py",
    "tests/unit/test_order_id_and_followup_rules.py",
    "docs/agents/INVARIANTS.md",
]


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


def json_content(body: dict[str, Any]) -> dict[str, Any]:
    text = text_response(body)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"assistant content was not parseable JSON: {text[:500]}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("assistant JSON content was not an object")
    return parsed


def prompt(target_root: str) -> str:
    return (
        f"In {target_root}, explain what find_stealth_order_by_placed_order_id does "
        "in core/stealth_order_manager.py. Read only. Include key inputs, outputs, side effects, and tests. "
        "Return JSON."
    )


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
        raise RuntimeError(f"{target_root} did not contain watched files")
    return hashes


def git_status(target_root: str) -> str | None:
    root = Path(target_root)
    if not (root / ".git").exists():
        return None
    result = subprocess.run(["git", "-C", target_root, "status", "--short"], check=True, capture_output=True, text=True)
    return result.stdout


def validate_unchanged(target_root: str, before_hashes: dict[str, str], before_status: str | None, label: str) -> None:
    if watched_hashes(target_root) != before_hashes:
        raise RuntimeError(f"{label} mutated watched files for {target_root}")
    after_status = git_status(target_root)
    if before_status is not None and after_status != before_status:
        raise RuntimeError(f"{label} changed git status for {target_root}: {after_status!r}")


def require_json_contract(parsed: dict[str, Any], target_root: str, label: str) -> None:
    if parsed.get("output_format") != "json":
        raise RuntimeError(f"{label} JSON output_format was wrong for {target_root}: {parsed.get('output_format')!r}")
    if parsed.get("workflow") != "workflow_router.plan":
        raise RuntimeError(f"{label} JSON workflow was wrong for {target_root}: {parsed.get('workflow')!r}")
    if parsed.get("status") != "completed":
        raise RuntimeError(f"{label} JSON status was wrong for {target_root}: {parsed.get('status')!r}")
    contract = parsed.get("chat_contract")
    if not isinstance(contract, dict):
        raise RuntimeError(f"{label} JSON did not include chat_contract for {target_root}")
    expected = {
        "workflow": "workflow_router.plan",
        "status": "completed",
        "selected_workflow": "code_investigation.plan",
        "next_action": "none",
    }
    wrong = {key: {"expected": value, "actual": contract.get(key)} for key, value in expected.items() if contract.get(key) != value}
    if wrong:
        raise RuntimeError(f"{label} chat_contract mismatch for {target_root}: {json.dumps(wrong, sort_keys=True)}")
    selected_skills = contract.get("selected_skills")
    selected_tools = contract.get("selected_tools")
    if not isinstance(selected_skills, list) or not selected_skills:
        raise RuntimeError(f"{label} chat_contract did not include selected skills for {target_root}")
    if not isinstance(selected_tools, list) or not selected_tools:
        raise RuntimeError(f"{label} chat_contract did not include selected tools for {target_root}")
    artifacts = parsed.get("artifacts")
    if not isinstance(artifacts, dict) or "downstream_code_explanation" not in artifacts:
        raise RuntimeError(f"{label} JSON did not include downstream_code_explanation artifact for {target_root}")


def validate_gateway(args: argparse.Namespace, target_root: str) -> dict[str, str]:
    before_hashes = watched_hashes(target_root)
    before_status = git_status(target_root)
    status, body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "output_format": "json",
            "messages": [{"role": "user", "content": prompt(target_root)}],
        },
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"gateway returned HTTP {status} for {target_root}: {json.dumps(body, ensure_ascii=True)}")
    parsed = json_content(body)
    require_json_contract(parsed, target_root, "gateway")
    validate_unchanged(target_root, before_hashes, before_status, "gateway json contract")
    run_id = parsed.get("run_id")
    print(f"CHAT CONTRACT JSON GATEWAY PASS target={target_root} run_id={run_id}")
    return {"target_root": target_root, "run_id": str(run_id)}


def validate_anythingllm(args: argparse.Namespace, target_root: str, api_key: str) -> dict[str, str]:
    before_hashes = watched_hashes(target_root)
    before_status = git_status(target_root)
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload={
            "message": prompt(target_root),
            "mode": "chat",
            "sessionId": f"workflow-router-json-contract-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"AnythingLLM returned HTTP {status} for {target_root}: {json.dumps(body, ensure_ascii=True)}")
    parsed = json_content(body)
    require_json_contract(parsed, target_root, "AnythingLLM")
    validate_unchanged(target_root, before_hashes, before_status, "AnythingLLM json contract")
    run_id = parsed.get("run_id")
    print(f"CHAT CONTRACT JSON ANYTHINGLLM PASS target={target_root} run_id={run_id}")
    return {"target_root": target_root, "run_id": str(run_id)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--skip-anythingllm", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_roots = args.target_roots or DEFAULT_TARGET_ROOTS
    summary: dict[str, Any] = {"gateway": [], "anythingllm": [], "target_roots": target_roots}
    for target_root in target_roots:
        summary["gateway"].append(validate_gateway(args, target_root))
    if not args.skip_anythingllm:
        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            raise RuntimeError(f"{args.api_key_env} is required unless --skip-anythingllm is set")
        for target_root in target_roots:
            summary["anythingllm"].append(validate_anythingllm(args, target_root, api_key))
    print("CHAT CONTRACT JSON SUMMARY")
    print(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
