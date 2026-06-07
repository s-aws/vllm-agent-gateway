"""Bounded recursive blind-testing policy and report validation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_POLICY_PATH = Path("runtime") / "recursive_blind_testing_policy.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "recursive-blind-testing"
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
REQUIRED_FINDING_CATEGORIES = {
    "routing_miss",
    "answer_quality_miss",
    "setup_issue",
    "unsafe_behavior",
    "missing_capability",
    "roadmap_drift",
    "docs_usability",
    "output_contract_miss",
    "prompt_ambiguity",
    "overfitting_risk",
    "rejected_non_product_request",
    "unknown",
}
REQUIRED_SCENARIOS = {
    "roadmap_next_phase_audit",
    "stable_handoff_usability",
    "feedback_triage_consistency",
    "anythingllm_output_review",
    "prompt_gap_discovery",
}
VALID_SEVERITIES = {"critical", "high", "medium", "low"}
TERMINAL_CONVERGENCE_STATUSES = {"converged", "round_limit_exhausted", "deferred_scope_expansion"}
REQUIRED_SCORE_DIMENSIONS = {
    "route_workflow_skill_tool_correctness": 20,
    "evidence_grounding_and_artifact_quality": 20,
    "semantic_correctness": 20,
    "output_contract_and_chat_visible_markers": 15,
    "verification_command_relevance": 10,
    "safety_approval_and_mutation_boundary": 10,
    "diagnosability": 5,
}


class RecursiveBlindTestingStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class RecursiveBlindTestingValidationConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    report_path: Path | None = None
    output_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"recursive-blind-testing-validation-{utc_timestamp()}.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_path(config_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else config_root / path


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object at {path}")
    return value


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def check(
    check_id: str,
    status: RecursiveBlindTestingStatus,
    message: str,
    *,
    category: str,
    details: dict[str, Any] | None = None,
    next_action: str = "",
) -> dict[str, Any]:
    return {
        "id": check_id,
        "category": category,
        "status": status.value,
        "message": message,
        "details": details or {},
        "next_action": next_action,
    }


def validate_policy(policy: dict[str, Any], *, policy_path: Path) -> list[dict[str, Any]]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if policy.get("kind") != "bounded_recursive_blind_testing_policy":
        errors.append("kind must be bounded_recursive_blind_testing_policy")
    version = policy.get("version")
    if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
        errors.append("version must be semantic version x.y.z")
    context = policy.get("context_policy")
    if not isinstance(context, dict):
        errors.append("context_policy must be an object")
    else:
        if context.get("fresh_agent_each_round") is not True:
            errors.append("context_policy.fresh_agent_each_round must be true")
        if context.get("fork_context") is not False:
            errors.append("context_policy.fork_context must be false")
        if context.get("session_history_allowed") is not False:
            errors.append("context_policy.session_history_allowed must be false")
        if not string_list(context.get("allowed_inputs")):
            errors.append("context_policy.allowed_inputs must be a non-empty string array")
        if not string_list(context.get("forbidden_inputs")):
            errors.append("context_policy.forbidden_inputs must be a non-empty string array")
    limits = policy.get("round_limits")
    if not isinstance(limits, dict):
        errors.append("round_limits must be an object")
    else:
        max_rounds = limits.get("max_rounds")
        if not isinstance(max_rounds, int) or max_rounds < 1 or max_rounds > 3:
            errors.append("round_limits.max_rounds must be an integer from 1 through 3")
        max_findings = limits.get("max_findings_per_round")
        if not isinstance(max_findings, int) or max_findings < 1:
            errors.append("round_limits.max_findings_per_round must be a positive integer")
        repair_cycles = limits.get("max_repair_cycles_per_issue")
        if not isinstance(repair_cycles, int) or repair_cycles < 1 or repair_cycles > 2:
            errors.append("round_limits.max_repair_cycles_per_issue must be an integer from 1 through 2")
        accepted_changes = limits.get("max_accepted_changes_per_round")
        if not isinstance(accepted_changes, int) or accepted_changes < 1:
            errors.append("round_limits.max_accepted_changes_per_round must be a positive integer")
    adjudication = policy.get("adjudication_policy")
    if not isinstance(adjudication, dict):
        errors.append("adjudication_policy must be an object")
    else:
        if adjudication.get("blind_evaluator_is_pass_fail_authority") is not False:
            errors.append("adjudication_policy.blind_evaluator_is_pass_fail_authority must be false")
        if adjudication.get("blind_evaluator_may_propose_findings") is not True:
            errors.append("adjudication_policy.blind_evaluator_may_propose_findings must be true")
        if adjudication.get("accept_or_reject_requires_deterministic_evidence") is not True:
            errors.append("adjudication_policy.accept_or_reject_requires_deterministic_evidence must be true")
        if not string_list(adjudication.get("deterministic_evidence_sources")):
            errors.append("adjudication_policy.deterministic_evidence_sources must be a non-empty string array")
    rubric = policy.get("score_rubric")
    if not isinstance(rubric, dict):
        errors.append("score_rubric must be an object")
    else:
        total_points = rubric.get("total_points")
        if total_points != 100:
            errors.append("score_rubric.total_points must be 100")
        acceptance_minimum = rubric.get("acceptance_minimum")
        if not isinstance(acceptance_minimum, int) or acceptance_minimum < 85 or acceptance_minimum > 100:
            errors.append("score_rubric.acceptance_minimum must be an integer from 85 through 100")
        category_floor = rubric.get("category_floor")
        if not isinstance(category_floor, int) or category_floor < 70 or category_floor > 100:
            errors.append("score_rubric.category_floor must be an integer from 70 through 100")
        stable_mean = rubric.get("stable_acceptance_mean_minimum")
        if not isinstance(stable_mean, int) or stable_mean < 90 or stable_mean > 100:
            errors.append("score_rubric.stable_acceptance_mean_minimum must be an integer from 90 through 100")
        stable_case = rubric.get("stable_acceptance_case_minimum")
        if not isinstance(stable_case, int) or stable_case < 85 or stable_case > 100:
            errors.append("score_rubric.stable_acceptance_case_minimum must be an integer from 85 through 100")
        dimensions = object_list(rubric.get("dimensions"))
        points_by_id = {
            str(item.get("id")): item.get("points")
            for item in dimensions
            if isinstance(item.get("id"), str)
        }
        missing_dimensions = sorted(set(REQUIRED_SCORE_DIMENSIONS) - set(points_by_id))
        if missing_dimensions:
            errors.append(f"score_rubric.dimensions missing required ids: {missing_dimensions}")
        for dimension_id, expected_points in REQUIRED_SCORE_DIMENSIONS.items():
            actual_points = points_by_id.get(dimension_id)
            if actual_points is not None and actual_points != expected_points:
                errors.append(f"score_rubric.dimensions[{dimension_id}].points must be {expected_points}")
        numeric_points = [item.get("points") for item in dimensions if isinstance(item.get("points"), int)]
        if numeric_points and sum(numeric_points) != total_points:
            errors.append("score_rubric dimension points must sum to score_rubric.total_points")
    categories = set(string_list(policy.get("finding_categories")))
    missing_categories = sorted(REQUIRED_FINDING_CATEGORIES - categories)
    if missing_categories:
        errors.append(f"finding_categories missing required values: {missing_categories}")
    severities = set(string_list(policy.get("severity_levels")))
    missing_severities = sorted(VALID_SEVERITIES - severities)
    if missing_severities:
        errors.append(f"severity_levels missing required values: {missing_severities}")
    scenarios = {str(item.get("id")) for item in object_list(policy.get("required_scenarios"))}
    missing_scenarios = sorted(REQUIRED_SCENARIOS - scenarios)
    if missing_scenarios:
        errors.append(f"required_scenarios missing required ids: {missing_scenarios}")
    acceptance = policy.get("acceptance_rules")
    if not isinstance(acceptance, dict):
        errors.append("acceptance_rules must be an object")
    else:
        for key in (
            "accept_finding_requires_evidence",
            "accepted_finding_requires_owner",
            "accepted_finding_requires_action",
            "accepted_finding_requires_validation",
            "rejected_finding_requires_reason",
            "prompt_tweak_requires_live_proof",
            "implementation_change_requires_regression",
            "runtime_change_requires_bash_anythingllm_proof",
            "protected_fixture_change_blocks_pass",
        ):
            if acceptance.get(key) is not True:
                errors.append(f"acceptance_rules.{key} must be true")
    convergence = policy.get("convergence_criteria")
    if not isinstance(convergence, dict) or not convergence:
        errors.append("convergence_criteria must be a non-empty object")
    else:
        for key in (
            "no_unresolved_critical_or_high_findings",
            "live_validation_after_accepted_changes",
            "regression_after_code_changes",
            "fixture_state_unchanged",
        ):
            if convergence.get(key) is not True:
                errors.append(f"convergence_criteria.{key} must be true")
    stop_conditions = string_list(policy.get("stop_conditions"))
    if not stop_conditions:
        errors.append("stop_conditions must be a non-empty string array")
    return [
        check(
            "policy.contract",
            RecursiveBlindTestingStatus.PASSED if not errors else RecursiveBlindTestingStatus.FAILED,
            "Recursive blind-testing policy contract is valid."
            if not errors
            else "Recursive blind-testing policy contract is invalid.",
            category="policy",
            details={"policy_path": str(policy_path), "errors": errors},
            next_action="" if not errors else "Fix runtime/recursive_blind_testing_policy.json before using recursive blind testing.",
        )
    ]


def finding_id(value: object, index: int) -> str:
    if isinstance(value, dict) and isinstance(value.get("id"), str) and value["id"].strip():
        return value["id"]
    return f"finding_{index}"


def validate_finding_contracts(policy: dict[str, Any], report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    allowed_categories = set(string_list(policy.get("finding_categories"))) or REQUIRED_FINDING_CATEGORIES
    allowed_severities = set(string_list(policy.get("severity_levels"))) or VALID_SEVERITIES
    for round_index, round_item in enumerate(object_list(report.get("rounds"))):
        for field_name in ("blind_findings", "accepted_findings", "rejected_findings"):
            for index, finding in enumerate(object_list(round_item.get(field_name))):
                prefix = f"rounds[{round_index}].{field_name}[{finding_id(finding, index)}]"
                category = finding.get("category")
                severity = finding.get("severity")
                if category not in allowed_categories:
                    errors.append(f"{prefix}.category must be one of the policy finding_categories")
                if severity not in allowed_severities:
                    errors.append(f"{prefix}.severity must be one of the policy severity_levels")
                if field_name in {"blind_findings", "accepted_findings"} and not string_list(finding.get("evidence_refs")):
                    errors.append(f"{prefix}.evidence_refs must be non-empty")
                if field_name == "accepted_findings":
                    if not isinstance(finding.get("owner"), str) or not str(finding.get("owner")).strip():
                        errors.append(f"{prefix}.owner must be non-empty")
                    if not isinstance(finding.get("action"), str) or not str(finding.get("action")).strip():
                        errors.append(f"{prefix}.action must be non-empty")
                    if not string_list(finding.get("validation_refs")):
                        errors.append(f"{prefix}.validation_refs must be non-empty")
                if field_name == "rejected_findings" and not isinstance(finding.get("rejection_reason"), str):
                    errors.append(f"{prefix}.rejection_reason must be present")
    return errors


def unresolved_high_findings(report: dict[str, Any]) -> list[str]:
    unresolved: list[str] = []
    accepted_ids = {
        str(item.get("id"))
        for round_item in object_list(report.get("rounds"))
        for item in object_list(round_item.get("accepted_findings"))
    }
    rejected_ids = {
        str(item.get("id"))
        for round_item in object_list(report.get("rounds"))
        for item in object_list(round_item.get("rejected_findings"))
    }
    resolved_ids = accepted_ids | rejected_ids
    for round_item in object_list(report.get("rounds")):
        for index, finding in enumerate(object_list(round_item.get("blind_findings"))):
            fid = finding_id(finding, index)
            if finding.get("severity") in {"critical", "high"} and fid not in resolved_ids:
                unresolved.append(fid)
    return sorted(set(unresolved))


def validate_score_contract(policy: dict[str, Any], report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    rubric = policy.get("score_rubric") if isinstance(policy.get("score_rubric"), dict) else {}
    acceptance_minimum = rubric.get("acceptance_minimum", 85) if isinstance(rubric, dict) else 85
    category_floor = rubric.get("category_floor", 70) if isinstance(rubric, dict) else 70
    score_summary = report.get("score_summary")
    if not isinstance(score_summary, dict):
        return ["score_summary must be an object"]
    total_score = score_summary.get("total_score")
    if not isinstance(total_score, int) or total_score < 0 or total_score > 100:
        errors.append("score_summary.total_score must be an integer from 0 through 100")
    category_scores = score_summary.get("category_scores")
    if not isinstance(category_scores, dict):
        errors.append("score_summary.category_scores must be an object")
        return errors
    missing_categories = sorted(set(REQUIRED_SCORE_DIMENSIONS) - set(category_scores))
    if missing_categories:
        errors.append(f"score_summary.category_scores missing required ids: {missing_categories}")
    for category_id, category_score in category_scores.items():
        if category_id not in REQUIRED_SCORE_DIMENSIONS:
            errors.append(f"score_summary.category_scores contains unknown id: {category_id}")
        if not isinstance(category_score, int) or category_score < 0 or category_score > 100:
            errors.append(f"score_summary.category_scores[{category_id}] must be an integer from 0 through 100")
        elif isinstance(category_floor, int) and report.get("status") == "passed" and category_score < category_floor:
            errors.append(
                f"score_summary.category_scores[{category_id}] must be at least category_floor={category_floor} for passed reports"
            )
    if (
        isinstance(total_score, int)
        and isinstance(acceptance_minimum, int)
        and report.get("status") == "passed"
        and total_score < acceptance_minimum
    ):
        errors.append(
            f"score_summary.total_score must be at least acceptance_minimum={acceptance_minimum} for passed reports"
        )
    return errors


def validate_recursive_report(policy: dict[str, Any], report: dict[str, Any], *, report_path: Path) -> list[dict[str, Any]]:
    errors: list[str] = []
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if report.get("kind") != "recursive_blind_testing_report":
        errors.append("kind must be recursive_blind_testing_report")
    rounds = object_list(report.get("rounds"))
    max_rounds = policy.get("round_limits", {}).get("max_rounds") if isinstance(policy.get("round_limits"), dict) else 3
    if not rounds:
        errors.append("rounds must contain at least one round")
    if isinstance(max_rounds, int) and len(rounds) > max_rounds:
        errors.append(f"rounds exceeds policy max_rounds={max_rounds}")
    for index, round_item in enumerate(rounds):
        evaluator = round_item.get("evaluator_context")
        if not isinstance(evaluator, dict):
            errors.append(f"rounds[{index}].evaluator_context must be an object")
        elif evaluator.get("fork_context") is not False:
            errors.append(f"rounds[{index}].evaluator_context.fork_context must be false")
        if not string_list(round_item.get("input_refs")):
            errors.append(f"rounds[{index}].input_refs must be non-empty")
    errors.extend(validate_finding_contracts(policy, report))
    errors.extend(validate_score_contract(policy, report))
    convergence = report.get("convergence")
    if not isinstance(convergence, dict):
        errors.append("convergence must be an object")
    else:
        if convergence.get("status") not in TERMINAL_CONVERGENCE_STATUSES:
            errors.append(f"convergence.status must be one of {sorted(TERMINAL_CONVERGENCE_STATUSES)}")
        if not string_list(convergence.get("evidence_refs")):
            errors.append("convergence.evidence_refs must be non-empty")
        if report.get("status") == "passed" and convergence.get("status") != "converged":
            errors.append("passed recursive blind-testing reports require convergence.status=converged")
    unresolved = unresolved_high_findings(report)
    if unresolved:
        errors.append(f"critical/high blind findings must be accepted or rejected: {unresolved}")
    if report.get("status") == "passed" and errors:
        errors.append("report status cannot be passed while validation errors exist")
    return [
        check(
            "report.contract",
            RecursiveBlindTestingStatus.PASSED if not errors else RecursiveBlindTestingStatus.FAILED,
            "Recursive blind-testing report contract is valid."
            if not errors
            else "Recursive blind-testing report contract is invalid.",
            category="report",
            details={"report_path": str(report_path), "round_count": len(rounds), "errors": errors},
            next_action="" if not errors else "Fix the recursive blind-testing report before using it as phase proof.",
        )
    ]


def validate_recursive_blind_testing(config: RecursiveBlindTestingValidationConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = config.output_path or default_report_path(config_root)
    report_path = resolve_path(config_root, config.report_path) if config.report_path else None
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "recursive_blind_testing_validation_report",
        "status": RecursiveBlindTestingStatus.FAILED.value,
        "created_at": utc_timestamp(),
        "config_root": str(config_root),
        "policy_path": str(policy_path),
        "validated_report_path": str(report_path) if report_path else None,
        "checks": [],
        "summary": {},
    }
    checks: list[dict[str, Any]]
    try:
        policy = read_json_object(policy_path)
        checks = validate_policy(policy, policy_path=policy_path)
        if report_path is not None:
            recursive_report = read_json_object(report_path)
            checks.extend(validate_recursive_report(policy, recursive_report, report_path=report_path))
        else:
            checks.append(
                check(
                    "report.contract",
                    RecursiveBlindTestingStatus.SKIPPED,
                    "No recursive blind-testing report was supplied; only policy was validated.",
                    category="report",
                )
            )
    except Exception as exc:  # noqa: BLE001
        checks = [
            check(
                "validation.load",
                RecursiveBlindTestingStatus.FAILED,
                f"Recursive blind-testing validation input could not be loaded: {type(exc).__name__}: {exc}",
                category="load",
                next_action="Check the policy and report paths.",
            )
        ]
    failed_ids = [item["id"] for item in checks if item.get("status") == RecursiveBlindTestingStatus.FAILED.value]
    report["checks"] = checks
    report["summary"] = {
        "check_count": len(checks),
        "failed_check_ids": failed_ids,
        "policy_validated": any(item["id"] == "policy.contract" for item in checks),
        "report_validated": report_path is not None,
    }
    report["status"] = RecursiveBlindTestingStatus.PASSED.value if not failed_ids else RecursiveBlindTestingStatus.FAILED.value
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
