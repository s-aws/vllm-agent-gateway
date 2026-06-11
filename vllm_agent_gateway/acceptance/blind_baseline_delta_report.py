"""Phase 178 blind-baseline delta report governance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "blind_baseline_delta_report_policy"
EXPECTED_REPORT_KIND = "blind_baseline_delta_report"
EXPECTED_ROUND2_KIND = "founder_field_round2_report"
EXPECTED_FIELD_KIND = "founder_field_prompt_evaluation"
EXPECTED_BASELINE_KIND = "founder_field_round2_blind_baselines"
EXPECTED_PHASE = 178
EXPECTED_BACKLOG_ID = "P0-BB-042"
DEFAULT_POLICY_PATH = Path("runtime") / "blind_baseline_delta_report_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase178" / "phase178-blind-baseline-delta-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase178" / "phase178-blind-baseline-delta-report.md"
REQUIRED_DIMENSIONS = [
    "routing",
    "evidence",
    "correctness",
    "completeness",
    "format",
    "user_visible_usefulness",
]


class BlindBaselineDeltaStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class BlindBaselineDeltaReportConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path | None = DEFAULT_MARKDOWN_OUTPUT_PATH


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


def sortable_timestamp(value: object) -> str:
    return str(value or "")


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 178")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if string_list(policy.get("required_dimensions")) != REQUIRED_DIMENSIONS:
        errors.append("policy.required_dimensions must match the Phase 178 dimension contract")
    required_case_ids = string_list(policy.get("required_case_ids"))
    if not required_case_ids:
        errors.append("policy.required_case_ids must be non-empty")
    if len(required_case_ids) != len(set(required_case_ids)):
        errors.append("policy.required_case_ids must be unique")
    grouped_ids: set[str] = set()
    for index, group in enumerate(object_list(policy.get("case_groups"))):
        prefix = f"policy.case_groups[{index}]"
        family = str(group.get("family") or "")
        target_ids = string_list(group.get("target_case_ids"))
        holdout_ids = string_list(group.get("holdout_case_ids"))
        if not family:
            errors.append(f"{prefix}.family is required")
        if not target_ids:
            errors.append(f"{prefix}.target_case_ids must be non-empty")
        if not holdout_ids:
            errors.append(f"{prefix}.holdout_case_ids must be non-empty")
        grouped_ids.update(target_ids)
        grouped_ids.update(holdout_ids)
    if set(required_case_ids) != grouped_ids:
        errors.append("policy.required_case_ids must match case group target and holdout IDs")
    if not isinstance(policy.get("minimum_score"), int) or int(policy.get("minimum_score")) < 85:
        errors.append("policy.minimum_score must be an integer >= 85")
    if policy.get("required_route_surface") != "anythingllm_via_workflow_router_gateway":
        errors.append("policy.required_route_surface must be anythingllm_via_workflow_router_gateway")
    if policy.get("acceptance_marker") != "PHASE178 BLIND BASELINE DELTA REPORT PASS":
        errors.append("policy.acceptance_marker must be PHASE178 BLIND BASELINE DELTA REPORT PASS")
    return errors


def build_case_contexts(policy: dict[str, Any]) -> list[dict[str, str]]:
    contexts: list[dict[str, str]] = []
    for group in object_list(policy.get("case_groups")):
        family = str(group.get("family") or "")
        for case_id in string_list(group.get("target_case_ids")):
            contexts.append({"case_id": case_id, "family": family, "role": "target"})
        for case_id in string_list(group.get("holdout_case_ids")):
            contexts.append({"case_id": case_id, "family": family, "role": "holdout"})
    return contexts


def dimension_status(case: dict[str, Any], minimum_score: int) -> dict[str, dict[str, Any]]:
    breakdown = dict_value(case.get("score_breakdown"))
    score = int(case.get("score") or 0)
    evidence_score = int(breakdown.get("evidence") or 0)
    return {
        "routing": {
            "status": "passed" if int(breakdown.get("routing") or 0) >= 20 else "failed",
            "score": int(breakdown.get("routing") or 0),
        },
        "evidence": {
            "status": "passed" if evidence_score >= 20 else "advisory" if evidence_score >= 14 else "failed",
            "score": evidence_score,
        },
        "correctness": {
            "status": "passed" if case.get("status") == "passed" and case.get("semantic_quality_status") == "passed" else "failed",
        },
        "completeness": {
            "status": "passed" if int(breakdown.get("answer_completeness") or 0) >= 30 else "failed",
            "score": int(breakdown.get("answer_completeness") or 0),
        },
        "format": {
            "status": "passed" if case.get("output_contract_status") == "passed" else "failed",
        },
        "user_visible_usefulness": {
            "status": "passed" if score >= minimum_score and case.get("response_artifact_path") else "failed",
            "score": score,
        },
    }


def classify_gaps(dimensions: dict[str, dict[str, Any]], case: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    if dimensions["routing"]["status"] == "failed":
        gaps.append("routing_miss")
    if dimensions["correctness"]["status"] == "failed":
        gaps.append("correctness_miss")
    if dimensions["completeness"]["status"] == "failed":
        gaps.append("completeness_miss")
    if dimensions["format"]["status"] == "failed":
        gaps.append("format_miss")
    if dimensions["user_visible_usefulness"]["status"] == "failed":
        gaps.append("usefulness_miss")
    if dimensions["evidence"]["status"] == "failed":
        gaps.append("evidence_miss")
    elif dimensions["evidence"]["status"] == "advisory":
        gaps.append("evidence_detail_advisory")
    if str(case.get("prompt_risk") or "").strip():
        gaps.append("prompt_wording_advisory")
    return gaps or ["none"]


def next_action_for_gap_classes(gap_classes: list[str]) -> str:
    blocking = {"routing_miss", "correctness_miss", "completeness_miss", "format_miss", "usefulness_miss", "evidence_miss"}
    if any(item in blocking for item in gap_classes):
        return "create roadmap proposal before repair"
    if gap_classes == ["none"]:
        return "no repair needed"
    return "monitor advisory; use existing refined prompt guidance when needed"


def validate_sources(
    *,
    config_root: Path,
    policy: dict[str, Any],
    round2_report: dict[str, Any],
    field_report: dict[str, Any],
    baseline_package: dict[str, Any],
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    errors.extend({"id": f"policy.{index}", "severity": "high", "message": error} for index, error in enumerate(validate_policy(policy)))
    if round2_report.get("kind") != EXPECTED_ROUND2_KIND:
        errors.append({"id": "round2.kind", "severity": "high", "message": f"round2 report kind must be {EXPECTED_ROUND2_KIND}"})
    if round2_report.get("status") != "passed":
        errors.append({"id": "round2.status", "severity": "high", "message": "round2 report must pass"})
    if field_report.get("kind") != EXPECTED_FIELD_KIND:
        errors.append({"id": "field.kind", "severity": "high", "message": f"field report kind must be {EXPECTED_FIELD_KIND}"})
    if field_report.get("status") != "passed":
        errors.append({"id": "field.status", "severity": "high", "message": "field report must pass"})
    if field_report.get("fixture_state_before") != field_report.get("fixture_state_after"):
        errors.append({"id": "field.fixture_state", "severity": "critical", "message": "field report must prove unchanged fixtures"})
    if baseline_package.get("kind") != EXPECTED_BASELINE_KIND:
        errors.append({"id": "baseline.kind", "severity": "high", "message": f"baseline package kind must be {EXPECTED_BASELINE_KIND}"})
    if baseline_package.get("local_model_output_seen_by_blind_agent") is not False:
        errors.append({"id": "baseline.local_output_seen", "severity": "critical", "message": "blind baseline must be collected before local output"})
    if sortable_timestamp(baseline_package.get("generated_at")) > sortable_timestamp(field_report.get("created_at")):
        errors.append({"id": "baseline.generated_at", "severity": "high", "message": "blind baseline must predate local field run"})

    required_case_ids = set(string_list(policy.get("required_case_ids")))
    round_cases = {str(item.get("case_id")): item for item in object_list(round2_report.get("case_evidence"))}
    field_cases = {str(item.get("case_id")): item for item in object_list(field_report.get("cases"))}
    baseline_cases = {str(item.get("case_id")): item for item in object_list(baseline_package.get("cases"))}
    for case_id in sorted(required_case_ids):
        if case_id not in round_cases:
            errors.append({"id": f"round2.{case_id}", "severity": "high", "message": "required case missing from round2 report"})
            continue
        if case_id not in field_cases:
            errors.append({"id": f"field.{case_id}", "severity": "high", "message": "required case missing from field report"})
        if case_id not in baseline_cases:
            errors.append({"id": f"baseline.{case_id}", "severity": "high", "message": "required case missing from blind baseline package"})
        case = round_cases[case_id]
        if case.get("route_surface") != policy.get("required_route_surface"):
            errors.append({"id": f"round2.{case_id}.route_surface", "severity": "high", "message": "case route surface must use AnythingLLM through workflow-router"})
        comparison = dict_value(case.get("blind_baseline_comparison"))
        for key in ("ideal_answer_shape", "must_have_facts", "evidence_expectations", "safety_boundaries", "output_expectations"):
            if not comparison.get(key):
                errors.append({"id": f"round2.{case_id}.baseline.{key}", "severity": "high", "message": "case must include blind-baseline comparison detail"})
        response_path_value = case.get("response_artifact_path")
        if not isinstance(response_path_value, str) or not response_path_value:
            errors.append({"id": f"round2.{case_id}.response_artifact_path", "severity": "high", "message": "case must include local answer artifact path"})
        else:
            response_path = resolve_path(config_root, response_path_value)
            if not response_path.is_file():
                errors.append({"id": f"round2.{case_id}.response_artifact_missing", "severity": "high", "message": "local answer artifact must exist"})
            elif case.get("response_artifact_sha256") != sha256_file(response_path):
                errors.append({"id": f"round2.{case_id}.response_artifact_sha256", "severity": "high", "message": "local answer artifact hash mismatch"})
    return errors


def build_blind_baseline_delta_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    round2_report: dict[str, Any],
    field_report: dict[str, Any],
    baseline_package: dict[str, Any],
    policy_path: Path | None = None,
    round2_report_path: Path | None = None,
    field_report_path: Path | None = None,
    baseline_path: Path | None = None,
) -> dict[str, Any]:
    errors = validate_sources(
        config_root=config_root,
        policy=policy,
        round2_report=round2_report,
        field_report=field_report,
        baseline_package=baseline_package,
    )
    minimum_score = int(policy.get("minimum_score") or 85)
    round_cases = {str(item.get("case_id")): item for item in object_list(round2_report.get("case_evidence"))}
    contexts = build_case_contexts(policy)
    deltas: list[dict[str, Any]] = []
    backlog_candidates: list[dict[str, Any]] = []
    for context in contexts:
        case = round_cases.get(context["case_id"], {})
        dimensions = dimension_status(case, minimum_score)
        gap_classes = classify_gaps(dimensions, case)
        next_action = next_action_for_gap_classes(gap_classes)
        delta = {
            "case_id": context["case_id"],
            "family": context["family"],
            "role": context["role"],
            "target_root": case.get("target_root"),
            "baseline_before_local": baseline_package.get("local_model_output_seen_by_blind_agent") is False,
            "baseline_ideal_answer_shape": dict_value(case.get("blind_baseline_comparison")).get("ideal_answer_shape"),
            "baseline_must_have_facts": dict_value(case.get("blind_baseline_comparison")).get("must_have_facts"),
            "local_answer_path": case.get("response_artifact_path"),
            "local_answer_sha256": case.get("response_artifact_sha256"),
            "run_id": case.get("run_id"),
            "route_surface": case.get("route_surface"),
            "expected_workflow": case.get("expected_workflow"),
            "expected_skill_id": case.get("expected_skill_id") or "",
            "score": int(case.get("score") or 0),
            "score_breakdown": case.get("score_breakdown"),
            "quality_classification": case.get("quality_classification"),
            "dimensions": dimensions,
            "gap_classes": gap_classes,
            "initial_difference": case.get("initial_difference") or "",
            "prompt_risk": case.get("prompt_risk") or "",
            "suggested_prompt_if_missed": case.get("suggested_prompt_if_missed") or "",
            "next_action": next_action,
        }
        deltas.append(delta)
        if next_action == "create roadmap proposal before repair":
            backlog_candidates.append(
                {
                    "case_id": context["case_id"],
                    "family": context["family"],
                    "gap_classes": gap_classes,
                    "recommended_phase_type": "Priority 0 repair proposal",
                }
            )
    blocking_count = len(backlog_candidates)
    unique_cases = sorted({item["case_id"] for item in deltas})
    status = BlindBaselineDeltaStatus.FAILED.value if errors or blocking_count else BlindBaselineDeltaStatus.PASSED.value
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": status,
        "generated_at": utc_timestamp(),
        "policy_path": str(policy_path.resolve()) if policy_path else None,
        "policy_sha256": artifact_hash(policy_path),
        "source_round2_report_path": str(round2_report_path.resolve()) if round2_report_path else None,
        "source_round2_report_sha256": artifact_hash(round2_report_path),
        "source_field_report_path": str(field_report_path.resolve()) if field_report_path else None,
        "source_field_report_sha256": artifact_hash(field_report_path),
        "source_baseline_path": str(baseline_path.resolve()) if baseline_path else None,
        "source_baseline_sha256": artifact_hash(baseline_path),
        "deltas": deltas,
        "backlog_candidates": backlog_candidates,
        "summary": {
            "delta_count": len(deltas),
            "unique_case_count": len(unique_cases),
            "families": sorted({item["family"] for item in deltas}),
            "required_case_ids": string_list(policy.get("required_case_ids")),
            "minimum_score": minimum_score,
            "min_score": min((int(item.get("score") or 0) for item in deltas), default=0),
            "average_score": round(sum(int(item.get("score") or 0) for item in deltas) / len(deltas), 2) if deltas else 0,
            "blocking_gap_count": blocking_count,
            "advisory_delta_count": sum(1 for item in deltas if item.get("gap_classes") != ["none"]),
            "validation_error_count": len(errors),
            "next_action": "work Phase 179 next" if not errors and not blocking_count else "convert blocking gaps into roadmap proposals",
        },
        "validation_errors": errors,
    }


def validate_blind_baseline_delta_report(
    report: dict[str, Any],
    *,
    config_root: Path,
    policy: dict[str, Any],
    round2_report: dict[str, Any],
    field_report: dict[str, Any],
    baseline_package: dict[str, Any],
    policy_path: Path | None = None,
    round2_report_path: Path | None = None,
    field_report_path: Path | None = None,
    baseline_path: Path | None = None,
) -> list[str]:
    expected = build_blind_baseline_delta_report(
        config_root=config_root,
        policy=policy,
        round2_report=round2_report,
        field_report=field_report,
        baseline_package=baseline_package,
        policy_path=policy_path,
        round2_report_path=round2_report_path,
        field_report_path=field_report_path,
        baseline_path=baseline_path,
    )
    errors: list[str] = []
    for key in (
        "schema_version",
        "kind",
        "phase",
        "priority_backlog_id",
        "status",
        "policy_path",
        "policy_sha256",
        "source_round2_report_path",
        "source_round2_report_sha256",
        "source_field_report_path",
        "source_field_report_sha256",
        "source_baseline_path",
        "source_baseline_sha256",
        "deltas",
        "backlog_candidates",
        "summary",
        "validation_errors",
    ):
        if report.get(key) != expected.get(key):
            errors.append("report must match rebuilt blind-baseline delta report")
            break
    return errors


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Blind-Baseline Delta Report",
        "",
        f"- Status: {report['status']}",
        f"- Delta count: {report['summary']['delta_count']}",
        f"- Unique cases: {report['summary']['unique_case_count']}",
        f"- Minimum score: {report['summary']['min_score']}",
        f"- Average score: {report['summary']['average_score']}",
        f"- Blocking gaps: {report['summary']['blocking_gap_count']}",
        f"- Next action: {report['summary']['next_action']}",
        "",
        "## Deltas",
        "",
        "| Family | Role | Case | Score | Gaps | Next Action | Local Answer |",
        "| --- | --- | --- | ---: | --- | --- | --- |",
    ]
    for item in object_list(report.get("deltas")):
        gaps = ", ".join(string_list(item.get("gap_classes")))
        lines.append(
            f"| {item.get('family')} | {item.get('role')} | {item.get('case_id')} | {item.get('score')} | "
            f"{gaps} | {item.get('next_action')} | {item.get('local_answer_path')} |"
        )
    if report.get("backlog_candidates"):
        lines.extend(["", "## Backlog Candidates", ""])
        for item in object_list(report.get("backlog_candidates")):
            lines.append(f"- {item.get('case_id')}: {', '.join(string_list(item.get('gap_classes')))}")
    if report.get("validation_errors"):
        lines.extend(["", "## Validation Errors", ""])
        for error in object_list(report.get("validation_errors")):
            lines.append(f"- `{error.get('id')}`: {error.get('message')}")
    write_text(path, "\n".join(lines) + "\n")


def run_blind_baseline_delta_report(config: BlindBaselineDeltaReportConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    round2_report_path = resolve_path(config_root, str(policy.get("source_round2_report_path") or ""))
    field_report_path = resolve_path(config_root, str(policy.get("source_field_report_path") or ""))
    baseline_path = resolve_path(config_root, str(policy.get("source_blind_baseline_path") or ""))
    report = build_blind_baseline_delta_report(
        config_root=config_root,
        policy=policy,
        round2_report=read_json_object(round2_report_path),
        field_report=read_json_object(field_report_path),
        baseline_package=read_json_object(baseline_path),
        policy_path=policy_path,
        round2_report_path=round2_report_path,
        field_report_path=field_report_path,
        baseline_path=baseline_path,
    )
    validation_errors = validate_blind_baseline_delta_report(
        report,
        config_root=config_root,
        policy=policy,
        round2_report=read_json_object(round2_report_path),
        field_report=read_json_object(field_report_path),
        baseline_package=read_json_object(baseline_path),
        policy_path=policy_path,
        round2_report_path=round2_report_path,
        field_report_path=field_report_path,
        baseline_path=baseline_path,
    )
    if validation_errors:
        report["status"] = BlindBaselineDeltaStatus.FAILED.value
        report["validation_errors"] = object_list(report.get("validation_errors")) + [
            {"id": f"report.{index}", "severity": "high", "message": error} for index, error in enumerate(validation_errors)
        ]
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
    output_path = resolve_path(config_root, config.output_path)
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    if config.markdown_output_path:
        markdown_path = resolve_path(config_root, config.markdown_output_path)
        write_markdown(markdown_path, report)
        report["markdown_path"] = str(markdown_path.resolve())
        write_json(output_path, report)
    return report
