#!/usr/bin/env python3
"""Validate Priority 0 output-format parity through gateway and AnythingLLM."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_task_decomposition_live import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONFIG_ROOT,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    PORT_HEALTH_PROBES,
    WATCHED_RUNTIME_FILES,
    changed_hashes,
    git_status,
    json_request,
    validate_no_target_mutation,
    watched_files_for_root,
    watched_hashes,
    write_json,
)
from vllm_agent_gateway.acceptance.output_format_parity import (  # noqa: E402
    DEFAULT_CASES_PATH,
    OutputFormatParityCase,
    assistant_text_from_body,
    load_output_format_parity_cases,
    parse_assistant_json,
    validate_case_catalog,
    validate_output_format_pair,
    validate_output_format_parity_report,
)


DEFAULT_OUTPUT_PATH = "runtime-state/output-format-parity/phase124-output-format-parity-live.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def gateway_payload(case: OutputFormatParityCase, *, json_output: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": "agentic-workflow-router",
        "messages": [{"role": "user", "content": case.prompt}],
    }
    if json_output:
        payload["output_format"] = "json"
        payload["response_format"] = {"type": "json_object"}
    return payload


def anythingllm_payload(case: OutputFormatParityCase, *, json_output: bool) -> dict[str, Any]:
    prompt = f"{case.prompt}\nReturn JSON." if json_output else case.prompt
    suffix = "json" if json_output else "format-a"
    return {
        "message": prompt,
        "mode": "chat",
        "sessionId": f"output-format-parity-{case.case_id.lower()}-{suffix}-{uuid.uuid4().hex}",
    }


def run_id_from_gateway_body(body: dict[str, Any]) -> str:
    compact = body.get("agentic_controller_response")
    if isinstance(compact, dict) and isinstance(compact.get("run_id"), str):
        return compact["run_id"]
    return ""


def run_id_from_json_object(parsed: dict[str, Any]) -> str:
    value = parsed.get("run_id")
    return value if isinstance(value, str) else ""


def collect_gateway_pair(args: argparse.Namespace, case: OutputFormatParityCase) -> dict[str, Any]:
    format_status, format_body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload=gateway_payload(case, json_output=False),
        timeout_seconds=args.timeout_seconds,
    )
    if format_status != 200:
        return {
            "status": "failed",
            "errors": [f"gateway FormatA returned HTTP {format_status}: {json.dumps(format_body, ensure_ascii=True)}"],
        }
    format_a_text = assistant_text_from_body(format_body)

    json_status, json_body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload=gateway_payload(case, json_output=True),
        timeout_seconds=args.timeout_seconds,
    )
    if json_status != 200:
        return {
            "status": "failed",
            "errors": [f"gateway JSON returned HTTP {json_status}: {json.dumps(json_body, ensure_ascii=True)}"],
            "format_a": {"http_status": format_status, "run_id": run_id_from_gateway_body(format_body), "text": format_a_text},
        }
    json_text = assistant_text_from_body(json_body)
    parsed = parse_assistant_json(json_text)
    errors = validate_output_format_pair(case, format_a_text=format_a_text, json_object=parsed)
    return {
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "format_a": {"http_status": format_status, "run_id": run_id_from_gateway_body(format_body), "text": format_a_text},
        "json": {
            "http_status": json_status,
            "run_id": run_id_from_json_object(parsed),
            "text": json_text,
            "parsed": parsed,
        },
    }


def collect_anythingllm_pair(args: argparse.Namespace, case: OutputFormatParityCase, api_key: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}"}
    format_status, format_body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload=anythingllm_payload(case, json_output=False),
        headers=headers,
        timeout_seconds=args.timeout_seconds,
    )
    if format_status != 200:
        return {
            "status": "failed",
            "errors": [
                f"AnythingLLM FormatA returned HTTP {format_status}: {json.dumps(format_body, ensure_ascii=True)}"
            ],
        }
    format_a_text = assistant_text_from_body(format_body)

    json_status, json_body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload=anythingllm_payload(case, json_output=True),
        headers=headers,
        timeout_seconds=args.timeout_seconds,
    )
    if json_status != 200:
        return {
            "status": "failed",
            "errors": [f"AnythingLLM JSON returned HTTP {json_status}: {json.dumps(json_body, ensure_ascii=True)}"],
            "format_a": {"http_status": format_status, "text": format_a_text},
        }
    json_text = assistant_text_from_body(json_body)
    parsed = parse_assistant_json(json_text)
    errors = validate_output_format_pair(
        case,
        format_a_text=format_a_text,
        json_object=parsed,
        require_exact_inline_match=False,
    )
    return {
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "format_a": {"http_status": format_status, "text": format_a_text},
        "json": {
            "http_status": json_status,
            "run_id": run_id_from_json_object(parsed),
            "text": json_text,
            "parsed": parsed,
        },
    }


def validate_port_health(timeout_seconds: int) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for label, url in PORT_HEALTH_PROBES:
        status, body = json_request(url, timeout_seconds=timeout_seconds, method="GET")
        if status != 200:
            raise RuntimeError(f"{label} health probe returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
        checks.append({"label": label, "url": url, "status": "passed"})
        print(f"OUTPUT FORMAT PARITY PORT PASS label={label} url={url}")
    return checks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=DEFAULT_CONFIG_ROOT)
    parser.add_argument("--cases-path", default=str(DEFAULT_CASES_PATH))
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--output-path", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--skip-gateway", action="store_true")
    parser.add_argument("--skip-anythingllm", action="store_true")
    parser.add_argument("--skip-port-health", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root).resolve()
    output_path = Path(args.output_path)
    if not output_path.is_absolute():
        output_path = config_root / output_path

    all_cases = load_output_format_parity_cases(Path(args.cases_path), repo_root=config_root)
    if args.case_ids:
        requested = set(args.case_ids)
        cases = [case for case in all_cases if case.case_id in requested]
        missing = sorted(requested - {case.case_id for case in cases})
        if missing:
            raise RuntimeError(f"Unknown case ids requested: {missing}")
    else:
        cases = all_cases
    catalog_errors = validate_case_catalog(cases)
    if catalog_errors:
        raise RuntimeError(f"output format parity case catalog failed: {catalog_errors}")

    if args.skip_gateway and args.skip_anythingllm:
        raise RuntimeError("At least one live surface must be enabled")
    api_key = os.environ.get(args.api_key_env)
    if not args.skip_anythingllm and not api_key:
        raise RuntimeError(f"{args.api_key_env} is required unless --skip-anythingllm is set")

    target_roots = sorted({case.target_root for case in cases})
    runtime_before = watched_hashes(config_root, WATCHED_RUNTIME_FILES)
    target_watch_files = {root: watched_files_for_root(Path(root)) for root in target_roots}
    target_before = {root: watched_hashes(Path(root), target_watch_files[root]) for root in target_roots}
    target_git_before = {root: git_status(Path(root)) for root in target_roots}

    report_cases: list[dict[str, Any]] = []
    for case in cases:
        case_report: dict[str, Any] = {
            "case_id": case.case_id,
            "prompt_family": case.prompt_family,
            "target_root": case.target_root,
            "expected_heading": case.expected_heading,
            "expected_artifact_kind": case.expected_artifact_kind,
            "responses": {},
            "errors": [],
        }
        if not args.skip_gateway:
            gateway_report = collect_gateway_pair(args, case)
            case_report["responses"]["gateway"] = gateway_report
            case_report["errors"].extend(gateway_report.get("errors", []))
            validate_no_target_mutation(
                Path(case.target_root),
                target_watch_files[case.target_root],
                target_before[case.target_root],
                target_git_before[case.target_root],
                f"output format parity gateway {case.case_id}",
            )
            print(f"OUTPUT FORMAT PARITY GATEWAY {gateway_report['status'].upper()} case={case.case_id}")
        if not args.skip_anythingllm:
            anythingllm_report = collect_anythingllm_pair(args, case, str(api_key))
            case_report["responses"]["anythingllm"] = anythingllm_report
            case_report["errors"].extend(anythingllm_report.get("errors", []))
            validate_no_target_mutation(
                Path(case.target_root),
                target_watch_files[case.target_root],
                target_before[case.target_root],
                target_git_before[case.target_root],
                f"output format parity AnythingLLM {case.case_id}",
            )
            print(f"OUTPUT FORMAT PARITY ANYTHINGLLM {anythingllm_report['status'].upper()} case={case.case_id}")
        report_cases.append(case_report)

    runtime_changed = changed_hashes(runtime_before, watched_hashes(config_root, WATCHED_RUNTIME_FILES))
    target_changed_files = {
        root: changed_hashes(target_before[root], watched_hashes(Path(root), target_watch_files[root]))
        for root in target_roots
    }
    target_git_changed = {
        root: git_status(Path(root))
        for root in target_roots
        if target_git_before[root] is not None and git_status(Path(root)) != target_git_before[root]
    }
    report = {
        "kind": "output_format_parity_live_report",
        "schema_version": 1,
        "status": "passed",
        "created_at": utc_now(),
        "priority_backlog_id": "P0-BB-009",
        "config_root": str(config_root),
        "cases_path": str(Path(args.cases_path)),
        "workflow_router_gateway_base_url": args.workflow_router_gateway_base_url,
        "anythingllm_api_base_url": args.anythingllm_api_base_url,
        "anythingllm_applicable": not args.skip_anythingllm,
        "port_health": [] if args.skip_port_health else validate_port_health(args.timeout_seconds),
        "case_count": len(report_cases),
        "target_roots": target_roots,
        "cases": report_cases,
        "mutation_proof": {
            "runtime_changed_files": runtime_changed,
            "target_changed_files": target_changed_files,
            "target_git_changed": target_git_changed,
        },
    }
    report_errors = validate_output_format_parity_report(report)
    if report_errors:
        report["status"] = "failed"
        report["errors"] = report_errors
    write_json(output_path, report)
    print(f"OUTPUT FORMAT PARITY REPORT {report['status'].upper()} path={output_path}")
    if report_errors:
        print(json.dumps(report_errors, ensure_ascii=True, indent=2, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
