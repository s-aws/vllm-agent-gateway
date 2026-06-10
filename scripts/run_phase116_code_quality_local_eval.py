#!/usr/bin/env python3
"""Collect Phase 116 code-quality local-model responses for blind-baseline comparison."""

from __future__ import annotations

import argparse
import json
import os
import re
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
    text_response,
    validate_no_target_mutation,
    watched_files_for_root,
    watched_hashes,
    write_json,
)


DEFAULT_CASES_PATH = REPO_ROOT / "runtime" / "phase116_code_quality_prompt_cases.json"
DEFAULT_BASELINES_PATH = REPO_ROOT / "runtime" / "phase116_code_quality_blind_baselines.json"
DEFAULT_OUTPUT_PATH = "runtime-state/phase116/code-quality-local-eval.json"
EVIDENCE_REF_RE = re.compile(r"(?P<path>[A-Za-z0-9_./-]+\.py):(?P<line>\d+)")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object at {path}")
    return value


def case_prompt(case: dict[str, Any]) -> str:
    prompt = case.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise RuntimeError(f"case {case.get('case_id')!r} did not contain a prompt")
    return prompt


def gateway_payload(prompt: str) -> dict[str, Any]:
    return {
        "model": "agentic-workflow-router",
        "messages": [{"role": "user", "content": prompt}],
    }


def anythingllm_payload(case_id: str, prompt: str) -> dict[str, Any]:
    return {
        "message": prompt,
        "mode": "chat",
        "sessionId": f"phase116-code-quality-{case_id.lower()}-{uuid.uuid4().hex}",
    }


def normalize_ref(value: str) -> str:
    match = EVIDENCE_REF_RE.search(value)
    if not match:
        return value.strip()
    return f"{match.group('path').lstrip('./')}:{match.group('line')}"


def evidence_refs_in_text(text: str) -> set[str]:
    refs: set[str] = set()
    for match in EVIDENCE_REF_RE.finditer(text):
        refs.add(f"{match.group('path').lstrip('./')}:{match.group('line')}")
    return refs


def route_summary(body: dict[str, Any], text: str) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    compact = body.get("agentic_controller_response")
    if isinstance(compact, dict):
        compact_summary = compact.get("summary")
        if isinstance(compact_summary, dict):
            for key in ("selected_workflow", "route_status", "next_action", "output_format"):
                value = compact_summary.get(key)
                if value is not None:
                    summary[key] = value
    workflow_match = re.search(r"- Selected workflow:\s*([A-Za-z0-9_.-]+)", text)
    if workflow_match and not isinstance(summary.get("selected_workflow"), str):
        summary["selected_workflow"] = workflow_match.group(1)
    run_match = re.search(r"run_id:\s*([A-Za-z0-9_.:-]+)", text)
    if run_match:
        summary["run_id"] = run_match.group(1)
    return summary


def baseline_lookup(baselines_catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["case_id"]: item
        for item in baselines_catalog.get("baselines", [])
        if isinstance(item, dict) and isinstance(item.get("case_id"), str)
    }


def response_diagnostics(text: str, baseline: dict[str, Any] | None) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "text_length": len(text),
        "line_count": len(text.splitlines()),
        "contains_read_only_marker": "read-only" in text.lower() or "read only" in text.lower(),
        "contains_source_mutation_false": "source mutation: false" in text.lower(),
        "contains_findings_label": "finding" in text.lower(),
    }
    if baseline:
        expected_refs = [normalize_ref(ref) for ref in baseline.get("evidence_expectations", []) if isinstance(ref, str)]
        found_refs = evidence_refs_in_text(text)
        diagnostics["expected_evidence_ref_count"] = len(expected_refs)
        diagnostics["matched_evidence_refs"] = sorted(ref for ref in expected_refs if ref in found_refs)
        diagnostics["matched_evidence_ref_count"] = len(diagnostics["matched_evidence_refs"])
        diagnostics["must_have_fact_count"] = len(
            [item for item in baseline.get("must_have_facts", []) if isinstance(item, str) and item.strip()]
        )
    return diagnostics


def validate_port_health(timeout_seconds: int) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for label, url in PORT_HEALTH_PROBES:
        status, body = json_request(url, timeout_seconds=timeout_seconds, method="GET")
        if status != 200:
            raise RuntimeError(f"{label} health probe returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
        checks.append({"label": label, "url": url, "status": "passed"})
        print(f"PHASE116 PORT PASS label={label} url={url}")
    return checks


def collect_gateway_response(args: argparse.Namespace, case: dict[str, Any], baseline: dict[str, Any] | None) -> dict[str, Any]:
    status, body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload=gateway_payload(case_prompt(case)),
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"gateway returned HTTP {status} for {case.get('case_id')}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    print(f"PHASE116 GATEWAY CAPTURED case={case.get('case_id')} chars={len(text)}")
    return {
        "status": "captured",
        "http_status": status,
        "route_summary": route_summary(body, text),
        "diagnostics": response_diagnostics(text, baseline),
        "text": text,
    }


def collect_anythingllm_response(
    args: argparse.Namespace,
    case: dict[str, Any],
    baseline: dict[str, Any] | None,
    api_key: str,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}"}
    case_id = str(case.get("case_id"))
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload=anythingllm_payload(case_id, case_prompt(case)),
        headers=headers,
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"AnythingLLM returned HTTP {status} for {case_id}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    print(f"PHASE116 ANYTHINGLLM CAPTURED case={case_id} chars={len(text)}")
    return {
        "status": "captured",
        "http_status": status,
        "route_summary": route_summary(body, text),
        "diagnostics": response_diagnostics(text, baseline),
        "text": text,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=DEFAULT_CONFIG_ROOT)
    parser.add_argument("--cases-path", default=str(DEFAULT_CASES_PATH))
    parser.add_argument("--baselines-path", default=str(DEFAULT_BASELINES_PATH))
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--output-path", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--skip-anythingllm", action="store_true")
    parser.add_argument("--skip-gateway", action="store_true")
    parser.add_argument("--skip-port-health", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root).resolve()
    output_path = Path(args.output_path)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    cases_catalog = read_json_object(Path(args.cases_path))
    baselines = baseline_lookup(read_json_object(Path(args.baselines_path)))
    cases = [item for item in cases_catalog.get("cases", []) if isinstance(item, dict)]
    if args.case_ids:
        requested = set(args.case_ids)
        cases = [item for item in cases if item.get("case_id") in requested]
        missing = sorted(requested - {str(item.get("case_id")) for item in cases})
        if missing:
            raise RuntimeError(f"Unknown case ids requested: {missing}")
    if not cases:
        raise RuntimeError("No Phase 116 cases selected")

    target_roots = sorted({str(item["target_root"]) for item in cases if isinstance(item.get("target_root"), str)})
    runtime_before = watched_hashes(config_root, WATCHED_RUNTIME_FILES)
    target_watch_files = {root: watched_files_for_root(Path(root)) for root in target_roots}
    target_before = {root: watched_hashes(Path(root), target_watch_files[root]) for root in target_roots}
    target_git_before = {root: git_status(Path(root)) for root in target_roots}

    checks: dict[str, Any] = {
        "ports": [] if args.skip_port_health else validate_port_health(args.timeout_seconds),
        "cases": [],
    }
    api_key = os.environ.get(args.api_key_env)
    if not args.skip_anythingllm and not api_key:
        raise RuntimeError(f"{args.api_key_env} is required unless --skip-anythingllm is set")

    for case in cases:
        case_id = str(case.get("case_id"))
        target_root = str(case.get("target_root"))
        baseline = baselines.get(case_id)
        case_report: dict[str, Any] = {
            "case_id": case_id,
            "case_type": case.get("case_type"),
            "holdout": case.get("holdout") is True,
            "target_root": target_root,
            "prompt": case_prompt(case),
            "responses": {},
        }
        if not args.skip_gateway:
            case_report["responses"]["gateway"] = collect_gateway_response(args, case, baseline)
            validate_no_target_mutation(
                Path(target_root),
                target_watch_files[target_root],
                target_before[target_root],
                target_git_before[target_root],
                f"Phase 116 gateway {case_id}",
            )
        if not args.skip_anythingllm:
            case_report["responses"]["anythingllm"] = collect_anythingllm_response(args, case, baseline, str(api_key))
            validate_no_target_mutation(
                Path(target_root),
                target_watch_files[target_root],
                target_before[target_root],
                target_git_before[target_root],
                f"Phase 116 AnythingLLM {case_id}",
            )
        checks["cases"].append(case_report)

    runtime_changed = changed_hashes(runtime_before, watched_hashes(config_root, WATCHED_RUNTIME_FILES))
    if runtime_changed:
        raise RuntimeError(f"canonical runtime metadata mutated during Phase 116 local eval: {runtime_changed}")

    report = {
        "kind": "phase116_code_quality_local_eval",
        "schema_version": 1,
        "status": "captured",
        "created_at": utc_now(),
        "priority_backlog_id": "P0-BB-001",
        "config_root": str(config_root),
        "source_prompt_cases": str(Path(args.cases_path)),
        "source_blind_baselines": str(Path(args.baselines_path)),
        "workflow_router_gateway_base_url": args.workflow_router_gateway_base_url,
        "anythingllm_api_base_url": args.anythingllm_api_base_url,
        "anythingllm_applicable": not args.skip_anythingllm,
        "case_count": len(cases),
        "target_roots": target_roots,
        "runtime_changed_files": runtime_changed,
        "target_changed_files": {},
        "checks": checks,
    }
    write_json(output_path, report)
    print(f"PHASE116 CODE QUALITY LOCAL EVAL CAPTURED report={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
