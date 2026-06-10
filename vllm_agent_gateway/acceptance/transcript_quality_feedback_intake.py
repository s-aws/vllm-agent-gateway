"""Phase 158 transcript quality and feedback intake governance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "transcript_quality_feedback_intake_policy"
EXPECTED_REPORT_KIND = "transcript_quality_feedback_intake_report"
EXPECTED_PHASE = 158
EXPECTED_BACKLOG_ID = "P0-BB-022"
EXPECTED_PHASE157_KIND = "founder_field_round1_report"
EXPECTED_PHASE157_PHASE = 157
EXPECTED_PHASE157_BACKLOG_ID = "P0-BB-021"
EXPECTED_FIELD_REPORT_KIND = "founder_field_prompt_evaluation"
EXPECTED_FOUNDER_NOTES_KIND = "transcript_quality_founder_notes"
DEFAULT_POLICY_PATH = Path("runtime") / "transcript_quality_feedback_intake_policy.json"
DEFAULT_PHASE157_REPORT_PATH = (
    Path("runtime-state")
    / "founder-field-round1"
    / "phase157"
    / "phase157-founder-field-round1-report.json"
)
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "transcript-quality-feedback-intake" / "phase158"
DEFAULT_REPORT_PATH = DEFAULT_OUTPUT_DIR / "phase158-transcript-quality-feedback-intake-report.json"
DEFAULT_MARKDOWN_PATH = DEFAULT_OUTPUT_DIR / "phase158-transcript-quality-feedback-intake-report.md"


class IntakeStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class QualityClassification(str, Enum):
    PASS = "pass"
    ADVISORY = "advisory"
    BLOCKER = "blocker"


class FindingCategory(str, Enum):
    PROMPT_ISSUE = "prompt_issue"
    HARNESS_ISSUE = "harness_issue"
    MISSING_SKILL_TOOL = "missing_skill_tool"
    MODEL_CAPABILITY = "model_capability"
    SAFETY_BOUNDARY = "safety_boundary"
    UNSUPPORTED_SCOPE = "unsupported_scope"
    DOCUMENTATION_ISSUE = "documentation_issue"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DecisionKind(str, Enum):
    ACCEPTED_FOR_PHASE159 = "accepted_for_phase159"
    ACCEPTED_FOR_MONITORING = "accepted_for_monitoring"
    REJECTED_NO_ACTION = "rejected_no_action"


class OwnerPath(str, Enum):
    PROMPT_CATALOG_REVIEW = "prompt_catalog_review"
    CONTROLLER_OR_FORMATTER_REPAIR = "controller_or_formatter_repair"
    SKILL_TOOL_GAP_REVIEW = "skill_tool_gap_review"
    MODEL_CAPABILITY_WATCHLIST = "model_capability_watchlist"
    DOCUMENTATION_UPDATE = "documentation_update"
    UNSUPPORTED_SCOPE_BOUNDARY = "unsupported_scope_boundary"


class RerunGate(str, Enum):
    PHASE157_FOUNDER_FIELD_ROUND1 = "phase157_founder_field_round1"
    PHASE159_TARGET_PLUS_HOLDOUT = "phase159_target_plus_holdout"
    PHASE160_STABLE_RELEASE_REFRESH = "phase160_stable_release_refresh"


CATEGORY_OWNER = {
    FindingCategory.PROMPT_ISSUE.value: OwnerPath.PROMPT_CATALOG_REVIEW.value,
    FindingCategory.HARNESS_ISSUE.value: OwnerPath.CONTROLLER_OR_FORMATTER_REPAIR.value,
    FindingCategory.MISSING_SKILL_TOOL.value: OwnerPath.SKILL_TOOL_GAP_REVIEW.value,
    FindingCategory.MODEL_CAPABILITY.value: OwnerPath.MODEL_CAPABILITY_WATCHLIST.value,
    FindingCategory.SAFETY_BOUNDARY.value: OwnerPath.UNSUPPORTED_SCOPE_BOUNDARY.value,
    FindingCategory.UNSUPPORTED_SCOPE.value: OwnerPath.UNSUPPORTED_SCOPE_BOUNDARY.value,
    FindingCategory.DOCUMENTATION_ISSUE.value: OwnerPath.DOCUMENTATION_UPDATE.value,
}


@dataclass(frozen=True)
class TranscriptQualityFeedbackIntakeConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    phase157_report_path: Path = DEFAULT_PHASE157_REPORT_PATH
    founder_notes_path: Path | None = None
    output_path: Path = DEFAULT_REPORT_PATH
    markdown_output_path: Path | None = DEFAULT_MARKDOWN_PATH


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


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


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


def enum_values(enum_class: type[Enum]) -> set[str]:
    return {item.value for item in enum_class}


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 158")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    inputs = policy.get("inputs")
    if not isinstance(inputs, dict):
        errors.append("policy.inputs must be an object")
    elif not isinstance(inputs.get("phase157_report"), str) or not inputs["phase157_report"].strip():
        errors.append("policy.inputs.phase157_report must be a path string")
    expected_source = policy.get("expected_source")
    if not isinstance(expected_source, dict):
        errors.append("policy.expected_source must be an object")
    else:
        expected = {
            "kind": EXPECTED_PHASE157_KIND,
            "phase": EXPECTED_PHASE157_PHASE,
            "status": IntakeStatus.PASSED.value,
            "priority_backlog_id": EXPECTED_PHASE157_BACKLOG_ID,
        }
        for key, value in expected.items():
            if expected_source.get(key) != value:
                errors.append(f"policy.expected_source.{key} must be {value}")
    expected_sets = {
        "required_quality_classifications": enum_values(QualityClassification),
        "finding_categories": enum_values(FindingCategory),
        "severity_levels": enum_values(Severity),
        "decision_kinds": enum_values(DecisionKind),
        "owner_paths": enum_values(OwnerPath),
        "required_rerun_gates": enum_values(RerunGate),
    }
    for key, expected_values in expected_sets.items():
        if set(string_list(policy.get(key))) != expected_values:
            errors.append(f"policy.{key} must be {', '.join(sorted(expected_values))}")
    eligible = set(string_list(policy.get("phase159_eligible_categories")))
    allowed_categories = enum_values(FindingCategory)
    if not eligible:
        errors.append("policy.phase159_eligible_categories must be non-empty")
    elif eligible - allowed_categories:
        errors.append("policy.phase159_eligible_categories must only include known categories")
    min_length = policy.get("founder_note_min_length")
    if not isinstance(min_length, int) or min_length < 8:
        errors.append("policy.founder_note_min_length must be an integer >= 8")
    if policy.get("require_raw_transcript_source") is not True:
        errors.append("policy.require_raw_transcript_source must be true")
    return errors


def source_ref(path: Path | None, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path) if path else None,
        "sha256": artifact_hash(path),
        "kind": payload.get("kind"),
        "phase": payload.get("phase"),
        "status": payload.get("status"),
        "priority_backlog_id": payload.get("priority_backlog_id"),
    }


def case_by_id(cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(case.get("case_id")): case for case in cases if isinstance(case.get("case_id"), str)}


def source_validation_errors(
    *,
    policy: dict[str, Any],
    phase157_report: dict[str, Any],
    field_report: dict[str, Any] | None,
    policy_path: Path | None = None,
    phase157_report_path: Path | None = None,
    field_report_path: Path | None = None,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    errors.extend(
        {
            "id": f"policy.{index}",
            "source": "policy",
            "severity": Severity.HIGH.value,
            "message": error,
        }
        for index, error in enumerate(validate_policy(policy))
    )
    if phase157_report.get("kind") != EXPECTED_PHASE157_KIND:
        errors.append(
            {
                "id": "phase157.kind",
                "source": "phase157_report",
                "severity": Severity.HIGH.value,
                "message": f"Phase 157 report kind must be {EXPECTED_PHASE157_KIND}",
            }
        )
    if phase157_report.get("phase") != EXPECTED_PHASE157_PHASE:
        errors.append(
            {
                "id": "phase157.phase",
                "source": "phase157_report",
                "severity": Severity.HIGH.value,
                "message": "Phase 157 report phase must be 157",
            }
        )
    if phase157_report.get("priority_backlog_id") != EXPECTED_PHASE157_BACKLOG_ID:
        errors.append(
            {
                "id": "phase157.priority_backlog_id",
                "source": "phase157_report",
                "severity": Severity.HIGH.value,
                "message": f"Phase 157 report priority_backlog_id must be {EXPECTED_PHASE157_BACKLOG_ID}",
            }
        )
    if phase157_report.get("status") != IntakeStatus.PASSED.value:
        errors.append(
            {
                "id": "phase157.status",
                "source": "phase157_report",
                "severity": Severity.HIGH.value,
                "message": "Phase 157 report status must be passed before intake",
            }
        )
    if policy_path is not None and phase157_report_path is not None:
        inputs = dict_value(policy.get("inputs"))
        declared_phase157_path = inputs.get("phase157_report")
        if isinstance(declared_phase157_path, str) and declared_phase157_path.strip():
            policy_root = policy_path.resolve().parent.parent
            expected_path = resolve_path(policy_root, declared_phase157_path)
            if expected_path.resolve() != phase157_report_path.resolve():
                errors.append(
                    {
                        "id": "policy.inputs.phase157_report_mismatch",
                        "source": "policy",
                        "severity": Severity.HIGH.value,
                        "message": "policy.inputs.phase157_report must match the Phase 157 report being classified",
                    }
                )
    source_cases = object_list(phase157_report.get("case_results"))
    if not source_cases:
        errors.append(
            {
                "id": "phase157.case_results",
                "source": "phase157_report",
                "severity": Severity.HIGH.value,
                "message": "Phase 157 report must include case_results",
            }
        )
    summary = dict_value(phase157_report.get("summary"))
    classification_counts = {
        "pass_case_count": sum(
            1 for case in source_cases if case.get("quality_classification") == QualityClassification.PASS.value
        ),
        "advisory_case_count": sum(
            1 for case in source_cases if case.get("quality_classification") == QualityClassification.ADVISORY.value
        ),
        "blocker_case_count": sum(
            1 for case in source_cases if case.get("quality_classification") == QualityClassification.BLOCKER.value
        ),
        "case_count": len(source_cases),
    }
    for key, value in classification_counts.items():
        if summary.get(key) != value:
            errors.append(
                {
                    "id": f"phase157.summary.{key}",
                    "source": "phase157_report",
                    "severity": Severity.HIGH.value,
                    "message": f"Phase 157 summary {key} must match case_results",
                }
            )
    allowed_classifications = set(string_list(policy.get("required_quality_classifications")))
    case_ids: list[str] = []
    for index, case in enumerate(source_cases):
        prefix = f"phase157.case_results[{index}]"
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            errors.append(
                {
                    "id": f"{prefix}.case_id",
                    "source": "phase157_report",
                    "severity": Severity.HIGH.value,
                    "message": "case_id must be a non-empty string",
                }
            )
        else:
            case_ids.append(case_id)
        classification = case.get("quality_classification")
        if classification not in allowed_classifications:
            errors.append(
                {
                    "id": f"{prefix}.quality_classification",
                    "source": "phase157_report",
                    "severity": Severity.HIGH.value,
                    "message": "quality_classification must be pass, advisory, or blocker",
                }
            )
        for key in ("target_root", "expected_workflow", "run_id", "initial_difference"):
            if not isinstance(case.get(key), str) or not case[key].strip():
                errors.append(
                    {
                        "id": f"{prefix}.{key}",
                        "source": "phase157_report",
                        "severity": Severity.HIGH.value,
                        "message": f"{key} must be a non-empty string",
                    }
                )
        if case.get("run_id") == "unknown":
            errors.append(
                {
                    "id": f"{prefix}.run_id",
                    "source": "phase157_report",
                    "severity": Severity.HIGH.value,
                    "message": "case run_id must not be unknown",
                }
            )
        if classification == QualityClassification.ADVISORY.value and not str(case.get("prompt_risk") or "").strip():
            errors.append(
                {
                    "id": f"{prefix}.prompt_risk",
                    "source": "phase157_report",
                    "severity": Severity.HIGH.value,
                    "message": "advisory case must include prompt_risk",
                }
            )
        if classification == QualityClassification.PASS.value and str(case.get("prompt_risk") or "").strip():
            errors.append(
                {
                    "id": f"{prefix}.pass_prompt_risk",
                    "source": "phase157_report",
                    "severity": Severity.HIGH.value,
                    "message": "pass case must not include prompt_risk",
                }
            )
        if classification == QualityClassification.BLOCKER.value and (
            case.get("output_contract_status") == IntakeStatus.PASSED.value
            and case.get("semantic_quality_status") == IntakeStatus.PASSED.value
        ):
            errors.append(
                {
                    "id": f"{prefix}.blocker_signal",
                    "source": "phase157_report",
                    "severity": Severity.HIGH.value,
                    "message": "blocker case must include failed contract or semantic status",
                }
            )
    duplicate_ids = sorted({case_id for case_id in case_ids if case_ids.count(case_id) > 1})
    for case_id in duplicate_ids:
        errors.append(
            {
                "id": f"phase157.duplicate_case.{case_id}",
                "source": "phase157_report",
                "severity": Severity.HIGH.value,
                "message": "Phase 157 case_results must not include duplicate case IDs",
            }
        )
    if policy.get("require_raw_transcript_source") is True:
        if field_report is None:
            errors.append(
                {
                    "id": "field_report.missing",
                    "source": "field_report",
                    "severity": Severity.HIGH.value,
                    "message": "raw Phase 157 field report must be available for transcript references",
                }
            )
        elif field_report.get("kind") != EXPECTED_FIELD_REPORT_KIND:
            errors.append(
                {
                    "id": "field_report.kind",
                    "source": "field_report",
                    "severity": Severity.HIGH.value,
                    "message": f"field report kind must be {EXPECTED_FIELD_REPORT_KIND}",
                }
            )
        else:
            reported_field_hash = phase157_report.get("field_report_sha256")
            if (
                field_report_path is not None
                and field_report_path.is_absolute()
                and field_report_path.is_file()
                and isinstance(reported_field_hash, str)
                and artifact_hash(field_report_path) != reported_field_hash
            ):
                errors.append(
                    {
                        "id": "field_report.sha256_mismatch",
                        "source": "field_report",
                        "severity": Severity.HIGH.value,
                        "message": "field report file hash must match Phase 157 field_report_sha256",
                    }
                )
            raw_cases = case_by_id(object_list(field_report.get("cases")))
            for case in source_cases:
                case_id = case.get("case_id")
                if not isinstance(case_id, str):
                    continue
                raw = raw_cases.get(case_id)
                if raw is None:
                    errors.append(
                        {
                            "id": f"field_report.{case_id}.missing",
                            "source": "field_report",
                            "severity": Severity.HIGH.value,
                            "message": "field report must include every Phase 157 case",
                        }
                    )
                    continue
                for key in ("prompt", "text_sample", "run_id"):
                    if not isinstance(raw.get(key), str) or not raw[key].strip():
                        errors.append(
                            {
                                "id": f"field_report.{case_id}.{key}",
                                "source": "field_report",
                                "severity": Severity.HIGH.value,
                                "message": f"raw field case must include {key}",
                            }
                        )
                if raw.get("run_id") != case.get("run_id"):
                    errors.append(
                        {
                            "id": f"field_report.{case_id}.run_id_mismatch",
                            "source": "field_report",
                            "severity": Severity.HIGH.value,
                            "message": "raw field case run_id must match Phase 157 case result",
                        }
                    )
                if isinstance(raw.get("prompt"), str) and raw.get("prompt") and case.get("prompt_sha256") != sha256_text(
                    raw["prompt"]
                ):
                    errors.append(
                        {
                            "id": f"field_report.{case_id}.prompt_sha256_mismatch",
                            "source": "field_report",
                            "severity": Severity.HIGH.value,
                            "message": "raw field case prompt hash must match Phase 157 prompt_sha256",
                        }
                    )
                if raw.get("text_sha256") != case.get("text_sha256"):
                    errors.append(
                        {
                            "id": f"field_report.{case_id}.text_sha256_mismatch",
                            "source": "field_report",
                            "severity": Severity.HIGH.value,
                            "message": "raw field case text_sha256 must match Phase 157 response hash",
                        }
                    )
    return errors


def phase159_eligible(policy: dict[str, Any], category: str) -> bool:
    return category in set(string_list(policy.get("phase159_eligible_categories")))


def owner_for_category(category: str) -> str:
    return CATEGORY_OWNER.get(category, OwnerPath.CONTROLLER_OR_FORMATTER_REPAIR.value)


def rerun_gate_for_category(policy: dict[str, Any], category: str) -> str:
    if phase159_eligible(policy, category):
        return RerunGate.PHASE159_TARGET_PLUS_HOLDOUT.value
    return RerunGate.PHASE157_FOUNDER_FIELD_ROUND1.value


def decision_for_category(policy: dict[str, Any], category: str) -> str:
    if phase159_eligible(policy, category):
        return DecisionKind.ACCEPTED_FOR_PHASE159.value
    return DecisionKind.ACCEPTED_FOR_MONITORING.value


def classify_blocker_case(case: dict[str, Any]) -> tuple[str, str, str]:
    forbidden = str(case.get("initial_difference") or "").lower()
    if "unsupported" in forbidden:
        return (
            FindingCategory.UNSUPPORTED_SCOPE.value,
            Severity.HIGH.value,
            "Phase 157 blocker indicates unsupported scope handling.",
        )
    if "safety" in forbidden or "mutation" in forbidden:
        return (
            FindingCategory.SAFETY_BOUNDARY.value,
            Severity.HIGH.value,
            "Phase 157 blocker indicates a safety-boundary failure.",
        )
    if case.get("output_contract_status") != IntakeStatus.PASSED.value:
        return (
            FindingCategory.HARNESS_ISSUE.value,
            Severity.HIGH.value,
            "Phase 157 output contract failed and needs controller or formatter repair.",
        )
    if case.get("expected_skill_id"):
        return (
            FindingCategory.MISSING_SKILL_TOOL.value,
            Severity.HIGH.value,
            "Phase 157 semantic quality failed on a skill-backed prompt and needs skill/tool review.",
        )
    return (
        FindingCategory.MODEL_CAPABILITY.value,
        Severity.HIGH.value,
        "Phase 157 semantic quality failed and needs model-capability or harness repair review.",
    )


def evidence_refs_for_case(
    *,
    case: dict[str, Any],
    raw_case: dict[str, Any] | None,
    phase157_report_path: Path | None,
    field_report_path: Path | None,
    field_markdown_path: Path | None,
) -> dict[str, Any]:
    run_id = case.get("run_id")
    return {
        "phase157_report_path": str(phase157_report_path) if phase157_report_path else None,
        "field_report_path": str(field_report_path) if field_report_path else None,
        "field_markdown_path": str(field_markdown_path) if field_markdown_path else None,
        "controller_artifact_hint": (
            str(Path("runtime-state") / "controller-artifacts" / "workflow-router" / str(run_id))
            if isinstance(run_id, str) and run_id
            else None
        ),
        "prompt_sha256": case.get("prompt_sha256") or (
            hashlib.sha256(str(raw_case.get("prompt", "")).encode("utf-8")).hexdigest()
            if raw_case is not None
            else None
        ),
        "response_text_sha256": case.get("text_sha256") or (raw_case.get("text_sha256") if raw_case else None),
    }


def build_case_finding(
    *,
    policy: dict[str, Any],
    case: dict[str, Any],
    raw_case: dict[str, Any] | None,
    phase157_report_path: Path | None,
    field_report_path: Path | None,
    field_markdown_path: Path | None,
) -> dict[str, Any] | None:
    classification = str(case.get("quality_classification") or "")
    if classification == QualityClassification.PASS.value:
        return None
    if classification == QualityClassification.ADVISORY.value:
        category = FindingCategory.PROMPT_ISSUE.value
        severity = Severity.LOW.value
        message = str(case.get("prompt_risk") or "").strip()
        finding_suffix = "prompt-risk"
    else:
        category, severity, message = classify_blocker_case(case)
        finding_suffix = "blocker"
    eligible = phase159_eligible(policy, category)
    return {
        "finding_id": f"phase158-{case.get('case_id')}-{finding_suffix}",
        "source": "phase157_case",
        "case_id": case.get("case_id"),
        "target_root": case.get("target_root"),
        "selected_workflow": case.get("expected_workflow"),
        "run_id": case.get("run_id"),
        "quality_classification": classification,
        "category": category,
        "severity": severity,
        "decision": decision_for_category(policy, category),
        "owner_path": owner_for_category(category),
        "required_rerun_gate": rerun_gate_for_category(policy, category),
        "phase159_eligible": eligible,
        "message": message,
        "initial_difference": case.get("initial_difference"),
        "prompt": raw_case.get("prompt") if raw_case else None,
        "refined_prompt": raw_case.get("refined_prompt") if raw_case else None,
        "transcript_reference": evidence_refs_for_case(
            case=case,
            raw_case=raw_case,
            phase157_report_path=phase157_report_path,
            field_report_path=field_report_path,
            field_markdown_path=field_markdown_path,
        ),
    }


def validate_founder_notes_payload(founder_notes: dict[str, Any] | None) -> list[str]:
    if founder_notes is None:
        return []
    errors: list[str] = []
    if founder_notes.get("kind") != EXPECTED_FOUNDER_NOTES_KIND:
        errors.append(f"founder_notes.kind must be {EXPECTED_FOUNDER_NOTES_KIND}")
    if founder_notes.get("phase") != EXPECTED_PHASE:
        errors.append("founder_notes.phase must be 158")
    if not isinstance(founder_notes.get("notes"), list):
        errors.append("founder_notes.notes must be a list")
    return errors


def classify_founder_notes(
    *,
    policy: dict[str, Any],
    founder_notes: dict[str, Any] | None,
    source_cases: dict[str, dict[str, Any]],
    raw_cases: dict[str, dict[str, Any]],
    phase157_report_path: Path | None,
    field_report_path: Path | None,
    field_markdown_path: Path | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, message in enumerate(validate_founder_notes_payload(founder_notes)):
        field_id = message.split(" must ", 1)[0] if " must " in message else f"founder_notes.{index}"
        errors.append(
            {
                "id": field_id,
                "source": "founder_notes",
                "severity": Severity.HIGH.value,
                "message": message,
            }
        )
    if founder_notes is None or errors:
        return accepted, rejected, errors
    allowed_categories = enum_values(FindingCategory)
    allowed_severities = enum_values(Severity)
    min_length = int(policy.get("founder_note_min_length", 12))
    notes_value = founder_notes.get("notes")
    notes = notes_value if isinstance(notes_value, list) else []
    for index, note in enumerate(notes):
        if not isinstance(note, dict):
            rejected.append(
                {
                    "finding_id": f"phase158-note-{index}-rejected",
                    "source": "founder_note",
                    "note_id": f"note-{index}",
                    "case_id": None,
                    "decision": DecisionKind.REJECTED_NO_ACTION.value,
                    "reasons": ["malformed_note"],
                    "message": "",
                }
            )
            continue
        note_id = note.get("note_id")
        case_id = note.get("case_id")
        text = note.get("text")
        category = note.get("category")
        severity = note.get("severity")
        reasons: list[str] = []
        if not isinstance(note_id, str) or not note_id.strip():
            reasons.append("missing_note_id")
            note_id = f"note-{index}"
        if not isinstance(case_id, str) or not case_id.strip() or case_id not in source_cases:
            reasons.append("unlinked_case_id")
        if not isinstance(text, str) or len(text.strip()) < min_length:
            reasons.append("vague_or_empty_feedback")
        if category not in allowed_categories:
            reasons.append("unknown_or_missing_category")
        if severity not in allowed_severities:
            reasons.append("unknown_or_missing_severity")
        if reasons:
            rejected.append(
                {
                    "finding_id": f"phase158-{note_id}-rejected",
                    "source": "founder_note",
                    "note_id": note_id,
                    "case_id": case_id,
                    "decision": DecisionKind.REJECTED_NO_ACTION.value,
                    "reasons": reasons,
                    "message": text if isinstance(text, str) else "",
                }
            )
            continue
        source_case = source_cases[str(case_id)]
        raw_case = raw_cases.get(str(case_id))
        accepted.append(
            {
                "finding_id": f"phase158-{note_id}",
                "source": "founder_note",
                "note_id": note_id,
                "case_id": case_id,
                "target_root": source_case.get("target_root"),
                "selected_workflow": source_case.get("expected_workflow"),
                "run_id": source_case.get("run_id"),
                "quality_classification": source_case.get("quality_classification"),
                "category": category,
                "severity": severity,
                "decision": decision_for_category(policy, str(category)),
                "owner_path": owner_for_category(str(category)),
                "required_rerun_gate": rerun_gate_for_category(policy, str(category)),
                "phase159_eligible": phase159_eligible(policy, str(category)),
                "message": text.strip(),
                "initial_difference": source_case.get("initial_difference"),
                "prompt": raw_case.get("prompt") if raw_case else None,
                "refined_prompt": raw_case.get("refined_prompt") if raw_case else None,
                "transcript_reference": evidence_refs_for_case(
                    case=source_case,
                    raw_case=raw_case,
                    phase157_report_path=phase157_report_path,
                    field_report_path=field_report_path,
                    field_markdown_path=field_markdown_path,
                ),
            }
        )
    return accepted, rejected, errors


def build_transcript_quality_feedback_intake_report(
    *,
    policy: dict[str, Any],
    phase157_report: dict[str, Any],
    field_report: dict[str, Any] | None = None,
    founder_notes: dict[str, Any] | None = None,
    policy_path: Path | None = None,
    phase157_report_path: Path | None = None,
    field_report_path: Path | None = None,
    field_markdown_path: Path | None = None,
    founder_notes_path: Path | None = None,
) -> dict[str, Any]:
    validation_errors = source_validation_errors(
        policy=policy,
        phase157_report=phase157_report,
        field_report=field_report,
        policy_path=policy_path,
        phase157_report_path=phase157_report_path,
        field_report_path=field_report_path,
    )
    source_cases = object_list(phase157_report.get("case_results"))
    source_cases_by_id = case_by_id(source_cases)
    raw_cases_by_id = case_by_id(object_list(field_report.get("cases")) if field_report is not None else [])
    accepted_findings = [
        finding
        for case in source_cases
        for finding in [
            build_case_finding(
                policy=policy,
                case=case,
                raw_case=raw_cases_by_id.get(str(case.get("case_id"))),
                phase157_report_path=phase157_report_path,
                field_report_path=field_report_path,
                field_markdown_path=field_markdown_path,
            )
        ]
        if finding is not None
    ]
    founder_accepted, rejected_findings, founder_note_errors = classify_founder_notes(
        policy=policy,
        founder_notes=founder_notes,
        source_cases=source_cases_by_id,
        raw_cases=raw_cases_by_id,
        phase157_report_path=phase157_report_path,
        field_report_path=field_report_path,
        field_markdown_path=field_markdown_path,
    )
    accepted_findings.extend(founder_accepted)
    validation_errors.extend(founder_note_errors)
    phase159_count = sum(1 for finding in accepted_findings if finding.get("phase159_eligible") is True)
    advisory_count = sum(
        1 for finding in accepted_findings if finding.get("quality_classification") == QualityClassification.ADVISORY.value
    )
    blocker_count = sum(
        1 for finding in accepted_findings if finding.get("quality_classification") == QualityClassification.BLOCKER.value
    )
    category_counts = {
        category: sum(1 for finding in accepted_findings if finding.get("category") == category)
        for category in sorted(enum_values(FindingCategory))
    }
    category_counts = {key: value for key, value in category_counts.items() if value}
    owner_counts = {
        owner: sum(1 for finding in accepted_findings if finding.get("owner_path") == owner)
        for owner in sorted(enum_values(OwnerPath))
    }
    owner_counts = {key: value for key, value in owner_counts.items() if value}
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": IntakeStatus.PASSED.value if not validation_errors else IntakeStatus.FAILED.value,
        "created_at": utc_timestamp(),
        "source_refs": {
            "policy": source_ref(policy_path, policy),
            "phase157_report": source_ref(phase157_report_path, phase157_report),
            "phase157_field_report": source_ref(field_report_path, field_report or {}),
            "founder_notes": source_ref(founder_notes_path, founder_notes or {}),
        },
        "accepted_findings": accepted_findings,
        "rejected_findings": rejected_findings,
        "validation_errors": validation_errors,
        "phase159_required": phase159_count > 0,
        "summary": {
            "source_case_count": len(source_cases),
            "accepted_finding_count": len(accepted_findings),
            "rejected_finding_count": len(rejected_findings),
            "phase157_advisory_finding_count": advisory_count,
            "phase157_blocker_finding_count": blocker_count,
            "founder_note_count": len((founder_notes or {}).get("notes") if isinstance((founder_notes or {}).get("notes"), list) else []),
            "phase159_eligible_count": phase159_count,
            "phase159_required": phase159_count > 0,
            "category_counts": category_counts,
            "owner_counts": owner_counts,
            "validation_error_count": len(validation_errors),
        },
    }
    return report


def stable_view(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: report.get(key)
        for key in (
            "schema_version",
            "kind",
            "phase",
            "priority_backlog_id",
            "status",
            "source_refs",
            "accepted_findings",
            "rejected_findings",
            "validation_errors",
            "phase159_required",
            "summary",
        )
    }


def validate_transcript_quality_feedback_intake_report(
    report: dict[str, Any],
    *,
    policy: dict[str, Any],
    phase157_report: dict[str, Any],
    field_report: dict[str, Any] | None = None,
    founder_notes: dict[str, Any] | None = None,
    policy_path: Path | None = None,
    phase157_report_path: Path | None = None,
    field_report_path: Path | None = None,
    field_markdown_path: Path | None = None,
    founder_notes_path: Path | None = None,
) -> list[str]:
    expected = build_transcript_quality_feedback_intake_report(
        policy=policy,
        phase157_report=phase157_report,
        field_report=field_report,
        founder_notes=founder_notes,
        policy_path=policy_path,
        phase157_report_path=phase157_report_path,
        field_report_path=field_report_path,
        field_markdown_path=field_markdown_path,
        founder_notes_path=founder_notes_path,
    )
    if stable_view(report) != stable_view(expected):
        return ["report must match rebuilt transcript quality feedback intake report"]
    return []


def markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Transcript Quality And Feedback Intake",
        "",
        f"- Status: {report.get('status')}",
        f"- Source cases: {summary.get('source_case_count')}",
        f"- Accepted findings: {summary.get('accepted_finding_count')}",
        f"- Rejected findings: {summary.get('rejected_finding_count')}",
        f"- Phase 159 eligible: {summary.get('phase159_eligible_count')}",
        f"- Phase 159 required: {report.get('phase159_required')}",
        "",
        "## Accepted Findings",
        "",
        "| Finding | Source | Case | Category | Severity | Decision | Owner | Rerun Gate | Phase 159 | Message |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    accepted = object_list(report.get("accepted_findings"))
    if accepted:
        for finding in accepted:
            message = str(finding.get("message") or "").replace("\n", " ")[:220]
            lines.append(
                "| {finding_id} | {source} | {case_id} | {category} | {severity} | {decision} | {owner} | {gate} | {eligible} | {message} |".format(
                    finding_id=finding.get("finding_id"),
                    source=finding.get("source"),
                    case_id=finding.get("case_id"),
                    category=finding.get("category"),
                    severity=finding.get("severity"),
                    decision=finding.get("decision"),
                    owner=finding.get("owner_path"),
                    gate=finding.get("required_rerun_gate"),
                    eligible=finding.get("phase159_eligible"),
                    message=message,
                )
            )
    else:
        lines.append("| none | none | none | none | none | none | none | none | none | none |")
    lines.extend(
        [
            "",
            "## Rejected Findings",
            "",
            "| Finding | Source | Case | Decision | Reasons |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    rejected = object_list(report.get("rejected_findings"))
    if rejected:
        for finding in rejected:
            lines.append(
                "| {finding_id} | {source} | {case_id} | {decision} | {reasons} |".format(
                    finding_id=finding.get("finding_id"),
                    source=finding.get("source"),
                    case_id=finding.get("case_id"),
                    decision=finding.get("decision"),
                    reasons=", ".join(string_list(finding.get("reasons"))),
                )
            )
    else:
        lines.append("| none | none | none | none | none |")
    lines.extend(["", "## Validation Errors", ""])
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(f"- {error.get('id')}: {error.get('message')}" for error in errors)
    else:
        lines.append("- none")
    return "\n".join(lines).rstrip() + "\n"


def load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    return read_json_object(path)


def run_transcript_quality_feedback_intake(config: TranscriptQualityFeedbackIntakeConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    phase157_report_path = resolve_path(config_root, config.phase157_report_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path) if config.markdown_output_path else None
    policy = read_json_object(policy_path)
    phase157_report = read_json_object(phase157_report_path)
    field_report_path: Path | None = None
    field_markdown_path: Path | None = None
    if isinstance(phase157_report.get("field_report_path"), str):
        field_report_path = resolve_path(config_root, phase157_report["field_report_path"])
    if isinstance(phase157_report.get("markdown_report_path"), str):
        field_markdown_path = resolve_path(config_root, phase157_report["markdown_report_path"])
    field_report = load_optional_json(field_report_path)
    founder_notes_path = resolve_path(config_root, config.founder_notes_path) if config.founder_notes_path else None
    if founder_notes_path is None:
        inputs = dict_value(policy.get("inputs"))
        optional_path = inputs.get("optional_founder_notes")
        if isinstance(optional_path, str) and optional_path.strip():
            candidate = resolve_path(config_root, optional_path)
            founder_notes_path = candidate if candidate.is_file() else None
    founder_notes = load_optional_json(founder_notes_path)
    report = build_transcript_quality_feedback_intake_report(
        policy=policy,
        phase157_report=phase157_report,
        field_report=field_report,
        founder_notes=founder_notes,
        policy_path=policy_path,
        phase157_report_path=phase157_report_path,
        field_report_path=field_report_path,
        field_markdown_path=field_markdown_path,
        founder_notes_path=founder_notes_path,
    )
    validation_errors = validate_transcript_quality_feedback_intake_report(
        report,
        policy=policy,
        phase157_report=phase157_report,
        field_report=field_report,
        founder_notes=founder_notes,
        policy_path=policy_path,
        phase157_report_path=phase157_report_path,
        field_report_path=field_report_path,
        field_markdown_path=field_markdown_path,
        founder_notes_path=founder_notes_path,
    )
    if validation_errors:
        report["status"] = IntakeStatus.FAILED.value
        report["validation_errors"] = [
            *object_list(report.get("validation_errors")),
            *[
                {
                    "id": f"self_validation.{index}",
                    "source": "transcript_quality_feedback_intake",
                    "severity": Severity.HIGH.value,
                    "message": error,
                }
                for index, error in enumerate(validation_errors)
            ],
        ]
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    if markdown_output_path:
        write_text(markdown_output_path, markdown_report(report))
        report["markdown_report_path"] = str(markdown_output_path.resolve())
    write_json(output_path, report)
    if markdown_output_path:
        write_text(markdown_output_path, markdown_report(report))
    return report
