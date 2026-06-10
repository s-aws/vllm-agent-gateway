"""Phase 159 Priority 0 repair-loop closure governance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "priority0_repair_loop_policy"
EXPECTED_REPORT_KIND = "priority0_repair_loop_report"
EXPECTED_REPAIR_RECORDS_KIND = "priority0_repair_loop_records"
EXPECTED_PHASE = 159
EXPECTED_BACKLOG_ID = "P0-BB-023"
EXPECTED_PHASE158_KIND = "transcript_quality_feedback_intake_report"
EXPECTED_PHASE158_PHASE = 158
EXPECTED_PHASE158_BACKLOG_ID = "P0-BB-022"
DEFAULT_POLICY_PATH = Path("runtime") / "priority0_repair_loop_policy.json"
DEFAULT_PHASE158_REPORT_PATH = (
    Path("runtime-state")
    / "transcript-quality-feedback-intake"
    / "phase158"
    / "phase158-transcript-quality-feedback-intake-report.json"
)
DEFAULT_REPAIR_RECORDS_PATH = Path("runtime-state") / "priority0-repair-loop" / "phase159" / "repair-records.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "priority0-repair-loop" / "phase159"
DEFAULT_REPORT_PATH = DEFAULT_OUTPUT_DIR / "phase159-priority0-repair-loop-report.json"
DEFAULT_MARKDOWN_PATH = DEFAULT_OUTPUT_DIR / "phase159-priority0-repair-loop-report.md"


class RepairLoopStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


class RepairMode(str, Enum):
    NO_REPAIR_REQUIRED = "no_repair_required"
    REPAIRS_CLOSED = "repairs_closed"
    BLOCKED_WITH_NEXT_ACTION = "blocked_with_next_action"


class ClosureStatus(str, Enum):
    CLOSED_WITH_TARGET_HOLDOUT_PROOF = "closed_with_target_holdout_proof"
    OPEN_BLOCKED = "open_blocked"


class FindingDecision(str, Enum):
    ACCEPTED_FOR_PHASE159 = "accepted_for_phase159"
    ACCEPTED_FOR_MONITORING = "accepted_for_monitoring"


class LiveSurface(str, Enum):
    GATEWAY = "gateway"
    ANYTHINGLLM = "anythingllm"


@dataclass(frozen=True)
class Priority0RepairLoopConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    phase158_report_path: Path = DEFAULT_PHASE158_REPORT_PATH
    repair_records_path: Path | None = None
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


def load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    return read_json_object(path)


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
        errors.append("policy.phase must be 159")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    inputs = policy.get("inputs")
    if not isinstance(inputs, dict):
        errors.append("policy.inputs must be an object")
    elif not isinstance(inputs.get("phase158_report"), str) or not inputs["phase158_report"].strip():
        errors.append("policy.inputs.phase158_report must be a path string")
    expected_source = policy.get("expected_source")
    if not isinstance(expected_source, dict):
        errors.append("policy.expected_source must be an object")
    else:
        expected = {
            "kind": EXPECTED_PHASE158_KIND,
            "phase": EXPECTED_PHASE158_PHASE,
            "status": RepairLoopStatus.PASSED.value,
            "priority_backlog_id": EXPECTED_PHASE158_BACKLOG_ID,
        }
        for key, value in expected.items():
            if expected_source.get(key) != value:
                errors.append(f"policy.expected_source.{key} must be {value}")
    if set(string_list(policy.get("allowed_repair_modes"))) != enum_values(RepairMode):
        errors.append("policy.allowed_repair_modes must include all governed repair modes")
    if set(string_list(policy.get("allowed_closure_statuses"))) != enum_values(ClosureStatus):
        errors.append("policy.allowed_closure_statuses must include all governed closure statuses")
    if set(string_list(policy.get("required_live_surfaces"))) != enum_values(LiveSurface):
        errors.append("policy.required_live_surfaces must include gateway and anythingllm")
    if policy.get("required_result_status") != RepairLoopStatus.PASSED.value:
        errors.append("policy.required_result_status must be passed")
    if policy.get("required_mutation_status") != "unchanged":
        errors.append("policy.required_mutation_status must be unchanged")
    if policy.get("required_rerun_gate") != "phase159_target_plus_holdout":
        errors.append("policy.required_rerun_gate must be phase159_target_plus_holdout")
    if policy.get("next_phase") != 160:
        errors.append("policy.next_phase must be 160")
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


def source_validation_errors(
    *,
    policy: dict[str, Any],
    phase158_report: dict[str, Any],
    policy_path: Path | None,
    phase158_report_path: Path | None,
    repair_records: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    errors.extend(
        {
            "id": f"policy.{index}",
            "source": "policy",
            "severity": "high",
            "message": error,
        }
        for index, error in enumerate(validate_policy(policy))
    )
    if policy_path is not None and phase158_report_path is not None:
        inputs = dict_value(policy.get("inputs"))
        declared_phase158_path = inputs.get("phase158_report")
        if isinstance(declared_phase158_path, str) and declared_phase158_path.strip():
            policy_root = policy_path.resolve().parent.parent
            expected_path = resolve_path(policy_root, declared_phase158_path)
            if expected_path.resolve() != phase158_report_path.resolve():
                errors.append(
                    {
                        "id": "policy.inputs.phase158_report_mismatch",
                        "source": "policy",
                        "severity": "high",
                        "message": "policy.inputs.phase158_report must match the Phase 158 report being closed",
                    }
                )
    if phase158_report.get("kind") != EXPECTED_PHASE158_KIND:
        errors.append(
            {
                "id": "phase158.kind",
                "source": "phase158_report",
                "severity": "high",
                "message": f"Phase 158 report kind must be {EXPECTED_PHASE158_KIND}",
            }
        )
    if phase158_report.get("phase") != EXPECTED_PHASE158_PHASE:
        errors.append(
            {
                "id": "phase158.phase",
                "source": "phase158_report",
                "severity": "high",
                "message": "Phase 158 report phase must be 158",
            }
        )
    if phase158_report.get("priority_backlog_id") != EXPECTED_PHASE158_BACKLOG_ID:
        errors.append(
            {
                "id": "phase158.priority_backlog_id",
                "source": "phase158_report",
                "severity": "high",
                "message": f"Phase 158 report priority_backlog_id must be {EXPECTED_PHASE158_BACKLOG_ID}",
            }
        )
    if phase158_report.get("status") != RepairLoopStatus.PASSED.value:
        errors.append(
            {
                "id": "phase158.status",
                "source": "phase158_report",
                "severity": "high",
                "message": "Phase 158 report status must be passed before repair-loop closure",
            }
        )
    findings = object_list(phase158_report.get("accepted_findings"))
    summary = dict_value(phase158_report.get("summary"))
    phase159_eligible_count = sum(1 for finding in findings if finding.get("phase159_eligible") is True)
    if summary.get("accepted_finding_count") != len(findings):
        errors.append(
            {
                "id": "phase158.summary.accepted_finding_count",
                "source": "phase158_report",
                "severity": "high",
                "message": "Phase 158 accepted_finding_count must match accepted_findings",
            }
        )
    if summary.get("phase159_eligible_count") != phase159_eligible_count:
        errors.append(
            {
                "id": "phase158.summary.phase159_eligible_count",
                "source": "phase158_report",
                "severity": "high",
                "message": "Phase 158 phase159_eligible_count must match accepted_findings",
            }
        )
    if (phase158_report.get("phase159_required") is True) != (phase159_eligible_count > 0):
        errors.append(
            {
                "id": "phase158.phase159_required",
                "source": "phase158_report",
                "severity": "high",
                "message": "Phase 158 phase159_required must match eligible findings",
            }
        )
    if repair_records is not None:
        if repair_records.get("kind") != EXPECTED_REPAIR_RECORDS_KIND:
            errors.append(
                {
                    "id": "repair_records.kind",
                    "source": "repair_records",
                    "severity": "high",
                    "message": f"repair records kind must be {EXPECTED_REPAIR_RECORDS_KIND}",
                }
            )
        if repair_records.get("phase") != EXPECTED_PHASE:
            errors.append(
                {
                    "id": "repair_records.phase",
                    "source": "repair_records",
                    "severity": "high",
                    "message": "repair records phase must be 159",
                }
            )
        if not isinstance(repair_records.get("records"), list):
            errors.append(
                {
                    "id": "repair_records.records",
                    "source": "repair_records",
                    "severity": "high",
                    "message": "repair records must include a records list",
                }
            )
    return errors


def findings_by_id(findings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(finding.get("finding_id")): finding
        for finding in findings
        if isinstance(finding.get("finding_id"), str) and finding["finding_id"].strip()
    }


def duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def repair_records_by_finding(repair_records: dict[str, Any] | None) -> tuple[dict[str, dict[str, Any]], list[str]]:
    records_value = (repair_records or {}).get("records")
    records = [record for record in records_value if isinstance(record, dict)] if isinstance(records_value, list) else []
    finding_ids = [str(record.get("finding_id")) for record in records if isinstance(record.get("finding_id"), str)]
    duplicates = duplicate_values(finding_ids)
    return (
        {
            str(record.get("finding_id")): record
            for record in records
            if isinstance(record.get("finding_id"), str) and record["finding_id"].strip()
        },
        duplicates,
    )


def malformed_repair_record_errors(repair_records: dict[str, Any] | None) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    records_value = (repair_records or {}).get("records")
    records = records_value if isinstance(records_value, list) else []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(
                {
                    "id": f"repair_records[{index}].malformed",
                    "source": "repair_records",
                    "severity": "high",
                    "message": "repair record entries must be objects",
                }
            )
            continue
        if not isinstance(record.get("finding_id"), str) or not record["finding_id"].strip():
            errors.append(
                {
                    "id": f"repair_records[{index}].finding_id",
                    "source": "repair_records",
                    "severity": "high",
                    "message": "repair record finding_id must be a non-empty string",
                }
            )
    return errors


def result_status(value: object) -> str:
    return value if isinstance(value, str) else ""


def load_json_file(path_value: object) -> dict[str, Any] | None:
    if not isinstance(path_value, str) or not path_value.strip():
        return None
    path = Path(path_value)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def validate_proof_report(report: dict[str, Any] | None, *, expected_kind: str, required_status: str) -> list[str]:
    if report is None:
        return [f"{expected_kind} proof report must exist and be readable JSON"]
    blockers: list[str] = []
    if report.get("kind") != expected_kind:
        blockers.append(f"{expected_kind} proof report kind must be {expected_kind}")
    if report.get("status") != required_status:
        blockers.append(f"{expected_kind} proof report status must be {required_status}")
    if report.get("result_status") != required_status:
        blockers.append(f"{expected_kind} proof report result_status must be {required_status}")
    return blockers


def validate_closed_record(policy: dict[str, Any], record: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if record.get("required_rerun_gate") != policy.get("required_rerun_gate"):
        blockers.append("required_rerun_gate must be phase159_target_plus_holdout")
    if set(string_list(record.get("live_surfaces"))) != set(string_list(policy.get("required_live_surfaces"))):
        blockers.append("live_surfaces must include gateway and anythingllm")
    if result_status(record.get("target_result_status")) != policy.get("required_result_status"):
        blockers.append("target_result_status must be passed")
    if result_status(record.get("holdout_result_status")) != policy.get("required_result_status"):
        blockers.append("holdout_result_status must be passed")
    if record.get("mutation_status") != policy.get("required_mutation_status"):
        blockers.append("mutation_status must be unchanged")
    for key in ("target_report_path", "holdout_report_path", "repair_summary"):
        if not isinstance(record.get(key), str) or not record[key].strip():
            blockers.append(f"{key} must be a non-empty string")
    target_report = load_json_file(record.get("target_report_path"))
    holdout_report = load_json_file(record.get("holdout_report_path"))
    blockers.extend(
        validate_proof_report(
            target_report,
            expected_kind="priority0_repair_target_proof",
            required_status=str(policy.get("required_result_status")),
        )
    )
    blockers.extend(
        validate_proof_report(
            holdout_report,
            expected_kind="priority0_repair_holdout_proof",
            required_status=str(policy.get("required_result_status")),
        )
    )
    return blockers


def validate_open_record(record: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    for key in ("blocker_reason", "next_action"):
        if not isinstance(record.get(key), str) or len(record[key].strip()) < 20:
            blockers.append(f"{key} must explain the open blocker")
    return blockers


def build_repair_items(
    *,
    policy: dict[str, Any],
    phase158_report: dict[str, Any],
    repair_records: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    findings = object_list(phase158_report.get("accepted_findings"))
    finding_map = findings_by_id(findings)
    repair_map, duplicate_ids = repair_records_by_finding(repair_records)
    eligible_findings = [finding for finding in findings if finding.get("phase159_eligible") is True]
    monitoring_findings = [finding for finding in findings if finding.get("phase159_eligible") is not True]
    repair_items: list[dict[str, Any]] = []
    monitoring_items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    errors.extend(malformed_repair_record_errors(repair_records))
    for finding_id in duplicate_ids:
        errors.append(
            {
                "id": f"repair_records.{finding_id}.duplicate",
                "source": "repair_records",
                "severity": "high",
                "message": "repair records must not include duplicate finding IDs",
            }
        )
    for record_id in sorted(set(repair_map) - set(finding_map)):
        errors.append(
            {
                "id": f"repair_records.{record_id}.unknown_finding",
                "source": "repair_records",
                "severity": "high",
                "message": "repair record finding_id must link to a Phase 158 finding",
            }
        )
    for finding in monitoring_findings:
        finding_id = str(finding.get("finding_id"))
        if finding_id in repair_map:
            errors.append(
                {
                    "id": f"repair_records.{finding_id}.not_eligible",
                    "source": "repair_records",
                    "severity": "medium",
                    "message": "monitoring-only finding must not be converted into Phase 159 repair work",
                }
            )
        monitoring_items.append(
            {
                "finding_id": finding_id,
                "case_id": finding.get("case_id"),
                "category": finding.get("category"),
                "decision": finding.get("decision"),
                "owner_path": finding.get("owner_path"),
                "closure_status": "monitoring_only",
                "phase159_eligible": False,
            }
        )
    for finding in eligible_findings:
        finding_id = str(finding.get("finding_id"))
        record = repair_map.get(finding_id)
        if record is None:
            errors.append(
                {
                    "id": f"repair_records.{finding_id}.missing",
                    "source": "repair_records",
                    "severity": "high",
                    "message": "Phase 159 eligible finding requires a repair closure record",
                }
            )
            repair_items.append(
                {
                    "finding_id": finding_id,
                    "case_id": finding.get("case_id"),
                    "category": finding.get("category"),
                    "owner_path": finding.get("owner_path"),
                    "closure_status": "missing",
                    "blockers": ["missing repair closure record"],
                }
            )
            continue
        closure_status = record.get("closure_status")
        if closure_status not in enum_values(ClosureStatus):
            errors.append(
                {
                    "id": f"repair_records.{finding_id}.closure_status",
                    "source": "repair_records",
                    "severity": "high",
                    "message": "closure_status must be closed_with_target_holdout_proof or open_blocked",
                }
            )
            blockers = ["invalid closure_status"]
        elif closure_status == ClosureStatus.CLOSED_WITH_TARGET_HOLDOUT_PROOF.value:
            blockers = validate_closed_record(policy, record)
        else:
            blockers = validate_open_record(record)
        for index, blocker in enumerate(blockers):
            errors.append(
                {
                    "id": f"repair_records.{finding_id}.blocker.{index}",
                    "source": "repair_records",
                    "severity": "high",
                    "message": blocker,
                }
            )
        repair_items.append(
            {
                "finding_id": finding_id,
                "case_id": finding.get("case_id"),
                "category": finding.get("category"),
                "owner_path": finding.get("owner_path"),
                "closure_status": closure_status,
                "blockers": blockers,
                "target_result_status": record.get("target_result_status"),
                "holdout_result_status": record.get("holdout_result_status"),
                "mutation_status": record.get("mutation_status"),
                "blocker_reason": record.get("blocker_reason"),
                "next_action": record.get("next_action"),
            }
        )
    return repair_items, monitoring_items, errors


def choose_repair_mode(repair_items: list[dict[str, Any]], eligible_count: int) -> str:
    if eligible_count == 0:
        return RepairMode.NO_REPAIR_REQUIRED.value
    open_count = sum(1 for item in repair_items if item.get("closure_status") == ClosureStatus.OPEN_BLOCKED.value)
    if open_count:
        return RepairMode.BLOCKED_WITH_NEXT_ACTION.value
    return RepairMode.REPAIRS_CLOSED.value


def build_priority0_repair_loop_report(
    *,
    policy: dict[str, Any],
    phase158_report: dict[str, Any],
    repair_records: dict[str, Any] | None = None,
    policy_path: Path | None = None,
    phase158_report_path: Path | None = None,
    repair_records_path: Path | None = None,
) -> dict[str, Any]:
    validation_errors = source_validation_errors(
        policy=policy,
        phase158_report=phase158_report,
        policy_path=policy_path,
        phase158_report_path=phase158_report_path,
        repair_records=repair_records,
    )
    repair_items, monitoring_items, repair_errors = build_repair_items(
        policy=policy,
        phase158_report=phase158_report,
        repair_records=repair_records,
    )
    validation_errors.extend(repair_errors)
    eligible_count = sum(1 for finding in object_list(phase158_report.get("accepted_findings")) if finding.get("phase159_eligible") is True)
    closed_count = sum(
        1 for item in repair_items if item.get("closure_status") == ClosureStatus.CLOSED_WITH_TARGET_HOLDOUT_PROOF.value
    )
    open_count = sum(1 for item in repair_items if item.get("closure_status") == ClosureStatus.OPEN_BLOCKED.value)
    repair_mode = choose_repair_mode(repair_items, eligible_count)
    status = RepairLoopStatus.PASSED.value if not validation_errors else RepairLoopStatus.FAILED.value
    if status == RepairLoopStatus.PASSED.value and repair_mode == RepairMode.BLOCKED_WITH_NEXT_ACTION.value:
        status = RepairLoopStatus.BLOCKED.value
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": status,
        "created_at": utc_timestamp(),
        "source_refs": {
            "policy": source_ref(policy_path, policy),
            "phase158_report": source_ref(phase158_report_path, phase158_report),
            "repair_records": source_ref(repair_records_path, repair_records or {}),
        },
        "repair_mode": repair_mode,
        "repair_items": repair_items,
        "monitoring_items": monitoring_items,
        "validation_errors": validation_errors,
        "next_phase": policy.get("next_phase"),
        "summary": {
            "phase158_finding_count": len(object_list(phase158_report.get("accepted_findings"))),
            "monitoring_only_count": len(monitoring_items),
            "phase159_eligible_count": eligible_count,
            "closed_repair_count": closed_count,
            "open_repair_count": open_count,
            "missing_repair_record_count": sum(1 for item in repair_items if item.get("closure_status") == "missing"),
            "validation_error_count": len(validation_errors),
            "repair_mode": repair_mode,
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
            "repair_mode",
            "repair_items",
            "monitoring_items",
            "validation_errors",
            "next_phase",
            "summary",
        )
    }


def validate_priority0_repair_loop_report(
    report: dict[str, Any],
    *,
    policy: dict[str, Any],
    phase158_report: dict[str, Any],
    repair_records: dict[str, Any] | None = None,
    policy_path: Path | None = None,
    phase158_report_path: Path | None = None,
    repair_records_path: Path | None = None,
) -> list[str]:
    expected = build_priority0_repair_loop_report(
        policy=policy,
        phase158_report=phase158_report,
        repair_records=repair_records,
        policy_path=policy_path,
        phase158_report_path=phase158_report_path,
        repair_records_path=repair_records_path,
    )
    if stable_view(report) != stable_view(expected):
        return ["report must match rebuilt Priority 0 repair-loop report"]
    return []


def markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Priority 0 Repair Loop",
        "",
        f"- Status: {report.get('status')}",
        f"- Repair mode: {report.get('repair_mode')}",
        f"- Phase 159 eligible findings: {summary.get('phase159_eligible_count')}",
        f"- Closed repairs: {summary.get('closed_repair_count')}",
        f"- Open repairs: {summary.get('open_repair_count')}",
        f"- Monitoring-only findings: {summary.get('monitoring_only_count')}",
        "",
        "## Repair Items",
        "",
        "| Finding | Case | Category | Closure | Target | Holdout | Mutation | Blockers |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    repair_items = object_list(report.get("repair_items"))
    if repair_items:
        for item in repair_items:
            lines.append(
                "| {finding_id} | {case_id} | {category} | {closure} | {target} | {holdout} | {mutation} | {blockers} |".format(
                    finding_id=item.get("finding_id"),
                    case_id=item.get("case_id"),
                    category=item.get("category"),
                    closure=item.get("closure_status"),
                    target=item.get("target_result_status"),
                    holdout=item.get("holdout_result_status"),
                    mutation=item.get("mutation_status"),
                    blockers=", ".join(string_list(item.get("blockers"))),
                )
            )
    else:
        lines.append("| none | none | none | none | none | none | none | none |")
    lines.extend(["", "## Monitoring Items", ""])
    monitoring_items = object_list(report.get("monitoring_items"))
    if monitoring_items:
        lines.extend(
            f"- {item.get('finding_id')}: {item.get('category')} ({item.get('owner_path')})"
            for item in monitoring_items
        )
    else:
        lines.append("- none")
    lines.extend(["", "## Validation Errors", ""])
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(f"- {error.get('id')}: {error.get('message')}" for error in errors)
    else:
        lines.append("- none")
    return "\n".join(lines).rstrip() + "\n"


def run_priority0_repair_loop(config: Priority0RepairLoopConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    phase158_report_path = resolve_path(config_root, config.phase158_report_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path) if config.markdown_output_path else None
    policy = read_json_object(policy_path)
    phase158_report = read_json_object(phase158_report_path)
    repair_records_path = resolve_path(config_root, config.repair_records_path) if config.repair_records_path else None
    if repair_records_path is None:
        inputs = dict_value(policy.get("inputs"))
        optional_path = inputs.get("optional_repair_records")
        if isinstance(optional_path, str) and optional_path.strip():
            candidate = resolve_path(config_root, optional_path)
            repair_records_path = candidate if candidate.is_file() else None
    repair_records = load_optional_json(repair_records_path)
    report = build_priority0_repair_loop_report(
        policy=policy,
        phase158_report=phase158_report,
        repair_records=repair_records,
        policy_path=policy_path,
        phase158_report_path=phase158_report_path,
        repair_records_path=repair_records_path,
    )
    validation_errors = validate_priority0_repair_loop_report(
        report,
        policy=policy,
        phase158_report=phase158_report,
        repair_records=repair_records,
        policy_path=policy_path,
        phase158_report_path=phase158_report_path,
        repair_records_path=repair_records_path,
    )
    if validation_errors:
        report["status"] = RepairLoopStatus.FAILED.value
        report["validation_errors"] = [
            *object_list(report.get("validation_errors")),
            *[
                {
                    "id": f"self_validation.{index}",
                    "source": "priority0_repair_loop",
                    "severity": "high",
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
