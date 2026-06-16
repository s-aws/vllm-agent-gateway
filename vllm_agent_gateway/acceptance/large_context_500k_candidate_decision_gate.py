"""Phase 276 decision gate for the 500k large-context candidate."""

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
EXPECTED_POLICY_KIND = "large_context_500k_candidate_decision_gate_policy"
EXPECTED_REPORT_KIND = "large_context_500k_candidate_decision_gate_report"
EXPECTED_PHASE = 276
EXPECTED_BACKLOG_ID = "P0-M15-276"
EXPECTED_MILESTONE_IDS = {"M1", "M14", "M15"}
CANDIDATE_ESTIMATED_PROJECT_TOKENS = 500_000
STABLE_ESTIMATED_PROJECT_TOKENS = 384_000
DEFAULT_POLICY_PATH = Path("runtime") / "large_context_500k_candidate_decision_gate_policy.json"
DEFAULT_PHASE275_REPORT_PATH = (
    Path("runtime-state")
    / "phase275"
    / "phase275-large-context-500k-clean-clone-replay-report.json"
)
DEFAULT_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase276"
    / "phase276-large-context-500k-candidate-decision-gate-report.json"
)
DEFAULT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase276"
    / "phase276-large-context-500k-candidate-decision-gate-report.md"
)
PHASE_HEADING_RE = re.compile(
    r"^### Approved Phase (?P<phase>\d+):.*?(?P<body>.*?)(?=^### Approved Phase |\Z)",
    re.MULTILINE | re.DOTALL,
)


@dataclass(frozen=True)
class LargeContext500kCandidateDecisionGateConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    phase275_report_path: Path = DEFAULT_PHASE275_REPORT_PATH
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
        errors.append(validation_error("policy.phase", "phase must be 276"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be exactly M1, M14, and M15"))
    if policy.get("candidate_estimated_project_tokens") != CANDIDATE_ESTIMATED_PROJECT_TOKENS:
        errors.append(validation_error("policy.candidate_estimated_project_tokens", "candidate target must be 500000"))
    if policy.get("stable_estimated_project_tokens") != STABLE_ESTIMATED_PROJECT_TOKENS:
        errors.append(validation_error("policy.stable_estimated_project_tokens", "stable baseline must be 384000"))
    if set(string_list(policy.get("allowed_decisions"))) != {item.value for item in ReleaseCandidateDecision}:
        errors.append(validation_error("policy.allowed_decisions", "allowed_decisions must be ship, hold, and repair_required"))
    phase_range = dict_value(policy.get("required_phase_range"))
    if phase_range.get("start") != 270 or phase_range.get("end") != 275:
        errors.append(validation_error("policy.required_phase_range", "required phase range must be 270-275"))
    phase275 = dict_value(policy.get("required_phase275_report"))
    if phase275.get("expected_kind") != "large_context_500k_clean_clone_replay_report":
        errors.append(validation_error("policy.required_phase275_report.expected_kind", "Phase 275 report kind mismatch"))
    if phase275.get("expected_status") != "passed":
        errors.append(validation_error("policy.required_phase275_report.expected_status", "Phase 275 expected status must be passed"))
    if phase275.get("expected_decision") != "phase275_clean_clone_500k_candidate_ready":
        errors.append(validation_error("policy.required_phase275_report.expected_decision", "Phase 275 expected decision mismatch"))
    if phase275.get("required_gate_count") != 7:
        errors.append(validation_error("policy.required_phase275_report.required_gate_count", "Phase 275 must require seven gates"))
    if set(string_list(phase275.get("required_strategy_ids"))) != {
        "artifact_paging",
        "chunked_investigation",
        "refusal",
        "retrieval",
        "summarization",
    }:
        errors.append(validation_error("policy.required_phase275_report.required_strategy_ids", "Phase 275 strategy set mismatch"))
    for key in ("minimum_response_count", "minimum_gateway_response_count", "minimum_anythingllm_response_count"):
        if not isinstance(phase275.get(key), int) or phase275[key] <= 0:
            errors.append(validation_error(f"policy.required_phase275_report.{key}", f"{key} must be positive"))
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
    if len(string_list(policy.get("known_limit_markers"))) < 4:
        errors.append(validation_error("policy.known_limit_markers", "known limit markers are required"))
    rules = dict_value(policy.get("decision_rules"))
    for key in (
        "ship_only_when_no_blockers",
        "hold_on_runtime_health_failure",
        "repair_on_missing_required_phase_or_artifact",
        "do_not_promote_raw_500k_prompt_serving",
    ):
        if rules.get(key) is not True:
            errors.append(validation_error(f"policy.decision_rules.{key}", f"{key} must be true"))
    if policy.get("acceptance_marker") != "PHASE276 LARGE CONTEXT 500K CANDIDATE DECISION GATE PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 276"))
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


def load_phase275_report(
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
            errors.append(validation_error("phase275_report.missing", f"required Phase 275 report missing: {resolved}", source="phase275"))
    else:
        try:
            payload = read_json_object(resolved)
        except Exception as exc:  # noqa: BLE001
            errors.append(validation_error("phase275_report.malformed", str(exc), source="phase275"))
    return {
        "path": str(resolved),
        "sha256": artifact_hash(resolved),
        "kind": payload.get("kind"),
        "status": payload.get("status"),
        "decision": payload.get("decision"),
        "summary": dict_value(payload.get("summary")),
        "gates": {
            key: {"status": value.get("status"), "summary": dict_value(value.get("summary"))}
            for key, value in dict_value(payload.get("gates")).items()
            if isinstance(value, dict)
        },
    }, errors


def phase275_errors(policy: dict[str, Any], phase275: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    required = dict_value(policy.get("required_phase275_report"))
    summary = dict_value(phase275.get("summary"))
    gates = dict_value(phase275.get("gates"))
    phase273 = dict_value(dict_value(gates.get("phase273_live_acceptance")).get("summary"))
    if phase275.get("kind") != required.get("expected_kind"):
        errors.append(validation_error("phase275.kind", "Phase 275 report kind mismatch", source="phase275"))
    if phase275.get("status") != required.get("expected_status"):
        errors.append(validation_error("phase275.status", "Phase 275 report status mismatch", source="phase275"))
    if phase275.get("decision") != required.get("expected_decision"):
        errors.append(validation_error("phase275.decision", "Phase 275 report decision mismatch", source="phase275"))
    exact_summary = {
        "gate_count": required.get("required_gate_count"),
        "passed_gate_count": required.get("required_gate_count"),
        "controller_preflight_status": "passed",
        "controller_clone_root_allowed": True,
        "phase273_json_default_parity_status": required.get("required_json_default_parity_status"),
        "phase273_critical_or_high_finding_count": 0,
        "phase274_decision": required.get("required_phase274_decision"),
        "phase274_phase275_ready": True,
        "runtime_state_ignored": True,
        "source_dirty_line_count_before": 0,
        "source_dirty_line_count_after": 0,
        "phase276_ready": True,
    }
    for key, expected in exact_summary.items():
        if summary.get(key) != expected:
            errors.append(validation_error(f"phase275.summary.{key}", f"{key} must be {expected!r}", source="phase275"))
    minimums = {
        "phase273_response_count": required.get("minimum_response_count"),
        "phase273_gateway_response_count": required.get("minimum_gateway_response_count"),
        "phase273_anythingllm_response_count": required.get("minimum_anythingllm_response_count"),
    }
    for key, minimum in minimums.items():
        if isinstance(minimum, int) and (not isinstance(summary.get(key), int) or summary[key] < minimum):
            errors.append(validation_error(f"phase275.summary.{key}", f"{key} below {minimum}", source="phase275"))
    if summary.get("source_branch") != required.get("required_branch"):
        errors.append(validation_error("phase275.summary.source_branch", "source branch mismatch", source="phase275"))
    remote = str(summary.get("source_remote_origin_url") or "")
    if str(required.get("required_remote_url_fragment") or "") not in remote:
        errors.append(validation_error("phase275.summary.source_remote_origin_url", "source remote mismatch", source="phase275"))
    for gate_id, gate in gates.items():
        if dict_value(gate).get("status") != "passed":
            errors.append(validation_error(f"phase275.gates.{gate_id}", "Phase 275 gate did not pass", source="phase275"))
    if phase273.get("candidate_estimated_project_tokens") != CANDIDATE_ESTIMATED_PROJECT_TOKENS:
        errors.append(validation_error("phase275.phase273.candidate_estimated_project_tokens", "candidate target must be 500000", source="phase275"))
    if phase273.get("raw_prompt_stuffing_allowed") is not False:
        errors.append(validation_error("phase275.phase273.raw_prompt_stuffing_allowed", "raw prompt stuffing must remain false", source="phase275"))
    missing_strategies = sorted(set(string_list(required.get("required_strategy_ids"))) - set(string_list(phase273.get("strategy_ids"))))
    if missing_strategies:
        errors.append(validation_error("phase275.phase273.strategy_ids", f"missing strategies: {', '.join(missing_strategies)}", source="phase275"))
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
        "# Large-Context 500k Candidate Decision Gate",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Decision: `{report.get('decision')}`",
        f"- Blocker count: `{len(object_list(report.get('blockers')))}`",
        f"- Phase 275 report: `{dict_value(report.get('phase275_report')).get('path')}`",
        "",
        "## Blockers",
    ]
    blockers = object_list(report.get("blockers"))
    if blockers:
        lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in blockers)
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def validate_large_context_500k_candidate_decision_gate(
    config: LargeContext500kCandidateDecisionGateConfig,
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
        int(phase_range.get("end", 275)),
    )
    phase275, phase275_load_errors = load_phase275_report(
        config_root,
        config.phase275_report_path,
        require_artifacts=config.require_artifacts,
    )
    phase275_validation_errors = phase275_errors(policy, phase275) if phase275.get("kind") else []
    doc_checks, doc_errors = docs_and_limit_checks(config_root, policy)
    health_results, health_errors = runtime_health(
        policy,
        run_live_health=config.run_live_health,
        timeout_seconds=config.health_timeout_seconds,
    )

    blockers = [
        *policy_errors,
        *phase_errors,
        *phase275_load_errors,
        *phase275_validation_errors,
        *doc_errors,
        *health_errors,
    ]
    decision = decision_for_errors(blockers)
    phase275_summary = dict_value(phase275.get("summary"))
    phase275_gates = dict_value(phase275.get("gates"))
    phase273_summary = dict_value(dict_value(phase275_gates.get("phase273_live_acceptance")).get("summary"))
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
        "phase275_report": phase275,
        "documentation": doc_checks,
        "runtime_health": health_results,
        "blockers": blockers,
        "next_action": {
            ReleaseCandidateDecision.SHIP.value: "Proceed to Phase 277 stable 500k handoff refresh.",
            ReleaseCandidateDecision.HOLD.value: "Restore runtime health, rerun live 500k proof as needed, then rerun Phase 276.",
            ReleaseCandidateDecision.REPAIR_REQUIRED.value: "Repair missing or failed 500k proof artifacts, then rerun Phase 275 and Phase 276.",
        }[decision],
        "summary": {
            "blocker_count": len(blockers),
            "runtime_health_blocker_count": len(health_errors),
            "phase_count": len(phase_statuses),
            "phase275_status": phase275.get("status"),
            "phase275_decision": phase275.get("decision"),
            "candidate_estimated_project_tokens": phase273_summary.get("candidate_estimated_project_tokens"),
            "stable_estimated_project_tokens": STABLE_ESTIMATED_PROJECT_TOKENS,
            "phase273_response_count": phase275_summary.get("phase273_response_count"),
            "phase273_gateway_response_count": phase275_summary.get("phase273_gateway_response_count"),
            "phase273_anythingllm_response_count": phase275_summary.get("phase273_anythingllm_response_count"),
            "phase273_critical_or_high_finding_count": phase275_summary.get("phase273_critical_or_high_finding_count"),
            "phase273_json_default_parity_status": phase275_summary.get("phase273_json_default_parity_status"),
            "raw_prompt_stuffing_allowed": phase273_summary.get("raw_prompt_stuffing_allowed"),
            "phase277_ready": decision == ReleaseCandidateDecision.SHIP.value,
        },
    }
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown(report))
    return report
