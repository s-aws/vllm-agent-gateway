#!/usr/bin/env python3
"""Validate the skill authoring factory through live localhost surfaces."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CONTROLLER_BASE_URL = "http://127.0.0.1:8400"
DEFAULT_GATEWAY_BASE_URL = "http://127.0.0.1:8300/v1"
DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "skill-authoring-factory"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def json_request(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: int,
) -> tuple[int, dict[str, Any]]:
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=request_headers, method="GET" if data is None else "POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8", errors="replace")
            body = json.loads(text) if text.strip() else {}
            return response.status, body if isinstance(body, dict) else {"value": body}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            body = {"error": text}
        return exc.code, body if isinstance(body, dict) else {"value": body}


def openai_chat_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def scaffold_spec(label: str) -> dict[str, Any]:
    route_slug = label.replace("-", "_")
    return {
        "skill_id": f"{label}-locator",
        "description": f"Locate bounded source evidence for {label} authoring factory live validation.",
        "prompt_family": f"{label}-lookup",
        "natural_prompt": f"In <repo>, find {label} authoring factory evidence. Read only.",
        "workflow_id": "code_investigation.plan",
        "route_key": f"code.{route_slug}_lookup",
        "trigger_terms": [f"{label} authoring factory lookup"],
        "task_types": [f"{route_slug}_lookup"],
        "output_artifact": "investigation_plan",
        "live_suite": "skill_registry_contract",
        "coverage_id": label.upper().replace("-", "-"),
        "level": "L1",
        "route_rule": "l1_find_behavior_start_terms",
        "tool_ids": ["git_grep", "read_file"],
        "docs": ["README.skill-registry.md", "docs/SKILL_LIBRARY_SCALING_PLAN.md"],
        "problem_solving_steps": [4],
    }


def controller_payload(label: str) -> dict[str, Any]:
    return {
        "workflow": "skill.scaffold",
        "schema_version": 1,
        "prompt_family_spec": scaffold_spec(label),
    }


def natural_prompt(label: str) -> str:
    spec = scaffold_spec(label)
    return "\n".join(
        [
            "Scaffold a skill for a deterministic L1 prompt family.",
            f"skill_id: {spec['skill_id']}",
            f"description: {spec['description']}",
            f"prompt_family: {spec['prompt_family']}",
            f"natural_prompt: {spec['natural_prompt']}",
            f"workflow_id: {spec['workflow_id']}",
            f"route_key: {spec['route_key']}",
            f"trigger_terms: {', '.join(spec['trigger_terms'])}",
            f"task_types: {', '.join(spec['task_types'])}",
            f"output_artifact: {spec['output_artifact']}",
            f"live_suite: {spec['live_suite']}",
            f"coverage_id: {spec['coverage_id']}",
            f"level: {spec['level']}",
            f"route_rule: {spec['route_rule']}",
            f"tool_ids: {', '.join(spec['tool_ids'])}",
        ]
    )


def require_scaffold_response(body: dict[str, Any], label: str) -> dict[str, Any]:
    compact = body.get("agentic_controller_response") if isinstance(body.get("agentic_controller_response"), dict) else body
    summary = compact.get("summary") if isinstance(compact.get("summary"), dict) else {}
    artifacts = compact.get("artifacts") if isinstance(compact.get("artifacts"), dict) else {}
    expected_skill_id = f"{label}-locator"
    if compact.get("workflow") != "skill.scaffold":
        raise RuntimeError(f"expected workflow skill.scaffold, got {compact.get('workflow')!r}")
    if summary.get("skill_id") != expected_skill_id:
        raise RuntimeError(f"expected skill_id {expected_skill_id}, got {summary.get('skill_id')!r}")
    if summary.get("scaffold_status") != "ready":
        raise RuntimeError(f"expected ready scaffold, got {summary.get('scaffold_status')!r}")
    if summary.get("authoring_factory_status") != "draft_sidecars_generated":
        raise RuntimeError("authoring factory sidecars were not reported")
    if summary.get("promotion_state") != "not_promoted_by_scaffold":
        raise RuntimeError("scaffold did not preserve not-promoted state")
    missing = sorted(
        set(
            [
                "prompt_coverage_entry",
                "eval_skeleton",
                "docs_stub",
                "docs_example_stub",
                "regression_test_skeleton",
                "authoring_factory_report",
            ]
        )
        - set(artifacts)
    )
    if missing:
        raise RuntimeError(f"missing authoring factory artifact(s): {', '.join(missing)}")
    return compact


def text_response(body: dict[str, Any]) -> str:
    for key in ("textResponse", "response", "message", "text"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            return value
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"]
    return ""


def validate_chat_text(body: dict[str, Any]) -> None:
    text = text_response(body)
    required = [
        "Skill Scaffold:",
        "Authoring factory: draft_sidecars_generated",
        "Promotion state: not_promoted_by_scaffold",
        "Factory sidecars:",
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeError(f"chat text missing marker(s): {', '.join(missing)}")


def port_smoke(args: argparse.Namespace) -> list[dict[str, Any]]:
    urls = [
        ("model_8000", "http://127.0.0.1:8000/v1/models"),
        ("gateway_8300", f"{args.gateway_base_url.rstrip('/')}/models"),
        ("workflow_router_8500", f"{args.workflow_router_gateway_base_url.rstrip('/')}/models"),
        ("controller_8400", f"{args.controller_base_url.rstrip('/')}/health"),
        ("documenter_8205", "http://127.0.0.1:8205/v1/models"),
    ]
    checks: list[dict[str, Any]] = []
    for label, url in urls:
        status, body = json_request(url, timeout_seconds=args.timeout_seconds)
        check = {"label": label, "url": url, "status": "passed" if status == 200 else "failed", "http_status": status}
        if status != 200:
            check["body"] = body
        checks.append(check)
    return checks


def validate_direct_controller(args: argparse.Namespace, label: str) -> dict[str, Any]:
    status, body = json_request(
        f"{args.controller_base_url.rstrip('/')}/v1/controller/skill-scaffolds",
        payload=controller_payload(label),
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"direct controller returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    compact = require_scaffold_response(body, label)
    return {"status": "passed", "http_status": status, "run_id": compact.get("run_id"), "summary": compact.get("summary")}


def validate_explicit_gateway(args: argparse.Namespace, label: str) -> dict[str, Any]:
    payload = {"model": "agentic-controller", "agentic_controller_request": controller_payload(label)}
    status, body = json_request(openai_chat_url(args.gateway_base_url), payload=payload, timeout_seconds=args.timeout_seconds)
    if status != 200:
        raise RuntimeError(f"explicit gateway returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    compact = require_scaffold_response(body, label)
    validate_chat_text(body)
    return {"status": "passed", "http_status": status, "run_id": compact.get("run_id"), "summary": compact.get("summary")}


def validate_workflow_router_gateway(args: argparse.Namespace, label: str) -> dict[str, Any]:
    payload = {
        "model": "agentic-workflow-router",
        "messages": [{"role": "user", "content": natural_prompt(label)}],
    }
    status, body = json_request(
        openai_chat_url(args.workflow_router_gateway_base_url),
        payload=payload,
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"workflow-router gateway returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    compact = require_scaffold_response(body, label)
    validate_chat_text(body)
    return {"status": "passed", "http_status": status, "run_id": compact.get("run_id"), "summary": compact.get("summary")}


def validate_anythingllm(args: argparse.Namespace, label: str, api_key: str) -> dict[str, Any]:
    payload = {
        "message": natural_prompt(label),
        "mode": "chat",
        "sessionId": f"skill-authoring-factory-{label}-{uuid.uuid4().hex}",
    }
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"AnythingLLM returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    validate_chat_text(body)
    text = text_response(body)
    return {"status": "passed", "http_status": status, "text_sample": text[:1200]}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller-base-url", default=DEFAULT_CONTROLLER_BASE_URL)
    parser.add_argument("--gateway-base-url", default=DEFAULT_GATEWAY_BASE_URL)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--skip-anythingllm", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output_path) if args.output_path else DEFAULT_OUTPUT_DIR / f"phase80-live-{utc_timestamp()}.json"
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "skill_authoring_factory_live_report",
        "status": "failed",
        "created_at": utc_timestamp(),
        "port_smoke": port_smoke(args),
        "checks": {},
        "anythingllm_applicable": not args.skip_anythingllm,
    }
    try:
        failed_ports = [item for item in report["port_smoke"] if item["status"] != "passed"]
        if failed_ports:
            raise RuntimeError(f"port smoke failed: {failed_ports}")
        report["checks"]["direct_controller"] = validate_direct_controller(args, "phase80-live-direct")
        report["checks"]["explicit_gateway_8300"] = validate_explicit_gateway(args, "phase80-live-gateway")
        report["checks"]["workflow_router_gateway_8500"] = validate_workflow_router_gateway(args, "phase80-live-router")
        if not args.skip_anythingllm:
            api_key = os.environ.get(args.api_key_env)
            if not api_key:
                raise RuntimeError(f"{args.api_key_env} is required unless --skip-anythingllm is set")
            report["checks"]["anythingllm"] = validate_anythingllm(args, "phase80-live-anythingllm", api_key)
        report["status"] = "passed"
    except Exception as exc:
        report["error"] = str(exc)
        write_json(output_path, report)
        print(f"SKILL AUTHORING FACTORY LIVE REPORT {output_path}")
        print("SKILL AUTHORING FACTORY LIVE FAIL " + str(exc))
        return 1
    write_json(output_path, report)
    print(f"SKILL AUTHORING FACTORY LIVE REPORT {output_path}")
    print("SKILL AUTHORING FACTORY LIVE PASS")
    print(json.dumps({"status": report["status"], "checks": sorted(report["checks"])}, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
