"""Phase 198 founder feedback intake and repair proposal governance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "founder_feedback_intake_repair_policy"
EXPECTED_REPORT_KIND = "founder_feedback_intake_repair_report"
EXPECTED_PHASE = 198
EXPECTED_BACKLOG_ID = "P0-BB-062"
EXPECTED_PHASE197_KIND = "founder_trial_execution_round_report"
EXPECTED_FOUNDER_NOTES_KIND = "founder_feedback_notes"
DEFAULT_POLICY_PATH = Path("runtime") / "founder_feedback_intake_repair_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase198" / "phase198-founder-feedback-intake-repair-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase198" / "phase198-founder-feedback-intake-repair-report.md"


class FounderFeedbackIntakeStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class SourceClassification(str, Enum):
    ADVISORY = "advisory"
    BLOCKER = "blocker"


class SourceType(str, Enum):
    PHASE197_CASE = "phase197_case"
    FOUNDER_NOTE = "founder_note"


class IssueCategory(str, Enum):
    PROMPT_ISSUE = "prompt_issue"
    ANSWER_QUALITY = "answer_quality"
    ROUTING_ISSUE = "routing_issue"
    HARNESS_ISSUE = "harness_issue"
    CONTROLLER_OR_FORMATTER = "controller_or_formatter"
    MISSING_SKILL_TOOL = "missing_skill_tool"
    MODEL_CAPABILITY = "model_capability"
    SAFETY_BOUNDARY = "safety_boundary"
    UNSUPPORTED_SCOPE = "unsupported_scope"
    DOCUMENTATION_ISSUE = "documentation_issue"


class RepairDecision(str, Enum):
    ACCEPTED_REPAIR_PROPOSAL = "accepted_repair_proposal"
    ACCEPTED_MONITORING_OR_DOCUMENTATION = "accepted_monitoring_or_documentation"
    ACCEPTED_FUTURE_ROADMAP_PROPOSAL = "accepted_future_roadmap_proposal"
    ACCEPTED_RELEASE_BLOCKER = "accepted_release_blocker"
    REJECTED_NO_ACTION = "rejected_no_action"


class ClosureStatus(str, Enum):
    OPEN = "open"
    CLOSED_WITH_PROOF = "closed_with_proof"
    DEFERRED_NONBLOCKING = "deferred_nonblocking"
    REJECTED = "rejected"


class OwnerPath(str, Enum):
    PROMPT_CATALOG_REVIEW = "prompt_catalog_review"
    CONTROLLER_OR_FORMATTER_REPAIR = "controller_or_formatter_repair"
    SKILL_TOOL_GAP_REVIEW = "skill_tool_gap_review"
    MODEL_CAPABILITY_WATCHLIST = "model_capability_watchlist"
    DOCUMENTATION_UPDATE = "documentation_update"
    UNSUPPORTED_SCOPE_BOUNDARY = "unsupported_scope_boundary"
    RELEASE_CLOSEOUT_OWNER = "release_closeout_owner"


class RerunGate(str, Enum):
    PHASE197_FOUNDER_TRIAL_RERUN = "phase197_founder_trial_rerun"
    TARGET_CASE_ANYTHINGLLM_RERUN = "target_case_anythingllm_rerun"
    TARGET_PLUS_HOLDOUT_ANYTHINGLLM_RERUN = "target_plus_holdout_anythingllm_rerun"
    DOCS_INDEX_CHECK = "docs_index_check"
    POST_RESTART_RUNTIME_READINESS = "post_restart_runtime_readiness"
    PHASE199_BETA_CLOSEOUT_REVIEW = "phase199_beta_closeout_review"
    FULL_BASH_REGRESSION = "full_bash_regression"


REQUIRED_FOUNDER_NOTE_FIELDS = {
    "case_id",
    "prompt",
    "target_run_id",
    "classification",
    "severity",
    "actual_response_excerpt",
    "expected_behavior",
    "fixture_root",
    "created_at",
}


@dataclass(frozen=True)
class FounderFeedbackIntakeRepairConfig:
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


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


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


def enum_values(enum_class: type[Enum]) -> set[str]:
    return {item.value for item in enum_class}


def validation_error(error_id: str, message: str, severity: str = "high", source: str = "policy") -> dict[str, str]:
    return {"id": error_id, "severity": severity, "source": source, "message": message}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "policy.schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"policy.kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "policy.phase must be 198"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    source = dict_value(policy.get("required_phase197_report"))
    if source.get("expected_kind") != EXPECTED_PHASE197_KIND:
        errors.append(validation_error("policy.required_phase197_report.expected_kind", f"expected_kind must be {EXPECTED_PHASE197_KIND}"))
    if source.get("expected_status") != FounderFeedbackIntakeStatus.PASSED.value:
        errors.append(validation_error("policy.required_phase197_report.expected_status", "expected_status must be passed"))
    if source.get("expected_phase") != 197:
        errors.append(validation_error("policy.required_phase197_report.expected_phase", "expected_phase must be 197"))
    if not isinstance(source.get("path"), str) or not source["path"].strip():
        errors.append(validation_error("policy.required_phase197_report.path", "Phase 197 report path is required"))
    expected_sets = {
        "required_source_classifications": enum_values(SourceClassification),
        "allowed_source_types": enum_values(SourceType),
        "allowed_issue_categories": enum_values(IssueCategory),
        "allowed_decisions": enum_values(RepairDecision),
        "allowed_closure_statuses": enum_values(ClosureStatus),
        "allowed_owner_paths": enum_values(OwnerPath),
        "allowed_rerun_gates": enum_values(RerunGate),
    }
    for key, expected in expected_sets.items():
        if set(string_list(policy.get(key))) != expected:
            errors.append(validation_error(f"policy.{key}", f"{key} must match the governed enum set"))
    blocker_policy = dict_value(policy.get("blocker_policy"))
    if blocker_policy.get("must_block_phase199") is not True:
        errors.append(validation_error("policy.blocker_policy.must_block_phase199", "blockers must block Phase 199"))
    if blocker_policy.get("required_decision") != RepairDecision.ACCEPTED_RELEASE_BLOCKER.value:
        errors.append(validation_error("policy.blocker_policy.required_decision", "blockers must become release blockers"))
    if not set(string_list(blocker_policy.get("required_rerun_gates"))).issubset(enum_values(RerunGate)):
        errors.append(validation_error("policy.blocker_policy.required_rerun_gates", "blocker rerun gates must be known"))
    advisory_policy = dict_value(policy.get("advisory_policy"))
    if advisory_policy.get("must_have_decision") is not True:
        errors.append(validation_error("policy.advisory_policy.must_have_decision", "advisories must have explicit decisions"))
    if advisory_policy.get("default_decision") not in enum_values(RepairDecision):
        errors.append(validation_error("policy.advisory_policy.default_decision", "advisory default decision must be known"))
    if advisory_policy.get("default_owner_path") not in enum_values(OwnerPath):
        errors.append(validation_error("policy.advisory_policy.default_owner_path", "advisory default owner path must be known"))
    if not string_list(policy.get("required_docs")):
        errors.append(validation_error("policy.required_docs", "required docs are required"))
    if policy.get("acceptance_marker") != "PHASE198 FOUNDER FEEDBACK INTAKE REPAIR PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 198"))
    return errors


def load_json_source(config_root: Path, raw_path: str, source: str) -> tuple[Path, dict[str, Any], list[dict[str, str]]]:
    path = resolve_path(config_root, raw_path)
    if not path.is_file():
        return path, {}, [validation_error(f"{source}.missing", f"{source} is missing: {raw_path}", source=source)]
    try:
        return path, read_json_object(path), []
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        return path, {}, [
            validation_error(
                f"{source}.malformed",
                f"{source} is malformed: {type(exc).__name__}: {exc}",
                source=source,
            )
        ]


def load_optional_founder_notes(config_root: Path, raw_path: object) -> tuple[Path | None, dict[str, Any], list[dict[str, str]]]:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None, {}, []
    path = resolve_path(config_root, raw_path)
    if not path.is_file():
        return path, {}, []
    try:
        notes = read_json_object(path)
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        return path, {}, [
            validation_error(
                "founder_notes.malformed",
                f"founder notes are malformed: {type(exc).__name__}: {exc}",
                source="founder_notes",
            )
        ]
    errors: list[dict[str, str]] = []
    if notes.get("kind") != EXPECTED_FOUNDER_NOTES_KIND:
        errors.append(validation_error("founder_notes.kind", f"founder notes kind must be {EXPECTED_FOUNDER_NOTES_KIND}", source="founder_notes"))
    if notes.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("founder_notes.phase", "founder notes phase must be 198", source="founder_notes"))
    return path, notes, errors


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


def phase197_field_report_ref(config_root: Path, phase197_report: dict[str, Any]) -> dict[str, Any]:
    field_ref = dict_value(dict_value(phase197_report.get("source_refs")).get("field_report"))
    raw_path = field_ref.get("path")
    path = resolve_path(config_root, raw_path) if isinstance(raw_path, str) and raw_path.strip() else None
    actual_hash = artifact_hash(path)
    return {
        "path": str(path) if path is not None else None,
        "exists": path.is_file() if path is not None else False,
        "expected_sha256": field_ref.get("sha256"),
        "actual_sha256": actual_hash,
        "hash_status": "passed" if actual_hash and actual_hash == field_ref.get("sha256") else "failed",
        "kind": field_ref.get("kind"),
        "phase": field_ref.get("phase"),
        "status": field_ref.get("status"),
    }


def doc_records(config_root: Path, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    docs: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for raw_path in string_list(policy.get("required_docs")):
        path = resolve_path(config_root, raw_path)
        exists = path.is_file()
        docs.append({"path": raw_path, "exists": exists, "sha256": artifact_hash(path)})
        if not exists:
            errors.append(validation_error(f"doc_missing.{raw_path}", f"required doc is missing: {raw_path}", "medium", "documentation"))
    return docs, errors


def validate_phase197_source(config_root: Path, report: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    source_policy = dict_value(policy.get("required_phase197_report"))
    if report.get("kind") != source_policy.get("expected_kind"):
        errors.append(validation_error("phase197.kind", f"Phase 197 report kind must be {source_policy.get('expected_kind')}", source="phase197"))
    if report.get("status") != source_policy.get("expected_status"):
        errors.append(validation_error("phase197.status", f"Phase 197 report status must be {source_policy.get('expected_status')}", source="phase197"))
    if report.get("phase") != source_policy.get("expected_phase"):
        errors.append(validation_error("phase197.phase", "Phase 197 report phase must be 197", source="phase197"))
    if object_list(report.get("validation_errors")):
        errors.append(validation_error("phase197.validation_errors", "Phase 197 validation errors must be empty", source="phase197"))
    if dict_value(report.get("summary")).get("validation_error_count") not in (None, 0):
        errors.append(validation_error("phase197.validation_error_count", "Phase 197 validation_error_count must be 0", source="phase197"))
    field_ref = phase197_field_report_ref(config_root, report)
    if field_ref.get("hash_status") != "passed":
        errors.append(validation_error("phase197.field_report_hash", "Phase 197 field report source ref must exist and match its hash", source="phase197"))
    return errors


def source_cases(phase197_report: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    required = set(string_list(policy.get("required_source_classifications")))
    return [
        case
        for case in object_list(phase197_report.get("case_results"))
        if str(case.get("quality_classification") or "") in required
    ]


def phase197_cases_by_id(phase197_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(case.get("case_id")): case for case in object_list(phase197_report.get("case_results")) if isinstance(case.get("case_id"), str)}


def case_artifact_proof(config_root: Path, case: dict[str, Any]) -> dict[str, Any]:
    raw_path = case.get("response_artifact_path")
    path = resolve_path(config_root, raw_path) if isinstance(raw_path, str) and raw_path.strip() else None
    expected_hash = case.get("response_artifact_sha256")
    actual_hash = artifact_hash(path)
    return {
        "response_artifact_path": str(path) if path is not None else None,
        "response_artifact_exists": path.is_file() if path is not None else False,
        "response_artifact_sha256": expected_hash,
        "actual_response_artifact_sha256": actual_hash,
        "response_artifact_hash_status": "passed" if actual_hash and actual_hash == expected_hash else "failed",
    }


def issue_category_for_case(case: dict[str, Any]) -> str:
    text = " ".join(str(case.get(key) or "") for key in ("prompt", "prompt_risk", "initial_difference", "suggested_prompt_if_missed")).lower()
    if any(term in text for term in ("handler", "route", "routing", "ui sender")):
        return IssueCategory.ROUTING_ISSUE.value
    if any(term in text for term in ("test", "command", "validation", "validate", "bash")):
        return IssueCategory.DOCUMENTATION_ISSUE.value
    if any(term in text for term in ("scope", "surface", "do-not-touch", "do not touch", "boundary")):
        return IssueCategory.SAFETY_BOUNDARY.value
    if any(term in text for term in ("evidence", "line", "source ref", "source")):
        return IssueCategory.ANSWER_QUALITY.value
    return IssueCategory.PROMPT_ISSUE.value


def owner_for_issue(issue_category: str, source_classification: str) -> str:
    if source_classification == SourceClassification.BLOCKER.value:
        return OwnerPath.CONTROLLER_OR_FORMATTER_REPAIR.value
    if issue_category in {IssueCategory.ROUTING_ISSUE.value, IssueCategory.CONTROLLER_OR_FORMATTER.value}:
        return OwnerPath.CONTROLLER_OR_FORMATTER_REPAIR.value
    if issue_category == IssueCategory.MISSING_SKILL_TOOL.value:
        return OwnerPath.SKILL_TOOL_GAP_REVIEW.value
    if issue_category == IssueCategory.MODEL_CAPABILITY.value:
        return OwnerPath.MODEL_CAPABILITY_WATCHLIST.value
    if issue_category in {IssueCategory.SAFETY_BOUNDARY.value, IssueCategory.UNSUPPORTED_SCOPE.value}:
        return OwnerPath.UNSUPPORTED_SCOPE_BOUNDARY.value
    if issue_category == IssueCategory.DOCUMENTATION_ISSUE.value:
        return OwnerPath.DOCUMENTATION_UPDATE.value
    return OwnerPath.PROMPT_CATALOG_REVIEW.value


def decision_for_classification(source_classification: str, policy: dict[str, Any]) -> str:
    if source_classification == SourceClassification.BLOCKER.value:
        return dict_value(policy.get("blocker_policy")).get("required_decision") or RepairDecision.ACCEPTED_RELEASE_BLOCKER.value
    return dict_value(policy.get("advisory_policy")).get("default_decision") or RepairDecision.ACCEPTED_MONITORING_OR_DOCUMENTATION.value


def rerun_gates_for_record(source_classification: str, policy: dict[str, Any]) -> list[str]:
    if source_classification == SourceClassification.BLOCKER.value:
        return string_list(dict_value(policy.get("blocker_policy")).get("required_rerun_gates"))
    return string_list(dict_value(policy.get("advisory_policy")).get("required_rerun_gates"))


def recommended_change(case: dict[str, Any], issue_category: str, source_classification: str) -> str:
    case_id = case.get("case_id")
    if source_classification == SourceClassification.BLOCKER.value:
        return f"Repair the runtime path for {case_id}, then rerun the target case, holdouts, and full Bash regression."
    if issue_category == IssueCategory.ROUTING_ISSUE.value:
        return f"Clarify {case_id} prompt/catalog guidance so handler versus caller boundaries are explicit."
    if issue_category == IssueCategory.DOCUMENTATION_ISSUE.value:
        return f"Clarify {case_id} prompt/catalog guidance so Bash verification and residual risk expectations are explicit."
    if issue_category == IssueCategory.SAFETY_BOUNDARY.value:
        return f"Clarify {case_id} prompt/catalog guidance so touch and do-not-touch boundaries are explicit."
    prompt_risk = str(case.get("prompt_risk") or "").strip()
    if prompt_risk:
        return f"Clarify {case_id} prompt/catalog guidance to remove ambiguity: {prompt_risk}"
    return f"Keep {case_id} under monitoring; current evidence does not justify runtime repair."


def decision_record_for_case(config_root: Path, case: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    source_classification = str(case.get("quality_classification") or "")
    issue_category = issue_category_for_case(case)
    decision = decision_for_classification(source_classification, policy)
    phase199_blocking = source_classification == SourceClassification.BLOCKER.value
    closure_status = ClosureStatus.OPEN.value if phase199_blocking else ClosureStatus.DEFERRED_NONBLOCKING.value
    prompt = str(case.get("prompt") or "")
    artifact_proof = case_artifact_proof(config_root, case)
    case_id = str(case.get("case_id"))
    return {
        "proposal_id": f"P198-{case_id}-{issue_category.replace('_', '-')}",
        "source_type": SourceType.PHASE197_CASE.value,
        "case_id": case_id,
        "run_id": case.get("run_id"),
        "target_root": case.get("target_root"),
        "selected_workflow": case.get("expected_workflow"),
        "source_quality_classification": source_classification,
        "prompt": prompt,
        "prompt_sha256": sha256_text(prompt),
        "prompt_risk": case.get("prompt_risk") or "",
        "initial_difference": case.get("initial_difference") or "",
        "issue_category": issue_category,
        "severity": "critical" if phase199_blocking else "medium",
        "decision": decision,
        "decision_rationale": recommended_change(case, issue_category, source_classification),
        "owner_path": owner_for_issue(issue_category, source_classification),
        "required_rerun_gate": rerun_gates_for_record(source_classification, policy),
        "phase199_blocking": phase199_blocking,
        "closure_status": closure_status,
        "source_proof": artifact_proof,
        "acceptance_criteria": [
            "The source Phase 197 run ID and response artifact hash remain valid.",
            "The owner path can execute or explicitly defer the selected decision.",
            "The required rerun gate proves the target case before Phase 199 closeout.",
        ],
    }


def note_rejection(note: dict[str, Any], index: int, reasons: list[str]) -> dict[str, Any]:
    return {
        "proposal_id": f"P198-founder-note-{index + 1:03d}",
        "source_type": SourceType.FOUNDER_NOTE.value,
        "case_id": note.get("case_id"),
        "decision": RepairDecision.REJECTED_NO_ACTION.value,
        "closure_status": ClosureStatus.REJECTED.value,
        "rejection_reasons": reasons,
        "raw_note": note,
    }


def validate_founder_note_link(note: dict[str, Any], case_lookup: dict[str, dict[str, Any]]) -> tuple[dict[str, Any] | None, list[str]]:
    reasons: list[str] = []
    missing = sorted(field for field in REQUIRED_FOUNDER_NOTE_FIELDS if not isinstance(note.get(field), str) or not note[field].strip())
    if missing:
        reasons.append("missing required fields: " + ", ".join(missing))
    case_id = note.get("case_id")
    case = case_lookup.get(str(case_id)) if isinstance(case_id, str) else None
    if case is None:
        reasons.append("case_id does not match a Phase 197 case")
        return None, reasons
    if note.get("target_run_id") != case.get("run_id"):
        reasons.append("target_run_id does not match the Phase 197 run_id")
    if note.get("fixture_root") != case.get("target_root"):
        reasons.append("fixture_root does not match the Phase 197 target_root")
    if note.get("prompt") != case.get("prompt"):
        reasons.append("prompt does not match the Phase 197 prompt")
    return case, reasons


def decision_record_for_founder_note(config_root: Path, note: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    severity = str(note.get("severity") or "").lower()
    phase199_blocking = severity == "blocker"
    decision = RepairDecision.ACCEPTED_RELEASE_BLOCKER.value if phase199_blocking else RepairDecision.ACCEPTED_REPAIR_PROPOSAL.value
    issue_category = IssueCategory.ANSWER_QUALITY.value
    prompt = str(case.get("prompt") or "")
    case_id = str(case.get("case_id"))
    return {
        "proposal_id": f"P198-{case_id}-founder-note-{sha256_text(str(note))[:8]}",
        "source_type": SourceType.FOUNDER_NOTE.value,
        "case_id": case_id,
        "run_id": case.get("run_id"),
        "target_root": case.get("target_root"),
        "selected_workflow": case.get("expected_workflow"),
        "source_quality_classification": note.get("classification"),
        "prompt": prompt,
        "prompt_sha256": sha256_text(prompt),
        "prompt_risk": case.get("prompt_risk") or "",
        "initial_difference": note.get("expected_behavior") or "",
        "issue_category": issue_category,
        "severity": severity or "medium",
        "decision": decision,
        "decision_rationale": str(note.get("expected_behavior") or "Founder note accepted for repair proposal."),
        "owner_path": OwnerPath.RELEASE_CLOSEOUT_OWNER.value if not phase199_blocking else OwnerPath.CONTROLLER_OR_FORMATTER_REPAIR.value,
        "required_rerun_gate": [
            RerunGate.TARGET_CASE_ANYTHINGLLM_RERUN.value,
            RerunGate.PHASE199_BETA_CLOSEOUT_REVIEW.value,
        ],
        "phase199_blocking": phase199_blocking,
        "closure_status": ClosureStatus.OPEN.value if phase199_blocking else ClosureStatus.DEFERRED_NONBLOCKING.value,
        "source_proof": case_artifact_proof(config_root, case),
        "founder_feedback": note,
        "acceptance_criteria": [
            "The founder note is linked to the exact Phase 197 run ID, fixture root, and prompt.",
            "The source response artifact hash remains valid.",
            "The rerun gate proves the expected behavior before closure.",
        ],
    }


def founder_note_records(
    config_root: Path,
    founder_notes: dict[str, Any],
    phase197_report: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    decision_records: list[dict[str, Any]] = []
    rejected_records: list[dict[str, Any]] = []
    case_lookup = phase197_cases_by_id(phase197_report)
    for index, note in enumerate(object_list(founder_notes.get("notes"))):
        case, reasons = validate_founder_note_link(note, case_lookup)
        if reasons or case is None:
            rejected_records.append(note_rejection(note, index, reasons))
            continue
        decision_records.append(decision_record_for_founder_note(config_root, note, case))
    return decision_records, rejected_records


def validate_decision_records(
    config_root: Path,
    decision_records: list[dict[str, Any]],
    rejected_records: list[dict[str, Any]],
    source_case_ids: list[str],
    policy: dict[str, Any],
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    phase197_records = [item for item in decision_records if item.get("source_type") == SourceType.PHASE197_CASE.value]
    phase197_case_ids = [str(item.get("case_id")) for item in phase197_records if isinstance(item.get("case_id"), str)]
    if phase197_case_ids != source_case_ids:
        errors.append(validation_error("decision_records.phase197_case_ids", "decision records must cover every advisory/blocker source case in source order", source="decision_records"))
    allowed = {
        "source_type": set(string_list(policy.get("allowed_source_types"))),
        "issue_category": set(string_list(policy.get("allowed_issue_categories"))),
        "decision": set(string_list(policy.get("allowed_decisions"))),
        "closure_status": set(string_list(policy.get("allowed_closure_statuses"))),
        "owner_path": set(string_list(policy.get("allowed_owner_paths"))),
        "required_rerun_gate": set(string_list(policy.get("allowed_rerun_gates"))),
    }
    seen_proposal_ids: set[str] = set()
    for index, record in enumerate(decision_records):
        prefix = f"decision_records[{index}]"
        proposal = record.get("proposal_id")
        if not isinstance(proposal, str) or not proposal.strip():
            errors.append(validation_error(f"{prefix}.proposal_id", "proposal_id is required", source="decision_records"))
        elif proposal in seen_proposal_ids:
            errors.append(validation_error(f"{prefix}.proposal_id_duplicate", "proposal_id must be unique", source="decision_records"))
        else:
            seen_proposal_ids.add(proposal)
        for key in ("source_type", "issue_category", "decision", "closure_status", "owner_path"):
            if record.get(key) not in allowed[key]:
                errors.append(validation_error(f"{prefix}.{key}", f"{key} must be allowed", source="decision_records"))
        gates = string_list(record.get("required_rerun_gate"))
        if not gates:
            errors.append(validation_error(f"{prefix}.required_rerun_gate", "at least one rerun gate is required", source="decision_records"))
        if set(gates) - allowed["required_rerun_gate"]:
            errors.append(validation_error(f"{prefix}.required_rerun_gate.unknown", "rerun gates must be allowed", source="decision_records"))
        for key in ("case_id", "run_id", "target_root", "selected_workflow", "prompt", "prompt_sha256", "decision_rationale"):
            if not isinstance(record.get(key), str) or not record[key].strip():
                errors.append(validation_error(f"{prefix}.{key}", f"{key} is required", source="decision_records"))
        if record.get("prompt_sha256") != sha256_text(str(record.get("prompt") or "")):
            errors.append(validation_error(f"{prefix}.prompt_sha256", "prompt_sha256 must match prompt", source="decision_records"))
        proof = dict_value(record.get("source_proof"))
        raw_path = proof.get("response_artifact_path")
        path = resolve_path(config_root, raw_path) if isinstance(raw_path, str) and raw_path.strip() else None
        actual_hash = artifact_hash(path)
        if proof.get("response_artifact_hash_status") != "passed" or actual_hash != proof.get("response_artifact_sha256"):
            errors.append(validation_error(f"{prefix}.source_proof.response_artifact_hash", "response artifact hash must be freshly verified", source="decision_records"))
        if len(string_list(record.get("acceptance_criteria"))) < 3:
            errors.append(validation_error(f"{prefix}.acceptance_criteria", "at least three acceptance criteria are required", source="decision_records"))
        if record.get("source_quality_classification") == SourceClassification.BLOCKER.value:
            if record.get("decision") != RepairDecision.ACCEPTED_RELEASE_BLOCKER.value:
                errors.append(validation_error(f"{prefix}.blocker_decision", "blockers must be accepted release blockers", "critical", "decision_records"))
            if record.get("phase199_blocking") is not True:
                errors.append(validation_error(f"{prefix}.blocker_phase199", "blockers must block Phase 199", "critical", "decision_records"))
    for index, record in enumerate(rejected_records):
        prefix = f"rejected_records[{index}]"
        if record.get("decision") != RepairDecision.REJECTED_NO_ACTION.value:
            errors.append(validation_error(f"{prefix}.decision", "rejected records must use rejected_no_action", source="rejected_records"))
        if record.get("closure_status") != ClosureStatus.REJECTED.value:
            errors.append(validation_error(f"{prefix}.closure_status", "rejected records must use rejected closure status", source="rejected_records"))
        if not string_list(record.get("rejection_reasons")):
            errors.append(validation_error(f"{prefix}.rejection_reasons", "rejected records must include explicit rejection reasons", source="rejected_records"))
    return errors


def count_by(records: list[dict[str, Any]], key: str, allowed_values: set[str] | None = None) -> dict[str, int]:
    values = sorted(allowed_values or {str(record.get(key)) for record in records if record.get(key) is not None})
    return {value: sum(1 for record in records if record.get(key) == value) for value in values}


def build_founder_feedback_intake_repair_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    phase197_path: Path,
    phase197_report: dict[str, Any],
    founder_notes_path: Path | None,
    founder_notes: dict[str, Any],
    source_load_errors: list[dict[str, str]],
    policy_path: Path | None = None,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    errors.extend(validate_policy(policy))
    errors.extend(source_load_errors)
    errors.extend(validate_phase197_source(config_root, phase197_report, policy))
    docs, doc_errors = doc_records(config_root, policy)
    errors.extend(doc_errors)
    source_nonpass_cases = source_cases(phase197_report, policy)
    phase197_decisions = [decision_record_for_case(config_root, case, policy) for case in source_nonpass_cases]
    founder_decisions, rejected_records = founder_note_records(config_root, founder_notes, phase197_report)
    decision_records = [*phase197_decisions, *founder_decisions]
    errors.extend(
        validate_decision_records(
            config_root,
            decision_records,
            rejected_records,
            [str(case.get("case_id")) for case in source_nonpass_cases],
            policy,
        )
    )
    classification_counts = {
        "advisory": sum(1 for item in source_nonpass_cases if item.get("quality_classification") == SourceClassification.ADVISORY.value),
        "blocker": sum(1 for item in source_nonpass_cases if item.get("quality_classification") == SourceClassification.BLOCKER.value),
    }
    phase199_blocked = bool(errors) or any(record.get("phase199_blocking") is True for record in decision_records)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": FounderFeedbackIntakeStatus.FAILED.value if errors else FounderFeedbackIntakeStatus.PASSED.value,
        "created_at": utc_timestamp(),
        "policy_path": str(policy_path or DEFAULT_POLICY_PATH),
        "policy_sha256": artifact_hash(policy_path),
        "source_refs": {
            "phase197_report": source_ref(phase197_path, phase197_report),
            "phase197_field_report": phase197_field_report_ref(config_root, phase197_report),
            "founder_notes": source_ref(founder_notes_path, founder_notes),
        },
        "decision_records": decision_records,
        "rejected_records": rejected_records,
        "docs": docs,
        "validation_errors": errors,
        "summary": {
            "source_advisory_count": classification_counts["advisory"],
            "source_blocker_count": classification_counts["blocker"],
            "founder_note_count": len(object_list(founder_notes.get("notes"))),
            "accepted_proposal_count": len(decision_records),
            "rejected_record_count": len(rejected_records),
            "release_blocker_count": sum(1 for item in decision_records if item.get("phase199_blocking") is True),
            "open_required_repair_count": sum(
                1
                for item in decision_records
                if item.get("closure_status") == ClosureStatus.OPEN.value or item.get("phase199_blocking") is True
            ),
            "owner_counts": count_by(decision_records, "owner_path", enum_values(OwnerPath)),
            "rerun_gate_counts": {
                gate.value: sum(1 for item in decision_records if gate.value in string_list(item.get("required_rerun_gate")))
                for gate in RerunGate
            },
            "decision_counts": count_by(decision_records, "decision", enum_values(RepairDecision)),
            "phase199_blocked": phase199_blocked,
            "phase199_ready_after_intake": not phase199_blocked,
            "validation_error_count": len(errors),
            "next_action": "repair or close blocking records before Phase 199"
            if phase199_blocked
            else "work Phase 199 V1 beta release closeout",
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
            "status",
            "policy_path",
            "policy_sha256",
            "source_refs",
            "decision_records",
            "rejected_records",
            "docs",
            "validation_errors",
            "summary",
        )
    }


def validate_founder_feedback_intake_repair_report(
    report: dict[str, Any],
    *,
    config_root: Path,
    policy: dict[str, Any],
    phase197_path: Path,
    phase197_report: dict[str, Any],
    founder_notes_path: Path | None,
    founder_notes: dict[str, Any],
    source_load_errors: list[dict[str, str]],
    policy_path: Path | None = None,
) -> list[str]:
    expected = build_founder_feedback_intake_repair_report(
        config_root=config_root,
        policy=policy,
        phase197_path=phase197_path,
        phase197_report=phase197_report,
        founder_notes_path=founder_notes_path,
        founder_notes=founder_notes,
        source_load_errors=source_load_errors,
        policy_path=policy_path,
    )
    if stable_report_view(report) != stable_report_view(expected):
        return ["report must match rebuilt founder feedback intake repair report"]
    return []


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Phase 198 Founder Feedback Intake And Repair Proposal",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Source advisories: `{summary.get('source_advisory_count')}`",
        f"- Source blockers: `{summary.get('source_blocker_count')}`",
        f"- Accepted proposals: `{summary.get('accepted_proposal_count')}`",
        f"- Rejected records: `{summary.get('rejected_record_count')}`",
        f"- Phase 199 blocked: `{summary.get('phase199_blocked')}`",
        f"- Next action: `{summary.get('next_action')}`",
        "",
        "## Decision Records",
        "",
        "| Proposal | Case | Source | Category | Decision | Owner | Closure | Blocks Phase 199 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in object_list(report.get("decision_records")):
        lines.append(
            f"| `{item.get('proposal_id')}` | `{item.get('case_id')}` | `{item.get('source_type')}` | `{item.get('issue_category')}` | `{item.get('decision')}` | `{item.get('owner_path')}` | `{item.get('closure_status')}` | `{item.get('phase199_blocking')}` |"
        )
    rejected = object_list(report.get("rejected_records"))
    if rejected:
        lines.extend(["", "## Rejected Records", ""])
        lines.extend(f"- `{item.get('proposal_id')}`: {'; '.join(string_list(item.get('rejection_reasons')))}" for item in rejected)
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(["", "## Validation Errors", ""])
        lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in errors)
    return "\n".join(lines) + "\n"


def run_founder_feedback_intake_repair(config: FounderFeedbackIntakeRepairConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    phase197_spec = dict_value(policy.get("required_phase197_report"))
    phase197_path, phase197_report, source_errors = load_json_source(
        config_root,
        str(phase197_spec.get("path") or ""),
        "phase197",
    )
    founder_notes_path, founder_notes, founder_note_errors = load_optional_founder_notes(
        config_root,
        policy.get("optional_founder_notes_path"),
    )
    source_load_errors = [*source_errors, *founder_note_errors]
    report = build_founder_feedback_intake_repair_report(
        config_root=config_root,
        policy=policy,
        phase197_path=phase197_path,
        phase197_report=phase197_report,
        founder_notes_path=founder_notes_path,
        founder_notes=founder_notes,
        source_load_errors=source_load_errors,
        policy_path=policy_path,
    )
    validation_errors = validate_founder_feedback_intake_repair_report(
        report,
        config_root=config_root,
        policy=policy,
        phase197_path=phase197_path,
        phase197_report=phase197_report,
        founder_notes_path=founder_notes_path,
        founder_notes=founder_notes,
        source_load_errors=source_load_errors,
        policy_path=policy_path,
    )
    if validation_errors:
        report["status"] = FounderFeedbackIntakeStatus.FAILED.value
        report["validation_errors"] = [
            *object_list(report.get("validation_errors")),
            *[
                validation_error(f"self_validation.{index}", error, "critical", "founder_feedback_intake_repair")
                for index, error in enumerate(validation_errors)
            ],
        ]
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
        report["summary"]["phase199_blocked"] = True
        report["summary"]["phase199_ready_after_intake"] = False
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
