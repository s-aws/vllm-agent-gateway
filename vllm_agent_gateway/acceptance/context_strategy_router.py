"""Phase 220 context strategy router acceptance gate."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.context_index_prototype import (
    dict_value,
    object_list,
    read_json_object,
    resolve_path,
    sha256_file,
    string_list,
    write_json,
)
from vllm_agent_gateway.controller_service.server import (
    ControllerServiceConfig,
    handle_workflow_router_chat_completion,
)
from vllm_agent_gateway.controllers.workflow_router.plan import (
    WorkflowRouterPlanRequest,
    invoke_workflow_router_plan,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "context_strategy_router_policy"
EXPECTED_REPORT_KIND = "context_strategy_router_report"
EXPECTED_PHASE = 220
EXPECTED_BACKLOG_ID = "P0-M8-220"
EXPECTED_MILESTONE_IDS = {"M8"}
DEFAULT_POLICY_PATH = Path("runtime") / "context_strategy_router_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase220" / "phase220-context-strategy-router-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase220" / "phase220-context-strategy-router-report.md"
REQUIRED_STRATEGIES = {
    "direct_context",
    "retrieval",
    "chunked_investigation",
    "summarization",
    "artifact_paging",
    "refusal",
}
REQUIRED_OUT_OF_SCOPE = {
    "new_chat_endpoint",
    "raw_1m_prompt_support_claim",
    "second_large_context_router",
    "vector_search_replacement",
    "protected_fixture_mutation",
    "advanced_refactor_reactivation",
}


@dataclass(frozen=True)
class ContextStrategyRouterConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    require_artifacts: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def validation_error(error_id: str, message: str, *, severity: str = "high", source: str = "policy") -> dict[str, str]:
    return {"id": error_id, "severity": severity, "source": source, "message": message}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "policy.schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"policy.kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "policy.phase must be 220"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be exactly M8"))
    if set(string_list(policy.get("required_strategy_ids"))) != REQUIRED_STRATEGIES:
        errors.append(validation_error("policy.required_strategy_ids", "required_strategy_ids must define the six Phase 215 strategies"))
    for key in ("phase215_policy_path", "target_root", "context_index_policy_path"):
        if not isinstance(policy.get(key), str) or not policy[key].strip():
            errors.append(validation_error(f"policy.{key}", f"{key} must be non-empty"))
    required_inputs = string_list(policy.get("required_routing_inputs"))
    for required in (
        "prompt_intent",
        "target_root",
        "estimated_corpus_tokens",
        "requested_specificity",
        "output_format",
        "mutation_intent",
        "index_safety_status",
        "source_freshness_status",
        "context_budget",
        "ambiguity_level",
    ):
        if required not in required_inputs:
            errors.append(validation_error("policy.required_routing_inputs", f"missing routing input {required}"))
    decision_cases = object_list(policy.get("decision_cases"))
    case_strategies = {str(case.get("expected_strategy")) for case in decision_cases}
    if case_strategies != REQUIRED_STRATEGIES:
        errors.append(validation_error("policy.decision_cases", "decision_cases must cover every strategy"))
    for case in decision_cases + object_list(policy.get("negative_controls")):
        for key in ("case_id", "target_root_kind", "mode", "prompt", "expected_strategy", "expected_strategy_status", "expected_execution_path"):
            if not isinstance(case.get(key), str) or not str(case.get(key)).strip():
                errors.append(validation_error(f"policy.case.{key}", f"{case.get('case_id', '<missing>')} missing {key}"))
        if case.get("expected_strategy") not in REQUIRED_STRATEGIES:
            errors.append(validation_error(f"policy.case.{case.get('case_id')}.expected_strategy", "unknown expected strategy"))
    contract = dict_value(policy.get("answer_contract"))
    expected_contract = {
        "answer_first_required": True,
        "artifact_only_allowed": False,
        "new_chat_endpoint_allowed": False,
        "raw_prompt_stuffing_allowed": False,
        "chat_visible_strategy_required": True,
    }
    for key, expected in expected_contract.items():
        if contract.get(key) is not expected:
            errors.append(validation_error(f"policy.answer_contract.{key}", f"{key} must be {expected}"))
    missing = sorted(REQUIRED_OUT_OF_SCOPE - set(string_list(policy.get("out_of_scope"))))
    if missing:
        errors.append(validation_error("policy.out_of_scope", f"missing boundaries: {missing}"))
    if policy.get("acceptance_marker") != "PHASE220 CONTEXT STRATEGY ROUTER PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 220"))
    return errors


def load_report(config_root: Path, raw_path: object, *, source: str, require_artifacts: bool) -> tuple[Path | None, dict[str, Any], list[dict[str, str]]]:
    path = resolve_path(config_root, raw_path) if isinstance(raw_path, str) else None
    if path is None or not path.is_file():
        if require_artifacts:
            return path, {}, [validation_error(f"{source}.missing", f"{source} report is required", source=source)]
        return path, {}, []
    try:
        return path, read_json_object(path), []
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        return path, {}, [validation_error(f"{source}.malformed", f"{source} report is malformed: {exc}", source=source)]


def target_root_for_case(config_root: Path, policy: dict[str, Any], case: dict[str, Any]) -> Path:
    kind = str(case.get("target_root_kind"))
    if kind == "config_root":
        return config_root
    if kind == "large_corpus":
        return resolve_path(config_root, str(policy.get("target_root"))).resolve()
    raise RuntimeError(f"unsupported target_root_kind: {kind}")


def context_for_case(config_root: Path, policy: dict[str, Any], case: dict[str, Any], output_root: Path) -> dict[str, Any]:
    context = {"context_index_policy_path": str(resolve_path(config_root, str(policy.get("context_index_policy_path"))))}
    if case.get("kind") != "stale_index_or_source_hash":
        return context
    original_policy_path = resolve_path(config_root, str(policy.get("context_index_policy_path")))
    original_policy = read_json_object(original_policy_path)
    original_index_path = resolve_path(config_root, str(dict_value(original_policy.get("index_artifact")).get("path")))
    mutated_index = copy.deepcopy(read_json_object(original_index_path))
    chunks = object_list(mutated_index.get("chunks"))
    if chunks:
        chunks[0]["source_sha256"] = "0" * 64
        mutated_index["chunks"] = chunks
    stale_dir = output_root / "stale-index-control"
    stale_index_path = stale_dir / "stale-context-index.json"
    stale_policy_path = stale_dir / "stale-context-index-policy.json"
    write_json(stale_index_path, mutated_index)
    mutated_policy = copy.deepcopy(original_policy)
    mutated_policy["index_artifact"] = {**dict_value(mutated_policy.get("index_artifact")), "path": str(stale_index_path)}
    write_json(stale_policy_path, mutated_policy)
    return {"context_index_policy_path": str(stale_policy_path)}


def case_prompt(case: dict[str, Any], target_root: Path) -> str:
    prompt = str(case.get("prompt") or "").strip()
    if prompt.lower().startswith("in "):
        return prompt
    return f"In {target_root}, {prompt}"


def expected_bool(value: object, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def route_case(config_root: Path, policy: dict[str, Any], output_root: Path, case: dict[str, Any]) -> dict[str, Any]:
    target_root = target_root_for_case(config_root, policy, case)
    request_context = context_for_case(config_root, policy, case, output_root)
    result = invoke_workflow_router_plan(
        WorkflowRouterPlanRequest(
            config_root=config_root,
            target_root=target_root,
            output_root=output_root / "workflow-router",
            user_request=case_prompt(case, target_root),
            mode=str(case.get("mode") or "execute_read_only"),
            budgets={"max_model_calls": 0, "max_selected_skills": 5, "max_selected_tools": 5},
            context=request_context,
        )
    )
    report = dict_value(result.report)
    summary = dict_value(report.get("summary"))
    decision = dict_value(report.get("decision"))
    strategy = dict_value(decision.get("context_strategy"))
    errors: list[str] = []
    if strategy.get("selected_strategy") != case.get("expected_strategy"):
        errors.append("selected_strategy_mismatch")
    if strategy.get("status") != case.get("expected_strategy_status"):
        errors.append("strategy_status_mismatch")
    if strategy.get("execution_path") != case.get("expected_execution_path"):
        errors.append("execution_path_mismatch")
    expected_route_status = case.get("expected_route_status")
    if isinstance(expected_route_status, str) and summary.get("route_status") != expected_route_status:
        errors.append("route_status_mismatch")
    required_inputs = set(string_list(policy.get("required_routing_inputs")))
    if not required_inputs.issubset(set(string_list(strategy.get("routing_inputs_used")))):
        errors.append("missing_routing_inputs")
    if len(object_list(strategy.get("rejected_strategies"))) < len(REQUIRED_STRATEGIES) - 1:
        errors.append("missing_rejected_strategies")
    if not string_list(strategy.get("rationale")):
        errors.append("missing_rationale")
    if not string_list(strategy.get("safe_alternatives")):
        errors.append("missing_safe_alternatives")
    expect_downstream = expected_bool(case.get("expect_downstream"))
    has_downstream = isinstance(summary.get("downstream_workflow"), str) and bool(summary.get("downstream_workflow"))
    if expect_downstream and not has_downstream:
        errors.append("missing_expected_downstream")
    if not expect_downstream and has_downstream:
        errors.append("unexpected_downstream")
    if case.get("expected_execution_path") == "large_context.retrieval_answer":
        if summary.get("downstream_workflow") != "large_context.retrieval_answer":
            errors.append("retrieval_downstream_not_invoked")
        if summary.get("raw_prompt_stuffing") is not False:
            errors.append("raw_prompt_stuffing_not_false")
    if case.get("expected_execution_path") == "large_context.chunked_investigation":
        if summary.get("downstream_workflow") != "large_context.chunked_investigation":
            errors.append("chunked_downstream_not_invoked")
        if summary.get("raw_prompt_stuffing") is not False:
            errors.append("raw_prompt_stuffing_not_false")
        if summary.get("phase222_contract_satisfied") is not True:
            errors.append("phase222_contract_not_satisfied")
    return {
        "case_id": case.get("case_id"),
        "kind": case.get("kind", "decision_case"),
        "passed": not errors,
        "errors": errors,
        "run_id": report.get("run_id"),
        "route_status": summary.get("route_status"),
        "selected_strategy": strategy.get("selected_strategy"),
        "strategy_status": strategy.get("status"),
        "execution_path": strategy.get("execution_path"),
        "reason": strategy.get("reason"),
        "source_freshness_status": strategy.get("source_freshness_status"),
        "downstream_workflow": summary.get("downstream_workflow"),
        "chat_visible_strategy": summary.get("selected_context_strategy"),
        "route_decision_artifact": dict_value(report.get("artifacts")).get("route_decision"),
    }


def chat_case_result(config_root: Path, policy: dict[str, Any], output_root: Path) -> dict[str, Any]:
    target_root = resolve_path(config_root, str(policy.get("target_root"))).resolve()
    config = ControllerServiceConfig(config_root=config_root, output_root=output_root, allowed_target_roots=(config_root, target_root))
    body = handle_workflow_router_chat_completion(
        {
            "model": "agentic-workflow-router",
            "messages": [
                {
                    "role": "user",
                    "content": f"In {target_root}, produce a long evidence report with all relevant top files for the order replay pipeline.",
                }
            ],
        },
        config,
    )
    text = str(body.get("choices", [{}])[0].get("message", {}).get("content", ""))
    summary = dict_value(dict_value(body.get("agentic_controller_response")).get("summary"))
    passed = (
        text.startswith("Answer:\n")
        and "selected_context_strategy" in text
        and "context_strategy_rationale" in text
        and summary.get("selected_context_strategy") == "artifact_paging"
        and summary.get("context_strategy_execution_path") == "large_context.retrieval_answer"
        and isinstance(summary.get("context_strategy_rationale"), str)
        and bool(summary.get("context_strategy_rationale"))
        and summary.get("raw_prompt_stuffing") is False
    )
    return {
        "case_id": "P220-CHAT-001",
        "passed": passed,
        "answer_first": text.startswith("Answer:\n"),
        "has_chat_visible_strategy": "selected_context_strategy" in text,
        "has_chat_visible_rationale": "context_strategy_rationale" in text,
        "selected_context_strategy": summary.get("selected_context_strategy"),
        "execution_path": summary.get("context_strategy_execution_path"),
        "run_id": dict_value(body.get("agentic_controller_response")).get("run_id"),
    }


def validate_phase219_precondition(policy: dict[str, Any], phase219_report: dict[str, Any]) -> list[dict[str, str]]:
    if not phase219_report:
        return []
    errors: list[dict[str, str]] = []
    precondition = dict_value(policy.get("phase219_precondition"))
    summary = dict_value(phase219_report.get("summary"))
    if phase219_report.get("status") != precondition.get("required_status"):
        errors.append(validation_error("phase219_report.status", "Phase 219 report status must be passed", source="phase219"))
    if summary.get("phase220_ready") is not precondition.get("required_phase220_ready"):
        errors.append(validation_error("phase219_report.phase220_ready", "Phase 219 must mark phase220_ready", source="phase219"))
    return errors


def build_report(config: ContextStrategyRouterConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    policy = read_json_object(policy_path)
    policy_errors = validate_policy(policy)
    phase219_path, phase219_report, phase219_errors = load_report(
        config_root,
        dict_value(policy.get("phase219_precondition")).get("report_path"),
        source="phase219_report",
        require_artifacts=config.require_artifacts,
    )
    phase219_precondition_errors = validate_phase219_precondition(policy, phase219_report)
    output_root = output_path.parent / "case-artifacts"
    decision_results = [route_case(config_root, policy, output_root / "decision", case) for case in object_list(policy.get("decision_cases"))]
    negative_results = [route_case(config_root, policy, output_root / "negative", case) for case in object_list(policy.get("negative_controls"))]
    chat_result = chat_case_result(config_root, policy, output_root / "chat")
    validation_errors: list[dict[str, str]] = policy_errors + phase219_errors + phase219_precondition_errors
    for name, results in (("decision_cases", decision_results), ("negative_controls", negative_results)):
        for item in results:
            if item.get("passed") is not True:
                validation_errors.append(validation_error(f"{name}.{item.get('case_id')}", f"{name} case did not pass: {item}", source=name))
    if chat_result.get("passed") is not True:
        validation_errors.append(validation_error("chat_case.P220-CHAT-001", f"chat case did not pass: {chat_result}", source="chat_case"))
    strategy_counts: dict[str, int] = {}
    for item in decision_results + negative_results:
        strategy = str(item.get("selected_strategy"))
        strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": sorted(EXPECTED_MILESTONE_IDS),
        "generated_at": utc_timestamp(),
        "status": "passed" if not validation_errors else "failed",
        "policy_path": str(policy_path),
        "policy_sha256": sha256_file(policy_path) if policy_path.is_file() else None,
        "output_path": str(output_path),
        "phase219_report_path": str(phase219_path) if phase219_path is not None else None,
        "phase219_report_sha256": sha256_file(phase219_path) if phase219_path is not None and phase219_path.is_file() else None,
        "decision_case_results": decision_results,
        "negative_control_results": negative_results,
        "chat_case_result": chat_result,
        "strategy_counts": strategy_counts,
        "validation_errors": validation_errors,
        "summary": {
            "decision_case_count": len(decision_results),
            "decision_passed_count": len([item for item in decision_results if item.get("passed") is True]),
            "negative_control_count": len(negative_results),
            "negative_control_passed_count": len([item for item in negative_results if item.get("passed") is True]),
            "chat_case_passed": chat_result.get("passed") is True,
            "strategy_count": len(strategy_counts),
            "required_strategy_count": len(REQUIRED_STRATEGIES),
            "all_strategies_covered": REQUIRED_STRATEGIES.issubset(set(strategy_counts)),
            "raw_prompt_stuffing_allowed": dict_value(policy.get("answer_contract")).get("raw_prompt_stuffing_allowed"),
            "chat_visible_strategy_required": dict_value(policy.get("answer_contract")).get("chat_visible_strategy_required"),
            "phase221_ready": not validation_errors,
            "validation_error_count": len(validation_errors),
        },
    }
    return report


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Context Strategy Router",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Decision cases: `{summary.get('decision_passed_count')}/{summary.get('decision_case_count')}`",
        f"- Negative controls: `{summary.get('negative_control_passed_count')}/{summary.get('negative_control_count')}`",
        f"- Chat case passed: `{summary.get('chat_case_passed')}`",
        f"- All strategies covered: `{summary.get('all_strategies_covered')}`",
        f"- Phase 221 ready: `{summary.get('phase221_ready')}`",
        "",
        "## Decision Cases",
    ]
    for item in object_list(report.get("decision_case_results")):
        lines.append(
            f"- `{item.get('case_id')}` -> `{item.get('selected_strategy')}` "
            f"status `{item.get('strategy_status')}` path `{item.get('execution_path')}` passed `{item.get('passed')}`"
        )
    lines.extend(["", "## Negative Controls"])
    for item in object_list(report.get("negative_control_results")):
        lines.append(
            f"- `{item.get('case_id')}` `{item.get('kind')}` -> `{item.get('selected_strategy')}` "
            f"reason `{item.get('reason')}` passed `{item.get('passed')}`"
        )
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(["", "## Validation Errors"])
        for item in errors:
            lines.append(f"- `{item.get('id')}` ({item.get('severity')}): {item.get('message')}")
    return "\n".join(lines) + "\n"


def run_context_strategy_router(config: ContextStrategyRouterConfig) -> dict[str, Any]:
    report = build_report(config)
    output_path = resolve_path(config.config_root.resolve(), config.output_path)
    markdown_output_path = resolve_path(config.config_root.resolve(), config.markdown_output_path)
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown_report(report))
    return report
