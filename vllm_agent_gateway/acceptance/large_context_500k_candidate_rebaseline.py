"""Phase 270 500k candidate objective rebaseline gate."""

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
EXPECTED_POLICY_KIND = "large_context_500k_candidate_rebaseline_policy"
EXPECTED_REPORT_KIND = "large_context_500k_candidate_rebaseline_report"
EXPECTED_PHASE = 270
EXPECTED_BACKLOG_ID = "P0-M15-270"
EXPECTED_MILESTONE_IDS = {"M6", "M8", "M14", "M15", "M16"}
STABLE_ESTIMATED_PROJECT_TOKENS = 384_000
CANDIDATE_ESTIMATED_PROJECT_TOKENS = 500_000
DEFAULT_POLICY_PATH = Path("runtime") / "large_context_500k_candidate_rebaseline_policy.json"
DEFAULT_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase270"
    / "phase270-large-context-500k-candidate-rebaseline-report.json"
)
DEFAULT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase270"
    / "phase270-large-context-500k-candidate-rebaseline-report.md"
)
PHASE_HEADING_RE = re.compile(
    r"^### Approved Phase (?P<phase>\d+):.*?(?P<body>.*?)(?=^### Approved Phase |\Z)",
    re.MULTILINE | re.DOTALL,
)


class LargeContext500kCandidateRebaselineStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class LargeContext500kCandidateRebaselineConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH


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


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def int_list(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, int)]


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def validation_error(error_id: str, message: str, *, source: str = "policy", severity: str = "high") -> dict[str, str]:
    return {"id": error_id, "message": message, "source": source, "severity": severity}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "phase must be 270"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be M6, M8, M14, M15, and M16"))
    if policy.get("stable_estimated_project_tokens") != STABLE_ESTIMATED_PROJECT_TOKENS:
        errors.append(validation_error("policy.stable_estimated_project_tokens", "stable target must remain 384000"))
    if policy.get("candidate_estimated_project_tokens") != CANDIDATE_ESTIMATED_PROJECT_TOKENS:
        errors.append(validation_error("policy.candidate_estimated_project_tokens", "candidate target must be 500000"))
    if len(string_list(policy.get("required_docs"))) < 5:
        errors.append(validation_error("policy.required_docs", "required_docs must include durable objective docs"))
    if not dict_value(policy.get("required_doc_markers")):
        errors.append(validation_error("policy.required_doc_markers", "required_doc_markers is required"))
    if len(string_list(policy.get("required_boundaries"))) < 3:
        errors.append(validation_error("policy.required_boundaries", "scope boundaries are required"))
    followups = int_list(policy.get("approved_followup_phases"))
    if followups != [271, 272, 273, 274, 275, 276, 277]:
        errors.append(validation_error("policy.approved_followup_phases", "approved follow-up phases must be 271 through 277"))
    if policy.get("acceptance_marker") != "PHASE270 LARGE CONTEXT 500K CANDIDATE REBASELINE PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 270"))
    return errors


def docs_checks(config_root: Path, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    results: list[dict[str, Any]] = []
    required_markers = dict_value(policy.get("required_doc_markers"))
    forbidden_markers = string_list(policy.get("forbidden_stable_claim_markers"))
    for raw_path in string_list(policy.get("required_docs")):
        path = resolve_path(config_root, raw_path)
        result: dict[str, Any] = {
            "path": raw_path,
            "exists": path.is_file(),
            "sha256": None,
            "missing_markers": [],
            "forbidden_markers": [],
        }
        if not path.is_file():
            errors.append(validation_error(f"docs.{raw_path}.missing", "required doc is missing", source="docs"))
            results.append(result)
            continue
        text = path.read_text(encoding="utf-8")
        result["sha256"] = sha256_file(path)
        missing = [marker for marker in string_list(required_markers.get(raw_path)) if marker not in text]
        result["missing_markers"] = missing
        for marker in missing:
            errors.append(validation_error(f"docs.{raw_path}.marker", f"required marker missing: {marker}", source="docs"))
        forbidden = [marker for marker in forbidden_markers if marker in text]
        result["forbidden_markers"] = forbidden
        for marker in forbidden:
            errors.append(validation_error(f"docs.{raw_path}.forbidden", f"forbidden stable-claim marker found: {marker}", source="docs"))
        results.append(result)
    return results, errors


def roadmap_phase_statuses(config_root: Path, policy: dict[str, Any]) -> tuple[dict[str, str | None], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    roadmap_path = config_root / "docs" / "ACTIONABLE_WORKFLOW_ROADMAP.md"
    if not roadmap_path.is_file():
        return {}, [validation_error("roadmap.missing", "docs/ACTIONABLE_WORKFLOW_ROADMAP.md is missing", source="roadmap")]
    text = roadmap_path.read_text(encoding="utf-8")
    phases = {match.group("phase"): match.group("body") for match in PHASE_HEADING_RE.finditer(text)}
    statuses: dict[str, str | None] = {}
    for phase, expected_status in dict_value(policy.get("required_phase_statuses")).items():
        body = phases.get(str(phase))
        status = None
        if body:
            status_match = re.search(r"^Status:\s*(?P<status>.+?)\s*$", body, flags=re.MULTILINE)
            status = status_match.group("status") if status_match else None
        statuses[str(phase)] = status
        if status != expected_status:
            errors.append(
                validation_error(
                    f"roadmap.phase{phase}.status",
                    f"Phase {phase} must be {expected_status!r}, got {status!r}",
                    source="roadmap",
                )
            )
    return statuses, errors


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Large-Context 500k Candidate Rebaseline",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Error count: `{summary.get('error_count')}`",
        f"- Stable estimated project tokens: `{summary.get('stable_estimated_project_tokens')}`",
        f"- Candidate estimated project tokens: `{summary.get('candidate_estimated_project_tokens')}`",
        "",
        "## Errors",
    ]
    errors = object_list(report.get("errors"))
    if errors:
        lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in errors)
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def validate_large_context_500k_candidate_rebaseline(config: LargeContext500kCandidateRebaselineConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path)
    policy = read_json_object(policy_path)

    policy_errors = validate_policy(policy)
    docs, docs_errors = docs_checks(config_root, policy)
    phase_statuses, roadmap_errors = roadmap_phase_statuses(config_root, policy)
    errors = policy_errors + docs_errors + roadmap_errors
    status = (
        LargeContext500kCandidateRebaselineStatus.PASSED.value
        if not errors
        else LargeContext500kCandidateRebaselineStatus.FAILED.value
    )
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
        "docs": docs,
        "roadmap_phase_statuses": phase_statuses,
        "boundaries": string_list(policy.get("required_boundaries")),
        "approved_followup_phases": int_list(policy.get("approved_followup_phases")),
        "errors": errors,
        "summary": {
            "error_count": len(errors),
            "stable_estimated_project_tokens": policy.get("stable_estimated_project_tokens"),
            "candidate_estimated_project_tokens": policy.get("candidate_estimated_project_tokens"),
            "doc_count": len(docs),
            "phase270_ready": not errors,
        },
    }
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown(report))
    return report
