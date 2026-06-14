"""Phase 219 artifact paging and long-answer usability gate."""

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
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "artifact_paging_long_answer_usability_policy"
EXPECTED_REPORT_KIND = "artifact_paging_long_answer_usability_report"
EXPECTED_PHASE = 219
EXPECTED_BACKLOG_ID = "P0-M6-219"
EXPECTED_MILESTONE_IDS = {"M6", "M8", "M16"}
DEFAULT_POLICY_PATH = Path("runtime") / "artifact_paging_long_answer_usability_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase219" / "phase219-artifact-paging-long-answer-usability-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase219" / "phase219-artifact-paging-long-answer-usability-report.md"
DEFAULT_CONTEXT_INDEX_POLICY_PATH = Path("runtime") / "context_index_prototype_policy.json"
REQUIRED_OUT_OF_SCOPE = {
    "full_context_strategy_router",
    "raw_1m_prompt_support_claim",
    "vector_search_replacement",
    "new_chat_endpoint",
    "protected_fixture_mutation",
}


@dataclass(frozen=True)
class ArtifactPagingLongAnswerUsabilityConfig:
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
        errors.append(validation_error("policy.phase", "policy.phase must be 219"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be M6, M8, and M16"))
    precondition = dict_value(policy.get("phase218_precondition"))
    for key in ("report_path", "required_status"):
        if not isinstance(precondition.get(key), str) or not str(precondition.get(key)).strip():
            errors.append(validation_error(f"policy.phase218_precondition.{key}", f"{key} must be non-empty"))
    if precondition.get("required_phase219_ready") is not True:
        errors.append(validation_error("policy.phase218_precondition.required_phase219_ready", "required_phase219_ready must be true"))
    for key in (
        "target_root",
        "retrieval_answer_policy_path",
    ):
        if not isinstance(policy.get(key), str) or not policy[key].strip():
            errors.append(validation_error(f"policy.{key}", f"{key} must be non-empty"))
    for key in (
        "target_input_limit",
        "model_context_limit",
        "chat_evidence_ref_limit",
        "artifact_evidence_ref_limit",
        "artifact_page_size",
    ):
        if positive_int(policy.get(key)) is None:
            errors.append(validation_error(f"policy.{key}", f"{key} must be a positive integer"))
    contract = dict_value(policy.get("answer_contract"))
    expected = {
        "answer_first_required": True,
        "artifact_only_allowed": False,
        "new_chat_endpoint_allowed": False,
        "source_text_in_pages_allowed": False,
        "raw_prompt_stuffing_allowed": False,
        "json_output_parity_required": True,
        "format_a_output_parity_required": True,
    }
    for key, value in expected.items():
        if contract.get(key) is not value:
            errors.append(validation_error(f"policy.answer_contract.{key}", f"{key} must be {value}"))
    minimums = dict_value(policy.get("minimums"))
    for key in (
        "prompt_case_count",
        "format_a_case_count",
        "json_case_count",
        "negative_control_count",
        "minimum_page_count",
        "minimum_artifact_refs",
    ):
        if positive_int(minimums.get(key)) is None:
            errors.append(validation_error(f"policy.minimums.{key}", f"{key} must be positive integer"))
    if len(object_list(policy.get("prompt_cases"))) < int(minimums.get("prompt_case_count", 0) or 0):
        errors.append(validation_error("policy.prompt_cases", "not enough prompt cases"))
    if len(object_list(policy.get("negative_controls"))) < int(minimums.get("negative_control_count", 0) or 0):
        errors.append(validation_error("policy.negative_controls", "not enough negative controls"))
    missing = sorted(REQUIRED_OUT_OF_SCOPE - set(string_list(policy.get("out_of_scope"))))
    if missing:
        errors.append(validation_error("policy.out_of_scope", f"missing boundaries: {missing}"))
    if policy.get("acceptance_marker") != "PHASE219 ARTIFACT PAGING LONG ANSWER USABILITY PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 219"))
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


def validate_phase218_precondition(policy: dict[str, Any], phase218_report: dict[str, Any]) -> list[dict[str, str]]:
    if not phase218_report:
        return []
    errors: list[dict[str, str]] = []
    precondition = dict_value(policy.get("phase218_precondition"))
    summary = dict_value(phase218_report.get("summary"))
    if phase218_report.get("status") != precondition.get("required_status"):
        errors.append(validation_error("phase218_report.status", "Phase 218 report status must be passed", source="phase218"))
    if summary.get("phase219_ready") is not precondition.get("required_phase219_ready"):
        errors.append(validation_error("phase218_report.phase219_ready", "Phase 218 must mark phase219_ready", source="phase218"))
    return errors


def case_prompt(case: dict[str, Any], target_root: Path) -> str:
    return f"In {target_root}, {str(case.get('prompt', '')).strip()}"


def page_contract_errors(report: dict[str, Any], case: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    pages = dict_value(report.get("artifact_pages"))
    evidence_refs = object_list(report.get("evidence_refs"))
    page_records = object_list(pages.get("pages"))
    minimum_chat_refs = int(case.get("minimum_chat_refs", 0))
    minimum_artifact_refs = int(case.get("minimum_artifact_refs", 0))
    minimum_page_count = int(case.get("minimum_page_count", 0))
    if len(evidence_refs) < minimum_chat_refs:
        errors.append("chat_evidence_ref_count_below_minimum")
    if pages.get("artifact_source_ref_count") < minimum_artifact_refs:
        errors.append("artifact_source_ref_count_below_minimum")
    if pages.get("page_count") < minimum_page_count:
        errors.append("page_count_below_minimum")
    if pages.get("chat_refs_trace_to_pages") is not True:
        errors.append("chat_refs_do_not_trace_to_pages")
    if pages.get("store_source_text") is not False:
        errors.append("pages_store_source_text")
    if pages.get("source_text_retention") != "metadata_only":
        errors.append("pages_not_metadata_only")
    if not page_records:
        errors.append("missing_page_records")
    for page in page_records:
        if not page.get("page_id") or not isinstance(page.get("continuation_hint"), str):
            errors.append("missing_page_id_or_continuation_hint")
            break
        for ref in object_list(page.get("source_refs")):
            for key in ("source_path", "line_start", "line_end", "chunk_sha256", "source_sha256", "freshness_status"):
                if ref.get(key) in (None, ""):
                    errors.append(f"page_ref_missing_{key}")
                    break
    serialized_pages = json.dumps(pages, sort_keys=True)
    for forbidden in ('"source_text":', '"chunk_text":', '"snippet":', '"content":'):
        if forbidden in serialized_pages:
            errors.append(f"forbidden_page_field_{forbidden}")
    return sorted(set(errors))


def direct_case_result(config_root: Path, target_root: Path, output_root: Path, policy: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    result = invoke_retrieval_backed_chat_answer(
        RetrievalBackedChatAnswerRequest(
            config_root=config_root,
            target_root=target_root,
            output_root=output_root,
            user_request=case_prompt(case, target_root),
            max_evidence_refs=int(policy.get("chat_evidence_ref_limit", 4)),
            max_artifact_evidence_refs=int(policy.get("artifact_evidence_ref_limit", 12)),
            artifact_page_size=int(policy.get("artifact_page_size", 4)),
            target_input_limit=int(policy.get("target_input_limit", 24000)),
            model_context_limit=int(policy.get("model_context_limit", 65536)),
        )
    )
    report = dict_value(result.report)
    errors = page_contract_errors(report, case)
    answer = str(report.get("answer") or "")
    if not answer:
        errors.append("missing_answer")
    if "Paged evidence:" not in answer:
        errors.append("missing_paged_evidence_chat_hint")
    if dict_value(report.get("prompt_budget")).get("raw_prompt_stuffing") is not False:
        errors.append("raw_prompt_stuffing_not_false")
    return {
        "case_id": case.get("case_id"),
        "status": report.get("status"),
        "passed": report.get("status") == "answered" and not errors,
        "artifact": result.artifact_paths.get("retrieval_backed_chat_answer"),
        "page_count": dict_value(report.get("artifact_pages")).get("page_count"),
        "chat_ref_count": len(object_list(report.get("evidence_refs"))),
        "artifact_ref_count": dict_value(report.get("artifact_pages")).get("artifact_source_ref_count"),
        "errors": errors,
    }


def format_a_case_result(config_root: Path, target_root: Path, output_root: Path, policy: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    config = ControllerServiceConfig(config_root=config_root, output_root=output_root, allowed_target_roots=(config_root, target_root))
    body = handle_workflow_router_chat_completion(
        {"model": "agentic-workflow-router", "messages": [{"role": "user", "content": case_prompt(case, target_root)}]},
        config,
    )
    text = str(body.get("choices", [{}])[0].get("message", {}).get("content", ""))
    summary = dict_value(dict_value(body.get("agentic_controller_response")).get("summary"))
    passed = (
        text.startswith("Answer:\n")
        and "Paged evidence:" in text
        and summary.get("retrieval_artifact_page_count", 0) >= int(case.get("minimum_page_count", 0))
        and summary.get("retrieval_artifact_source_ref_count", 0) >= int(case.get("minimum_artifact_refs", 0))
        and summary.get("raw_prompt_stuffing") is False
    )
    return {
        "case_id": case.get("case_id"),
        "passed": passed,
        "answer_first": text.startswith("Answer:\n"),
        "has_paging_hint": "Paged evidence:" in text,
        "page_count": summary.get("retrieval_artifact_page_count"),
        "artifact_ref_count": summary.get("retrieval_artifact_source_ref_count"),
        "run_id": dict_value(body.get("agentic_controller_response")).get("run_id"),
    }


def json_case_result(config_root: Path, target_root: Path, output_root: Path, policy: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    config = ControllerServiceConfig(config_root=config_root, output_root=output_root, allowed_target_roots=(config_root, target_root))
    body = handle_workflow_router_chat_completion(
        {
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": case_prompt(case, target_root)}],
            "response_format": {"type": "json_object"},
        },
        config,
    )
    text = str(body.get("choices", [{}])[0].get("message", {}).get("content", ""))
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = {}
    summary = dict_value(parsed.get("summary"))
    primary = dict_value(parsed.get("primary_answer_contract"))
    artifacts = dict_value(parsed.get("artifacts"))
    passed = (
        parsed.get("output_format") == "json"
        and isinstance(primary.get("text"), str)
        and "Paged evidence:" in primary.get("text", "")
        and summary.get("retrieval_artifact_page_count", 0) >= int(case.get("minimum_page_count", 0))
        and summary.get("retrieval_artifact_source_ref_count", 0) >= int(case.get("minimum_artifact_refs", 0))
        and any("retrieval_backed_chat_answer" in key for key in artifacts)
    )
    return {
        "case_id": case.get("case_id"),
        "passed": passed,
        "output_format": parsed.get("output_format"),
        "has_primary_answer": bool(primary.get("text")),
        "page_count": summary.get("retrieval_artifact_page_count"),
        "artifact_ref_count": summary.get("retrieval_artifact_source_ref_count"),
        "artifact_keys": sorted(artifacts)[:8],
    }


def negative_control_result(config_root: Path, target_root: Path, output_root: Path, control: dict[str, Any]) -> dict[str, Any]:
    kind = control.get("kind")
    if kind == "small_repo_non_regression":
        config = ControllerServiceConfig(config_root=config_root, output_root=output_root, allowed_target_roots=(config_root, target_root))
        body = handle_workflow_router_chat_completion(
            {
                "model": "agentic-workflow-router",
                "messages": [{"role": "user", "content": f"In {config_root}, identify the most relevant modules for the order replay pipeline."}],
            },
            config,
        )
        summary = dict_value(dict_value(body.get("agentic_controller_response")).get("summary"))
        return {"case_id": control.get("case_id"), "kind": kind, "status": "not_intercepted", "passed": summary.get("retrieval_status") is None}
    result = invoke_retrieval_backed_chat_answer(
        RetrievalBackedChatAnswerRequest(
            config_root=config_root,
            target_root=target_root,
            output_root=output_root,
            user_request=case_prompt(control, target_root),
        )
    )
    report = dict_value(result.report)
    pages = dict_value(report.get("artifact_pages"))
    if kind == "unsafe_evidence":
        passed = report.get("status") == "blocked" and not object_list(report.get("evidence_refs")) and pages.get("page_count") == 0
    elif kind == "raw_1m_claim":
        passed = report.get("status") == "answered" and pages.get("page_count") == 0 and "No." in str(report.get("answer"))
    else:
        passed = False
    return {"case_id": control.get("case_id"), "kind": kind, "status": report.get("status"), "passed": passed}


def validate_sanitized_report(report: dict[str, Any]) -> list[dict[str, str]]:
    serialized = json.dumps(report, sort_keys=True)
    errors: list[dict[str, str]] = []
    for forbidden in ("PHASE216_DUMMY_SECRET_DO_NOT_EXPOSE", "DUMMY_SECRET_DO_NOT_USE", "ignored generated note"):
        if forbidden in serialized:
            errors.append(validation_error("report.rejected_content_leak", f"report contains rejected marker {forbidden}", source="report"))
    return errors


def build_report(config: ArtifactPagingLongAnswerUsabilityConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    policy = read_json_object(policy_path)
    policy_errors = validate_policy(policy)
    phase218_path, phase218_report, phase218_errors = load_report(
        config_root,
        dict_value(policy.get("phase218_precondition")).get("report_path"),
        source="phase218_report",
        require_artifacts=config.require_artifacts,
    )
    phase218_precondition_errors = validate_phase218_precondition(policy, phase218_report)
    target_root = resolve_path(config_root, str(policy.get("target_root"))).resolve()
    output_root = output_path.parent / "case-artifacts"
    direct_results = [
        direct_case_result(config_root, target_root, output_root / "direct", policy, case)
        for case in object_list(policy.get("prompt_cases"))
    ]
    format_a_results = [
        format_a_case_result(config_root, target_root, output_root / "format-a", policy, case)
        for case in object_list(policy.get("prompt_cases"))
    ]
    json_results = [
        json_case_result(config_root, target_root, output_root / "json", policy, case)
        for case in object_list(policy.get("prompt_cases"))
    ]
    negative_results = [
        negative_control_result(config_root, target_root, output_root / "negative", control)
        for control in object_list(policy.get("negative_controls"))
    ]
    validation_errors: list[dict[str, str]] = policy_errors + phase218_errors + phase218_precondition_errors
    for name, results in (
        ("direct_cases", direct_results),
        ("format_a_cases", format_a_results),
        ("json_cases", json_results),
        ("negative_controls", negative_results),
    ):
        for item in results:
            if item.get("passed") is not True:
                validation_errors.append(validation_error(f"{name}.{item.get('case_id')}", f"{name} case did not pass: {item}", source=name))
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
        "phase218_report_path": str(phase218_path) if phase218_path is not None else None,
        "phase218_report_sha256": sha256_file(phase218_path) if phase218_path is not None and phase218_path.is_file() else None,
        "target_root": str(target_root),
        "direct_case_results": direct_results,
        "format_a_case_results": format_a_results,
        "json_case_results": json_results,
        "negative_control_results": negative_results,
        "out_of_scope": string_list(policy.get("out_of_scope")),
        "validation_errors": validation_errors,
        "summary": {
            "direct_case_count": len(direct_results),
            "direct_passed_count": len([item for item in direct_results if item.get("passed") is True]),
            "format_a_case_count": len(format_a_results),
            "format_a_passed_count": len([item for item in format_a_results if item.get("passed") is True]),
            "json_case_count": len(json_results),
            "json_passed_count": len([item for item in json_results if item.get("passed") is True]),
            "negative_control_count": len(negative_results),
            "negative_control_passed_count": len([item for item in negative_results if item.get("passed") is True]),
            "answer_first_required": dict_value(policy.get("answer_contract")).get("answer_first_required"),
            "artifact_only_allowed": dict_value(policy.get("answer_contract")).get("artifact_only_allowed"),
            "raw_prompt_stuffing_allowed": dict_value(policy.get("answer_contract")).get("raw_prompt_stuffing_allowed"),
            "phase220_ready": status == "passed",
            "validation_error_count": len(validation_errors),
        },
    }
    leak_errors = validate_sanitized_report(report)
    if leak_errors:
        report["validation_errors"] = validation_errors + leak_errors
        report["status"] = "failed"
        report["summary"]["phase220_ready"] = False
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
    return report


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Artifact Paging And Long Answer Usability",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Direct cases: `{summary.get('direct_passed_count')}/{summary.get('direct_case_count')}`",
        f"- FormatA cases: `{summary.get('format_a_passed_count')}/{summary.get('format_a_case_count')}`",
        f"- JSON cases: `{summary.get('json_passed_count')}/{summary.get('json_case_count')}`",
        f"- Negative controls: `{summary.get('negative_control_passed_count')}/{summary.get('negative_control_count')}`",
        f"- Phase 220 ready: `{summary.get('phase220_ready')}`",
        "",
        "## Direct Cases",
    ]
    for item in object_list(report.get("direct_case_results")):
        lines.append(f"- `{item.get('case_id')}` pages `{item.get('page_count')}` refs `{item.get('artifact_ref_count')}` passed `{item.get('passed')}`")
    lines.extend(["", "## Output Parity"])
    for item in object_list(report.get("format_a_case_results")):
        lines.append(f"- FormatA `{item.get('case_id')}` passed `{item.get('passed')}` run `{item.get('run_id')}`")
    for item in object_list(report.get("json_case_results")):
        lines.append(f"- JSON `{item.get('case_id')}` passed `{item.get('passed')}` pages `{item.get('page_count')}`")
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(["", "## Validation Errors"])
        for item in errors:
            lines.append(f"- `{item.get('id')}` ({item.get('severity')}): {item.get('message')}")
    return "\n".join(lines) + "\n"


def run_artifact_paging_long_answer_usability(config: ArtifactPagingLongAnswerUsabilityConfig) -> dict[str, Any]:
    report = build_report(config)
    output_path = resolve_path(config.config_root.resolve(), config.output_path)
    markdown_output_path = resolve_path(config.config_root.resolve(), config.markdown_output_path)
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown_report(report))
    return report
