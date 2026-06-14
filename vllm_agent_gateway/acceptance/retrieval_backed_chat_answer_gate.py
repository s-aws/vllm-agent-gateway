"""Phase 218 retrieval-backed chat answer gate."""

from __future__ import annotations

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
)
from vllm_agent_gateway.controller_service.server import (
    ControllerServiceConfig,
    handle_workflow_router_chat_completion,
)
from vllm_agent_gateway.controllers.large_context.retrieval_answer import (
    RetrievalBackedChatAnswerRequest,
    invoke_retrieval_backed_chat_answer,
    target_matches_indexed_corpus,
)
from vllm_agent_gateway.controllers.workflow_router.plan import (
    WorkflowRouterPlanRequest,
    invoke_workflow_router_plan,
    route_request,
    should_invoke_large_context_retrieval,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "retrieval_backed_chat_answer_gate_policy"
EXPECTED_REPORT_KIND = "retrieval_backed_chat_answer_gate_report"
EXPECTED_PHASE = 218
EXPECTED_BACKLOG_ID = "P0-M6-218"
EXPECTED_MILESTONE_IDS = {"M6", "M16"}
DEFAULT_POLICY_PATH = Path("runtime") / "retrieval_backed_chat_answer_gate_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase218" / "phase218-retrieval-backed-chat-answer-gate-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase218" / "phase218-retrieval-backed-chat-answer-gate-report.md"
REQUIRED_OUT_OF_SCOPE = {
    "artifact_paging",
    "full_context_strategy_router",
    "raw_1m_prompt_support_claim",
    "vector_search_replacement",
    "new_chat_endpoint",
    "protected_fixture_mutation",
}


@dataclass(frozen=True)
class RetrievalBackedChatAnswerGateConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    require_artifacts: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def validation_error(error_id: str, message: str, *, severity: str = "high", source: str = "policy") -> dict[str, str]:
    return {"id": error_id, "severity": severity, "source": source, "message": message}


def positive_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "policy.schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"policy.kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "policy.phase must be 218"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be M6 and M16"))
    precondition = dict_value(policy.get("phase217_precondition"))
    for key in ("report_path", "required_status"):
        if not isinstance(precondition.get(key), str) or not str(precondition.get(key)).strip():
            errors.append(validation_error(f"policy.phase217_precondition.{key}", f"{key} must be non-empty"))
    if precondition.get("required_phase218_ready") is not True:
        errors.append(validation_error("policy.phase217_precondition.required_phase218_ready", "required_phase218_ready must be true"))
    if precondition.get("retrieval_backed_chat_integration_in_scope_must_be") is not False:
        errors.append(
            validation_error(
                "policy.phase217_precondition.retrieval_backed_chat_integration_in_scope_must_be",
                "Phase 217 must not already include retrieval-backed chat integration",
            )
        )
    if not isinstance(policy.get("context_index_policy_path"), str) or not policy["context_index_policy_path"].strip():
        errors.append(validation_error("policy.context_index_policy_path", "context_index_policy_path must be non-empty"))
    if not isinstance(policy.get("target_root"), str) or not policy["target_root"].strip():
        errors.append(validation_error("policy.target_root", "target_root must be non-empty"))
    for key in ("target_input_limit", "model_context_limit", "max_evidence_refs"):
        if positive_int(policy.get(key)) is None:
            errors.append(validation_error(f"policy.{key}", f"{key} must be a positive integer"))
    contract = dict_value(policy.get("answer_contract"))
    expected_contract = {
        "existing_workflow_path_only": True,
        "new_chat_endpoint_allowed": False,
        "summary_answer_required": True,
        "source_text_from_index_allowed": False,
        "source_text_in_artifacts_allowed": False,
        "raw_prompt_stuffing_allowed": False,
        "limitations_required": True,
        "confidence_required": True,
    }
    for key, expected in expected_contract.items():
        if contract.get(key) is not expected:
            errors.append(validation_error(f"policy.answer_contract.{key}", f"{key} must be {expected}"))
    minimums = dict_value(policy.get("minimums"))
    for key in ("prompt_case_count", "holdout_case_count", "negative_control_count", "router_case_count", "chat_case_count"):
        if positive_int(minimums.get(key)) is None:
            errors.append(validation_error(f"policy.minimums.{key}", f"{key} must be a positive integer"))
    cases = object_list(policy.get("prompt_cases"))
    if len(cases) < int(minimums.get("prompt_case_count", 0) or 0):
        errors.append(validation_error("policy.prompt_cases", "not enough prompt cases"))
    categories = {str(item.get("category")) for item in cases}
    for required in (
        "large_corpus_navigation",
        "large_corpus_evidence_lookup",
        "large_corpus_summarization",
        "large_corpus_limitations",
    ):
        if required not in categories:
            errors.append(validation_error("policy.prompt_cases.categories", f"missing {required}"))
    for collection_name in ("prompt_cases", "holdout_cases"):
        for index, case in enumerate(object_list(policy.get(collection_name))):
            prefix = f"policy.{collection_name}[{index}]"
            for key in ("case_id", "category", "prompt"):
                if not isinstance(case.get(key), str) or not str(case.get(key)).strip():
                    errors.append(validation_error(f"{prefix}.{key}", f"{key} must be non-empty"))
            if not isinstance(case.get("minimum_evidence_refs"), int) or isinstance(case.get("minimum_evidence_refs"), bool):
                errors.append(validation_error(f"{prefix}.minimum_evidence_refs", "minimum_evidence_refs must be integer"))
    if len(object_list(policy.get("negative_controls"))) < int(minimums.get("negative_control_count", 0) or 0):
        errors.append(validation_error("policy.negative_controls", "not enough negative controls"))
    missing_out_of_scope = sorted(REQUIRED_OUT_OF_SCOPE - set(string_list(policy.get("out_of_scope"))))
    if missing_out_of_scope:
        errors.append(validation_error("policy.out_of_scope", f"missing boundaries: {missing_out_of_scope}"))
    if policy.get("acceptance_marker") != "PHASE218 RETRIEVAL BACKED CHAT ANSWER GATE PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 218"))
    return errors


def load_report(
    config_root: Path,
    raw_path: object,
    *,
    source: str,
    require_artifacts: bool,
) -> tuple[Path | None, dict[str, Any], list[dict[str, str]]]:
    path = resolve_path(config_root, raw_path) if isinstance(raw_path, str) else None
    if path is None or not path.is_file():
        if require_artifacts:
            return path, {}, [validation_error(f"{source}.missing", f"{source} report is required", source=source)]
        return path, {}, []
    try:
        return path, read_json_object(path), []
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        return path, {}, [validation_error(f"{source}.malformed", f"{source} report is malformed: {exc}", source=source)]


def validate_phase217_precondition(policy: dict[str, Any], phase217_report: dict[str, Any]) -> list[dict[str, str]]:
    if not phase217_report:
        return []
    errors: list[dict[str, str]] = []
    precondition = dict_value(policy.get("phase217_precondition"))
    summary = dict_value(phase217_report.get("summary"))
    if phase217_report.get("status") != precondition.get("required_status"):
        errors.append(validation_error("phase217_report.status", "Phase 217 report status must be passed", source="phase217"))
    if summary.get("phase218_ready") is not precondition.get("required_phase218_ready"):
        errors.append(validation_error("phase217_report.phase218_ready", "Phase 217 must mark phase218_ready", source="phase217"))
    if summary.get("retrieval_backed_chat_integration_in_scope") is not precondition.get(
        "retrieval_backed_chat_integration_in_scope_must_be"
    ):
        errors.append(
            validation_error(
                "phase217_report.retrieval_backed_chat_integration_in_scope",
                "Phase 217 must not already include retrieval-backed chat integration",
                source="phase217",
            )
        )
    return errors


def case_prompt(case: dict[str, Any], target_root: Path) -> str:
    return f"In {target_root}, {str(case.get('prompt', '')).strip()}"


def answer_has_terms(answer: str, terms: list[str]) -> list[str]:
    lower_answer = answer.lower()
    return [term for term in terms if term.lower() not in lower_answer]


def direct_case_result(
    *,
    config_root: Path,
    target_root: Path,
    output_root: Path,
    case: dict[str, Any],
    max_evidence_refs: int,
    target_input_limit: int,
    model_context_limit: int,
    context_index_policy_path: str,
) -> dict[str, Any]:
    prompt = case_prompt(case, target_root)
    result = invoke_retrieval_backed_chat_answer(
        RetrievalBackedChatAnswerRequest(
            config_root=config_root,
            target_root=target_root,
            output_root=output_root,
            user_request=prompt,
            context_index_policy_path=context_index_policy_path,
            max_evidence_refs=max_evidence_refs,
            target_input_limit=target_input_limit,
            model_context_limit=model_context_limit,
        )
    )
    report = result.report if isinstance(result.report, dict) else {}
    evidence_refs = object_list(report.get("evidence_refs"))
    prompt_budget = dict_value(report.get("prompt_budget"))
    answer = str(report.get("answer") or "")
    missing_terms = answer_has_terms(answer, string_list(case.get("required_answer_terms")))
    expected_evidence = int(case.get("minimum_evidence_refs", 0))
    passed = (
        report.get("status") == "answered"
        and str(report.get("category")) == str(case.get("category"))
        and len(evidence_refs) >= expected_evidence
        and prompt_budget.get("raw_prompt_stuffing") is False
        and prompt_budget.get("within_target_input_limit") is True
        and not missing_terms
    )
    return {
        "case_id": case.get("case_id"),
        "category": case.get("category"),
        "status": report.get("status"),
        "passed": passed,
        "artifact": result.artifact_paths.get("retrieval_backed_chat_answer"),
        "answer_present": bool(answer),
        "evidence_ref_count": len(evidence_refs),
        "minimum_evidence_refs": expected_evidence,
        "raw_prompt_stuffing": prompt_budget.get("raw_prompt_stuffing"),
        "within_target_input_limit": prompt_budget.get("within_target_input_limit"),
        "missing_answer_terms": missing_terms,
    }


def router_case_result(
    *,
    config_root: Path,
    target_root: Path,
    output_root: Path,
    case: dict[str, Any],
    context_index_policy_path: str,
) -> dict[str, Any]:
    prompt = case_prompt(case, target_root)
    result = invoke_workflow_router_plan(
        WorkflowRouterPlanRequest(
            config_root=config_root,
            target_root=target_root,
            output_root=output_root,
            user_request=prompt,
            mode="execute_read_only",
            budgets={"max_model_calls": 0, "max_selected_skills": 5, "max_selected_tools": 5},
            context={"context_index_policy_path": context_index_policy_path},
        )
    )
    summary = dict_value(dict_value(result.report).get("summary"))
    decision = dict_value(dict_value(result.report).get("decision"))
    large_context = dict_value(decision.get("large_context_retrieval"))
    passed = (
        result.status.value == "completed"
        and large_context.get("status") == "invoked"
        and isinstance(summary.get("answer"), str)
        and bool(str(summary.get("answer")).strip())
        and summary.get("retrieval_status") == "answered"
        and summary.get("raw_prompt_stuffing") is False
    )
    return {
        "case_id": case.get("case_id"),
        "passed": passed,
        "route_status": summary.get("route_status"),
        "selected_workflow": summary.get("selected_workflow"),
        "downstream_workflow": summary.get("downstream_workflow"),
        "retrieval_status": summary.get("retrieval_status"),
        "retrieval_evidence_count": summary.get("retrieval_evidence_count"),
        "answer_present": isinstance(summary.get("answer"), str) and bool(str(summary.get("answer")).strip()),
        "large_context_retrieval": large_context,
    }


def chat_case_result(
    *,
    config_root: Path,
    target_root: Path,
    output_root: Path,
    case: dict[str, Any],
    context_index_policy_path: str,
) -> dict[str, Any]:
    prompt = case_prompt(case, target_root)
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=output_root,
        allowed_target_roots=(config_root, target_root),
    )
    body = handle_workflow_router_chat_completion(
        {
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": prompt}],
            "context": {"context_index_policy_path": context_index_policy_path},
        },
        config,
    )
    content = str(body.get("choices", [{}])[0].get("message", {}).get("content", ""))
    response = dict_value(body.get("agentic_controller_response"))
    summary = dict_value(response.get("summary"))
    expected_evidence = int(case.get("minimum_evidence_refs", 0))
    chunk_required = expected_evidence > 0
    passed = (
        content.startswith("Answer:\n")
        and "source" in content.lower()
        and (not chunk_required or "chunk" in content.lower())
        and summary.get("retrieval_status") == "answered"
        and summary.get("raw_prompt_stuffing") is False
    )
    return {
        "case_id": case.get("case_id"),
        "passed": passed,
        "content_starts_with_answer": content.startswith("Answer:\n"),
        "content_has_source": "source" in content.lower(),
        "content_has_chunk": "chunk" in content.lower(),
        "retrieval_status": summary.get("retrieval_status"),
        "retrieval_evidence_count": summary.get("retrieval_evidence_count"),
        "run_id": response.get("run_id"),
    }


def negative_control_result(
    *,
    config_root: Path,
    target_root: Path,
    output_root: Path,
    control: dict[str, Any],
    context_index_policy_path: str,
) -> dict[str, Any]:
    kind = control.get("kind")
    if kind == "unapproved_root":
        unapproved = config_root / "runtime-state" / "phase216" / "corpus-safety-negative-controls"
        passed = target_matches_indexed_corpus(config_root, unapproved) is False
        return {"case_id": control.get("case_id"), "kind": kind, "status": "rejected", "passed": passed}
    if kind == "small_repo_non_regression":
        request = WorkflowRouterPlanRequest(
            config_root=config_root,
            target_root=config_root,
            user_request="In this repository, identify the most relevant modules for the order replay pipeline.",
            mode="execute_read_only",
            budgets={"max_model_calls": 0, "max_selected_skills": 5, "max_selected_tools": 5},
        )
        decision = route_request(request, {"max_model_calls": 0, "max_selected_skills": 5, "max_selected_tools": 5})
        intercepted = should_invoke_large_context_retrieval(request, decision)
        return {"case_id": control.get("case_id"), "kind": kind, "status": "not_intercepted", "passed": intercepted is False}
    if kind == "unavailable_private_evidence":
        result = invoke_retrieval_backed_chat_answer(
            RetrievalBackedChatAnswerRequest(
                config_root=config_root,
                target_root=target_root,
                output_root=output_root,
                user_request=case_prompt(control, target_root),
                context_index_policy_path=context_index_policy_path,
            )
        )
        report = dict_value(result.report)
        answer = str(report.get("answer") or "")
        passed = report.get("status") == "blocked" and "cannot retrieve private" in answer.lower()
        return {"case_id": control.get("case_id"), "kind": kind, "status": report.get("status"), "passed": passed}
    if kind == "raw_1m_claim":
        result = invoke_retrieval_backed_chat_answer(
            RetrievalBackedChatAnswerRequest(
                config_root=config_root,
                target_root=target_root,
                output_root=output_root,
                user_request=case_prompt(control, target_root),
                context_index_policy_path=context_index_policy_path,
            )
        )
        report = dict_value(result.report)
        answer = str(report.get("answer") or "")
        prompt_budget = dict_value(report.get("prompt_budget"))
        passed = report.get("status") == "answered" and answer.lower().startswith("no.") and prompt_budget.get("raw_prompt_stuffing") is False
        return {"case_id": control.get("case_id"), "kind": kind, "status": "answered_with_refusal", "passed": passed}
    return {"case_id": control.get("case_id"), "kind": kind, "status": "unknown_negative_control", "passed": False}


def validate_sanitized_report(report: dict[str, Any]) -> list[dict[str, str]]:
    serialized = json.dumps(report, sort_keys=True)
    errors: list[dict[str, str]] = []
    for forbidden in (
        "DUMMY_SECRET_DO_NOT_USE",
        "PHASE216_DUMMY_SECRET_DO_NOT_EXPOSE",
        "ignored generated note",
        "local runtime artifact",
    ):
        if forbidden in serialized:
            errors.append(validation_error("report.rejected_content_leak", f"report contains rejected marker {forbidden}", source="report"))
    for field in ('"source_text"', '"chunk_text"', '"snippet"', '"content"'):
        if field in serialized:
            errors.append(validation_error("report.source_text_field", f"report contains forbidden field {field}", source="report"))
    return errors


def build_report(config: RetrievalBackedChatAnswerGateConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    policy = read_json_object(policy_path)
    policy_errors = validate_policy(policy)
    phase217_path, phase217_report, phase217_errors = load_report(
        config_root,
        dict_value(policy.get("phase217_precondition")).get("report_path"),
        source="phase217_report",
        require_artifacts=config.require_artifacts,
    )
    phase217_precondition_errors = validate_phase217_precondition(policy, phase217_report)
    target_root = resolve_path(config_root, str(policy.get("target_root"))).resolve()
    output_root = output_path.parent / "case-artifacts"
    max_evidence_refs = int(policy.get("max_evidence_refs", 4))
    target_input_limit = int(policy.get("target_input_limit", 24000))
    model_context_limit = int(policy.get("model_context_limit", 65536))
    context_index_policy_path = str(policy.get("context_index_policy_path"))
    direct_cases = [
        direct_case_result(
            config_root=config_root,
            target_root=target_root,
            output_root=output_root / "direct",
            case=case,
            max_evidence_refs=max_evidence_refs,
            target_input_limit=target_input_limit,
            model_context_limit=model_context_limit,
            context_index_policy_path=context_index_policy_path,
        )
        for case in object_list(policy.get("prompt_cases"))
    ]
    holdout_cases = [
        direct_case_result(
            config_root=config_root,
            target_root=target_root,
            output_root=output_root / "holdouts",
            case=case,
            max_evidence_refs=max_evidence_refs,
            target_input_limit=target_input_limit,
            model_context_limit=model_context_limit,
            context_index_policy_path=context_index_policy_path,
        )
        for case in object_list(policy.get("holdout_cases"))
    ]
    router_cases = [
        router_case_result(
            config_root=config_root,
            target_root=target_root,
            output_root=output_root / "router",
            case=case,
            context_index_policy_path=context_index_policy_path,
        )
        for case in object_list(policy.get("prompt_cases"))
    ]
    chat_cases = [
        chat_case_result(
            config_root=config_root,
            target_root=target_root,
            output_root=output_root / "chat",
            case=case,
            context_index_policy_path=context_index_policy_path,
        )
        for case in object_list(policy.get("prompt_cases"))
    ]
    negative_controls = [
        negative_control_result(
            config_root=config_root,
            target_root=target_root,
            output_root=output_root / "negative",
            control=control,
            context_index_policy_path=context_index_policy_path,
        )
        for control in object_list(policy.get("negative_controls"))
    ]
    validation_errors: list[dict[str, str]] = policy_errors + phase217_errors + phase217_precondition_errors
    for collection_name, results in (
        ("direct_cases", direct_cases),
        ("holdout_cases", holdout_cases),
        ("router_cases", router_cases),
        ("chat_cases", chat_cases),
        ("negative_controls", negative_controls),
    ):
        for item in results:
            if item.get("passed") is not True:
                validation_errors.append(
                    validation_error(
                        f"{collection_name}.{item.get('case_id')}",
                        f"{collection_name} case did not pass: {item}",
                        source=collection_name,
                    )
                )
    status = "passed" if not validation_errors else "failed"
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": sorted(EXPECTED_MILESTONE_IDS),
        "generated_at": utc_timestamp(),
        "status": status,
        "policy_path": str(policy_path),
        "policy_sha256": sha256_file(policy_path) if policy_path.is_file() else None,
        "output_path": str(output_path),
        "phase217_report_path": str(phase217_path) if phase217_path is not None else None,
        "phase217_report_sha256": sha256_file(phase217_path) if phase217_path is not None and phase217_path.is_file() else None,
        "target_root": str(target_root),
        "direct_case_results": direct_cases,
        "holdout_case_results": holdout_cases,
        "router_case_results": router_cases,
        "chat_case_results": chat_cases,
        "negative_control_results": negative_controls,
        "out_of_scope": string_list(policy.get("out_of_scope")),
        "live_closeout": {
            "required_before_phase_close": dict_value(policy.get("live_closeout")).get("required_before_phase_close") is True,
            "status": "not_run_by_offline_validator",
        },
        "validation_errors": validation_errors,
        "summary": {
            "direct_case_count": len(direct_cases),
            "direct_passed_count": len([item for item in direct_cases if item.get("passed") is True]),
            "holdout_case_count": len(holdout_cases),
            "holdout_passed_count": len([item for item in holdout_cases if item.get("passed") is True]),
            "router_case_count": len(router_cases),
            "router_passed_count": len([item for item in router_cases if item.get("passed") is True]),
            "chat_case_count": len(chat_cases),
            "chat_passed_count": len([item for item in chat_cases if item.get("passed") is True]),
            "negative_control_count": len(negative_controls),
            "negative_control_passed_count": len([item for item in negative_controls if item.get("passed") is True]),
            "summary_answer_required": dict_value(policy.get("answer_contract")).get("summary_answer_required"),
            "raw_prompt_stuffing_allowed": dict_value(policy.get("answer_contract")).get("raw_prompt_stuffing_allowed"),
            "new_chat_endpoint_allowed": dict_value(policy.get("answer_contract")).get("new_chat_endpoint_allowed"),
            "live_closeout_required": dict_value(policy.get("live_closeout")).get("required_before_phase_close") is True,
            "phase219_ready": status == "passed",
            "validation_error_count": len(validation_errors),
        },
    }
    leak_errors = validate_sanitized_report(report)
    if leak_errors:
        report["validation_errors"] = validation_errors + leak_errors
        report["status"] = "failed"
        report["summary"]["phase219_ready"] = False
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
    return report


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Retrieval-Backed Chat Answer Gate",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Direct cases: `{summary.get('direct_passed_count')}/{summary.get('direct_case_count')}`",
        f"- Holdouts: `{summary.get('holdout_passed_count')}/{summary.get('holdout_case_count')}`",
        f"- Router cases: `{summary.get('router_passed_count')}/{summary.get('router_case_count')}`",
        f"- Chat cases: `{summary.get('chat_passed_count')}/{summary.get('chat_case_count')}`",
        f"- Negative controls: `{summary.get('negative_control_passed_count')}/{summary.get('negative_control_count')}`",
        f"- Phase 219 ready: `{summary.get('phase219_ready')}`",
        "",
        "## Direct Cases",
    ]
    for item in object_list(report.get("direct_case_results")):
        lines.append(
            f"- `{item.get('case_id')}` passed `{item.get('passed')}` evidence `{item.get('evidence_ref_count')}` "
            f"artifact `{item.get('artifact')}`"
        )
    lines.extend(["", "## Router Cases"])
    for item in object_list(report.get("router_case_results")):
        lines.append(f"- `{item.get('case_id')}` passed `{item.get('passed')}` downstream `{item.get('downstream_workflow')}`")
    lines.extend(["", "## Chat Cases"])
    for item in object_list(report.get("chat_case_results")):
        lines.append(f"- `{item.get('case_id')}` passed `{item.get('passed')}` run `{item.get('run_id')}`")
    lines.extend(["", "## Negative Controls"])
    for item in object_list(report.get("negative_control_results")):
        lines.append(f"- `{item.get('case_id')}` `{item.get('kind')}` passed `{item.get('passed')}`")
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(["", "## Validation Errors"])
        for item in errors:
            lines.append(f"- `{item.get('id')}` ({item.get('severity')}): {item.get('message')}")
    return "\n".join(lines) + "\n"


def run_retrieval_backed_chat_answer_gate(config: RetrievalBackedChatAnswerGateConfig) -> dict[str, Any]:
    report = build_report(config)
    output_path = resolve_path(config.config_root.resolve(), config.output_path)
    markdown_output_path = resolve_path(config.config_root.resolve(), config.markdown_output_path)
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown_report(report))
    return report
