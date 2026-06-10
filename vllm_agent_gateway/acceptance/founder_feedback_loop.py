"""Founder-feedback loop governance for Priority 0 chat quality."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vllm_agent_gateway.controllers.workflow_feedback.record import feedback_governance_decision


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES_PATH = REPO_ROOT / "runtime" / "founder_feedback_loop_cases.json"
REQUIRED_TARGET_ROOTS = {
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
}
REQUIRED_SURFACES = {"gateway", "anythingllm"}
REQUIRED_DECISIONS = {
    "baseline_prompt_candidate",
    "holdout_prompt_candidate",
    "repair_followup",
    "rejected_finding",
}
ACCEPTED_DECISIONS = {"baseline_prompt_candidate", "holdout_prompt_candidate", "repair_followup"}
REJECTED_DECISIONS = {"rejected_finding"}
GAP_CLASSES = {
    "routing",
    "context_gathering",
    "skill_tool_selection",
    "deterministic_formatter",
    "model_capability",
    "safety_boundary",
    "documentation",
    "test_coverage",
    "none",
}


@dataclass(frozen=True)
class FounderFeedbackLoopCase:
    case_id: str
    surface: str
    target_root: str
    seed_prompt: str
    feedback_template: str
    expected_classifications: tuple[str, ...]
    expected_decision_kind: str
    expected_gap_class: str


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return value


def _required_string(item: dict[str, Any], field: str, case_id: str) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{case_id} {field} is required")
    return value


def _string_tuple(item: dict[str, Any], field: str, case_id: str) -> tuple[str, ...]:
    value = item.get(field)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{case_id} {field} must be a non-empty list")
    values = tuple(entry for entry in value if isinstance(entry, str) and entry)
    if len(values) != len(value):
        raise ValueError(f"{case_id} {field} must contain only strings")
    return values


def load_founder_feedback_loop_cases(cases_path: Path = DEFAULT_CASES_PATH) -> list[FounderFeedbackLoopCase]:
    catalog = read_json_object(cases_path)
    if catalog.get("kind") != "founder_feedback_loop_cases":
        raise ValueError(f"{cases_path} kind must be founder_feedback_loop_cases")
    raw_cases = catalog.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError(f"{cases_path} must contain at least one case")
    cases: list[FounderFeedbackLoopCase] = []
    seen: set[str] = set()
    for item in raw_cases:
        if not isinstance(item, dict):
            raise ValueError("founder feedback cases must be objects")
        case_id = _required_string(item, "case_id", "case")
        if case_id in seen:
            raise ValueError(f"duplicate founder feedback case_id: {case_id}")
        seen.add(case_id)
        expected_decision_kind = _required_string(item, "expected_decision_kind", case_id)
        if expected_decision_kind not in REQUIRED_DECISIONS:
            raise ValueError(f"{case_id} unsupported expected_decision_kind: {expected_decision_kind}")
        expected_gap_class = _required_string(item, "expected_gap_class", case_id)
        if expected_gap_class not in GAP_CLASSES:
            raise ValueError(f"{case_id} unsupported expected_gap_class: {expected_gap_class}")
        surface = _required_string(item, "surface", case_id)
        if surface not in REQUIRED_SURFACES:
            raise ValueError(f"{case_id} unsupported surface: {surface}")
        cases.append(
            FounderFeedbackLoopCase(
                case_id=case_id,
                surface=surface,
                target_root=_required_string(item, "target_root", case_id),
                seed_prompt=_required_string(item, "seed_prompt", case_id),
                feedback_template=_required_string(item, "feedback_template", case_id),
                expected_classifications=_string_tuple(item, "expected_classifications", case_id),
                expected_decision_kind=expected_decision_kind,
                expected_gap_class=expected_gap_class,
            )
        )
    return cases


def validate_case_catalog(cases: list[FounderFeedbackLoopCase]) -> list[str]:
    errors: list[str] = []
    if not cases:
        return ["founder feedback loop catalog has no cases"]
    target_roots = {case.target_root for case in cases}
    missing_roots = sorted(REQUIRED_TARGET_ROOTS - target_roots)
    if missing_roots:
        errors.append(f"missing required target roots: {', '.join(missing_roots)}")
    surfaces = {case.surface for case in cases}
    missing_surfaces = sorted(REQUIRED_SURFACES - surfaces)
    if missing_surfaces:
        errors.append(f"missing required surfaces: {', '.join(missing_surfaces)}")
    decisions = {case.expected_decision_kind for case in cases}
    missing_decisions = sorted(REQUIRED_DECISIONS - decisions)
    if missing_decisions:
        errors.append(f"missing required decision kinds: {', '.join(missing_decisions)}")
    return errors


def all_feedback_text(record: dict[str, Any]) -> str:
    feedback = record.get("feedback") if isinstance(record.get("feedback"), dict) else {}
    parts: list[str] = []
    for value in feedback.values():
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(item for item in value if isinstance(item, str))
    return "\n".join(parts).lower()


def feedback_decision_for_record(record: dict[str, Any], case: FounderFeedbackLoopCase) -> dict[str, Any]:
    decision = record.get("governed_decision")
    if isinstance(decision, dict):
        return decision
    classifications = record.get("classifications")
    normalized = [item for item in classifications if isinstance(item, str)] if isinstance(classifications, list) else []
    context = record.get("feedback_context") if isinstance(record.get("feedback_context"), dict) else {}
    feedback = record.get("feedback") if isinstance(record.get("feedback"), dict) else {}
    fallback = feedback_governance_decision(normalized, context, feedback)
    fallback["feedback_run_id"] = record.get("run_id") if isinstance(record.get("run_id"), str) else None
    return fallback


def validate_feedback_record_decision(
    case: FounderFeedbackLoopCase,
    record: dict[str, Any],
    decision: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if record.get("kind") != "workflow_feedback_record":
        errors.append(f"{case.case_id} feedback record kind was {record.get('kind')!r}")
    if record.get("status") != "completed":
        errors.append(f"{case.case_id} feedback record status was {record.get('status')!r}")
    if record.get("target_root") != case.target_root:
        errors.append(f"{case.case_id} target_root mismatch: {record.get('target_root')!r}")
    classifications = record.get("classifications")
    if classifications != list(case.expected_classifications):
        errors.append(
            f"{case.case_id} classifications were {classifications!r}; "
            f"expected {list(case.expected_classifications)!r}"
        )
    if decision.get("kind") != case.expected_decision_kind:
        errors.append(
            f"{case.case_id} decision kind was {decision.get('kind')!r}; "
            f"expected {case.expected_decision_kind!r}"
        )
    if decision.get("gap_class") != case.expected_gap_class:
        errors.append(
            f"{case.case_id} gap_class was {decision.get('gap_class')!r}; expected {case.expected_gap_class!r}"
        )
    if case.expected_decision_kind in ACCEPTED_DECISIONS and decision.get("decision_status") != "accepted":
        errors.append(f"{case.case_id} accepted decision had status {decision.get('decision_status')!r}")
    if case.expected_decision_kind in REJECTED_DECISIONS and decision.get("decision_status") != "rejected":
        errors.append(f"{case.case_id} rejected decision had status {decision.get('decision_status')!r}")
    if decision.get("mutation_policy") != "controller_artifacts_only":
        errors.append(f"{case.case_id} decision mutation_policy was {decision.get('mutation_policy')!r}")
    durable_decision = record.get("governed_decision")
    if not isinstance(durable_decision, dict):
        errors.append(f"{case.case_id} feedback record missing durable governed_decision")
    elif durable_decision != decision:
        errors.append(f"{case.case_id} durable governed_decision did not match validated decision")
    if decision.get("prompt_case_id") != case.case_id:
        errors.append(f"{case.case_id} decision prompt_case_id was {decision.get('prompt_case_id')!r}")
    if decision.get("target_run_id") != record.get("target_run_id"):
        errors.append(
            f"{case.case_id} decision target_run_id {decision.get('target_run_id')!r} "
            f"did not match feedback record {record.get('target_run_id')!r}"
        )
    if decision.get("feedback_run_id") != record.get("run_id"):
        errors.append(
            f"{case.case_id} decision feedback_run_id {decision.get('feedback_run_id')!r} "
            f"did not match feedback record {record.get('run_id')!r}"
        )
    validation_result = decision.get("validation_result")
    if not isinstance(validation_result, dict) or not isinstance(validation_result.get("status"), str):
        errors.append(f"{case.case_id} decision missing validation_result.status")
    if not isinstance(decision.get("target_run_id"), str) or not decision["target_run_id"]:
        errors.append(f"{case.case_id} decision missing target_run_id")
    if not isinstance(decision.get("feedback_run_id"), str) or not decision["feedback_run_id"]:
        errors.append(f"{case.case_id} decision missing feedback_run_id")
    return errors


def validate_founder_feedback_loop_report(
    report: dict[str, Any],
    expected_cases: list[FounderFeedbackLoopCase] | None = None,
) -> list[str]:
    if report.get("kind") != "founder_feedback_loop_live_report":
        return ["report kind must be founder_feedback_loop_live_report"]
    errors: list[str] = []
    expected_by_id = {case.case_id: case for case in expected_cases or []}
    case_reports = report.get("cases")
    if not isinstance(case_reports, list) or not case_reports:
        return ["report must contain at least one case"]
    decisions = set()
    surfaces = set()
    target_roots = set()
    for case_report in case_reports:
        if not isinstance(case_report, dict):
            errors.append("case report must be an object")
            continue
        case_id = case_report.get("case_id")
        if case_report.get("status") != "passed":
            errors.append(f"{case_id} status was {case_report.get('status')!r}")
        decision = case_report.get("decision")
        if isinstance(decision, dict) and isinstance(decision.get("kind"), str):
            decisions.add(decision["kind"])
        else:
            errors.append(f"{case_id} missing decision")
        if expected_by_id:
            case = expected_by_id.get(str(case_id))
            if case is None:
                errors.append(f"unexpected case report: {case_id!r}")
            else:
                feedback_record = case_report.get("feedback_record")
                if not isinstance(feedback_record, dict):
                    errors.append(f"{case_id} missing feedback_record")
                elif isinstance(decision, dict):
                    errors.extend(validate_feedback_record_decision(case, feedback_record, decision))
        surface = case_report.get("surface")
        if isinstance(surface, str):
            surfaces.add(surface)
        target_root = case_report.get("target_root")
        if isinstance(target_root, str):
            target_roots.add(target_root)
        case_errors = case_report.get("errors")
        if isinstance(case_errors, list):
            errors.extend(str(error) for error in case_errors if error)
    missing_decisions = sorted(REQUIRED_DECISIONS - decisions)
    if missing_decisions:
        errors.append(f"missing decision coverage: {', '.join(missing_decisions)}")
    missing_surfaces = sorted(REQUIRED_SURFACES - surfaces)
    if missing_surfaces:
        errors.append(f"missing surface coverage: {', '.join(missing_surfaces)}")
    missing_roots = sorted(REQUIRED_TARGET_ROOTS - target_roots)
    if missing_roots:
        errors.append(f"missing target-root coverage: {', '.join(missing_roots)}")
    if expected_by_id:
        missing_cases = sorted(set(expected_by_id) - {str(item.get("case_id")) for item in case_reports if isinstance(item, dict)})
        if missing_cases:
            errors.append(f"missing expected case reports: {', '.join(missing_cases)}")
    mutation = report.get("mutation_proof")
    if not isinstance(mutation, dict):
        errors.append("report missing mutation_proof")
    else:
        if mutation.get("runtime_changed_files"):
            errors.append(f"runtime metadata mutated: {mutation.get('runtime_changed_files')!r}")
        target_changed = mutation.get("target_changed_files")
        if isinstance(target_changed, dict):
            changed = {root: paths for root, paths in target_changed.items() if paths}
            if changed:
                errors.append(f"target files mutated: {changed!r}")
        else:
            errors.append("mutation_proof.target_changed_files must be an object")
        git_changed = mutation.get("target_git_changed")
        if isinstance(git_changed, dict):
            changed_git = {root: status for root, status in git_changed.items() if status}
            if changed_git:
                errors.append(f"target git status changed: {changed_git!r}")
        else:
            errors.append("mutation_proof.target_git_changed must be an object")
    return errors
