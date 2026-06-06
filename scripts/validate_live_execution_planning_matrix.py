#!/usr/bin/env python3
"""Run the live execution-planning runtime matrix.

This is the founder/tester validation surface for the current local stack. It
checks the live ports, runs explicit controller-envelope requests through the
gateway and AnythingLLM, and optionally runs mutation regression against
disposable copies of the frozen fixtures.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from validate_gateway_controller_route import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_GATEWAY_BASE_URL,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKSPACE,
    FROZEN_INVARIANT_NEW,
    FROZEN_INVARIANT_OLD,
    INVARIANT_REL,
    json_request,
    run_id_from_text,
    resolve_modes,
    text_response,
    validate_anythingllm_route,
    validate_gateway_route,
)
from vllm_agent_gateway.implementation.workflow import (  # noqa: E402
    ImplementationWorkflowInvocationRequest,
    invoke_implementation_workflow,
)
from vllm_agent_gateway.invocation import WorkflowStatus  # noqa: E402


DEFAULT_MODEL_BASE_URL = "http://127.0.0.1:8000/v1"
DEFAULT_CONTROLLER_BASE_URL = "http://127.0.0.1:8400"
DEFAULT_EXPECTED_ANYTHINGLLM_BASE_URL = "http://127.0.0.1:8300/v1"
ROLE_PORTS = [8101, 8102, 8201, 8202, 8203, 8204, 8205]
CODE_CONTEXT_QUERY = "client_order_id"
CODE_INVESTIGATION_BEHAVIOR = "placed_order_id stealth lookup"


def require_status(status: int, body: dict[str, Any], label: str) -> dict[str, Any]:
    if status != 200:
        raise RuntimeError(f"{label} returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    return body


def require_model_list(body: dict[str, Any], label: str) -> str:
    data = body.get("data")
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"{label} did not return an OpenAI-style model list")
    first = data[0]
    model_id = first.get("id") if isinstance(first, dict) else None
    if not isinstance(model_id, str) or not model_id:
        raise RuntimeError(f"{label} model list did not include a model id")
    return model_id


def find_key(value: Any, target_key: str) -> Any:
    if isinstance(value, dict):
        if target_key in value:
            return value[target_key]
        for child in value.values():
            found = find_key(child, target_key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_key(child, target_key)
            if found is not None:
                return found
    return None


def validate_anythingllm_provider_setting(
    *,
    api_base_url: str,
    api_key: str | None,
    expected_base_url: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    if not api_key:
        return {"checked": False, "reason": "missing_api_key"}
    status, body = json_request(
        f"{api_base_url.rstrip('/')}/api/v1/system",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=timeout_seconds,
    )
    require_status(status, body, "anythingllm system")
    configured = find_key(body, "GenericOpenAiBasePath")
    if not isinstance(configured, str):
        print("ANYTHINGLLM SYSTEM WARN GenericOpenAiBasePath not found in /api/v1/system response")
        return {"checked": False, "reason": "setting_not_found"}
    if configured.rstrip("/") != expected_base_url.rstrip("/"):
        raise RuntimeError(
            "AnythingLLM GenericOpenAiBasePath is "
            f"{configured!r}, expected {expected_base_url!r}. Point AnythingLLM at the gateway, not 8400."
        )
    print(f"ANYTHINGLLM SYSTEM PASS GenericOpenAiBasePath={configured}")
    return {"checked": True, "GenericOpenAiBasePath": configured}


def validate_port_smoke(args: argparse.Namespace, api_key: str | None) -> dict[str, Any]:
    results: dict[str, Any] = {}

    status, body = json_request(f"{args.model_base_url.rstrip('/')}/models", timeout_seconds=args.timeout_seconds)
    model_id = require_model_list(require_status(status, body, "model /models"), "model /models")
    results["model"] = {"url": args.model_base_url, "model_id": model_id}
    print(f"PORT SMOKE PASS model_base={args.model_base_url} model={model_id}")

    gateway_root = args.gateway_base_url.rstrip("/")
    gateway_origin = gateway_root[:-3] if gateway_root.endswith("/v1") else gateway_root
    status, body = json_request(f"{gateway_origin}/__gateway/health", timeout_seconds=args.timeout_seconds)
    gateway_health = require_status(status, body, "gateway health")
    if gateway_health.get("controller_routing") != "explicit_envelope":
        raise RuntimeError(f"gateway controller_routing is not explicit_envelope: {gateway_health!r}")
    results["gateway_health"] = gateway_health
    print(
        "PORT SMOKE PASS gateway_health "
        f"controller_routing={gateway_health.get('controller_routing')} "
        f"controller_harness_url={gateway_health.get('controller_harness_url')}"
    )

    status, body = json_request(f"{gateway_root}/models", timeout_seconds=args.timeout_seconds)
    gateway_model = require_model_list(require_status(status, body, "gateway /models"), "gateway /models")
    results["gateway_models"] = {"model_id": gateway_model}
    print(f"PORT SMOKE PASS gateway_models model={gateway_model}")

    status, body = json_request(f"{args.controller_base_url.rstrip('/')}/health", timeout_seconds=args.timeout_seconds)
    controller_health = require_status(status, body, "controller health")
    allowed_roots = controller_health.get("allowed_target_roots")
    if not isinstance(allowed_roots, list):
        raise RuntimeError("controller health did not include allowed_target_roots")
    missing_roots = [root for root in args.target_root if root not in allowed_roots]
    if missing_roots:
        raise RuntimeError(f"controller is missing allowed target root(s): {missing_roots}")
    results["controller_health"] = {
        "status": controller_health.get("status"),
        "allowed_target_roots": allowed_roots,
    }
    print("PORT SMOKE PASS controller_health allowed_roots=" + json.dumps(allowed_roots, ensure_ascii=True))

    role_results: dict[str, Any] = {}
    for port in ROLE_PORTS:
        status, body = json_request(f"http://127.0.0.1:{port}/v1/models", timeout_seconds=args.timeout_seconds)
        role_model = require_model_list(require_status(status, body, f"role {port} /models"), f"role {port} /models")
        role_results[str(port)] = {"model_id": role_model}
        print(f"PORT SMOKE PASS role_port={port} model={role_model}")
    results["roles"] = role_results

    status, body = json_request(f"{args.anythingllm_api_base_url.rstrip('/')}/api/ping", timeout_seconds=args.timeout_seconds)
    require_status(status, body, "AnythingLLM ping")
    results["anythingllm_ping"] = body
    print("PORT SMOKE PASS anythingllm_ping " + json.dumps(body, ensure_ascii=True, sort_keys=True))

    if api_key:
        status, body = json_request(
            f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspaces",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout_seconds=args.timeout_seconds,
        )
        require_status(status, body, "AnythingLLM workspaces")
        workspaces = body.get("workspaces")
        if not isinstance(workspaces, list):
            raise RuntimeError("AnythingLLM workspaces response did not include a workspace list")
        slugs = [
            workspace.get("slug")
            for workspace in workspaces
            if isinstance(workspace, dict) and isinstance(workspace.get("slug"), str)
        ]
        if args.workspace not in slugs:
            raise RuntimeError(f"AnythingLLM workspace {args.workspace!r} was not found in {slugs!r}")
        results["anythingllm_workspaces"] = slugs
        print("PORT SMOKE PASS anythingllm_workspaces " + json.dumps(slugs, ensure_ascii=True))
        results["anythingllm_provider"] = validate_anythingllm_provider_setting(
            api_base_url=args.anythingllm_api_base_url,
            api_key=api_key,
            expected_base_url=args.expected_anythingllm_base_url,
            timeout_seconds=args.timeout_seconds,
        )

    return results


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_packet_file(path: Path) -> None:
    packet = {
        "schema_version": 1,
        "packets": [
            {
                "id": "LIVE-MUTATION-0001",
                "target_files": [INVARIANT_REL],
                "allowed_operations": ["replace_text"],
                "operation": {
                    "kind": "replace_text",
                    "path": INVARIANT_REL,
                    "old": FROZEN_INVARIANT_OLD,
                    "new": FROZEN_INVARIANT_NEW,
                },
                "acceptance_criteria": ["Invariant text includes stealth manager placed-order index keys."],
                "max_context_tokens": 2000,
            }
        ],
        "verification_commands": [],
    }
    path.write_text(json.dumps(packet, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def run_command(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )


def ensure_git_for_apply(target: Path) -> str:
    result = run_command(["git", "rev-parse", "--show-toplevel"], target)
    if result.returncode == 0:
        top_level = Path(result.stdout.strip()).resolve()
        if top_level == target.resolve():
            return "existing_git"
    init = run_command(["git", "init"], target)
    if init.returncode != 0:
        raise RuntimeError(f"git init failed for disposable mutation copy: {init.stderr}")
    add = run_command(["git", "add", INVARIANT_REL], target)
    if add.returncode != 0:
        raise RuntimeError(f"git add failed for disposable mutation copy: {add.stderr}")
    return "initialized_git"


def run_mutation_probe(args: argparse.Namespace) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for source_root_value in args.target_root:
        source_root = Path(source_root_value).resolve()
        source_invariant = source_root / INVARIANT_REL
        if not source_invariant.exists():
            raise RuntimeError(f"mutation source is missing invariant file: {source_invariant}")
        source_text_before = source_invariant.read_text(encoding="utf-8")
        if FROZEN_INVARIANT_OLD not in source_text_before:
            raise RuntimeError(f"mutation source invariant text has changed: {source_invariant}")
        source_hash_before = file_digest(source_invariant)

        with tempfile.TemporaryDirectory(prefix="agentic-live-mutation-") as temp_dir:
            target = Path(temp_dir) / source_root.name
            shutil.copytree(source_root, target)
            git_mode = ensure_git_for_apply(target)
            target_invariant = target / INVARIANT_REL
            target_hash_before = file_digest(target_invariant)
            packet_file = Path(temp_dir) / "mutation-packet.json"
            write_packet_file(packet_file)
            result = invoke_implementation_workflow(
                ImplementationWorkflowInvocationRequest(
                    target_root=target,
                    output_dir=Path(temp_dir) / "mutation-output",
                    mode="apply",
                    packet_file=packet_file,
                    no_structure_index=True,
                )
            )
            target_text_after = target_invariant.read_text(encoding="utf-8")
            target_hash_after = file_digest(target_invariant)
            if result.status != WorkflowStatus.COMPLETED:
                raise RuntimeError(f"mutation probe workflow failed for {source_root}: {result.status.value}")
            if FROZEN_INVARIANT_NEW not in target_text_after or FROZEN_INVARIANT_OLD in target_text_after:
                raise RuntimeError(f"mutation probe did not mutate disposable copy as expected: {target}")
            if target_hash_before == target_hash_after:
                raise RuntimeError(f"mutation probe did not change disposable copy hash: {target}")

        source_hash_after = file_digest(source_invariant)
        if source_hash_before != source_hash_after:
            raise RuntimeError(f"mutation probe changed source fixture: {source_root}")
        if source_invariant.read_text(encoding="utf-8") != source_text_before:
            raise RuntimeError(f"mutation probe changed source fixture text: {source_root}")
        record = {
            "source_root": str(source_root),
            "git_mode": git_mode,
            "source_hash_unchanged": True,
            "disposable_copy_mutated": True,
        }
        results.append(record)
        print("MUTATION PROBE PASS " + json.dumps(record, ensure_ascii=True, sort_keys=True))
    return {"target_roots": results}


def build_code_context_envelope(target_root: str) -> dict[str, Any]:
    return {
        "workflow": "code_context.lookup",
        "schema_version": 1,
        "target_root": target_root,
        "query": CODE_CONTEXT_QUERY,
        "paths": [
            INVARIANT_REL,
            "core/stealth_order_manager.py",
            "bridges/stealth_order_bridge.py",
        ],
        "allowed_context_tools": ["structure_index", "git_grep", "read_file", "codegraph_context"],
        "relationship_queries": [
            {
                "kind": "callers",
                "symbol": "reveal_order_slice",
                "max_results": 20,
            }
        ],
        "max_results": 20,
        "max_files": 3,
    }


def require_code_context_response(body: dict[str, Any], label: str, target_root: str) -> dict[str, Any]:
    if body.get("workflow") != "code_context.lookup":
        raise RuntimeError(f"{label} returned unexpected workflow for {target_root}: {body.get('workflow')!r}")
    if body.get("status") != "completed":
        raise RuntimeError(f"{label} did not complete for {target_root}: {body.get('status')!r}")
    artifacts = body.get("artifacts")
    if not isinstance(artifacts, dict) or "lookup_results" not in artifacts:
        raise RuntimeError(f"{label} did not include lookup_results artifact for {target_root}")
    summary = body.get("summary")
    if not isinstance(summary, dict) or not isinstance(summary.get("grep_match_count"), int):
        raise RuntimeError(f"{label} did not include a bounded lookup summary for {target_root}")
    if not isinstance(summary.get("relationship_result_count"), int) or summary["relationship_result_count"] < 1:
        raise RuntimeError(f"{label} did not include curated relationship results for {target_root}: {summary!r}")
    return body


def validate_code_context_direct(args: argparse.Namespace, target_root: str) -> dict[str, Any]:
    watched = Path(target_root) / INVARIANT_REL
    before = file_digest(watched)
    status, body = json_request(
        f"{args.controller_base_url.rstrip('/')}/v1/controller/code-context/lookups",
        payload=build_code_context_envelope(target_root),
        timeout_seconds=args.timeout_seconds,
    )
    require_status(status, body, "code_context direct controller")
    response = require_code_context_response(body, "code_context direct controller", target_root)
    after = file_digest(watched)
    if before != after:
        raise RuntimeError(f"code_context direct controller mutated selected frozen file for {target_root}")
    print(f"CODE CONTEXT DIRECT PASS target={target_root} run_id={response.get('run_id')}")
    return response


def validate_code_context_gateway(args: argparse.Namespace, target_root: str) -> dict[str, Any]:
    watched = Path(target_root) / INVARIANT_REL
    before = file_digest(watched)
    payload = {
        "model": "agentic-controller",
        "messages": [
            {
                "role": "user",
                "content": json.dumps({"agentic_controller_request": build_code_context_envelope(target_root)}),
            }
        ],
    }
    status, body = json_request(
        f"{args.gateway_base_url.rstrip('/')}/chat/completions",
        payload=payload,
        timeout_seconds=args.timeout_seconds,
    )
    require_status(status, body, "code_context gateway route")
    response = body.get("agentic_controller_response")
    if not isinstance(response, dict):
        raise RuntimeError(f"code_context gateway route did not include agentic_controller_response for {target_root}")
    response = require_code_context_response(response, "code_context gateway route", target_root)
    after = file_digest(watched)
    if before != after:
        raise RuntimeError(f"code_context gateway route mutated selected frozen file for {target_root}")
    print(f"CODE CONTEXT GATEWAY PASS target={target_root} run_id={response.get('run_id')}")
    return response


def validate_code_context_anythingllm(args: argparse.Namespace, target_root: str, api_key: str) -> dict[str, Any]:
    watched = Path(target_root) / INVARIANT_REL
    before = file_digest(watched)
    envelope_text = json.dumps({"agentic_controller_request": build_code_context_envelope(target_root)}, ensure_ascii=True)
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload={"message": envelope_text, "mode": "chat"},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=args.timeout_seconds,
    )
    require_status(status, body, "code_context AnythingLLM route")
    text = text_response(body)
    missing = [
        marker
        for marker in ["code_context.lookup", "run_id:", "Artifacts:", "lookup_results", "relationship_results"]
        if marker not in text
    ]
    if missing:
        raise RuntimeError(f"code_context AnythingLLM route missing markers {missing} for {target_root}")
    after = file_digest(watched)
    if before != after:
        raise RuntimeError(f"code_context AnythingLLM route mutated selected frozen file for {target_root}")
    run_id = run_id_from_text(text)
    print(f"CODE CONTEXT ANYTHINGLLM PASS target={target_root} run_id={run_id or 'unknown'}")
    return {"run_id": run_id, "target_root": target_root}


def validate_code_context_routes(args: argparse.Namespace, api_key: str | None) -> dict[str, Any]:
    summary: dict[str, Any] = {"direct_controller": [], "gateway": [], "anythingllm": []}
    for target_root in args.target_root:
        direct = validate_code_context_direct(args, target_root)
        summary["direct_controller"].append({"target_root": target_root, "run_id": direct.get("run_id")})
        gateway = validate_code_context_gateway(args, target_root)
        summary["gateway"].append({"target_root": target_root, "run_id": gateway.get("run_id")})
    if args.skip_anythingllm:
        print("SKIP code_context AnythingLLM route validation")
    else:
        if not api_key:
            raise RuntimeError(f"{args.api_key_env} is required for code_context AnythingLLM route validation")
        for target_root in args.target_root:
            anything = validate_code_context_anythingllm(args, target_root, api_key)
            summary["anythingllm"].append(anything)
    return summary


def build_code_investigation_envelope(target_root: str) -> dict[str, Any]:
    return {
        "workflow": "code_investigation.plan",
        "schema_version": 1,
        "target_root": target_root,
        "user_request": (
            "Investigate whether StealthOrderManager.find_stealth_order_by_placed_order_id has one path before "
            "planning a refactor."
        ),
        "behavior": CODE_INVESTIGATION_BEHAVIOR,
        "entrypoint_hints": [
            {
                "path": "core/stealth_order_manager.py",
                "symbol": "StealthOrderManager.find_stealth_order_by_placed_order_id",
                "reason": "Known owner of placed-order lookup behavior.",
            }
        ],
        "queries": ["find_stealth_order_by_placed_order_id", "placed_order_id"],
        "paths": [
            "core/stealth_order_manager.py",
            "tests/unit/test_order_id_and_followup_rules.py",
            "tests/regression/test_order_id_regression.py",
        ],
        "max_results": 50,
        "max_files": 10,
    }


def require_code_investigation_response(body: dict[str, Any], label: str, target_root: str) -> dict[str, Any]:
    if body.get("workflow") != "code_investigation.plan":
        raise RuntimeError(f"{label} returned unexpected workflow for {target_root}: {body.get('workflow')!r}")
    if body.get("status") != "completed":
        raise RuntimeError(f"{label} did not complete for {target_root}: {body.get('status')!r}")
    artifacts = body.get("artifacts")
    if not isinstance(artifacts, dict) or "investigation_plan" not in artifacts:
        raise RuntimeError(f"{label} did not include investigation_plan artifact for {target_root}")
    summary = body.get("summary")
    if not isinstance(summary, dict) or not isinstance(summary.get("participating_file_count"), int):
        raise RuntimeError(f"{label} did not include a bounded investigation summary for {target_root}")
    return body


def validate_code_investigation_direct(args: argparse.Namespace, target_root: str) -> dict[str, Any]:
    watched = Path(target_root) / INVARIANT_REL
    before = file_digest(watched)
    status, body = json_request(
        f"{args.controller_base_url.rstrip('/')}/v1/controller/code-investigation/plans",
        payload=build_code_investigation_envelope(target_root),
        timeout_seconds=args.timeout_seconds,
    )
    require_status(status, body, "code_investigation direct controller")
    response = require_code_investigation_response(body, "code_investigation direct controller", target_root)
    after = file_digest(watched)
    if before != after:
        raise RuntimeError(f"code_investigation direct controller mutated selected frozen file for {target_root}")
    print(f"CODE INVESTIGATION DIRECT PASS target={target_root} run_id={response.get('run_id')}")
    return response


def validate_code_investigation_gateway(args: argparse.Namespace, target_root: str) -> dict[str, Any]:
    watched = Path(target_root) / INVARIANT_REL
    before = file_digest(watched)
    payload = {
        "model": "agentic-controller",
        "messages": [
            {
                "role": "user",
                "content": json.dumps({"agentic_controller_request": build_code_investigation_envelope(target_root)}),
            }
        ],
    }
    status, body = json_request(
        f"{args.gateway_base_url.rstrip('/')}/chat/completions",
        payload=payload,
        timeout_seconds=args.timeout_seconds,
    )
    require_status(status, body, "code_investigation gateway route")
    response = body.get("agentic_controller_response")
    if not isinstance(response, dict):
        raise RuntimeError(f"code_investigation gateway route did not include agentic_controller_response for {target_root}")
    response = require_code_investigation_response(response, "code_investigation gateway route", target_root)
    after = file_digest(watched)
    if before != after:
        raise RuntimeError(f"code_investigation gateway route mutated selected frozen file for {target_root}")
    print(f"CODE INVESTIGATION GATEWAY PASS target={target_root} run_id={response.get('run_id')}")
    return response


def validate_code_investigation_anythingllm(args: argparse.Namespace, target_root: str, api_key: str) -> dict[str, Any]:
    watched = Path(target_root) / INVARIANT_REL
    before = file_digest(watched)
    envelope_text = json.dumps({"agentic_controller_request": build_code_investigation_envelope(target_root)}, ensure_ascii=True)
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload={"message": envelope_text, "mode": "chat"},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=args.timeout_seconds,
    )
    require_status(status, body, "code_investigation AnythingLLM route")
    text = text_response(body)
    missing = [
        marker
        for marker in ["code_investigation.plan", "run_id:", "Artifacts:", "investigation_plan"]
        if marker not in text
    ]
    if missing:
        raise RuntimeError(f"code_investigation AnythingLLM route missing markers {missing} for {target_root}")
    after = file_digest(watched)
    if before != after:
        raise RuntimeError(f"code_investigation AnythingLLM route mutated selected frozen file for {target_root}")
    run_id = run_id_from_text(text)
    print(f"CODE INVESTIGATION ANYTHINGLLM PASS target={target_root} run_id={run_id or 'unknown'}")
    return {"run_id": run_id, "target_root": target_root}


def validate_code_investigation_routes(args: argparse.Namespace, api_key: str | None) -> dict[str, Any]:
    summary: dict[str, Any] = {"direct_controller": [], "gateway": [], "anythingllm": []}
    for target_root in args.target_root:
        direct = validate_code_investigation_direct(args, target_root)
        summary["direct_controller"].append({"target_root": target_root, "run_id": direct.get("run_id")})
        gateway = validate_code_investigation_gateway(args, target_root)
        summary["gateway"].append({"target_root": target_root, "run_id": gateway.get("run_id")})
    if args.skip_anythingllm:
        print("SKIP code_investigation AnythingLLM route validation")
    else:
        if not api_key:
            raise RuntimeError(f"{args.api_key_env} is required for code_investigation AnythingLLM route validation")
        for target_root in args.target_root:
            anything = validate_code_investigation_anythingllm(args, target_root, api_key)
            summary["anythingllm"].append(anything)
    return summary


def build_refactor_single_path_envelope(target_root: str) -> dict[str, Any]:
    return {
        "workflow": "refactor.single_path",
        "schema_version": 1,
        "target_root": target_root,
        "user_request": (
            "Investigate whether StealthOrderManager.find_stealth_order_by_placed_order_id has one path before "
            "planning a refactor."
        ),
        "behavior": CODE_INVESTIGATION_BEHAVIOR,
        "entrypoint_hints": [
            {
                "path": "core/stealth_order_manager.py",
                "symbol": "StealthOrderManager.find_stealth_order_by_placed_order_id",
                "reason": "Known owner of placed-order lookup behavior.",
            }
        ],
        "queries": ["find_stealth_order_by_placed_order_id", "placed_order_id"],
        "paths": [
            "core/stealth_order_manager.py",
            "tests/unit/test_order_id_and_followup_rules.py",
            "tests/regression/test_order_id_regression.py",
        ],
        "max_results": 50,
        "max_files": 10,
    }


def require_refactor_single_path_response(body: dict[str, Any], label: str, target_root: str) -> dict[str, Any]:
    if body.get("workflow") != "refactor.single_path":
        raise RuntimeError(f"{label} returned unexpected workflow for {target_root}: {body.get('workflow')!r}")
    if body.get("status") != "completed":
        raise RuntimeError(f"{label} did not complete for {target_root}: {body.get('status')!r}")
    artifacts = body.get("artifacts")
    if not isinstance(artifacts, dict) or "refactor_plan" not in artifacts:
        raise RuntimeError(f"{label} did not include refactor_plan artifact for {target_root}")
    summary = body.get("summary")
    if not isinstance(summary, dict) or summary.get("refactor_status") != "approval_required":
        raise RuntimeError(f"{label} did not return the expected approval gate for {target_root}: {summary!r}")
    return body


def validate_refactor_single_path_direct(args: argparse.Namespace, target_root: str) -> dict[str, Any]:
    watched = Path(target_root) / INVARIANT_REL
    before = file_digest(watched)
    status, body = json_request(
        f"{args.controller_base_url.rstrip('/')}/v1/controller/refactor/single-path",
        payload=build_refactor_single_path_envelope(target_root),
        timeout_seconds=args.timeout_seconds,
    )
    require_status(status, body, "refactor.single_path direct controller")
    response = require_refactor_single_path_response(body, "refactor.single_path direct controller", target_root)
    after = file_digest(watched)
    if before != after:
        raise RuntimeError(f"refactor.single_path direct controller mutated selected frozen file for {target_root}")
    print(f"REFACTOR SINGLE PATH DIRECT PASS target={target_root} run_id={response.get('run_id')}")
    return response


def validate_refactor_single_path_gateway(args: argparse.Namespace, target_root: str) -> dict[str, Any]:
    watched = Path(target_root) / INVARIANT_REL
    before = file_digest(watched)
    payload = {
        "model": "agentic-controller",
        "messages": [
            {
                "role": "user",
                "content": json.dumps({"agentic_controller_request": build_refactor_single_path_envelope(target_root)}),
            }
        ],
    }
    status, body = json_request(
        f"{args.gateway_base_url.rstrip('/')}/chat/completions",
        payload=payload,
        timeout_seconds=args.timeout_seconds,
    )
    require_status(status, body, "refactor.single_path gateway route")
    response = body.get("agentic_controller_response")
    if not isinstance(response, dict):
        raise RuntimeError(f"refactor.single_path gateway route did not include agentic_controller_response for {target_root}")
    response = require_refactor_single_path_response(response, "refactor.single_path gateway route", target_root)
    after = file_digest(watched)
    if before != after:
        raise RuntimeError(f"refactor.single_path gateway route mutated selected frozen file for {target_root}")
    print(f"REFACTOR SINGLE PATH GATEWAY PASS target={target_root} run_id={response.get('run_id')}")
    return response


def validate_refactor_single_path_anythingllm(args: argparse.Namespace, target_root: str, api_key: str) -> dict[str, Any]:
    watched = Path(target_root) / INVARIANT_REL
    before = file_digest(watched)
    envelope_text = json.dumps({"agentic_controller_request": build_refactor_single_path_envelope(target_root)}, ensure_ascii=True)
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload={"message": envelope_text, "mode": "chat"},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=args.timeout_seconds,
    )
    require_status(status, body, "refactor.single_path AnythingLLM route")
    text = text_response(body)
    missing = [
        marker
        for marker in ["refactor.single_path", "run_id:", "Artifacts:", "refactor_plan"]
        if marker not in text
    ]
    if missing:
        raise RuntimeError(f"refactor.single_path AnythingLLM route missing markers {missing} for {target_root}")
    after = file_digest(watched)
    if before != after:
        raise RuntimeError(f"refactor.single_path AnythingLLM route mutated selected frozen file for {target_root}")
    run_id = run_id_from_text(text)
    print(f"REFACTOR SINGLE PATH ANYTHINGLLM PASS target={target_root} run_id={run_id or 'unknown'}")
    return {"run_id": run_id, "target_root": target_root}


def validate_refactor_single_path_routes(args: argparse.Namespace, api_key: str | None) -> dict[str, Any]:
    summary: dict[str, Any] = {"direct_controller": [], "gateway": [], "anythingllm": []}
    for target_root in args.target_root:
        direct = validate_refactor_single_path_direct(args, target_root)
        summary["direct_controller"].append({"target_root": target_root, "run_id": direct.get("run_id")})
        gateway = validate_refactor_single_path_gateway(args, target_root)
        summary["gateway"].append({"target_root": target_root, "run_id": gateway.get("run_id")})
    if args.skip_anythingllm:
        print("SKIP refactor.single_path AnythingLLM route validation")
    else:
        if not api_key:
            raise RuntimeError(f"{args.api_key_env} is required for refactor.single_path AnythingLLM route validation")
        for target_root in args.target_root:
            anything = validate_refactor_single_path_anythingllm(args, target_root, api_key)
            summary["anythingllm"].append(anything)
    return summary


def build_workflow_feedback_envelope(
    *,
    target_root: str,
    target_workflow: str,
    target_run_id: str,
    surface: str,
) -> dict[str, Any]:
    return {
        "workflow": "workflow_feedback.record",
        "schema_version": 1,
        "target_workflow": target_workflow,
        "target_run_id": target_run_id,
        "target_root": target_root,
        "feedback": {
            "useful": [f"{surface} route returned bounded controller artifacts."],
            "wrong": [],
            "missing": ["Founder/tester should review whether this workflow result was actionable."],
            "too_slow": [],
            "too_noisy": [],
            "notes": "Live matrix feedback capture probe. This records validation feedback only and does not approve follow-up work.",
        },
        "tester": {"id": "live-matrix", "surface": surface},
        "request_payload": {"source": "scripts/validate_live_execution_planning_matrix.py"},
        "artifact_refs": {},
    }


def require_workflow_feedback_response(body: dict[str, Any], label: str, target_root: str) -> dict[str, Any]:
    if body.get("workflow") != "workflow_feedback.record":
        raise RuntimeError(f"{label} returned unexpected workflow for {target_root}: {body.get('workflow')!r}")
    if body.get("status") != "completed":
        raise RuntimeError(f"{label} did not complete for {target_root}: {body.get('status')!r}")
    artifacts = body.get("artifacts")
    if not isinstance(artifacts, dict) or "feedback_record" not in artifacts:
        raise RuntimeError(f"{label} did not include feedback_record artifact for {target_root}")
    summary = body.get("summary")
    if not isinstance(summary, dict) or not isinstance(summary.get("feedback_counts"), dict):
        raise RuntimeError(f"{label} did not include a feedback summary for {target_root}")
    if summary.get("linked_run_found") is not True:
        raise RuntimeError(f"{label} did not link to the target controller run for {target_root}: {summary!r}")
    return body


def route_record(route_summary: dict[str, Any], surface: str, target_root: str) -> dict[str, Any]:
    records = route_summary.get(surface)
    if not isinstance(records, list):
        raise RuntimeError(f"refactor.single_path summary is missing {surface} records")
    for record in records:
        if isinstance(record, dict) and record.get("target_root") == target_root:
            run_id = record.get("run_id")
            if not isinstance(run_id, str) or not run_id:
                raise RuntimeError(f"refactor.single_path {surface} run_id is missing for {target_root}: {record!r}")
            return record
    raise RuntimeError(f"refactor.single_path {surface} record is missing for {target_root}")


def validate_workflow_feedback_direct(
    args: argparse.Namespace,
    target_root: str,
    target_workflow: str,
    target_run_id: str,
) -> dict[str, Any]:
    watched = Path(target_root) / INVARIANT_REL
    before = file_digest(watched)
    status, body = json_request(
        f"{args.controller_base_url.rstrip('/')}/v1/controller/workflow-feedback/records",
        payload=build_workflow_feedback_envelope(
            target_root=target_root,
            target_workflow=target_workflow,
            target_run_id=target_run_id,
            surface="direct-controller",
        ),
        timeout_seconds=args.timeout_seconds,
    )
    require_status(status, body, "workflow_feedback direct controller")
    response = require_workflow_feedback_response(body, "workflow_feedback direct controller", target_root)
    after = file_digest(watched)
    if before != after:
        raise RuntimeError(f"workflow_feedback direct controller mutated selected frozen file for {target_root}")
    print(f"WORKFLOW FEEDBACK DIRECT PASS target={target_root} run_id={response.get('run_id')}")
    return response


def validate_workflow_feedback_gateway(
    args: argparse.Namespace,
    target_root: str,
    target_workflow: str,
    target_run_id: str,
) -> dict[str, Any]:
    watched = Path(target_root) / INVARIANT_REL
    before = file_digest(watched)
    payload = {
        "model": "agentic-controller",
        "messages": [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "agentic_controller_request": build_workflow_feedback_envelope(
                            target_root=target_root,
                            target_workflow=target_workflow,
                            target_run_id=target_run_id,
                            surface="gateway",
                        )
                    }
                ),
            }
        ],
    }
    status, body = json_request(
        f"{args.gateway_base_url.rstrip('/')}/chat/completions",
        payload=payload,
        timeout_seconds=args.timeout_seconds,
    )
    require_status(status, body, "workflow_feedback gateway route")
    response = body.get("agentic_controller_response")
    if not isinstance(response, dict):
        raise RuntimeError(f"workflow_feedback gateway route did not include agentic_controller_response for {target_root}")
    response = require_workflow_feedback_response(response, "workflow_feedback gateway route", target_root)
    after = file_digest(watched)
    if before != after:
        raise RuntimeError(f"workflow_feedback gateway route mutated selected frozen file for {target_root}")
    print(f"WORKFLOW FEEDBACK GATEWAY PASS target={target_root} run_id={response.get('run_id')}")
    return response


def validate_workflow_feedback_anythingllm(
    args: argparse.Namespace,
    target_root: str,
    target_workflow: str,
    target_run_id: str,
    api_key: str,
) -> dict[str, Any]:
    watched = Path(target_root) / INVARIANT_REL
    before = file_digest(watched)
    envelope_text = json.dumps(
        {
            "agentic_controller_request": build_workflow_feedback_envelope(
                target_root=target_root,
                target_workflow=target_workflow,
                target_run_id=target_run_id,
                surface="AnythingLLM",
            )
        },
        ensure_ascii=True,
    )
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload={"message": envelope_text, "mode": "chat"},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=args.timeout_seconds,
    )
    require_status(status, body, "workflow_feedback AnythingLLM route")
    text = text_response(body)
    missing = [
        marker
        for marker in ["workflow_feedback.record", "run_id:", "Artifacts:", "feedback_record"]
        if marker not in text
    ]
    if missing:
        raise RuntimeError(f"workflow_feedback AnythingLLM route missing markers {missing} for {target_root}")
    after = file_digest(watched)
    if before != after:
        raise RuntimeError(f"workflow_feedback AnythingLLM route mutated selected frozen file for {target_root}")
    run_id = run_id_from_text(text)
    print(f"WORKFLOW FEEDBACK ANYTHINGLLM PASS target={target_root} run_id={run_id or 'unknown'}")
    return {"run_id": run_id, "target_root": target_root}


def validate_workflow_feedback_routes(
    args: argparse.Namespace,
    api_key: str | None,
    refactor_summary: dict[str, Any],
) -> dict[str, Any]:
    summary: dict[str, Any] = {"direct_controller": [], "gateway": [], "anythingllm": []}
    target_workflow = "refactor.single_path"
    for target_root in args.target_root:
        direct_target = route_record(refactor_summary, "direct_controller", target_root)
        direct = validate_workflow_feedback_direct(args, target_root, target_workflow, direct_target["run_id"])
        summary["direct_controller"].append({"target_root": target_root, "run_id": direct.get("run_id")})
        gateway_target = route_record(refactor_summary, "gateway", target_root)
        gateway = validate_workflow_feedback_gateway(args, target_root, target_workflow, gateway_target["run_id"])
        summary["gateway"].append({"target_root": target_root, "run_id": gateway.get("run_id")})
    if args.skip_anythingllm:
        print("SKIP workflow_feedback AnythingLLM route validation")
    else:
        if not api_key:
            raise RuntimeError(f"{args.api_key_env} is required for workflow_feedback AnythingLLM route validation")
        for target_root in args.target_root:
            anything_target = route_record(refactor_summary, "anythingllm", target_root)
            anything = validate_workflow_feedback_anythingllm(
                args,
                target_root,
                target_workflow,
                anything_target["run_id"],
                api_key,
            )
            summary["anythingllm"].append(anything)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-base-url", default=DEFAULT_MODEL_BASE_URL)
    parser.add_argument("--gateway-base-url", default=DEFAULT_GATEWAY_BASE_URL)
    parser.add_argument("--controller-base-url", default=DEFAULT_CONTROLLER_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--expected-anythingllm-base-url", default=DEFAULT_EXPECTED_ANYTHINGLLM_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--target-root", action="append", default=[])
    parser.add_argument(
        "--mode",
        action="append",
        choices=["investigation_only", "dry_run", "workflow_router_apply_disposable_copy", "both"],
        default=[],
        help="Controller mode to validate through direct gateway and AnythingLLM. Default: dry_run.",
    )
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--skip-port-smoke", action="store_true")
    parser.add_argument("--skip-anythingllm", action="store_true")
    parser.add_argument("--skip-mutation-probe", action="store_true")
    parser.add_argument("--skip-code-context", action="store_true")
    parser.add_argument("--skip-code-investigation", action="store_true")
    parser.add_argument("--skip-refactor-single-path", action="store_true")
    parser.add_argument("--skip-workflow-feedback", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.target_root = args.target_root or list(DEFAULT_TARGET_ROOTS)
    modes = resolve_modes(args.mode or ["dry_run"])
    api_key = os.environ.get(args.api_key_env)
    if not args.skip_anythingllm and not api_key:
        raise RuntimeError(f"{args.api_key_env} is required unless --skip-anythingllm is set")

    summary: dict[str, Any] = {
        "modes": modes,
        "target_roots": args.target_root,
        "port_smoke": None,
        "gateway": [],
        "anythingllm": [],
        "code_context": None,
        "code_investigation": None,
        "refactor_single_path": None,
        "workflow_feedback": None,
        "mutation_probe": None,
    }

    if not args.skip_port_smoke:
        summary["port_smoke"] = validate_port_smoke(args, api_key)

    route_args = argparse.Namespace(
        gateway_base_url=args.gateway_base_url,
        anythingllm_api_base_url=args.anythingllm_api_base_url,
        workspace=args.workspace,
        timeout_seconds=args.timeout_seconds,
    )
    for mode in modes:
        for target_root in args.target_root:
            response = validate_gateway_route(route_args, target_root, mode)
            summary["gateway"].append({"mode": mode, "target_root": target_root, "run_id": response.get("run_id")})

    if args.skip_anythingllm:
        print("SKIP AnythingLLM route validation")
    else:
        assert api_key is not None
        for mode in modes:
            for target_root in args.target_root:
                result = validate_anythingllm_route(route_args, target_root, api_key, mode)
                summary["anythingllm"].append(
                    {"mode": mode, "target_root": target_root, "run_id": result.get("run_id")}
                )

    if args.skip_code_context:
        print("SKIP code_context route validation")
    else:
        summary["code_context"] = validate_code_context_routes(args, api_key)

    if args.skip_code_investigation:
        print("SKIP code_investigation route validation")
    else:
        summary["code_investigation"] = validate_code_investigation_routes(args, api_key)

    if args.skip_refactor_single_path:
        print("SKIP refactor.single_path route validation")
    else:
        summary["refactor_single_path"] = validate_refactor_single_path_routes(args, api_key)

    if args.skip_workflow_feedback:
        print("SKIP workflow_feedback route validation")
    elif args.skip_refactor_single_path or not isinstance(summary["refactor_single_path"], dict):
        raise RuntimeError("workflow_feedback route validation requires refactor.single_path route validation")
    else:
        summary["workflow_feedback"] = validate_workflow_feedback_routes(args, api_key, summary["refactor_single_path"])

    if args.skip_mutation_probe:
        print("SKIP mutation probe")
    else:
        summary["mutation_probe"] = run_mutation_probe(args)

    print("LIVE MATRIX SUMMARY " + json.dumps(summary, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
