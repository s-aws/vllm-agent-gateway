#!/usr/bin/env python3
"""Validate Phase 105 advanced-refactor readiness through live local clients."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


DEFAULT_TARGET_ROOTS = [
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
]
DEFAULT_OUTPUT_PATH = "runtime-state/advanced-refactor-readiness/phase105-live-natural.json"
DEFAULT_WORKSPACE = "my-workspace"
WATCHED_RELATIVE_PATHS = [
    "core/stealth_order_manager.py",
    "tests/unit/test_order_id_and_followup_rules.py",
    "tests/regression/test_order_id_regression.py",
    "docs/agents/INVARIANTS.md",
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--target-root", action="append", default=[])
    parser.add_argument("--output-path", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--workflow-router-gateway-base-url", default="http://127.0.0.1:8500/v1")
    parser.add_argument("--controller-base-url", default="http://127.0.0.1:8400")
    parser.add_argument("--anythingllm-api-base-url", default="http://127.0.0.1:3001")
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--role-base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--timeout-seconds", type=int, default=360)
    parser.add_argument("--skip-anythingllm", action="store_true")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fixture_state(target_root: str) -> dict[str, Any]:
    root = Path(target_root)
    hashes = {relative: sha256_file(root / relative) for relative in WATCHED_RELATIVE_PATHS if (root / relative).exists()}
    git_status = None
    if (root / ".git").exists():
        git_status = subprocess.run(
            ["git", "-C", target_root, "status", "--short"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    return {"hashes": hashes, "git_status": git_status}


def json_request(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    method: str = "POST",
    timeout_seconds: int,
) -> tuple[int, dict[str, Any]]:
    request_headers = dict(headers or {})
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8")
            return response.status, json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            body = {"error": {"message": text}}
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
    return json.dumps(body, ensure_ascii=True)[:4000]


def run_id_from_text(text: str) -> str:
    marker = "run_id:"
    if marker not in text:
        return "unknown"
    return text.split(marker, 1)[1].strip().split()[0]


def controller_run(config: argparse.Namespace, run_id: str) -> dict[str, Any] | None:
    if run_id == "unknown":
        return None
    status, body = json_request(
        f"{config.controller_base_url.rstrip('/')}/v1/controller/runs/{run_id}",
        method="GET",
        timeout_seconds=config.timeout_seconds,
    )
    if status != 200:
        return {"http_status": status, "body": body}
    return body


def advanced_refactor_prompt(target_root: str) -> str:
    return (
        f"In {target_root}, refactor the placed_order_id stealth lookup so there is only one code path. "
        "Start from the logic beginning point, investigate first, create an implementation plan, "
        "wait for approval before implementation prep, and provide verification commands."
    )


def validate_port_health(config: argparse.Namespace) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for label, url in PORT_HEALTH_PROBES:
        status, _body = json_request(url, method="GET", timeout_seconds=min(config.timeout_seconds, 30))
        checks.append(
            {
                "label": label,
                "url": url,
                "http_status": status,
                "status": "passed" if status == 200 else "failed",
            }
        )
    return checks


def validate_gateway_case(config: argparse.Namespace, target_root: str, message: str) -> dict[str, Any]:
    status, body = json_request(
        f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": message}],
            "role_base_url": config.role_base_url,
        },
        timeout_seconds=config.timeout_seconds,
    )
    text = text_response(body)
    compact = body.get("agentic_controller_response") if isinstance(body.get("agentic_controller_response"), dict) else {}
    summary = compact.get("summary") if isinstance(compact.get("summary"), dict) else {}
    run_id = compact.get("run_id") if isinstance(compact.get("run_id"), str) else run_id_from_text(text)
    record = controller_run(config, run_id)
    return {
        "http_status": status,
        "run_id": run_id,
        "route_status": summary.get("route_status"),
        "selected_workflow": summary.get("selected_workflow"),
        "next_action": summary.get("next_action"),
        "approval_type": summary.get("approval_type"),
        "target_repo_read": summary.get("target_repo_read"),
        "blocker_count": summary.get("blocker_count"),
        "record_status": record.get("status") if isinstance(record, dict) else None,
    }


def validate_anythingllm_case(
    config: argparse.Namespace,
    target_root: str,
    message: str,
    *,
    api_key: str,
) -> dict[str, Any]:
    status, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={"message": message, "mode": "chat", "sessionId": f"phase105-{uuid.uuid4().hex}"},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=config.timeout_seconds,
    )
    text = text_response(body)
    run_id = run_id_from_text(text)
    record = controller_run(config, run_id)
    return {
        "http_status": status,
        "run_id": run_id,
        "text_has_refactor_marker": "refactor.single_path" in text,
        "text_has_request_approval": "request_approval" in text or "Approval:" in text,
        "record_status": record.get("status") if isinstance(record, dict) else None,
    }


def main() -> int:
    config = parse_args()
    config_root = Path(config.config_root)
    target_roots = config.target_root or DEFAULT_TARGET_ROOTS
    output_path = Path(config.output_path)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    api_key = os.environ.get(config.api_key_env, "")
    report: dict[str, Any] = {
        "kind": "advanced_refactor_readiness_live_natural_validation",
        "schema_version": 1,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target_roots": target_roots,
        "ports": validate_port_health(config),
        "cases": [],
        "errors": [],
    }
    for port in report["ports"]:
        if port.get("status") != "passed":
            report["errors"].append(f"port {port.get('label')} returned {port.get('http_status')}")
    if not config.skip_anythingllm and not api_key:
        report["errors"].append(f"{config.api_key_env} is missing")

    for target_root in target_roots:
        before = fixture_state(target_root)
        message = advanced_refactor_prompt(target_root)
        gateway = validate_gateway_case(config, target_root, message)
        anythingllm: dict[str, Any] = {"skipped": True}
        if not config.skip_anythingllm and api_key:
            anythingllm = validate_anythingllm_case(config, target_root, message, api_key=api_key)
        after = fixture_state(target_root)
        source_unchanged = before == after
        case = {
            "target_root": target_root,
            "source_unchanged": source_unchanged,
            "gateway": gateway,
            "anythingllm": anythingllm,
        }
        if (
            gateway.get("http_status") != 200
            or gateway.get("selected_workflow") != "refactor.single_path"
            or gateway.get("next_action") != "request_approval"
            or gateway.get("approval_type") != "packet_design"
        ):
            report["errors"].append(f"gateway advanced refactor readiness failed for {target_root}: {gateway}")
        if not config.skip_anythingllm and (
            anythingllm.get("http_status") != 200
            or anythingllm.get("run_id") == "unknown"
            or anythingllm.get("text_has_refactor_marker") is not True
        ):
            report["errors"].append(f"AnythingLLM advanced refactor readiness failed for {target_root}: {anythingllm}")
        if not source_unchanged:
            report["errors"].append(f"protected target changed for {target_root}")
        report["cases"].append(case)

    report["status"] = "passed" if not report["errors"] else "failed"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"PHASE105 LIVE NATURAL REPORT {output_path}")
    print(
        "PHASE105 LIVE NATURAL SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "case_count": len(report["cases"]),
                "error_count": len(report["errors"]),
                "port_count": len(report["ports"]),
                "anythingllm_skipped": bool(config.skip_anythingllm),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["errors"]:
        print("PHASE105 LIVE NATURAL ERRORS " + json.dumps(report["errors"], ensure_ascii=True, indent=2))
        return 1
    print("PHASE105 LIVE NATURAL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
