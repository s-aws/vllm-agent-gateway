#!/usr/bin/env python3
"""Validate live skill-batch proposal and registration rejection paths."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_ROOT = "/mnt/c/agentic_agents"
DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_CONTROLLER_BASE_URL = "http://127.0.0.1:8400"
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_TARGET_ROOTS = [
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
]
WATCHED_TARGET_FILES = [
    "core/stealth_order_manager.py",
]
WATCHED_REGISTRY_FILES = [
    "runtime/skills.json",
    "runtime/skill_evals.json",
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


def watched_hashes(root: Path, relatives: list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in relatives:
        path = root / relative
        if path.exists():
            hashes[relative] = digest_file(path)
    if not hashes:
        raise RuntimeError(f"{root} did not contain watched files: {', '.join(relatives)}")
    return hashes


def git_status(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "-C", str(root), "status", "--short"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def validate_unchanged(root: Path, before_hashes: dict[str, str], before_status: str | None, label: str) -> None:
    after_hashes = watched_hashes(root, list(before_hashes))
    if after_hashes != before_hashes:
        raise RuntimeError(f"{label} changed watched files under {root}")
    if before_status is None:
        return
    after_status = git_status(root)
    if after_status != before_status:
        raise RuntimeError(f"{label} changed git status under {root}")


def text_response(body: dict[str, Any]) -> str:
    for key in ("textResponse", "response", "message"):
        value = body.get(key)
        if isinstance(value, str):
            return value
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first.get("message"), dict) else {}
        content = message.get("content")
        if isinstance(content, str):
            return content
    return json.dumps(body, ensure_ascii=True, sort_keys=True)


def require_markers(text: str, markers: tuple[str, ...], *, label: str) -> None:
    missing = [marker for marker in markers if marker not in text]
    if missing:
        raise RuntimeError(f"{label} missing marker(s): {', '.join(missing)}")


def duplicate_prompt(target_root: str) -> str:
    return (
        f"In {target_root}, propose a skill batch for duplicate code explanation. "
        "Proposal only. Do not register or append runtime skills."
    )


def approval() -> dict[str, Any]:
    return {
        "status": "approved_for_skill_registration",
        "scope": "skill_batch_registration",
        "runtime_registry_append": True,
        "skill_body_install": True,
        "approval_refs": ["phase37-live-rejection-proof"],
    }


def validate_gateway_probe(args: argparse.Namespace, target_root: str) -> str:
    target = Path(target_root)
    config_root = Path(args.config_root)
    before_target = watched_hashes(target, WATCHED_TARGET_FILES)
    before_target_status = git_status(target)
    before_registry = watched_hashes(config_root, WATCHED_REGISTRY_FILES)
    status, body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": duplicate_prompt(target_root)}],
        },
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"gateway proposal returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    require_markers(
        text,
        ("Draft proposal:", "skill_batch_proposal", "do_not_admit", "Runtime registry changed: False"),
        label=f"gateway proposal {target_root}",
    )
    compact = body.get("agentic_controller_response") if isinstance(body.get("agentic_controller_response"), dict) else {}
    artifacts = compact.get("artifacts") if isinstance(compact.get("artifacts"), dict) else {}
    proposal_path = artifacts.get("downstream_skill_batch_proposal")
    if not isinstance(proposal_path, str) or not proposal_path:
        raise RuntimeError("gateway proposal did not expose downstream_skill_batch_proposal")
    validate_unchanged(target, before_target, before_target_status, "gateway proposal")
    validate_unchanged(config_root, before_registry, None, "gateway proposal registry")
    run_id = compact.get("run_id")
    print(f"PHASE37 GATEWAY PROPOSAL PASS target={target_root} run_id={run_id}")
    return proposal_path


def validate_registration_rejection(args: argparse.Namespace, target_root: str, proposal_path: str) -> None:
    target = Path(target_root)
    config_root = Path(args.config_root)
    before_target = watched_hashes(target, WATCHED_TARGET_FILES)
    before_target_status = git_status(target)
    before_registry = watched_hashes(config_root, WATCHED_REGISTRY_FILES)
    status, body = json_request(
        f"{args.controller_base_url.rstrip()}/v1/controller/skill-batch/registrations",
        payload={
            "workflow": "skill_batch.register",
            "schema_version": 1,
            "proposal_path": proposal_path,
            "approval": approval(),
        },
        timeout_seconds=args.timeout_seconds,
    )
    if status != 422:
        raise RuntimeError(f"registration rejection returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    if error.get("code") != "proposal_not_ready":
        raise RuntimeError(f"registration rejection returned wrong error: {json.dumps(body, ensure_ascii=True)}")
    validate_unchanged(target, before_target, before_target_status, "registration rejection")
    validate_unchanged(config_root, before_registry, None, "registration rejection registry")
    print(f"PHASE37 REGISTRATION REJECTION PASS target={target_root} error=proposal_not_ready")


def validate_anythingllm_probe(args: argparse.Namespace, target_root: str, api_key: str) -> None:
    target = Path(target_root)
    config_root = Path(args.config_root)
    before_target = watched_hashes(target, WATCHED_TARGET_FILES)
    before_target_status = git_status(target)
    before_registry = watched_hashes(config_root, WATCHED_REGISTRY_FILES)
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload={
            "message": duplicate_prompt(target_root),
            "mode": "chat",
            "sessionId": f"phase37-skill-batch-registration-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"AnythingLLM proposal returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    require_markers(
        text,
        ("Draft proposal:", "skill_batch_proposal", "do_not_admit", "Runtime registry changed: False"),
        label=f"AnythingLLM proposal {target_root}",
    )
    validate_unchanged(target, before_target, before_target_status, "AnythingLLM proposal")
    validate_unchanged(config_root, before_registry, None, "AnythingLLM proposal registry")
    print(f"PHASE37 ANYTHINGLLM PROPOSAL PASS target={target_root}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=DEFAULT_CONFIG_ROOT)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--controller-base-url", default=DEFAULT_CONTROLLER_BASE_URL)
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
    proposal_paths: dict[str, str] = {}
    for target_root in target_roots:
        proposal_paths[target_root] = validate_gateway_probe(args, target_root)
        validate_registration_rejection(args, target_root, proposal_paths[target_root])
    if not args.skip_anythingllm:
        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            raise RuntimeError(f"{args.api_key_env} is required unless --skip-anythingllm is set")
        for target_root in target_roots:
            validate_anythingllm_probe(args, target_root, api_key)
    print(
        "PHASE37 LIVE SUMMARY "
        + json.dumps(
            {
                "target_roots": target_roots,
                "gateway_proposals": len(proposal_paths),
                "registration_rejections": len(proposal_paths),
                "anythingllm": not args.skip_anythingllm,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
