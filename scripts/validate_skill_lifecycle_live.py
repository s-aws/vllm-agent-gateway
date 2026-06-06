#!/usr/bin/env python3
"""Validate live skill lifecycle audit paths without mutating registries or fixtures."""

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
WATCHED_TARGET_FILES = ["core/stealth_order_manager.py"]
WATCHED_REGISTRY_FILES = ["runtime/skills.json", "runtime/skill_evals.json"]
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
    return {path.relative_to(root).as_posix(): digest_file(path) for path in sorted(skill_root.glob("*/SKILL.md"))}


def git_status(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    result = subprocess.run(["git", "-C", str(root), "status", "--short"], check=True, capture_output=True, text=True)
    return result.stdout


def validate_unchanged(root: Path, before_hashes: dict[str, str], before_status: str | None, label: str) -> None:
    after_hashes = watched_hashes(root, list(before_hashes))
    if after_hashes != before_hashes:
        raise RuntimeError(f"{label} changed watched files under {root}")
    if before_status is not None and git_status(root) != before_status:
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
        print(f"PHASE39 PORT PASS label={label} url={url}")


def validate_static_gates(args: argparse.Namespace, config_root: Path) -> None:
    python = sys.executable
    run_repo_command(
        config_root,
        [
            python,
            "scripts/validate_skill_evals.py",
            "--output-path",
            "runtime-state/skill-evals/phase39-live-precheck.json",
        ],
        timeout_seconds=args.timeout_seconds,
    )
    run_repo_command(
        config_root,
        [
            python,
            "scripts/validate_skill_scale.py",
            "--output-path",
            "runtime-state/skill-scale/phase39-live-precheck.json",
        ],
        timeout_seconds=args.timeout_seconds,
    )
    run_repo_command(config_root, [python, "scripts/check_docs_index.py"], timeout_seconds=args.timeout_seconds)
    print("PHASE39 STATIC GATES PASS")


def before_state(config_root: Path, target_roots: list[str]) -> dict[str, Any]:
    return {
        "registry": watched_hashes(config_root, WATCHED_REGISTRY_FILES),
        "skill_bodies": skill_body_hashes(config_root),
        "targets": {
            target: {
                "hashes": watched_hashes(Path(target), WATCHED_TARGET_FILES),
                "status": git_status(Path(target)),
            }
            for target in target_roots
        },
    }


def validate_state_unchanged(config_root: Path, target_roots: list[str], state: dict[str, Any], label: str) -> None:
    validate_unchanged(config_root, state["registry"], None, f"{label} registry")
    if skill_body_hashes(config_root) != state["skill_bodies"]:
        raise RuntimeError(f"{label} changed skill body files")
    for target in target_roots:
        target_state = state["targets"][target]
        validate_unchanged(Path(target), target_state["hashes"], target_state["status"], f"{label} target")


def audit_prompt() -> str:
    return "Audit the skill lifecycle. Return counts, blockers, and exact next actions."


def validate_direct_audit(args: argparse.Namespace, config_root: Path, target_roots: list[str]) -> None:
    state = before_state(config_root, target_roots)
    status, body = json_request(
        f"{args.controller_base_url.rstrip('/')}/v1/controller/skill-lifecycle/audits",
        payload={"workflow": "skill_lifecycle.audit", "schema_version": 1},
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"direct lifecycle audit returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    summary = body.get("summary") if isinstance(body.get("summary"), dict) else {}
    if summary.get("lifecycle_status") != "passed":
        raise RuntimeError(f"direct lifecycle audit did not pass: {json.dumps(summary, ensure_ascii=True)}")
    if summary.get("runtime_registry_changed") is not False:
        raise RuntimeError("direct lifecycle audit reported runtime registry mutation")
    validate_state_unchanged(config_root, target_roots, state, "direct lifecycle audit")
    print("PHASE39 DIRECT AUDIT PASS")


def validate_gateway_audit(args: argparse.Namespace, config_root: Path, target_roots: list[str]) -> None:
    state = before_state(config_root, target_roots)
    status, body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={"model": "agentic-workflow-router", "messages": [{"role": "user", "content": audit_prompt()}]},
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"gateway lifecycle audit returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    require_markers(
        text,
        ("Lifecycle Audit:", "Lifecycle status: passed", "Runtime registry changed: False"),
        label="gateway lifecycle audit",
    )
    validate_state_unchanged(config_root, target_roots, state, "gateway lifecycle audit")
    print("PHASE39 GATEWAY AUDIT PASS")


def validate_anythingllm_audit(args: argparse.Namespace, config_root: Path, target_roots: list[str], api_key: str) -> None:
    state = before_state(config_root, target_roots)
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload={
            "message": audit_prompt(),
            "mode": "chat",
            "sessionId": f"phase39-skill-lifecycle-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"AnythingLLM lifecycle audit returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    require_markers(
        text,
        ("Lifecycle Audit:", "Lifecycle status: passed", "Runtime registry changed: False"),
        label="AnythingLLM lifecycle audit",
    )
    validate_state_unchanged(config_root, target_roots, state, "AnythingLLM lifecycle audit")
    print("PHASE39 ANYTHINGLLM AUDIT PASS")


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
    validate_direct_audit(args, config_root, target_roots)
    validate_gateway_audit(args, config_root, target_roots)
    if not args.skip_anythingllm:
        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            raise RuntimeError(f"{args.api_key_env} is required unless --skip-anythingllm is set")
        validate_anythingllm_audit(args, config_root, target_roots, api_key)
    print(
        "PHASE39 LIVE SUMMARY "
        + json.dumps(
            {
                "target_roots": target_roots,
                "direct_audit": True,
                "gateway_audit": True,
                "anythingllm": not args.skip_anythingllm,
                "canonical_registry_mutated": False,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

