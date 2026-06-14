#!/usr/bin/env python3
"""Validate workflow-router behavior across controlled fixture repositories."""

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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.fixtures.manager import (  # noqa: E402
    DEFAULT_MANIFEST_PATH,
    FixtureEntry,
    fixture_entries,
    load_fixture_manifest,
)


DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "multi-repo-fixtures"
PORT_HEALTH_PROBES = (
    ("localhost-model", "http://127.0.0.1:8000/v1/models"),
    ("llm-gateway", "http://127.0.0.1:8300/v1/models"),
    ("controller", "http://127.0.0.1:8400/health"),
    ("workflow-router-gateway", "http://127.0.0.1:8500/v1/models"),
)
EVIDENCE_BOUNDARY_ARTIFACTS = {
    "downstream_data_model_lookup",
    "downstream_change_surface_summary",
}


@dataclass(frozen=True)
class FixtureLiveCase:
    case_id: str
    prompt_family: str
    fixture_id: str
    prompt_template: str
    expected_workflow: str
    expected_artifact: str
    expected_route_hint: str
    expected_task_class: str
    expected_layout_status: str = "supported"
    expected_artifact_markers: tuple[str, ...] = ()


LIVE_CASES = [
    FixtureLiveCase(
        case_id="coinbase-code-explanation",
        prompt_family="code_explanation",
        fixture_id="coinbase-frozen",
        prompt_template=(
            "In {target_root}, explain what find_stealth_order_by_placed_order_id does "
            "in core/stealth_order_manager.py. Read only. Include key inputs, outputs, side effects, and tests. Return JSON."
        ),
        expected_workflow="code_investigation.plan",
        expected_artifact="downstream_code_explanation",
        expected_route_hint="l1_explain_code_terms",
        expected_task_class="read_only_l1",
    ),
    FixtureLiveCase(
        case_id="coinbase-git-code-explanation",
        prompt_family="code_explanation",
        fixture_id="coinbase-frozen-git",
        prompt_template=(
            "In {target_root}, explain what find_stealth_order_by_placed_order_id does "
            "in core/stealth_order_manager.py. Read only. Include key inputs, outputs, side effects, and tests. Return JSON."
        ),
        expected_workflow="code_investigation.plan",
        expected_artifact="downstream_code_explanation",
        expected_route_hint="l1_explain_code_terms",
        expected_task_class="read_only_l1",
    ),
    FixtureLiveCase(
        case_id="python-service-code-explanation",
        prompt_family="code_explanation",
        fixture_id="python-service-generalization",
        prompt_template=(
            "In {target_root}, explain resolve_order_status in service/orders.py. Read only. "
            "Include inputs, return value, side effects, and tests. Return JSON."
        ),
        expected_workflow="code_investigation.plan",
        expected_artifact="downstream_code_explanation",
        expected_route_hint="l1_explain_code_terms",
        expected_task_class="read_only_l1",
    ),
    FixtureLiveCase(
        case_id="python-service-endpoint-route-lookup",
        prompt_family="endpoint_route_lookup",
        fixture_id="python-service-generalization",
        prompt_template=(
            "In {target_root}, locate the order request message handler. Read only. "
            "Return handler file, handler symbol, route or message evidence, related tests, "
            "and whether an HTTP method/path is present. Return JSON."
        ),
        expected_workflow="code_investigation.plan",
        expected_artifact="downstream_endpoint_route_lookup",
        expected_route_hint="l1_endpoint_route_lookup_terms",
        expected_task_class="read_only_l1",
        expected_artifact_markers=("service/api.py", "handle_create_order", "message.get", "read_only_no_source_mutation"),
    ),
    FixtureLiveCase(
        case_id="coinbase-schema-lookup",
        prompt_family="schema_lookup",
        fixture_id="coinbase-frozen",
        prompt_template=(
            "In {target_root}, find only the persisted stealth_orders table schema. Read only. "
            "Return schema field names, model files, and source refs. Exclude runtime dictionary fields. Return JSON."
        ),
        expected_workflow="code_investigation.plan",
        expected_artifact="downstream_data_model_lookup",
        expected_route_hint="l1_data_model_lookup_terms",
        expected_task_class="read_only_l1",
    ),
    FixtureLiveCase(
        case_id="coinbase-git-schema-lookup",
        prompt_family="schema_lookup",
        fixture_id="coinbase-frozen-git",
        prompt_template=(
            "In {target_root}, find only the persisted stealth_orders table schema. Read only. "
            "Return schema field names, model files, and source refs. Exclude runtime dictionary fields. Return JSON."
        ),
        expected_workflow="code_investigation.plan",
        expected_artifact="downstream_data_model_lookup",
        expected_route_hint="l1_data_model_lookup_terms",
        expected_task_class="read_only_l1",
    ),
    FixtureLiveCase(
        case_id="python-service-schema-lookup",
        prompt_family="schema_lookup",
        fixture_id="python-service-generalization",
        prompt_template=(
            "In {target_root}, find the orders table schema only. Read only. "
            "Return schema field names, model files, and source refs. Return JSON."
        ),
        expected_workflow="code_investigation.plan",
        expected_artifact="downstream_data_model_lookup",
        expected_route_hint="l1_data_model_lookup_terms",
        expected_task_class="read_only_l1",
        expected_artifact_markers=("database/schema.py", "OrderRecord", "ORDERS_TABLE_SCHEMA", "item_count"),
    ),
    FixtureLiveCase(
        case_id="coinbase-request-flow",
        prompt_family="request_flow",
        fixture_id="coinbase-frozen",
        prompt_template=(
            "In {target_root}, map the request/data flow for request_stealth_orders from dashboard message "
            "to stealth order snapshot. Read only. Return flow steps, participating files, risks, gaps, "
            "and verification commands. Return JSON."
        ),
        expected_workflow="code_investigation.plan",
        expected_artifact="downstream_request_flow_map",
        expected_route_hint="l2_request_flow_map_terms",
        expected_task_class="l2_read_only",
    ),
    FixtureLiveCase(
        case_id="coinbase-git-request-flow",
        prompt_family="request_flow",
        fixture_id="coinbase-frozen-git",
        prompt_template=(
            "In {target_root}, map the request/data flow for request_stealth_orders from dashboard message "
            "to stealth order snapshot. Read only. Return flow steps, participating files, risks, gaps, "
            "and verification commands. Return JSON."
        ),
        expected_workflow="code_investigation.plan",
        expected_artifact="downstream_request_flow_map",
        expected_route_hint="l2_request_flow_map_terms",
        expected_task_class="l2_read_only",
    ),
    FixtureLiveCase(
        case_id="python-service-request-flow",
        prompt_family="request_flow",
        fixture_id="python-service-generalization",
        prompt_template=(
            "In {target_root}, follow handler branch trace for handle_create_order as a request flow through "
            "the downstream snapshot function. Read only. Return flow steps, participating files, evidence refs, "
            "related tests, risks, gaps, and verification. Return JSON."
        ),
        expected_workflow="code_investigation.plan",
        expected_artifact="downstream_request_flow_map",
        expected_route_hint="l2_request_flow_map_terms",
        expected_task_class="l2_read_only",
    ),
    FixtureLiveCase(
        case_id="coinbase-change-surface",
        prompt_family="change_surface",
        fixture_id="coinbase-frozen",
        prompt_template=(
            "In {target_root}, identify the minimal safe change surface for changing placed_order_id stealth lookup behavior. "
            "Read only. Return files that would need review, related tests, risk level, gaps, and verification commands. "
            "Stop before implementation. Return JSON."
        ),
        expected_workflow="code_investigation.plan",
        expected_artifact="downstream_change_surface_summary",
        expected_route_hint="l2_change_surface_summary_terms",
        expected_task_class="l2_read_only",
    ),
    FixtureLiveCase(
        case_id="coinbase-git-change-surface",
        prompt_family="change_surface",
        fixture_id="coinbase-frozen-git",
        prompt_template=(
            "In {target_root}, identify the minimal safe change surface for changing placed_order_id stealth lookup behavior. "
            "Read only. Return files that would need review, related tests, risk level, gaps, and verification commands. "
            "Stop before implementation. Return JSON."
        ),
        expected_workflow="code_investigation.plan",
        expected_artifact="downstream_change_surface_summary",
        expected_route_hint="l2_change_surface_summary_terms",
        expected_task_class="l2_read_only",
    ),
    FixtureLiveCase(
        case_id="python-service-change-surface",
        prompt_family="change_surface",
        fixture_id="python-service-generalization",
        prompt_template=(
            "In {target_root}, identify files to touch and files not to touch for the minimal safe change surface "
            "for order status behavior. Read only and stop before implementation. Return risks, gaps, "
            "and verification commands. Return JSON."
        ),
        expected_workflow="code_investigation.plan",
        expected_artifact="downstream_change_surface_summary",
        expected_route_hint="l2_change_surface_summary_terms",
        expected_task_class="l2_read_only",
    ),
    FixtureLiveCase(
        case_id="node-cli-configuration-lookup",
        prompt_family="configuration_lookup",
        fixture_id="node-cli-generalization",
        prompt_template=(
            "In {target_root}, locate where DEFAULT_PROFILE is defined or used as a configuration setting. "
            "Read only. Include source refs and runtime effect. Return JSON."
        ),
        expected_workflow="code_investigation.plan",
        expected_artifact="downstream_configuration_lookup",
        expected_route_hint="l1_configuration_lookup_terms",
        expected_task_class="read_only_l1",
    ),
    FixtureLiveCase(
        case_id="go-http-configuration-lookup",
        prompt_family="configuration_lookup",
        fixture_id="go-http-generalization",
        prompt_template=(
            "In {target_root}, locate where ORDER_STATUS_TIMEOUT_MS is defined or used as a configuration setting. "
            "Read only. Include source refs and runtime effect. Return JSON."
        ),
        expected_workflow="code_investigation.plan",
        expected_artifact="downstream_configuration_lookup",
        expected_route_hint="l1_configuration_lookup_terms",
        expected_task_class="read_only_l1",
    ),
    FixtureLiveCase(
        case_id="go-http-table-read-write",
        prompt_family="table_read_write",
        fixture_id="go-http-generalization",
        prompt_template=(
            "In {target_root}, locate the orders table definition, reads, and writes. Read only. "
            "Return definition sites, read sites, write sites, source refs, gaps, and mutation policy. Return JSON."
        ),
        expected_workflow="code_investigation.plan",
        expected_artifact="downstream_table_read_write_lookup",
        expected_route_hint="l2_table_read_write_lookup_terms",
        expected_task_class="l2_read_only",
    ),
]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


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
        text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            body = {"error": {"message": text, "code": "invalid_json_error_body"}}
        return exc.code, body


def text_response(body: dict[str, Any]) -> str:
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
    for key in ("textResponse", "response", "message", "text"):
        value = body.get(key)
        if isinstance(value, str):
            return value
    raise RuntimeError("response did not include assistant text")


def json_content(body: dict[str, Any]) -> dict[str, Any]:
    text = text_response(body)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise RuntimeError("assistant JSON content was not an object")
    return parsed


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def watched_hashes(entry: FixtureEntry) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative_path in entry.watched_paths:
        path = entry.source_path / relative_path
        if path.exists() and path.is_file():
            hashes[relative_path] = digest_file(path)
    if not hashes:
        raise RuntimeError(f"{entry.fixture_id} did not contain watched files")
    return hashes


def git_status(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    result = subprocess.run(["git", "-C", str(root), "status", "--short"], check=True, capture_output=True, text=True)
    return result.stdout


def read_json_artifact(path_value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(path_value, str) or not path_value:
        raise RuntimeError(f"{label} artifact path was missing")
    path = Path(path_value)
    if not path.is_file():
        raise RuntimeError(f"{label} artifact path does not exist: {path_value}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} artifact was not a JSON object: {path_value}")
    return value


def assert_route_decision(parsed: dict[str, Any], *, case: FixtureLiveCase, label: str) -> dict[str, Any]:
    artifacts = parsed.get("artifacts") if isinstance(parsed.get("artifacts"), dict) else {}
    decision = read_json_artifact(artifacts.get("route_decision"), label=f"{label} route_decision")
    evidence = decision.get("evidence") if isinstance(decision.get("evidence"), list) else []
    if not any(item.get("rule") == case.expected_route_hint for item in evidence if isinstance(item, dict)):
        raise RuntimeError(f"{label} missing route hint {case.expected_route_hint}")
    gate = decision.get("model_capability_routing")
    if not isinstance(gate, dict):
        raise RuntimeError(f"{label} missing model_capability_routing")
    expected_gate = {
        "status": "approved",
        "task_class": case.expected_task_class,
        "task_policy_status": "approved",
    }
    wrong = {key: {"expected": value, "actual": gate.get(key)} for key, value in expected_gate.items() if gate.get(key) != value}
    if wrong:
        raise RuntimeError(f"{label} model capability gate mismatch: {json.dumps(wrong, sort_keys=True)}")
    audit = decision.get("context_source_audit")
    if not isinstance(audit, dict):
        raise RuntimeError(f"{label} missing context_source_audit")
    layout = audit.get("layout") if isinstance(audit.get("layout"), dict) else {}
    if layout.get("status") != case.expected_layout_status:
        raise RuntimeError(
            f"{label} layout status mismatch: expected {case.expected_layout_status}, got {layout.get('status')!r}"
        )
    return decision


def assert_parsed_content(parsed: dict[str, Any], *, case: FixtureLiveCase, label: str) -> dict[str, Any]:
    contract = parsed.get("chat_contract") if isinstance(parsed.get("chat_contract"), dict) else {}
    inline_contract = parsed.get("inline_answer_contract") if isinstance(parsed.get("inline_answer_contract"), dict) else {}
    artifacts = parsed.get("artifacts") if isinstance(parsed.get("artifacts"), dict) else {}
    if parsed.get("workflow") != "workflow_router.plan":
        raise RuntimeError(f"{label} returned wrong wrapper workflow: {parsed.get('workflow')!r}")
    if contract.get("selected_workflow") != case.expected_workflow:
        raise RuntimeError(f"{label} selected wrong workflow: {contract.get('selected_workflow')!r}")
    if case.expected_artifact not in artifacts:
        raise RuntimeError(f"{label} missing expected artifact: {case.expected_artifact}")
    artifact_markers = list(case.expected_artifact_markers)
    artifact_marker_status = None
    if artifact_markers:
        artifact_path_value = artifacts.get(case.expected_artifact)
        if not isinstance(artifact_path_value, str) or not artifact_path_value:
            raise RuntimeError(f"{label} expected artifact path missing for marker validation")
        artifact_path = Path(artifact_path_value)
        if not artifact_path.is_file():
            raise RuntimeError(f"{label} expected artifact path does not exist for marker validation: {artifact_path}")
        artifact_text = artifact_path.read_text(encoding="utf-8")
        missing_markers = [marker for marker in artifact_markers if marker not in artifact_text]
        if missing_markers:
            raise RuntimeError(f"{label} artifact missing marker(s): {json.dumps(missing_markers, ensure_ascii=True)}")
        artifact_marker_status = {"required": artifact_markers, "missing": []}
    evidence_boundary_status = None
    evidence_boundary_errors: list[Any] = []
    if case.expected_artifact in EVIDENCE_BOUNDARY_ARTIFACTS:
        evidence_boundary_status = inline_contract.get("evidence_boundary_status")
        evidence_boundary_errors = (
            inline_contract.get("evidence_boundary_errors")
            if isinstance(inline_contract.get("evidence_boundary_errors"), list)
            else []
        )
        if evidence_boundary_status != "passed" or evidence_boundary_errors:
            raise RuntimeError(
                f"{label} evidence boundary gate failed: "
                + json.dumps(
                    {"status": evidence_boundary_status, "errors": evidence_boundary_errors},
                    ensure_ascii=True,
                    sort_keys=True,
                )
            )
    decision = assert_route_decision(parsed, case=case, label=label)
    audit = decision.get("context_source_audit") if isinstance(decision.get("context_source_audit"), dict) else {}
    layout = audit.get("layout") if isinstance(audit.get("layout"), dict) else {}
    return {
        "run_id": str(parsed.get("run_id") or ""),
        "selected_workflow": contract.get("selected_workflow"),
        "selected_skills": contract.get("selected_skills"),
        "selected_tools": contract.get("selected_tools"),
        "artifact_keys": sorted(artifacts),
        "route_decision": str(artifacts.get("route_decision")),
        "route_status": decision.get("status"),
        "layout_status": layout.get("status"),
        "supported_file_count": layout.get("supported_file_count"),
        "selected_context_sources": audit.get("selected_source_ids") if isinstance(audit.get("selected_source_ids"), list) else [],
        "context_gaps": audit.get("gaps") if isinstance(audit.get("gaps"), list) else [],
        "evidence_boundary_status": evidence_boundary_status,
        "evidence_boundary_error_count": len(evidence_boundary_errors),
        "artifact_marker_status": artifact_marker_status,
    }


def assert_unchanged(entry: FixtureEntry, before_hashes: dict[str, str], before_git_status: str | None, *, label: str) -> None:
    after_hashes = watched_hashes(entry)
    after_git_status = git_status(entry.source_path)
    if before_hashes != after_hashes:
        raise RuntimeError(f"{label} mutated watched files for {entry.fixture_id}")
    if before_git_status is not None and before_git_status != after_git_status:
        raise RuntimeError(f"{label} changed git status for {entry.fixture_id}")


def validate_gateway_case(args: argparse.Namespace, entry: FixtureEntry, case: FixtureLiveCase) -> dict[str, Any]:
    before_hashes = watched_hashes(entry)
    before_git_status = git_status(entry.source_path)
    prompt = case.prompt_template.format(target_root=entry.source_path.as_posix())
    status, body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "output_format": "json",
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"gateway {case.case_id} returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    parsed = json_content(body)
    proof = assert_parsed_content(parsed, case=case, label=f"gateway {case.case_id}")
    assert_unchanged(entry, before_hashes, before_git_status, label=f"gateway {case.case_id}")
    result = case_result("gateway", entry, case, proof, before_git_status)
    print(f"MULTI REPO FIXTURE GATEWAY PASS case={case.case_id} fixture={entry.fixture_id} run_id={result['run_id']}")
    return result


def validate_anythingllm_case(
    args: argparse.Namespace,
    entry: FixtureEntry,
    case: FixtureLiveCase,
    api_key: str,
) -> dict[str, Any]:
    before_hashes = watched_hashes(entry)
    before_git_status = git_status(entry.source_path)
    prompt = case.prompt_template.format(target_root=entry.source_path.as_posix())
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload={
            "message": prompt,
            "mode": "chat",
            "sessionId": f"phase101-multi-repo-{case.case_id}-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"AnythingLLM {case.case_id} returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    parsed = json_content(body)
    proof = assert_parsed_content(parsed, case=case, label=f"AnythingLLM {case.case_id}")
    assert_unchanged(entry, before_hashes, before_git_status, label=f"AnythingLLM {case.case_id}")
    result = case_result("anythingllm", entry, case, proof, before_git_status)
    print(f"MULTI REPO FIXTURE ANYTHINGLLM PASS case={case.case_id} fixture={entry.fixture_id} run_id={result['run_id']}")
    return result


def case_result(
    client: str,
    entry: FixtureEntry,
    case: FixtureLiveCase,
    proof: dict[str, Any],
    before_git_status: str | None,
) -> dict[str, Any]:
    return {
        "client": client,
        "case_id": case.case_id,
        "prompt_family": case.prompt_family,
        "fixture_id": case.fixture_id,
        "category": entry.category,
        "target_root": entry.source_path.as_posix(),
        "run_id": proof["run_id"],
        "status": "passed",
        "selected_workflow": proof["selected_workflow"],
        "selected_skills": proof["selected_skills"],
        "selected_tools": proof["selected_tools"],
        "expected_artifact": case.expected_artifact,
        "artifact_keys": proof["artifact_keys"],
        "route_decision": proof["route_decision"],
        "layout_status": proof["layout_status"],
        "supported_file_count": proof["supported_file_count"],
        "selected_context_sources": proof["selected_context_sources"],
        "context_gaps": proof["context_gaps"],
        "evidence_boundary_status": proof.get("evidence_boundary_status"),
        "evidence_boundary_error_count": proof.get("evidence_boundary_error_count"),
        "artifact_marker_status": proof.get("artifact_marker_status"),
        "expected_route_hint": case.expected_route_hint,
        "expected_task_class": case.expected_task_class,
        "repo_layout_limitations": repo_layout_limitations(entry),
        "source_unchanged": True,
        "git_status_unchanged": before_git_status == git_status(entry.source_path),
    }


def parity_matrix(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_family: dict[str, list[dict[str, Any]]] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        by_family.setdefault(str(item.get("prompt_family") or "unknown"), []).append(item)
    families: list[dict[str, Any]] = []
    fixture_specific_deltas: list[dict[str, Any]] = []
    shared_workflow_deltas: list[dict[str, Any]] = []
    for family, items in sorted(by_family.items()):
        failed = [item for item in items if item.get("status") != "passed"]
        selected_workflows = sorted({str(item.get("selected_workflow")) for item in items})
        artifacts = sorted({str(item.get("expected_artifact")) for item in items})
        fixtures = sorted({str(item.get("fixture_id")) for item in items})
        categories = sorted({str(item.get("category")) for item in items})
        clients = sorted({str(item.get("client")) for item in items})
        status = "passed" if not failed else "failed"
        if failed and len(failed) == len(items):
            shared_workflow_deltas.append({"prompt_family": family, "failed_case_ids": [item["case_id"] for item in failed]})
        elif failed:
            fixture_specific_deltas.append({"prompt_family": family, "failed_case_ids": [item["case_id"] for item in failed]})
        families.append(
            {
                "prompt_family": family,
                "status": status,
                "case_count": len(items),
                "fixture_count": len(fixtures),
                "fixtures": fixtures,
                "category_count": len(categories),
                "categories": categories,
                "clients": clients,
                "selected_workflows": selected_workflows,
                "expected_artifacts": artifacts,
                "fixture_specific_delta_count": 0 if not failed else len(failed),
            }
        )
    return {
        "status": "passed" if not fixture_specific_deltas and not shared_workflow_deltas else "failed",
        "family_count": len(families),
        "families": families,
        "fixture_specific_deltas": fixture_specific_deltas,
        "shared_workflow_deltas": shared_workflow_deltas,
    }


def repo_layout_limitations(entry: FixtureEntry) -> list[str]:
    if entry.category == "synthetic-go-http-service":
        return [
            "Go files are admitted by the router layout gate, but structure indexing remains generic rather than Go-AST-specific.",
            "Go verification command quality is not a Phase 101 pass condition.",
        ]
    if entry.category == "synthetic-node-cli":
        return [
            "JavaScript files are admitted by the router layout gate, but structure indexing remains generic rather than JavaScript-AST-specific.",
        ]
    return []


def validate_port_health(timeout_seconds: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for label, url in PORT_HEALTH_PROBES:
        try:
            status, _body = json_request(url, timeout_seconds=min(30, timeout_seconds), method="GET")
            item = {"label": label, "url": url, "status": "passed", "http_status": status}
        except Exception as exc:  # noqa: BLE001
            item = {"label": label, "url": url, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}
        results.append(item)
        if item.get("status") != "passed" or item.get("http_status") != 200:
            failures.append(item)
    if failures:
        raise RuntimeError("port health failed: " + json.dumps(failures, ensure_ascii=True, sort_keys=True))
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_PATH))
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--live-anythingllm", action="store_true")
    parser.add_argument("--port-health", action="store_true")
    return parser.parse_args()


def selected_cases(case_ids: list[str] | None) -> list[FixtureLiveCase]:
    if not case_ids:
        return LIVE_CASES
    by_id = {case.case_id: case for case in LIVE_CASES}
    missing = sorted(set(case_ids) - set(by_id))
    if missing:
        raise RuntimeError("unknown case id(s): " + ", ".join(missing))
    return [by_id[case_id] for case_id in case_ids]


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root).resolve()
    manifest = load_fixture_manifest(config_root, Path(args.manifest))
    entries = {entry.fixture_id: entry for entry in fixture_entries(config_root, manifest)}
    output_path = Path(args.output_path) if args.output_path else config_root / DEFAULT_OUTPUT_DIR / f"multi-repo-fixtures-{utc_timestamp()}.json"
    cases = selected_cases(args.case_ids)
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "multi_repo_fixture_live_report",
        "status": "failed",
        "created_at": utc_timestamp(),
        "cases": [],
        "port_health": [],
        "errors": [],
    }
    try:
        if args.port_health:
            report["port_health"] = validate_port_health(args.timeout_seconds)
        api_key = ""
        if args.live_anythingllm:
            api_key = os.environ.get(args.api_key_env) or ""
            if not api_key:
                raise RuntimeError(f"{args.api_key_env} is required when --live-anythingllm is set")
        for case in cases:
            entry = entries.get(case.fixture_id)
            if entry is None:
                raise RuntimeError(f"missing fixture in manifest: {case.fixture_id}")
            report["cases"].append(validate_gateway_case(args, entry, case))
            if args.live_anythingllm:
                report["cases"].append(validate_anythingllm_case(args, entry, case, api_key))
        categories = {case["category"] for case in report["cases"] if isinstance(case, dict)}
        report["summary"] = {
            "case_count": len(cases),
            "client_case_count": len(report["cases"]),
            "fixture_count": len({case["fixture_id"] for case in report["cases"] if isinstance(case, dict)}),
            "prompt_family_count": len({case["prompt_family"] for case in report["cases"] if isinstance(case, dict)}),
            "category_count": len(categories),
            "categories": sorted(categories),
            "clients": sorted({case["client"] for case in report["cases"] if isinstance(case, dict)}),
            "repo_layout_limitations": sorted(
                {
                    limitation
                    for case in report["cases"]
                    if isinstance(case, dict)
                    for limitation in case.get("repo_layout_limitations", [])
                }
            ),
            "error_count": 0,
        }
        report["parity_matrix"] = parity_matrix(report["cases"])
        if report["parity_matrix"]["status"] != "passed":
            raise RuntimeError("multi-fixture prompt parity matrix failed")
        report["status"] = "passed"
    except Exception as exc:
        report["errors"].append(str(exc))
        report["summary"] = {
            "case_count": len(cases),
            "client_case_count": len(report["cases"]),
            "error_count": len(report["errors"]),
        }
        write_json(output_path, report)
        print(f"MULTI REPO FIXTURE REPORT {output_path}")
        print("MULTI REPO FIXTURE FAIL " + str(exc))
        return 1
    write_json(output_path, report)
    print(f"MULTI REPO FIXTURE REPORT {output_path}")
    print("MULTI REPO FIXTURE PASS")
    print(json.dumps({"status": report["status"], "summary": report["summary"]}, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
