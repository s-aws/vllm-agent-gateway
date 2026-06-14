"""Phase 201 chat-visible answer contract enforcement gate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.controller_service.server import (
    ControllerOutputFormat,
    assistant_content_for_controller_response,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "chat_visible_answer_contract_enforcement_policy"
EXPECTED_REPORT_KIND = "chat_visible_answer_contract_enforcement_report"
EXPECTED_PHASE = 201
EXPECTED_BACKLOG_ID = "P0-BB-065"
EXPECTED_MILESTONE_ID = "M2"
DEFAULT_POLICY_PATH = Path("runtime") / "chat_visible_answer_contract_enforcement_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase201" / "phase201-chat-visible-answer-contract-enforcement-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase201" / "phase201-chat-visible-answer-contract-enforcement-report.md"


class ContractEnforcementStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class OutputFormat(str, Enum):
    FORMAT_A = "format_a"
    JSON = "json"


class NegativeControl(str, Enum):
    ARTIFACT_ONLY = "artifact_only"
    MISSING_EVIDENCE = "missing_evidence"
    MISSING_SAFETY_BOUNDARY = "missing_safety_boundary"
    UNSUPPORTED_MUTATION_CLAIM = "unsupported_mutation_claim"


class FailureReason(str, Enum):
    MISSING_ANSWER = "missing_answer"
    ARTIFACT_ONLY = "artifact_only"
    MISSING_OUTPUT_FORMAT = "missing_output_format"
    MISSING_CONTRACT_DETAIL = "missing_contract_detail"
    MISSING_EVIDENCE = "missing_evidence"
    MISSING_SAFETY_BOUNDARY = "missing_safety_boundary"
    MISSING_RUN_TRACEABILITY = "missing_run_traceability"
    UNSUPPORTED_MUTATION_CLAIM = "unsupported_mutation_claim"


@dataclass(frozen=True)
class ChatVisibleAnswerContractEnforcementConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path | None = DEFAULT_MARKDOWN_OUTPUT_PATH


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_hash(path: Path | None) -> str | None:
    return sha256_file(path) if path is not None and path.is_file() else None


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validation_error(error_id: str, message: str, severity: str = "high", source: str = "policy") -> dict[str, str]:
    return {"id": error_id, "severity": severity, "source": source, "message": message}


def enum_values(enum_class: type[Enum]) -> set[str]:
    return {item.value for item in enum_class}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "policy.schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"policy.kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "policy.phase must be 201"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if policy.get("milestone_id") != EXPECTED_MILESTONE_ID:
        errors.append(validation_error("policy.milestone_id", "policy.milestone_id must be M2"))
    source = dict_value(policy.get("required_phase200_report"))
    for key in ("path", "expected_kind", "expected_status"):
        if not isinstance(source.get(key), str) or not source[key].strip():
            errors.append(validation_error(f"policy.required_phase200_report.{key}", f"{key} is required"))
    if source.get("expected_phase") != 200:
        errors.append(validation_error("policy.required_phase200_report.expected_phase", "expected_phase must be 200"))
    if set(string_list(policy.get("required_output_formats"))) != enum_values(OutputFormat):
        errors.append(validation_error("policy.required_output_formats", "required output formats must be format_a and json"))
    if set(string_list(policy.get("required_negative_controls"))) != enum_values(NegativeControl):
        errors.append(validation_error("policy.required_negative_controls", "required negative controls must match the governed set"))
    if set(string_list(policy.get("required_failure_reasons"))) != enum_values(FailureReason):
        errors.append(validation_error("policy.required_failure_reasons", "required failure reasons must match the governed set"))
    if not string_list(policy.get("required_docs")):
        errors.append(validation_error("policy.required_docs", "required docs are required"))
    if policy.get("acceptance_marker") != "PHASE201 CHAT VISIBLE ANSWER CONTRACT ENFORCEMENT PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 201"))
    return errors


def load_phase200(config_root: Path, policy: dict[str, Any]) -> tuple[Path, dict[str, Any], list[dict[str, str]]]:
    source = dict_value(policy.get("required_phase200_report"))
    raw_path = str(source.get("path") or "")
    path = resolve_path(config_root, raw_path)
    if not path.is_file():
        return path, {}, [validation_error("phase200.missing", f"Phase 200 report is missing: {raw_path}", source="phase200")]
    try:
        report = read_json_object(path)
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        return path, {}, [validation_error("phase200.malformed", f"Phase 200 report is malformed: {type(exc).__name__}: {exc}", source="phase200")]
    errors: list[dict[str, str]] = []
    if report.get("kind") != source.get("expected_kind"):
        errors.append(validation_error("phase200.kind", f"Phase 200 kind must be {source.get('expected_kind')}", source="phase200"))
    if report.get("status") != source.get("expected_status"):
        errors.append(validation_error("phase200.status", f"Phase 200 status must be {source.get('expected_status')}", source="phase200"))
    if report.get("phase") != source.get("expected_phase"):
        errors.append(validation_error("phase200.phase", "Phase 200 phase must be 200", source="phase200"))
    if object_list(report.get("validation_errors")):
        errors.append(validation_error("phase200.validation_errors", "Phase 200 validation_errors must be empty", source="phase200"))
    if dict_value(report.get("summary")).get("phase201_ready") is not True:
        errors.append(validation_error("phase200.phase201_ready", "Phase 200 must report phase201_ready=true", source="phase200"))
    return path, report, errors


def source_ref(path: Path | None, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path) if path is not None else None,
        "exists": path.is_file() if path is not None else False,
        "sha256": artifact_hash(path),
        "kind": payload.get("kind"),
        "phase": payload.get("phase"),
        "status": payload.get("status"),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
    }


def controller_response_for_record(record: dict[str, Any]) -> dict[str, Any]:
    entry_id = str(record.get("entry_id") or "unknown").lower()
    display_entry_id = str(record.get("entry_id") or "unknown")
    selected_workflow = str(record.get("selected_workflow") or "workflow")
    prompt_family = str(record.get("prompt_family") or entry_id)
    evidence_expectations = string_list(record.get("evidence_expectations"))
    safety_boundaries = string_list(record.get("safety_boundaries"))
    required_sections = string_list(record.get("required_sections"))
    docs_examples = string_list(record.get("docs_examples"))
    evidence_phrase = "; ".join(evidence_expectations) or "source-backed evidence"
    safety_phrase = "; ".join(safety_boundaries) or "source_mutation_status"
    section_phrase = ", ".join(required_sections) or "Answer, Evidence, Safety boundary, Run traceability"
    source_ref = docs_examples[0] if docs_examples else "runtime/prompt_skill_coverage.json"
    answer = (
        f"{prompt_family} ({display_entry_id}) uses {selected_workflow}. "
        f"Required sections: {section_phrase}. "
        f"Evidence: {evidence_phrase}; source: {source_ref}. "
        f"Safety boundary: {safety_phrase}; source_mutation_status=no source mutation. "
        f"Run traceability: selected_workflow={selected_workflow}; run_id=workflow-router-phase201-{entry_id}."
    )
    return {
        "run_id": f"workflow-router-phase201-{entry_id}",
        "workflow": "workflow_router.plan",
        "status": "completed",
        "summary": {
            "route_status": "ready",
            "selected_workflow": selected_workflow,
            "downstream_status": "completed",
            "answer": answer,
            "next_action": "none",
            "verification_command_count": 1,
            "evidence_expectations": evidence_expectations,
            "mutation_policy": "read_only_no_source_mutation"
            if "read_only_no_source_mutation" in safety_boundaries
            else "no source mutation",
            "source_mutation_status": "no source mutation",
            "safety_boundaries": safety_boundaries,
        },
        "artifacts": {},
        "warning_count": 0,
        "warnings": [],
        "failure_count": 0,
        "failures": [],
        "run_lookup": f"/v1/controller/runs/workflow-router-phase201-{entry_id}",
    }


def positive_format_a(record: dict[str, Any]) -> str:
    return assistant_content_for_controller_response(
        controller_response_for_record(record),
        ControllerOutputFormat.FORMAT_A,
    )


def positive_json(record: dict[str, Any]) -> dict[str, Any]:
    return json.loads(
        assistant_content_for_controller_response(
            controller_response_for_record(record),
            ControllerOutputFormat.JSON,
        )
    )


def strip_between(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    if start < 0:
        return text
    end = text.find(end_marker, start + len(start_marker))
    if end < 0:
        return text[:start]
    return text[:start] + text[end:]


def apply_negative_control_format_a(text: str, control: str) -> str:
    if control == NegativeControl.ARTIFACT_ONLY.value:
        return "Answer:\nSee runtime-state/example/report.json.\n\nrun_id: workflow-router-phase201\n\nArtifacts:\n- runtime-state/example/report.json"
    if control == NegativeControl.MISSING_EVIDENCE.value:
        stripped = strip_between(text, "Evidence:", "Safety boundary:")
        return "\n".join(
            line
            for line in stripped.splitlines()
            if not line.startswith("Evidence")
            and not line.startswith("- Source:")
            and "evidence_expectations" not in line
            and "source:" not in line.lower()
        )
    if control == NegativeControl.MISSING_SAFETY_BOUNDARY.value:
        stripped = strip_between(text, "Safety boundary:", "Run traceability:")
        return "\n".join(
            line
            for line in stripped.splitlines()
            if not line.startswith("Safety boundary")
            and "source_mutation_status" not in line
            and "mutation_policy" not in line
            and "safety_boundaries" not in line
        )
    if control == NegativeControl.UNSUPPORTED_MUTATION_CLAIM.value:
        return text + "\nSource mutation: true"
    return text


def apply_negative_control_json(payload: dict[str, Any], control: str) -> dict[str, Any]:
    value = json.loads(json.dumps(payload))
    if control == NegativeControl.ARTIFACT_ONLY.value:
        value["summary"] = {"answer": "See runtime-state/example/report.json.", "selected_workflow": "code_investigation.plan"}
        value["chat_contract"] = {"answer": "See runtime-state/example/report.json."}
        value["primary_answer_contract"] = {"text": "See runtime-state/example/report.json."}
        value["artifacts"] = {"report": "runtime-state/example/report.json"}
        return value
    if control == NegativeControl.MISSING_EVIDENCE.value:
        value["evidence"] = []
        summary = dict_value(value.get("summary"))
        summary["evidence_expectations"] = []
        for container_key in ("summary", "chat_contract", "primary_answer_contract"):
            container = dict_value(value.get(container_key))
            for text_key in ("answer", "text"):
                if isinstance(container.get(text_key), str):
                    container[text_key] = strip_between(container[text_key], "Evidence:", "Safety boundary:")
    elif control == NegativeControl.MISSING_SAFETY_BOUNDARY.value:
        value["safety_boundaries"] = []
        value.pop("source_mutation_status", None)
        summary = dict_value(value.get("summary"))
        summary.pop("source_mutation_status", None)
        summary.pop("mutation_policy", None)
        summary["safety_boundaries"] = []
        for container_key in ("summary", "chat_contract", "primary_answer_contract"):
            container = dict_value(value.get(container_key))
            for text_key in ("answer", "text"):
                if isinstance(container.get(text_key), str):
                    container[text_key] = strip_between(container[text_key], "Safety boundary:", "Run traceability:")
    elif control == NegativeControl.UNSUPPORTED_MUTATION_CLAIM.value:
        value["source_mutation"] = True
    return value


def has_record_contract_detail(text: str, record: dict[str, Any] | None) -> bool:
    if record is None:
        return True
    lowered = text.lower()
    entry_id = str(record.get("entry_id") or "").lower()
    prompt_family = str(record.get("prompt_family") or "").lower()
    selected_workflow = str(record.get("selected_workflow") or "").lower()
    if selected_workflow and selected_workflow not in lowered:
        return False
    if entry_id and prompt_family and entry_id not in lowered and prompt_family not in lowered:
        return False
    required_sections = [section.lower() for section in string_list(record.get("required_sections"))]
    if required_sections and not all(section in lowered for section in required_sections):
        return False
    evidence_expectations = [expectation.lower() for expectation in string_list(record.get("evidence_expectations"))]
    if evidence_expectations and not any(expectation in lowered for expectation in evidence_expectations):
        return False
    safety_boundaries = [boundary.lower() for boundary in string_list(record.get("safety_boundaries"))]
    if safety_boundaries and not any(boundary in lowered for boundary in safety_boundaries):
        return False
    return True


def evaluate_format_a(text: str, record: dict[str, Any] | None = None) -> list[str]:
    lowered = text.lower()
    reasons: list[str] = []
    if "answer:" not in lowered and "draft proposal:" not in lowered and "task decomposition:" not in lowered:
        reasons.append(FailureReason.MISSING_ANSWER.value)
    artifact_pointer = (
        "see runtime-state/" in lowered
        or "see the artifact" in lowered
        or "see artifact" in lowered
        or "see the report" in lowered
        or "see report" in lowered
    )
    if (
        ("artifact" in lowered and "answer:" not in lowered and "draft proposal:" not in lowered)
        or artifact_pointer
    ):
        reasons.append(FailureReason.ARTIFACT_ONLY.value)
    if "evidence:" not in lowered and "source:" not in lowered:
        reasons.append(FailureReason.MISSING_EVIDENCE.value)
    if "safety boundary:" not in lowered or "source_mutation_status" not in lowered:
        reasons.append(FailureReason.MISSING_SAFETY_BOUNDARY.value)
    if "workflow-router-" not in lowered and "run_id:" not in lowered:
        reasons.append(FailureReason.MISSING_RUN_TRACEABILITY.value)
    if "source mutation: true" in lowered or "source_changed: true" in lowered:
        reasons.append(FailureReason.UNSUPPORTED_MUTATION_CLAIM.value)
    if not has_record_contract_detail(text, record):
        reasons.append(FailureReason.MISSING_CONTRACT_DETAIL.value)
    return list(dict.fromkeys(reasons))


def evaluate_json(payload: dict[str, Any], record: dict[str, Any] | None = None) -> list[str]:
    reasons: list[str] = []
    summary = dict_value(payload.get("summary"))
    chat_contract = dict_value(payload.get("chat_contract"))
    primary_answer_contract = dict_value(payload.get("primary_answer_contract"))
    run_traceability = dict_value(payload.get("run_traceability"))
    answer = (
        primary_answer_contract.get("text")
        if isinstance(primary_answer_contract.get("text"), str)
        else chat_contract.get("answer")
        if isinstance(chat_contract.get("answer"), str)
        else summary.get("answer")
        if isinstance(summary.get("answer"), str)
        else payload.get("answer")
    )
    answer_text = answer if isinstance(answer, str) else ""
    lowered_answer = answer_text.lower()
    output_format = payload.get("output_format") or payload.get("format")
    if output_format != OutputFormat.JSON.value:
        reasons.append(FailureReason.MISSING_OUTPUT_FORMAT.value)
    if not answer_text.strip():
        reasons.append(FailureReason.MISSING_ANSWER.value)
    artifact_pointer = (
        "see runtime-state/" in lowered_answer
        or "see the artifact" in lowered_answer
        or "see artifact" in lowered_answer
        or "see the report" in lowered_answer
        or "see report" in lowered_answer
    )
    if (payload.get("artifacts") and not answer_text.strip()) or artifact_pointer:
        reasons.append(FailureReason.ARTIFACT_ONLY.value)
    has_evidence = bool(object_list(payload.get("evidence"))) or "evidence:" in lowered_answer or "source:" in lowered_answer
    if not has_evidence:
        reasons.append(FailureReason.MISSING_EVIDENCE.value)
    safety_boundaries = string_list(payload.get("safety_boundaries")) or string_list(summary.get("safety_boundaries"))
    has_safety = (
        "source_mutation_status" in payload
        or "source_mutation_status" in summary
        or "source_mutation_status" in lowered_answer
        or "mutation_policy" in summary
        or bool(safety_boundaries)
    )
    if not has_safety:
        reasons.append(FailureReason.MISSING_SAFETY_BOUNDARY.value)
    run_id = payload.get("run_id") if isinstance(payload.get("run_id"), str) else run_traceability.get("run_id")
    if not isinstance(run_id, str) or not run_id.startswith("workflow-router-"):
        reasons.append(FailureReason.MISSING_RUN_TRACEABILITY.value)
    if payload.get("source_mutation") is True or payload.get("source_changed") is True or summary.get("source_changed") is True:
        reasons.append(FailureReason.UNSUPPORTED_MUTATION_CLAIM.value)
    detail_text = " ".join(
        str(part)
        for part in (
            answer_text,
            summary,
            chat_contract,
            primary_answer_contract,
        )
    )
    if not has_record_contract_detail(detail_text, record):
        reasons.append(FailureReason.MISSING_CONTRACT_DETAIL.value)
    return list(dict.fromkeys(reasons))


def enforcement_case(record: dict[str, Any], output_format: str, negative_control: str | None = None) -> dict[str, Any]:
    if output_format == OutputFormat.FORMAT_A.value:
        body = positive_format_a(record)
        if negative_control is not None:
            body = apply_negative_control_format_a(body, negative_control)
        reasons = evaluate_format_a(body, record)
    else:
        payload = positive_json(record)
        if negative_control is not None:
            payload = apply_negative_control_json(payload, negative_control)
        reasons = evaluate_json(payload, record)
    expected_pass = negative_control is None
    actual_pass = not reasons
    return {
        "entry_id": record.get("entry_id"),
        "output_format": output_format,
        "negative_control": negative_control,
        "expected_pass": expected_pass,
        "actual_pass": actual_pass,
        "failure_reasons": reasons,
    }


def enforcement_cases(records: list[dict[str, Any]], policy: dict[str, Any]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for record in records:
        for output_format in string_list(policy.get("required_output_formats")):
            cases.append(enforcement_case(record, output_format))
            for control in string_list(policy.get("required_negative_controls")):
                cases.append(enforcement_case(record, output_format, control))
    return cases


def validate_enforcement_cases(cases: list[dict[str, Any]], policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    allowed_reasons = set(string_list(policy.get("required_failure_reasons")))
    allowed_formats = set(string_list(policy.get("required_output_formats")))
    for index, case in enumerate(cases):
        prefix = f"cases[{index}]"
        expected_pass = case.get("expected_pass") is True
        actual_pass = case.get("actual_pass") is True
        reasons = set(string_list(case.get("failure_reasons")))
        output_format = case.get("output_format")
        if output_format not in allowed_formats:
            errors.append(validation_error(f"{prefix}.output_format", "case output_format must be governed", "critical", "enforcement"))
        if expected_pass and not actual_pass:
            errors.append(validation_error(f"{prefix}.positive_failed", "positive contract fixture must pass", "critical", "enforcement"))
        if not expected_pass and actual_pass:
            errors.append(validation_error(f"{prefix}.negative_passed", "negative contract fixture must fail closed", "critical", "enforcement"))
        if reasons - allowed_reasons:
            errors.append(validation_error(f"{prefix}.unknown_failure_reason", "failure reasons must be governed", source="enforcement"))
        if not expected_pass and not reasons:
            errors.append(validation_error(f"{prefix}.missing_failure_reason", "negative fixture must include failure reasons", source="enforcement"))
    return errors


def doc_records(config_root: Path, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    docs: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for raw_path in string_list(policy.get("required_docs")):
        path = resolve_path(config_root, raw_path)
        exists = path.is_file()
        docs.append({"path": raw_path, "exists": exists, "sha256": artifact_hash(path)})
        if not exists:
            errors.append(validation_error(f"docs.{raw_path}.missing", f"required doc is missing: {raw_path}", "medium", "documentation"))
    return docs, errors


def build_chat_visible_answer_contract_enforcement_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    phase200_path: Path,
    phase200_report: dict[str, Any],
    source_load_errors: list[dict[str, str]],
    policy_path: Path | None = None,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    errors.extend(validate_policy(policy))
    errors.extend(source_load_errors)
    records = object_list(phase200_report.get("contract_records"))
    cases = enforcement_cases(records, policy)
    errors.extend(validate_enforcement_cases(cases, policy))
    docs, doc_errors = doc_records(config_root, policy)
    errors.extend(doc_errors)
    positive_cases = [case for case in cases if case.get("expected_pass") is True]
    negative_cases = [case for case in cases if case.get("expected_pass") is not True]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_id": EXPECTED_MILESTONE_ID,
        "status": ContractEnforcementStatus.FAILED.value if errors else ContractEnforcementStatus.PASSED.value,
        "created_at": utc_timestamp(),
        "policy_path": str(policy_path or DEFAULT_POLICY_PATH),
        "policy_sha256": artifact_hash(policy_path),
        "source_refs": {"phase200": source_ref(phase200_path, phase200_report)},
        "enforcement_cases": cases,
        "docs": docs,
        "validation_errors": errors,
        "summary": {
            "contract_count": len(records),
            "output_format_count": len(string_list(policy.get("required_output_formats"))),
            "negative_control_count": len(string_list(policy.get("required_negative_controls"))),
            "positive_case_count": len(positive_cases),
            "negative_case_count": len(negative_cases),
            "passed_positive_case_count": sum(1 for case in positive_cases if case.get("actual_pass") is True),
            "rejected_negative_case_count": sum(1 for case in negative_cases if case.get("actual_pass") is not True),
            "validation_error_count": len(errors),
            "phase202_ready": not errors,
            "next_action": "work Phase 202 Output Format And Usefulness Refresh"
            if not errors
            else "repair Phase 201 enforcement gaps before live refresh",
        },
    }


def stable_report_view(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: report.get(key)
        for key in (
            "schema_version",
            "kind",
            "phase",
            "priority_backlog_id",
            "milestone_id",
            "status",
            "policy_path",
            "policy_sha256",
            "source_refs",
            "enforcement_cases",
            "docs",
            "validation_errors",
            "summary",
        )
    }


def validate_chat_visible_answer_contract_enforcement_report(
    report: dict[str, Any],
    *,
    config_root: Path,
    policy: dict[str, Any],
    phase200_path: Path,
    phase200_report: dict[str, Any],
    source_load_errors: list[dict[str, str]],
    policy_path: Path | None = None,
) -> list[str]:
    expected = build_chat_visible_answer_contract_enforcement_report(
        config_root=config_root,
        policy=policy,
        phase200_path=phase200_path,
        phase200_report=phase200_report,
        source_load_errors=source_load_errors,
        policy_path=policy_path,
    )
    if stable_report_view(report) != stable_report_view(expected):
        return ["report must match rebuilt chat-visible answer contract enforcement"]
    return []


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Phase 201 Chat-Visible Answer Contract Enforcement",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Contracts: `{summary.get('contract_count')}`",
        f"- Positive cases: `{summary.get('passed_positive_case_count')}/{summary.get('positive_case_count')}`",
        f"- Negative cases rejected: `{summary.get('rejected_negative_case_count')}/{summary.get('negative_case_count')}`",
        f"- Validation errors: `{summary.get('validation_error_count')}`",
        f"- Next action: `{summary.get('next_action')}`",
    ]
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(["", "## Validation Errors", ""])
        lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in errors)
    return "\n".join(lines) + "\n"


def run_chat_visible_answer_contract_enforcement(config: ChatVisibleAnswerContractEnforcementConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    phase200_path, phase200_report, source_errors = load_phase200(config_root, policy)
    report = build_chat_visible_answer_contract_enforcement_report(
        config_root=config_root,
        policy=policy,
        phase200_path=phase200_path,
        phase200_report=phase200_report,
        source_load_errors=source_errors,
        policy_path=policy_path,
    )
    validation_errors = validate_chat_visible_answer_contract_enforcement_report(
        report,
        config_root=config_root,
        policy=policy,
        phase200_path=phase200_path,
        phase200_report=phase200_report,
        source_load_errors=source_errors,
        policy_path=policy_path,
    )
    if validation_errors:
        report["status"] = ContractEnforcementStatus.FAILED.value
        report["validation_errors"] = [
            *object_list(report.get("validation_errors")),
            *[
                validation_error(f"self_validation.{index}", error, "critical", "chat_visible_answer_contract_enforcement")
                for index, error in enumerate(validation_errors)
            ],
        ]
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
        report["summary"]["phase202_ready"] = False
    output_path = resolve_path(config_root, config.output_path)
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    if config.markdown_output_path is not None:
        markdown_path = resolve_path(config_root, config.markdown_output_path)
        write_text(markdown_path, render_markdown(report))
        report["markdown_report_path"] = str(markdown_path.resolve())
    write_json(output_path, report)
    if config.markdown_output_path is not None:
        write_text(resolve_path(config_root, config.markdown_output_path), render_markdown(report))
    return report
