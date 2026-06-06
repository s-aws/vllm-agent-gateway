#!/usr/bin/env python3
"""Run the V1 founder field-test prompt set through AnythingLLM."""

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_REPORT_DIR = Path("runtime-state") / "founder-field-tests"
DEFAULT_TIMEOUT_SECONDS = 900
WATCHED_RELATIVE_PATHS = [
    "README.md",
    "agent.md",
    "configuration.py",
    "dashboard_server.py",
    "main.py",
    "business/lot_config.py",
    "core/orderbook.py",
    "core/stealth_order_manager.py",
    "database/order.py",
    "docs/agents/INVARIANTS.md",
    "tests/test_dashboard_handler.py",
    "tests/test_lot_tracking_integration.py",
    "tests/unit/test_order_id_and_followup_rules.py",
    "tests/unit/test_orderbook_v2.py",
]


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.prompt_catalogs import (  # noqa: E402
    PromptCatalogCase as FieldPrompt,
    load_founder_field_catalog,
    load_founder_field_prompts,
    prompt_refinements_from_cases,
)

_FOUNDER_FIELD_CATALOG = load_founder_field_catalog(REPO_ROOT)
FIELD_PROMPTS: tuple[FieldPrompt, ...] = load_founder_field_prompts(REPO_ROOT)
PROMPT_REFINEMENTS: dict[str, dict[str, str]] = prompt_refinements_from_cases(FIELD_PROMPTS)
COMMON_FORMAT_A_MARKERS = tuple(_FOUNDER_FIELD_CATALOG["common_format_a_markers"])
COMMON_FORBIDDEN_MARKERS = tuple(_FOUNDER_FIELD_CATALOG["common_forbidden_markers"])


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def json_request(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: int,
) -> tuple[int, dict[str, Any]]:
    request_headers = dict(headers or {})
    data = None
    method = "GET"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body_text = response.read().decode("utf-8")
            try:
                body = json.loads(body_text)
            except json.JSONDecodeError:
                body = {"text": body_text}
            return response.status, body
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(body_text)
        except json.JSONDecodeError:
            body = {"error": {"message": body_text, "code": "invalid_json_error_body"}}
        return exc.code, body


def text_response(body: dict[str, Any]) -> str:
    for key in ("textResponse", "response", "message", "text"):
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
    raise RuntimeError("response did not include assistant text")


def run_id_from_text(text: str) -> str:
    marker = "run_id:"
    if marker not in text:
        return "unknown"
    return text.split(marker, 1)[1].strip().split()[0]


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
        raise RuntimeError(f"{target_root} did not contain watched validation files")
    return hashes


def git_status(target_root: str) -> str | None:
    root = Path(target_root)
    if not (root / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "-C", target_root, "status", "--short"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def fixture_state(target_roots: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    return {
        target_root: {
            "hashes": watched_hashes(target_root),
            "git_status": git_status(target_root),
        }
        for target_root in sorted(set(target_roots))
    }


def selected_cases(case_ids: list[str] | None, limit: int | None) -> tuple[FieldPrompt, ...]:
    cases = FIELD_PROMPTS
    if case_ids:
        wanted = {case_id.upper() for case_id in case_ids}
        cases = tuple(case for case in cases if case.case_id.upper() in wanted)
        missing = sorted(wanted - {case.case_id.upper() for case in cases})
        if missing:
            raise RuntimeError(f"unknown field prompt case id(s): {', '.join(missing)}")
    if limit is not None:
        cases = cases[:limit]
    return cases


def semantic_markers_for_case(case: FieldPrompt) -> tuple[str, ...]:
    return case.semantic_markers


def forbidden_markers_for_case(case: FieldPrompt) -> tuple[str, ...]:
    return case.forbidden_markers


def prompt_refinement_for_case(case: FieldPrompt) -> dict[str, str]:
    return PROMPT_REFINEMENTS.get(case.case_id, {"refined_prompt": "", "prompt_risk": ""})


def evaluate_semantic_quality(case: FieldPrompt, text: str) -> dict[str, Any]:
    semantic_markers = semantic_markers_for_case(case)
    missing_semantic_markers = sorted({marker for marker in semantic_markers if marker not in text})
    forbidden_markers_found = sorted({marker for marker in forbidden_markers_for_case(case) if marker in text})
    return {
        "status": "passed" if not missing_semantic_markers and not forbidden_markers_found else "failed",
        "required_semantic_markers": list(semantic_markers),
        "missing_semantic_markers": missing_semantic_markers,
        "forbidden_markers_found": forbidden_markers_found,
    }


def evaluate_text(case: FieldPrompt, text: str) -> dict[str, Any]:
    markers = list(COMMON_FORMAT_A_MARKERS)
    if f"selected_workflow: {case.expected_workflow}" not in markers:
        markers.append(f"selected_workflow: {case.expected_workflow}")
    markers.extend(case.expected_markers)
    if case.expected_skill_id:
        markers.append(case.expected_skill_id)
    if case.expected_artifact_key:
        markers.append(case.expected_artifact_key)
    missing = sorted({marker for marker in markers if marker not in text})
    semantic_quality = evaluate_semantic_quality(case, text)
    status = "passed" if not missing and semantic_quality["status"] == "passed" else "failed"
    difference_parts = []
    if missing:
        difference_parts.append("Response missed baseline chat markers: " + ", ".join(missing))
    if semantic_quality["missing_semantic_markers"]:
        difference_parts.append(
            "Response missed semantic answer concepts: "
            + ", ".join(semantic_quality["missing_semantic_markers"])
        )
    if semantic_quality["forbidden_markers_found"]:
        difference_parts.append(
            "Response included forbidden answer concepts: "
            + ", ".join(semantic_quality["forbidden_markers_found"])
        )
    refinement = prompt_refinement_for_case(case)
    return {
        "status": status,
        "output_contract_status": "passed" if not missing else "failed",
        "missing_markers": missing,
        "semantic_quality_status": semantic_quality["status"],
        "missing_semantic_markers": semantic_quality["missing_semantic_markers"],
        "forbidden_markers_found": semantic_quality["forbidden_markers_found"],
        "required_semantic_markers": semantic_quality["required_semantic_markers"],
        "run_id": run_id_from_text(text),
        "expected_skill_id": case.expected_skill_id,
        "expected_artifact_key": case.expected_artifact_key,
        "text_sha256": hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest(),
        "text_sample": text[:1600],
        "initial_difference": "No marker-level or semantic difference from the baseline target." if not difference_parts else (
            " ".join(difference_parts)
        ),
        "suggested_prompt_if_missed": "" if status == "passed" else (refinement["refined_prompt"] or case.miss_suggestion),
        "refined_prompt": refinement["refined_prompt"],
        "prompt_risk": refinement["prompt_risk"],
    }


def run_anythingllm_case(args: argparse.Namespace, case: FieldPrompt, api_key: str) -> dict[str, Any]:
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload={
            "message": case.prompt,
            "mode": "chat",
            "sessionId": f"founder-field-{case.case_id.lower()}-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=args.timeout_seconds,
    )
    result: dict[str, Any] = {
        "case_id": case.case_id,
        "target_root": case.target_root,
        "prompt": case.prompt,
        "baseline_target": case.baseline_target,
        "expected_workflow": case.expected_workflow,
        "expected_skill_id": case.expected_skill_id,
        "expected_artifact_key": case.expected_artifact_key,
        "http_status": status,
    }
    if status != 200:
        result.update(
            {
                "status": "failed",
                "initial_difference": f"AnythingLLM returned HTTP {status}.",
                "suggested_prompt_if_missed": case.miss_suggestion,
                "body": body,
            }
        )
        return result
    text = text_response(body)
    result.update(evaluate_text(case, text))
    return result


def anythingllm_preflight(args: argparse.Namespace, api_key: str) -> dict[str, Any]:
    ping_status, ping_body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/ping",
        timeout_seconds=min(30, args.timeout_seconds),
    )
    workspace_status, workspace_body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspaces",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=min(30, args.timeout_seconds),
    )
    workspaces = workspace_body.get("workspaces") if isinstance(workspace_body, dict) else []
    slugs = [item.get("slug") for item in workspaces if isinstance(item, dict)]
    return {
        "status": "passed" if ping_status == 200 and workspace_status == 200 and args.workspace in slugs else "failed",
        "ping_status": ping_status,
        "workspace_status": workspace_status,
        "workspace": args.workspace,
        "workspace_found": args.workspace in slugs,
        "ping": ping_body,
    }


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"founder-field-prompts-{utc_timestamp()}.json"


def markdown_path_for(report_path: Path) -> Path:
    return report_path.with_suffix(".md")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Founder Field Prompt Evaluation",
        "",
        f"- Status: {report['status']}",
        f"- Created at: {report['created_at']}",
        f"- AnythingLLM workspace: {report['workspace']}",
        f"- Prompt count: {len(report['cases'])}",
        f"- Passed: {report['summary']['passed']}",
        f"- Failed: {report['summary']['failed']}",
        "",
        "## Results",
        "",
        "| Case | Status | Output contract | Semantic quality | Expected workflow | Run ID | Initial difference | Miss suggestion | Refined prompt |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in report["cases"]:
        difference = str(item.get("initial_difference", "")).replace("\n", " ")
        suggestion = str(item.get("suggested_prompt_if_missed", "")).replace("\n", " ")
        refined_prompt = str(item.get("refined_prompt", "")).replace("\n", " ")
        lines.append(
            "| {case_id} | {status} | {output_contract} | {semantic_quality} | {workflow} | {run_id} | {difference} | {suggestion} | {refined_prompt} |".format(
                case_id=item["case_id"],
                status=item["status"],
                output_contract=item.get("output_contract_status", ""),
                semantic_quality=item.get("semantic_quality_status", ""),
                workflow=item["expected_workflow"],
                run_id=item.get("run_id", ""),
                difference=difference[:500],
                suggestion=suggestion[:300],
                refined_prompt=refined_prompt[:300],
            )
        )
    lines.extend(
        [
            "",
            "## Prompt Baselines",
            "",
        ]
    )
    for item in report["cases"]:
        lines.extend(
            [
                f"### {item['case_id']}",
                "",
                f"Prompt: {item['prompt']}",
                "",
                f"Baseline target: {item['baseline_target']}",
                "",
                f"Expected workflow: `{item['expected_workflow']}`",
                "",
                f"Expected skill: `{item.get('expected_skill_id') or 'not asserted'}`",
                "",
                f"Expected artifact: `{item.get('expected_artifact_key') or 'not asserted'}`",
                "",
                f"Output contract: {item.get('output_contract_status', '')}",
                "",
                f"Semantic quality: {item.get('semantic_quality_status', '')}",
                "",
                f"Missing semantic markers: {item.get('missing_semantic_markers', [])}",
                "",
                f"Forbidden markers found: {item.get('forbidden_markers_found', [])}",
                "",
                f"Initial difference: {item.get('initial_difference', '')}",
                "",
                f"Suggested prompt if missed: {item.get('suggested_prompt_if_missed') or 'None'}",
                "",
                f"Refined prompt: {item.get('refined_prompt') or 'None'}",
                "",
                f"Prompt risk: {item.get('prompt_risk') or 'None'}",
                "",
                f"Run ID: `{item.get('run_id', 'unknown')}`",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--markdown-output-path", default=None)
    parser.add_argument("--list-prompts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases = selected_cases(args.case_ids, args.limit)
    if args.list_prompts:
        print(json.dumps([case.__dict__ for case in cases], ensure_ascii=True, indent=2, sort_keys=True))
        return 0
    config_root = Path(args.config_root).resolve()
    report_path = Path(args.output_path) if args.output_path else default_report_path(config_root)
    markdown_path = Path(args.markdown_output_path) if args.markdown_output_path else markdown_path_for(report_path)
    api_key = os.environ.get(args.api_key_env)
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "founder_field_prompt_evaluation",
        "status": "failed",
        "created_at": utc_timestamp(),
        "anythingllm_api_base_url": args.anythingllm_api_base_url,
        "workspace": args.workspace,
        "cases": [],
        "summary": {"passed": 0, "failed": 0},
        "anythingllm_preflight": {},
        "fixture_state_before": {},
        "fixture_state_after": {},
        "errors": [],
    }
    try:
        if not api_key:
            raise RuntimeError(f"{args.api_key_env} is required")
        target_roots = tuple(case.target_root for case in cases)
        report["fixture_state_before"] = fixture_state(target_roots)
        report["anythingllm_preflight"] = anythingllm_preflight(args, api_key)
        if report["anythingllm_preflight"].get("status") != "passed":
            raise RuntimeError("AnythingLLM preflight failed")
        for case in cases:
            item = run_anythingllm_case(args, case, api_key)
            report["cases"].append(item)
            print(
                "FIELD PROMPT {case_id} {status} run_id={run_id}".format(
                    case_id=item["case_id"],
                    status=item["status"].upper(),
                    run_id=item.get("run_id", "unknown"),
                )
            )
        report["fixture_state_after"] = fixture_state(target_roots)
        if report["fixture_state_after"] != report["fixture_state_before"]:
            raise RuntimeError("field prompt suite changed protected fixture state")
        passed = sum(1 for item in report["cases"] if item.get("status") == "passed")
        failed = len(report["cases"]) - passed
        report["summary"] = {"passed": passed, "failed": failed}
        report["status"] = "passed" if failed == 0 else "failed"
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"{type(exc).__name__}: {exc}")
    write_json(report_path, report)
    write_markdown(markdown_path, report)
    print(f"FOUNDER FIELD REPORT {report_path.resolve()}")
    print(f"FOUNDER FIELD MARKDOWN {markdown_path.resolve()}")
    print("FOUNDER FIELD SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("FOUNDER FIELD FAILURES " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("FOUNDER FIELD PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
