"""EIG-3 governed memory lifecycle validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.eig3_sensitive_data import (
    DEFAULT_FIXTURE_PATH as DEFAULT_SENSITIVE_FIXTURE_PATH,
    EIG3ValidationStatus,
    detect_sensitive_classes,
    read_json_object,
    sha256_text,
    string_list,
    validation_error,
    write_json,
)


SCHEMA_VERSION = 1
DEFAULT_MEMORY_FIXTURE_PATH = Path("runtime") / "eig3_memory_lifecycle_fixtures.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "eig3-memory-lifecycle"


class EIG3MemoryDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class EIG3MemoryScope(str, Enum):
    SESSION = "session"
    ACTOR = "actor"
    PROJECT = "project"


class EIG3MemoryStatus(str, Enum):
    ACTIVE = "active"
    DELETED = "deleted"


@dataclass(frozen=True)
class EIG3MemoryLifecycleConfig:
    config_root: Path
    memory_fixture_path: Path = DEFAULT_MEMORY_FIXTURE_PATH
    sensitive_fixture_path: Path = DEFAULT_SENSITIVE_FIXTURE_PATH
    output_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"eig3-memory-lifecycle-{utc_timestamp()}.json"


def resolve_path(config_root: Path, raw_path: Path | str) -> Path:
    path = raw_path if isinstance(raw_path, Path) else Path(raw_path)
    return path if path.is_absolute() else config_root / path


def parse_utc_timestamp(value: Any, label: str, *, allow_null: bool = False) -> tuple[datetime | None, list[dict[str, str]]]:
    if value is None and allow_null:
        return None, []
    if not isinstance(value, str) or not value.strip():
        return None, [validation_error(label, f"{label} must be an ISO timestamp")]
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None, [validation_error(label, f"{label} must be an ISO timestamp")]
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc), []


def sensitive_fixtures_by_id(config_root: Path, sensitive_fixture_path: Path) -> dict[str, dict[str, Any]]:
    path = resolve_path(config_root, sensitive_fixture_path)
    pack = read_json_object(path)
    fixtures = pack.get("fixtures") if isinstance(pack.get("fixtures"), list) else []
    return {str(item.get("id")): item for item in fixtures if isinstance(item, dict) and isinstance(item.get("id"), str)}


def validate_pack_shape(pack: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if pack.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("pack.schema_version", f"schema_version must be {SCHEMA_VERSION}"))
    if pack.get("kind") != "eig3_memory_lifecycle_fixture_pack":
        errors.append(validation_error("pack.kind", "kind must be eig3_memory_lifecycle_fixture_pack"))
    if pack.get("phase") != 300:
        errors.append(validation_error("pack.phase", "phase must be 300"))
    if pack.get("synthetic_only") is not True:
        errors.append(validation_error("pack.synthetic_only", "memory fixture pack must be synthetic_only=true"))
    if not isinstance(pack.get("source_fixture_pack"), str) or not pack["source_fixture_pack"].strip():
        errors.append(validation_error("pack.source_fixture_pack", "source_fixture_pack must be a non-empty string"))
    if not isinstance(pack.get("evaluation_context"), dict):
        errors.append(validation_error("pack.evaluation_context", "evaluation_context must be an object"))
    if not isinstance(pack.get("records"), list) or not pack["records"]:
        errors.append(validation_error("pack.records", "records must be a non-empty list"))
    return errors


def validate_record_shape(record: Any) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if not isinstance(record, dict):
        return [validation_error("record.shape", "record must be a JSON object")]
    record_id = str(record.get("id") or "unknown")
    required = {
        "id",
        "case_type",
        "synthetic_only",
        "memory_scope",
        "purpose",
        "source_fixture_id",
        "source_hash_at_write",
        "source_hash_current",
        "actor_id",
        "session_id",
        "status",
        "retention_expires_at",
        "deleted_at",
        "user_visible",
        "inspectable",
        "content",
        "expected_decision",
        "expected_reason",
        "expected_influence_allowed",
        "milestones",
    }
    missing = sorted(required - set(record))
    if missing:
        errors.append(validation_error("record.missing_fields", f"record is missing fields: {', '.join(missing)}", fixture_id=record_id))
        return errors
    if not isinstance(record["id"], str) or not record["id"].strip():
        errors.append(validation_error("record.id", "record id must be a non-empty string", fixture_id=record_id))
    if record["synthetic_only"] is not True:
        errors.append(validation_error("record.synthetic_only", "record must be synthetic_only=true", fixture_id=record_id))
    if record["memory_scope"] not in {item.value for item in EIG3MemoryScope}:
        errors.append(validation_error("record.memory_scope", "unsupported memory scope", fixture_id=record_id))
    if record["status"] not in {item.value for item in EIG3MemoryStatus}:
        errors.append(validation_error("record.status", "unsupported memory status", fixture_id=record_id))
    if record["expected_decision"] not in {item.value for item in EIG3MemoryDecision}:
        errors.append(validation_error("record.expected_decision", "unsupported expected decision", fixture_id=record_id))
    for field in ("purpose", "source_fixture_id", "source_hash_at_write", "source_hash_current", "actor_id", "session_id", "content", "expected_reason"):
        if not isinstance(record[field], str) or not record[field].strip():
            errors.append(validation_error(f"record.{field}", f"{field} must be a non-empty string", fixture_id=record_id))
    if not isinstance(record["user_visible"], bool):
        errors.append(validation_error("record.user_visible", "user_visible must be boolean", fixture_id=record_id))
    if not isinstance(record["inspectable"], bool):
        errors.append(validation_error("record.inspectable", "inspectable must be boolean", fixture_id=record_id))
    if not isinstance(record["expected_influence_allowed"], bool):
        errors.append(validation_error("record.expected_influence_allowed", "expected_influence_allowed must be boolean", fixture_id=record_id))
    if not string_list(record["milestones"]):
        errors.append(validation_error("record.milestones", "milestones must be a non-empty string array", fixture_id=record_id))
    return errors


def lifecycle_decision(record: dict[str, Any], context: dict[str, Any], evaluation_time: datetime) -> tuple[str, str]:
    if record["status"] == EIG3MemoryStatus.DELETED.value or record.get("deleted_at") is not None:
        return EIG3MemoryDecision.DENY.value, "deleted_memory"
    expires_at, errors = parse_utc_timestamp(record.get("retention_expires_at"), "record.retention_expires_at")
    if errors or expires_at is None or expires_at <= evaluation_time:
        return EIG3MemoryDecision.DENY.value, "expired_memory"
    if record["source_hash_at_write"] != record["source_hash_current"]:
        return EIG3MemoryDecision.DENY.value, "stale_source"
    if record["user_visible"] is not True or record["inspectable"] is not True:
        return EIG3MemoryDecision.DENY.value, "hidden_memory"
    if record["actor_id"] != context.get("actor_id"):
        return EIG3MemoryDecision.DENY.value, "wrong_actor"
    if record["memory_scope"] == EIG3MemoryScope.SESSION.value and record["session_id"] != context.get("session_id"):
        return EIG3MemoryDecision.DENY.value, "wrong_session"
    if detect_sensitive_classes(record["content"]):
        return EIG3MemoryDecision.DENY.value, "raw_sensitive_memory"
    return EIG3MemoryDecision.ALLOW.value, "active_inspectable_scoped_memory"


def validate_record(
    record: dict[str, Any],
    *,
    context: dict[str, Any],
    evaluation_time: datetime,
    source_fixtures: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    record_id = record["id"]
    source_fixture = source_fixtures.get(record["source_fixture_id"])
    if source_fixture is None:
        errors.append(validation_error("record.source_fixture_id", "source fixture id is unknown", fixture_id=record_id))
    decision, reason = lifecycle_decision(record, context, evaluation_time)
    if decision != record["expected_decision"]:
        errors.append(validation_error("record.expected_decision", f"expected {record['expected_decision']} but got {decision}", fixture_id=record_id))
    if reason != record["expected_reason"]:
        errors.append(validation_error("record.expected_reason", f"expected reason {record['expected_reason']} but got {reason}", fixture_id=record_id))
    if (decision == EIG3MemoryDecision.ALLOW.value) != record["expected_influence_allowed"]:
        errors.append(validation_error("record.expected_influence_allowed", "expected influence flag does not match decision", fixture_id=record_id))
    if decision == EIG3MemoryDecision.ALLOW.value and detect_sensitive_classes(record["content"]):
        errors.append(validation_error("record.raw_sensitive_memory", "allowed memory must not contain raw sensitive classes", fixture_id=record_id))
    retention, timestamp_errors = parse_utc_timestamp(record.get("retention_expires_at"), "record.retention_expires_at")
    errors.extend({**item, "fixture_id": record_id} for item in timestamp_errors)
    deleted_at, deleted_errors = parse_utc_timestamp(record.get("deleted_at"), "record.deleted_at", allow_null=True)
    errors.extend({**item, "fixture_id": record_id} for item in deleted_errors)
    result = {
        "id": record_id,
        "case_type": record["case_type"],
        "memory_scope": record["memory_scope"],
        "source_fixture_id": record["source_fixture_id"],
        "content_sha256": sha256_text(record["content"]),
        "decision": decision,
        "reason": reason,
        "expected_influence_allowed": record["expected_influence_allowed"],
        "user_visible": record["user_visible"],
        "inspectable": record["inspectable"],
        "retention_expires_at": retention.isoformat().replace("+00:00", "Z") if retention else None,
        "deleted_at": deleted_at.isoformat().replace("+00:00", "Z") if deleted_at else None,
        "status": EIG3ValidationStatus.PASSED.value if not errors else EIG3ValidationStatus.FAILED.value,
        "error_ids": [item["id"] for item in errors],
    }
    return result, errors


def validate_required_case_coverage(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    expected_reasons = {
        "active_inspectable_scoped_memory",
        "deleted_memory",
        "expired_memory",
        "stale_source",
        "hidden_memory",
        "wrong_actor",
        "wrong_session",
        "raw_sensitive_memory",
    }
    observed_reasons = {str(item.get("expected_reason")) for item in records}
    missing = sorted(expected_reasons - observed_reasons)
    if missing:
        errors.append(validation_error("coverage.expected_reasons", f"missing memory lifecycle cases: {', '.join(missing)}"))
    return errors


def run_eig3_memory_lifecycle_validation(config: EIG3MemoryLifecycleConfig) -> dict[str, Any]:
    memory_fixture_path = resolve_path(config.config_root, config.memory_fixture_path)
    output_path = config.output_path or default_report_path(config.config_root)
    errors: list[dict[str, str]] = []
    record_results: list[dict[str, Any]] = []
    try:
        pack = read_json_object(memory_fixture_path)
    except Exception as exc:  # noqa: BLE001
        pack = {}
        errors.append(validation_error("pack.read", f"could not read memory fixture pack: {type(exc).__name__}: {exc}"))
    errors.extend(validate_pack_shape(pack))
    context = pack.get("evaluation_context") if isinstance(pack.get("evaluation_context"), dict) else {}
    evaluation_time, time_errors = parse_utc_timestamp(context.get("timestamp"), "evaluation_context.timestamp")
    errors.extend(time_errors)
    if evaluation_time is None:
        evaluation_time = datetime.now(timezone.utc)
    sensitive_fixture_path = Path(str(pack.get("source_fixture_pack") or config.sensitive_fixture_path))
    try:
        source_fixtures = sensitive_fixtures_by_id(config.config_root, sensitive_fixture_path)
    except Exception as exc:  # noqa: BLE001
        source_fixtures = {}
        errors.append(validation_error("source_fixtures.read", f"could not read source fixture pack: {type(exc).__name__}: {exc}"))
    raw_records = pack.get("records") if isinstance(pack.get("records"), list) else []
    shaped_records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_record in raw_records:
        shape_errors = validate_record_shape(raw_record)
        errors.extend(shape_errors)
        if shape_errors:
            continue
        record = raw_record
        if record["id"] in seen_ids:
            errors.append(validation_error("record.duplicate_id", f"duplicate memory record id: {record['id']}", fixture_id=record["id"]))
            continue
        seen_ids.add(record["id"])
        shaped_records.append(record)
        result, record_errors = validate_record(record, context=context, evaluation_time=evaluation_time, source_fixtures=source_fixtures)
        record_results.append(result)
        errors.extend(record_errors)
    errors.extend(validate_required_case_coverage(shaped_records))
    status = EIG3ValidationStatus.PASSED.value if not errors else EIG3ValidationStatus.FAILED.value
    summary = {
        "status": status,
        "record_count": len(shaped_records),
        "allowed_record_count": sum(1 for item in record_results if item.get("decision") == EIG3MemoryDecision.ALLOW.value),
        "denied_record_count": sum(1 for item in record_results if item.get("decision") == EIG3MemoryDecision.DENY.value),
        "failed_record_count": sum(1 for item in record_results if item.get("status") == EIG3ValidationStatus.FAILED.value),
        "validation_error_count": len(errors),
        "phase301_ready": status == EIG3ValidationStatus.PASSED.value,
        "raw_memory_content_retained_in_report": False,
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "eig3_memory_lifecycle_validation_report",
        "phase": 300,
        "status": status,
        "memory_fixture_path": str(memory_fixture_path),
        "summary": summary,
        "record_results": record_results,
        "validation_errors": errors,
        "report_path": str(output_path),
    }
    write_json(output_path, report)
    return report
