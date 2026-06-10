"""Contextless audit scorecard for Priority 0 release evidence."""

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
EXPECTED_POLICY_KIND = "contextless_audit_scorecard_policy"
EXPECTED_REPORT_KIND = "contextless_audit_scorecard_report"
EXPECTED_PHASE = 149
EXPECTED_BACKLOG_ID = "P0-BB-020"
DEFAULT_POLICY_PATH = Path("runtime") / "contextless_audit_scorecard_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "contextless-audit-scorecard" / "phase149"
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
REQUIRED_DIMENSIONS = {
    "blind_baseline_before_local": 20,
    "context_isolation": 15,
    "chat_visible_answer_quality": 15,
    "route_skill_tool_evidence": 15,
    "fixture_mutation_safety": 15,
    "repair_rerun_traceability": 10,
    "residual_risk_handling": 10,
}
REQUIRED_RELEASE_SIGNALS = {
    "blocked",
    "needs_review",
    "evidence_complete_not_sufficient",
    "candidate_ready_for_founder_review",
}


class ScorecardStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class ReleaseSignal(str, Enum):
    BLOCKED = "blocked"
    NEEDS_REVIEW = "needs_review"
    EVIDENCE_COMPLETE_NOT_SUFFICIENT = "evidence_complete_not_sufficient"
    CANDIDATE_READY_FOR_FOUNDER_REVIEW = "candidate_ready_for_founder_review"


@dataclass(frozen=True)
class ContextlessAuditScorecardConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    markdown_output_path: Path | None = None
    require_artifacts: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"contextless-audit-scorecard-{utc_timestamp()}.json"


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
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def int_value(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) else default


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 149")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    version = policy.get("policy_version")
    if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
        errors.append("policy.policy_version must use semantic version x.y.z")
    purpose = str(policy.get("purpose") or "").lower()
    if "not a substitute" not in purpose or "does not grant release approval" not in purpose:
        errors.append("policy.purpose must state the scorecard is not a substitute and does not grant release approval")
    if not isinstance(policy.get("recursive_policy_path"), str) or not policy["recursive_policy_path"].strip():
        errors.append("policy.recursive_policy_path must be a path string")
    authority = dict_value(policy.get("authority_policy"))
    if authority.get("blind_evaluator_is_pass_fail_authority") is not False:
        errors.append("authority_policy.blind_evaluator_is_pass_fail_authority must be false")
    if authority.get("scorecard_grants_release_approval") is not False:
        errors.append("authority_policy.scorecard_grants_release_approval must be false")
    if authority.get("deterministic_validator_is_pass_fail_authority") is not True:
        errors.append("authority_policy.deterministic_validator_is_pass_fail_authority must be true")
    if set(string_list(policy.get("release_signal_values"))) != REQUIRED_RELEASE_SIGNALS:
        errors.append("policy.release_signal_values must match the required release signal values")
    floors = dict_value(policy.get("score_floors"))
    for key in ("aggregate_minimum", "source_minimum", "dimension_minimum"):
        value = floors.get(key)
        if not isinstance(value, int) or value < 0 or value > 100:
            errors.append(f"score_floors.{key} must be an integer from 0 through 100")
    dimensions = object_list(policy.get("scoring_dimensions"))
    points_by_id = {
        str(item.get("id")): item.get("points")
        for item in dimensions
        if isinstance(item.get("id"), str)
    }
    if set(points_by_id) != set(REQUIRED_DIMENSIONS):
        errors.append("policy.scoring_dimensions must contain exactly the required dimension ids")
    for dimension_id, expected_points in REQUIRED_DIMENSIONS.items():
        if points_by_id.get(dimension_id) != expected_points:
            errors.append(f"scoring_dimensions[{dimension_id}].points must be {expected_points}")
    if sum(value for value in points_by_id.values() if isinstance(value, int)) != 100:
        errors.append("policy.scoring_dimensions points must sum to 100")
    if not string_list(policy.get("hard_blocker_codes")):
        errors.append("policy.hard_blocker_codes must be a non-empty string list")
    if not string_list(policy.get("forbidden_blind_authority_markers")):
        errors.append("policy.forbidden_blind_authority_markers must be a non-empty string list")
    if not string_list(policy.get("required_target_roots")):
        errors.append("policy.required_target_roots must be a non-empty string list")
    if set(string_list(policy.get("required_routes"))) != {"gateway", "anythingllm"}:
        errors.append("policy.required_routes must contain gateway and anythingllm")
    sources = object_list(policy.get("source_artifacts"))
    if not sources:
        errors.append("policy.source_artifacts must contain required artifacts")
    source_ids = [str(item.get("id")) for item in sources if isinstance(item.get("id"), str)]
    if len(source_ids) != len(set(source_ids)):
        errors.append("policy.source_artifacts ids must be unique")
    for index, source in enumerate(sources):
        prefix = f"policy.source_artifacts[{index}]"
        for key in ("id", "type", "path", "expected_kind", "expected_status"):
            if not isinstance(source.get(key), str) or not source[key].strip():
                errors.append(f"{prefix}.{key} must be a non-empty string")
        if source.get("required") is not True:
            errors.append(f"{prefix}.required must be true")
        expected_phase = source.get("expected_phase")
        if expected_phase is not None and not isinstance(expected_phase, int):
            errors.append(f"{prefix}.expected_phase must be an integer when present")
    return errors


def source_ref(path: Path | None, payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "path": str(path) if path else None,
        "sha256": artifact_hash(path),
        "kind": payload.get("kind"),
        "status": payload.get("status"),
        "phase": payload.get("phase"),
        "priority_backlog_id": payload.get("priority_backlog_id"),
        "created_at": payload.get("created_at"),
        "generated_at": payload.get("generated_at"),
    }


def hard_blocker(code: str, source_id: str, message: str, evidence_refs: list[str] | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "source_id": source_id,
        "severity": "critical" if code in {"protected_fixture_mutation", "context_leakage"} else "high",
        "message": message,
        "evidence_refs": evidence_refs or [],
    }


def contains_forbidden_authority(payload: dict[str, Any], markers: list[str]) -> list[str]:
    text = json.dumps(payload, ensure_ascii=True, sort_keys=True).lower()
    return [marker for marker in markers if marker.lower() in text]


def recursive_unresolved_high_findings(payload: dict[str, Any]) -> list[str]:
    accepted_ids = {
        str(item.get("id"))
        for round_item in object_list(payload.get("rounds"))
        for item in object_list(round_item.get("accepted_findings"))
    }
    rejected_ids = {
        str(item.get("id"))
        for round_item in object_list(payload.get("rounds"))
        for item in object_list(round_item.get("rejected_findings"))
    }
    resolved_ids = accepted_ids | rejected_ids
    unresolved: list[str] = []
    for round_item in object_list(payload.get("rounds")):
        for index, finding in enumerate(object_list(round_item.get("blind_findings"))):
            finding_id = str(finding.get("id") or f"finding_{index}")
            if finding.get("severity") in {"critical", "high"} and finding_id not in resolved_ids:
                unresolved.append(finding_id)
    return sorted(set(unresolved))


def recursive_has_context_leakage(payload: dict[str, Any]) -> bool:
    for round_item in object_list(payload.get("rounds")):
        evaluator = dict_value(round_item.get("evaluator_context"))
        if evaluator.get("fork_context") is not False:
            return True
        if evaluator.get("session_history_allowed") is True:
            return True
    return False


def recursive_repair_trace_missing(payload: dict[str, Any]) -> bool:
    for round_item in object_list(payload.get("rounds")):
        for finding in object_list(round_item.get("accepted_findings")):
            if not string_list(finding.get("validation_refs")):
                return True
            if not isinstance(finding.get("owner"), str) or not str(finding.get("owner")).strip():
                return True
            if not isinstance(finding.get("action"), str) or not str(finding.get("action")).strip():
                return True
    return False


def fixture_hashes_unchanged(payload: dict[str, Any]) -> bool:
    before = dict_value(payload.get("fixture_state_before"))
    after = dict_value(payload.get("fixture_state_after"))
    if not before or not after:
        return True
    for root, before_state in before.items():
        after_state = after.get(root)
        if not isinstance(before_state, dict) or not isinstance(after_state, dict):
            return False
        if before_state.get("hashes") != after_state.get("hashes"):
            return False
        if before_state.get("git_status") != after_state.get("git_status"):
            return False
    return True


def fresh_drift_family_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for family in object_list(payload.get("families")):
        comparison = dict_value(family.get("comparison"))
        local_eval = dict_value(family.get("local_eval_summary"))
        records.append(
            {
                "record_type": "blind_baseline_local_comparison",
                "source_id": "phase127_fresh_local_model_drift",
                "family_id": family.get("family_id"),
                "case_ids": string_list(family.get("case_ids")),
                "prompt_ref": family.get("fresh_local_eval_path"),
                "blind_baseline_ref": {
                    "blind_baselines_sha256": dict_value(family.get("source_hashes")).get("blind_baselines_sha256"),
                    "prompt_cases_sha256": dict_value(family.get("source_hashes")).get("prompt_cases_sha256"),
                },
                "local_answer_ref": {
                    "path": family.get("fresh_local_eval_path"),
                    "sha256": family.get("fresh_local_eval_sha256"),
                },
                "difference": {
                    "comparison_status": comparison.get("status"),
                    "minimum_route_score": family.get("minimum_route_score"),
                    "drift_severity": family.get("drift_severity"),
                    "gap_categories": comparison.get("gap_categories"),
                },
                "repair": {
                    "next_action": family.get("next_action"),
                    "recommended_next_repairs": comparison.get("recommended_next_repairs"),
                },
                "rerun": {
                    "routes": string_list(family.get("required_routes")),
                    "target_roots": string_list(family.get("target_roots")),
                    "comparison_path": family.get("fresh_comparison_path"),
                },
                "residual_risk": {
                    "critical_finding_count": comparison.get("critical_finding_count"),
                    "high_finding_count": comparison.get("high_finding_count"),
                    "target_changed_files": local_eval.get("target_changed_files"),
                },
            }
        )
    return records


def founder_smoke_case_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for case in object_list(payload.get("cases")):
        records.append(
            {
                "record_type": "founder_smoke_prompt",
                "source_id": "phase134_founder_smoke",
                "case_id": case.get("case_id"),
                "prompt": case.get("prompt"),
                "blind_baseline": case.get("baseline_target"),
                "local_answer_ref": {
                    "run_id": case.get("run_id"),
                    "text_sha256": case.get("text_sha256"),
                    "text_sample": str(case.get("text_sample") or "")[:800],
                },
                "difference": case.get("initial_difference"),
                "repair": {
                    "refined_prompt": case.get("refined_prompt"),
                    "suggested_prompt_if_missed": case.get("suggested_prompt_if_missed"),
                },
                "rerun": {
                    "expected_workflow": case.get("expected_workflow"),
                    "target_root": case.get("target_root"),
                    "http_status": case.get("http_status"),
                },
                "residual_risk": {
                    "prompt_risk": case.get("prompt_risk"),
                    "missing_markers": case.get("missing_markers"),
                    "missing_semantic_markers": case.get("missing_semantic_markers"),
                },
            }
        )
    return records


def evaluate_source(
    *,
    source_policy: dict[str, Any],
    payload: dict[str, Any] | None,
    path: Path | None,
    policy: dict[str, Any],
) -> dict[str, Any]:
    source_id = str(source_policy.get("id"))
    source_type = str(source_policy.get("type"))
    blockers: list[dict[str, Any]] = []
    warnings: list[str] = []
    evidence_refs = [str(path)] if path is not None else []
    score = 100
    if path is None or payload is None:
        return {
            "source_id": source_id,
            "type": source_type,
            "score": 0,
            "status": "failed",
            "blockers": [
                hard_blocker("missing_required_artifact", source_id, "required scorecard source artifact is missing")
            ],
            "warnings": warnings,
            "evidence_refs": evidence_refs,
        }
    if payload.get("kind") != source_policy.get("expected_kind"):
        blockers.append(
            hard_blocker(
                "source_kind_mismatch",
                source_id,
                f"expected kind {source_policy.get('expected_kind')} but found {payload.get('kind')}",
                evidence_refs,
            )
        )
    if payload.get("status") != source_policy.get("expected_status"):
        blockers.append(
            hard_blocker(
                "source_status_failed",
                source_id,
                f"expected status {source_policy.get('expected_status')} but found {payload.get('status')}",
                evidence_refs,
            )
        )
    if source_policy.get("expected_phase") is not None and payload.get("phase") != source_policy.get("expected_phase"):
        blockers.append(
            hard_blocker(
                "source_phase_mismatch",
                source_id,
                f"expected phase {source_policy.get('expected_phase')} but found {payload.get('phase')}",
                evidence_refs,
            )
        )
    forbidden = contains_forbidden_authority(payload, string_list(policy.get("forbidden_blind_authority_markers")))
    if forbidden:
        blockers.append(
            hard_blocker(
                "blind_agent_release_authority",
                source_id,
                "source artifact contains blind-agent release authority wording",
                evidence_refs + forbidden,
            )
        )
    summary = dict_value(payload.get("summary"))
    if source_type == "baseline_corpus":
        if int_value(summary.get("entry_count")) == 0 or summary.get("entry_count") != summary.get("stable_entry_count"):
            warnings.append("baseline corpus does not show all entries stable")
            score -= 20
        for entry in object_list(payload.get("entries")):
            if entry.get("comparison_status") != "passed" or entry.get("status") != "stable":
                blockers.append(
                    hard_blocker(
                        "missing_blind_baseline_order",
                        source_id,
                        "baseline corpus entry is not stable with a passed comparison",
                        evidence_refs,
                    )
                )
    elif source_type == "fresh_local_model_drift":
        if summary.get("response_count") != summary.get("passed_response_count"):
            blockers.append(
                hard_blocker("missing_blind_baseline_order", source_id, "not all fresh local responses passed", evidence_refs)
            )
        required_routes = set(string_list(policy.get("required_routes")))
        if set(string_list(summary.get("required_routes"))) != required_routes:
            blockers.append(
                hard_blocker(
                    "missing_local_gateway_anythingllm_evidence",
                    source_id,
                    "fresh drift summary does not prove both gateway and AnythingLLM routes",
                    evidence_refs,
                )
            )
        if set(string_list(summary.get("target_roots"))) != set(string_list(policy.get("required_target_roots"))):
            blockers.append(
                hard_blocker(
                    "protected_fixture_mutation",
                    source_id,
                    "fresh drift summary does not cover both required frozen target roots",
                    evidence_refs,
                )
            )
        if int_value(summary.get("critical_finding_count")) or int_value(summary.get("high_finding_count")):
            blockers.append(
                hard_blocker(
                    "unresolved_critical_high_risk",
                    source_id,
                    "fresh drift report contains critical or high findings",
                    evidence_refs,
                )
            )
        minimum_scores = dict_value(summary.get("minimum_route_scores"))
        if minimum_scores:
            numeric_scores = [int(value) for value in minimum_scores.values() if isinstance(value, int)]
            if numeric_scores:
                score = min(score, min(numeric_scores))
        for family in object_list(payload.get("families")):
            hashes = dict_value(family.get("source_hashes"))
            if not hashes.get("blind_baselines_sha256") or not hashes.get("prompt_cases_sha256"):
                blockers.append(
                    hard_blocker(
                        "missing_blind_baseline_order",
                        source_id,
                        "fresh drift family is missing governed prompt or blind-baseline hashes",
                        evidence_refs,
                    )
                )
            local_eval_command = dict_value(dict_value(family.get("commands")).get("local_eval"))
            if "--baselines-path" not in string_list(local_eval_command.get("argv")):
                blockers.append(
                    hard_blocker(
                        "missing_blind_baseline_order",
                        source_id,
                        "fresh local eval command did not use a governed baselines path",
                        evidence_refs,
                    )
                )
            comparison = dict_value(family.get("comparison"))
            if comparison.get("status") != "passed" or comparison.get("response_count") != comparison.get("passed_response_count"):
                blockers.append(
                    hard_blocker("missing_blind_baseline_order", source_id, "fresh family comparison did not pass", evidence_refs)
                )
            local_eval = dict_value(family.get("local_eval_summary"))
            if local_eval.get("runtime_changed_files") not in ([], None):
                blockers.append(
                    hard_blocker("protected_fixture_mutation", source_id, "fresh local eval mutated runtime files", evidence_refs)
                )
            target_changed = local_eval.get("target_changed_files")
            if isinstance(target_changed, dict) and any(target_changed.values()):
                blockers.append(
                    hard_blocker("protected_fixture_mutation", source_id, "fresh local eval mutated target files", evidence_refs)
                )
    elif source_type == "founder_smoke":
        passed_count = int_value(summary.get("passed"))
        failed_count = int_value(summary.get("failed"))
        total_count = passed_count + failed_count
        score = 100 if total_count == 0 else int(round((passed_count / total_count) * 100))
        if failed_count:
            blockers.append(hard_blocker("source_status_failed", source_id, "founder smoke contains failed cases", evidence_refs))
        for case in object_list(payload.get("cases")):
            if case.get("status") != "passed" or case.get("semantic_quality_status") != "passed":
                blockers.append(hard_blocker("source_status_failed", source_id, "founder smoke case did not pass", evidence_refs))
            if not case.get("run_id") or not case.get("expected_workflow"):
                blockers.append(
                    hard_blocker(
                        "missing_local_gateway_anythingllm_evidence",
                        source_id,
                        "founder smoke case is missing run_id or expected workflow",
                        evidence_refs,
                    )
                )
        if not fixture_hashes_unchanged(payload):
            blockers.append(
                hard_blocker("protected_fixture_mutation", source_id, "founder smoke fixture hashes changed", evidence_refs)
            )
    elif source_type == "chat_transcript_quality":
        if payload.get("quality_status") != "pass":
            blockers.append(hard_blocker("source_status_failed", source_id, "chat transcript quality did not pass", evidence_refs))
        if int_value(summary.get("blocker_finding_count")) or int_value(summary.get("blocker_case_count")):
            blockers.append(
                hard_blocker(
                    "unresolved_critical_high_risk",
                    source_id,
                    "chat transcript quality has blocker findings",
                    evidence_refs,
                )
            )
        pass_count = int_value(summary.get("pass_case_count"))
        case_count = int_value(summary.get("case_count"))
        score = 100 if case_count == 0 else int(round((pass_count / case_count) * 100))
    elif source_type == "recursive_audit":
        score = int_value(dict_value(payload.get("score_summary")).get("total_score"))
        if recursive_has_context_leakage(payload):
            blockers.append(hard_blocker("context_leakage", source_id, "recursive audit used forked or session context", evidence_refs))
        unresolved = recursive_unresolved_high_findings(payload)
        if unresolved:
            blockers.append(
                hard_blocker(
                    "unresolved_critical_high_risk",
                    source_id,
                    "recursive audit has unresolved critical/high findings",
                    evidence_refs + unresolved,
                )
            )
        if dict_value(payload.get("convergence")).get("status") != "converged":
            blockers.append(
                hard_blocker(
                    "unresolved_critical_high_risk",
                    source_id,
                    "recursive audit did not converge",
                    evidence_refs,
                )
            )
        if recursive_repair_trace_missing(payload):
            blockers.append(
                hard_blocker(
                    "missing_repair_rerun_trace",
                    source_id,
                    "recursive audit accepted finding lacks owner, action, or validation refs",
                    evidence_refs,
                )
            )
    elif source_type == "external_tester_dry_run":
        if summary.get("live_runtime") is not True or summary.get("onboarding_live_status") != "passed":
            blockers.append(
                hard_blocker(
                    "missing_local_gateway_anythingllm_evidence",
                    source_id,
                    "external tester dry run did not pass live runtime onboarding",
                    evidence_refs,
                )
            )
        if int_value(summary.get("doctor_failed_check_count")) or int_value(summary.get("doc_blocker_count")):
            blockers.append(
                hard_blocker("unresolved_critical_high_risk", source_id, "external tester dry run has blockers", evidence_refs)
            )
        manual_prompt = dict_value(payload.get("manual_prompt"))
        if manual_prompt.get("source_mutation") is not False:
            blockers.append(
                hard_blocker("protected_fixture_mutation", source_id, "external tester dry run reported source mutation", evidence_refs)
            )
        if not manual_prompt.get("run_id") or not manual_prompt.get("selected_workflow"):
            blockers.append(
                hard_blocker(
                    "missing_local_gateway_anythingllm_evidence",
                    source_id,
                    "external tester manual prompt lacks run_id or selected workflow",
                    evidence_refs,
                )
            )
    elif source_type == "failure_to_roadmap":
        if int_value(summary.get("release_blocker_count")) or int_value(summary.get("error_count")):
            blockers.append(
                hard_blocker(
                    "unresolved_critical_high_risk",
                    source_id,
                    "failure-to-roadmap gate has release blockers or errors",
                    evidence_refs,
                )
            )
        if int_value(summary.get("unapproved_proposal_count")):
            warnings.append("failure-to-roadmap has unapproved proposals")
            score -= 10
    else:
        warnings.append(f"unknown source type {source_type}")
        score -= 20
    source_minimum = int_value(dict_value(policy.get("score_floors")).get("source_minimum"), 85)
    if score < source_minimum:
        blockers.append(
            hard_blocker(
                "source_score_below_floor",
                source_id,
                f"source score {score} is below source_minimum={source_minimum}",
                evidence_refs,
            )
        )
    if blockers:
        score = min(score, 84)
    return {
        "source_id": source_id,
        "type": source_type,
        "score": max(0, min(100, score)),
        "status": "passed" if not blockers else "failed",
        "blockers": blockers,
        "warnings": warnings,
        "evidence_refs": evidence_refs,
    }


def source_by_type(
    sources: dict[str, tuple[Path | None, dict[str, Any] | None]],
    policy: dict[str, Any],
    source_type: str,
) -> list[tuple[str, Path | None, dict[str, Any] | None]]:
    type_by_id = {str(item.get("id")): str(item.get("type")) for item in object_list(policy.get("source_artifacts"))}
    return [
        (source_id, path, payload)
        for source_id, (path, payload) in sources.items()
        if type_by_id.get(source_id) == source_type
    ]


def dimension_score(
    dimension_id: str,
    score: int,
    evidence_refs: list[str],
    blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "dimension_id": dimension_id,
        "score": max(0, min(100, score)),
        "evidence_refs": evidence_refs,
        "blocker_codes": sorted({str(item.get("code")) for item in blockers}),
    }


def build_dimension_scores(
    *,
    sources: dict[str, tuple[Path | None, dict[str, Any] | None]],
    policy: dict[str, Any],
    source_evaluations: list[dict[str, Any]],
    recursive_policy: dict[str, Any] | None,
    recursive_policy_path: Path | None,
) -> list[dict[str, Any]]:
    blockers_by_code: dict[str, list[dict[str, Any]]] = {}
    evaluation_by_id = {str(item.get("source_id")): item for item in source_evaluations}
    for evaluation in source_evaluations:
        for blocker_item in object_list(evaluation.get("blockers")):
            blockers_by_code.setdefault(str(blocker_item.get("code")), []).append(blocker_item)
    recursive_sources = source_by_type(sources, policy, "recursive_audit")
    fresh_sources = source_by_type(sources, policy, "fresh_local_model_drift")
    founder_sources = source_by_type(sources, policy, "founder_smoke")
    chat_sources = source_by_type(sources, policy, "chat_transcript_quality")
    external_sources = source_by_type(sources, policy, "external_tester_dry_run")
    ftr_sources = source_by_type(sources, policy, "failure_to_roadmap")

    def type_sources_pass(source_items: list[tuple[str, Path | None, dict[str, Any] | None]]) -> bool:
        return bool(source_items) and all(
            payload is not None and evaluation_by_id.get(source_id, {}).get("status") == "passed"
            for source_id, _path, payload in source_items
        )

    fresh_ok = type_sources_pass(fresh_sources) and not blockers_by_code.get("missing_blind_baseline_order")
    recursive_policy_ok = bool(recursive_policy) and dict_value(recursive_policy.get("adjudication_policy")).get(
        "blind_evaluator_is_pass_fail_authority"
    ) is False
    context_ok = recursive_policy_ok and type_sources_pass(recursive_sources) and not blockers_by_code.get("context_leakage")
    chat_ok = type_sources_pass(founder_sources) and type_sources_pass(chat_sources) and not blockers_by_code.get("source_status_failed")
    route_ok = type_sources_pass(fresh_sources) and type_sources_pass(external_sources) and not blockers_by_code.get(
        "missing_local_gateway_anythingllm_evidence"
    )
    fixture_ok = not blockers_by_code.get("protected_fixture_mutation")
    repair_ok = type_sources_pass(recursive_sources) and type_sources_pass(ftr_sources) and not blockers_by_code.get("missing_repair_rerun_trace")
    residual_ok = not blockers_by_code.get("unresolved_critical_high_risk")

    recursive_refs = [str(path) for _, path, _ in recursive_sources if path is not None]
    fresh_refs = [str(path) for _, path, _ in fresh_sources if path is not None]
    founder_refs = [str(path) for _, path, _ in founder_sources if path is not None]
    chat_refs = [str(path) for _, path, _ in chat_sources if path is not None]
    external_refs = [str(path) for _, path, _ in external_sources if path is not None]
    ftr_refs = [str(path) for _, path, _ in ftr_sources if path is not None]
    return [
        dimension_score(
            "blind_baseline_before_local",
            100 if fresh_ok else 0,
            fresh_refs,
            blockers_by_code.get("missing_blind_baseline_order", []),
        ),
        dimension_score(
            "context_isolation",
            100 if context_ok else 0,
            recursive_refs + ([str(recursive_policy_path)] if recursive_policy_path else []),
            blockers_by_code.get("context_leakage", []) + blockers_by_code.get("blind_agent_release_authority", []),
        ),
        dimension_score(
            "chat_visible_answer_quality",
            100 if chat_ok else 0,
            founder_refs + chat_refs,
            blockers_by_code.get("source_status_failed", []),
        ),
        dimension_score(
            "route_skill_tool_evidence",
            100 if route_ok else 0,
            fresh_refs + external_refs,
            blockers_by_code.get("missing_local_gateway_anythingllm_evidence", []),
        ),
        dimension_score(
            "fixture_mutation_safety",
            100 if fixture_ok else 0,
            fresh_refs + founder_refs + external_refs,
            blockers_by_code.get("protected_fixture_mutation", []),
        ),
        dimension_score(
            "repair_rerun_traceability",
            100 if repair_ok else 0,
            recursive_refs + ftr_refs,
            blockers_by_code.get("missing_repair_rerun_trace", []),
        ),
        dimension_score(
            "residual_risk_handling",
            100 if residual_ok else 0,
            [str(path) for path, _payload in sources.values() if path is not None],
            blockers_by_code.get("unresolved_critical_high_risk", []),
        ),
    ]


def weighted_dimension_score(policy: dict[str, Any], dimensions: list[dict[str, Any]]) -> int:
    points_by_id = {
        str(item.get("id")): int_value(item.get("points"))
        for item in object_list(policy.get("scoring_dimensions"))
    }
    total_points = sum(points_by_id.values()) or 100
    score = 0.0
    for dimension in dimensions:
        dimension_id = str(dimension.get("dimension_id"))
        score += int_value(dimension.get("score")) * (points_by_id.get(dimension_id, 0) / total_points)
    return int(round(score))


def collect_audit_records(sources: dict[str, tuple[Path | None, dict[str, Any] | None]], policy: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for _source_id, _path, payload in source_by_type(sources, policy, "fresh_local_model_drift"):
        if payload is not None:
            records.extend(fresh_drift_family_records(payload))
    for _source_id, _path, payload in source_by_type(sources, policy, "founder_smoke"):
        if payload is not None:
            records.extend(founder_smoke_case_records(payload))
    return records


def collect_residual_risks(sources: dict[str, tuple[Path | None, dict[str, Any] | None]], policy: dict[str, Any]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for source_id, _path, payload in source_by_type(sources, policy, "founder_smoke"):
        if payload is None:
            continue
        for case in object_list(payload.get("cases")):
            prompt_risk = case.get("prompt_risk")
            if isinstance(prompt_risk, str) and prompt_risk.strip():
                risks.append(
                    {
                        "source_id": source_id,
                        "severity": "low",
                        "case_id": case.get("case_id"),
                        "risk": prompt_risk,
                        "disposition": "documented_prompt_risk",
                    }
                )
    for source_id, _path, payload in source_by_type(sources, policy, "recursive_audit"):
        if payload is None:
            continue
        for round_item in object_list(payload.get("rounds")):
            for finding in object_list(round_item.get("rejected_findings")):
                if finding.get("severity") in {"critical", "high"}:
                    risks.append(
                        {
                            "source_id": source_id,
                            "severity": finding.get("severity"),
                            "case_id": finding.get("id"),
                            "risk": finding.get("finding"),
                            "disposition": finding.get("rejection_reason"),
                        }
                    )
    return risks


def load_source_artifacts(
    *,
    config_root: Path,
    policy: dict[str, Any],
    require_artifacts: bool,
) -> tuple[dict[str, tuple[Path | None, dict[str, Any] | None]], list[str]]:
    sources: dict[str, tuple[Path | None, dict[str, Any] | None]] = {}
    errors: list[str] = []
    for source in object_list(policy.get("source_artifacts")):
        source_id = str(source.get("id"))
        path_value = source.get("path")
        if not isinstance(path_value, str):
            sources[source_id] = (None, None)
            errors.append(f"source artifact {source_id} path is invalid")
            continue
        path = resolve_path(config_root, path_value)
        if not path.is_file():
            sources[source_id] = (None, None)
            if require_artifacts or source.get("required") is True:
                errors.append(f"required source artifact is missing: {path_value}")
            continue
        try:
            sources[source_id] = (path, read_json_object(path))
        except Exception as exc:  # noqa: BLE001
            sources[source_id] = (path, None)
            errors.append(f"source artifact {source_id} is malformed: {type(exc).__name__}: {exc}")
    return sources, errors


def load_recursive_policy(config_root: Path, policy: dict[str, Any]) -> tuple[Path | None, dict[str, Any] | None, list[str]]:
    path_value = policy.get("recursive_policy_path")
    if not isinstance(path_value, str):
        return None, None, ["recursive policy path is invalid"]
    path = resolve_path(config_root, path_value)
    if not path.is_file():
        return path, None, [f"recursive policy is missing: {path_value}"]
    try:
        return path, read_json_object(path), []
    except Exception as exc:  # noqa: BLE001
        return path, None, [f"recursive policy is malformed: {type(exc).__name__}: {exc}"]


def build_contextless_audit_scorecard_report(
    *,
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any] | None]],
    recursive_policy: dict[str, Any] | None,
    policy_path: Path | None = None,
    recursive_policy_path: Path | None = None,
    input_errors: list[str] | None = None,
) -> dict[str, Any]:
    errors = validate_policy(policy)
    errors.extend(input_errors or [])
    source_evaluations: list[dict[str, Any]] = []
    source_policy_by_id = {str(item.get("id")): item for item in object_list(policy.get("source_artifacts"))}
    for source_id, source_policy in source_policy_by_id.items():
        path, payload = sources.get(source_id, (None, None))
        source_evaluations.append(
            evaluate_source(source_policy=source_policy, payload=payload, path=path, policy=policy)
        )
    recursive_errors: list[str] = []
    if recursive_policy is None:
        recursive_errors.append("recursive blind-testing policy must be loadable")
    else:
        adjudication = dict_value(recursive_policy.get("adjudication_policy"))
        if adjudication.get("blind_evaluator_is_pass_fail_authority") is not False:
            recursive_errors.append("recursive policy grants blind evaluator pass/fail authority")
    for recursive_error in recursive_errors:
        source_evaluations.append(
            {
                "source_id": "recursive_policy",
                "type": "recursive_policy",
                "score": 0,
                "status": "failed",
                "blockers": [
                    hard_blocker(
                        "blind_agent_release_authority",
                        "recursive_policy",
                        recursive_error,
                        [str(recursive_policy_path)] if recursive_policy_path else [],
                    )
                ],
                "warnings": [],
                "evidence_refs": [str(recursive_policy_path)] if recursive_policy_path else [],
            }
        )
    dimension_scores = build_dimension_scores(
        sources=sources,
        policy=policy,
        source_evaluations=source_evaluations,
        recursive_policy=recursive_policy,
        recursive_policy_path=recursive_policy_path,
    )
    hard_blockers = [
        blocker
        for evaluation in source_evaluations
        for blocker in object_list(evaluation.get("blockers"))
    ]
    source_scores = [
        int_value(evaluation.get("score"))
        for evaluation in source_evaluations
        if evaluation.get("type") != "recursive_policy"
    ]
    source_average = int(round(sum(source_scores) / len(source_scores))) if source_scores else 0
    dimension_average = weighted_dimension_score(policy, dimension_scores)
    aggregate_score = min(source_average, dimension_average)
    aggregate_minimum = int_value(dict_value(policy.get("score_floors")).get("aggregate_minimum"), 85)
    dimension_minimum = int_value(dict_value(policy.get("score_floors")).get("dimension_minimum"), 70)
    low_dimensions = [
        str(item.get("dimension_id"))
        for item in dimension_scores
        if int_value(item.get("score")) < dimension_minimum
    ]
    if aggregate_score < aggregate_minimum:
        hard_blockers.append(
            hard_blocker(
                "aggregate_score_below_floor",
                "scorecard",
                f"aggregate score {aggregate_score} is below aggregate_minimum={aggregate_minimum}",
            )
        )
    for dimension_id in low_dimensions:
        hard_blockers.append(
            hard_blocker(
                "aggregate_score_below_floor",
                "scorecard",
                f"dimension {dimension_id} is below dimension_minimum={dimension_minimum}",
            )
        )
    residual_risks = collect_residual_risks(sources, policy)
    high_or_critical_residual_count = sum(1 for risk in residual_risks if risk.get("severity") in {"critical", "high"})
    if hard_blockers or errors:
        signal = ReleaseSignal.BLOCKED.value
    elif high_or_critical_residual_count:
        signal = ReleaseSignal.NEEDS_REVIEW.value
    elif aggregate_score >= 90:
        signal = ReleaseSignal.CANDIDATE_READY_FOR_FOUNDER_REVIEW.value
    else:
        signal = ReleaseSignal.EVIDENCE_COMPLETE_NOT_SUFFICIENT.value
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": ScorecardStatus.PASSED.value if not hard_blockers and not errors else ScorecardStatus.FAILED.value,
        "generated_at": utc_timestamp(),
        "policy_ref": source_ref(policy_path, policy),
        "recursive_policy_ref": source_ref(recursive_policy_path, recursive_policy),
        "source_refs": {
            source_id: source_ref(path, payload)
            for source_id, (path, payload) in sources.items()
        },
        "scorecard": {
            "release_readiness_signal": signal,
            "aggregate_score": aggregate_score,
            "dimension_average_score": dimension_average,
            "source_average_score": source_average,
            "dimension_scores": dimension_scores,
            "source_scores": source_evaluations,
            "audit_records": collect_audit_records(sources, policy),
            "residual_risks": residual_risks,
            "hard_blockers": hard_blockers,
        },
        "summary": {
            "source_count": len(sources),
            "audit_record_count": len(collect_audit_records(sources, policy)),
            "hard_blocker_count": len(hard_blockers),
            "residual_risk_count": len(residual_risks),
            "high_or_critical_residual_risk_count": high_or_critical_residual_count,
            "aggregate_score": aggregate_score,
            "release_readiness_signal": signal,
            "error_count": len(errors),
        },
        "errors": errors,
    }
    return report


def stable_report_view(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in report.items()
        if key not in {"generated_at", "report_path", "markdown_report_path"}
    }


def validate_contextless_audit_scorecard_report(
    report: dict[str, Any],
    *,
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any] | None]],
    recursive_policy: dict[str, Any] | None,
    policy_path: Path | None = None,
    recursive_policy_path: Path | None = None,
    input_errors: list[str] | None = None,
) -> list[str]:
    expected = build_contextless_audit_scorecard_report(
        policy=policy,
        sources=sources,
        recursive_policy=recursive_policy,
        policy_path=policy_path,
        recursive_policy_path=recursive_policy_path,
        input_errors=input_errors,
    )
    errors: list[str] = []
    for key, value in stable_report_view(expected).items():
        if stable_report_view(report).get(key) != value:
            errors.append(f"report.{key} must match rebuilt contextless audit scorecard")
    return errors


def markdown_from_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    scorecard = dict_value(report.get("scorecard"))
    lines = [
        "# Contextless Audit Scorecard",
        "",
        f"- Status: {report.get('status')}",
        f"- Release readiness signal: {summary.get('release_readiness_signal')}",
        f"- Aggregate score: {summary.get('aggregate_score')}",
        f"- Hard blockers: {summary.get('hard_blocker_count')}",
        f"- Residual risks: {summary.get('residual_risk_count')}",
        "",
        "## Dimension Scores",
        "",
    ]
    for dimension in object_list(scorecard.get("dimension_scores")):
        lines.append(f"- {dimension.get('dimension_id')}: {dimension.get('score')}")
    lines.extend(["", "## Hard Blockers", ""])
    blockers = object_list(scorecard.get("hard_blockers"))
    if not blockers:
        lines.append("- None")
    else:
        for blocker_item in blockers:
            lines.append(f"- {blocker_item.get('code')} ({blocker_item.get('source_id')}): {blocker_item.get('message')}")
    lines.extend(["", "## Audit Records", ""])
    for record in object_list(scorecard.get("audit_records"))[:20]:
        label = record.get("case_id") or record.get("family_id")
        lines.append(f"- {record.get('record_type')} {label}: {record.get('difference')}")
    lines.append("")
    return "\n".join(lines)


def run_contextless_audit_scorecard(config: ContextlessAuditScorecardConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    try:
        policy = read_json_object(policy_path)
    except Exception as exc:  # noqa: BLE001
        policy = {}
        source_load_errors = [f"policy could not be loaded: {type(exc).__name__}: {exc}"]
    else:
        source_load_errors = []
    sources, load_errors = load_source_artifacts(
        config_root=config_root,
        policy=policy,
        require_artifacts=config.require_artifacts,
    )
    recursive_policy_path, recursive_policy, recursive_errors = load_recursive_policy(config_root, policy)
    source_load_errors.extend(load_errors)
    source_load_errors.extend(recursive_errors)
    report = build_contextless_audit_scorecard_report(
        policy=policy,
        sources=sources,
        recursive_policy=recursive_policy,
        policy_path=policy_path if policy_path.is_file() else None,
        recursive_policy_path=recursive_policy_path,
        input_errors=source_load_errors,
    )
    validation_errors = validate_contextless_audit_scorecard_report(
        report,
        policy=policy,
        sources=sources,
        recursive_policy=recursive_policy,
        policy_path=policy_path if policy_path.is_file() else None,
        recursive_policy_path=recursive_policy_path,
        input_errors=source_load_errors,
    )
    if validation_errors:
        report["status"] = ScorecardStatus.FAILED.value
        report["errors"] = list(report.get("errors", [])) + validation_errors
        report["summary"]["error_count"] = len(report["errors"])
        report["scorecard"]["release_readiness_signal"] = ReleaseSignal.BLOCKED.value
        report["summary"]["release_readiness_signal"] = ReleaseSignal.BLOCKED.value
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    if config.markdown_output_path is not None:
        markdown_path = config.markdown_output_path
        if not markdown_path.is_absolute():
            markdown_path = config_root / markdown_path
        write_text(markdown_path, markdown_from_report(report))
        report["markdown_report_path"] = str(markdown_path.resolve())
        write_json(output_path, report)
    return report
