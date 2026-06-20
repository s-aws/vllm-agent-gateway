"""EIG-3 synthetic sensitive-data fixture validation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_FIXTURE_PATH = Path("runtime") / "eig3_sensitive_data_fixtures.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "eig3-sensitive-data"


class EIG3SensitiveDataArchetype(str, Enum):
    PERSONAL_DATA = "personal_data"
    SECRET_LIKE = "secret_like"
    CONFIDENTIAL_BUSINESS = "confidential_business"


class EIG3FixtureCaseType(str, Enum):
    REQUIRED = "required"
    SAFE = "safe"
    NEAR_MISS = "near_miss"
    HOLDOUT = "holdout"
    NEGATIVE_CONTROL = "negative_control"
    DEFERRED = "deferred"


class EIG3HandlingDecision(str, Enum):
    ALLOW = "allow"
    MASK = "mask"
    REFUSE = "refuse"
    SUMMARIZE = "summarize"
    OMIT = "omit"


class EIG3OutputSurface(str, Enum):
    CHAT = "chat"
    JSON = "json"
    ARTIFACT = "artifact"
    AUDIT_SUMMARY = "audit_summary"
    MEMORY = "memory"


class EIG3ValidationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class EIG3Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


SENSITIVE_ARCHETYPES = {
    EIG3SensitiveDataArchetype.PERSONAL_DATA.value,
    EIG3SensitiveDataArchetype.SECRET_LIKE.value,
    EIG3SensitiveDataArchetype.CONFIDENTIAL_BUSINESS.value,
}

CASE_TYPES = {item.value for item in EIG3FixtureCaseType}
HANDLING_DECISIONS = {item.value for item in EIG3HandlingDecision}
OUTPUT_SURFACES = {item.value for item in EIG3OutputSurface}

MIN_COUNTS_BY_ARCHETYPE = {
    EIG3FixtureCaseType.REQUIRED.value: 3,
    "safe_or_near_miss": 2,
    EIG3FixtureCaseType.HOLDOUT.value: 2,
    EIG3FixtureCaseType.NEGATIVE_CONTROL.value: 2,
    EIG3FixtureCaseType.DEFERRED.value: 1,
}

PERSONAL_PATTERNS = [
    re.compile(r"(?<![:/])\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"),
    re.compile(r"\b(?:member|customer|employee)[-_ ]?id[:= ]+[A-Z]{2,6}-\d{3,}\b", re.IGNORECASE),
    re.compile(r"\b\d{3,5}\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?\s+(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln)\b"),
]

SECRET_PATTERNS = [
    re.compile(r"\bsk-synth-[A-Za-z0-9]{12,}\b"),
    re.compile(r"\bghp_synth_[A-Za-z0-9]{12,}\b"),
    re.compile(r"\bBearer\s+eig3_[A-Za-z0-9._-]{12,}\b"),
    re.compile(r"-----BEGIN SYNTHETIC PRIVATE KEY-----"),
    re.compile(r"\bpassword\s*[:=]\s*[^,\s]{8,}", re.IGNORECASE),
    re.compile(r"\b(?:postgres|mysql)://[^:\s]+:[^@\s]+@[^/\s]+/", re.IGNORECASE),
]

CONFIDENTIAL_BUSINESS_TERMS = {
    "confidential",
    "contract",
    "legal review",
    "procurement",
    "budget ceiling",
    "vendor pricing",
    "account record",
    "internal incident",
    "launch decision",
    "signed dpa",
    "financial",
}

UNSAFE_REQUEST_TERMS = {
    "print",
    "list all",
    "reveal",
    "extract",
    "decode",
    "reconstruct",
    "store",
    "save",
    "reverse",
    "base64",
    "raw",
    "infer",
    "fill in",
}


@dataclass(frozen=True)
class EIG3SensitiveDataConfig:
    config_root: Path
    fixture_path: Path = DEFAULT_FIXTURE_PATH
    output_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"eig3-sensitive-data-{utc_timestamp()}.json"


def resolve_path(config_root: Path, raw_path: Path | str) -> Path:
    path = raw_path if isinstance(raw_path, Path) else Path(raw_path)
    return path if path.is_absolute() else config_root / path


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object at {path}")
    return value


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def detect_sensitive_classes(text: str) -> list[str]:
    lowered = text.lower()
    detected: set[str] = set()
    if any(pattern.search(text) for pattern in PERSONAL_PATTERNS):
        detected.add(EIG3SensitiveDataArchetype.PERSONAL_DATA.value)
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        detected.add(EIG3SensitiveDataArchetype.SECRET_LIKE.value)
    if any(term in lowered for term in CONFIDENTIAL_BUSINESS_TERMS):
        detected.add(EIG3SensitiveDataArchetype.CONFIDENTIAL_BUSINESS.value)
    return sorted(detected)


def detect_unsafe_request(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in UNSAFE_REQUEST_TERMS)


def validation_error(error_id: str, message: str, *, fixture_id: str | None = None) -> dict[str, str]:
    value = {"id": error_id, "message": message}
    if fixture_id:
        value["fixture_id"] = fixture_id
    return value


def validate_fixture_shape(fixture: Any) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if not isinstance(fixture, dict):
        return [validation_error("fixture.shape", "fixture must be a JSON object")]
    fixture_id = str(fixture.get("id") or "unknown")
    required = {
        "id",
        "case_type",
        "archetype",
        "synthetic_only",
        "text",
        "expected_sensitive_classes",
        "expected_handling_decision",
        "surface_decisions",
        "memory_behavior",
        "risk_label",
        "milestones",
        "release_blocking_severity",
    }
    missing = sorted(required - set(fixture))
    if missing:
        errors.append(validation_error("fixture.missing_fields", f"fixture is missing fields: {', '.join(missing)}", fixture_id=fixture_id))
        return errors
    if not isinstance(fixture["id"], str) or not fixture["id"].strip():
        errors.append(validation_error("fixture.id", "fixture id must be a non-empty string", fixture_id=fixture_id))
    if fixture["case_type"] not in CASE_TYPES:
        errors.append(validation_error("fixture.case_type", f"unsupported case_type: {fixture['case_type']!r}", fixture_id=fixture_id))
    if fixture["archetype"] not in SENSITIVE_ARCHETYPES:
        errors.append(validation_error("fixture.archetype", f"unsupported archetype: {fixture['archetype']!r}", fixture_id=fixture_id))
    if fixture["synthetic_only"] is not True:
        errors.append(validation_error("fixture.synthetic_only", "fixture must be marked synthetic_only=true", fixture_id=fixture_id))
    if not isinstance(fixture["text"], str):
        errors.append(validation_error("fixture.text", "fixture text must be a string", fixture_id=fixture_id))
    if any(item not in SENSITIVE_ARCHETYPES for item in string_list(fixture["expected_sensitive_classes"])):
        errors.append(validation_error("fixture.expected_sensitive_classes", "expected classes must be supported sensitive-data archetypes", fixture_id=fixture_id))
    if fixture["expected_handling_decision"] not in HANDLING_DECISIONS:
        errors.append(validation_error("fixture.expected_handling_decision", "unsupported handling decision", fixture_id=fixture_id))
    surfaces = fixture["surface_decisions"]
    if not isinstance(surfaces, dict):
        errors.append(validation_error("fixture.surface_decisions", "surface_decisions must be an object", fixture_id=fixture_id))
    else:
        missing_surfaces = sorted(OUTPUT_SURFACES - set(surfaces))
        if missing_surfaces:
            errors.append(validation_error("fixture.surface_decisions", f"missing output surfaces: {', '.join(missing_surfaces)}", fixture_id=fixture_id))
        for surface, decision in surfaces.items():
            if surface not in OUTPUT_SURFACES:
                errors.append(validation_error("fixture.surface_decisions", f"unsupported output surface: {surface}", fixture_id=fixture_id))
            if decision not in HANDLING_DECISIONS:
                errors.append(validation_error("fixture.surface_decisions", f"unsupported decision for {surface}: {decision!r}", fixture_id=fixture_id))
    if not isinstance(fixture["memory_behavior"], str) or not fixture["memory_behavior"].strip():
        errors.append(validation_error("fixture.memory_behavior", "memory_behavior must be a non-empty string", fixture_id=fixture_id))
    if not string_list(fixture["milestones"]):
        errors.append(validation_error("fixture.milestones", "milestones must be a non-empty string array", fixture_id=fixture_id))
    if fixture["release_blocking_severity"] not in {item.value for item in EIG3Severity}:
        errors.append(validation_error("fixture.release_blocking_severity", "unsupported release-blocking severity", fixture_id=fixture_id))
    if fixture["case_type"] == EIG3FixtureCaseType.DEFERRED.value and not isinstance(fixture.get("deferred_reason"), str):
        errors.append(validation_error("fixture.deferred_reason", "deferred fixtures must include deferred_reason", fixture_id=fixture_id))
    return errors


def validate_surface_policy(fixture: dict[str, Any], detected_classes: list[str]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    fixture_id = fixture["id"]
    surfaces = fixture["surface_decisions"]
    decision = fixture["expected_handling_decision"]
    case_type = fixture["case_type"]
    if case_type == EIG3FixtureCaseType.DEFERRED.value:
        return errors
    if case_type == EIG3FixtureCaseType.NEGATIVE_CONTROL.value and decision != EIG3HandlingDecision.REFUSE.value:
        errors.append(validation_error("fixture.negative_control_decision", "negative controls must expect refusal", fixture_id=fixture_id))
    if detect_unsafe_request(fixture["text"]) and detected_classes and decision == EIG3HandlingDecision.ALLOW.value:
        errors.append(validation_error("fixture.unsafe_request_decision", "unsafe sensitive-data requests must not expect allow", fixture_id=fixture_id))
    if EIG3SensitiveDataArchetype.SECRET_LIKE.value in detected_classes:
        for surface in (
            EIG3OutputSurface.CHAT.value,
            EIG3OutputSurface.JSON.value,
            EIG3OutputSurface.ARTIFACT.value,
            EIG3OutputSurface.AUDIT_SUMMARY.value,
            EIG3OutputSurface.MEMORY.value,
        ):
            if surfaces.get(surface) == EIG3HandlingDecision.ALLOW.value:
                errors.append(validation_error("fixture.secret_surface_allow", f"secret-like fixture allows surface {surface}", fixture_id=fixture_id))
    if detected_classes and surfaces.get(EIG3OutputSurface.MEMORY.value) == EIG3HandlingDecision.ALLOW.value:
        errors.append(validation_error("fixture.memory_allow", "sensitive fixtures must not allow raw durable memory", fixture_id=fixture_id))
    return errors


def validate_fixture_detection(fixture: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    text = fixture["text"]
    detected_classes = detect_sensitive_classes(text)
    expected_classes = sorted(string_list(fixture["expected_sensitive_classes"]))
    if fixture["case_type"] != EIG3FixtureCaseType.DEFERRED.value:
        if detected_classes != expected_classes:
            errors.append(
                validation_error(
                    "fixture.detected_classes",
                    f"detected classes {detected_classes} did not match expected classes {expected_classes}",
                    fixture_id=fixture["id"],
                )
            )
    errors.extend(validate_surface_policy(fixture, detected_classes))
    result = {
        "id": fixture["id"],
        "case_type": fixture["case_type"],
        "archetype": fixture["archetype"],
        "text_sha256": sha256_text(text),
        "expected_sensitive_classes": expected_classes,
        "detected_sensitive_classes": detected_classes,
        "expected_handling_decision": fixture["expected_handling_decision"],
        "release_blocking_severity": fixture["release_blocking_severity"],
        "status": EIG3ValidationStatus.PASSED.value if not errors else EIG3ValidationStatus.FAILED.value,
        "error_ids": [item["id"] for item in errors],
    }
    return result, errors


def validate_minimum_counts(fixtures: list[dict[str, Any]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    by_arch: dict[str, list[dict[str, Any]]] = {item: [] for item in sorted(SENSITIVE_ARCHETYPES)}
    for fixture in fixtures:
        archetype = fixture.get("archetype")
        if archetype in by_arch:
            by_arch[archetype].append(fixture)
    for archetype, items in by_arch.items():
        counts = {item.value: 0 for item in EIG3FixtureCaseType}
        for fixture in items:
            case_type = fixture.get("case_type")
            if case_type in counts:
                counts[case_type] += 1
        safe_near_miss_count = counts[EIG3FixtureCaseType.SAFE.value] + counts[EIG3FixtureCaseType.NEAR_MISS.value]
        if counts[EIG3FixtureCaseType.REQUIRED.value] < MIN_COUNTS_BY_ARCHETYPE[EIG3FixtureCaseType.REQUIRED.value]:
            errors.append(validation_error("counts.required", f"{archetype} must have at least 3 required fixtures"))
        if safe_near_miss_count < MIN_COUNTS_BY_ARCHETYPE["safe_or_near_miss"]:
            errors.append(validation_error("counts.safe_or_near_miss", f"{archetype} must have at least 2 safe or near-miss fixtures"))
        if counts[EIG3FixtureCaseType.HOLDOUT.value] < MIN_COUNTS_BY_ARCHETYPE[EIG3FixtureCaseType.HOLDOUT.value]:
            errors.append(validation_error("counts.holdout", f"{archetype} must have at least 2 holdout fixtures"))
        if counts[EIG3FixtureCaseType.NEGATIVE_CONTROL.value] < MIN_COUNTS_BY_ARCHETYPE[EIG3FixtureCaseType.NEGATIVE_CONTROL.value]:
            errors.append(validation_error("counts.negative_control", f"{archetype} must have at least 2 negative-control fixtures"))
        if counts[EIG3FixtureCaseType.DEFERRED.value] < MIN_COUNTS_BY_ARCHETYPE[EIG3FixtureCaseType.DEFERRED.value]:
            errors.append(validation_error("counts.deferred", f"{archetype} must have at least 1 deferred fixture"))
    return errors


def validate_pack_shape(pack: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if pack.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("pack.schema_version", f"schema_version must be {SCHEMA_VERSION}"))
    if pack.get("kind") != "eig3_sensitive_data_fixture_pack":
        errors.append(validation_error("pack.kind", "kind must be eig3_sensitive_data_fixture_pack"))
    if pack.get("phase") != 298:
        errors.append(validation_error("pack.phase", "phase must be 298"))
    if pack.get("synthetic_only") is not True:
        errors.append(validation_error("pack.synthetic_only", "fixture pack must be synthetic_only=true"))
    if not isinstance(pack.get("source_matrix"), str) or not pack["source_matrix"].strip():
        errors.append(validation_error("pack.source_matrix", "source_matrix must be a non-empty string"))
    fixtures = pack.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        errors.append(validation_error("pack.fixtures", "fixtures must be a non-empty list"))
    return errors


def run_eig3_sensitive_data_validation(config: EIG3SensitiveDataConfig) -> dict[str, Any]:
    fixture_path = resolve_path(config.config_root, config.fixture_path)
    output_path = config.output_path or default_report_path(config.config_root)
    errors: list[dict[str, str]] = []
    fixture_results: list[dict[str, Any]] = []
    try:
        pack = read_json_object(fixture_path)
    except Exception as exc:  # noqa: BLE001
        pack = {}
        errors.append(validation_error("pack.read", f"could not read fixture pack: {type(exc).__name__}: {exc}"))
    errors.extend(validate_pack_shape(pack))
    raw_fixtures = pack.get("fixtures") if isinstance(pack.get("fixtures"), list) else []
    shaped_fixtures: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_fixture in raw_fixtures:
        shape_errors = validate_fixture_shape(raw_fixture)
        errors.extend(shape_errors)
        if shape_errors:
            continue
        fixture = raw_fixture
        if fixture["id"] in seen_ids:
            errors.append(validation_error("fixture.duplicate_id", f"duplicate fixture id: {fixture['id']}", fixture_id=fixture["id"]))
            continue
        seen_ids.add(fixture["id"])
        shaped_fixtures.append(fixture)
        result, fixture_errors = validate_fixture_detection(fixture)
        fixture_results.append(result)
        errors.extend(fixture_errors)
    errors.extend(validate_minimum_counts(shaped_fixtures))
    status = EIG3ValidationStatus.PASSED.value if not errors else EIG3ValidationStatus.FAILED.value
    summary = {
        "status": status,
        "fixture_count": len(shaped_fixtures),
        "archetype_count": len({item["archetype"] for item in shaped_fixtures}),
        "failed_fixture_count": sum(1 for item in fixture_results if item["status"] == EIG3ValidationStatus.FAILED.value),
        "validation_error_count": len(errors),
        "phase299_ready": status == EIG3ValidationStatus.PASSED.value,
        "raw_fixture_text_retained_in_report": False,
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "eig3_sensitive_data_validation_report",
        "phase": 298,
        "status": status,
        "fixture_pack_path": str(fixture_path),
        "summary": summary,
        "fixture_results": fixture_results,
        "validation_errors": errors,
        "report_path": str(output_path),
    }
    write_json(output_path, report)
    return report
