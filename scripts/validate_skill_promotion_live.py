#!/usr/bin/env python3
"""Validate live skill-eval promotion guards without mutating canonical registries."""

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


DEFAULT_CONFIG_ROOT = "/mnt/c/agentic_agents"
DEFAULT_CONTROLLER_BASE_URL = "http://127.0.0.1:8400"
DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
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
PORT_HEALTH_PROBES = [
    ("localhost-model", "http://127.0.0.1:8000/v1/models"),
    ("llm-gateway", "http://127.0.0.1:8300/v1/models"),
    ("controller", "http://127.0.0.1:8400/health"),
    ("workflow-router-gateway", "http://127.0.0.1:8500/v1/models"),
    ("documenter-role", "http://127.0.0.1:8101/v1/models"),
    ("architect-role", "http://127.0.0.1:8102/v1/models"),
    ("agent-role-8201", "http://127.0.0.1:8201/v1/models"),
    ("agent-role-8202", "http://127.0.0.1:8202/v1/models"),
    ("agent-role-8203", "http://127.0.0.1:8203/v1/models"),
    ("agent-role-8204", "http://127.0.0.1:8204/v1/models"),
    ("agent-role-8205", "http://127.0.0.1:8205/v1/models"),
]


def json_request(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: int,
    method: str = "POST",
) -> tuple[int, dict[str, Any]]:
    request_headers = dict(headers or {})
    data = None
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8")
            return response.status, json.loads(text) if text else {}
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


def skill_body_hashes(root: Path) -> dict[str, str]:
    skill_root = root / ".qwen" / "skills"
    if not skill_root.exists():
        raise RuntimeError(f"Missing skill body root: {skill_root}")
    return {
        path.relative_to(root).as_posix(): digest_file(path)
        for path in sorted(skill_root.glob("*/SKILL.md"))
    }


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


def require_test_mention(text: str, *, label: str) -> None:
    if "test" not in text.lower():
        raise RuntimeError(f"{label} missing test evidence mention")


def run_repo_command(config_root: Path, command: list[str], *, timeout_seconds: int) -> None:
    result = subprocess.run(
        command,
        cwd=config_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Command failed: "
            + " ".join(command)
            + "\nSTDOUT:\n"
            + result.stdout[-4000:]
            + "\nSTDERR:\n"
            + result.stderr[-4000:]
        )


def validate_port_health(args: argparse.Namespace) -> None:
    for label, url in PORT_HEALTH_PROBES:
        status, body = json_request(url, timeout_seconds=args.timeout_seconds, method="GET")
        if status != 200:
            raise RuntimeError(f"{label} health probe returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
        print(f"PHASE38 PORT PASS label={label} url={url}")


def validate_static_gates(args: argparse.Namespace, config_root: Path) -> None:
    python = sys.executable
    run_repo_command(
        config_root,
        [
            python,
            "scripts/validate_skill_evals.py",
            "--output-path",
            "runtime-state/skill-evals/phase38-live-precheck.json",
        ],
        timeout_seconds=args.timeout_seconds,
    )
    run_repo_command(
        config_root,
        [
            python,
            "scripts/validate_skill_scale.py",
            "--output-path",
            "runtime-state/skill-scale/phase38-live-precheck.json",
        ],
        timeout_seconds=args.timeout_seconds,
    )
    run_repo_command(config_root, [python, "scripts/check_docs_index.py"], timeout_seconds=args.timeout_seconds)
    print("PHASE38 STATIC GATES PASS")


def read_only_prompt(target_root: str) -> str:
    return (
        f"In {target_root}, explain what find_stealth_order_by_placed_order_id does in "
        "core/stealth_order_manager.py. Read only. Include key inputs, outputs, side effects, and tests."
    )


def validate_gateway_probe(args: argparse.Namespace, target_root: str) -> None:
    target = Path(target_root)
    config_root = Path(args.config_root)
    before_target = watched_hashes(target, WATCHED_TARGET_FILES)
    before_target_status = git_status(target)
    before_registry = watched_hashes(config_root, WATCHED_REGISTRY_FILES)
    before_skills = skill_body_hashes(config_root)
    status, body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": read_only_prompt(target_root)}],
        },
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"gateway read-only probe returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    require_markers(
        text,
        ("Answer:", "Inputs:", "Outputs:", "Side effects:"),
        label=f"gateway read-only probe {target_root}",
    )
    require_test_mention(text, label=f"gateway read-only probe {target_root}")
    validate_unchanged(target, before_target, before_target_status, "gateway read-only probe")
    validate_unchanged(config_root, before_registry, None, "gateway read-only probe registry")
    if skill_body_hashes(config_root) != before_skills:
        raise RuntimeError("gateway read-only probe changed skill body files")
    print(f"PHASE38 GATEWAY READONLY PASS target={target_root}")


def validate_anythingllm_probe(args: argparse.Namespace, target_root: str, api_key: str) -> None:
    target = Path(target_root)
    config_root = Path(args.config_root)
    before_target = watched_hashes(target, WATCHED_TARGET_FILES)
    before_target_status = git_status(target)
    before_registry = watched_hashes(config_root, WATCHED_REGISTRY_FILES)
    before_skills = skill_body_hashes(config_root)
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload={
            "message": read_only_prompt(target_root),
            "mode": "chat",
            "sessionId": f"phase38-skill-promotion-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"AnythingLLM read-only probe returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    require_markers(
        text,
        ("Answer:", "Inputs:", "Outputs:", "Side effects:"),
        label=f"AnythingLLM read-only probe {target_root}",
    )
    require_test_mention(text, label=f"AnythingLLM read-only probe {target_root}")
    validate_unchanged(target, before_target, before_target_status, "AnythingLLM read-only probe")
    validate_unchanged(config_root, before_registry, None, "AnythingLLM read-only probe registry")
    if skill_body_hashes(config_root) != before_skills:
        raise RuntimeError("AnythingLLM read-only probe changed skill body files")
    print(f"PHASE38 ANYTHINGLLM READONLY PASS target={target_root}")


def promotion_approval() -> dict[str, Any]:
    return {
        "status": "approved_for_skill_promotion",
        "scope": "skill_eval_promotion",
        "eval_status_update": True,
        "approval_refs": ["phase38-live-invalid-promotion-no-mutation-proof"],
    }


def validate_invalid_promotion_rejection(args: argparse.Namespace) -> None:
    config_root = Path(args.config_root)
    before_registry = watched_hashes(config_root, WATCHED_REGISTRY_FILES)
    before_skills = skill_body_hashes(config_root)
    status, body = json_request(
        f"{args.controller_base_url.rstrip('/')}/v1/controller/skill-evals/promotions",
        payload={
            "workflow": "skill_eval.promote",
            "schema_version": 1,
            "skill_ids": ["phase38-live-missing-skill"],
            "approval": promotion_approval(),
        },
        timeout_seconds=args.timeout_seconds,
    )
    if status != 422:
        raise RuntimeError(f"invalid promotion returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    if error.get("code") != "skill_not_registered":
        raise RuntimeError(f"invalid promotion returned wrong error: {json.dumps(body, ensure_ascii=True)}")
    validate_unchanged(config_root, before_registry, None, "invalid promotion rejection registry")
    if skill_body_hashes(config_root) != before_skills:
        raise RuntimeError("invalid promotion rejection changed skill body files")
    print("PHASE38 PROMOTION REJECTION PASS error=skill_not_registered")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=DEFAULT_CONFIG_ROOT)
    parser.add_argument("--controller-base-url", default=DEFAULT_CONTROLLER_BASE_URL)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--skip-anythingllm", action="store_true")
    parser.add_argument("--skip-port-health", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root)
    target_roots = args.target_roots or DEFAULT_TARGET_ROOTS
    if not args.skip_port_health:
        validate_port_health(args)
    validate_static_gates(args, config_root)
    for target_root in target_roots:
        validate_gateway_probe(args, target_root)
    if not args.skip_anythingllm:
        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            raise RuntimeError(f"{args.api_key_env} is required unless --skip-anythingllm is set")
        for target_root in target_roots:
            validate_anythingllm_probe(args, target_root, api_key)
    validate_invalid_promotion_rejection(args)
    print(
        "PHASE38 LIVE SUMMARY "
        + json.dumps(
            {
                "target_roots": target_roots,
                "gateway_read_only": True,
                "anythingllm": not args.skip_anythingllm,
                "promotion_rejection": True,
                "canonical_registry_mutated": False,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
