#!/usr/bin/env python3
"""Validate the full L1 workflow-router prompt suite through gateway and AnythingLLM."""

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
from pathlib import Path
from typing import Any


DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_TARGET_ROOTS = [
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
]
WATCHED_RELATIVE_PATHS = [
    "README.md",
    "agent.md",
    "configuration.py",
    "core/stealth_order_manager.py",
    "dashboard_server.py",
    "database/order.py",
    "main.py",
    "docs/agents/INVARIANTS.md",
    "business/lot_config.py",
    "core/orderbook.py",
    "tests/unit/test_order_id_and_followup_rules.py",
    "tests/unit/test_orderbook_v2.py",
    "tests/test_lot_tracking_integration.py",
]


@dataclass(frozen=True)
class L1Case:
    case_id: str
    name: str
    selected_workflow: str
    downstream_workflow: str
    artifact_keys: tuple[str, ...]
    markers: tuple[str, ...]
    prompt_template: str

    def prompt(self, target_root: str) -> str:
        return self.prompt_template.format(target_root=target_root)


L1_CASES: tuple[L1Case, ...] = (
    L1Case(
        case_id="L1-001",
        name="Find Where Behavior Starts",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_investigation_plan",),
        markers=(
            "Answer:",
            "Beginning point:",
            "Related tests:",
            "Recommended commands:",
            "python -m pytest",
        ),
        prompt_template=(
            "In {target_root}, find where the placed_order_id stealth lookup begins. "
            "Read only. Return the entrypoint, evidence files, related tests, and confidence."
        ),
    ),
    L1Case(
        case_id="L1-002",
        name="Explain A Function Or File",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_code_explanation",),
        markers=(
            "Answer:",
            "StealthOrderManager.find_stealth_order_by_placed_order_id",
            "Inputs:",
            "placed_order_id",
            "Outputs:",
            "Side effects:",
            "Related tests:",
        ),
        prompt_template=(
            "In {target_root}, explain what find_stealth_order_by_placed_order_id does "
            "in core/stealth_order_manager.py. Read only. Include key inputs, outputs, "
            "side effects, and tests."
        ),
    ),
    L1Case(
        case_id="L1-003",
        name="Find Related Tests",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_investigation_plan",),
        markers=(
            "Answer:",
            "Related tests:",
            "Recommended commands:",
            "python -m pytest",
        ),
        prompt_template=(
            "In {target_root}, find tests related to placed_order_id stealth lookup. "
            "Read only. Return test files, matching terms, and recommended test commands."
        ),
    ),
    L1Case(
        case_id="L1-004",
        name="Locate Configuration Or Environment Setting",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_configuration_lookup",),
        markers=(
            "Answer:",
            "Target: COINBASE_API_KEY",
            "References:",
            "Runtime effect:",
            "configuration.py",
        ),
        prompt_template=(
            "In {target_root}, find where COINBASE_API_KEY environment variable is defined or used. "
            "Read only. Return files, references, and likely runtime effect."
        ),
    ),
    L1Case(
        case_id="L1-005",
        name="Summarize Test Failure From Pasted Output",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_test_failure_summary",),
        markers=(
            "Answer:",
            "Failed tests:",
            "tests/unit/test_order_id_and_followup_rules.py",
            "Primary error: AssertionError",
            "Likely cause:",
            "Next steps:",
        ),
        prompt_template=(
            "In {target_root}, summarize this pasted test failure. Do not edit files. "
            "Return what failed, likely cause, and next bounded inspection step.\n"
            "FAILED tests/unit/test_order_id_and_followup_rules.py::"
            "test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - "
            "AssertionError: expected client_order_id index\n"
            "E   AssertionError: expected client_order_id index"
        ),
    ),
    L1Case(
        case_id="L1-006",
        name="Check Whether Behavior Already Exists",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_behavior_existence",),
        markers=(
            "Answer:",
            "Result: yes",
            "Evidence files:",
            "core/",
        ),
        prompt_template=(
            "In {target_root}, check whether placed_order_id stealth lookup already exists. "
            "Read only. Return evidence for yes, no, or unknown."
        ),
    ),
    L1Case(
        case_id="L1-007",
        name="Find Callers Or Usages",
        selected_workflow="code_context.lookup",
        downstream_workflow="code_context.lookup",
        artifact_keys=("downstream_usage_summary",),
        markers=(
            "Answer:",
            "Target: find_stealth_order_by_placed_order_id",
            "Usage count:",
            "core/",
        ),
        prompt_template=(
            "In {target_root}, find callers/usages of find_stealth_order_by_placed_order_id. "
            "Read only. Group by file and explain each usage briefly."
        ),
    ),
    L1Case(
        case_id="L1-008",
        name="Produce A Safe Test Command",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_investigation_plan",),
        markers=(
            "Answer:",
            "Recommended commands:",
            "python -m pytest",
            "tests/",
        ),
        prompt_template=(
            "In {target_root}, recommend the smallest test command for placed_order_id stealth lookup. "
            "Read only. Explain why that command is relevant."
        ),
    ),
    L1Case(
        case_id="L1-009",
        name="Add Or Update A Small Unit Test",
        selected_workflow="execution_planning.plan",
        downstream_workflow="execution_planning.plan",
        artifact_keys=("small_unit_test_proposal", "downstream_implementation_workflow_report"),
        markers=(
            "Draft proposal:",
            "small_unit_test_proposal",
            "tests/",
            "append_text",
            "Verification:",
            "python -m pytest",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, add a small unit test for "
            "sync_exchange_order_id_for_placed_order setting exchange_order_id when it is missing. "
            "Draft only. Show the proposed test file and verification command before applying."
        ),
    ),
    L1Case(
        case_id="L1-010",
        name="Make A Small Text Or Documentation Edit",
        selected_workflow="execution_planning.plan",
        downstream_workflow="execution_planning.plan",
        artifact_keys=("small_text_edit_proposal", "downstream_implementation_workflow_report"),
        markers=(
            "Draft proposal:",
            "small_text_edit_proposal",
            "docs/agents/INVARIANTS.md",
            "replace_text",
            "Verification:",
            "git diff -- docs/agents/INVARIANTS.md",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, draft a small documentation edit to docs/agents/INVARIANTS.md. "
            "After \"- Use one code path per behavior.\" add "
            "\"- L1-010 draft proof: route small documentation edits through packet dry-run.\". "
            "Do not mutate files. Return the exact file, proposed change, safety checks, and verification command."
        ),
    ),
    L1Case(
        case_id="L1-011",
        name="Fix A Simple Failing Test",
        selected_workflow="execution_planning.plan",
        downstream_workflow="execution_planning.plan",
        artifact_keys=("simple_test_fix_proposal", "downstream_implementation_workflow_report"),
        markers=(
            "Draft proposal:",
            "simple_test_fix_proposal",
            "core/stealth_order_manager.py",
            "replace_text",
            "client_order_id",
            "Verification:",
            "python -m pytest",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, inspect this failing test and propose the smallest fix. "
            "Draft only; do not apply until approved.\n"
            "FAILED tests/unit/test_order_id_and_followup_rules.py::"
            "test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - "
            "AssertionError: expected find_stealth_order_by_placed_order_id docstring to mention client_order_id"
        ),
    ),
    L1Case(
        case_id="D1-004",
        name="Draft Small Config Default Test",
        selected_workflow="execution_planning.plan",
        downstream_workflow="execution_planning.plan",
        artifact_keys=("small_unit_test_proposal", "downstream_implementation_workflow_report"),
        markers=(
            "Draft proposal:",
            "small_unit_test_proposal",
            "tests/test_lot_tracking_integration.py",
            "append_text",
            "test_default_profit_margin_pct_config_default",
            "Verification:",
            "python -m pytest tests/test_lot_tracking_integration.py",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, draft a small unit test in tests/test_lot_tracking_integration.py "
            "proving config default DEFAULT_PROFIT_MARGIN_PCT in business/lot_config.py defaults to 0.5. "
            "Draft only. Show the proposed test file, safety checks, and verification command before applying."
        ),
    ),
    L1Case(
        case_id="D1-005",
        name="Draft Small Error Message Assertion Test",
        selected_workflow="execution_planning.plan",
        downstream_workflow="execution_planning.plan",
        artifact_keys=("small_unit_test_proposal", "downstream_implementation_workflow_report"),
        markers=(
            "Draft proposal:",
            "small_unit_test_proposal",
            "tests/unit/test_orderbook_v2.py",
            "append_text",
            "test_orderbook_read_only_error_message_names_blocked_operation",
            "OrderBook is read-only; refusing upsert_order()",
            "Verification:",
            "python -m pytest tests/unit/test_orderbook_v2.py",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, draft a small unit test in tests/unit/test_orderbook_v2.py "
            "asserting exact error message \"OrderBook is read-only; refusing upsert_order()\" "
            "from core/orderbook.py. Draft only. Show the proposed test file, safety checks, "
            "and verification command before applying."
        ),
    ),
    L1Case(
        case_id="D1-006",
        name="Draft Small Test Assertion Update",
        selected_workflow="execution_planning.plan",
        downstream_workflow="execution_planning.plan",
        artifact_keys=("small_unit_test_proposal", "downstream_implementation_workflow_report"),
        markers=(
            "Draft proposal:",
            "small_unit_test_proposal",
            "tests/unit/test_order_id_and_followup_rules.py",
            "replace_text",
            "inherited from root parent",
            "Verification:",
            "python -m pytest tests/unit/test_order_id_and_followup_rules.py",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, draft a small test assertion update in "
            "tests/unit/test_order_id_and_followup_rules.py. Replace the assertion "
            "`assert call_kwargs[\"reveal_pricing_policy\"] == \"top_of_book\"` with "
            "`assert call_kwargs[\"reveal_pricing_policy\"] == \"top_of_book\"  # inherited from root parent`. "
            "Draft only. Do not mutate files. Show the proposed change, safety checks, and verification command."
        ),
    ),
    L1Case(
        case_id="L1-012",
        name="Locate Endpoint Or Route Handler",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_endpoint_route_lookup",),
        markers=(
            "Answer:",
            "Target: request_stealth_orders",
            "Handler files:",
            "dashboard_server.py",
            "websocket_message_handler",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, find the WebSocket handler for \"request_stealth_orders\". "
            "Read only. Return handler files, source refs, and related tests."
        ),
    ),
    L1Case(
        case_id="L1-013",
        name="Locate Error Or Log Message Source",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_message_source_lookup",),
        markers=(
            "Answer:",
            "Target message: Missing 'type' field in message",
            "Sources:",
            "dashboard_server.py",
            "raised_exception",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, locate the source of error message "
            "\"Missing 'type' field in message\". Read only. Return file, line, and role."
        ),
    ),
    L1Case(
        case_id="L1-014",
        name="Summarize A Module Or File",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_module_summary",),
        markers=(
            "Answer:",
            "Target module: core/stealth_order_manager.py",
            "Responsibilities:",
            "Definitions:",
            "StealthOrderManager",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, summarize module core/stealth_order_manager.py. "
            "Read only. Return responsibilities, definitions, related tests, and source refs."
        ),
    ),
    L1Case(
        case_id="L1-015",
        name="Find Data Model Or Schema",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_data_model_lookup",),
        markers=(
            "Answer:",
            "Target model/schema: stealth_orders",
            "Fields:",
            "stealth_order_id",
            "database/order.py",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, find the database schema fields for stealth_orders. "
            "Read only. Return model files, fields, and source refs."
        ),
    ),
    L1Case(
        case_id="L1-016",
        name="Find Imports Or Dependencies",
        selected_workflow="code_context.lookup",
        downstream_workflow="code_context.lookup",
        artifact_keys=("downstream_dependency_lookup",),
        markers=(
            "Answer:",
            "Target: core/stealth_order_manager.py",
            "Imports:",
            "database.order",
            "core.enums",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, find imports/dependencies for core/stealth_order_manager.py. "
            "Read only. Return imports, source refs, and whether files were mutated."
        ),
    ),
    L1Case(
        case_id="L1-017",
        name="Identify Test Coverage Gaps",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_coverage_gap_summary",),
        markers=(
            "Answer:",
            "Target: placed_order_id",
            "Coverage gaps:",
            "Related tests:",
            "Recommended commands:",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, identify test coverage gaps for placed_order_id stealth lookup. "
            "Read only. Return covered tests, uncovered source files, verification commands, and gaps."
        ),
    ),
    L1Case(
        case_id="L1-018",
        name="Find Documentation For Behavior",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_documentation_lookup",),
        markers=(
            "Answer:",
            "Target: request_stealth_orders",
            "Documentation files:",
            "agent.md",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, find documentation for request_stealth_orders dashboard behavior. "
            "Read only. Return documentation files, source refs, and gaps."
        ),
    ),
    L1Case(
        case_id="L1-019",
        name="Locate CLI Or Script Entrypoint",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_cli_entrypoint_lookup",),
        markers=(
            "Answer:",
            "Target entrypoint: main.py",
            "Entrypoints:",
            "main.py",
            "python main.py",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, locate the CLI/script entrypoint main.py for running the trading engine. "
            "Read only. Return entrypoint files, command, and source refs."
        ),
    ),
    L1Case(
        case_id="L1-020",
        name="Explain Configuration Runtime Effect",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_configuration_effect_summary",),
        markers=(
            "Answer:",
            "Target config: COINBASE_API_KEY",
            "Runtime effect:",
            "configuration.py",
            "API_KEY",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, explain the runtime effect of COINBASE_API_KEY in configuration.py. "
            "Read only. Return references, effect, and source refs."
        ),
    ),
    L1Case(
        case_id="L1-021",
        name="Find Recent Or Local Changes",
        selected_workflow="code_investigation.plan",
        downstream_workflow="code_investigation.plan",
        artifact_keys=("downstream_local_change_summary",),
        markers=(
            "Answer:",
            "Local change status:",
            "Git status:",
            "Recent commits:",
            "Source mutation: false",
        ),
        prompt_template=(
            "In {target_root}, find recent or local changes. "
            "Read only. Return git status, recent commits, changed files, and unsupported gaps."
        ),
    ),
)


def selected_cases(case_ids: list[str] | None) -> tuple[L1Case, ...]:
    if not case_ids:
        return L1_CASES
    allowed = {case_id.upper() for case_id in case_ids}
    cases = tuple(case for case in L1_CASES if case.case_id.upper() in allowed)
    missing = sorted(allowed - {case.case_id.upper() for case in cases})
    if missing:
        raise RuntimeError(f"unknown L1 case id(s): {', '.join(missing)}")
    return cases


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


def watched_hashes(target_root: str) -> dict[str, str]:
    root = Path(target_root)
    hashes: dict[str, str] = {}
    for relative_path in WATCHED_RELATIVE_PATHS:
        path = root / relative_path
        if path.exists():
            hashes[relative_path] = digest_file(path)
    if not hashes:
        raise RuntimeError(f"{target_root} did not contain any watched validation files")
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


def text_response(body: dict[str, Any]) -> str:
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
    raise RuntimeError("response did not include assistant text")


def run_id_from_text(text: str) -> str:
    marker = "run_id:"
    if marker not in text:
        return "unknown"
    return text.split(marker, 1)[1].strip().split()[0]


def require_text_markers(text: str, markers: tuple[str, ...], *, label: str, target_root: str, case: L1Case) -> None:
    common_markers = (
        "I completed workflow_router.plan.",
        "workflow_router.plan completed",
        "run_id: workflow-router-",
        "Result:",
        "- Selected workflow:",
        "- Selected skills:",
        "- Selected tools:",
        "- Next action:",
        "- Verification:",
        f"selected_workflow: {case.selected_workflow}",
        "Artifacts:",
    )
    missing = [marker for marker in (*common_markers, *markers) if marker not in text]
    if missing:
        raise RuntimeError(
            f"{label} missing markers for {case.case_id} on {target_root}: "
            f"{json.dumps(missing, ensure_ascii=True)}"
        )


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


def expected_model_capability_task_class(case: L1Case) -> str:
    if case.selected_workflow == "execution_planning.plan":
        return "draft_only_l1"
    return "read_only_l1"


def require_model_capability_gateway_artifacts(compact: dict[str, Any], target_root: str, case: L1Case) -> None:
    artifacts = compact.get("artifacts")
    if not isinstance(artifacts, dict):
        raise RuntimeError(f"gateway response did not include artifacts for {case.case_id} on {target_root}")
    summary = compact.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError(f"gateway response did not include summary for {case.case_id} on {target_root}")
    decision = read_json_artifact(artifacts.get("route_decision"), label=f"{case.case_id} route_decision")
    gate = decision.get("model_capability_routing")
    if not isinstance(gate, dict):
        raise RuntimeError(f"{case.case_id} route decision did not include model_capability_routing on {target_root}")
    expected_task_class = expected_model_capability_task_class(case)
    expected = {
        "status": "approved",
        "task_class": expected_task_class,
        "task_policy_status": "approved",
    }
    wrong = {key: {"expected": value, "actual": gate.get(key)} for key, value in expected.items() if gate.get(key) != value}
    if wrong:
        raise RuntimeError(
            f"{case.case_id} model capability gate mismatch on {target_root}: "
            f"{json.dumps(wrong, sort_keys=True)}"
        )
    if not isinstance(gate.get("profile_id"), str) or not gate["profile_id"]:
        raise RuntimeError(f"{case.case_id} model capability gate did not record profile_id on {target_root}")
    if summary.get("model_capability_status") != gate.get("status"):
        raise RuntimeError(f"{case.case_id} summary did not expose model_capability_status on {target_root}")
    if summary.get("model_capability_task_class") != gate.get("task_class"):
        raise RuntimeError(f"{case.case_id} summary did not expose model_capability_task_class on {target_root}")
    evidence = decision.get("evidence") if isinstance(decision.get("evidence"), list) else []
    if not any(item.get("source") == "model_capability_routing" for item in evidence if isinstance(item, dict)):
        raise RuntimeError(f"{case.case_id} evidence did not include model_capability_routing on {target_root}")


def require_gateway_response(body: dict[str, Any], target_root: str, case: L1Case) -> str:
    compact = body.get("agentic_controller_response")
    if not isinstance(compact, dict):
        raise RuntimeError(f"gateway response did not include agentic_controller_response for {case.case_id} on {target_root}")
    if compact.get("workflow") != "workflow_router.plan":
        raise RuntimeError(f"gateway returned unexpected workflow for {case.case_id}: {compact.get('workflow')!r}")
    if compact.get("status") != "completed":
        raise RuntimeError(f"gateway did not complete {case.case_id}: {compact.get('status')!r}")
    summary = compact.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError(f"gateway response did not include summary for {case.case_id} on {target_root}")
    expected = {
        "route_status": "ready",
        "selected_workflow": case.selected_workflow,
        "downstream_workflow": case.downstream_workflow,
        "downstream_status": "completed",
    }
    wrong = {
        key: {"expected": expected_value, "actual": summary.get(key)}
        for key, expected_value in expected.items()
        if summary.get(key) != expected_value
    }
    if wrong:
        raise RuntimeError(
            f"gateway response summary mismatch for {case.case_id} on {target_root}: "
            f"{json.dumps(wrong, sort_keys=True)}"
        )
    artifacts = compact.get("artifacts")
    if not isinstance(artifacts, dict):
        raise RuntimeError(f"gateway response did not include artifacts for {case.case_id} on {target_root}")
    missing_artifacts = [key for key in case.artifact_keys if key not in artifacts]
    if missing_artifacts:
        raise RuntimeError(
            f"gateway response missing artifacts for {case.case_id} on {target_root}: "
            f"{json.dumps(missing_artifacts, ensure_ascii=True)}"
        )
    text = text_response(body)
    require_text_markers(text, case.markers, label="gateway", target_root=target_root, case=case)
    require_model_capability_gateway_artifacts(compact, target_root, case)
    return text


def validate_unchanged(target_root: str, before_hashes: dict[str, str], before_status: str | None, label: str) -> None:
    after_hashes = watched_hashes(target_root)
    if after_hashes != before_hashes:
        raise RuntimeError(f"{label} mutated watched files for {target_root}")
    after_status = git_status(target_root)
    if before_status is not None and after_status != before_status:
        raise RuntimeError(f"{label} changed git status for {target_root}: {after_status!r}")


def validate_gateway(args: argparse.Namespace, target_root: str, case: L1Case) -> dict[str, str]:
    before_hashes = watched_hashes(target_root)
    before_status = git_status(target_root)
    status, body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": case.prompt(target_root)}],
        },
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(
            f"gateway returned HTTP {status} for {case.case_id} on {target_root}: "
            f"{json.dumps(body, ensure_ascii=True)}"
        )
    text = require_gateway_response(body, target_root, case)
    validate_unchanged(target_root, before_hashes, before_status, f"gateway {case.case_id}")
    run_id = run_id_from_text(text)
    print(f"L1 SUITE GATEWAY PASS case={case.case_id} target={target_root} run_id={run_id}")
    return {"case_id": case.case_id, "target_root": target_root, "run_id": run_id}


def validate_anythingllm(args: argparse.Namespace, target_root: str, case: L1Case, api_key: str) -> dict[str, str]:
    before_hashes = watched_hashes(target_root)
    before_status = git_status(target_root)
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload={
            "message": case.prompt(target_root),
            "mode": "chat",
            "sessionId": f"workflow-router-l1-{case.case_id.lower()}-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(
            f"AnythingLLM returned HTTP {status} for {case.case_id} on {target_root}: "
            f"{json.dumps(body, ensure_ascii=True)}"
        )
    text = text_response(body)
    require_text_markers(text, case.markers, label="AnythingLLM", target_root=target_root, case=case)
    validate_unchanged(target_root, before_hashes, before_status, f"AnythingLLM {case.case_id}")
    run_id = run_id_from_text(text)
    print(f"L1 SUITE ANYTHINGLLM PASS case={case.case_id} target={target_root} run_id={run_id}")
    return {"case_id": case.case_id, "target_root": target_root, "run_id": run_id}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--skip-anythingllm", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_roots = args.target_roots or DEFAULT_TARGET_ROOTS
    cases = selected_cases(args.case_ids)
    summary: dict[str, Any] = {
        "gateway": [],
        "anythingllm": [],
        "target_roots": target_roots,
        "case_ids": [case.case_id for case in cases],
    }
    for target_root in target_roots:
        for case in cases:
            summary["gateway"].append(validate_gateway(args, target_root, case))
    if not args.skip_anythingllm:
        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            raise RuntimeError(f"{args.api_key_env} is required unless --skip-anythingllm is set")
        for target_root in target_roots:
            for case in cases:
                summary["anythingllm"].append(validate_anythingllm(args, target_root, case, api_key))
    print("L1 SUITE SUMMARY")
    print(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
