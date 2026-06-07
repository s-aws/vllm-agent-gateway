"""Natural-language capability gap backlog validation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_BACKLOG_PATH = Path("runtime") / "natural_language_capability_gap_backlog.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "capability-gap-backlog"
VALID_CLASSIFICATIONS = {"existing_support", "small_extension", "new_workflow", "defer"}
ACCEPTED_CLASSIFICATIONS = {"existing_support", "small_extension", "new_workflow"}
VALIDATION_TIERS = {
    "gateway_anythingllm",
    "gateway_anythingllm_fixture_mutation",
    "gateway_anythingllm_security",
    "future_phase_96",
}
ID_RE = re.compile(r"^P93-\d{3}$")
BROAD_REFACTOR_RE = re.compile(r"\b(refactor|whole subsystem|one path|single path)\b", re.IGNORECASE)
MANUAL_INJECTION_RE = re.compile(r"\b(SKILL\.md|paste.*skill|manual skill|JSON envelope|controller JSON envelope)\b", re.IGNORECASE)


class GapBacklogStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class CapabilityGapBacklogValidationConfig:
    config_root: Path
    backlog_path: Path = DEFAULT_BACKLOG_PATH
    output_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"capability-gap-backlog-{utc_timestamp()}.json"


def resolve_path(config_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else config_root / path


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object at {path}")
    return value


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def check(
    check_id: str,
    status: GapBacklogStatus,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    next_action: str = "",
) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": status.value,
        "message": message,
        "details": details or {},
        "next_action": next_action,
    }


def entry_text(entry: dict[str, Any]) -> str:
    return " ".join(str(entry.get(key, "")) for key in ("id", "prompt", "rationale", "defer_reason"))


def validate_accepted_entry(entry: dict[str, Any], prefix: str) -> list[str]:
    errors: list[str] = []
    for field in ("expected_workflow", "eval_gate", "validation_tier"):
        if not isinstance(entry.get(field), str) or not entry[field].strip():
            errors.append(f"{prefix}.{field} must be a non-empty string")
    for field in ("expected_skills", "expected_tools", "expected_artifacts", "acceptance_markers"):
        if not string_list(entry.get(field)):
            errors.append(f"{prefix}.{field} must be a non-empty string array")
    if entry.get("validation_tier") not in VALIDATION_TIERS:
        errors.append(f"{prefix}.validation_tier must be one of {sorted(VALIDATION_TIERS)}")
    if BROAD_REFACTOR_RE.search(entry_text(entry)) and entry.get("classification") != "defer":
        errors.append(f"{prefix} broad refactor wording must be classified as defer")
    return errors


def validate_deferred_entry(entry: dict[str, Any], prefix: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(entry.get("defer_reason"), str) or not entry["defer_reason"].strip():
        errors.append(f"{prefix}.defer_reason must be a non-empty string")
    if entry.get("mutation_policy") != "blocked":
        errors.append(f"{prefix}.mutation_policy must be blocked for deferred entries")
    suggested = entry.get("suggested_next_phase")
    if not isinstance(suggested, int) or suggested < 94:
        errors.append(f"{prefix}.suggested_next_phase must be an integer >= 94 for deferred entries")
    return errors


def validate_entry(entry: dict[str, Any], index: int) -> list[str]:
    prefix = f"entries[{index}]"
    errors: list[str] = []
    entry_id = entry.get("id")
    if not isinstance(entry_id, str) or not ID_RE.fullmatch(entry_id):
        errors.append(f"{prefix}.id must match P93-###")
    for field in ("prompt", "source", "classification", "rationale", "mutation_policy"):
        if not isinstance(entry.get(field), str) or not entry[field].strip():
            errors.append(f"{prefix}.{field} must be a non-empty string")
    classification = entry.get("classification")
    if classification not in VALID_CLASSIFICATIONS:
        errors.append(f"{prefix}.classification must be one of {sorted(VALID_CLASSIFICATIONS)}")
    if entry.get("requires_manual_skill_injection") is not False:
        errors.append(f"{prefix}.requires_manual_skill_injection must be false")
    if entry.get("requires_json_envelope") is not False:
        errors.append(f"{prefix}.requires_json_envelope must be false")
    if MANUAL_INJECTION_RE.search(entry_text(entry)):
        errors.append(f"{prefix} must not rely on manual skill injection or JSON-envelope prompting")
    if classification in ACCEPTED_CLASSIFICATIONS:
        errors.extend(validate_accepted_entry(entry, prefix))
    elif classification == "defer":
        errors.extend(validate_deferred_entry(entry, prefix))
    return errors


def validate_backlog(backlog: dict[str, Any], *, backlog_path: Path) -> list[dict[str, Any]]:
    errors: list[str] = []
    if backlog.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if backlog.get("kind") != "natural_language_capability_gap_backlog":
        errors.append("kind must be natural_language_capability_gap_backlog")
    if backlog.get("phase") != 93:
        errors.append("phase must be 93")
    entries = backlog.get("entries")
    if not isinstance(entries, list):
        errors.append("entries must be an array")
        entries = []
    if len(entries) < 25 or len(entries) > 50:
        errors.append("entries must contain 25 through 50 prompt families")
    entry_ids = [entry.get("id") for entry in entries if isinstance(entry, dict)]
    duplicate_ids = sorted({entry_id for entry_id in entry_ids if isinstance(entry_id, str) and entry_ids.count(entry_id) > 1})
    if duplicate_ids:
        errors.append(f"entries contain duplicate ids: {duplicate_ids}")
    classification_counts = {classification: 0 for classification in VALID_CLASSIFICATIONS}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"entries[{index}] must be an object")
            continue
        classification = entry.get("classification")
        if classification in classification_counts:
            classification_counts[classification] += 1
        errors.extend(validate_entry(entry, index))
    if classification_counts["existing_support"] < 3:
        errors.append("backlog must identify at least three existing support prompts")
    if classification_counts["small_extension"] < 5:
        errors.append("backlog must identify at least five small extensions")
    if classification_counts["new_workflow"] < 3:
        errors.append("backlog must identify at least three new workflows")
    if classification_counts["defer"] < 1:
        errors.append("backlog must include deferred out-of-scope prompts")
    return [
        check(
            "backlog.contract",
            GapBacklogStatus.PASSED if not errors else GapBacklogStatus.FAILED,
            "Capability gap backlog contract is valid."
            if not errors
            else "Capability gap backlog contract is invalid.",
            details={
                "backlog_path": str(backlog_path),
                "entry_count": len(entries),
                "classification_counts": classification_counts,
                "errors": errors,
            },
            next_action="" if not errors else "Fix runtime/natural_language_capability_gap_backlog.json before Phase 93 can close.",
        )
    ]


def validate_capability_gap_backlog(config: CapabilityGapBacklogValidationConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    backlog_path = resolve_path(config_root, config.backlog_path)
    output_path = config.output_path or default_report_path(config_root)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_gap_backlog_validation_report",
        "status": GapBacklogStatus.FAILED.value,
        "created_at": utc_timestamp(),
        "config_root": str(config_root),
        "backlog_path": str(backlog_path),
        "checks": [],
        "summary": {},
    }
    try:
        backlog = read_json_object(backlog_path)
        checks = validate_backlog(backlog, backlog_path=backlog_path)
    except Exception as exc:  # noqa: BLE001
        checks = [
            check(
                "validation.load",
                GapBacklogStatus.FAILED,
                f"Capability gap backlog validation input could not be loaded: {type(exc).__name__}: {exc}",
                next_action="Check the backlog path and JSON syntax.",
            )
        ]
    failed_ids = [item["id"] for item in checks if item.get("status") == GapBacklogStatus.FAILED.value]
    report["checks"] = checks
    report["summary"] = {
        "check_count": len(checks),
        "failed_check_ids": failed_ids,
        "backlog_validated": any(item["id"] == "backlog.contract" for item in checks),
    }
    report["status"] = GapBacklogStatus.PASSED.value if not failed_ids else GapBacklogStatus.FAILED.value
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
