#!/usr/bin/env python3
"""Validate the Phase 125 founder-feedback loop through gateway and AnythingLLM."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
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
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    PORT_HEALTH_PROBES,
    WATCHED_RUNTIME_FILES,
    changed_hashes,
    git_status,
    json_request,
    text_response,
    validate_no_target_mutation,
    watched_files_for_root,
    watched_hashes,
    write_json,
)
from vllm_agent_gateway.acceptance.founder_feedback_loop import (  # noqa: E402
    DEFAULT_CASES_PATH,
    FounderFeedbackLoopCase,
    feedback_decision_for_record,
    load_founder_feedback_loop_cases,
    validate_case_catalog,
    validate_feedback_record_decision,
    validate_founder_feedback_loop_report,
)


DEFAULT_OUTPUT_PATH = "runtime-state/founder-feedback-loop/phase125-founder-feedback-loop-live.json"
RUN_ID_RE = re.compile(r"run_id:\s*(?P<run_id>[A-Za-z0-9_.:-]+)")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git_metadata(path: Path) -> dict[str, Any]:
    def git_output(*args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", "-C", str(path), *args],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        value = result.stdout.strip()
        return value if result.returncode == 0 and value else None

    return {
        "branch": git_output("rev-parse", "--abbrev-ref", "HEAD"),
        "commit": git_output("rev-parse", "HEAD"),
        "remote_origin_url": git_output("config", "--get", "remote.origin.url"),
        "status_short": git_output("status", "--short") or "",
    }


def workflow_router_gateway_payload(message: str) -> dict[str, Any]:
    return {"model": "agentic-workflow-router", "messages": [{"role": "user", "content": message}]}


def anythingllm_payload(case: FounderFeedbackLoopCase, message: str, *, phase: str) -> dict[str, Any]:
    return {
        "message": message,
        "mode": "chat",
        "sessionId": f"founder-feedback-loop-{case.case_id.lower()}-{phase}-{uuid.uuid4().hex}",
    }


def run_id_from_text(text: str) -> str:
    match = RUN_ID_RE.search(text)
    if not match:
        raise RuntimeError(f"response text did not include run_id marker: {text[:500]}")
    return match.group("run_id")


def read_json_artifact(path_value: Any) -> dict[str, Any]:
    if not isinstance(path_value, str) or not path_value:
        raise RuntimeError(f"artifact path was not a string: {path_value!r}")
    path = Path(path_value)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"artifact did not contain an object: {path}")
    return value


def controller_run_record(args: argparse.Namespace, run_id: str) -> dict[str, Any]:
    status, body = json_request(
        f"{args.controller_base_url.rstrip('/')}/v1/controller/runs/{run_id}",
        timeout_seconds=args.timeout_seconds,
        method="GET",
    )
    if status != 200:
        raise RuntimeError(f"controller run lookup returned HTTP {status} for {run_id}: {json.dumps(body, ensure_ascii=True)}")
    if not isinstance(body, dict):
        raise RuntimeError(f"controller run lookup returned non-object for {run_id}")
    return body


def feedback_record_from_run(args: argparse.Namespace, feedback_run_id: str) -> dict[str, Any]:
    run_record = controller_run_record(args, feedback_run_id)
    artifacts = run_record.get("artifacts") if isinstance(run_record.get("artifacts"), dict) else {}
    feedback_record_path = artifacts.get("feedback_record")
    return read_json_artifact(feedback_record_path)


def send_gateway_message(args: argparse.Namespace, message: str) -> tuple[int, dict[str, Any], str]:
    status, body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload=workflow_router_gateway_payload(message),
        timeout_seconds=args.timeout_seconds,
    )
    text = text_response(body) if status == 200 else ""
    return status, body, text


def send_anythingllm_message(
    args: argparse.Namespace,
    case: FounderFeedbackLoopCase,
    message: str,
    api_key: str,
    *,
    phase: str,
) -> tuple[int, dict[str, Any], str]:
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload=anythingllm_payload(case, message, phase=phase),
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=args.timeout_seconds,
    )
    text = text_response(body) if status == 200 else ""
    return status, body, text


def validate_port_health(timeout_seconds: int) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for label, url in PORT_HEALTH_PROBES:
        status, body = json_request(url, timeout_seconds=timeout_seconds, method="GET")
        if status != 200:
            raise RuntimeError(f"{label} health probe returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
        checks.append({"label": label, "url": url, "status": "passed"})
        print(f"FOUNDER FEEDBACK PORT PASS label={label} url={url}")
    return checks


def run_case(args: argparse.Namespace, case: FounderFeedbackLoopCase, api_key: str | None) -> dict[str, Any]:
    errors: list[str] = []
    if case.surface == "gateway":
        seed_status, seed_body, seed_text = send_gateway_message(args, case.seed_prompt)
    elif case.surface == "anythingllm":
        if not api_key:
            raise RuntimeError("AnythingLLM case selected without an API key")
        seed_status, seed_body, seed_text = send_anythingllm_message(args, case, case.seed_prompt, api_key, phase="seed")
    else:
        raise RuntimeError(f"unsupported surface: {case.surface}")
    if seed_status != 200:
        errors.append(f"seed request returned HTTP {seed_status}: {json.dumps(seed_body, ensure_ascii=True)}")
        return {
            "case_id": case.case_id,
            "status": "failed",
            "surface": case.surface,
            "target_root": case.target_root,
            "errors": errors,
        }
    target_run_id = run_id_from_text(seed_text)
    feedback_message = f"{case.feedback_template.format(run_id=target_run_id)} prompt case: {case.case_id}."
    if case.surface == "gateway":
        feedback_status, feedback_body, feedback_text = send_gateway_message(args, feedback_message)
    else:
        feedback_status, feedback_body, feedback_text = send_anythingllm_message(
            args,
            case,
            feedback_message,
            str(api_key),
            phase="feedback",
        )
    if feedback_status != 200:
        errors.append(f"feedback request returned HTTP {feedback_status}: {json.dumps(feedback_body, ensure_ascii=True)}")
        return {
            "case_id": case.case_id,
            "status": "failed",
            "surface": case.surface,
            "target_root": case.target_root,
            "target_run_id": target_run_id,
            "errors": errors,
        }
    feedback_run_id = run_id_from_text(feedback_text)
    feedback_record = feedback_record_from_run(args, feedback_run_id)
    decision = feedback_decision_for_record(feedback_record, case)
    if feedback_record.get("target_run_id") != target_run_id:
        errors.append(
            f"{case.case_id} feedback record target_run_id {feedback_record.get('target_run_id')!r} "
            f"did not match seeded run {target_run_id!r}"
        )
    if decision.get("target_run_id") != target_run_id:
        errors.append(
            f"{case.case_id} decision target_run_id {decision.get('target_run_id')!r} "
            f"did not match seeded run {target_run_id!r}"
        )
    errors.extend(validate_feedback_record_decision(case, feedback_record, decision))
    return {
        "case_id": case.case_id,
        "status": "passed" if not errors else "failed",
        "surface": case.surface,
        "target_root": case.target_root,
        "target_run_id": target_run_id,
        "feedback_run_id": feedback_run_id,
        "feedback_record": feedback_record,
        "decision": decision,
        "errors": errors,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=DEFAULT_CONFIG_ROOT)
    parser.add_argument("--cases-path", default=str(DEFAULT_CASES_PATH))
    parser.add_argument("--controller-base-url", default=DEFAULT_CONTROLLER_BASE_URL)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--output-path", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--required-decision-kind", action="append", dest="required_decision_kinds")
    parser.add_argument("--skip-port-health", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root).resolve()
    output_path = Path(args.output_path)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    all_cases = load_founder_feedback_loop_cases(Path(args.cases_path))
    if args.case_ids:
        requested = set(args.case_ids)
        cases = [case for case in all_cases if case.case_id in requested]
        missing = sorted(requested - {case.case_id for case in cases})
        if missing:
            raise RuntimeError(f"Unknown case ids requested: {missing}")
    else:
        cases = all_cases
    required_decisions = set(args.required_decision_kinds) if args.required_decision_kinds else None
    catalog_errors = validate_case_catalog(cases, required_decisions=required_decisions)
    if catalog_errors:
        raise RuntimeError(f"founder feedback loop case catalog failed: {catalog_errors}")

    needs_anythingllm = any(case.surface == "anythingllm" for case in cases)
    api_key = os.environ.get(args.api_key_env)
    if needs_anythingllm and not api_key:
        raise RuntimeError(f"{args.api_key_env} is required for AnythingLLM feedback cases")

    target_roots = sorted({case.target_root for case in cases})
    runtime_before = watched_hashes(config_root, WATCHED_RUNTIME_FILES)
    target_watch_files = {root: watched_files_for_root(Path(root)) for root in target_roots}
    target_before = {root: watched_hashes(Path(root), target_watch_files[root]) for root in target_roots}
    target_git_before = {root: git_status(Path(root)) for root in target_roots}

    report_cases: list[dict[str, Any]] = []
    for case in cases:
        case_report = run_case(args, case, api_key)
        validate_no_target_mutation(
            Path(case.target_root),
            target_watch_files[case.target_root],
            target_before[case.target_root],
            target_git_before[case.target_root],
            f"founder feedback loop {case.case_id}",
        )
        report_cases.append(case_report)
        print(f"FOUNDER FEEDBACK {case_report['status'].upper()} case={case.case_id} surface={case.surface}")

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
        "kind": "founder_feedback_loop_live_report",
        "schema_version": 1,
        "status": "passed",
        "created_at": utc_now(),
        "priority_backlog_id": "P0-BB-010",
        "config_root": str(config_root),
        "source_git": git_metadata(config_root),
        "cases_path": str(Path(args.cases_path)),
        "controller_base_url": args.controller_base_url,
        "workflow_router_gateway_base_url": args.workflow_router_gateway_base_url,
        "anythingllm_api_base_url": args.anythingllm_api_base_url,
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
    report_errors = validate_founder_feedback_loop_report(report, cases, required_decisions=required_decisions)
    if report_errors:
        report["status"] = "failed"
        report["errors"] = report_errors
    write_json(output_path, report)
    print(f"FOUNDER FEEDBACK LOOP REPORT {report['status'].upper()} path={output_path}")
    if report_errors:
        print(json.dumps(report_errors, ensure_ascii=True, indent=2, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
