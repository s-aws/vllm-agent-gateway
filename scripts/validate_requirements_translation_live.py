#!/usr/bin/env python3
"""Validate Phase 114 requirements translation against the live local stack."""

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
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    PORT_HEALTH_PROBES,
    WATCHED_RUNTIME_FILES,
    changed_hashes,
    git_status,
    json_content,
    json_request,
    read_json_artifact,
    run_id_from_text,
    text_response,
    validate_no_target_mutation,
    watched_files_for_root,
    watched_hashes,
    write_json,
)
from vllm_agent_gateway.acceptance.task_decomposition_quality import evaluate_task_decomposition_plan  # noqa: E402


DEFAULT_REPORT_PATH = "runtime-state/task-decomposition/phase114-requirements-live.json"
FORMAT_A_MARKERS = [
    "I completed workflow_router.plan.",
    "workflow_router.plan completed",
    "run_id: workflow-router-",
    "Result:",
    "- Selected workflow: task.decompose",
    "- Next action: none",
    "Task Decomposition:",
    "Requirements Translation:",
    "- Business requirements:",
    "- Technical requirements:",
    "- Explicit assumptions:",
    "- Rejected assumptions:",
    "- Effort estimate:",
    "- Revision triggers:",
    "- Source mutation: False",
    "Artifacts:",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_phase114_port_health(timeout_seconds: int) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for label, url in PORT_HEALTH_PROBES:
        status, body = json_request(url, timeout_seconds=timeout_seconds, method="GET")
        if status != 200:
            raise RuntimeError(f"{label} health probe returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
        checks.append({"label": label, "url": url, "status": "passed"})
        print(f"PHASE114 PORT PASS label={label} url={url}")
    return checks


def requirement_subjects_for_target(target_root: str) -> dict[str, str]:
    root = Path(target_root)
    if (root / "service" / "orders.py").exists():
        return {
            "business_to_technical": "the create-order response should show resolved order status",
            "estimate_revision": (
                "the create-order response should show resolved order status and now also include "
                "a requirement note without changing files yet"
            ),
        }
    return {
        "business_to_technical": (
            "users need the stealth order lookup answer to say whether placed_order_id evidence was found"
        ),
        "estimate_revision": (
            "users need the stealth order lookup answer to say whether placed_order_id evidence was found "
            "and now also include a requirement note without changing files yet"
        ),
    }


def requirements_prompt(target_root: str, *, case_type: str, json_output: bool = False) -> str:
    subjects = requirement_subjects_for_target(target_root)
    revision_phrase = " and revise estimate because scope changed" if case_type == "estimate_revision" else ""
    suffix = " Return JSON." if json_output else " Return the answer in the default format."
    return (
        f"In {target_root}, translate this business requirement into technical requirements{revision_phrase} "
        f"and estimate effort: {subjects[case_type]}.{suffix}"
    )


def direct_payload(target_root: str, *, case_type: str) -> dict[str, Any]:
    return {
        "workflow": "task.decompose",
        "schema_version": 1,
        "target_root": target_root,
        "user_request": requirements_prompt(target_root, case_type=case_type),
    }


def gateway_payload(target_root: str, *, case_type: str, json_output: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": "agentic-workflow-router",
        "messages": [{"role": "user", "content": requirements_prompt(target_root, case_type=case_type, json_output=json_output)}],
    }
    if json_output:
        payload["response_format"] = {"type": "json_object"}
    return payload


def anythingllm_payload(target_root: str, *, case_type: str, json_output: bool = False) -> dict[str, Any]:
    return {
        "message": requirements_prompt(target_root, case_type=case_type, json_output=json_output),
        "mode": "chat",
        "sessionId": f"requirements-translation-{uuid.uuid4().hex}",
    }


def require_requirements_contract(
    plan: dict[str, Any],
    target_root: str,
    label: str,
    *,
    revised: bool,
    full_artifact: bool = True,
) -> None:
    if plan.get("prompt_family") != "requirements_translation":
        raise RuntimeError(f"{label} prompt_family mismatch for {target_root}: {plan.get('prompt_family')!r}")
    if plan.get("target_repository_changed") is not False or plan.get("runtime_registry_changed") is not False:
        raise RuntimeError(f"{label} reported mutation for {target_root}: {json.dumps(plan, ensure_ascii=True)[:1000]}")
    tenet_contract = plan.get("tenet_contract")
    if not isinstance(tenet_contract, dict) or tenet_contract.get("phase") != 114 or tenet_contract.get("tenet_ids") != ["T04", "T05"]:
        raise RuntimeError(f"{label} missing Phase 114 tenet contract for {target_root}")
    if full_artifact:
        quality_report = evaluate_task_decomposition_plan(plan)
        if quality_report.get("status") != "passed":
            raise RuntimeError(f"{label} quality contract failed for {target_root}: {json.dumps(quality_report, ensure_ascii=True)}")
    contract = plan.get("requirements_translation")
    if not isinstance(contract, dict):
        raise RuntimeError(f"{label} missing requirements_translation contract for {target_root}")
    business = contract.get("source_business_requirements")
    technical = contract.get("technical_requirements")
    assumptions = contract.get("explicit_assumptions")
    rejected = contract.get("rejected_assumptions")
    estimate = contract.get("effort_estimate")
    revision = contract.get("estimate_revision")
    if not isinstance(business, list) or not business:
        raise RuntimeError(f"{label} missing business requirements for {target_root}")
    if not isinstance(technical, list) or len(technical) < 2:
        raise RuntimeError(f"{label} missing technical requirements for {target_root}")
    if any(not isinstance(item, dict) or item.get("derived_from") != ["BR1"] for item in technical):
        raise RuntimeError(f"{label} technical requirements are not traced to BR1 for {target_root}")
    if not isinstance(assumptions, list) or len(assumptions) < 2:
        raise RuntimeError(f"{label} missing explicit assumptions for {target_root}")
    if not isinstance(rejected, list) or len(rejected) < 2:
        raise RuntimeError(f"{label} missing rejected assumptions for {target_root}")
    if not isinstance(estimate, dict):
        raise RuntimeError(f"{label} missing effort estimate for {target_root}")
    if estimate.get("estimate_band") not in {"small", "medium"} or estimate.get("confidence") not in {"low", "medium"}:
        raise RuntimeError(f"{label} unexpected estimate for {target_root}: {json.dumps(estimate, ensure_ascii=True)}")
    if estimate.get("assumption_ids") != ["A1", "A2"]:
        raise RuntimeError(f"{label} estimate does not trace to assumptions for {target_root}")
    if not estimate.get("scope_drivers") or not estimate.get("revision_triggers"):
        raise RuntimeError(f"{label} estimate missing scope drivers or revision triggers for {target_root}")
    if not isinstance(revision, dict) or revision.get("status") != ("revised" if revised else "not_requested"):
        raise RuntimeError(f"{label} estimate revision mismatch for {target_root}: {json.dumps(revision, ensure_ascii=True)}")
    if revision.get("requires_reapproval_before_implementation_prep") is not revised:
        raise RuntimeError(f"{label} revision reapproval mismatch for {target_root}: {json.dumps(revision, ensure_ascii=True)}")


def require_format_a(body: dict[str, Any], target_root: str, label: str, *, revised: bool) -> str:
    text = text_response(body)
    missing = [marker for marker in FORMAT_A_MARKERS if marker not in text]
    if revised and "- Estimate revision:" not in text:
        missing.append("- Estimate revision:")
    if missing:
        raise RuntimeError(f"{label} missing FormatA markers for {target_root}: {missing}")
    compact = body.get("agentic_controller_response")
    if isinstance(compact, dict):
        summary = compact.get("summary")
        if isinstance(summary, dict) and summary.get("selected_workflow") != "task.decompose":
            raise RuntimeError(f"{label} selected wrong workflow for {target_root}: {summary.get('selected_workflow')!r}")
        artifacts = compact.get("artifacts")
        if isinstance(artifacts, dict) and any("packet" in key for key in artifacts):
            raise RuntimeError(f"{label} created packet artifact for {target_root}: {sorted(artifacts)}")
    return text


def require_json_contract(parsed: dict[str, Any], target_root: str, label: str, *, revised: bool) -> None:
    if parsed.get("output_format") != "json":
        raise RuntimeError(f"{label} output_format mismatch for {target_root}: {parsed.get('output_format')!r}")
    contract = parsed.get("chat_contract")
    if not isinstance(contract, dict) or contract.get("selected_workflow") != "task.decompose":
        raise RuntimeError(f"{label} JSON selected wrong workflow for {target_root}: {json.dumps(contract, ensure_ascii=True)}")
    decomposition_contract = parsed.get("task_decomposition_contract")
    if not isinstance(decomposition_contract, dict):
        raise RuntimeError(f"{label} JSON missing task_decomposition_contract for {target_root}")
    require_requirements_contract(
        decomposition_contract,
        target_root,
        f"{label} inline contract",
        revised=revised,
        full_artifact=False,
    )
    artifacts = parsed.get("artifacts")
    if not isinstance(artifacts, dict) or "downstream_task_decomposition" not in artifacts:
        raise RuntimeError(f"{label} JSON missing downstream_task_decomposition artifact for {target_root}")
    if any("packet" in key for key in artifacts):
        raise RuntimeError(f"{label} JSON created packet artifact for {target_root}: {sorted(artifacts)}")
    require_requirements_contract(
        read_json_artifact(artifacts["downstream_task_decomposition"]),
        target_root,
        f"{label} artifact",
        revised=revised,
    )


def validate_direct(args: argparse.Namespace, target_root: str) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    for case_type in ("business_to_technical", "estimate_revision"):
        status, body = json_request(
            f"{args.controller_base_url.rstrip('/')}/v1/controller/task-decompositions",
            payload=direct_payload(target_root, case_type=case_type),
            timeout_seconds=args.timeout_seconds,
        )
        if status != 200:
            raise RuntimeError(f"direct controller returned HTTP {status} for {target_root}: {json.dumps(body, ensure_ascii=True)}")
        summary = body.get("summary")
        if not isinstance(summary, dict) or summary.get("prompt_family") != "requirements_translation":
            raise RuntimeError(f"direct summary mismatch for {target_root}: {json.dumps(summary, ensure_ascii=True)}")
        artifacts = body.get("artifacts")
        if not isinstance(artifacts, dict) or "task_decomposition" not in artifacts:
            raise RuntimeError(f"direct missing task_decomposition artifact for {target_root}")
        if any("packet" in key for key in artifacts):
            raise RuntimeError(f"direct created packet artifact for {target_root}: {sorted(artifacts)}")
        require_requirements_contract(
            read_json_artifact(artifacts["task_decomposition"]),
            target_root,
            "direct",
            revised=case_type == "estimate_revision",
        )
        runs.append({"case_type": case_type, "run_id": body.get("run_id")})
    print(f"PHASE114 DIRECT PASS target={target_root} runs={len(runs)}")
    return {"target_root": target_root, "runs": runs}


def validate_gateway(args: argparse.Namespace, target_root: str) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    for case_type in ("business_to_technical", "estimate_revision"):
        status, body = json_request(
            f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
            payload=gateway_payload(target_root, case_type=case_type),
            timeout_seconds=args.timeout_seconds,
        )
        if status != 200:
            raise RuntimeError(f"gateway returned HTTP {status} for {target_root}: {json.dumps(body, ensure_ascii=True)}")
        text = require_format_a(body, target_root, f"gateway {case_type}", revised=case_type == "estimate_revision")
        runs.append({"case_type": case_type, "format_a_run_id": run_id_from_text(text)})
    json_status, json_body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload=gateway_payload(target_root, case_type="business_to_technical", json_output=True),
        timeout_seconds=args.timeout_seconds,
    )
    if json_status != 200:
        raise RuntimeError(f"gateway JSON returned HTTP {json_status} for {target_root}: {json.dumps(json_body, ensure_ascii=True)}")
    parsed = json_content(json_body)
    require_json_contract(parsed, target_root, "gateway", revised=False)
    print(f"PHASE114 GATEWAY PASS target={target_root} run_id={parsed.get('run_id')}")
    return {"target_root": target_root, "runs": runs, "json_run_id": parsed.get("run_id")}


def validate_anythingllm(args: argparse.Namespace, target_root: str, api_key: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}"}
    runs: list[dict[str, Any]] = []
    for case_type in ("business_to_technical", "estimate_revision"):
        status, body = json_request(
            f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
            payload=anythingllm_payload(target_root, case_type=case_type),
            headers=headers,
            timeout_seconds=args.timeout_seconds,
        )
        if status != 200:
            raise RuntimeError(f"AnythingLLM returned HTTP {status} for {target_root}: {json.dumps(body, ensure_ascii=True)}")
        text = require_format_a(body, target_root, f"AnythingLLM {case_type}", revised=case_type == "estimate_revision")
        runs.append({"case_type": case_type, "format_a_run_id": run_id_from_text(text)})
    json_status, json_body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload=anythingllm_payload(target_root, case_type="business_to_technical", json_output=True),
        headers=headers,
        timeout_seconds=args.timeout_seconds,
    )
    if json_status != 200:
        raise RuntimeError(f"AnythingLLM JSON returned HTTP {json_status} for {target_root}: {json.dumps(json_body, ensure_ascii=True)}")
    parsed = json_content(json_body)
    require_json_contract(parsed, target_root, "AnythingLLM", revised=False)
    print(f"PHASE114 ANYTHINGLLM PASS target={target_root} run_id={parsed.get('run_id')}")
    return {"target_root": target_root, "runs": runs, "json_run_id": parsed.get("run_id")}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=DEFAULT_CONFIG_ROOT)
    parser.add_argument("--controller-base-url", default=DEFAULT_CONTROLLER_BASE_URL)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--output-path", default=DEFAULT_REPORT_PATH)
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--skip-anythingllm", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root).resolve()
    output_path = Path(args.output_path)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    target_roots = [Path(value).resolve() for value in (args.target_roots or DEFAULT_TARGET_ROOTS)]

    runtime_before = watched_hashes(config_root, WATCHED_RUNTIME_FILES)
    target_watch_files = {str(root): watched_files_for_root(root) for root in target_roots}
    target_before = {str(root): watched_hashes(root, target_watch_files[str(root)]) for root in target_roots}
    target_git_before = {str(root): git_status(root) for root in target_roots}
    checks: dict[str, Any] = {
        "ports": validate_phase114_port_health(args.timeout_seconds),
        "direct": [],
        "gateway": [],
        "anythingllm": [],
    }
    for root in target_roots:
        target = str(root)
        checks["direct"].append(validate_direct(args, target))
        validate_no_target_mutation(root, target_watch_files[target], target_before[target], target_git_before[target], "direct controller")
        checks["gateway"].append(validate_gateway(args, target))
        validate_no_target_mutation(root, target_watch_files[target], target_before[target], target_git_before[target], "gateway")

    if not args.skip_anythingllm:
        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            raise RuntimeError(f"{args.api_key_env} is required unless --skip-anythingllm is set")
        for root in target_roots:
            target = str(root)
            checks["anythingllm"].append(validate_anythingllm(args, target, api_key))
            validate_no_target_mutation(root, target_watch_files[target], target_before[target], target_git_before[target], "AnythingLLM")

    runtime_changed = changed_hashes(runtime_before, watched_hashes(config_root, WATCHED_RUNTIME_FILES))
    if runtime_changed:
        raise RuntimeError(f"canonical runtime metadata mutated during live validation: {runtime_changed}")

    report = {
        "kind": "requirements_translation_live_validation",
        "schema_version": 1,
        "status": "passed",
        "created_at": utc_now(),
        "config_root": str(config_root),
        "target_roots": [str(root) for root in target_roots],
        "controller_base_url": args.controller_base_url,
        "workflow_router_gateway_base_url": args.workflow_router_gateway_base_url,
        "anythingllm_applicable": not args.skip_anythingllm,
        "checks": checks,
        "port_probe_count": len(PORT_HEALTH_PROBES),
        "runtime_changed_files": runtime_changed,
        "target_changed_files": {},
    }
    write_json(output_path, report)
    print(f"PHASE114 REQUIREMENTS TRANSLATION LIVE PASS report={output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
