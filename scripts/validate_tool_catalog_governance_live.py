#!/usr/bin/env python3
"""Validate Phase 51 tool catalog governance against the live local stack."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_ROOT = "/mnt/c/agentic_agents"
DEFAULT_CONTROLLER_BASE_URL = "http://127.0.0.1:8400"
DEFAULT_REPORT_PATH = "runtime-state/tool-catalog-governance/phase51-live.json"
DEFAULT_TARGET_ROOTS = [
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
]
PORT_HEALTH_PROBES = [
    ("localhost-model", "http://127.0.0.1:8000/v1/models"),
    ("llm-gateway", "http://127.0.0.1:8300/v1/models"),
    ("controller", "http://127.0.0.1:8400/health"),
    ("workflow-router-gateway", "http://127.0.0.1:8500/v1/models"),
    ("reviewer-code", "http://127.0.0.1:8101/v1/models"),
    ("tester-code", "http://127.0.0.1:8102/v1/models"),
    ("architect-default", "http://127.0.0.1:8201/v1/models"),
    ("dispatcher-default", "http://127.0.0.1:8202/v1/models"),
    ("implementer-default", "http://127.0.0.1:8203/v1/models"),
    ("researcher-default", "http://127.0.0.1:8204/v1/models"),
    ("documenter-default", "http://127.0.0.1:8205/v1/models"),
]
WATCHED_RUNTIME_FILES = [
    "runtime/tools.json",
    "runtime/workflows.json",
    "runtime/roles.json",
]
WATCHED_TARGET_FILES = [
    "core/stealth_order_manager.py",
    "tests/unit/test_order_id_and_followup_rules.py",
    "docs/agents/INVARIANTS.md",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
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
            hashes[relative] = sha256_file(path)
    if not hashes:
        raise RuntimeError(f"{root} did not contain any watched files")
    return hashes


def changed_hashes(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(key for key, value in after.items() if before.get(key) != value)


def json_request(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout_seconds: int,
    method: str = "POST",
) -> tuple[int, dict[str, Any]]:
    headers: dict[str, str] = {}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8")
            return response.status, json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            body = {"error": {"message": text, "code": "invalid_json_error_body"}}
        return exc.code, body


def scan_files_manifest() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "tool_admission_manifest",
        "tool": {
            "id": "scan_files",
            "owner": "agentic_agents",
            "kind": "filesystem_read",
            "description": "Scan repository files for first-run or bootstrap discovery.",
            "read_only": True,
            "args_schema": {
                "ignored_dirs": {
                    "type": "array",
                    "required": False,
                }
            },
            "input_schema": {
                "type": "object",
                "properties": {
                    "ignored_dirs": {"type": "array", "items": {"type": "string"}},
                },
                "required": [],
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "paths": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["paths"],
            },
            "safety_class": "read_only",
            "mutation_policy": "no_repository_mutation",
            "allowed_workflows": ["documenter.review"],
            "allowed_roles": ["documenter/default"],
        },
    }


def validate_port_health(timeout_seconds: int) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for label, url in PORT_HEALTH_PROBES:
        status, body = json_request(url, timeout_seconds=timeout_seconds, method="GET")
        if status != 200:
            raise RuntimeError(f"{label} health probe returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
        checks.append({"label": label, "url": url, "status": "passed"})
        print(f"PHASE51 PORT PASS label={label} url={url}")
    return checks


def validate_duplicate_rejection(controller_base_url: str, timeout_seconds: int) -> dict[str, Any]:
    status, body = json_request(
        f"{controller_base_url.rstrip('/')}/v1/controller/tool-catalog/validations",
        payload={
            "workflow": "tool_catalog.validate",
            "schema_version": 1,
            "tool_manifest": scan_files_manifest(),
        },
        timeout_seconds=timeout_seconds,
    )
    failures = body.get("failures") if isinstance(body.get("failures"), list) else []
    first_code = failures[0].get("code") if failures and isinstance(failures[0], dict) else None
    if status != 200 or body.get("status") != "failed" or first_code != "tool_already_registered":
        raise RuntimeError(f"unexpected duplicate validation response: HTTP {status} {json.dumps(body, ensure_ascii=True)}")
    print("PHASE51 LIVE VALIDATION PASS duplicate_tool_already_registered")
    return {
        "label": "canonical_duplicate_validation",
        "http_status": status,
        "workflow_status": body.get("status"),
        "error_code": first_code,
        "run_id": body.get("run_id"),
        "status": "passed",
    }


def validate_missing_approval_rejection(controller_base_url: str, timeout_seconds: int) -> dict[str, Any]:
    status, body = json_request(
        f"{controller_base_url.rstrip('/')}/v1/controller/tool-catalog/registrations",
        payload={
            "workflow": "tool_catalog.register",
            "schema_version": 1,
            "tool_manifest": scan_files_manifest(),
        },
        timeout_seconds=timeout_seconds,
    )
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    if status != 403 or error.get("code") != "missing_tool_catalog_registration_approval":
        raise RuntimeError(f"unexpected missing-approval response: HTTP {status} {json.dumps(body, ensure_ascii=True)}")
    print("PHASE51 LIVE REGISTRATION GATE PASS missing_approval_rejected")
    return {
        "label": "missing_approval_registration",
        "http_status": status,
        "error_code": error.get("code"),
        "status": "passed",
    }


def run_controlled_copy_regression(config_root: Path, timeout_seconds: int) -> dict[str, Any]:
    command = [sys.executable, "-m", "pytest", "tests/regression/test_tool_catalog.py", "-q"]
    started = time.monotonic()
    result = subprocess.run(
        command,
        cwd=config_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout_seconds,
    )
    elapsed = time.monotonic() - started
    if result.returncode != 0:
        raise RuntimeError(
            "controlled-copy regression failed\nSTDOUT:\n"
            + result.stdout[-4000:]
            + "\nSTDERR:\n"
            + result.stderr[-4000:]
        )
    print("PHASE51 CONTROLLED COPY REGRESSION PASS")
    return {
        "label": "controlled_copy_registration_regression",
        "command": command,
        "returncode": result.returncode,
        "elapsed_seconds": elapsed,
        "stdout_tail": result.stdout[-1000:],
        "stderr_tail": result.stderr[-1000:],
        "status": "passed",
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=DEFAULT_CONFIG_ROOT)
    parser.add_argument("--controller-base-url", default=DEFAULT_CONTROLLER_BASE_URL)
    parser.add_argument("--output-path", default=DEFAULT_REPORT_PATH)
    parser.add_argument("--target-root", action="append", default=None)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root).resolve()
    output_path = Path(args.output_path)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    target_roots = [Path(value).resolve() for value in (args.target_root or DEFAULT_TARGET_ROOTS)]

    runtime_before = watched_hashes(config_root, WATCHED_RUNTIME_FILES)
    target_before = {str(root): watched_hashes(root, WATCHED_TARGET_FILES) for root in target_roots}
    checks: list[dict[str, Any]] = []
    checks.extend(validate_port_health(args.timeout_seconds))
    checks.append(validate_duplicate_rejection(args.controller_base_url, args.timeout_seconds))
    checks.append(validate_missing_approval_rejection(args.controller_base_url, args.timeout_seconds))
    checks.append(run_controlled_copy_regression(config_root, args.timeout_seconds))

    runtime_after = watched_hashes(config_root, WATCHED_RUNTIME_FILES)
    target_after = {str(root): watched_hashes(root, WATCHED_TARGET_FILES) for root in target_roots}
    runtime_changed = changed_hashes(runtime_before, runtime_after)
    target_changed = {
        root: changed_hashes(target_before[root], target_after[root])
        for root in target_before
        if changed_hashes(target_before[root], target_after[root])
    }
    if runtime_changed:
        raise RuntimeError(f"canonical runtime metadata mutated during live validation: {runtime_changed}")
    if target_changed:
        raise RuntimeError(f"protected frozen target files mutated during live validation: {target_changed}")

    report = {
        "kind": "tool_catalog_governance_live_validation",
        "schema_version": 1,
        "status": "passed",
        "created_at": utc_now(),
        "config_root": str(config_root),
        "controller_base_url": args.controller_base_url,
        "anythingllm_applicable": False,
        "checks": checks,
        "runtime_changed_files": runtime_changed,
        "target_changed_files": target_changed,
    }
    write_json(output_path, report)
    print(f"PHASE51 TOOL CATALOG GOVERNANCE LIVE PASS report={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
