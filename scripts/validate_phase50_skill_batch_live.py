#!/usr/bin/env python3
"""Validate Phase 50 Batch C skills through gateway and AnythingLLM."""

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
PHASE50_SKILL_IDS = [
    "auth-check-locator",
    "state-mutation-locator",
    "external-integration-locator",
    "error-handling-path-locator",
]
PHASE50_EVAL_CASE_IDS = [
    "phase50_auth_check_lookup",
    "phase50_state_mutation_lookup",
    "phase50_external_integration_lookup",
    "phase50_error_handling_path_lookup",
]
WATCHED_REGISTRY_FILES = ["runtime/skills.json", "runtime/skill_evals.json"]
WATCHED_TARGET_FILES = [
    "core/stealth_order_manager.py",
    "tests/unit/test_order_id_and_followup_rules.py",
    "docs/agents/INVARIANTS.md",
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
PHASE50_CASES = [
    {
        "skill_id": "auth-check-locator",
        "expected_workflow": "code_investigation.plan",
        "prompt": (
            "In {target_root}, find auth checks and permission guards for stealth order actions. "
            "Read only. Return guard files, evidence, and related tests."
        ),
    },
    {
        "skill_id": "state-mutation-locator",
        "expected_workflow": "code_investigation.plan",
        "prompt": (
            "In {target_root}, find state mutation sites for placed_order_id indexing. "
            "Read only. Return mutation sites, evidence files, and related tests."
        ),
    },
    {
        "skill_id": "external-integration-locator",
        "expected_workflow": "code_investigation.plan",
        "prompt": (
            "In {target_root}, find external integration points for Coinbase order placement. "
            "Read only. Return client files, request boundaries, and evidence gaps."
        ),
    },
    {
        "skill_id": "error-handling-path-locator",
        "expected_workflow": "code_investigation.plan",
        "prompt": (
            "In {target_root}, find the error handling path for order placement failures. "
            "Read only. Return exception handlers, fallback logic, and related tests."
        ),
    },
]


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
    missing = [marker for marker in markers if marker not in text]
    if missing:
        raise RuntimeError(f"{label} missing marker(s): {', '.join(missing)}")


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
        print(f"PHASE50 PORT PASS label={label} url={url}")


def validate_batch_c_registered(config_root: Path) -> None:
    skills = read_json(config_root / "runtime" / "skills.json")
    evals = read_json(config_root / "runtime" / "skill_evals.json")
    statuses = {
        item.get("id"): item.get("eval_status")
        for item in skills.get("skills", [])
        if isinstance(item, dict) and item.get("id") in PHASE50_SKILL_IDS
    }
    if statuses != {skill_id: "validated" for skill_id in PHASE50_SKILL_IDS}:
        raise RuntimeError(f"Phase 50 skill statuses are wrong: {statuses}")
    eval_case_ids = {
        item.get("id")
        for item in evals.get("cases", [])
        if isinstance(item, dict) and item.get("id") in PHASE50_EVAL_CASE_IDS
    }
    if eval_case_ids != set(PHASE50_EVAL_CASE_IDS):
        raise RuntimeError(f"Phase 50 eval cases are missing: {eval_case_ids}")
    for skill_id in PHASE50_SKILL_IDS:
        if not (config_root / ".qwen" / "skills" / skill_id / "SKILL.md").is_file():
            raise RuntimeError(f"Missing Phase 50 skill body: {skill_id}")


def validate_static_gates(args: argparse.Namespace, config_root: Path) -> None:
    python = sys.executable
    run_repo_command(
        config_root,
        [python, "scripts/validate_skill_evals.py", "--output-path", "runtime-state/skill-evals/phase50-skill-evals.json"],
        timeout_seconds=args.timeout_seconds,
    )
    run_repo_command(
        config_root,
        [python, "scripts/validate_skill_scale.py", "--output-path", "runtime-state/skill-scale/phase50-skill-scale.json"],
        timeout_seconds=args.timeout_seconds,
    )
    run_repo_command(config_root, [python, "scripts/check_docs_index.py"], timeout_seconds=args.timeout_seconds)
    print("PHASE50 STATIC GATES PASS")


def validate_lifecycle_audit(args: argparse.Namespace) -> None:
    status, body = json_request(
        f"{args.controller_base_url.rstrip('/')}/v1/controller/skill-lifecycle/audits",
        payload={"workflow": "skill_lifecycle.audit", "schema_version": 1},
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"Phase 50 lifecycle audit returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    artifacts = body.get("artifacts") if isinstance(body.get("artifacts"), dict) else {}
    audit_path = artifacts.get("skill_lifecycle_audit")
    if not isinstance(audit_path, str):
        raise RuntimeError("Phase 50 lifecycle audit did not expose skill_lifecycle_audit")
    audit = read_json(Path(audit_path))
    queue = audit.get("action_queue") if isinstance(audit.get("action_queue"), list) else []
    actions = {
        item.get("skill_id"): item.get("action")
        for item in queue
        if isinstance(item, dict) and item.get("skill_id") in PHASE50_SKILL_IDS
    }
    if actions != {skill_id: "no_action" for skill_id in PHASE50_SKILL_IDS}:
        raise RuntimeError(f"Phase 50 lifecycle audit returned wrong actions: {actions}")
    print(f"PHASE50 LIFECYCLE AUDIT PASS run_id={body.get('run_id')}")


def route_decision_path_from_gateway(body: dict[str, Any]) -> Path:
    compact = body.get("agentic_controller_response") if isinstance(body.get("agentic_controller_response"), dict) else {}
    artifacts = compact.get("artifacts") if isinstance(compact.get("artifacts"), dict) else {}
    path = artifacts.get("route_decision")
    if not isinstance(path, str) or not path:
        raise RuntimeError("Gateway response did not expose route_decision artifact")
    return Path(path)


def run_id_from_text(text: str) -> str:
    match = re.search(r"workflow-router-\d{8}T\d{12,}Z", text)
    if not match:
        raise RuntimeError("Could not find workflow-router run_id in response text")
    return match.group(0)


def route_decision_path_from_anythingllm(text: str, artifact_root: Path) -> Path:
    run_id = run_id_from_text(text)
    candidates = list((artifact_root / "workflow-router").glob(f"{run_id}/route-decision.json"))
    if not candidates:
        candidates = list(artifact_root.glob(f"workflow-router/**/{run_id}/route-decision.json"))
    if not candidates:
        raise RuntimeError(f"Could not locate route decision artifact for AnythingLLM run {run_id}")
    return candidates[0]


def validate_route_decision(path: Path, *, skill_id: str, expected_workflow: str, label: str) -> None:
    decision = read_json(path)
    if decision.get("selected_workflow") != expected_workflow:
        raise RuntimeError(f"{label} selected {decision.get('selected_workflow')}, expected {expected_workflow}")
    selected = decision.get("selected_skills")
    if not isinstance(selected, list) or skill_id not in selected:
        raise RuntimeError(f"{label} did not select {skill_id}; selected={selected}")


def validate_gateway_case(args: argparse.Namespace, target_root: str, case: dict[str, Any]) -> None:
    target = Path(target_root)
    before_target = watched_hashes(target, WATCHED_TARGET_FILES)
    before_status = git_status(target)
    status, body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": case["prompt"].format(target_root=target_root)}],
        },
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"Gateway {case['skill_id']} returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    require_markers(text, ("workflow_router.plan completed", "code_investigation.plan"), label=f"gateway {case['skill_id']} {target_root}")
    validate_route_decision(
        route_decision_path_from_gateway(body),
        skill_id=case["skill_id"],
        expected_workflow=case["expected_workflow"],
        label=f"gateway {case['skill_id']} {target_root}",
    )
    validate_unchanged(target, before_target, before_status, f"gateway {case['skill_id']}")
    print(f"PHASE50 GATEWAY CASE PASS target={target_root} skill={case['skill_id']}")


def validate_anythingllm_case(args: argparse.Namespace, target_root: str, case: dict[str, Any], api_key: str) -> None:
    target = Path(target_root)
    before_target = watched_hashes(target, WATCHED_TARGET_FILES)
    before_status = git_status(target)
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload={
            "message": case["prompt"].format(target_root=target_root),
            "mode": "chat",
            "sessionId": f"phase50-batch-c-{case['skill_id']}-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"AnythingLLM {case['skill_id']} returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    require_markers(text, ("workflow_router.plan completed", "code_investigation.plan"), label=f"AnythingLLM {case['skill_id']} {target_root}")
    validate_route_decision(
        route_decision_path_from_anythingllm(text, Path(args.controller_artifact_root)),
        skill_id=case["skill_id"],
        expected_workflow=case["expected_workflow"],
        label=f"AnythingLLM {case['skill_id']} {target_root}",
    )
    validate_unchanged(target, before_target, before_status, f"AnythingLLM {case['skill_id']}")
    print(f"PHASE50 ANYTHINGLLM CASE PASS target={target_root} skill={case['skill_id']}")


def validate_live_cases(args: argparse.Namespace, config_root: Path) -> None:
    before_registry = watched_hashes(config_root, WATCHED_REGISTRY_FILES)
    before_skills = skill_body_hashes(config_root)
    target_roots = args.target_roots or DEFAULT_TARGET_ROOTS
    for target_root in target_roots:
        for case in PHASE50_CASES:
            validate_gateway_case(args, target_root, case)
    if not args.skip_anythingllm:
        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            raise RuntimeError(f"{args.api_key_env} is required unless --skip-anythingllm is set")
        for target_root in target_roots:
            for case in PHASE50_CASES:
                validate_anythingllm_case(args, target_root, case, api_key)
    if watched_hashes(config_root, WATCHED_REGISTRY_FILES) != before_registry:
        raise RuntimeError("Phase 50 live validation changed watched runtime registry files")
    if skill_body_hashes(config_root) != before_skills:
        raise RuntimeError("Phase 50 live validation changed skill body files")
    print("PHASE50 LIVE CASES PASS")


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
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root)
    if not args.skip_port_health:
        validate_port_health(args)
    validate_batch_c_registered(config_root)
    validate_static_gates(args, config_root)
    validate_lifecycle_audit(args)
    validate_live_cases(args, config_root)
    print(
        "PHASE50 LIVE SUMMARY "
        + json.dumps(
            {
                "skill_ids": PHASE50_SKILL_IDS,
                "target_roots": args.target_roots or DEFAULT_TARGET_ROOTS,
                "anythingllm": not args.skip_anythingllm,
                "canonical_registry_mutated_during_validation": False,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
