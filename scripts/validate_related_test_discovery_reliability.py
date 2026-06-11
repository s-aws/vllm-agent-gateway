#!/usr/bin/env python3
"""Validate Phase 183 related-test discovery reliability."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.related_test_discovery_reliability import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    build_synthetic_report,
    load_policy,
    validate_policy,
    validate_related_test_discovery_reliability_report,
)


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
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Related-Test Discovery Reliability Report",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Synthetic cases: `{report.get('passed_case_count')}/{report.get('case_count')}`",
        f"- Live cases: `{report.get('live_passed_case_count', 0)}/{report.get('live_case_count', 0)}`",
        f"- Errors: `{len(report.get('errors', []))}`",
        "",
        "## Live Cases",
    ]
    for case in report.get("live_cases", []):
        if isinstance(case, dict):
            lines.append(
                f"- `{case.get('surface')}` `{case.get('case_kind')}` `{case.get('target_root')}`: `{case.get('status')}` run=`{case.get('run_id')}`"
            )
    if report.get("errors"):
        lines.extend(["", "## Errors"])
        lines.extend(f"- {error}" for error in report["errors"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def direct_prompt(target_root: str) -> str:
    return (
        f"In {target_root}, choose the smallest, medium, and broad validation commands for "
        "placed_order_id stealth lookup. Read only. Explain why each command is relevant, "
        "what risk it covers, and what gaps remain."
    )


def no_test_prompt(target_root: str) -> str:
    return (
        f"In {target_root}, choose the smallest, medium, and broad validation commands for "
        "resolve_payment_timeout. Read only. Explain why each command is relevant, "
        "what risk it covers, and what gaps remain."
    )


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def watched_hashes(target_root: str) -> dict[str, str]:
    root = Path(target_root)
    return {
        relative_path: digest_file(root / relative_path)
        for relative_path in WATCHED_RELATIVE_PATHS
        if (root / relative_path).exists()
    }


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
            return exc.code, json.loads(text)
        except json.JSONDecodeError:
            return exc.code, {"error": {"message": text, "code": "invalid_json_error_body"}}


def assistant_text(body: dict[str, Any]) -> str:
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
    return ""


def run_id_from_text(text: str) -> str:
    if "run_id:" not in text:
        return ""
    return text.split("run_id:", 1)[1].strip().split()[0]


def validate_direct_text(text: str, *, label: str, target_root: str) -> list[str]:
    errors: list[str] = []
    for marker in (
        "Answer:",
        "- Related tests:",
        "tests/unit/test_order_id_and_followup_rules.py",
        "direct evidence",
        "high confidence",
        "python -m pytest tests/unit/test_order_id_and_followup_rules.py",
        "- Source mutation: false",
    ):
        if marker not in text:
            errors.append(f"{label} {target_root} missing direct-test marker {marker!r}")
    return errors


def validate_no_test_text(text: str, *, label: str, target_root: str) -> list[str]:
    errors: list[str] = []
    for marker in (
        "Answer:",
        "- Related tests: none found in bounded evidence",
        "verification_tests_not_found",
        "- Confidence: low",
        "- Source mutation: false",
    ):
        if marker not in text:
            errors.append(f"{label} {target_root} missing no-test marker {marker!r}")
    if "python -m pytest tests/unit/test_order_id_and_followup_rules.py" in text:
        errors.append(f"{label} {target_root} invented unrelated placed_order_id test command for no-test case")
    return errors


def validate_gateway_artifact(body: dict[str, Any], *, case_kind: str, target_root: str) -> tuple[str, list[str]]:
    compact = body.get("agentic_controller_response")
    if not isinstance(compact, dict):
        return "", [f"gateway {target_root} missing agentic_controller_response"]
    artifacts = compact.get("artifacts") if isinstance(compact.get("artifacts"), dict) else {}
    artifact_path = artifacts.get("downstream_test_selection_plan")
    if not isinstance(artifact_path, str):
        return str(compact.get("run_id") or ""), [f"gateway {target_root} missing downstream_test_selection_plan"]
    artifact = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    errors: list[str] = []
    if case_kind == "direct":
        related = artifact.get("related_tests") if isinstance(artifact.get("related_tests"), list) else []
        first = related[0] if related and isinstance(related[0], dict) else {}
        if first.get("confidence") != "high" or first.get("evidence_kind") != "direct":
            errors.append(f"gateway {target_root} direct related test lacks high/direct evidence: {first}")
        commands = [
            command
            for tier in artifact.get("command_tiers", [])
            if isinstance(tier, dict)
            for command in tier.get("commands", [])
            if isinstance(command, dict)
        ]
        if not any(command.get("confidence") == "high" and command.get("evidence_kind") == "direct" for command in commands):
            errors.append(f"gateway {target_root} direct commands lack evidence metadata")
    else:
        if artifact.get("related_tests") != [] or artifact.get("command_tiers") != []:
            errors.append(f"gateway {target_root} no-test case returned related tests or commands")
        if artifact.get("status") != "not_ready_no_related_tests":
            errors.append(f"gateway {target_root} no-test status was {artifact.get('status')!r}")
    return str(compact.get("run_id") or ""), errors


def run_gateway_case(args: argparse.Namespace, target_root: str, case_kind: str) -> dict[str, Any]:
    before = watched_hashes(target_root)
    prompt = direct_prompt(target_root) if case_kind == "direct" else no_test_prompt(target_root)
    status, body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={"model": "agentic-workflow-router", "messages": [{"role": "user", "content": prompt}]},
        timeout_seconds=args.timeout_seconds,
    )
    errors: list[str] = []
    text = assistant_text(body)
    run_id = ""
    if status != 200:
        errors.append(f"gateway {target_root} {case_kind} returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    else:
        errors.extend(
            validate_direct_text(text, label="gateway", target_root=target_root)
            if case_kind == "direct"
            else validate_no_test_text(text, label="gateway", target_root=target_root)
        )
        run_id, artifact_errors = validate_gateway_artifact(body, case_kind=case_kind, target_root=target_root)
        errors.extend(artifact_errors)
    if watched_hashes(target_root) != before:
        errors.append(f"gateway {target_root} {case_kind} mutated watched files")
    return {"surface": "workflow_router_gateway", "case_kind": case_kind, "target_root": target_root, "run_id": run_id, "status": "passed" if not errors else "failed", "errors": errors}


def run_anythingllm_case(args: argparse.Namespace, target_root: str, case_kind: str, api_key: str) -> dict[str, Any]:
    before = watched_hashes(target_root)
    prompt = direct_prompt(target_root) if case_kind == "direct" else no_test_prompt(target_root)
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload={"message": prompt, "mode": "chat", "sessionId": f"related-test-discovery-{case_kind}-{uuid.uuid4().hex}"},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=args.timeout_seconds,
    )
    errors: list[str] = []
    text = assistant_text(body)
    if status != 200:
        errors.append(f"AnythingLLM {target_root} {case_kind} returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    else:
        errors.extend(
            validate_direct_text(text, label="AnythingLLM", target_root=target_root)
            if case_kind == "direct"
            else validate_no_test_text(text, label="AnythingLLM", target_root=target_root)
        )
    if watched_hashes(target_root) != before:
        errors.append(f"AnythingLLM {target_root} {case_kind} mutated watched files")
    return {"surface": "anythingllm", "case_kind": case_kind, "target_root": target_root, "run_id": run_id_from_text(text), "status": "passed" if not errors else "failed", "errors": errors}


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    policy = load_policy(Path(args.policy_path))
    errors = validate_policy(policy)
    report = build_synthetic_report(policy)
    errors.extend(validate_related_test_discovery_reliability_report(report))
    live_cases: list[dict[str, Any]] = []
    if args.live:
        api_key = os.environ.get("ANYTHINGLLM_API_KEY", "")
        if not api_key:
            errors.append("ANYTHINGLLM_API_KEY is required for --live")
        for target_root in args.target_roots:
            for case_kind in ("direct", "no_test"):
                live_cases.append(run_gateway_case(args, target_root, case_kind))
                if api_key:
                    live_cases.append(run_anythingllm_case(args, target_root, case_kind, api_key))
    errors.extend(error for case in live_cases for error in case.get("errors", []) if isinstance(error, str))
    report["created_at"] = utc_now()
    report["policy_path"] = args.policy_path
    report["live"] = bool(args.live)
    report["live_cases"] = live_cases
    report["live_case_count"] = len(live_cases)
    report["live_passed_case_count"] = len([case for case in live_cases if case.get("status") == "passed"])
    report["errors"] = errors
    report["status"] = "passed" if not errors else "failed"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default="runtime-state/related-test-discovery-reliability/phase183-report.json")
    parser.add_argument("--markdown-output-path", default="")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--target-roots", nargs="*", default=DEFAULT_TARGET_ROOTS)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args(argv)

    report = build_report(args)
    output_path = Path(args.output_path)
    write_json(output_path, report)
    if args.markdown_output_path:
        write_markdown(Path(args.markdown_output_path), report)
    print(
        "RELATED TEST DISCOVERY RELIABILITY",
        report["status"],
        f"synthetic={report.get('passed_case_count')}/{report.get('case_count')}",
        f"live={report.get('live_passed_case_count')}/{report.get('live_case_count')}",
        f"errors={len(report.get('errors', []))}",
        f"output={output_path}",
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
