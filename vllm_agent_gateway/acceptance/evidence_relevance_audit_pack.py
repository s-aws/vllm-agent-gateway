"""Evidence relevance audit-pack validation for Phase 206."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "evidence_relevance_audit_pack_policy"
EXPECTED_REPORT_KIND = "evidence_relevance_audit_pack_report"
EXPECTED_PHASE = 206
EXPECTED_BACKLOG_ID = "P0-M4-206"
EXPECTED_MILESTONE_ID = "M4"
DEFAULT_POLICY_PATH = Path("runtime") / "evidence_relevance_audit_pack_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase206" / "phase206-evidence-relevance-audit-pack-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase206" / "phase206-evidence-relevance-audit-pack-report.md"
REQUIRED_SOURCE_REPORT_IDS = {
    "phase182_evidence_relevance_ranking_live",
    "phase205_route_stability_holdout_replay",
}


class EvidenceAuditStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class EvidenceRelevanceAuditPackConfig:
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


def validate_source_report(
    *,
    config_root: Path,
    source_spec: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    source_id = str(source_spec.get("id") or "<missing>")
    path_value = source_spec.get("path")
    if not isinstance(path_value, str) or not path_value.strip():
        return {}, [f"source_report {source_id} path must be a non-empty string"]
    path = resolve_path(config_root, path_value)
    if not path.is_file():
        return {}, [f"source_report {source_id} missing at {path}"]
    report = read_json_object(path)
    required_status = source_spec.get("required_status")
    if isinstance(required_status, str) and report.get("status") != required_status:
        errors.append(f"source_report {source_id} status expected {required_status!r} got {report.get('status')!r}")
    if "required_phase" in source_spec and report.get("phase") != source_spec.get("required_phase"):
        errors.append(f"source_report {source_id} phase expected {source_spec.get('required_phase')!r} got {report.get('phase')!r}")
    if source_spec.get("required_live") is True and report.get("live") is not True:
        errors.append(f"source_report {source_id} must be live")
    if source_spec.get("required_phase206_ready") is True:
        summary = dict_value(report.get("summary"))
        if summary.get("phase206_ready") is not True:
            errors.append(f"source_report {source_id} summary.phase206_ready must be true")
    if isinstance(report.get("errors"), list) and report.get("errors"):
        errors.append(f"source_report {source_id} must not contain errors")
    return report, errors


def source_report_proof(source_spec: dict[str, Any], report: dict[str, Any], config_root: Path) -> dict[str, Any]:
    path_value = str(source_spec.get("path") or "")
    path = resolve_path(config_root, path_value) if path_value else Path("")
    summary = dict_value(report.get("summary"))
    return {
        "id": source_spec.get("id"),
        "path": path_value,
        "exists": path.is_file(),
        "status": report.get("status"),
        "phase": report.get("phase"),
        "live": report.get("live"),
        "phase206_ready": summary.get("phase206_ready"),
        "error_count": len(report.get("errors")) if isinstance(report.get("errors"), list) else 0,
    }


def catalog_case_by_id(config_root: Path, catalog_path: str) -> dict[str, dict[str, Any]]:
    catalog = read_json_object(resolve_path(config_root, catalog_path))
    return {
        str(item.get("case_id")): item
        for item in object_list(catalog.get("cases"))
        if isinstance(item.get("case_id"), str)
    }


def phase205_case_by_catalog_case_id(config_root: Path, policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    phase205_spec = next(
        (
            spec
            for spec in object_list(policy.get("required_source_reports"))
            if spec.get("id") == "phase205_route_stability_holdout_replay"
        ),
        {},
    )
    path_value = phase205_spec.get("path")
    if not isinstance(path_value, str) or not path_value:
        return {}
    report = read_json_object(resolve_path(config_root, path_value))
    return {
        str(item.get("case_id")): item
        for item in object_list(report.get("replay_cases"))
        if isinstance(item.get("case_id"), str) and not str(item.get("case_id")).startswith("H-")
    }


def rubric_total(case: dict[str, Any]) -> int:
    baseline = dict_value(case.get("blind_baseline"))
    return sum(int_value(item.get("points")) for item in object_list(baseline.get("scoring_rubric")))


def validate_case(
    *,
    config_root: Path,
    policy: dict[str, Any],
    case: dict[str, Any],
    seen_case_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    case_id = str(case.get("case_id") or "<missing>")
    prefix = f"case {case_id}"
    if case_id in seen_case_ids:
        errors.append(f"{prefix} duplicates an earlier case_id")
    seen_case_ids.add(case_id)
    required_categories = set(string_list(policy.get("required_categories")))
    if case.get("category") not in required_categories:
        errors.append(f"{prefix} category must be one of policy.required_categories")
    if case.get("target_root") not in string_list(policy.get("required_target_roots")):
        errors.append(f"{prefix} target_root must be policy-approved")
    for key in ("source_catalog_path", "source_catalog_case_id", "prompt_family", "expected_workflow", "expected_route_rule", "prompt"):
        if not isinstance(case.get(key), str) or not str(case[key]).strip():
            errors.append(f"{prefix} {key} must be a non-empty string")
    if isinstance(case.get("source_catalog_path"), str) and isinstance(case.get("source_catalog_case_id"), str):
        try:
            catalog_case = catalog_case_by_id(config_root, str(case["source_catalog_path"])).get(str(case["source_catalog_case_id"]))
            if catalog_case is None:
                errors.append(f"{prefix} source catalog case was not found")
            else:
                if catalog_case.get("prompt") != case.get("prompt"):
                    errors.append(f"{prefix} prompt must match source catalog case prompt")
                if catalog_case.get("expected_workflow") != case.get("expected_workflow"):
                    errors.append(f"{prefix} expected_workflow must match source catalog case")
                if catalog_case.get("expected_rule") != case.get("expected_route_rule"):
                    errors.append(f"{prefix} expected_route_rule must match source catalog case")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{prefix} source catalog validation failed: {type(exc).__name__}: {exc}")
    try:
        phase205_case = phase205_case_by_catalog_case_id(config_root, policy).get(str(case.get("source_catalog_case_id")))
        if phase205_case is None:
            errors.append(f"{prefix} source catalog case missing from Phase 205 replay proof")
        elif phase205_case.get("prompt_family") != case.get("prompt_family"):
            errors.append(
                f"{prefix} prompt_family must match Phase 205 replay proof: "
                f"{phase205_case.get('prompt_family')!r} != {case.get('prompt_family')!r}"
            )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{prefix} Phase 205 replay proof validation failed: {type(exc).__name__}: {exc}")

    baseline = dict_value(case.get("blind_baseline"))
    if not baseline:
        errors.append(f"{prefix} blind_baseline must be an object")
        return errors
    for key in ("ideal_answer_shape", "must_have_evidence", "safety_boundaries", "red_flags"):
        if not string_list(baseline.get(key)):
            errors.append(f"{prefix} blind_baseline.{key} must be a non-empty string list")
    tiers = dict_value(baseline.get("evidence_tier_definitions"))
    for tier in string_list(policy.get("required_evidence_tiers")):
        if not isinstance(tiers.get(tier), str) or not tiers[tier].strip():
            errors.append(f"{prefix} evidence_tier_definitions.{tier} must be a non-empty string")
    rubric = object_list(baseline.get("scoring_rubric"))
    if not rubric:
        errors.append(f"{prefix} scoring_rubric must be a non-empty object list")
    allowed_dimensions = set(string_list(policy.get("required_scoring_dimensions")))
    for item in rubric:
        dimension = item.get("dimension")
        points = item.get("points")
        if dimension not in allowed_dimensions:
            errors.append(f"{prefix} scoring dimension {dimension!r} is not policy-approved")
        if not isinstance(points, int) or points <= 0:
            errors.append(f"{prefix} scoring dimension {dimension!r} points must be a positive integer")
    if rubric_total(case) != 100:
        errors.append(f"{prefix} scoring_rubric points must total 100")

    joined_must_have = " ".join(string_list(baseline.get("must_have_evidence"))).lower()
    joined_shape = " ".join(string_list(baseline.get("ideal_answer_shape"))).lower()
    if "line" not in joined_must_have and "line" not in joined_shape:
        errors.append(f"{prefix} must require line-level evidence or explicitly bounded no-line evidence")
    if case.get("category") == "code_investigation" and "call" not in joined_shape + joined_must_have:
        errors.append(f"{prefix} code investigation baseline must require call-chain or data-flow evidence")
    if case.get("category") == "related_test_discovery" and "test name" not in joined_must_have and "line" not in joined_must_have:
        errors.append(f"{prefix} related-test baseline must require exact test names or line references")
    if case.get("category") == "validation_command_selection" and "working" not in joined_shape + joined_must_have:
        errors.append(f"{prefix} validation-command baseline must require working-directory assumptions")
    if case.get("category") == "change_boundary_analysis" and "single-code-path" not in joined_shape + joined_must_have + " ".join(string_list(baseline.get("safety_boundaries"))).lower():
        errors.append(f"{prefix} change-boundary baseline must require single-code-path discipline")

    allowed_gap_classes = set(string_list(policy.get("allowed_gap_classes")))
    gap_records = object_list(case.get("current_gap_classifications"))
    if not gap_records:
        errors.append(f"{prefix} current_gap_classifications must be non-empty")
    for gap in gap_records:
        if gap.get("gap_class") not in allowed_gap_classes:
            errors.append(f"{prefix} gap_class {gap.get('gap_class')!r} is not policy-approved")
        if gap.get("severity") not in {"monitoring", "advisory", "blocker"}:
            errors.append(f"{prefix} gap severity must be monitoring, advisory, or blocker")
        if not isinstance(gap.get("reason"), str) or not gap["reason"].strip():
            errors.append(f"{prefix} gap reason must be a non-empty string")
    return errors


def validate_policy(policy: dict[str, Any], *, config_root: Path) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 206")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if policy.get("milestone_id") != EXPECTED_MILESTONE_ID:
        errors.append(f"policy.milestone_id must be {EXPECTED_MILESTONE_ID}")
    required_categories = set(string_list(policy.get("required_categories")))
    if required_categories != {
        "code_investigation",
        "related_test_discovery",
        "validation_command_selection",
        "change_boundary_analysis",
    }:
        errors.append("policy.required_categories must match the Phase 206 representative categories")
    cases = object_list(policy.get("cases"))
    if len(cases) < int_value(policy.get("minimum_case_count"), 4):
        errors.append("policy.cases below policy.minimum_case_count")
    case_categories = {str(item.get("category")) for item in cases if isinstance(item.get("category"), str)}
    missing_categories = sorted(required_categories - case_categories)
    if missing_categories:
        errors.append("policy.cases missing required categories: " + ", ".join(missing_categories))
    if not string_list(policy.get("required_evidence_tiers")):
        errors.append("policy.required_evidence_tiers must be non-empty")
    if not string_list(policy.get("required_scoring_dimensions")):
        errors.append("policy.required_scoring_dimensions must be non-empty")
    if not string_list(policy.get("allowed_gap_classes")):
        errors.append("policy.allowed_gap_classes must be non-empty")
    source_specs = object_list(policy.get("required_source_reports"))
    source_ids = {str(item.get("id")) for item in source_specs if isinstance(item.get("id"), str)}
    if source_ids != REQUIRED_SOURCE_REPORT_IDS:
        errors.append("policy.required_source_reports must be exactly: " + ", ".join(sorted(REQUIRED_SOURCE_REPORT_IDS)))
    for source_spec in source_specs:
        _, source_errors = validate_source_report(config_root=config_root, source_spec=source_spec)
        errors.extend(source_errors)
    seen: set[str] = set()
    for case in cases:
        errors.extend(validate_case(config_root=config_root, policy=policy, case=case, seen_case_ids=seen))
    return errors


def build_summary(policy: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    cases = object_list(policy.get("cases"))
    gap_records = [gap for case in cases for gap in object_list(case.get("current_gap_classifications"))]
    severity_counts: dict[str, int] = {}
    for gap in gap_records:
        severity = str(gap.get("severity") or "unknown")
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
    return {
        "case_count": len(cases),
        "categories": sorted({str(item.get("category")) for item in cases if isinstance(item.get("category"), str)}),
        "source_report_count": len(object_list(policy.get("required_source_reports"))),
        "gap_record_count": len(gap_records),
        "gap_severity_counts": severity_counts,
        "blocking_gap_count": severity_counts.get("blocker", 0),
        "error_count": len(errors),
        "phase207_ready": not errors and severity_counts.get("blocker", 0) == 0,
    }


def source_report_proofs(config_root: Path, policy: dict[str, Any]) -> list[dict[str, Any]]:
    proofs: list[dict[str, Any]] = []
    for source_spec in object_list(policy.get("required_source_reports")):
        try:
            report, _ = validate_source_report(config_root=config_root, source_spec=source_spec)
            proofs.append(source_report_proof(source_spec, report, config_root))
        except Exception as exc:  # noqa: BLE001
            proofs.append(
                {
                    "id": source_spec.get("id"),
                    "path": source_spec.get("path"),
                    "exists": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return proofs


def validate_evidence_relevance_audit_pack(config: EvidenceRelevanceAuditPackConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path)
    errors: list[str] = []
    policy: dict[str, Any] = {}
    try:
        policy = read_json_object(policy_path)
        errors.extend(validate_policy(policy, config_root=config_root))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"load failed: {type(exc).__name__}: {exc}")
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_id": EXPECTED_MILESTONE_ID,
        "status": EvidenceAuditStatus.PASSED.value if not errors else EvidenceAuditStatus.FAILED.value,
        "created_at": utc_timestamp(),
        "policy_path": str(policy_path),
        "summary": build_summary(policy, errors),
        "source_report_proofs": source_report_proofs(config_root, policy) if policy else [],
        "audit_cases": object_list(policy.get("cases")) if policy else [],
        "errors": errors,
    }
    write_json(output_path, report)
    write_text(markdown_output_path, markdown_report(report))
    report["report_path"] = str(output_path.resolve())
    report["markdown_report_path"] = str(markdown_output_path.resolve())
    write_json(output_path, report)
    return report


def markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Evidence Relevance Audit Pack",
        "",
        f"- Status: {report.get('status')}",
        f"- Cases: {summary.get('case_count')}",
        f"- Categories: {', '.join(string_list(summary.get('categories')))}",
        f"- Source reports: {summary.get('source_report_count')}",
        f"- Gap records: {summary.get('gap_record_count')}",
        f"- Blocking gaps: {summary.get('blocking_gap_count')}",
        f"- Phase 207 ready: {summary.get('phase207_ready')}",
        "",
        "## Source Reports",
        "",
        "| Source | Status | Phase | Live | Phase 207 Input | Errors |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for proof in object_list(report.get("source_report_proofs")):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(proof.get("id")),
                    str(proof.get("status")),
                    str(proof.get("phase")),
                    str(proof.get("live")),
                    str(proof.get("phase206_ready")),
                    str(proof.get("error_count")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
        "## Cases",
        "",
        "| Case | Category | Prompt Family | Gap Count |",
        "| --- | --- | --- | --- |",
        ]
    )
    for case in object_list(report.get("audit_cases")):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(case.get("case_id")),
                    str(case.get("category")),
                    str(case.get("prompt_family")),
                    str(len(object_list(case.get("current_gap_classifications")))),
                ]
            )
            + " |"
        )
    if report.get("errors"):
        lines.extend(["", "## Errors", ""])
        for error in string_list(report.get("errors")):
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"
