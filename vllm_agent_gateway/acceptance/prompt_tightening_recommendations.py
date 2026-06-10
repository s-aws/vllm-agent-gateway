"""Prompt-tightening recommendation governance for Priority 0 chat quality."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.baseline_corpus import validate_baseline_corpus


SCHEMA_VERSION = 1
DEFAULT_POLICY_PATH = Path("runtime") / "prompt_tightening_recommendation_policy.json"
DEFAULT_BASELINE_CORPUS_PATH = Path("runtime") / "baseline_corpus.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "prompt-tightening-recommendations" / "phase128"
DEFAULT_FRESH_DRIFT_REPORT_PATH = (
    Path("runtime-state") / "fresh-local-model-drift" / "phase127" / "phase127-fresh-local-model-drift-report.json"
)
EXPECTED_POLICY_KIND = "prompt_tightening_recommendation_policy"
EXPECTED_REPORT_KIND = "prompt_tightening_recommendation_report"
EXPECTED_BACKLOG_ID = "P0-BB-013"
EXPECTED_PHASE = 128
EXPECTED_DECISION_STATUSES = {"pending_review", "accepted", "rejected"}
EXPECTED_TRIGGER_REASONS = {
    "baseline_failure",
    "low_confidence_pass",
    "fresh_drift_watch",
    "fresh_drift_failed",
}
EXPECTED_SUGGESTION_CLASSES = {
    "evidence_request",
    "output_contract",
    "scope_boundary",
    "safety_boundary",
    "disambiguation",
    "verification_request",
    "prompt_specificity",
}
MINIMUM_STABLE_SCORE = 85


class PromptTighteningStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class DecisionStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class PromptTighteningRecommendationConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    baseline_corpus_path: Path = DEFAULT_BASELINE_CORPUS_PATH
    fresh_drift_report_path: Path = DEFAULT_FRESH_DRIFT_REPORT_PATH
    output_path: Path | None = None
    require_artifacts: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"prompt-tightening-recommendations-{utc_timestamp()}.json"


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


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_hash(path: Path | None) -> str | None:
    return sha256_file(path) if path is not None and path.is_file() else None


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def stable_baseline_entries(corpus: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(entry["entry_id"]): entry
        for entry in object_list(corpus.get("entries"))
        if entry.get("status") == "stable" and isinstance(entry.get("entry_id"), str)
    }


def prompt_case_lookup(path: Path) -> dict[str, dict[str, Any]]:
    payload = read_json_object(path)
    return {
        str(item["case_id"]): item
        for item in object_list(payload.get("cases"))
        if isinstance(item.get("case_id"), str)
    }


def blind_baseline_lookup(path: Path) -> dict[str, dict[str, Any]]:
    payload = read_json_object(path)
    return {
        str(item["case_id"]): item
        for item in object_list(payload.get("baselines"))
        if isinstance(item.get("case_id"), str)
    }


def holdout_case_ids(cases: dict[str, dict[str, Any]]) -> list[str]:
    return sorted(case_id for case_id, case in cases.items() if case.get("holdout") is True)


def route_scores(case_report: dict[str, Any]) -> dict[str, int]:
    scores: dict[str, int] = {}
    for route in object_list(case_report.get("routes")):
        route_name = route.get("route")
        score = route.get("score")
        if isinstance(route_name, str) and isinstance(score, int):
            scores[route_name] = score
    return scores


def route_findings(case_report: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for route in object_list(case_report.get("routes")):
        for finding in object_list(route.get("unresolved_findings")):
            copied = dict(finding)
            copied["route"] = route.get("route")
            findings.append(copied)
    return findings


def case_passed(case_report: dict[str, Any]) -> bool:
    routes = object_list(case_report.get("routes"))
    return bool(routes) and all(route.get("pass") is True for route in routes)


def classify_suggestion(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ("evidence", "refs", "line", "source")):
        return "evidence_request"
    if any(term in lowered for term in ("section", "table", "bullets", "start with", "require")):
        return "output_contract"
    if any(term in lowered for term in ("read-only", "do not", "no mutation", "before implementation")):
        return "safety_boundary"
    if any(term in lowered for term in ("scope", "at most", "only", "exclude")):
        return "scope_boundary"
    if any(term in lowered for term in ("differentiate", "classify", "compare", "versus", "confirmed versus inferred")):
        return "disambiguation"
    if any(term in lowered for term in ("test", "command", "verification", "validate")):
        return "verification_request"
    return "prompt_specificity"


def trigger_reasons_for_case(
    case_report: dict[str, Any],
    *,
    low_confidence_score: int,
    family_has_summary_gap: bool = False,
) -> list[str]:
    reasons: list[str] = []
    scores = route_scores(case_report)
    if family_has_summary_gap or not case_passed(case_report) or route_findings(case_report):
        reasons.append("baseline_failure")
    if scores and min(scores.values()) <= low_confidence_score:
        reasons.append("low_confidence_pass")
    return reasons


def fresh_drift_case_scores(fresh_drift_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    scores: dict[str, dict[str, Any]] = {}
    for family in object_list(fresh_drift_report.get("families")):
        family_id = str(family.get("family_id"))
        comparison_path = family.get("fresh_comparison_path")
        if not isinstance(comparison_path, str):
            continue
        scores[family_id] = {
            "drift_severity": family.get("drift_severity"),
            "minimum_route_score": family.get("minimum_route_score"),
            "comparison_path": comparison_path,
        }
    return scores


def validate_prompt_tightening_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 128")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    score = policy.get("low_confidence_maximum_route_score")
    if not isinstance(score, int) or score < MINIMUM_STABLE_SCORE or score > 100:
        errors.append("policy.low_confidence_maximum_route_score must be an integer from 85 through 100")
    if set(string_list(policy.get("allowed_trigger_reasons"))) != EXPECTED_TRIGGER_REASONS:
        errors.append("policy.allowed_trigger_reasons must match the governed trigger set")
    if set(string_list(policy.get("allowed_suggestion_classes"))) != EXPECTED_SUGGESTION_CLASSES:
        errors.append("policy.allowed_suggestion_classes must match the governed class set")
    if set(string_list(policy.get("allowed_decision_statuses"))) != EXPECTED_DECISION_STATUSES:
        errors.append("policy.allowed_decision_statuses must be pending_review, accepted, and rejected")
    acceptance = dict_value(policy.get("acceptance_policy"))
    if acceptance.get("prompt_catalog_rewrite_allowed") is not False:
        errors.append("policy.acceptance_policy.prompt_catalog_rewrite_allowed must be false")
    for key in (
        "accepted_change_requires_approval",
        "accepted_change_requires_target_rerun",
        "accepted_change_requires_holdout_rerun",
        "rejected_change_requires_rationale",
    ):
        if acceptance.get(key) is not True:
            errors.append(f"policy.acceptance_policy.{key} must be true")
    return errors


def generate_candidates(
    *,
    config_root: Path,
    policy: dict[str, Any],
    baseline_corpus: dict[str, Any],
    fresh_drift_report: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    low_confidence_score = int(policy["low_confidence_maximum_route_score"])
    fresh_scores = fresh_drift_case_scores(fresh_drift_report or {})
    candidates: list[dict[str, Any]] = []
    for family_id, entry in sorted(stable_baseline_entries(baseline_corpus).items()):
        prompt_ref = dict_value(entry.get("prompt_cases"))
        baseline_ref = dict_value(entry.get("blind_baselines"))
        comparison_ref = dict_value(entry.get("comparison"))
        prompt_cases = prompt_case_lookup(resolve_path(config_root, str(prompt_ref.get("path"))))
        baselines = blind_baseline_lookup(resolve_path(config_root, str(baseline_ref.get("path"))))
        comparison_path = resolve_path(config_root, str(comparison_ref.get("path")))
        if not comparison_path.is_file():
            continue
        comparison = read_json_object(comparison_path)
        family_has_summary_gap = (
            comparison.get("status") != "passed"
            or bool(dict_value(comparison.get("gap_categories")))
            or bool(comparison.get("recommended_next_repairs"))
        )
        family_holdouts = holdout_case_ids(prompt_cases)
        for case_report in object_list(comparison.get("cases")):
            case_id = str(case_report.get("case_id"))
            baseline = baselines.get(case_id, {})
            suggestion = baseline.get("prompt_tightening_suggestion")
            if not isinstance(suggestion, str) or not suggestion.strip():
                continue
            reasons = trigger_reasons_for_case(
                case_report,
                low_confidence_score=low_confidence_score,
                family_has_summary_gap=family_has_summary_gap,
            )
            fresh_family = fresh_scores.get(family_id, {})
            if fresh_family.get("drift_severity") == "watch":
                reasons.append("fresh_drift_watch")
            if fresh_family.get("drift_severity") == "failed":
                reasons.append("fresh_drift_failed")
            reasons = sorted(set(reasons))
            if not reasons:
                continue
            scores = route_scores(case_report)
            candidate = {
                "candidate_id": f"PTR-{family_id}-{case_id}",
                "family_id": family_id,
                "priority_backlog_id": entry.get("priority_backlog_id"),
                "case_id": case_id,
                "target_root": prompt_cases.get(case_id, {}).get("target_root"),
                "source_prompt": prompt_cases.get(case_id, {}).get("prompt"),
                "source_baseline_path": baseline_ref.get("path"),
                "source_comparison_path": comparison_ref.get("path"),
                "source_comparison_sha256": comparison_ref.get("sha256"),
                "source_prompt_case_sha256": prompt_ref.get("sha256"),
                "trigger_reasons": reasons,
                "route_scores": scores,
                "minimum_route_score": min(scores.values()) if scores else None,
                "unresolved_findings": route_findings(case_report),
                "suggestion_class": classify_suggestion(suggestion),
                "suggestion_text": suggestion,
                "decision": {
                    "status": DecisionStatus.PENDING_REVIEW.value,
                    "approval_required_before_prompt_change": True,
                    "rationale": "",
                },
                "rerun_policy": {
                    "required_after_acceptance": True,
                    "target_case_id": case_id,
                    "holdout_case_ids": family_holdouts,
                    "required_routes": ["gateway", "anythingllm"],
                },
                "applied_to_prompt_catalog": False,
            }
            if family_id in fresh_scores:
                candidate["fresh_drift_context"] = fresh_scores[family_id]
            candidates.append(candidate)
    return candidates


def expected_summary(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    by_status = {status: 0 for status in sorted(EXPECTED_DECISION_STATUSES)}
    by_reason: dict[str, int] = {}
    by_class: dict[str, int] = {}
    for candidate in candidates:
        status = dict_value(candidate.get("decision")).get("status")
        if isinstance(status, str):
            by_status[status] = by_status.get(status, 0) + 1
        for reason in string_list(candidate.get("trigger_reasons")):
            by_reason[reason] = by_reason.get(reason, 0) + 1
        suggestion_class = candidate.get("suggestion_class")
        if isinstance(suggestion_class, str):
            by_class[suggestion_class] = by_class.get(suggestion_class, 0) + 1
    return {
        "candidate_count": len(candidates),
        "decision_status_counts": dict(sorted(by_status.items())),
        "trigger_reason_counts": dict(sorted(by_reason.items())),
        "suggestion_class_counts": dict(sorted(by_class.items())),
        "applied_prompt_catalog_change_count": sum(1 for item in candidates if item.get("applied_to_prompt_catalog") is True),
    }


def build_prompt_tightening_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    baseline_corpus: dict[str, Any],
    fresh_drift_report: dict[str, Any] | None = None,
    policy_path: Path | None = None,
    baseline_corpus_path: Path | None = None,
    fresh_drift_report_path: Path | None = None,
) -> dict[str, Any]:
    candidates = generate_candidates(
        config_root=config_root,
        policy=policy,
        baseline_corpus=baseline_corpus,
        fresh_drift_report=fresh_drift_report,
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": PromptTighteningStatus.PASSED.value,
        "generated_at": utc_timestamp(),
        "policy_path": str(policy_path or DEFAULT_POLICY_PATH),
        "policy_sha256": artifact_hash(policy_path) if policy_path else None,
        "baseline_corpus_path": str(baseline_corpus_path or DEFAULT_BASELINE_CORPUS_PATH),
        "baseline_corpus_sha256": artifact_hash(baseline_corpus_path) if baseline_corpus_path else None,
        "fresh_drift_report_path": str(fresh_drift_report_path or DEFAULT_FRESH_DRIFT_REPORT_PATH),
        "fresh_drift_report_sha256": artifact_hash(fresh_drift_report_path) if fresh_drift_report_path else None,
        "low_confidence_maximum_route_score": policy.get("low_confidence_maximum_route_score"),
        "candidates": candidates,
        "summary": expected_summary(candidates),
        "errors": [],
    }
    return report


def candidate_validation_errors(
    candidate: dict[str, Any],
    *,
    prefix: str,
    baseline_entries: dict[str, dict[str, Any]],
    config_root: Path,
    policy: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    family_id = candidate.get("family_id")
    case_id = candidate.get("case_id")
    if not isinstance(family_id, str) or family_id not in baseline_entries:
        return [f"{prefix}.family_id must reference a stable baseline corpus entry"]
    entry = baseline_entries[family_id]
    prompt_ref = dict_value(entry.get("prompt_cases"))
    baseline_ref = dict_value(entry.get("blind_baselines"))
    comparison_ref = dict_value(entry.get("comparison"))
    baselines = blind_baseline_lookup(resolve_path(config_root, str(baseline_ref.get("path"))))
    prompt_cases = prompt_case_lookup(resolve_path(config_root, str(prompt_ref.get("path"))))
    baseline = baselines.get(str(case_id), {})
    prompt_case = prompt_cases.get(str(case_id), {})

    if candidate.get("priority_backlog_id") != entry.get("priority_backlog_id"):
        errors.append(f"{prefix}.priority_backlog_id must match baseline corpus")
    if candidate.get("candidate_id") != f"PTR-{family_id}-{case_id}":
        errors.append(f"{prefix}.candidate_id must be deterministic")
    if str(case_id) not in baselines:
        errors.append(f"{prefix}.case_id must exist in blind baselines")
    if str(case_id) not in prompt_cases:
        errors.append(f"{prefix}.case_id must exist in prompt cases")
    if candidate.get("source_prompt") != prompt_case.get("prompt"):
        errors.append(f"{prefix}.source_prompt must match governed prompt case")
    if candidate.get("target_root") != prompt_case.get("target_root"):
        errors.append(f"{prefix}.target_root must match governed prompt case")
    if candidate.get("suggestion_text") != baseline.get("prompt_tightening_suggestion"):
        errors.append(f"{prefix}.suggestion_text must match blind baseline prompt_tightening_suggestion")
    if candidate.get("source_baseline_path") != baseline_ref.get("path"):
        errors.append(f"{prefix}.source_baseline_path must match baseline corpus")
    if candidate.get("source_comparison_path") != comparison_ref.get("path"):
        errors.append(f"{prefix}.source_comparison_path must match baseline corpus")
    if candidate.get("source_comparison_sha256") != comparison_ref.get("sha256"):
        errors.append(f"{prefix}.source_comparison_sha256 must match baseline corpus")
    if candidate.get("source_prompt_case_sha256") != prompt_ref.get("sha256"):
        errors.append(f"{prefix}.source_prompt_case_sha256 must match baseline corpus")

    reasons = set(string_list(candidate.get("trigger_reasons")))
    if not reasons:
        errors.append(f"{prefix}.trigger_reasons is required")
    if reasons - set(string_list(policy.get("allowed_trigger_reasons"))):
        errors.append(f"{prefix}.trigger_reasons contains unsupported reason")
    if candidate.get("suggestion_class") not in set(string_list(policy.get("allowed_suggestion_classes"))):
        errors.append(f"{prefix}.suggestion_class must be governed")
    scores = dict_value(candidate.get("route_scores"))
    if not scores:
        errors.append(f"{prefix}.route_scores is required")
    elif candidate.get("minimum_route_score") != min(value for value in scores.values() if isinstance(value, int)):
        errors.append(f"{prefix}.minimum_route_score must match route_scores")
    if "low_confidence_pass" in reasons:
        min_score = candidate.get("minimum_route_score")
        if not isinstance(min_score, int) or min_score > int(policy.get("low_confidence_maximum_route_score")):
            errors.append(f"{prefix}.low_confidence_pass requires a score at or below the policy low-confidence floor")

    decision = dict_value(candidate.get("decision"))
    status = decision.get("status")
    if status not in set(string_list(policy.get("allowed_decision_statuses"))):
        errors.append(f"{prefix}.decision.status must be governed")
    if candidate.get("applied_to_prompt_catalog") is not False:
        errors.append(f"{prefix}.applied_to_prompt_catalog must be false in Phase 128")
    if "rewritten_prompt" in candidate or "applied_prompt" in candidate:
        errors.append(f"{prefix} must not include rewritten or applied prompt text")
    rerun_policy = dict_value(candidate.get("rerun_policy"))
    if rerun_policy.get("required_after_acceptance") is not True:
        errors.append(f"{prefix}.rerun_policy.required_after_acceptance must be true")
    if rerun_policy.get("target_case_id") != case_id:
        errors.append(f"{prefix}.rerun_policy.target_case_id must match case_id")
    if not string_list(rerun_policy.get("holdout_case_ids")):
        errors.append(f"{prefix}.rerun_policy.holdout_case_ids is required")
    if set(string_list(rerun_policy.get("required_routes"))) != {"gateway", "anythingllm"}:
        errors.append(f"{prefix}.rerun_policy.required_routes must include gateway and anythingllm")

    if status == DecisionStatus.ACCEPTED.value:
        approval = dict_value(candidate.get("approval"))
        rationale = decision.get("rationale")
        if not isinstance(rationale, str) or len(rationale.split()) < 4:
            errors.append(f"{prefix}.decision.rationale is required when accepted")
        if not all(isinstance(approval.get(key), str) and approval[key].strip() for key in ("approved_by", "approved_at", "approval_artifact")):
            errors.append(f"{prefix}.approval with approved_by, approved_at, and approval_artifact is required when accepted")
        rerun = dict_value(candidate.get("rerun_proof"))
        if rerun.get("status") != PromptTighteningStatus.PASSED.value:
            errors.append(f"{prefix}.rerun_proof.status must be passed when accepted")
        if rerun.get("target_case_status") != PromptTighteningStatus.PASSED.value:
            errors.append(f"{prefix}.rerun_proof.target_case_status must be passed when accepted")
        if rerun.get("holdout_status") != PromptTighteningStatus.PASSED.value:
            errors.append(f"{prefix}.rerun_proof.holdout_status must be passed when accepted")
    if status == DecisionStatus.REJECTED.value:
        rationale = decision.get("rationale")
        if not isinstance(rationale, str) or len(rationale.split()) < 4:
            errors.append(f"{prefix}.decision.rationale is required when rejected")
    if status == DecisionStatus.PENDING_REVIEW.value and candidate.get("rerun_proof"):
        errors.append(f"{prefix}.rerun_proof must not exist while pending review")
    return errors


def validate_prompt_tightening_report(
    report: dict[str, Any],
    *,
    policy: dict[str, Any],
    baseline_corpus: dict[str, Any],
    config_root: Path,
    require_artifacts: bool = False,
) -> list[str]:
    errors = validate_prompt_tightening_policy(policy)
    errors.extend(
        f"baseline_corpus: {error}"
        for error in validate_baseline_corpus(
            baseline_corpus,
            config_root=config_root,
            require_artifacts=require_artifacts,
        )
    )
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append("report.schema_version must be 1")
    if report.get("kind") != EXPECTED_REPORT_KIND:
        errors.append(f"report.kind must be {EXPECTED_REPORT_KIND}")
    if report.get("phase") != EXPECTED_PHASE:
        errors.append("report.phase must be 128")
    if report.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"report.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if report.get("low_confidence_maximum_route_score") != policy.get("low_confidence_maximum_route_score"):
        errors.append("report.low_confidence_maximum_route_score must match policy")

    baseline_entries = stable_baseline_entries(baseline_corpus)
    candidates = object_list(report.get("candidates"))
    for index, candidate in enumerate(candidates):
        errors.extend(
            candidate_validation_errors(
                candidate,
                prefix=f"report.candidates[{index}]",
                baseline_entries=baseline_entries,
                config_root=config_root,
                policy=policy,
            )
        )
    summary = dict_value(report.get("summary"))
    if summary != expected_summary(candidates):
        errors.append("report.summary must match candidates")
    if summary.get("applied_prompt_catalog_change_count") != 0:
        errors.append("report.summary.applied_prompt_catalog_change_count must be 0")
    if not candidates:
        errors.append("report.candidates must contain at least one recommendation candidate")

    expected_status = PromptTighteningStatus.PASSED.value if not errors else PromptTighteningStatus.FAILED.value
    if report.get("status") != expected_status:
        errors.append(f"report.status must be {expected_status}")
    return errors


def run_prompt_tightening_recommendation_gate(config: PromptTighteningRecommendationConfig) -> dict[str, Any]:
    config_root = config.config_root
    policy_path = resolve_path(config_root, config.policy_path)
    baseline_corpus_path = resolve_path(config_root, config.baseline_corpus_path)
    fresh_drift_report_path = resolve_path(config_root, config.fresh_drift_report_path)
    policy = read_json_object(policy_path)
    baseline_corpus = read_json_object(baseline_corpus_path)
    fresh_drift_report = read_json_object(fresh_drift_report_path) if fresh_drift_report_path.is_file() else {}
    report = build_prompt_tightening_report(
        config_root=config_root,
        policy=policy,
        baseline_corpus=baseline_corpus,
        fresh_drift_report=fresh_drift_report,
        policy_path=policy_path,
        baseline_corpus_path=baseline_corpus_path,
        fresh_drift_report_path=fresh_drift_report_path,
    )
    errors = validate_prompt_tightening_report(
        report,
        policy=policy,
        baseline_corpus=baseline_corpus,
        config_root=config_root,
        require_artifacts=config.require_artifacts,
    )
    if errors:
        report["status"] = PromptTighteningStatus.FAILED.value
        report["errors"] = errors
        errors = validate_prompt_tightening_report(
            report,
            policy=policy,
            baseline_corpus=baseline_corpus,
            config_root=config_root,
            require_artifacts=config.require_artifacts,
        )
        report["errors"] = errors
    report["summary"]["error_count"] = len(report["errors"])
    write_json(config.output_path or default_report_path(config_root), report)
    return report
