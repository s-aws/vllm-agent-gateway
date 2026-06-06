#!/usr/bin/env python3
"""Validate workflow generalization on a disposable non-Coinbase fixture."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.fixtures.manager import (
    FixtureEntry,
    cleanup_run as managed_cleanup_run,
    copy_fixture as managed_copy_fixture,
    hash_tree as managed_hash_tree,
    sha256_file as managed_sha256_file,
)


DEFAULT_CONFIG_ROOT = "/mnt/c/agentic_agents"
DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_CONTROLLER_ARTIFACT_ROOT = "/mnt/c/private_agentic_agents/runtime-state/controller-artifacts"
DEFAULT_TIMEOUT_SECONDS = 900
TEMPLATE_RELATIVE_PATH = Path("tests") / "fixtures" / "generalization" / "python_service_fixture"
DEFAULT_FIXTURE_ROOT = Path("runtime-state") / "generalization-fixtures"
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
class GeneralizationCase:
    case_id: str
    category: str
    prompt_template: str
    expected_workflow: str
    expected_skill_id: str
    expected_artifact_key: str
    text_markers: tuple[str, ...]

    def prompt(self, target_root: str) -> str:
        return self.prompt_template.format(target_root=target_root)


GENERALIZATION_CASES: tuple[GeneralizationCase, ...] = (
    GeneralizationCase(
        case_id="G01",
        category="l1_explain_code",
        prompt_template=(
            "In {target_root}, explain resolve_order_status in service/orders.py. Read only. "
            "Include inputs, return value, side effects, and tests."
        ),
        expected_workflow="code_investigation.plan",
        expected_skill_id="code-explanation-summarizer",
        expected_artifact_key="downstream_code_explanation",
        text_markers=("Answer:", "resolve_order_status", "Inputs:", "Outputs:", "Side effects:", "Related tests:"),
    ),
    GeneralizationCase(
        case_id="G02",
        category="batch_d_handler_branch_trace",
        prompt_template=(
            "In {target_root}, follow handler branch trace for handle_create_order as a request flow through "
            "the downstream snapshot function. Read only. Return flow steps, participating files, evidence refs, "
            "related tests, risks, gaps, and verification."
        ),
        expected_workflow="code_investigation.plan",
        expected_skill_id="handler-branch-tracer",
        expected_artifact_key="downstream_request_flow_map",
        text_markers=("Answer:", "Target flow:", "handle_create_order", "Flow steps:", "Participating files:", "Source mutation: false"),
    ),
    GeneralizationCase(
        case_id="G03",
        category="batch_d_table_schema_only",
        prompt_template=(
            "In {target_root}, find the orders table schema only. Read only. Return schema field names, "
            "model files, and source refs. Exclude runtime fields."
        ),
        expected_workflow="code_investigation.plan",
        expected_skill_id="table-schema-isolator",
        expected_artifact_key="downstream_data_model_lookup",
        text_markers=("Answer:", "Target model/schema:", "orders", "Fields:", "Model files:", "Source refs:", "Source mutation: false"),
    ),
    GeneralizationCase(
        case_id="G04",
        category="batch_d_runtime_entrypoint",
        prompt_template=(
            "In {target_root}, locate the runtime entrypoint for the order worker, not the request handler. "
            "Read only. Return command, source refs, and exclusions."
        ),
        expected_workflow="code_investigation.plan",
        expected_skill_id="runtime-entrypoint-disambiguator",
        expected_artifact_key="downstream_cli_entrypoint_lookup",
        text_markers=("Answer:", "Target entrypoint:", "Entrypoints:", "Source refs:", "Source mutation: false"),
    ),
    GeneralizationCase(
        case_id="G05",
        category="batch_d_change_boundary",
        prompt_template=(
            "In {target_root}, identify files to touch and files not to touch for the minimal safe change "
            "surface and change boundary for order status behavior. Read only and stop before implementation. "
            "Return risks, gaps, and verification commands."
        ),
        expected_workflow="code_investigation.plan",
        expected_skill_id="change-boundary-summarizer",
        expected_artifact_key="downstream_change_surface_summary",
        text_markers=("Answer:", "Change surface files:", "Risk level:", "Implementation status: not_ready_without_approval", "Verification:", "Source mutation: false"),
    ),
    GeneralizationCase(
        case_id="G06",
        category="l2_test_selection",
        prompt_template=(
            "In {target_root}, choose the smallest, medium, and broad validation commands for "
            "resolve_order_status. Read only. Explain why each command matters and what risk remains."
        ),
        expected_workflow="code_investigation.plan",
        expected_skill_id="test-selection-rationale",
        expected_artifact_key="downstream_test_selection_plan",
        text_markers=("Answer:", "Smallest command:", "Medium command:", "Broad command:", "Rationale:"),
    ),
)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return value


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
    for key in ("textResponse", "response", "message", "text"):
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


def sha256_file(path: Path) -> str:
    return managed_sha256_file(path)


def hash_tree(root: Path) -> dict[str, str]:
    return managed_hash_tree(root)


def copy_disposable_fixture(template_root: Path, fixture_root: Path, *, run_id: str) -> Path:
    watched_paths = tuple(sorted(hash_tree(template_root)))
    entry = FixtureEntry(
        fixture_id=template_root.name,
        source_path=template_root.resolve(),
        category="generalization",
        protected=True,
        disposable_only=True,
        watched_paths=watched_paths,
        description="Generalization validator disposable fixture.",
    )
    result = managed_copy_fixture(entry, fixture_root, run_id=run_id)
    return Path(result["copy_root"])


def remove_fixture(path: Path) -> bool:
    result = managed_cleanup_run(path.parent, run_id=path.name)
    return bool(result["removed"])


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


def validate_route_and_run_state(
    route_decision_path: Path,
    *,
    case: GeneralizationCase,
    expected_target_root: str,
    label: str,
) -> dict[str, Any]:
    decision = read_json(route_decision_path)
    if decision.get("selected_workflow") != case.expected_workflow:
        raise RuntimeError(f"{label} selected {decision.get('selected_workflow')}, expected {case.expected_workflow}")
    selected = decision.get("selected_skills")
    if not isinstance(selected, list) or case.expected_skill_id not in selected:
        raise RuntimeError(f"{label} did not select {case.expected_skill_id}: {selected}")
    run_state_path = route_decision_path.parent / "run-state.json"
    run_state = read_json(run_state_path)
    summary = run_state.get("summary") if isinstance(run_state.get("summary"), dict) else {}
    artifacts = run_state.get("artifacts") if isinstance(run_state.get("artifacts"), dict) else {}
    if summary.get("target_root") != expected_target_root:
        raise RuntimeError(f"{label} target_root {summary.get('target_root')} != {expected_target_root}")
    if summary.get("source_changed") is not False:
        raise RuntimeError(f"{label} reported source_changed={summary.get('source_changed')}")
    if case.expected_artifact_key not in artifacts:
        raise RuntimeError(f"{label} missing expected artifact {case.expected_artifact_key}")
    return {
        "run_id": run_state.get("run_id"),
        "route_decision": str(route_decision_path),
        "run_state": str(run_state_path),
        "selected_skills": selected,
        "artifact_path": artifacts[case.expected_artifact_key],
        "downstream_run_id": summary.get("downstream_run_id"),
    }


def run_gateway_case(args: argparse.Namespace, case: GeneralizationCase, target_root: Path) -> dict[str, Any]:
    status, body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={"model": "agentic-workflow-router", "messages": [{"role": "user", "content": case.prompt(str(target_root))}]},
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"gateway {case.case_id} returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    require_markers(text, (*case.text_markers, case.expected_skill_id, case.expected_artifact_key), label=f"gateway {case.case_id}")
    route = validate_route_and_run_state(
        route_decision_path_from_gateway(body),
        case=case,
        expected_target_root=str(target_root),
        label=f"gateway {case.case_id}",
    )
    return {"client": "gateway", "case_id": case.case_id, "category": case.category, **route}


def run_anythingllm_case(args: argparse.Namespace, case: GeneralizationCase, target_root: Path, api_key: str) -> dict[str, Any]:
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload={
            "message": case.prompt(str(target_root)),
            "mode": "chat",
            "sessionId": f"phase66-generalization-{case.case_id.lower()}-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"AnythingLLM {case.case_id} returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    require_markers(text, (*case.text_markers, case.expected_skill_id, case.expected_artifact_key), label=f"AnythingLLM {case.case_id}")
    route = validate_route_and_run_state(
        route_decision_path_from_anythingllm(text, Path(args.controller_artifact_root)),
        case=case,
        expected_target_root=str(target_root),
        label=f"AnythingLLM {case.case_id}",
    )
    return {"client": "anythingllm", "case_id": case.case_id, "category": case.category, **route}


def anythingllm_preflight(args: argparse.Namespace, api_key: str) -> dict[str, Any]:
    ping_status, ping_body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/ping",
        timeout_seconds=min(30, args.timeout_seconds),
        method="GET",
    )
    workspace_status, workspace_body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspaces",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=min(30, args.timeout_seconds),
        method="GET",
    )
    workspaces = workspace_body.get("workspaces") if isinstance(workspace_body, dict) else []
    slugs = [item.get("slug") for item in workspaces if isinstance(item, dict)]
    status = "passed" if ping_status == 200 and workspace_status == 200 and args.workspace in slugs else "failed"
    return {
        "status": status,
        "ping_status": ping_status,
        "workspace_status": workspace_status,
        "workspace": args.workspace,
        "workspace_found": args.workspace in slugs,
        "ping": ping_body,
    }


def default_output_path(config_root: Path) -> Path:
    return config_root / "runtime-state" / "generalization-fixtures" / f"phase66-generalization-live-{utc_timestamp()}.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=DEFAULT_CONFIG_ROOT)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--controller-artifact-root", default=DEFAULT_CONTROLLER_ARTIFACT_ROOT)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--fixture-root", default=None)
    parser.add_argument("--skip-anythingllm", action="store_true")
    parser.add_argument("--skip-port-health", action="store_true")
    parser.add_argument("--keep-fixture", action="store_true")
    parser.add_argument("--list-cases", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.list_cases:
        print(json.dumps([case.__dict__ for case in GENERALIZATION_CASES], ensure_ascii=True, indent=2, sort_keys=True))
        return 0
    config_root = Path(args.config_root).resolve()
    template_root = config_root / TEMPLATE_RELATIVE_PATH
    fixture_parent = Path(args.fixture_root).resolve() if args.fixture_root else config_root / DEFAULT_FIXTURE_ROOT
    run_id = f"phase66-generalization-{utc_timestamp()}"
    output_path = Path(args.output_path).resolve() if args.output_path else default_output_path(config_root)
    api_key = os.environ.get(args.api_key_env) or ""
    if not args.skip_anythingllm and not api_key:
        print(f"GENERALIZATION LIVE FAIL: {args.api_key_env} is required unless --skip-anythingllm is set")
        return 1

    disposable_root: Path | None = None
    report: dict[str, Any] = {
        "kind": "phase66_generalization_fixture_live_report",
        "schema_version": 1,
        "status": "failed",
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "config_root": str(config_root),
        "template_root": str(template_root),
        "disposable_root": "",
        "case_count": len(GENERALIZATION_CASES),
        "fixture_policy": {
            "template_mutation_allowed": False,
            "disposable_copy_mutation_allowed": False,
            "cleanup": "delete_disposable_copy_after_validation_unless_keep_fixture_is_set",
        },
        "port_health": [],
        "anythingllm_preflight": {},
        "template_hashes_before": {},
        "template_hashes_after": {},
        "fixture_hashes_before": {},
        "fixture_hashes_after": {},
        "gateway": [],
        "anythingllm": [],
        "cleanup": {},
        "errors": [],
    }
    try:
        if not template_root.is_dir():
            raise RuntimeError(f"missing fixture template: {template_root}")
        report["template_hashes_before"] = hash_tree(template_root)
        disposable_root = copy_disposable_fixture(template_root, fixture_parent, run_id=run_id)
        report["disposable_root"] = str(disposable_root)
        report["fixture_hashes_before"] = hash_tree(disposable_root)
        if not args.skip_port_health:
            report["port_health"] = validate_port_health(args.timeout_seconds)
        if not args.skip_anythingllm:
            report["anythingllm_preflight"] = anythingllm_preflight(args, api_key)
            if report["anythingllm_preflight"].get("status") != "passed":
                raise RuntimeError("AnythingLLM preflight failed")
        for case in GENERALIZATION_CASES:
            gateway_result = run_gateway_case(args, case, disposable_root)
            report["gateway"].append(gateway_result)
            print(f"GENERALIZATION GATEWAY PASS case={case.case_id} run_id={gateway_result['run_id']}")
        if not args.skip_anythingllm:
            for case in GENERALIZATION_CASES:
                anythingllm_result = run_anythingllm_case(args, case, disposable_root, api_key)
                report["anythingllm"].append(anythingllm_result)
                print(f"GENERALIZATION ANYTHINGLLM PASS case={case.case_id} run_id={anythingllm_result['run_id']}")
        report["fixture_hashes_after"] = hash_tree(disposable_root)
        report["template_hashes_after"] = hash_tree(template_root)
        if report["fixture_hashes_after"] != report["fixture_hashes_before"]:
            raise RuntimeError("disposable fixture changed during read-only validation")
        if report["template_hashes_after"] != report["template_hashes_before"]:
            raise RuntimeError("fixture template changed during validation")
        report["status"] = "passed"
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        if disposable_root is not None:
            if args.keep_fixture:
                report["cleanup"] = {"status": "kept", "path": str(disposable_root)}
            else:
                report["cleanup"] = {"status": "removed" if remove_fixture(disposable_root.parent) else "failed", "path": str(disposable_root.parent)}
                if report["cleanup"]["status"] != "removed":
                    report["status"] = "failed"
                    report["errors"].append("disposable fixture cleanup failed")
    write_json(output_path, report)
    print(f"GENERALIZATION LIVE REPORT {output_path}")
    print(
        "GENERALIZATION LIVE SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "case_count": report["case_count"],
                "gateway_count": len(report["gateway"]),
                "anythingllm_count": len(report["anythingllm"]),
                "cleanup": report["cleanup"].get("status"),
                "error_count": len(report["errors"]),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        print("GENERALIZATION LIVE FAILURES " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("GENERALIZATION LIVE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
