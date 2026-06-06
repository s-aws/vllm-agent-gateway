#!/usr/bin/env python3
"""Validate Phase 63 Batch D skills through gateway, AnythingLLM, and promotion."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_ROOT = "/mnt/c/agentic_agents"
DEFAULT_CONTROLLER_BASE_URL = "http://127.0.0.1:8400"
DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_CONTROLLER_ARTIFACT_ROOT = "/mnt/c/private_agentic_agents/runtime-state/controller-artifacts"
DEFAULT_TARGET_ROOTS = [
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
]
PHASE63_SKILL_IDS = [
    "handler-branch-tracer",
    "table-schema-isolator",
    "runtime-entrypoint-disambiguator",
    "change-boundary-summarizer",
]
PHASE63_EVAL_CASE_IDS = [
    "phase61_handler_branch_trace",
    "phase61_table_schema_only",
    "phase61_runtime_entrypoint_disambiguation",
    "phase61_change_boundary_summary",
]
WATCHED_REGISTRY_FILES = ["runtime/skills.json", "runtime/skill_evals.json"]
WATCHED_TARGET_FILES = [
    "agent.md",
    "configuration.py",
    "dashboard_server.py",
    "core/stealth_order_manager.py",
    "database/order.py",
    "docs/agents/INVARIANTS.md",
    "tests/test_dashboard_handler.py",
    "tests/unit/test_order_id_and_followup_rules.py",
]
PORT_HEALTH_PROBES = [
    ("localhost-model", "http://127.0.0.1:8000/v1/models"),
    ("llm-gateway", "http://127.0.0.1:8300/v1/models"),
    ("controller", "http://127.0.0.1:8400/health"),
    ("workflow-router-gateway", "http://127.0.0.1:8500/v1/models"),
    ("documenter-role", "http://127.0.0.1:8101/v1/models"),
    ("architect-role", "http://127.0.0.1:8102/v1/models"),
    ("agent-role-8201", "http://127.0.0.1:8201/v1/models"),
    ("agent-role-8202", "http://127.0.0.1:8202/v1/models"),
    ("agent-role-8203", "http://127.0.0.1:8203/v1/models"),
    ("agent-role-8204", "http://127.0.0.1:8204/v1/models"),
    ("agent-role-8205", "http://127.0.0.1:8205/v1/models"),
]


@dataclass(frozen=True)
class Phase63Case:
    case_id: str
    skill_id: str
    expected_workflow: str
    artifact_key: str
    text_markers: tuple[str, ...]
    prompt_template: str

    def prompt(self, target_root: str) -> str:
        return self.prompt_template.format(target_root=target_root)


PHASE63_CASES: tuple[Phase63Case, ...] = (
    Phase63Case(
        case_id="phase61_handler_branch_trace",
        skill_id="handler-branch-tracer",
        expected_workflow="code_investigation.plan",
        artifact_key="downstream_request_flow_map",
        text_markers=(
            "Answer:",
            "Target flow:",
            "request_stealth_orders",
            "Flow steps:",
            "Participating files:",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, follow handler branch trace for request_stealth_orders as a request flow "
            "through the downstream snapshot function. Read only. Return flow steps, participating files, "
            "evidence refs, related tests, risks, gaps, and verification."
        ),
    ),
    Phase63Case(
        case_id="phase61_table_schema_only",
        skill_id="table-schema-isolator",
        expected_workflow="code_investigation.plan",
        artifact_key="downstream_data_model_lookup",
        text_markers=(
            "Answer:",
            "Target model/schema:",
            "stealth_orders",
            "Fields:",
            "Model files:",
            "Source refs:",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, find the stealth_orders table schema only. Read only. "
            "Return schema field names, model files, and source refs. Exclude runtime fields."
        ),
    ),
    Phase63Case(
        case_id="phase61_runtime_entrypoint_disambiguation",
        skill_id="runtime-entrypoint-disambiguator",
        expected_workflow="code_investigation.plan",
        artifact_key="downstream_cli_entrypoint_lookup",
        text_markers=(
            "Answer:",
            "Target entrypoint:",
            "Entrypoints:",
            "Source refs:",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, locate the runtime entrypoint for the trading engine entrypoint, not dashboard server. "
            "Read only. Return command, source refs, and exclusions."
        ),
    ),
    Phase63Case(
        case_id="phase61_change_boundary_summary",
        skill_id="change-boundary-summarizer",
        expected_workflow="code_investigation.plan",
        artifact_key="downstream_change_surface_summary",
        text_markers=(
            "Answer:",
            "Change surface files:",
            "Risk level:",
            "Implementation status: not_ready_without_approval",
            "Verification:",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, identify files to touch and files not to touch for the minimal safe change surface "
            "and change boundary for placed_order_id stealth lookup behavior. Read only and stop before implementation. "
            "Return risks, gaps, and verification commands."
        ),
    ),
)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_output_path(config_root: Path) -> Path:
    return config_root / "runtime-state" / "skill-batches" / f"phase63-batch-d-live-{utc_timestamp()}.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def json_request(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: int,
    method: str = "POST",
) -> tuple[int, dict[str, Any]]:
    request_headers = dict(headers or {})
    data = None
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8")
            return response.status, json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(body_text)
        except json.JSONDecodeError:
            body = {"error": {"message": body_text, "code": "invalid_json_error_body"}}
        return exc.code, body


def digest_file(path: Path) -> str:
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
            hashes[relative] = digest_file(path)
    if not hashes:
        raise RuntimeError(f"{root} did not contain watched files: {', '.join(relatives)}")
    return hashes


def skill_body_hashes(root: Path) -> dict[str, str]:
    skill_root = root / ".qwen" / "skills"
    return {path.relative_to(root).as_posix(): digest_file(path) for path in sorted(skill_root.glob("*/SKILL.md"))}


def git_status(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    result = subprocess.run(["git", "-C", str(root), "status", "--short"], check=True, capture_output=True, text=True)
    return result.stdout


def validate_unchanged(root: Path, before_hashes: dict[str, str], before_status: str | None, label: str) -> None:
    if watched_hashes(root, list(before_hashes)) != before_hashes:
        raise RuntimeError(f"{label} changed watched files under {root}")
    if before_status is not None and git_status(root) != before_status:
        raise RuntimeError(f"{label} changed git status under {root}")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return value


def text_response(body: dict[str, Any]) -> str:
    for key in ("textResponse", "response", "message"):
        value = body.get(key)
        if isinstance(value, str):
            return value
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first.get("message"), dict) else {}
        content = message.get("content")
        if isinstance(content, str):
            return content
    return json.dumps(body, ensure_ascii=True, sort_keys=True)


def require_markers(text: str, markers: tuple[str, ...], *, label: str) -> None:
    common = (
        "workflow_router.plan completed",
        "run_id: workflow-router-",
        "Result:",
        "- Selected workflow:",
        "- Selected skills:",
        "- Verification:",
        "Artifacts:",
    )
    missing = [marker for marker in (*common, *markers) if marker not in text]
    if missing:
        raise RuntimeError(f"{label} missing marker(s): {json.dumps(missing, ensure_ascii=True)}")


def run_id_from_text(text: str) -> str:
    match = re.search(r"workflow-router-\d{8}T\d{12,}Z", text)
    if not match:
        raise RuntimeError("Could not find workflow-router run_id in response text")
    return match.group(0)


def route_decision_path_from_gateway(body: dict[str, Any]) -> Path:
    compact = body.get("agentic_controller_response") if isinstance(body.get("agentic_controller_response"), dict) else {}
    artifacts = compact.get("artifacts") if isinstance(compact.get("artifacts"), dict) else {}
    path = artifacts.get("route_decision")
    if not isinstance(path, str) or not path:
        raise RuntimeError("Gateway response did not expose route_decision artifact")
    return Path(path)


def route_decision_path_from_anythingllm(text: str, artifact_root: Path) -> Path:
    run_id = run_id_from_text(text)
    candidates = list((artifact_root / "workflow-router").glob(f"{run_id}/route-decision.json"))
    if not candidates:
        candidates = list(artifact_root.glob(f"workflow-router/**/{run_id}/route-decision.json"))
    if not candidates:
        raise RuntimeError(f"Could not locate route decision artifact for AnythingLLM run {run_id}")
    return candidates[0]


def run_state_path_from_route_decision(route_decision_path: Path) -> Path:
    run_state_path = route_decision_path.parent / "run-state.json"
    if not run_state_path.is_file():
        raise RuntimeError(f"Missing workflow-router run-state artifact: {run_state_path}")
    return run_state_path


def validate_route_and_run_state(
    route_decision_path: Path,
    *,
    case: Phase63Case,
    expected_target_root: str,
    label: str,
) -> dict[str, Any]:
    decision = read_json(route_decision_path)
    if decision.get("selected_workflow") != case.expected_workflow:
        raise RuntimeError(f"{label} selected {decision.get('selected_workflow')}, expected {case.expected_workflow}")
    selected = decision.get("selected_skills")
    if not isinstance(selected, list) or case.skill_id not in selected:
        raise RuntimeError(f"{label} did not select {case.skill_id}; selected={selected}")
    if decision.get("target_root") != expected_target_root:
        raise RuntimeError(f"{label} target root mismatch: {decision.get('target_root')} != {expected_target_root}")
    run_state = read_json(run_state_path_from_route_decision(route_decision_path))
    summary = run_state.get("summary") if isinstance(run_state.get("summary"), dict) else {}
    if summary.get("downstream_workflow") != case.expected_workflow or summary.get("downstream_status") != "completed":
        raise RuntimeError(f"{label} downstream summary mismatch: {json.dumps(summary, ensure_ascii=True)}")
    if summary.get("source_changed") is not False:
        raise RuntimeError(f"{label} reported source_changed={summary.get('source_changed')}")
    artifacts = run_state.get("artifacts") if isinstance(run_state.get("artifacts"), dict) else {}
    if case.artifact_key not in artifacts:
        raise RuntimeError(f"{label} missing artifact {case.artifact_key}; artifacts={sorted(artifacts)}")
    return {
        "route_decision": str(route_decision_path),
        "run_state": str(run_state_path_from_route_decision(route_decision_path)),
        "selected_skills": selected,
        "artifact_path": artifacts[case.artifact_key],
        "downstream_run_id": summary.get("downstream_run_id"),
    }


def run_repo_command(config_root: Path, command: list[str], *, timeout_seconds: int) -> None:
    result = subprocess.run(
        command,
        cwd=config_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Command failed: "
            + " ".join(command)
            + "\nSTDOUT:\n"
            + result.stdout[-4000:]
            + "\nSTDERR:\n"
            + result.stderr[-4000:]
        )


def validate_port_health(args: argparse.Namespace) -> None:
    for label, url in PORT_HEALTH_PROBES:
        status, body = json_request(url, timeout_seconds=args.timeout_seconds, method="GET")
        if status != 200:
            raise RuntimeError(f"{label} health probe returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
        print(f"PHASE63 PORT PASS label={label} url={url}")


def phase63_skill_statuses(config_root: Path) -> dict[str, str]:
    skills = read_json(config_root / "runtime" / "skills.json")
    return {
        item.get("id"): item.get("eval_status")
        for item in skills.get("skills", [])
        if isinstance(item, dict) and item.get("id") in PHASE63_SKILL_IDS
    }


def validate_phase63_registered(config_root: Path) -> str:
    skills = read_json(config_root / "runtime" / "skills.json")
    evals = read_json(config_root / "runtime" / "skill_evals.json")
    statuses = phase63_skill_statuses(config_root)
    if set(statuses) != set(PHASE63_SKILL_IDS):
        raise RuntimeError(f"Phase 63 skill ids are missing: {statuses}")
    status_values = set(statuses.values())
    if status_values == {"draft"}:
        lifecycle_state = "draft"
    elif status_values == {"validated"}:
        lifecycle_state = "validated"
    else:
        raise RuntimeError(f"Phase 63 skills are in a partial lifecycle state: {statuses}")
    eval_case_ids = {
        item.get("id")
        for item in evals.get("cases", [])
        if isinstance(item, dict) and item.get("id") in PHASE63_EVAL_CASE_IDS
    }
    if eval_case_ids != set(PHASE63_EVAL_CASE_IDS):
        raise RuntimeError(f"Phase 63 eval cases are missing: {eval_case_ids}")
    skill_by_id = {
        item.get("id"): item
        for item in skills.get("skills", [])
        if isinstance(item, dict) and item.get("id") in PHASE63_SKILL_IDS
    }
    for skill_id in PHASE63_SKILL_IDS:
        if not (config_root / ".qwen" / "skills" / skill_id / "SKILL.md").is_file():
            raise RuntimeError(f"Missing Phase 63 skill body: {skill_id}")
        evals_block = skill_by_id[skill_id].get("evals") if isinstance(skill_by_id[skill_id], dict) else {}
        if lifecycle_state == "validated" and not all(evals_block.get(key) == "passed" for key in ("localhost_8000", "gateway_8300", "anythingllm")):
            raise RuntimeError(f"Validated skill is missing passed eval fields: {skill_id}")
    print(f"PHASE63 REGISTRY STATE PASS state={lifecycle_state}")
    return lifecycle_state


def validate_static_gates(args: argparse.Namespace, config_root: Path) -> None:
    python = sys.executable
    run_repo_command(config_root, [python, "scripts/validate_skill_batch_d_proposal.py"], timeout_seconds=args.timeout_seconds)
    run_repo_command(
        config_root,
        [python, "scripts/validate_skill_evals.py", "--output-path", "runtime-state/skill-evals/phase63-skill-evals-before-live.json"],
        timeout_seconds=args.timeout_seconds,
    )
    run_repo_command(
        config_root,
        [python, "scripts/validate_skill_scale.py", "--output-path", "runtime-state/skill-scale/phase63-skill-scale-before-live.json"],
        timeout_seconds=args.timeout_seconds,
    )
    run_repo_command(config_root, [python, "scripts/check_docs_index.py"], timeout_seconds=args.timeout_seconds)
    print("PHASE63 STATIC GATES PASS")


def validate_gateway_case(args: argparse.Namespace, target_root: str, case: Phase63Case) -> dict[str, Any]:
    target = Path(target_root)
    before_target = watched_hashes(target, WATCHED_TARGET_FILES)
    before_status = git_status(target)
    status, body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": case.prompt(target_root)}],
        },
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"Gateway {case.skill_id} returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    require_markers(text, case.text_markers, label=f"gateway {case.skill_id} {target_root}")
    proof = validate_route_and_run_state(
        route_decision_path_from_gateway(body),
        case=case,
        expected_target_root=target_root,
        label=f"gateway {case.skill_id} {target_root}",
    )
    validate_unchanged(target, before_target, before_status, f"gateway {case.skill_id}")
    run_id = run_id_from_text(text)
    print(f"PHASE63 GATEWAY CASE PASS target={target_root} skill={case.skill_id} run_id={run_id}")
    return {"client": "gateway", "target_root": target_root, "skill_id": case.skill_id, "run_id": run_id, **proof}


def validate_anythingllm_case(args: argparse.Namespace, target_root: str, case: Phase63Case, api_key: str) -> dict[str, Any]:
    target = Path(target_root)
    before_target = watched_hashes(target, WATCHED_TARGET_FILES)
    before_status = git_status(target)
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload={
            "message": case.prompt(target_root),
            "mode": "chat",
            "sessionId": f"phase63-batch-d-{case.skill_id}-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"AnythingLLM {case.skill_id} returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    require_markers(text, case.text_markers, label=f"AnythingLLM {case.skill_id} {target_root}")
    proof = validate_route_and_run_state(
        route_decision_path_from_anythingllm(text, Path(args.controller_artifact_root)),
        case=case,
        expected_target_root=target_root,
        label=f"AnythingLLM {case.skill_id} {target_root}",
    )
    validate_unchanged(target, before_target, before_status, f"AnythingLLM {case.skill_id}")
    run_id = run_id_from_text(text)
    print(f"PHASE63 ANYTHINGLLM CASE PASS target={target_root} skill={case.skill_id} run_id={run_id}")
    return {"client": "anythingllm", "target_root": target_root, "skill_id": case.skill_id, "run_id": run_id, **proof}


def validate_live_cases(args: argparse.Namespace, config_root: Path) -> dict[str, Any]:
    before_registry = watched_hashes(config_root, WATCHED_REGISTRY_FILES)
    before_skills = skill_body_hashes(config_root)
    target_roots = args.target_roots or DEFAULT_TARGET_ROOTS
    gateway_results: list[dict[str, Any]] = []
    anythingllm_results: list[dict[str, Any]] = []
    for target_root in target_roots:
        for case in PHASE63_CASES:
            gateway_results.append(validate_gateway_case(args, target_root, case))
    if not args.skip_anythingllm:
        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            raise RuntimeError(f"{args.api_key_env} is required unless --skip-anythingllm is set")
        for target_root in target_roots:
            for case in PHASE63_CASES:
                anythingllm_results.append(validate_anythingllm_case(args, target_root, case, api_key))
    if watched_hashes(config_root, WATCHED_REGISTRY_FILES) != before_registry:
        raise RuntimeError("Phase 63 live validation changed watched runtime registry files before promotion")
    if skill_body_hashes(config_root) != before_skills:
        raise RuntimeError("Phase 63 live validation changed skill body files")
    print("PHASE63 LIVE CASES PASS")
    return {
        "gateway": gateway_results,
        "anythingllm": anythingllm_results,
        "live_suite_runs": [
            {
                "suite": "phase63_batch_d_live_suite",
                "live_suite": "phase63_batch_d_live_suite",
                "status": "passed",
                "case_ids": PHASE63_EVAL_CASE_IDS,
                "target_roots": target_roots,
                "anythingllm": not args.skip_anythingllm,
                "live_target": "gateway_and_anythingllm" if not args.skip_anythingllm else "gateway",
            }
        ],
    }


def promotion_approval(ref: str) -> dict[str, Any]:
    return {
        "status": "approved_for_skill_promotion",
        "scope": "skill_eval_promotion",
        "eval_status_update": True,
        "approval_refs": [ref],
    }


def promote_after_live(args: argparse.Namespace, report_path: Path, live_results: dict[str, Any]) -> dict[str, Any]:
    proof = {
        "kind": "phase63_batch_d_live_proof",
        "schema_version": 1,
        "proof_artifact": str(report_path),
        "live_suite_runs": live_results["live_suite_runs"],
    }
    status, body = json_request(
        f"{args.controller_base_url.rstrip('/')}/v1/controller/skill-evals/promotions",
        payload={
            "workflow": "skill_eval.promote",
            "schema_version": 1,
            "skill_ids": PHASE63_SKILL_IDS,
            "approval": promotion_approval("phase63-batch-d-live-proof"),
            "proof": proof,
            "metadata": {"roadmap_phase": "63", "source": "validate_phase63_skill_batch_live"},
        },
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"Phase 63 promotion returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    summary = body.get("summary") if isinstance(body.get("summary"), dict) else {}
    if summary.get("promotion_status") != "promoted":
        raise RuntimeError(f"Phase 63 promotion did not complete: {json.dumps(body, ensure_ascii=True)}")
    print(f"PHASE63 PROMOTION PASS run_id={body.get('run_id')}")
    return body


def validate_lifecycle_after_promotion(args: argparse.Namespace) -> dict[str, Any]:
    status, body = json_request(
        f"{args.controller_base_url.rstrip('/')}/v1/controller/skill-lifecycle/audits",
        payload={"workflow": "skill_lifecycle.audit", "schema_version": 1, "skill_ids": PHASE63_SKILL_IDS},
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"Phase 63 lifecycle audit returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    summary = body.get("summary") if isinstance(body.get("summary"), dict) else {}
    if summary.get("lifecycle_status") != "passed":
        raise RuntimeError(f"Phase 63 lifecycle audit did not pass after promotion: {json.dumps(body, ensure_ascii=True)}")
    print(f"PHASE63 LIFECYCLE AUDIT PASS run_id={body.get('run_id')}")
    return body


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=DEFAULT_CONFIG_ROOT)
    parser.add_argument("--controller-base-url", default=DEFAULT_CONTROLLER_BASE_URL)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--controller-artifact-root", default=DEFAULT_CONTROLLER_ARTIFACT_ROOT)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--skip-anythingllm", action="store_true")
    parser.add_argument("--skip-port-health", action="store_true")
    parser.add_argument("--skip-promotion", action="store_true")
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root)
    output_path = Path(args.output_path) if args.output_path else default_output_path(config_root)
    if not args.skip_port_health:
        validate_port_health(args)
    initial_state = validate_phase63_registered(config_root)
    validate_static_gates(args, config_root)
    live_results = validate_live_cases(args, config_root)
    report: dict[str, Any] = {
        "kind": "phase63_batch_d_live_report",
        "schema_version": 1,
        "status": "passed",
        "config_root": str(config_root),
        "skill_ids": PHASE63_SKILL_IDS,
        "eval_case_ids": PHASE63_EVAL_CASE_IDS,
        "target_roots": args.target_roots or DEFAULT_TARGET_ROOTS,
        "initial_lifecycle_state": initial_state,
        "gateway": live_results["gateway"],
        "anythingllm": live_results["anythingllm"],
        "live_suite_runs": live_results["live_suite_runs"],
        "promotion": {"status": "not_requested"},
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)

    if initial_state == "draft" and not args.skip_anythingllm and not args.skip_promotion:
        promotion = promote_after_live(args, output_path.resolve(), live_results)
        lifecycle = validate_lifecycle_after_promotion(args)
        report["promotion"] = {
            "status": "promoted",
            "run_id": promotion.get("run_id"),
            "summary": promotion.get("summary"),
            "artifacts": promotion.get("artifacts"),
            "lifecycle_audit_run_id": lifecycle.get("run_id"),
        }
        report["final_lifecycle_state"] = validate_phase63_registered(config_root)
        write_json(output_path, report)
    elif initial_state == "validated":
        report["promotion"] = {"status": "already_validated"}
        report["final_lifecycle_state"] = "validated"
        write_json(output_path, report)
    else:
        report["promotion"] = {
            "status": "skipped",
            "reason": "promotion requires AnythingLLM live proof and --skip-promotion must be false",
        }
        report["final_lifecycle_state"] = initial_state
        write_json(output_path, report)

    print(
        "PHASE63 LIVE SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "report_path": str(output_path.resolve()),
                "skill_ids": PHASE63_SKILL_IDS,
                "target_roots": args.target_roots or DEFAULT_TARGET_ROOTS,
                "anythingllm": not args.skip_anythingllm,
                "promotion": report["promotion"]["status"],
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
