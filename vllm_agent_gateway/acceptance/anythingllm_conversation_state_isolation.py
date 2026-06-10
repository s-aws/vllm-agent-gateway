"""AnythingLLM conversation-state isolation validation.

Phase 152 proves that stale chat history does not control the current
workflow-router response. The validator exercises the existing controller,
gateway, and AnythingLLM paths; it does not add production routing behavior.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.skill_selection_hardening import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    artifact_json,
    assert_fixture_state_unchanged,
    controller_run_record,
    fixture_state,
    json_request,
    selection_signature,
    text_response,
)
from vllm_agent_gateway.controller_service.server import (
    ControllerServiceConfig,
    handle_workflow_router_chat_completion,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "anythingllm_conversation_state_isolation_policy"
EXPECTED_REPORT_KIND = "anythingllm_conversation_state_isolation_report"
EXPECTED_PHASE = 152
EXPECTED_BACKLOG_ID = "P0-BB-020"
DEFAULT_POLICY_PATH = Path("runtime") / "anythingllm_conversation_state_isolation_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "anythingllm-conversation-state-isolation" / "phase152"


class ConversationIsolationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class AnythingLLMConversationStateIsolationConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    markdown_output_path: Path | None = None
    target_roots: tuple[str, ...] = DEFAULT_TARGET_ROOTS
    include_direct: bool = True
    include_gateway: bool = True
    include_anythingllm: bool = True
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 900


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"anythingllm-conversation-state-isolation-{utc_timestamp()}.json"


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object at {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 152")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    version = policy.get("policy_version")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        errors.append("policy.policy_version must use semantic version x.y.z")
    purpose = str(policy.get("purpose") or "").lower()
    for phrase in ("current user message controls", "stale prior", "anythingllm"):
        if phrase not in purpose:
            errors.append(f"policy.purpose must mention {phrase!r}")
    if set(string_list(policy.get("required_surfaces"))) != {
        "direct_controller_history",
        "gateway_history_payload",
        "anythingllm_same_session",
    }:
        errors.append("policy.required_surfaces must include direct_controller_history, gateway_history_payload, and anythingllm_same_session")
    if set(string_list(policy.get("required_target_roots"))) != set(DEFAULT_TARGET_ROOTS):
        errors.append("policy.required_target_roots must match both frozen Coinbase fixtures")
    cases = object_list(policy.get("cases"))
    if len(cases) < 3:
        errors.append("policy.cases must include at least three contamination cases")
    seen: set[str] = set()
    required_seed_kinds = {"stale_repo_prompt", "stale_json_prompt", "stale_controller_envelope", "stale_format_a_prompt"}
    actual_seed_kinds: set[str] = set()
    for index, case in enumerate(cases):
        prefix = f"policy.cases[{index}]"
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            errors.append(f"{prefix}.case_id is required")
        elif case_id in seen:
            errors.append(f"duplicate case_id {case_id}")
        else:
            seen.add(case_id)
        seed_kind = case.get("seed_kind")
        if isinstance(seed_kind, str):
            actual_seed_kinds.add(seed_kind)
        if seed_kind not in required_seed_kinds:
            errors.append(f"{prefix}.seed_kind must be one of {sorted(required_seed_kinds)}")
        if not isinstance(case.get("current_prompt_template"), str) or not case["current_prompt_template"].strip():
            errors.append(f"{prefix}.current_prompt_template is required")
        if case.get("expected_route_status") not in {"ready", "general_chat_no_target"}:
            errors.append(f"{prefix}.expected_route_status must be ready or general_chat_no_target")
        if case.get("expected_output_format") not in {"format_a", "json"}:
            errors.append(f"{prefix}.expected_output_format must be format_a or json")
        if not isinstance(case.get("forbidden_current_markers"), list):
            errors.append(f"{prefix}.forbidden_current_markers must be a list")
        if case.get("expected_route_status") == "ready":
            if not isinstance(case.get("expected_selected_workflow"), str) or not case["expected_selected_workflow"].strip():
                errors.append(f"{prefix}.expected_selected_workflow is required for ready cases")
            if not string_list(case.get("expected_route_rules")):
                errors.append(f"{prefix}.expected_route_rules is required for ready cases")
    missing_seed_kinds = sorted(required_seed_kinds - actual_seed_kinds)
    if missing_seed_kinds:
        errors.append(f"policy.cases missing seed kinds: {missing_seed_kinds}")
    if not string_list(policy.get("required_current_markers")):
        errors.append("policy.required_current_markers must be non-empty")
    if policy.get("non_mutation_required") is not True:
        errors.append("policy.non_mutation_required must be true")
    return errors


def other_target(target_root: str, target_roots: tuple[str, ...]) -> str:
    for candidate in target_roots:
        if candidate != target_root:
            return candidate
    return target_root


def seed_prompt(seed_kind: str, *, target_root: str, stale_target_root: str) -> str:
    if seed_kind == "stale_repo_prompt":
        return (
            f"In {stale_target_root}, explain what find_stealth_order_by_placed_order_id does in "
            "core/stealth_order_manager.py. Read only. Include inputs and tests."
        )
    if seed_kind == "stale_json_prompt":
        return (
            f"In {stale_target_root}, explain what find_stealth_order_by_placed_order_id does in "
            "core/stealth_order_manager.py. Read only. Return JSON."
        )
    if seed_kind == "stale_controller_envelope":
        envelope = {
            "agentic_controller_request": {
                "workflow": "workflow_router.plan",
                "target_root": stale_target_root,
                "user_request": (
                    f"In {stale_target_root}, explain what find_stealth_order_by_placed_order_id does. Read only."
                ),
                "mode": "execute_read_only",
                "budgets": {"max_model_calls": 1, "max_selected_skills": 5, "max_selected_tools": 5},
            }
        }
        return json.dumps(envelope, ensure_ascii=True, sort_keys=True)
    if seed_kind == "stale_format_a_prompt":
        return (
            f"In {stale_target_root}, find callers and usages of find_stealth_order_by_placed_order_id. "
            "Read only. Group by file and explain each usage briefly. Use FormatA."
        )
    raise RuntimeError(f"unsupported seed_kind {seed_kind!r}")


def current_prompt(case: dict[str, Any], target_root: str) -> str:
    template = str(case["current_prompt_template"])
    return template.format(target_root=target_root)


def history_messages(case: dict[str, Any], *, target_root: str, target_roots: tuple[str, ...]) -> list[dict[str, str]]:
    stale_target_root = other_target(target_root, target_roots)
    return [
        {"role": "user", "content": seed_prompt(str(case["seed_kind"]), target_root=target_root, stale_target_root=stale_target_root)},
        {"role": "assistant", "content": "prior run_id: workflow-router-stale-history"},
        {"role": "user", "content": current_prompt(case, target_root)},
    ]


def run_id_from_text(text: str) -> str:
    match = re.search(r"\brun_id:\s*(workflow-router-[A-Za-z0-9]+)", text)
    if match:
        return match.group(1)
    parsed = parsed_json_object(text)
    if parsed is not None and isinstance(parsed.get("run_id"), str):
        return parsed["run_id"]
    return "unknown"


def text_is_json_object(text: str) -> bool:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return False
    return isinstance(parsed, dict)


def parsed_json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def route_decision_from_json_content(parsed: dict[str, Any]) -> dict[str, Any] | None:
    contract = dict_value(parsed.get("chat_contract"))
    explanation = dict_value(parsed.get("selection_explanation"))
    selected_workflow = contract.get("selected_workflow")
    if not isinstance(selected_workflow, str) or not selected_workflow:
        return None
    route_rules = string_list(explanation.get("route_rules"))
    selected_skills = string_list(contract.get("selected_skills"))
    selected_tools = string_list(contract.get("selected_tools"))
    rejected = dict_value(explanation.get("rejected_candidates"))
    return {
        "status": "ready",
        "selected_workflow": selected_workflow,
        "confidence": explanation.get("confidence"),
        "selected_skills": selected_skills,
        "selected_tools": selected_tools,
        "selection_audit": {
            "selected": {
                "route_rules": route_rules,
                "coverage_entry_ids": string_list(explanation.get("coverage_entry_ids")),
                "confidence_reasons": string_list(explanation.get("confidence_reasons")),
            },
            "workflow_candidates": {"rejected_count": rejected.get("workflow_rejected_count", 0)},
            "skill_candidates": {"rejected_count": rejected.get("skill_rejected_count", 0)},
            "tool_candidates": {"rejected_count": rejected.get("tool_rejected_count", 0)},
        },
    }


def validate_current_response(
    *,
    policy: dict[str, Any],
    case: dict[str, Any],
    target_root: str,
    surface: str,
    text: str,
    output_format: str | None,
    route_decision: dict[str, Any] | None = None,
    request_artifact: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    label = f"{surface}.{case.get('case_id')}.{Path(target_root).name}"
    for marker in string_list(case.get("forbidden_current_markers")):
        if marker in text:
            errors.append(f"{label}.text contains stale/forbidden marker {marker}")
    expected_output_format = case.get("expected_output_format")
    parsed_json = parsed_json_object(text)
    if expected_output_format == "format_a":
        for marker in string_list(policy.get("required_current_markers")):
            if marker not in text:
                errors.append(f"{label}.text missing required marker {marker}")
    elif expected_output_format == "json":
        if parsed_json is None:
            errors.append(f"{label}.text is not parseable JSON")
        elif not isinstance(parsed_json.get("run_id"), str):
            errors.append(f"{label}.json missing run_id")
    if output_format is not None and output_format != expected_output_format:
        errors.append(f"{label}.output_format expected {case.get('expected_output_format')!r} got {output_format!r}")
    if expected_output_format == "format_a" and parsed_json is not None:
        errors.append(f"{label}.text is JSON even though current prompt expects FormatA")
    if expected_output_format == "json":
        if parsed_json is not None and parsed_json.get("output_format") != "json":
            errors.append(f"{label}.json output_format expected 'json' got {parsed_json.get('output_format')!r}")
        for section_marker in ("chat_contract", "selection_explanation"):
            if parsed_json is not None and section_marker not in dict_value(parsed_json):
                errors.append(f"{label}.json missing {section_marker}")
        if route_decision is None and parsed_json is not None:
            route_decision = route_decision_from_json_content(parsed_json)

    expected_status = case.get("expected_route_status")
    if expected_status == "general_chat_no_target":
        if "general_chat_no_target" not in text:
            errors.append(f"{label}.text missing general_chat_no_target")
        if "Selected workflow: none" not in text:
            errors.append(f"{label}.text missing Selected workflow: none")
        return errors

    if route_decision is None:
        errors.append(f"{label}.route_decision missing for ready current prompt")
        return errors
    signature = selection_signature(route_decision)
    expected_workflow = case.get("expected_selected_workflow")
    if signature["selected_workflow"] != expected_workflow:
        errors.append(f"{label}.route selected_workflow expected {expected_workflow!r} got {signature['selected_workflow']!r}")
    if expected_output_format == "format_a" and f"- Selected workflow: {expected_workflow}" not in text:
        errors.append(f"{label}.text missing selected workflow {expected_workflow}")
    if expected_output_format == "json" and parsed_json is not None:
        contract = dict_value(parsed_json.get("chat_contract"))
        if contract.get("selected_workflow") != expected_workflow:
            errors.append(f"{label}.json selected_workflow expected {expected_workflow!r} got {contract.get('selected_workflow')!r}")
    for rule in string_list(case.get("expected_route_rules")):
        if rule not in signature["route_rules"]:
            errors.append(f"{label}.route missing expected rule {rule}")
        if rule not in text:
            errors.append(f"{label}.text missing expected rule {rule}")
    if "target_root" in route_decision and route_decision.get("target_root") != target_root:
        errors.append(f"{label}.route target_root expected {target_root!r} got {route_decision.get('target_root')!r}")
    if request_artifact is not None:
        if request_artifact.get("target_root") != target_root:
            errors.append(f"{label}.request target_root expected {target_root!r} got {request_artifact.get('target_root')!r}")
        if request_artifact.get("user_request") != current_prompt(case, target_root):
            errors.append(f"{label}.request user_request did not match current prompt")
    return errors


def route_signature_from_current_response(
    *,
    case: dict[str, Any],
    text: str,
    route_decision: dict[str, Any] | None,
) -> dict[str, Any]:
    if route_decision is not None:
        signature = selection_signature(route_decision)
        return {
            "selected_workflow": signature["selected_workflow"],
            "selected_skills": signature["selected_skills"],
            "selected_tools": signature["selected_tools"],
            "route_rules": signature["route_rules"],
        }
    parsed = parsed_json_object(text)
    if parsed is not None:
        reconstructed = route_decision_from_json_content(parsed)
        if reconstructed is not None:
            return route_signature_from_current_response(case=case, text=text, route_decision=reconstructed)
    if case.get("expected_route_status") == "general_chat_no_target":
        return {"selected_workflow": None, "selected_skills": [], "selected_tools": [], "route_rules": []}
    return {"selected_workflow": "unknown", "selected_skills": [], "selected_tools": [], "route_rules": []}


def direct_controller_case(
    config: AnythingLLMConversationStateIsolationConfig,
    *,
    policy: dict[str, Any],
    case: dict[str, Any],
    target_root: str,
) -> dict[str, Any]:
    service_config = ControllerServiceConfig(
        config_root=config.config_root,
        output_root=config.config_root / DEFAULT_OUTPUT_DIR / "direct-controller-artifacts",
        allowed_target_roots=tuple(Path(root).resolve() for root in config.target_roots),
        port=0,
    )
    body = handle_workflow_router_chat_completion(
        {"model": "agentic-workflow-router", "messages": history_messages(case, target_root=target_root, target_roots=config.target_roots)},
        service_config,
    )
    text = text_response(body)
    compact = dict_value(body.get("agentic_controller_response"))
    route_decision = artifact_json(compact, "route_decision") if dict_value(compact.get("artifacts")).get("route_decision") else None
    request_artifact = artifact_json(compact, "request") if dict_value(compact.get("artifacts")).get("request") else None
    errors = validate_current_response(
        policy=policy,
        case=case,
        target_root=target_root,
        surface="direct_controller_history",
        text=text,
        output_format=compact.get("output_format") if isinstance(compact.get("output_format"), str) else None,
        route_decision=route_decision,
        request_artifact=request_artifact,
    )
    return result_record(
        case=case,
        target_root=target_root,
        surface="direct_controller_history",
        text=text,
        run_id=str(compact.get("run_id") or run_id_from_text(text)),
        output_format=compact.get("output_format") if isinstance(compact.get("output_format"), str) else None,
        errors=errors,
    )


def gateway_history_case(
    config: AnythingLLMConversationStateIsolationConfig,
    *,
    policy: dict[str, Any],
    case: dict[str, Any],
    target_root: str,
) -> dict[str, Any]:
    before = fixture_state(target_root)
    stale_before = fixture_state(other_target(target_root, config.target_roots))
    status, body = json_request(
        f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "messages": history_messages(case, target_root=target_root, target_roots=config.target_roots),
            "role_base_url": config.model_base_url,
            "budgets": {"max_model_calls": 3, "max_selected_skills": 5, "max_selected_tools": 5},
        },
        timeout_seconds=config.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"gateway returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    compact = dict_value(body.get("agentic_controller_response"))
    route_decision = artifact_json(compact, "route_decision") if dict_value(compact.get("artifacts")).get("route_decision") else None
    request_artifact = artifact_json(compact, "request") if dict_value(compact.get("artifacts")).get("request") else None
    errors = validate_current_response(
        policy=policy,
        case=case,
        target_root=target_root,
        surface="gateway_history_payload",
        text=text,
        output_format=compact.get("output_format") if isinstance(compact.get("output_format"), str) else None,
        route_decision=route_decision,
        request_artifact=request_artifact,
    )
    assert_fixture_state_unchanged(before, target_root, f"gateway history {case.get('case_id')}")
    assert_fixture_state_unchanged(stale_before, other_target(target_root, config.target_roots), f"gateway stale history {case.get('case_id')}")
    return result_record(
        case=case,
        target_root=target_root,
        surface="gateway_history_payload",
        text=text,
        run_id=str(compact.get("run_id") or run_id_from_text(text)),
        output_format=compact.get("output_format") if isinstance(compact.get("output_format"), str) else None,
        errors=errors,
    )


def anythingllm_same_session_case(
    config: AnythingLLMConversationStateIsolationConfig,
    *,
    policy: dict[str, Any],
    case: dict[str, Any],
    target_root: str,
    api_key: str,
) -> dict[str, Any]:
    before = fixture_state(target_root)
    stale_target = other_target(target_root, config.target_roots)
    stale_before = fixture_state(stale_target)
    session_id = f"phase152-isolation-{case.get('case_id', 'case').lower()}-{uuid.uuid4().hex}"
    seed_status, seed_body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={
            "message": seed_prompt(str(case["seed_kind"]), target_root=target_root, stale_target_root=stale_target),
            "mode": "chat",
            "sessionId": session_id,
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=config.timeout_seconds,
    )
    if seed_status != 200:
        raise RuntimeError(f"AnythingLLM seed returned HTTP {seed_status}: {json.dumps(seed_body, ensure_ascii=True)}")
    status, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={"message": current_prompt(case, target_root), "mode": "chat", "sessionId": session_id},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=config.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"AnythingLLM current returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    route_decision: dict[str, Any] | None = None
    request_artifact: dict[str, Any] | None = None
    run_id = run_id_from_text(text)
    if case.get("expected_route_status") == "ready" and run_id != "unknown":
        record = controller_run_record(config, run_id)
        route_decision = artifact_json(record, "route_decision")
        request_artifact = artifact_json(record, "request")
    elif case.get("expected_route_status") == "ready" and case.get("expected_output_format") != "json":
        raise RuntimeError("AnythingLLM current response did not include a workflow-router run_id")
    errors = validate_current_response(
        policy=policy,
        case=case,
        target_root=target_root,
        surface="anythingllm_same_session",
        text=text,
        output_format=None,
        route_decision=route_decision,
        request_artifact=request_artifact,
    )
    fresh_status, fresh_body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={
            "message": current_prompt(case, target_root),
            "mode": "chat",
            "sessionId": f"phase152-fresh-{case.get('case_id', 'case').lower()}-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=config.timeout_seconds,
    )
    fresh_text = text_response(fresh_body)
    fresh_route_decision: dict[str, Any] | None = None
    fresh_run_id = run_id_from_text(fresh_text)
    if case.get("expected_route_status") == "ready" and fresh_run_id != "unknown":
        fresh_record = controller_run_record(config, fresh_run_id)
        fresh_route_decision = artifact_json(fresh_record, "route_decision")
    elif case.get("expected_route_status") == "ready" and case.get("expected_output_format") != "json":
        errors.append("fresh AnythingLLM current response did not include a workflow-router run_id")
    if fresh_status != 200:
        errors.append(f"fresh AnythingLLM comparison returned HTTP {fresh_status}")
    contaminated_signature = route_signature_from_current_response(case=case, text=text, route_decision=route_decision)
    fresh_signature = route_signature_from_current_response(case=case, text=fresh_text, route_decision=fresh_route_decision)
    if contaminated_signature != fresh_signature:
        errors.append(
            "contaminated AnythingLLM session route signature did not match fresh-session route signature: "
            f"{contaminated_signature!r} != {fresh_signature!r}"
        )
    assert_fixture_state_unchanged(before, target_root, f"AnythingLLM current {case.get('case_id')}")
    assert_fixture_state_unchanged(stale_before, stale_target, f"AnythingLLM stale {case.get('case_id')}")
    return result_record(
        case=case,
        target_root=target_root,
        surface="anythingllm_same_session",
        text=text,
        run_id=run_id,
        output_format=None,
        errors=errors,
        session_id=session_id,
        seed_http_status=seed_status,
        fresh_run_id=fresh_run_id,
    )


def result_record(
    *,
    case: dict[str, Any],
    target_root: str,
    surface: str,
    text: str,
    run_id: str,
    output_format: str | None,
    errors: list[str],
    session_id: str | None = None,
    seed_http_status: int | None = None,
    fresh_run_id: str | None = None,
) -> dict[str, Any]:
    return {
        "case_id": case.get("case_id"),
        "surface": surface,
        "target_root": target_root,
        "status": ConversationIsolationStatus.PASSED.value if not errors else ConversationIsolationStatus.FAILED.value,
        "run_id": run_id,
        "session_id": session_id,
        "seed_http_status": seed_http_status,
        "fresh_run_id": fresh_run_id,
        "output_format": output_format,
        "assistant_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "assistant_text_excerpt": text[:2000],
        "errors": errors,
    }


def skipped_result(case: dict[str, Any], target_root: str, surface: str, reason: str) -> dict[str, Any]:
    return {
        "case_id": case.get("case_id"),
        "surface": surface,
        "target_root": target_root,
        "status": ConversationIsolationStatus.SKIPPED.value,
        "run_id": "not_run",
        "errors": [reason],
    }


def build_summary(results: list[dict[str, Any]], policy_errors: list[str]) -> dict[str, Any]:
    passed = [item for item in results if item.get("status") == ConversationIsolationStatus.PASSED.value]
    failed = [item for item in results if item.get("status") == ConversationIsolationStatus.FAILED.value]
    skipped = [item for item in results if item.get("status") == ConversationIsolationStatus.SKIPPED.value]
    return {
        "case_count": len({str(item.get("case_id")) for item in results if isinstance(item.get("case_id"), str)}),
        "target_root_count": len({str(item.get("target_root")) for item in results if isinstance(item.get("target_root"), str)}),
        "surface_count": len({str(item.get("surface")) for item in results if isinstance(item.get("surface"), str)}),
        "response_count": len(results),
        "passed_response_count": len(passed),
        "failed_response_count": len(failed),
        "skipped_response_count": len(skipped),
        "policy_error_count": len(policy_errors),
        "surfaces": sorted({str(item.get("surface")) for item in results if isinstance(item.get("surface"), str)}),
        "case_ids": sorted({str(item.get("case_id")) for item in results if isinstance(item.get("case_id"), str)}),
        "target_roots": sorted({str(item.get("target_root")) for item in results if isinstance(item.get("target_root"), str)}),
    }


def validate_report(report: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append("report.schema_version must be 1")
    if report.get("kind") != EXPECTED_REPORT_KIND:
        errors.append(f"report.kind must be {EXPECTED_REPORT_KIND}")
    if report.get("phase") != EXPECTED_PHASE:
        errors.append("report.phase must be 152")
    if report.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"report.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    results = object_list(report.get("results"))
    summary = dict_value(report.get("summary"))
    expected_summary = build_summary(results, string_list(report.get("policy_errors")))
    for key, expected in expected_summary.items():
        if summary.get(key) != expected:
            errors.append(f"report.summary.{key} mismatch")
    if report.get("status") == ConversationIsolationStatus.PASSED.value:
        if any(item.get("status") != ConversationIsolationStatus.PASSED.value for item in results):
            errors.append("passed report cannot contain failed or skipped results")
        if set(summary.get("surfaces", [])) != set(string_list(policy.get("required_surfaces"))):
            errors.append("passed report must include all required surfaces")
        if set(summary.get("target_roots", [])) != set(string_list(policy.get("required_target_roots"))):
            errors.append("passed report must include all required target roots")
    return errors


def markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# AnythingLLM Conversation State Isolation",
        "",
        f"Status: {report.get('status')}",
        f"Phase: {report.get('phase')}",
        f"Created: {report.get('created_at')}",
        "",
        "## Summary",
        "",
        f"- Cases: {summary.get('case_count')}",
        f"- Responses: {summary.get('passed_response_count')} passed / {summary.get('response_count')} total",
        f"- Surfaces: {', '.join(string_list(summary.get('surfaces')))}",
        f"- Targets: {', '.join(string_list(summary.get('target_roots')))}",
        "",
        "## Results",
        "",
        "| Case | Surface | Target | Status | Run ID |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in object_list(report.get("results")):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("case_id")),
                    str(item.get("surface")),
                    Path(str(item.get("target_root"))).name,
                    str(item.get("status")),
                    str(item.get("run_id")),
                ]
            )
            + " |"
        )
    if report.get("errors"):
        lines.extend(["", "## Errors", ""])
        for error in string_list(report.get("errors")):
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"


def run_anythingllm_conversation_state_isolation(
    config: AnythingLLMConversationStateIsolationConfig,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root)
    policy_path = resolve_path(config_root, config.policy_path)
    policy_errors: list[str] = []
    errors: list[str] = []
    results: list[dict[str, Any]] = []
    policy: dict[str, Any] = {}
    cases: list[dict[str, Any]] = []
    try:
        policy = read_json_object(policy_path)
        policy_errors = validate_policy(policy)
        cases = object_list(policy.get("cases")) if not policy_errors else []
    except Exception as exc:  # noqa: BLE001
        policy_errors.append(f"policy load failed: {type(exc).__name__}: {exc}")
    errors.extend(policy_errors)
    if not policy_errors:
        api_key = os.environ.get(config.api_key_env) if config.include_anythingllm else None
        if config.include_anythingllm and not api_key:
            errors.append(f"{config.api_key_env} is required for AnythingLLM validation")
        for target_root in config.target_roots:
            for case in cases:
                if config.include_direct:
                    try:
                        results.append(direct_controller_case(config, policy=policy, case=case, target_root=target_root))
                    except Exception as exc:  # noqa: BLE001
                        results.append(failed_result(case, target_root, "direct_controller_history", exc))
                else:
                    results.append(skipped_result(case, target_root, "direct_controller_history", "direct validation disabled"))
                if config.include_gateway:
                    try:
                        results.append(gateway_history_case(config, policy=policy, case=case, target_root=target_root))
                    except Exception as exc:  # noqa: BLE001
                        results.append(failed_result(case, target_root, "gateway_history_payload", exc))
                else:
                    results.append(skipped_result(case, target_root, "gateway_history_payload", "gateway validation disabled"))
                if config.include_anythingllm and api_key:
                    try:
                        results.append(
                            anythingllm_same_session_case(
                                config,
                                policy=policy,
                                case=case,
                                target_root=target_root,
                                api_key=api_key,
                            )
                        )
                    except Exception as exc:  # noqa: BLE001
                        results.append(failed_result(case, target_root, "anythingllm_same_session", exc))
                elif config.include_anythingllm:
                    results.append(skipped_result(case, target_root, "anythingllm_same_session", f"{config.api_key_env} missing"))
                else:
                    results.append(skipped_result(case, target_root, "anythingllm_same_session", "AnythingLLM validation disabled"))
    errors.extend(
        error
        for item in results
        for error in string_list(item.get("errors"))
        if item.get("status") != ConversationIsolationStatus.PASSED.value
    )
    summary = build_summary(results, policy_errors)
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": ConversationIsolationStatus.PASSED.value if results and not errors else ConversationIsolationStatus.FAILED.value,
        "created_at": utc_timestamp(),
        "config_root": str(config_root),
        "policy_path": str(policy_path),
        "policy_sha256": hashlib.sha256(policy_path.read_bytes()).hexdigest() if policy_path.is_file() else None,
        "policy_errors": policy_errors,
        "summary": summary,
        "results": results,
        "errors": errors,
    }
    validation_errors = validate_report(report, policy)
    if validation_errors:
        report["status"] = ConversationIsolationStatus.FAILED.value
        report["errors"] = errors + validation_errors
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    if config.markdown_output_path:
        write_text(config.markdown_output_path, markdown_report(report))
        report["markdown_report_path"] = str(config.markdown_output_path.resolve())
        write_json(output_path, report)
    return report


def failed_result(case: dict[str, Any], target_root: str, surface: str, exc: Exception) -> dict[str, Any]:
    return {
        "case_id": case.get("case_id"),
        "surface": surface,
        "target_root": target_root,
        "status": ConversationIsolationStatus.FAILED.value,
        "run_id": "unknown",
        "errors": [f"{surface} failed: {type(exc).__name__}: {exc}"],
    }
