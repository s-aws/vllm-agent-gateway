#!/usr/bin/env python3
"""Validate execution-planning skills through the AnythingLLM workspace API."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from validate_execution_planning_skills import (  # noqa: E402
    FOLLOWUP_SKILL_NAMES,
    SKILL_NAMES,
    SKILLS_ROOT,
    assert_required_keys,
    feedback_adjustments_require_approval,
    file_digest,
    list_value,
    next_skill,
    normalize_repo_path,
    packet_preview_packets,
    plan_actions,
    relationship_queries_are_adapter_safe,
    stop_required,
    strip_thinking_and_extract_json,
    verification_commands_are_allowed,
)


DEFAULT_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_TIMEOUT_SECONDS = 300


def api_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def anythingllm_json_request(
    *,
    api_base_url: str,
    api_key: str | None,
    path: str,
    timeout_seconds: int,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers: dict[str, str] = {}
    data = None
    method = "GET"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(
        api_url(api_base_url, path),
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AnythingLLM {path} returned HTTP {exc.code}: {detail[:1000]}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"AnythingLLM response from {path} was not a JSON object.")
    return value


def text_response(value: dict[str, Any]) -> str:
    for key in ("textResponse", "response", "message"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return item
    choices = value.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
    raise RuntimeError("AnythingLLM chat response did not contain text content.")


def get_workspace_slugs(api_base_url: str, api_key: str, timeout_seconds: int) -> list[str]:
    body = anythingllm_json_request(
        api_base_url=api_base_url,
        api_key=api_key,
        path="/api/v1/workspaces",
        timeout_seconds=timeout_seconds,
    )
    workspaces = body.get("workspaces")
    if not isinstance(workspaces, list):
        raise RuntimeError("AnythingLLM workspaces response did not contain a workspace list.")
    slugs: list[str] = []
    for workspace in workspaces:
        if isinstance(workspace, dict) and isinstance(workspace.get("slug"), str):
            slugs.append(workspace["slug"])
    return slugs


def anythingllm_chat_skill(
    *,
    api_base_url: str,
    workspace_slug: str,
    api_key: str,
    skill_name: str,
    case_input: dict[str, Any],
    timeout_seconds: int,
    session_id: str | None = None,
) -> dict[str, Any]:
    skill_path = SKILLS_ROOT / skill_name / "SKILL.md"
    skill_text = skill_path.read_text(encoding="utf-8")
    prompt = (
        "This is a deterministic validation run. Ignore prior chat history and workspace documents unless they are "
        "explicitly included in the Case input JSON below.\n\n"
        "Use the following SKILL.md instructions exactly.\n\n"
        f"<skill>\n{skill_text}\n</skill>\n\n"
        "Case input JSON:\n"
        f"{json.dumps(case_input, ensure_ascii=True, indent=2)}\n\n"
        "Return exactly one JSON object matching the skill output shape. Do not include markdown, comments, "
        "explanations, tool calls, or chain-of-thought."
    )
    body = anythingllm_json_request(
        api_base_url=api_base_url,
        api_key=api_key,
        path=f"/api/v1/workspace/{workspace_slug}/chat",
        timeout_seconds=timeout_seconds,
        payload={
            "message": prompt,
            "mode": "chat",
            "sessionId": session_id or f"agentic-skill-validation-{skill_name}-{uuid.uuid4().hex}",
        },
    )
    return strip_thinking_and_extract_json(text_response(body))


def run_anythingllm_followup_skill_smokes(
    *,
    api_base_url: str,
    workspace_slug: str,
    api_key: str,
    timeout_seconds: int,
    target_root: Path,
    verbose: bool,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    if "codegraph-context-lookup" not in FOLLOWUP_SKILL_NAMES:
        return results

    value = anythingllm_chat_skill(
        api_base_url=api_base_url,
        workspace_slug=workspace_slug,
        api_key=api_key,
        skill_name="codegraph-context-lookup",
        case_input={
            "objective": "Map who calls reveal_order_slice before a single-path refactor.",
            "selected_entrypoint": {
                "path": "core/stealth_order_manager.py",
                "symbol": "reveal_order_slice",
                "confidence": "high",
            },
            "allowed_context_tools": ["structure_index", "git_grep", "read_file", "codegraph_context"],
            "target_root": str(target_root.resolve()),
        },
        timeout_seconds=timeout_seconds,
    )
    assert_required_keys("codegraph-context-lookup", value)
    if value.get("status") != "ready":
        raise AssertionError("codegraph-context-lookup did not produce a ready relationship lookup.")
    if not relationship_queries_are_adapter_safe(value):
        raise AssertionError("codegraph-context-lookup produced relationship queries that are not adapter-safe.")
    if not any(
        isinstance(query, dict)
        and query.get("kind") == "callers"
        and query.get("symbol") == "reveal_order_slice"
        for query in value.get("relationship_queries", [])
    ):
        raise AssertionError("codegraph-context-lookup did not request callers for reveal_order_slice.")
    print("ANYTHINGLLM SKILL PASS codegraph-context-lookup")
    if verbose:
        print("ANYTHINGLLM SKILL OUTPUT codegraph-context-lookup")
        print(json.dumps(value, ensure_ascii=True, indent=2))
    results["codegraph-context-lookup"] = {
        "status": value.get("status"),
        "relationship_query_count": len(value.get("relationship_queries") or []),
        "next_step": next_skill(value),
    }
    return results


def require_file_contains(path: Path, text: str, rel: str) -> None:
    if not path.exists():
        raise RuntimeError(f"frozen target repo is missing {rel}")
    if text not in path.read_text(encoding="utf-8"):
        raise RuntimeError(f"frozen target repo text changed: {rel}")


def run_anythingllm_frozen_repo_chain(
    *,
    api_base_url: str,
    workspace_slug: str,
    api_key: str,
    timeout_seconds: int,
    target_root: Path,
    verbose: bool,
) -> dict[str, Any]:
    from vllm_agent_gateway.implementation.workflow import (  # noqa: PLC0415
        ImplementationWorkflowInvocationRequest,
        invoke_implementation_workflow,
        normalize_verification_commands,
    )
    from vllm_agent_gateway.invocation import WorkflowStatus  # noqa: PLC0415

    target_root = target_root.resolve()
    if not target_root.exists() or not target_root.is_dir():
        raise RuntimeError(f"frozen target repo does not exist: {target_root}")

    invariant_rel = "docs/agents/INVARIANTS.md"
    manager_rel = "core/stealth_order_manager.py"
    unit_test_rel = "tests/unit/test_order_id_and_followup_rules.py"
    regression_test_rel = "tests/regression/test_order_id_regression.py"
    required_files = [invariant_rel, manager_rel, unit_test_rel, regression_test_rel]
    selected_files = {rel: target_root / rel for rel in required_files}
    old_text = (
        "- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n"
        "  maps, dashboard references, follow-up claims, fill ledger ownership, and DB\n"
        "  local rows."
    )
    new_text = (
        "- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n"
        "  maps, dashboard references, follow-up claims, fill ledger ownership, DB\n"
        "  local rows, and stealth manager placed-order index keys."
    )
    require_file_contains(selected_files[invariant_rel], old_text, invariant_rel)
    for rel, path in selected_files.items():
        if not path.exists():
            raise RuntimeError(f"frozen target repo is missing {rel}")

    before_hashes = {rel: file_digest(path) for rel, path in selected_files.items()}
    user_request = (
        "Prepare implementation packet candidates for an approved frozen-repo documentation clarification "
        "that client_order_id owns internal lookup paths, including StealthOrderManager placed-order index keys. "
        "Use draft mode only and do not mutate the frozen repository."
    )
    bounded_context = [
        {
            "source": "read_file",
            "ref": f"{invariant_rel}:11",
            "text": "The invariant says client_order_id owns internal tracking and order_id is exchange-facing only.",
        },
        {
            "source": "read_file",
            "ref": f"{manager_rel}:20",
            "text": "StealthOrderManager treats stealth_order_id as client_order_id for internal lookup behavior.",
        },
        {
            "source": "git_grep",
            "ref": f"{unit_test_rel}:8",
            "text": "Unit tests assert placed-order lookup uses the client_order_id index.",
        },
        {
            "source": "git_grep",
            "ref": f"{regression_test_rel}:58",
            "text": "Regression tests assert filled-order lookup uses client_order_id instead of exchange order_id.",
        },
    ]

    outputs: dict[str, dict[str, Any]] = {}
    expected_skill_chain = list(SKILL_NAMES)

    def chat(skill_name: str, case_input: dict[str, Any]) -> dict[str, Any]:
        value = anythingllm_chat_skill(
            api_base_url=api_base_url,
            workspace_slug=workspace_slug,
            api_key=api_key,
            skill_name=skill_name,
            case_input=case_input,
            timeout_seconds=timeout_seconds,
        )
        assert_required_keys(skill_name, value)
        outputs[skill_name] = value
        print(f"ANYTHINGLLM SKILL PASS {skill_name}")
        if verbose:
            print("ANYTHINGLLM SKILL OUTPUT " + skill_name)
            print(json.dumps(value, ensure_ascii=True, indent=2))
        return value

    triage = chat(
        "request-triage",
        {
            "user_request": user_request,
            "target_root": str(target_root),
            "requested_mode": "draft",
        },
    )
    if next_skill(triage) != "scope-and-assumptions":
        raise AssertionError("request-triage did not route to scope-and-assumptions.")
    if triage.get("requires_user_approval_before_write") is not True:
        raise AssertionError("request-triage did not preserve approval gating for packet creation.")

    scope = chat(
        "scope-and-assumptions",
        {
            "request_type": triage.get("request_type"),
            "user_request": user_request,
            "target_root": str(target_root),
            "known_target": invariant_rel,
            "known_bounded_context": bounded_context,
            "write_policy": "User approved packet design only. Apply mode and repo mutation are not approved.",
        },
    )
    if next_skill(scope) == "none":
        raise AssertionError("scope-and-assumptions blocked the frozen repo validation chain.")

    entrypoint = chat(
        "entrypoint-finder",
        {
            "request_type": triage.get("request_type"),
            "user_request": user_request,
            "scope": scope.get("scope"),
            "goal": scope.get("goal"),
            "bounded_context": bounded_context,
            "known_target": invariant_rel,
        },
    )
    if stop_required(entrypoint):
        raise AssertionError(f"entrypoint-finder stopped: {json.dumps(entrypoint.get('stop'), ensure_ascii=True)}")
    selected = entrypoint.get("selected_entrypoint")
    if not isinstance(selected, dict) or selected.get("confidence") not in {"medium", "high"}:
        raise AssertionError("entrypoint-finder did not select a usable entrypoint.")

    context_plan = chat(
        "context-plan-builder",
        {
            "objective": user_request,
            "selected_entrypoint": selected,
            "followup_context_needed": entrypoint.get("followup_context_needed"),
            "allowed_tools": ["structure_index", "git_grep", "read_file", "manual"],
            "target_root": str(target_root),
        },
    )
    if stop_required(context_plan):
        raise AssertionError(f"context-plan-builder stopped: {json.dumps(context_plan.get('stop'), ensure_ascii=True)}")
    if not list_value(context_plan, "context_requests"):
        raise AssertionError("context-plan-builder did not request bounded context.")
    budget = context_plan.get("context_budget")
    if not isinstance(budget, dict) or budget.get("allow_broad_scan") is not False:
        raise AssertionError("context-plan-builder did not preserve bounded context policy.")

    context_results = [
        {
            "id": "CTX-FROZEN-INVARIANT-0001",
            "purpose": "docs",
            "summary": "The public invariant requires client_order_id for internal tracking and order_id only for exchange-facing operations.",
            "source_refs": [f"{invariant_rel}:11", f"{invariant_rel}:16"],
            "exact_text": old_text,
        },
        {
            "id": "CTX-FROZEN-MANAGER-0001",
            "purpose": "entrypoint",
            "summary": "StealthOrderManager documents that stealth_order_id is the client_order_id and internal lookups should key off client_order_id.",
            "source_refs": [f"{manager_rel}:20", f"{manager_rel}:23", f"{manager_rel}:966"],
        },
        {
            "id": "CTX-FROZEN-TESTS-0001",
            "purpose": "tests",
            "summary": "Unit and regression tests assert client_order_id lookup behavior and reject exchange order_id ownership.",
            "source_refs": [
                f"{unit_test_rel}:8",
                f"{unit_test_rel}:18",
                f"{regression_test_rel}:58",
                f"{regression_test_rel}:86",
            ],
        },
    ]
    impact = chat(
        "impact-map-builder",
        {
            "request_type": "documentation",
            "objective": user_request,
            "entrypoint": selected,
            "context_plan": context_plan,
            "context_results": context_results,
        },
    )
    if stop_required(impact):
        raise AssertionError(f"impact-map-builder stopped: {json.dumps(impact.get('stop'), ensure_ascii=True)}")
    impact["related_tests"] = [
        {
            "path": unit_test_rel,
            "test_name": "test_find_stealth_order_by_placed_order_id_uses_client_order_id_index",
            "coverage_for": [manager_rel, invariant_rel],
            "status": "existing",
            "evidence_refs": [f"{unit_test_rel}:8"],
        },
        {
            "path": regression_test_rel,
            "test_name": "test_filled_order_lookup_uses_client_order_id_not_exchange_order_id",
            "coverage_for": [manager_rel, invariant_rel],
            "status": "existing",
            "evidence_refs": [f"{regression_test_rel}:58"],
        },
    ]

    plan = chat(
        "execution-plan-writer",
        {
            "request_type": "documentation",
            "objective": user_request,
            "entrypoint": selected,
            "impact_map": impact,
            "user_approvals": ["User approves packet design only. User does not approve apply mode."],
            "operation_details": {"kind": "replace_text", "path": invariant_rel, "old": old_text, "new": new_text},
        },
    )
    if plan.get("plan_mode") != "implementation_prep":
        raise AssertionError(f"execution-plan-writer produced plan_mode={plan.get('plan_mode')!r}")
    design_steps = [step for step in list_value(plan, "steps") if isinstance(step, dict) and step.get("action") == "design_packet"]
    if not design_steps:
        raise AssertionError("execution-plan-writer did not emit a design_packet step.")
    approved_step_id = str(design_steps[0].get("id"))

    packet_design = chat(
        "implementation-packet-designer",
        {
            "execution_plan": plan,
            "impact_map": impact,
            "approved_step_ids": [approved_step_id],
            "approval_refs": [f"user:approved {approved_step_id} for packet design only"],
            "requested_mode": "draft",
            "operation_details": [
                {
                    "source_step_id": approved_step_id,
                    "kind": "replace_text",
                    "path": invariant_rel,
                    "old": old_text,
                    "new": new_text,
                }
            ],
        },
    )
    if stop_required(packet_design):
        raise AssertionError(f"implementation-packet-designer stopped: {json.dumps(packet_design.get('stop'), ensure_ascii=True)}")
    preview = packet_design.get("packet_file_preview")
    packets = packet_preview_packets(packet_design)
    if not isinstance(preview, dict) or not packets:
        raise AssertionError("implementation-packet-designer did not produce packet_file_preview.packets.")
    for packet in packets:
        if not isinstance(packet, dict):
            raise AssertionError("packet preview contains a non-object packet.")
        operation = packet.get("operation")
        if not isinstance(operation, dict):
            raise AssertionError("packet preview packet is missing operation.")
        if operation.get("kind") != "replace_text":
            raise AssertionError(f"packet preview used unsupported operation {operation.get('kind')!r}.")
        if normalize_repo_path(str(operation.get("path") or "")) != invariant_rel:
            raise AssertionError(f"packet preview targeted {operation.get('path')!r}, expected {invariant_rel!r}.")

    verification_plan = chat(
        "verification-planner",
        {
            "execution_plan": plan,
            "packet_design": packet_design,
            "impact_map": impact,
        },
    )
    if stop_required(verification_plan):
        raise AssertionError(f"verification-planner stopped: {json.dumps(verification_plan.get('stop'), ensure_ascii=True)}")
    if not verification_commands_are_allowed(verification_plan):
        raise AssertionError("verification-planner emitted a command outside pytest policy.")
    normalize_verification_commands(verification_plan.get("verification_commands"))

    with tempfile.TemporaryDirectory(prefix="agentic-anythingllm-frozen-repo-") as temp_dir:
        packet_file = Path(temp_dir) / "packet-preview.json"
        packet_file.write_text(json.dumps(preview, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        result = invoke_implementation_workflow(
            ImplementationWorkflowInvocationRequest(
                target_root=target_root,
                output_dir=Path(temp_dir) / "out",
                mode="draft",
                packet_file=packet_file,
                no_structure_index=True,
            )
        )
    if result.status != WorkflowStatus.COMPLETED:
        raise AssertionError(f"implementation workflow status was {result.status.value!r}.")
    after_hashes = {rel: file_digest(path) for rel, path in selected_files.items()}
    changed = [rel for rel in required_files if before_hashes[rel] != after_hashes[rel]]
    if changed:
        raise AssertionError(f"frozen repo files mutated in draft mode: {', '.join(changed)}")

    feedback = chat(
        "feedback-capture",
        {
            "workflow_id": "anythingllm-frozen-coinbase-full-chain",
            "run_id": str(target_root),
            "result_summary": {
                "surface": "AnythingLLM workspace API",
                "workspace_slug": workspace_slug,
                "target_root": str(target_root),
                "target_files": required_files,
                "skill_chain": expected_skill_chain,
                "packet_preview_workflow_status": result.status.value,
                "repo_mutated": False,
                "verification_commands": [
                    item.get("command")
                    for item in list_value(verification_plan, "verification_commands")
                    if isinstance(item, dict)
                ],
            },
            "tester_feedback": (
                "The AnythingLLM full chain is useful because the founder harness API completed all nine skills "
                "against the frozen Coinbase repository, produced a draft packet preview, and preserved selected "
                "file hashes. The remaining product gap is a controller-owned execution_planning.plan workflow "
                "that gathers context and writes artifacts automatically."
            ),
        },
    )
    if not list_value(feedback, "useful"):
        raise AssertionError("feedback-capture did not record useful AnythingLLM evidence.")
    if not feedback_adjustments_require_approval(feedback):
        raise AssertionError("feedback-capture produced an adjustment without write approval gating.")

    return {
        "workspace_slug": workspace_slug,
        "target_root": str(target_root),
        "target_files": required_files,
        "skill_chain": list(outputs),
        "selected_entrypoint": selected,
        "plan_mode": plan.get("plan_mode"),
        "plan_actions": plan_actions(plan),
        "approved_step_ids": [approved_step_id],
        "packet_candidates": len(packet_design.get("packet_candidates") or []),
        "packet_file_preview_packets": len(packets),
        "verification_commands": [
            item.get("command")
            for item in list_value(verification_plan, "verification_commands")
            if isinstance(item, dict)
        ],
        "feedback_useful": len(feedback.get("useful") or []),
        "feedback_missing": len(feedback.get("missing") or []),
        "packet_preview_workflow_status": result.status.value,
        "repo_mutated": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate execution-planning skills through AnythingLLM.")
    parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--target-root", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--skip-followup-smokes", action="store_true")
    parser.add_argument("--skip-chain", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        print(f"ERROR missing {args.api_key_env}; pass it into Bash with WSLENV={args.api_key_env}.")
        return 1

    try:
        ping = anythingllm_json_request(
            api_base_url=args.api_base_url,
            api_key=None,
            path="/api/ping",
            timeout_seconds=args.timeout_seconds,
        )
        print("ANYTHINGLLM PING " + json.dumps(ping, ensure_ascii=True, sort_keys=True))
        slugs = get_workspace_slugs(args.api_base_url, api_key, args.timeout_seconds)
        print("ANYTHINGLLM WORKSPACES " + json.dumps(slugs, ensure_ascii=True))
        if args.workspace not in slugs:
            raise RuntimeError(f"workspace {args.workspace!r} was not found.")
        followup_skill_smokes = (
            {}
            if args.skip_followup_smokes
            else run_anythingllm_followup_skill_smokes(
                api_base_url=args.api_base_url,
                workspace_slug=args.workspace,
                api_key=api_key,
                timeout_seconds=args.timeout_seconds,
                target_root=Path(args.target_root),
                verbose=args.verbose,
            )
        )
        result: dict[str, Any] | None = None
        if not args.skip_chain:
            result = run_anythingllm_frozen_repo_chain(
                api_base_url=args.api_base_url,
                workspace_slug=args.workspace,
                api_key=api_key,
                timeout_seconds=args.timeout_seconds,
                target_root=Path(args.target_root),
                verbose=args.verbose,
            )
            print("ANYTHINGLLM CHAIN PASS frozen-real-repo-full")
            print(json.dumps(result, ensure_ascii=True, indent=2))
        print(
            "SUMMARY "
            + json.dumps(
                {
                    "anythingllm_chain_passed": None if args.skip_chain else True,
                    "followup_skill_smokes": followup_skill_smokes,
                    "workspace": args.workspace,
                    "target_root": str(Path(args.target_root).resolve()),
                    "repo_mutated": False,
                    "failure_count": 0,
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ANYTHINGLLM CHAIN FAIL {type(exc).__name__}: {exc}")
        print(
            "SUMMARY "
            + json.dumps(
                {
                    "anythingllm_chain_passed": False,
                    "workspace": args.workspace,
                    "target_root": str(Path(args.target_root).resolve()),
                    "failure_count": 1,
                    "failures": [f"{type(exc).__name__}: {exc}"],
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
