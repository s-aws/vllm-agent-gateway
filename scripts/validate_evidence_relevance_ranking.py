#!/usr/bin/env python3
"""Validate Phase 182 evidence relevance ranking."""

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

from vllm_agent_gateway.acceptance.evidence_relevance_ranking import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    build_synthetic_report,
    load_policy,
    validate_evidence_relevance_ranking_report,
    validate_policy,
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
    "core/order_engine.py",
    "tests/unit/test_order_id_and_followup_rules.py",
    "database/order.py",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Evidence Relevance Ranking Report",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Synthetic cases: `{report.get('passed_case_count')}/{report.get('case_count')}`",
        f"- Live cases: `{report.get('live_passed_case_count', 0)}/{report.get('live_case_count', 0)}`",
        f"- Errors: `{len(report.get('errors', []))}`",
        "",
        "## Synthetic Cases",
    ]
    for case in report.get("cases", []):
        if not isinstance(case, dict):
            continue
        lines.append(f"- `{case.get('case_id')}`: `{case.get('status')}` top=`{case.get('actual_top_path') or case.get('actual_top_query') or case.get('actual_top_role')}`")
    if report.get("live_cases"):
        lines.extend(["", "## Live Cases"])
        for case in report.get("live_cases", []):
            if not isinstance(case, dict):
                continue
            lines.append(
                f"- `{case.get('surface')}` `{case.get('target_root')}`: `{case.get('status')}` run=`{case.get('run_id')}`"
            )
    if report.get("errors"):
        lines.extend(["", "## Errors"])
        for error in report["errors"]:
            lines.append(f"- {error}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def prompt(target_root: str) -> str:
    return (
        f"In {target_root}, identify files to touch and files not to touch for a minimal safe "
        "placed_order_id stealth lookup change. Read only and stop before implementation. "
        "Lead with strongest evidence, related tests, risks, gaps, and verification commands."
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


def validate_chat_text(text: str, *, label: str, target_root: str) -> list[str]:
    errors: list[str] = []
    required = [
        "Answer:",
        "- Change surface files:",
        "- Files to touch:",
        "core/stealth_order_manager.py",
        "evidence",
        "- Files not to touch:",
        "- Source mutation: false",
    ]
    for marker in required:
        if marker not in text:
            errors.append(f"{label} {target_root} missing chat marker {marker!r}")
    manager_index = text.find("core/stealth_order_manager.py")
    order_engine_index = text.find("core/order_engine.py")
    if manager_index >= 0 and order_engine_index >= 0 and manager_index > order_engine_index:
        errors.append(f"{label} {target_root} demoted manager-owned evidence below caller evidence")
    if "direct evidence" not in text and "strong evidence" not in text:
        errors.append(f"{label} {target_root} missing direct/strong evidence relevance label")
    return errors


def validate_gateway_artifact(body: dict[str, Any], *, target_root: str) -> tuple[str, list[str]]:
    errors: list[str] = []
    compact = body.get("agentic_controller_response")
    if not isinstance(compact, dict):
        return "", [f"gateway {target_root} missing agentic_controller_response"]
    summary = compact.get("summary") if isinstance(compact.get("summary"), dict) else {}
    if summary.get("selected_workflow") != "code_investigation.plan":
        errors.append(f"gateway {target_root} selected wrong workflow {summary.get('selected_workflow')!r}")
    artifacts = compact.get("artifacts") if isinstance(compact.get("artifacts"), dict) else {}
    artifact_path = artifacts.get("downstream_change_surface_summary")
    if not isinstance(artifact_path, str) or not artifact_path:
        return str(compact.get("run_id") or ""), errors + [f"gateway {target_root} missing downstream_change_surface_summary"]
    try:
        artifact = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return str(compact.get("run_id") or ""), errors + [f"gateway {target_root} could not read change surface artifact: {exc}"]
    touch = [item for item in artifact.get("files_to_touch", []) if isinstance(item, dict)]
    touch_paths = [item.get("path") for item in touch]
    if "core/stealth_order_manager.py" not in touch_paths[:2]:
        errors.append(f"gateway {target_root} did not lead files_to_touch with manager-owned evidence: {touch_paths[:4]}")
    manager = next((item for item in touch if item.get("path") == "core/stealth_order_manager.py"), {})
    relevance = manager.get("relevance") if isinstance(manager.get("relevance"), dict) else {}
    if relevance.get("tier") not in {"direct", "strong"}:
        errors.append(f"gateway {target_root} manager evidence tier was not direct/strong: {relevance}")
    do_not_touch = [item.get("path") for item in artifact.get("files_not_to_touch", []) if isinstance(item, dict)]
    if "core/order_engine.py" not in do_not_touch:
        errors.append(f"gateway {target_root} missing caller do-not-touch boundary: {do_not_touch[:4]}")
    if artifact.get("mutation_policy") != "read_only_no_source_mutation":
        errors.append(f"gateway {target_root} missing read-only mutation policy")
    return str(compact.get("run_id") or ""), errors


def run_gateway_case(args: argparse.Namespace, target_root: str) -> dict[str, Any]:
    before = watched_hashes(target_root)
    status, body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={"model": "agentic-workflow-router", "messages": [{"role": "user", "content": prompt(target_root)}]},
        timeout_seconds=args.timeout_seconds,
    )
    errors: list[str] = []
    if status != 200:
        errors.append(f"gateway {target_root} returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
        text = ""
        run_id = ""
    else:
        text = assistant_text(body)
        errors.extend(validate_chat_text(text, label="gateway", target_root=target_root))
        run_id, artifact_errors = validate_gateway_artifact(body, target_root=target_root)
        errors.extend(artifact_errors)
    if watched_hashes(target_root) != before:
        errors.append(f"gateway {target_root} mutated watched files")
    return {
        "surface": "workflow_router_gateway",
        "target_root": target_root,
        "status": "passed" if not errors else "failed",
        "run_id": run_id,
        "errors": errors,
    }


def run_anythingllm_case(args: argparse.Namespace, target_root: str, api_key: str) -> dict[str, Any]:
    before = watched_hashes(target_root)
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload={
            "message": prompt(target_root),
            "mode": "chat",
            "sessionId": f"evidence-relevance-ranking-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=args.timeout_seconds,
    )
    errors: list[str] = []
    text = assistant_text(body)
    if status != 200:
        errors.append(f"AnythingLLM {target_root} returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    else:
        errors.extend(validate_chat_text(text, label="AnythingLLM", target_root=target_root))
    if watched_hashes(target_root) != before:
        errors.append(f"AnythingLLM {target_root} mutated watched files")
    return {
        "surface": "anythingllm",
        "target_root": target_root,
        "status": "passed" if not errors else "failed",
        "run_id": run_id_from_text(text),
        "errors": errors,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    policy = load_policy(Path(args.policy_path))
    errors = validate_policy(policy)
    report = build_synthetic_report(policy)
    errors.extend(validate_evidence_relevance_ranking_report(report))
    live_cases: list[dict[str, Any]] = []
    if args.live:
        api_key = os.environ.get("ANYTHINGLLM_API_KEY", "")
        if not api_key:
            errors.append("ANYTHINGLLM_API_KEY is required for --live")
        for target_root in args.target_roots:
            live_cases.append(run_gateway_case(args, target_root))
            if api_key:
                live_cases.append(run_anythingllm_case(args, target_root, api_key))
    live_errors = [error for case in live_cases for error in case.get("errors", []) if isinstance(error, str)]
    errors.extend(live_errors)
    report["policy_path"] = args.policy_path
    report["created_at"] = utc_now()
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
    parser.add_argument("--output-path", default="runtime-state/evidence-relevance-ranking/phase182-report.json")
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
        "EVIDENCE RELEVANCE RANKING",
        report["status"],
        f"synthetic={report.get('passed_case_count')}/{report.get('case_count')}",
        f"live={report.get('live_passed_case_count')}/{report.get('live_case_count')}",
        f"errors={len(report.get('errors', []))}",
        f"output={output_path}",
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
