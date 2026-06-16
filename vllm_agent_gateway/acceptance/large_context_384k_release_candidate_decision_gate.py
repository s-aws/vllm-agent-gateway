"""Phase 265 release-candidate decision gate for the 384k large-context target."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.v1_release_candidate_decision_gate import (
    ReleaseCandidateDecision,
    artifact_hash,
    dict_value,
    object_list,
    probe_url,
    read_json_object,
    sha256_file,
    string_list,
    validation_error,
    write_json,
    write_text,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "large_context_384k_release_candidate_decision_gate_policy"
EXPECTED_REPORT_KIND = "large_context_384k_release_candidate_decision_gate_report"
EXPECTED_PHASE = 265
EXPECTED_BACKLOG_ID = "P0-M6-265"
EXPECTED_MILESTONE_IDS = {"M1", "M6", "M14"}
TARGET_ESTIMATED_PROJECT_TOKENS = 384_000
DEFAULT_POLICY_PATH = Path("runtime") / "large_context_384k_release_candidate_decision_gate_policy.json"
DEFAULT_PHASE264_REPORT_PATH = (
    Path("runtime-state")
    / "phase264"
    / "phase264-large-context-384k-clean-clone-replay-report.json"
)
DEFAULT_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase265"
    / "phase265-large-context-384k-release-candidate-decision-gate-report.json"
)
DEFAULT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase265"
    / "phase265-large-context-384k-release-candidate-decision-gate-report.md"
)
PHASE_HEADING_RE = re.compile(
    r"^### Approved Phase (?P<phase>\d+):.*?(?P<body>.*?)(?=^### Approved Phase |\Z)",
    re.MULTILINE | re.DOTALL,
)


@dataclass(frozen=True)
class LargeContext384kReleaseCandidateDecisionGateConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    phase264_report_path: Path = DEFAULT_PHASE264_REPORT_PATH
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


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "phase must be 265"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be exactly M1, M6, and M14"))
    if set(string_list(policy.get("allowed_decisions"))) != {item.value for item in ReleaseCandidateDecision}:
        errors.append(validation_error("policy.allowed_decisions", "allowed_decisions must be ship, hold, and repair_required"))
    phase_range = dict_value(policy.get("required_phase_range"))
    if phase_range.get("start") != 258 or phase_range.get("end") != 264:
        errors.append(validation_error("policy.required_phase_range", "required phase range must be 258-264"))
    phase264 = dict_value(policy.get("required_phase264_report"))
    if phase264.get("required_target_estimated_project_tokens") != TARGET_ESTIMATED_PROJECT_TOKENS:
        errors.append(validation_error("policy.required_phase264_report.target", "Phase 264 target must be 384000"))
    if phase264.get("expected_kind") != "large_context_384k_clean_clone_replay_report":
        errors.append(validation_error("policy.required_phase264_report.expected_kind", "Phase 264 report kind mismatch"))
    if phase264.get("expected_status") != "passed":
        errors.append(validation_error("policy.required_phase264_report.expected_status", "Phase 264 expected status must be passed"))
    if phase264.get("expected_decision") != "phase264_clean_clone_384k_usability_ready":
        errors.append(validation_error("policy.required_phase264_report.expected_decision", "Phase 264 expected decision mismatch"))
    if set(string_list(phase264.get("required_strategy_ids"))) != {
        "artifact_paging",
        "chunked_investigation",
        "refusal",
        "retrieval",
        "summarization",
    }:
        errors.append(validation_error("policy.required_phase264_report.required_strategy_ids", "Phase 264 strategy set mismatch"))
    for key in ("minimum_response_count", "minimum_gateway_response_count", "minimum_anythingllm_response_count"):
        if not isinstance(phase264.get(key), int) or phase264[key] <= 0:
            errors.append(validation_error(f"policy.required_phase264_report.{key}", f"{key} must be positive"))
    if len(object_list(policy.get("required_runtime_health"))) < 5:
        errors.append(validation_error("policy.required_runtime_health", "runtime health probes are required"))
    for item in object_list(policy.get("required_runtime_health")):
        probe_id = str(item.get("id") or "unknown")
        if not isinstance(item.get("url"), str) or not item["url"].startswith("http://127.0.0.1:"):
            errors.append(validation_error(f"policy.required_runtime_health.{probe_id}.url", "localhost URL is required"))
        if item.get("required") is not True:
            errors.append(validation_error(f"policy.required_runtime_health.{probe_id}.required", "probe must be required"))
    if len(string_list(policy.get("required_docs"))) < 5:
        errors.append(validation_error("policy.required_docs", "required docs are required"))
    if len(string_list(policy.get("known_limit_markers"))) < 3:
        errors.append(validation_error("policy.known_limit_markers", "known limit markers are required"))
    rules = dict_value(policy.get("decision_rules"))
    for key in ("ship_only_when_no_blockers", "hold_on_runtime_health_failure", "repair_on_missing_required_phase_or_artifact"):
        if rules.get(key) is not True:
            errors.append(validation_error(f"policy.decision_rules.{key}", f"{key} must be true"))
    if policy.get("acceptance_marker") != "PHASE265 LARGE CONTEXT 384K RELEASE CANDIDATE DECISION GATE PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 265"))
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


def load_phase264_report(
    config_root: Path,
    report_path: Path,
    *,
    require_artifacts: bool,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    resolved = resolve_path(config_root, report_path)
    payload: dict[str, Any] = {}
    if not resolved.is_file():
        if require_artifacts:
            errors.append(validation_error("phase264_report.missing", f"required Phase 264 report missing: {resolved}", source="phase264"))
    else:
        try:
            payload = read_json_object(resolved)
        except Exception as exc:  # noqa: BLE001
            errors.append(validation_error("phase264_report.malformed", str(exc), source="phase264"))
    return {
        "path": str(resolved),
        "sha256": artifact_hash(resolved),
        "kind": payload.get("kind"),
        "status": payload.get("status"),
        "decision": payload.get("decision"),
        "summary": dict_value(payload.get("summary")),
        "static_gates": {
            key: {"status": value.get("status"), "summary": dict_value(value.get("summary"))}
            for key, value in dict_value(payload.get("static_gates")).items()
            if isinstance(value, dict)
        },
    }, errors


def phase264_errors(policy: dict[str, Any], phase264: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    required = dict_value(policy.get("required_phase264_report"))
    summary = dict_value(phase264.get("summary"))
    if phase264.get("kind") != required.get("expected_kind"):
        errors.append(validation_error("phase264.kind", "Phase 264 report kind mismatch", source="phase264"))
    if phase264.get("status") != required.get("expected_status"):
        errors.append(validation_error("phase264.status", "Phase 264 report status mismatch", source="phase264"))
    if phase264.get("decision") != required.get("expected_decision"):
        errors.append(validation_error("phase264.decision", "Phase 264 report decision mismatch", source="phase264"))
    exact_summary = {
        "target_estimated_project_tokens": required.get("required_target_estimated_project_tokens"),
        "json_default_parity_status": required.get("required_json_default_parity_status"),
        "target_settings_status": required.get("required_target_settings_status"),
        "failed_small_repo_regression_count": 0,
        "critical_or_high_finding_count": 0,
        "runtime_state_ignored": True,
        "source_dirty_line_count_before": 0,
        "source_dirty_line_count_after": 0,
        "phase265_ready": True,
    }
    for key, expected in exact_summary.items():
        if summary.get(key) != expected:
            errors.append(validation_error(f"phase264.summary.{key}", f"{key} must be {expected!r}", source="phase264"))
    minimums = {
        "response_count": required.get("minimum_response_count"),
        "gateway_response_count": required.get("minimum_gateway_response_count"),
        "anythingllm_response_count": required.get("minimum_anythingllm_response_count"),
    }
    for key, minimum in minimums.items():
        if isinstance(minimum, int) and (not isinstance(summary.get(key), int) or summary[key] < minimum):
            errors.append(validation_error(f"phase264.summary.{key}", f"{key} below {minimum}", source="phase264"))
    if summary.get("static_gate_count") != required.get("required_static_gate_count"):
        errors.append(validation_error("phase264.summary.static_gate_count", "static gate count mismatch", source="phase264"))
    if summary.get("passed_static_gate_count") != required.get("required_static_gate_count"):
        errors.append(validation_error("phase264.summary.passed_static_gate_count", "not all static gates passed", source="phase264"))
    missing_strategies = sorted(set(string_list(required.get("required_strategy_ids"))) - set(string_list(summary.get("strategy_ids"))))
    if missing_strategies:
        errors.append(validation_error("phase264.summary.strategy_ids", f"missing strategies: {', '.join(missing_strategies)}", source="phase264"))
    if summary.get("source_branch") != required.get("required_branch"):
        errors.append(validation_error("phase264.summary.source_branch", "source branch mismatch", source="phase264"))
    remote = str(summary.get("source_remote_origin_url") or "")
    if str(required.get("required_remote_url_fragment") or "") not in remote:
        errors.append(validation_error("phase264.summary.source_remote_origin_url", "source remote mismatch", source="phase264"))
    for gate_id, gate in dict_value(phase264.get("static_gates")).items():
        if gate.get("status") != "passed":
            errors.append(validation_error(f"phase264.static_gates.{gate_id}", "Phase 264 static gate did not pass", source="phase264"))
    return errors


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
    return ReleaseCandidateDecision.REPAIR_REQUIRED.value


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Large-Context 384k Release-Candidate Decision Gate",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Decision: `{report.get('decision')}`",
        f"- Blocker count: `{len(object_list(report.get('blockers')))}`",
        f"- Phase 264 report: `{dict_value(report.get('phase264_report')).get('path')}`",
        "",
        "## Blockers",
    ]
    blockers = object_list(report.get("blockers"))
    if blockers:
        lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in blockers)
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def validate_large_context_384k_release_candidate_decision_gate(
    config: LargeContext384kReleaseCandidateDecisionGateConfig,
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
        int(phase_range.get("start", 258)),
        int(phase_range.get("end", 264)),
    )
    phase264, phase264_load_errors = load_phase264_report(
        config_root,
        config.phase264_report_path,
        require_artifacts=config.require_artifacts,
    )
    phase264_validation_errors = phase264_errors(policy, phase264) if phase264.get("kind") else []
    doc_checks, doc_errors = docs_and_limit_checks(config_root, policy)
    health_results, health_errors = runtime_health(
        policy,
        run_live_health=config.run_live_health,
        timeout_seconds=config.health_timeout_seconds,
    )

    blockers = [
        *policy_errors,
        *phase_errors,
        *phase264_load_errors,
        *phase264_validation_errors,
        *doc_errors,
        *health_errors,
    ]
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
        "policy_sha256": sha256_file(policy_path) if policy_path.is_file() else None,
        "phase_statuses": phase_statuses,
        "phase264_report": phase264,
        "documentation": doc_checks,
        "runtime_health": health_results,
        "blockers": blockers,
        "next_action": {
            ReleaseCandidateDecision.SHIP.value: "Proceed to Phase 266 stable 384k handoff refresh.",
            ReleaseCandidateDecision.HOLD.value: "Restore runtime health, rerun live 384k proof as needed, then rerun Phase 265.",
            ReleaseCandidateDecision.REPAIR_REQUIRED.value: "Repair missing or failed 384k proof artifacts, then rerun Phase 264 and Phase 265.",
        }[decision],
        "summary": {
            "blocker_count": len(blockers),
            "runtime_health_blocker_count": len(health_errors),
            "phase_count": len(phase_statuses),
            "phase264_status": phase264.get("status"),
            "phase264_decision": phase264.get("decision"),
            "target_estimated_project_tokens": dict_value(phase264.get("summary")).get("target_estimated_project_tokens"),
            "phase266_ready": decision == ReleaseCandidateDecision.SHIP.value,
        },
    }
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown(report))
    return report
