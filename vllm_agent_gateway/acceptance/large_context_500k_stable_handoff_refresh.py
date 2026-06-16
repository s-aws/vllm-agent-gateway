"""Phase 277 stable handoff refresh gate for governed 500k project usability."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.v1_release_candidate_decision_gate import (
    artifact_hash,
    dict_value,
    object_list,
    read_json_object,
    sha256_file,
    string_list,
    validation_error,
    write_json,
    write_text,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "large_context_500k_stable_handoff_refresh_policy"
EXPECTED_REPORT_KIND = "large_context_500k_stable_handoff_refresh_report"
EXPECTED_PHASE = 277
EXPECTED_BACKLOG_ID = "P0-M15-277"
EXPECTED_MILESTONE_IDS = {"M14", "M15"}
CANDIDATE_ESTIMATED_PROJECT_TOKENS = 500_000
PREVIOUS_STABLE_ESTIMATED_PROJECT_TOKENS = 384_000
DEFAULT_POLICY_PATH = Path("runtime") / "large_context_500k_stable_handoff_refresh_policy.json"
DEFAULT_PHASE276_REPORT_PATH = (
    Path("runtime-state")
    / "phase276"
    / "phase276-large-context-500k-candidate-decision-gate-report.json"
)
DEFAULT_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase277"
    / "phase277-large-context-500k-stable-handoff-refresh-report.json"
)
DEFAULT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase277"
    / "phase277-large-context-500k-stable-handoff-refresh-report.md"
)
PHASE_HEADING_RE = re.compile(
    r"^### Approved Phase (?P<phase>\d+):.*?(?P<body>.*?)(?=^### Approved Phase |\Z)",
    re.MULTILINE | re.DOTALL,
)


@dataclass(frozen=True)
class LargeContext500kStableHandoffRefreshConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    phase276_report_path: Path = DEFAULT_PHASE276_REPORT_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    require_artifacts: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "phase must be 277"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be exactly M14 and M15"))
    if policy.get("candidate_estimated_project_tokens") != CANDIDATE_ESTIMATED_PROJECT_TOKENS:
        errors.append(validation_error("policy.candidate_estimated_project_tokens", "candidate target must be 500000"))
    if policy.get("previous_stable_estimated_project_tokens") != PREVIOUS_STABLE_ESTIMATED_PROJECT_TOKENS:
        errors.append(validation_error("policy.previous_stable_estimated_project_tokens", "previous stable baseline must be 384000"))
    phase_range = dict_value(policy.get("required_phase_range"))
    if phase_range.get("start") != 270 or phase_range.get("end") != 276:
        errors.append(validation_error("policy.required_phase_range", "required phase range must be 270-276"))
    phase276 = dict_value(policy.get("required_phase276_report"))
    if phase276.get("expected_kind") != "large_context_500k_candidate_decision_gate_report":
        errors.append(validation_error("policy.required_phase276_report.expected_kind", "Phase 276 report kind mismatch"))
    if phase276.get("expected_status") != "passed":
        errors.append(validation_error("policy.required_phase276_report.expected_status", "Phase 276 expected status must be passed"))
    if phase276.get("expected_decision") != "ship":
        errors.append(validation_error("policy.required_phase276_report.expected_decision", "Phase 276 expected decision must be ship"))
    for key in ("minimum_response_count", "minimum_gateway_response_count", "minimum_anythingllm_response_count"):
        if not isinstance(phase276.get(key), int) or phase276[key] <= 0:
            errors.append(validation_error(f"policy.required_phase276_report.{key}", f"{key} must be positive"))
    for key in ("required_release_channel_manifest", "required_stable_proof"):
        if not isinstance(policy.get(key), str) or not policy[key].strip():
            errors.append(validation_error(f"policy.{key}", f"{key} must be a path string"))
    refresh = dict_value(policy.get("stable_refresh_metadata"))
    for key in ("refreshed_at", "refreshed_by", "refreshed_from_report", "metadata_key"):
        if not isinstance(refresh.get(key), str) or not refresh[key].strip():
            errors.append(validation_error(f"policy.stable_refresh_metadata.{key}", f"{key} is required"))
    if not dict_value(policy.get("required_500k_metadata")):
        errors.append(validation_error("policy.required_500k_metadata", "500k metadata requirements are required"))
    if not dict_value(policy.get("required_384k_lineage")):
        errors.append(validation_error("policy.required_384k_lineage", "384k lineage requirements are required"))
    if len(string_list(policy.get("required_docs"))) < 5:
        errors.append(validation_error("policy.required_docs", "required docs are required"))
    if len(string_list(policy.get("known_boundary_required_markers"))) < 4:
        errors.append(validation_error("policy.known_boundary_required_markers", "known boundary markers are required"))
    if len(string_list(policy.get("docs_required_markers"))) < 4:
        errors.append(validation_error("policy.docs_required_markers", "doc markers are required"))
    if len(string_list(policy.get("forbidden_claim_markers"))) < 3:
        errors.append(validation_error("policy.forbidden_claim_markers", "forbidden claim markers are required"))
    if policy.get("acceptance_marker") != "PHASE277 LARGE CONTEXT 500K STABLE HANDOFF REFRESH PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 277"))
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


def load_json_artifact(
    config_root: Path,
    path: Path,
    *,
    source: str,
    require_artifacts: bool,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]]]:
    resolved = resolve_path(config_root, path)
    payload: dict[str, Any] = {}
    errors: list[dict[str, str]] = []
    if not resolved.is_file():
        if require_artifacts:
            errors.append(validation_error(f"{source}.missing", f"required artifact missing: {resolved}", source=source))
    else:
        try:
            payload = read_json_object(resolved)
        except Exception as exc:  # noqa: BLE001
            errors.append(validation_error(f"{source}.malformed", str(exc), source=source))
    details = {
        "path": str(resolved),
        "exists": resolved.is_file(),
        "sha256": artifact_hash(resolved),
        "kind": payload.get("kind"),
        "status": payload.get("status"),
        "decision": payload.get("decision"),
        "summary": dict_value(payload.get("summary")),
    }
    return payload, details, errors


def phase276_errors(policy: dict[str, Any], report: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    required = dict_value(policy.get("required_phase276_report"))
    summary = dict_value(report.get("summary"))
    if report.get("kind") != required.get("expected_kind"):
        errors.append(validation_error("phase276.kind", "Phase 276 report kind mismatch", source="phase276"))
    if report.get("status") != required.get("expected_status"):
        errors.append(validation_error("phase276.status", "Phase 276 report status mismatch", source="phase276"))
    if report.get("decision") != required.get("expected_decision"):
        errors.append(validation_error("phase276.decision", "Phase 276 decision must be ship", source="phase276"))
    exact_summary = {
        "blocker_count": 0,
        "runtime_health_blocker_count": 0,
        "phase275_status": "passed",
        "phase275_decision": "phase275_clean_clone_500k_candidate_ready",
        "candidate_estimated_project_tokens": CANDIDATE_ESTIMATED_PROJECT_TOKENS,
        "stable_estimated_project_tokens": PREVIOUS_STABLE_ESTIMATED_PROJECT_TOKENS,
        "phase273_critical_or_high_finding_count": 0,
        "phase273_json_default_parity_status": required.get("required_json_default_parity_status"),
        "raw_prompt_stuffing_allowed": required.get("required_raw_prompt_stuffing_allowed"),
        "phase277_ready": required.get("required_phase277_ready"),
    }
    for key, expected in exact_summary.items():
        if summary.get(key) != expected:
            errors.append(validation_error(f"phase276.summary.{key}", f"{key} must be {expected!r}", source="phase276"))
    minimums = {
        "phase273_response_count": required.get("minimum_response_count"),
        "phase273_gateway_response_count": required.get("minimum_gateway_response_count"),
        "phase273_anythingllm_response_count": required.get("minimum_anythingllm_response_count"),
    }
    for key, minimum in minimums.items():
        if isinstance(minimum, int) and (not isinstance(summary.get(key), int) or summary[key] < minimum):
            errors.append(validation_error(f"phase276.summary.{key}", f"{key} below {minimum}", source="phase276"))
    if object_list(report.get("blockers")):
        errors.append(validation_error("phase276.blockers", "Phase 276 blockers must be empty", source="phase276"))
    return errors


def forbidden_claim_errors(text: str, markers: list[str], source: str) -> list[dict[str, str]]:
    lower = text.lower()
    return [
        validation_error(f"{source}.forbidden_claim.{marker}", f"forbidden claim marker present: {marker}", source=source)
        for marker in markers
        if marker.lower() in lower
    ]


def metadata_block_errors(
    payload: dict[str, Any],
    policy: dict[str, Any],
    *,
    source: str,
    stable_readiness_container: bool,
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    refresh = dict_value(policy.get("stable_refresh_metadata"))
    metadata_key = str(refresh.get("metadata_key") or "large_context_500k_project_usability")
    required_500k = dict_value(policy.get("required_500k_metadata"))
    required_384k = dict_value(policy.get("required_384k_lineage"))
    boundary = str(payload.get("known_boundary") or "")
    for marker in string_list(policy.get("known_boundary_required_markers")):
        if marker not in boundary:
            errors.append(validation_error(f"{source}.known_boundary.{marker}", f"known boundary missing marker: {marker}", source=source))
    errors.extend(forbidden_claim_errors(boundary, string_list(policy.get("forbidden_claim_markers")), source))

    if stable_readiness_container:
        for key in ("refreshed_at", "refreshed_by", "refreshed_from_report"):
            if payload.get(key) != refresh.get(key):
                errors.append(
                    validation_error(
                        f"{source}.{key}",
                        f"{key} must be {refresh.get(key)!r}, got {payload.get(key)!r}",
                        source=source,
                    )
                )
    else:
        stable_refresh = dict_value(payload.get("stable_refresh"))
        if stable_refresh.get("phase") != EXPECTED_PHASE:
            errors.append(validation_error(f"{source}.stable_refresh.phase", "stable_refresh.phase must be 277", source=source))
        if stable_refresh.get("refreshed_by") != refresh.get("refreshed_by"):
            errors.append(validation_error(f"{source}.stable_refresh.refreshed_by", "stable_refresh.refreshed_by mismatch", source=source))

    metadata_500k = dict_value(payload.get(metadata_key))
    if not metadata_500k:
        errors.append(validation_error(f"{source}.{metadata_key}.missing", f"{metadata_key} is required", source=source))
    for key, expected in required_500k.items():
        if metadata_500k.get(key) != expected:
            errors.append(
                validation_error(
                    f"{source}.{metadata_key}.{key}",
                    f"{key} must be {expected!r}, got {metadata_500k.get(key)!r}",
                    source=source,
                )
            )

    metadata_384k = dict_value(payload.get("large_context_384k_release_candidate"))
    if not metadata_384k:
        errors.append(validation_error(f"{source}.large_context_384k_release_candidate.missing", "384k lineage is required", source=source))
    for key, expected in required_384k.items():
        if metadata_384k.get(key) != expected:
            errors.append(
                validation_error(
                    f"{source}.large_context_384k_release_candidate.{key}",
                    f"{key} must be {expected!r}, got {metadata_384k.get(key)!r}",
                    source=source,
                )
            )
    return errors


def release_metadata_checks(
    config_root: Path,
    policy: dict[str, Any],
    *,
    require_artifacts: bool,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    manifest_payload, manifest_details, manifest_load_errors = load_json_artifact(
        config_root,
        Path(str(policy.get("required_release_channel_manifest"))),
        source="release_channel",
        require_artifacts=require_artifacts,
    )
    proof_payload, proof_details, proof_load_errors = load_json_artifact(
        config_root,
        Path(str(policy.get("required_stable_proof"))),
        source="stable_proof",
        require_artifacts=require_artifacts,
    )
    errors: list[dict[str, str]] = [*manifest_load_errors, *proof_load_errors]
    stable = next((item for item in object_list(manifest_payload.get("channels")) if item.get("id") == "stable"), None)
    stable_readiness = dict_value(stable.get("stable_readiness")) if isinstance(stable, dict) else {}
    if not stable_readiness:
        errors.append(validation_error("release_channel.stable_readiness.missing", "stable_readiness is required", source="release_channel"))
    else:
        errors.extend(metadata_block_errors(stable_readiness, policy, source="release_channel.stable_readiness", stable_readiness_container=True))
    if proof_payload:
        errors.extend(metadata_block_errors(proof_payload, policy, source="stable_proof", stable_readiness_container=False))
    return {
        "release_channel": {**manifest_details, "stable_readiness": stable_readiness},
        "stable_proof": proof_details,
    }, errors


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
    marker_results: dict[str, bool] = {}
    for marker in string_list(policy.get("docs_required_markers")):
        present = marker.lower() in combined
        marker_results[marker] = present
        if not present:
            errors.append(validation_error(f"docs.marker.{marker}", f"required doc marker missing: {marker}", source="docs"))
    errors.extend(forbidden_claim_errors(combined, string_list(policy.get("forbidden_claim_markers")), "docs"))
    return {"docs": docs, "required_markers": marker_results}, errors


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Large-Context 500k Stable Handoff Refresh",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Decision: `{report.get('decision')}`",
        f"- Blocker count: `{len(object_list(report.get('blockers')))}`",
        f"- Phase 276 report: `{dict_value(report.get('phase276_report')).get('path')}`",
        "",
        "## Blockers",
    ]
    blockers = object_list(report.get("blockers"))
    if blockers:
        lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in blockers)
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def validate_large_context_500k_stable_handoff_refresh(
    config: LargeContext500kStableHandoffRefreshConfig,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path)
    policy = read_json_object(policy_path)

    policy_errors = validate_policy(policy)
    phase_range = dict_value(policy.get("required_phase_range"))
    phase_statuses, phase_errors = roadmap_phase_statuses(
        config_root,
        int(phase_range.get("start", 270)),
        int(phase_range.get("end", 276)),
    )
    phase276_payload, phase276_details, phase276_load_errors = load_json_artifact(
        config_root,
        config.phase276_report_path,
        source="phase276",
        require_artifacts=config.require_artifacts,
    )
    phase276_validation_errors = phase276_errors(policy, phase276_payload) if phase276_payload else []
    release_metadata, release_metadata_errors = release_metadata_checks(
        config_root,
        policy,
        require_artifacts=config.require_artifacts,
    )
    doc_checks, doc_errors = docs_and_limit_checks(config_root, policy)
    blockers = [
        *policy_errors,
        *phase_errors,
        *phase276_load_errors,
        *phase276_validation_errors,
        *release_metadata_errors,
        *doc_errors,
    ]
    decision = "stable_500k_handoff_refreshed" if not blockers else "repair_required"
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": sorted(EXPECTED_MILESTONE_IDS),
        "generated_at": utc_timestamp(),
        "status": "passed" if not blockers else "failed",
        "decision": decision,
        "policy_path": str(policy_path),
        "policy_sha256": sha256_file(policy_path) if policy_path.is_file() else None,
        "phase_statuses": phase_statuses,
        "phase276_report": phase276_details,
        "release_metadata": release_metadata,
        "documentation": doc_checks,
        "blockers": blockers,
        "next_action": "Proceed to the 500k completion audit." if not blockers else "Repair stable 500k handoff metadata or docs, then rerun Phase 277.",
        "summary": {
            "blocker_count": len(blockers),
            "phase_count": len(phase_statuses),
            "phase276_status": phase276_payload.get("status"),
            "phase276_decision": phase276_payload.get("decision"),
            "candidate_estimated_project_tokens": CANDIDATE_ESTIMATED_PROJECT_TOKENS,
            "previous_stable_estimated_project_tokens": PREVIOUS_STABLE_ESTIMATED_PROJECT_TOKENS,
            "raw_500k_prompt_serving_claimed": False if not blockers else None,
            "stable_500k_handoff_refreshed": not blockers,
            "phase278_ready": not blockers,
        },
    }
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown(report))
    return report
