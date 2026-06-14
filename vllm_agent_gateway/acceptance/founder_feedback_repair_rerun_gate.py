"""Phase 228 founder-feedback repair rerun gate."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.context_index_prototype import dict_value, object_list, read_json_object, string_list, write_json


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "founder_feedback_repair_rerun_gate_policy"
EXPECTED_REPORT_KIND = "founder_feedback_repair_rerun_gate_report"
EXPECTED_PHASE = 228
EXPECTED_BACKLOG_ID = "P0-M9-228"
EXPECTED_MILESTONE_IDS = {"M9"}
DEFAULT_POLICY_PATH = Path("runtime") / "founder_feedback_repair_rerun_gate_policy.json"
DEFAULT_OUTPUT_PATH = (
    Path("runtime-state") / "founder-feedback-loop" / "phase228" / "phase228-founder-feedback-repair-rerun-gate-report.json"
)
DEFAULT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state") / "founder-feedback-loop" / "phase228" / "phase228-founder-feedback-repair-rerun-gate-report.md"
)
REQUIRED_CONTRACT_TRUE = {
    "blind_baseline_first_required",
    "target_prompt_rerun_required",
    "holdout_prompt_rerun_required",
    "gateway_surface_required",
    "anythingllm_surface_required",
    "fixture_mutation_check_required",
    "rejected_explanations_required",
    "gap_class_comparison_required",
    "artifact_trace_required",
}
REQUIRED_NEGATIVE_CONTROLS = {
    "missing_blind_baseline",
    "missing_target_rerun",
    "missing_holdout_rerun",
    "missing_anythingllm_surface",
    "missing_fixture_mutation_check",
    "missing_rejected_explanations",
    "manual_success_without_rerun",
}


@dataclass(frozen=True)
class FounderFeedbackRepairRerunGateConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    require_live_artifacts: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def validation_error(error_id: str, message: str) -> dict[str, str]:
    return {"id": error_id, "message": message}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "phase must be 228"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be exactly M9"))
    precondition = dict_value(policy.get("phase227_precondition"))
    for key in ("report_path", "required_status"):
        if not isinstance(precondition.get(key), str) or not str(precondition[key]).strip():
            errors.append(validation_error(f"policy.phase227_precondition.{key}", f"{key} is required"))
    if precondition.get("required_phase228_ready") is not True:
        errors.append(validation_error("policy.phase227_precondition.required_phase228_ready", "must be true"))
    if string_list(policy.get("accepted_repair_decision_kinds")) != ["repair_followup"]:
        errors.append(validation_error("policy.accepted_repair_decision_kinds", "must be exactly repair_followup"))
    contract = dict_value(policy.get("rerun_gate_contract"))
    for key in sorted(REQUIRED_CONTRACT_TRUE):
        if contract.get(key) is not True:
            errors.append(validation_error(f"policy.rerun_gate_contract.{key}", f"{key} must be true"))
    if contract.get("manual_success_without_rerun_allowed") is not False:
        errors.append(
            validation_error(
                "policy.rerun_gate_contract.manual_success_without_rerun_allowed",
                "manual success without rerun must be false",
            )
        )
    missing_controls = sorted(REQUIRED_NEGATIVE_CONTROLS - set(string_list(policy.get("negative_controls"))))
    if missing_controls:
        errors.append(validation_error("policy.negative_controls", f"missing negative controls: {missing_controls}"))
    if not object_list(policy.get("repair_cases")):
        errors.append(validation_error("policy.repair_cases", "at least one repair case is required"))
    for case in object_list(policy.get("repair_cases")):
        case_id = str(case.get("source_case_id") or "unknown")
        if case.get("expected_decision_kind") != "repair_followup":
            errors.append(validation_error(f"policy.repair_cases.{case_id}.expected_decision_kind", "must be repair_followup"))
        if not isinstance(case.get("target_prompt"), str) or not str(case["target_prompt"]).strip():
            errors.append(validation_error(f"policy.repair_cases.{case_id}.target_prompt", "target_prompt is required"))
        if not isinstance(case.get("holdout_prompt"), str) or not str(case["holdout_prompt"]).strip():
            errors.append(validation_error(f"policy.repair_cases.{case_id}.holdout_prompt", "holdout_prompt is required"))
        if set(string_list(case.get("required_surfaces"))) != {"gateway", "anythingllm"}:
            errors.append(validation_error(f"policy.repair_cases.{case_id}.required_surfaces", "gateway and anythingllm are required"))
        if len(string_list(case.get("required_fixture_roots"))) < 2:
            errors.append(validation_error(f"policy.repair_cases.{case_id}.required_fixture_roots", "both frozen fixtures are required"))
        if case.get("minimum_rerun_records") != 2:
            errors.append(validation_error(f"policy.repair_cases.{case_id}.minimum_rerun_records", "must be 2"))
        if case.get("closure_status_before_rerun") != "open_pending_repair":
            errors.append(validation_error(f"policy.repair_cases.{case_id}.closure_status_before_rerun", "must be open_pending_repair"))
    if policy.get("acceptance_marker") != "PHASE228 FOUNDER FEEDBACK REPAIR RERUN GATE PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 228"))
    return errors


def load_optional_report(config_root: Path, raw_path: object, *, required: bool) -> tuple[Path | None, dict[str, Any], list[dict[str, str]]]:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None, {}, [validation_error("report.path", "report path is required")]
    path = resolve_path(config_root, raw_path)
    if not path.is_file():
        if required:
            return path, {}, [validation_error("report.missing", f"required report missing: {path}")]
        return path, {}, []
    return path, read_json_object(path), []


def validate_phase227_precondition(policy: dict[str, Any], phase227_report: dict[str, Any]) -> list[dict[str, str]]:
    if not phase227_report:
        return []
    errors: list[dict[str, str]] = []
    precondition = dict_value(policy.get("phase227_precondition"))
    summary = dict_value(phase227_report.get("summary"))
    if phase227_report.get("status") != precondition.get("required_status"):
        errors.append(validation_error("phase227.status", "Phase 227 report status must be passed"))
    if summary.get("phase228_ready") is not precondition.get("required_phase228_ready"):
        errors.append(validation_error("phase227.phase228_ready", "Phase 227 report must mark phase228_ready"))
    return errors


def decisions_by_case(live_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for item in object_list(live_report.get("cases")):
        case_id = item.get("case_id")
        if isinstance(case_id, str):
            rows[case_id] = item
    return rows


def validate_repair_cases(policy: dict[str, Any], live_report: dict[str, Any]) -> list[dict[str, str]]:
    if not live_report:
        return []
    errors: list[dict[str, str]] = []
    live_cases = decisions_by_case(live_report)
    for case in object_list(policy.get("repair_cases")):
        case_id = str(case.get("source_case_id") or "unknown")
        live_case = live_cases.get(case_id)
        if not live_case:
            errors.append(validation_error(f"repair_cases.{case_id}.missing", "repair case missing from Phase 227 live report"))
            continue
        decision = dict_value(live_case.get("decision"))
        if decision.get("kind") != case.get("expected_decision_kind"):
            errors.append(validation_error(f"repair_cases.{case_id}.decision_kind", "live decision kind mismatch"))
        if decision.get("gap_class") != case.get("expected_gap_class"):
            errors.append(validation_error(f"repair_cases.{case_id}.gap_class", "live gap_class mismatch"))
        if decision.get("decision_status") != "accepted":
            errors.append(validation_error(f"repair_cases.{case_id}.decision_status", "repair follow-up must be accepted"))
    return errors


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Founder Feedback Repair Rerun Gate",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Repair case count: `{summary.get('repair_case_count')}`",
        f"- Phase 229 ready: `{summary.get('phase229_ready')}`",
        "",
        "## Validation Errors",
    ]
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in errors)
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def validate_founder_feedback_repair_rerun_gate(config: FounderFeedbackRepairRerunGateConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path)
    policy = read_json_object(policy_path)
    validation_errors = validate_policy(policy)
    phase227_path, phase227_report, phase227_errors = load_optional_report(
        config_root,
        dict_value(policy.get("phase227_precondition")).get("report_path"),
        required=config.require_live_artifacts,
    )
    validation_errors.extend(phase227_errors)
    validation_errors.extend(validate_phase227_precondition(policy, phase227_report))
    live_path, live_report, live_errors = load_optional_report(
        config_root,
        policy.get("live_feedback_report_path"),
        required=config.require_live_artifacts,
    )
    validation_errors.extend(live_errors)
    validation_errors.extend(validate_repair_cases(policy, live_report))
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": sorted(EXPECTED_MILESTONE_IDS),
        "generated_at": utc_timestamp(),
        "status": "passed" if not validation_errors else "failed",
        "policy_path": str(policy_path),
        "phase227_report_path": str(phase227_path) if phase227_path else None,
        "live_feedback_report_path": str(live_path) if live_path else None,
        "validation_errors": validation_errors,
        "summary": {
            "repair_case_count": len(object_list(policy.get("repair_cases"))),
            "negative_control_count": len(string_list(policy.get("negative_controls"))),
            "requires_blind_baseline": dict_value(policy.get("rerun_gate_contract")).get("blind_baseline_first_required"),
            "requires_target_and_holdout": dict_value(policy.get("rerun_gate_contract")).get(
                "target_prompt_rerun_required"
            )
            is True
            and dict_value(policy.get("rerun_gate_contract")).get("holdout_prompt_rerun_required") is True,
            "manual_success_without_rerun_allowed": dict_value(policy.get("rerun_gate_contract")).get(
                "manual_success_without_rerun_allowed"
            ),
            "phase229_ready": not validation_errors,
        },
    }
    write_json(output_path, report)
    markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_output_path.write_text(render_markdown(report), encoding="utf-8")
    return report
