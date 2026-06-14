"""Phase 244 V1 release-candidate decision gate."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "v1_release_candidate_decision_gate_policy"
EXPECTED_REPORT_KIND = "v1_release_candidate_decision_gate_report"
EXPECTED_PHASE = 244
EXPECTED_BACKLOG_ID = "P0-M14-244"
EXPECTED_MILESTONE_IDS = {"M1", "M14"}
DEFAULT_POLICY_PATH = Path("runtime") / "v1_release_candidate_decision_gate_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "v1-release-candidate-decision-gate" / "phase244" / "phase244-v1-release-candidate-decision-gate-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "v1-release-candidate-decision-gate" / "phase244" / "phase244-v1-release-candidate-decision-gate-report.md"
PHASE_HEADING_RE = re.compile(
    r"^### Approved Phase (?P<phase>\d+):.*?(?P<body>.*?)(?=^### Approved Phase |\Z)",
    re.MULTILINE | re.DOTALL,
)


class ReleaseCandidateDecision(str, Enum):
    SHIP = "ship"
    HOLD = "hold"
    REPAIR_REQUIRED = "repair_required"


@dataclass(frozen=True)
class V1ReleaseCandidateDecisionGateConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    require_artifacts: bool = True
    run_live_health: bool = True
    health_timeout_seconds: int = 10


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


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def validation_error(error_id: str, message: str, *, severity: str = "high", source: str = "policy") -> dict[str, str]:
    return {"id": error_id, "message": message, "severity": severity, "source": source}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "phase must be 244"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be exactly M1 and M14"))
    if set(string_list(policy.get("allowed_decisions"))) != {item.value for item in ReleaseCandidateDecision}:
        errors.append(validation_error("policy.allowed_decisions", "allowed_decisions must be ship, hold, and repair_required"))
    phase_range = dict_value(policy.get("required_phase_range"))
    if phase_range.get("start") != 232 or phase_range.get("end") != 243:
        errors.append(validation_error("policy.required_phase_range", "required phase range must be 232-243"))
    if not object_list(policy.get("required_machine_reports")):
        errors.append(validation_error("policy.required_machine_reports", "at least one machine report is required"))
    for item in object_list(policy.get("required_machine_reports")):
        report_id = str(item.get("id") or "unknown")
        for key in ("id", "path", "expected_kind", "expected_status"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                errors.append(validation_error(f"policy.required_machine_reports.{report_id}.{key}", f"{key} is required"))
    if len(object_list(policy.get("required_runtime_health"))) < 4:
        errors.append(validation_error("policy.required_runtime_health", "runtime health probes are required"))
    for item in object_list(policy.get("required_runtime_health")):
        probe_id = str(item.get("id") or "unknown")
        if not isinstance(item.get("url"), str) or not item["url"].startswith("http://127.0.0.1:"):
            errors.append(validation_error(f"policy.required_runtime_health.{probe_id}.url", "localhost URL is required"))
        if item.get("required") is not True:
            errors.append(validation_error(f"policy.required_runtime_health.{probe_id}.required", "probe must be required"))
    if not string_list(policy.get("required_docs")):
        errors.append(validation_error("policy.required_docs", "required docs are required"))
    if not string_list(policy.get("known_limit_markers")):
        errors.append(validation_error("policy.known_limit_markers", "known limit markers are required"))
    rules = dict_value(policy.get("decision_rules"))
    for key in ("ship_only_when_no_blockers", "hold_on_runtime_health_failure", "repair_on_missing_required_phase_or_artifact"):
        if rules.get(key) is not True:
            errors.append(validation_error(f"policy.decision_rules.{key}", f"{key} must be true"))
    if policy.get("acceptance_marker") != "PHASE244 V1 RELEASE CANDIDATE DECISION GATE PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 244"))
    return errors


def roadmap_phase_statuses(config_root: Path, start: int, end: int) -> tuple[dict[str, str | None], list[dict[str, str]]]:
    roadmap_path = config_root / "docs" / "ACTIONABLE_WORKFLOW_ROADMAP.md"
    text = roadmap_path.read_text(encoding="utf-8")
    matches = {int(match.group("phase")): match.group("body") for match in PHASE_HEADING_RE.finditer(text)}
    statuses: dict[str, str | None] = {}
    errors: list[dict[str, str]] = []
    for phase in range(start, end + 1):
        body = matches.get(phase)
        status: str | None = None
        if body is not None:
            status_match = re.search(r"^Status:\s*(?P<status>.+?)\s*$", body, flags=re.MULTILINE)
            status = status_match.group("status") if status_match else None
        statuses[str(phase)] = status
        if status != "Complete.":
            errors.append(validation_error(f"phase.{phase}.status", f"Phase {phase} must be Complete.", source="roadmap"))
    return statuses, errors


def load_machine_reports(
    config_root: Path,
    policy: dict[str, Any],
    *,
    require_artifacts: bool,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    refs: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    for item in object_list(policy.get("required_machine_reports")):
        report_id = str(item.get("id"))
        path = resolve_path(config_root, str(item.get("path")))
        payload: dict[str, Any] = {}
        if not path.is_file():
            if require_artifacts:
                errors.append(validation_error(f"machine_reports.{report_id}.missing", f"required report missing: {path}", source=report_id))
        else:
            try:
                payload = read_json_object(path)
            except (OSError, json.JSONDecodeError, RuntimeError) as exc:
                errors.append(validation_error(f"machine_reports.{report_id}.malformed", str(exc), source=report_id))
        refs[report_id] = {
            "path": str(path),
            "sha256": artifact_hash(path),
            "kind": payload.get("kind"),
            "status": payload.get("status"),
            "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
        }
        if payload:
            if payload.get("kind") != item.get("expected_kind"):
                errors.append(validation_error(f"machine_reports.{report_id}.kind", "kind mismatch", source=report_id))
            if payload.get("status") != item.get("expected_status"):
                errors.append(validation_error(f"machine_reports.{report_id}.status", "status mismatch", source=report_id))
            expected_summary = dict_value(item.get("expected_summary"))
            summary = dict_value(payload.get("summary"))
            for key, expected in expected_summary.items():
                if summary.get(key) != expected:
                    errors.append(validation_error(f"machine_reports.{report_id}.summary.{key}", f"summary {key} mismatch", source=report_id))
    return refs, errors


def docs_and_limit_checks(config_root: Path, policy: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    docs: list[dict[str, Any]] = []
    combined_parts: list[str] = []
    for raw_path in string_list(policy.get("required_docs")):
        path = resolve_path(config_root, raw_path)
        exists = path.is_file()
        docs.append({"path": raw_path, "exists": exists, "sha256": artifact_hash(path)})
        if not exists:
            errors.append(validation_error(f"docs.{raw_path}.missing", "required doc is missing", source="docs"))
            continue
        combined_parts.append(path.read_text(encoding="utf-8"))
    combined = "\n".join(combined_parts).lower()
    marker_results = {}
    for marker in string_list(policy.get("known_limit_markers")):
        present = marker.lower() in combined
        marker_results[marker] = present
        if not present:
            errors.append(validation_error(f"known_limits.{marker}.missing", "known limit marker is missing", source="known_limits"))
    return {"docs": docs, "known_limit_markers": marker_results}, errors


def probe_url(url: str, timeout_seconds: int) -> dict[str, Any]:
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return {"url": url, "status_code": response.status, "passed": 200 <= response.status < 400}
    except urllib.error.HTTPError as exc:
        return {"url": url, "status_code": exc.code, "passed": 200 <= exc.code < 400, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"url": url, "status_code": None, "passed": False, "error": str(exc)}


def runtime_health(policy: dict[str, Any], *, run_live_health: bool, timeout_seconds: int) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for item in object_list(policy.get("required_runtime_health")):
        probe_id = str(item.get("id"))
        url = str(item.get("url"))
        result = {"id": probe_id, **(probe_url(url, timeout_seconds) if run_live_health else {"url": url, "passed": None, "status_code": None, "skipped": True})}
        results.append(result)
        if run_live_health and item.get("required") is True and result.get("passed") is not True:
            errors.append(validation_error(f"runtime_health.{probe_id}", f"required runtime probe failed: {url}", source="runtime_health"))
    return results, errors


def decision_for_errors(errors: list[dict[str, str]]) -> str:
    if not errors:
        return ReleaseCandidateDecision.SHIP.value
    if all(error.get("source") == "runtime_health" for error in errors):
        return ReleaseCandidateDecision.HOLD.value
    runtime_errors = [error for error in errors if error.get("source") == "runtime_health"]
    non_runtime_errors = [error for error in errors if error.get("source") != "runtime_health"]
    if non_runtime_errors:
        return ReleaseCandidateDecision.REPAIR_REQUIRED.value
    if runtime_errors:
        return ReleaseCandidateDecision.HOLD.value
    return ReleaseCandidateDecision.REPAIR_REQUIRED.value


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# V1 Release-Candidate Decision Gate",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Decision: `{report.get('decision')}`",
        f"- Blocker count: `{len(object_list(report.get('blockers')))}`",
        "",
        "## Blockers",
    ]
    blockers = object_list(report.get("blockers"))
    if blockers:
        lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in blockers)
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def validate_v1_release_candidate_decision_gate(config: V1ReleaseCandidateDecisionGateConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path)
    policy = read_json_object(policy_path)

    policy_errors = validate_policy(policy)
    phase_range = dict_value(policy.get("required_phase_range"))
    phase_statuses, phase_errors = roadmap_phase_statuses(config_root, int(phase_range.get("start", 232)), int(phase_range.get("end", 243)))
    machine_reports, machine_errors = load_machine_reports(config_root, policy, require_artifacts=config.require_artifacts)
    doc_checks, doc_errors = docs_and_limit_checks(config_root, policy)
    health_results, health_errors = runtime_health(policy, run_live_health=config.run_live_health, timeout_seconds=config.health_timeout_seconds)

    blockers = [*policy_errors, *phase_errors, *machine_errors, *doc_errors, *health_errors]
    decision = decision_for_errors(blockers)
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": sorted(EXPECTED_MILESTONE_IDS),
        "generated_at": utc_timestamp(),
        "status": "passed",
        "decision": decision,
        "policy_path": str(policy_path),
        "policy_sha256": artifact_hash(policy_path),
        "phase_statuses": phase_statuses,
        "machine_reports": machine_reports,
        "documentation": doc_checks,
        "runtime_health": health_results,
        "blockers": blockers,
        "next_action": {
            ReleaseCandidateDecision.SHIP.value: "Promote release candidate to founder/external tester use.",
            ReleaseCandidateDecision.HOLD.value: "Restore runtime health, rerun live gates, then rerun Phase 244.",
            ReleaseCandidateDecision.REPAIR_REQUIRED.value: "Repair missing or failed proof artifacts, then rerun Phase 244.",
        }[decision],
        "summary": {
            "blocker_count": len(blockers),
            "runtime_health_blocker_count": len(health_errors),
            "machine_report_count": len(machine_reports),
            "phase_count": len(phase_statuses),
        },
    }
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown(report))
    return report
