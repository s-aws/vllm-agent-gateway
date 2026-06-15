"""Phase 247 release-candidate ship handoff gate."""

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
EXPECTED_POLICY_KIND = "release_candidate_ship_handoff_policy"
EXPECTED_REPORT_KIND = "release_candidate_ship_handoff_report"
EXPECTED_PHASE = 247
EXPECTED_BACKLOG_ID = "P0-M14-247"
EXPECTED_MILESTONE_IDS = {"M1", "M14"}
DEFAULT_POLICY_PATH = Path("runtime") / "release_candidate_ship_handoff_policy.json"
DEFAULT_OUTPUT_PATH = (
    Path("runtime-state")
    / "release-candidate-ship-handoff"
    / "phase247"
    / "phase247-release-candidate-ship-handoff-report.json"
)
DEFAULT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state")
    / "release-candidate-ship-handoff"
    / "phase247"
    / "phase247-release-candidate-ship-handoff-report.md"
)
PHASE_HEADING_RE = re.compile(
    r"^### Approved Phase (?P<phase>\d+):.*?(?P<body>.*?)(?=^### Approved Phase |\Z)",
    re.MULTILINE | re.DOTALL,
)


class ReleaseCandidateShipHandoffStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class ReleaseCandidateShipHandoffConfig:
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


def marker_map(value: object) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, list[str]] = {}
    for key, raw_markers in value.items():
        if isinstance(key, str):
            markers = string_list(raw_markers)
            if markers:
                result[key] = markers
    return result


def nested_value(payload: dict[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def validation_error(error_id: str, message: str, *, source: str = "policy", severity: str = "high") -> dict[str, str]:
    return {"id": error_id, "message": message, "source": source, "severity": severity}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "phase must be 247"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be exactly M1 and M14"))
    for key in ("required_release_proof", "required_release_channel_manifest"):
        if not isinstance(policy.get(key), str) or not policy[key].strip():
            errors.append(validation_error(f"policy.{key}", f"{key} must be a path string"))
    if not dict_value(policy.get("decision_source")):
        errors.append(validation_error("policy.decision_source", "decision_source is required"))
    expected_proof = dict_value(policy.get("expected_release_proof"))
    for key in (
        "kind",
        "status",
        "profile",
        "proof_kind",
        "source_phase",
        "phase244_decision",
        "phase245_decision",
        "decision_source_branch",
        "decision_source_commit",
    ):
        if key not in expected_proof:
            errors.append(validation_error(f"policy.expected_release_proof.{key}", f"{key} is required"))
    expected_readiness = dict_value(policy.get("expected_stable_readiness"))
    for key in ("activated_at", "activated_by", "activated_from_report", "activated_profile"):
        if not isinstance(expected_readiness.get(key), str) or not expected_readiness[key].strip():
            errors.append(validation_error(f"policy.expected_stable_readiness.{key}", f"{key} is required"))
    docs = string_list(policy.get("required_docs"))
    if len(docs) < 5:
        errors.append(validation_error("policy.required_docs", "release handoff docs are required"))
    docs_markers = marker_map(policy.get("docs_required_markers"))
    for doc in docs:
        if doc not in docs_markers:
            errors.append(validation_error(f"policy.docs_required_markers.{doc}", "each required doc must have markers"))
    if len(string_list(policy.get("global_known_limit_markers"))) < 3:
        errors.append(validation_error("policy.global_known_limit_markers", "known-limit markers are required"))
    if policy.get("acceptance_marker") != "PHASE247 RELEASE CANDIDATE SHIP HANDOFF PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 247"))
    return errors


def phase247_status(config_root: Path) -> tuple[str | None, dict[str, str] | None]:
    roadmap_path = config_root / "docs" / "ACTIONABLE_WORKFLOW_ROADMAP.md"
    if not roadmap_path.is_file():
        return None, validation_error("roadmap.missing", "docs/ACTIONABLE_WORKFLOW_ROADMAP.md is missing", source="roadmap")
    text = roadmap_path.read_text(encoding="utf-8")
    matches = {int(match.group("phase")): match.group("body") for match in PHASE_HEADING_RE.finditer(text)}
    body = matches.get(EXPECTED_PHASE)
    if body is None:
        return None, validation_error("roadmap.phase247.missing", "Phase 247 is missing from the roadmap", source="roadmap")
    status_match = re.search(r"^Status:\s*(?P<status>.+?)\s*$", body, flags=re.MULTILINE)
    status = status_match.group("status") if status_match else None
    if status != "Complete.":
        return status, validation_error("roadmap.phase247.status", "Phase 247 must be Complete.", source="roadmap")
    return status, None


def release_proof_checks(config_root: Path, policy: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    proof_path = resolve_path(config_root, str(policy.get("required_release_proof")))
    details: dict[str, Any] = {
        "path": str(proof_path),
        "exists": proof_path.is_file(),
        "sha256": artifact_hash(proof_path),
    }
    if not proof_path.is_file():
        return details, [validation_error("release_proof.missing", f"release proof missing: {proof_path}", source="release_proof")]
    try:
        proof = read_json_object(proof_path)
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        return details, [validation_error("release_proof.malformed", str(exc), source="release_proof")]

    details.update(
        {
            "kind": proof.get("kind"),
            "status": proof.get("status"),
            "profile": proof.get("profile"),
            "proof_kind": proof.get("proof_kind"),
            "source_phase": proof.get("source_phase"),
            "ship_decision": proof.get("ship_decision"),
            "decision_source": proof.get("decision_source") if isinstance(proof.get("decision_source"), dict) else {},
            "runtime_restoration": proof.get("runtime_restoration") if isinstance(proof.get("runtime_restoration"), dict) else {},
            "final_regression": proof.get("final_regression") if isinstance(proof.get("final_regression"), dict) else {},
        }
    )

    expected = dict_value(policy.get("expected_release_proof"))
    comparisons = {
        "kind": proof.get("kind"),
        "status": proof.get("status"),
        "profile": proof.get("profile"),
        "proof_kind": proof.get("proof_kind"),
        "source_phase": proof.get("source_phase"),
        "phase244_decision": nested_value(proof, "decision_source.phase244_summary.decision"),
        "phase244_runtime_health_blocker_count": nested_value(proof, "decision_source.phase244_summary.runtime_health_blocker_count"),
        "phase244_machine_report_count": nested_value(proof, "decision_source.phase244_summary.machine_report_count"),
        "phase245_decision": nested_value(proof, "runtime_restoration.decision"),
        "phase245_gateway_run_id": nested_value(proof, "runtime_restoration.gateway_run_id"),
        "phase245_anythingllm_run_id": nested_value(proof, "runtime_restoration.anythingllm_run_id"),
        "decision_source_branch": nested_value(proof, "decision_source.branch"),
        "decision_source_commit": nested_value(proof, "decision_source.commit"),
        "decision_source_clone_path": nested_value(proof, "decision_source.clone_path"),
        "final_regression_result_contains": str(nested_value(proof, "final_regression.result") or ""),
    }
    for key, expected_value in expected.items():
        actual_value = comparisons.get(key)
        if key == "final_regression_result_contains":
            if not isinstance(expected_value, str) or expected_value not in str(actual_value):
                errors.append(
                    validation_error(
                        f"release_proof.{key}",
                        f"final regression result must contain {expected_value!r}, got {actual_value!r}",
                        source="release_proof",
                    )
                )
            continue
        if actual_value != expected_value:
            errors.append(
                validation_error(
                    f"release_proof.{key}",
                    f"{key} must be {expected_value!r}, got {actual_value!r}",
                    source="release_proof",
                )
            )
    if proof.get("ship_decision") != "ship":
        errors.append(validation_error("release_proof.ship_decision", "ship_decision must be ship", source="release_proof"))
    boundary = proof.get("known_boundary")
    if not isinstance(boundary, str) or "Advanced broad refactor orchestration remains deferred" not in boundary:
        errors.append(validation_error("release_proof.known_boundary", "known_boundary must defer advanced broad refactor orchestration", source="release_proof"))
    regression = dict_value(proof.get("final_regression"))
    result = str(regression.get("result") or "")
    expected_regression_marker = expected.get("final_regression_result_contains")
    if isinstance(expected_regression_marker, str) and expected_regression_marker not in result:
        errors.append(
            validation_error(
                "release_proof.final_regression.result",
                f"final regression result must record {expected_regression_marker}",
                source="release_proof",
            )
        )
    return details, errors


def release_channel_checks(config_root: Path, policy: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    manifest_path = resolve_path(config_root, str(policy.get("required_release_channel_manifest")))
    details: dict[str, Any] = {
        "path": str(manifest_path),
        "exists": manifest_path.is_file(),
        "sha256": artifact_hash(manifest_path),
    }
    if not manifest_path.is_file():
        return details, [validation_error("release_channel.missing", f"release channel manifest missing: {manifest_path}", source="release_channel")]
    try:
        manifest = read_json_object(manifest_path)
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        return details, [validation_error("release_channel.malformed", str(exc), source="release_channel")]
    stable = next((item for item in object_list(manifest.get("channels")) if item.get("id") == "stable"), None)
    if stable is None:
        return details, [validation_error("release_channel.stable.missing", "stable channel is missing", source="release_channel")]
    readiness = dict_value(stable.get("stable_readiness"))
    details["stable_readiness"] = readiness
    expected = dict_value(policy.get("expected_stable_readiness"))
    for key, expected_value in expected.items():
        if readiness.get(key) != expected_value:
            errors.append(
                validation_error(
                    f"release_channel.stable_readiness.{key}",
                    f"{key} must be {expected_value!r}, got {readiness.get(key)!r}",
                    source="release_channel",
                )
            )
    boundary = str(readiness.get("known_boundary") or "")
    for marker in ("Advanced broad refactor orchestration remains deferred", "Raw 1M-token prompt serving is not claimed"):
        if marker not in boundary:
            errors.append(validation_error(f"release_channel.stable_readiness.boundary.{marker}", f"known_boundary missing marker: {marker}", source="release_channel"))
    return details, errors


def docs_checks(config_root: Path, policy: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    docs: list[dict[str, Any]] = []
    combined_parts: list[str] = []
    markers_by_doc = marker_map(policy.get("docs_required_markers"))
    for raw_path in string_list(policy.get("required_docs")):
        path = resolve_path(config_root, raw_path)
        exists = path.is_file()
        doc_result = {"path": raw_path, "exists": exists, "sha256": artifact_hash(path), "missing_markers": []}
        if not exists:
            errors.append(validation_error(f"docs.{raw_path}.missing", "required doc is missing", source="docs"))
            docs.append(doc_result)
            continue
        text = path.read_text(encoding="utf-8")
        combined_parts.append(text)
        missing = [marker for marker in markers_by_doc.get(raw_path, []) if marker not in text]
        doc_result["missing_markers"] = missing
        for marker in missing:
            errors.append(validation_error(f"docs.{raw_path}.marker", f"required marker missing: {marker}", source="docs"))
        docs.append(doc_result)

    combined = "\n".join(combined_parts)
    global_markers: dict[str, bool] = {}
    for marker in string_list(policy.get("global_known_limit_markers")):
        present = marker in combined
        global_markers[marker] = present
        if not present:
            errors.append(validation_error(f"docs.global_marker.{marker}", f"global marker missing: {marker}", source="docs"))
    return {"docs": docs, "global_known_limit_markers": global_markers}, errors


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Release-Candidate Ship Handoff",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Error count: `{report.get('summary', {}).get('error_count')}`",
        f"- Decision source commit: `{nested_value(report, 'release_proof.decision_source.commit')}`",
        f"- Stable activated by: `{nested_value(report, 'release_channel.stable_readiness.activated_by')}`",
        "",
        "## Errors",
    ]
    errors = object_list(report.get("errors"))
    if errors:
        lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in errors)
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def validate_release_candidate_ship_handoff(config: ReleaseCandidateShipHandoffConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path)
    policy = read_json_object(policy_path)

    policy_errors = validate_policy(policy)
    roadmap_status, roadmap_error = phase247_status(config_root)
    release_proof, release_proof_errors = release_proof_checks(config_root, policy)
    release_channel, release_channel_errors = release_channel_checks(config_root, policy)
    documentation, doc_errors = docs_checks(config_root, policy)

    errors = [*policy_errors, *release_proof_errors, *release_channel_errors, *doc_errors]
    if roadmap_error is not None:
        errors.append(roadmap_error)
    status = ReleaseCandidateShipHandoffStatus.PASSED.value if not errors else ReleaseCandidateShipHandoffStatus.FAILED.value
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": sorted(EXPECTED_MILESTONE_IDS),
        "generated_at": utc_timestamp(),
        "status": status,
        "policy_path": str(policy_path),
        "policy_sha256": artifact_hash(policy_path),
        "roadmap": {"phase": EXPECTED_PHASE, "status": roadmap_status},
        "release_proof": release_proof,
        "release_channel": release_channel,
        "documentation": documentation,
        "errors": errors,
        "summary": {
            "error_count": len(errors),
            "doc_count": len(string_list(policy.get("required_docs"))),
            "global_known_limit_marker_count": len(string_list(policy.get("global_known_limit_markers"))),
            "ship_handoff_ready": not errors,
        },
    }
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown(report))
    return report
