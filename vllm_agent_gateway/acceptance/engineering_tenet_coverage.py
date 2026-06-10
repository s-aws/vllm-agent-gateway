"""Engineering tenet coverage matrix validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_MATRIX_PATH = Path("runtime") / "engineering_tenet_coverage.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "engineering-tenet-coverage"
DEFAULT_WORKFLOWS_PATH = Path("runtime") / "workflows.json"
DEFAULT_TOOLS_PATH = Path("runtime") / "tools.json"
DEFAULT_SKILLS_PATH = Path("runtime") / "skills.json"
DEFAULT_SKILL_EVALS_PATH = Path("runtime") / "skill_evals.json"
DEFAULT_FOUNDER_FIELD_CATALOG_PATH = Path("runtime") / "prompt_catalogs" / "founder_field_v1.json"
DEFAULT_SEMI_WELL_DEFINED_CATALOG_PATH = Path("runtime") / "prompt_catalogs" / "semi_well_defined_v1.json"

KNOWN_EXTERNAL_EVAL_IDS = {
    "controlled_apply_disposable_copy",
    "phase111_closed_loop_eval_repair",
    "phase116_code_quality",
    "phase117_defect_diagnosis",
    "phase118_engineering_judgment",
    "phase119_delivery_mentorship",
    "release_adherence",
    "runtime_state_hygiene",
    "requirements_translation_live",
    "requirements_translation_phase114_cases",
    "incremental_implementation_live",
    "incremental_implementation_phase115_cases",
    "task_decomposition_advanced_refactor_deferred",
    "task_decomposition_ambiguous",
    "task_decomposition_oversized",
    "task_decomposition_phase113_cases",
    "task_decomposition_quality",
    "task_decomposition_live",
}


EXPECTED_TENETS: dict[str, str] = {
    "T01": "I can consistently decompose a feature, bug, or requirement into tasks that can be completed, tested, and reviewed independently within a short development cycle.",
    "T02": "I can identify tasks that remain ambiguous, high-risk, or oversized and further decompose them until implementation scope, acceptance criteria, and dependencies are clear.",
    "T03": "I can define objective acceptance criteria before implementation begins and use those criteria to determine when work is complete.",
    "T04": "I can translate business requirements into technical requirements without introducing unnecessary complexity or assumptions.",
    "T05": "I can estimate development effort using documented assumptions and revise estimates when new information changes scope.",
    "T06": "I can implement changes incrementally, ensuring that each change produces a functional and testable outcome.",
    "T07": "I can use version control according to industry standards, including meaningful commits, isolated changesets, and traceable change history.",
    "T08": "I can review my own code against established coding standards before requesting peer review.",
    "T09": "I can identify common code quality issues such as duplication, excessive complexity, poor naming, and tight coupling, and remediate them before deployment.",
    "T10": "I can write and maintain automated tests that validate expected behavior, edge cases, and regression scenarios for the code I develop.",
    "T11": "I can determine the appropriate testing level, such as unit, integration, end-to-end, or manual validation, for a given change and justify that decision.",
    "T12": "I can reproduce reported defects reliably, isolate root causes, and verify that implemented fixes resolve the issue without introducing regressions.",
    "T13": "I can use logs, debugging tools, and observability data to diagnose failures rather than relying on assumptions.",
    "T14": "I can evaluate whether a solution is simpler, more maintainable, and more testable than available alternatives before implementation.",
    "T15": "I can identify technical debt created during development and document remediation work separately from feature delivery.",
    "T16": "I can communicate implementation plans, risks, blockers, and tradeoffs in a manner that allows other engineers to understand and validate my approach.",
    "T17": "I can participate in code reviews by providing actionable feedback focused on correctness, maintainability, testability, and system impact.",
    "T18": "I can explain the reasoning behind architectural and implementation decisions using established engineering principles rather than personal preference.",
    "T19": "I can independently deliver small-to-medium features from requirement intake through deployment while maintaining quality and testing standards.",
    "T20": "I can mentor less experienced engineers on task decomposition, testing strategy, debugging methodology, code quality practices, and development workflows.",
}


class TenetCoverageStatus(str, Enum):
    COVERED = "covered"
    PARTIALLY_COVERED = "partially_covered"
    NOT_COVERED = "not_covered"
    NOT_APPLICABLE_YET = "not_applicable_yet"


class ValidationTier(str, Enum):
    GATEWAY = "gateway"
    ANYTHINGLLM_API = "anythingllm_api"
    UI = "ui"
    FIXTURE_MUTATION = "fixture_mutation"
    RELEASE_ADHERENCE = "release_adherence"
    CONTEXTLESS_AUDIT = "contextless_audit"


@dataclass(frozen=True)
class EngineeringTenetCoverageConfig:
    config_root: Path
    matrix_path: Path = DEFAULT_MATRIX_PATH
    output_path: Path | None = None
    markdown_output_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"engineering-tenet-coverage-{utc_timestamp()}.json"


def markdown_path_for(path: Path) -> Path:
    return path.with_suffix(".md")


def resolve_path(config_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else config_root / path


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object at {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def ids_from_named_list(config_root: Path, path: Path, list_key: str) -> set[str]:
    data = read_json_object(resolve_path(config_root, path))
    return {
        str(item.get("id") or item.get("skill_id"))
        for item in object_list(data.get(list_key))
        if str(item.get("id") or item.get("skill_id") or "").strip()
    }


def skill_eval_ids(config_root: Path) -> set[str]:
    data = read_json_object(resolve_path(config_root, DEFAULT_SKILL_EVALS_PATH))
    return {str(item.get("id")) for item in object_list(data.get("cases")) if str(item.get("id") or "").strip()}


def prompt_catalog_eval_ids(config_root: Path, path: Path) -> set[str]:
    data = read_json_object(resolve_path(config_root, path))
    catalog_id = str(data.get("catalog_id") or resolve_path(config_root, path).stem)
    return {
        f"{catalog_id}:{item.get('case_id')}"
        for item in object_list(data.get("cases"))
        if str(item.get("case_id") or "").strip()
    }


def known_eval_ids(config_root: Path) -> set[str]:
    return (
        skill_eval_ids(config_root)
        | prompt_catalog_eval_ids(config_root, DEFAULT_FOUNDER_FIELD_CATALOG_PATH)
        | prompt_catalog_eval_ids(config_root, DEFAULT_SEMI_WELL_DEFINED_CATALOG_PATH)
        | KNOWN_EXTERNAL_EVAL_IDS
    )


def validation_references(config_root: Path) -> dict[str, set[str]]:
    return {
        "workflows": ids_from_named_list(config_root, DEFAULT_WORKFLOWS_PATH, "workflows"),
        "tools": ids_from_named_list(config_root, DEFAULT_TOOLS_PATH, "tools"),
        "skills": ids_from_named_list(config_root, DEFAULT_SKILLS_PATH, "skills"),
        "eval_cases": known_eval_ids(config_root),
    }


def has_advanced_refactor_dependency(item: dict[str, Any]) -> bool:
    terms = ("advanced_refactor", "advanced-refactor", "advanced refactor")
    dependencies = " ".join(string_list(item.get("dependencies"))).lower()
    return any(term in dependencies for term in terms)


def validate_entry(item: dict[str, Any], index: int, *, config_root: Path | None = None, references: dict[str, set[str]] | None = None) -> list[str]:
    errors: list[str] = []
    prefix = f"entries[{item.get('tenet_id') or index}]"
    tenet_id = item.get("tenet_id")
    if tenet_id not in EXPECTED_TENETS:
        errors.append(f"{prefix}.tenet_id must be one of the expected tenet IDs")
    elif item.get("tenet") != EXPECTED_TENETS[tenet_id]:
        errors.append(f"{prefix}.tenet must exactly match Local Model Engineering Tenets")
    status = item.get("status")
    if status not in {value.value for value in TenetCoverageStatus}:
        errors.append(f"{prefix}.status must be a supported coverage status")
    tier = item.get("minimum_live_validation_tier")
    if tier not in {value.value for value in ValidationTier}:
        errors.append(f"{prefix}.minimum_live_validation_tier must be a supported validation tier")
    list_fields = (
        "current_workflows",
        "skills",
        "tools",
        "eval_cases",
        "live_validators",
        "known_gaps",
        "chat_visible_evidence",
        "contextless_audit_criteria",
        "future_phase_ids",
        "dependencies",
    )
    for field in list_fields:
        if not isinstance(item.get(field), list):
            errors.append(f"{prefix}.{field} must be a list")
        elif any(not isinstance(value, str) or not value.strip() for value in item[field]):
            errors.append(f"{prefix}.{field} must contain only non-empty strings")
    if config_root is not None and references is not None:
        for field, reference_key in (
            ("current_workflows", "workflows"),
            ("skills", "skills"),
            ("tools", "tools"),
            ("eval_cases", "eval_cases"),
        ):
            allowed = references.get(reference_key, set())
            unknown = sorted(set(string_list(item.get(field))) - allowed)
            if unknown:
                errors.append(f"{prefix}.{field} contains unknown reference(s): " + ", ".join(unknown))
        for script_path in string_list(item.get("live_validators")):
            resolved = resolve_path(config_root, Path(script_path))
            if not resolved.is_file():
                errors.append(f"{prefix}.live_validators path does not exist: {script_path}")
    if has_advanced_refactor_dependency(item):
        errors.append(f"{prefix}.dependencies must not require unapproved advanced-refactor work")
    if status in {TenetCoverageStatus.COVERED.value, TenetCoverageStatus.PARTIALLY_COVERED.value}:
        if not (string_list(item.get("current_workflows")) or string_list(item.get("skills")) or string_list(item.get("tools"))):
            errors.append(f"{prefix} covered entries must map to at least one workflow, skill, or tool")
        if not string_list(item.get("eval_cases")):
            errors.append(f"{prefix} covered entries must map to eval cases")
        if not string_list(item.get("live_validators")):
            errors.append(f"{prefix} covered entries must map to live validators")
        if not string_list(item.get("chat_visible_evidence")):
            errors.append(f"{prefix} covered entries must define chat-visible evidence")
        if not string_list(item.get("contextless_audit_criteria")):
            errors.append(f"{prefix} covered entries must define contextless audit criteria")
    if status in {TenetCoverageStatus.NOT_COVERED.value, TenetCoverageStatus.NOT_APPLICABLE_YET.value}:
        if not string_list(item.get("known_gaps")):
            errors.append(f"{prefix} uncovered entries must define known gaps")
        if not string_list(item.get("future_phase_ids")):
            errors.append(f"{prefix} uncovered entries must map to future phases")
        if not string_list(item.get("contextless_audit_criteria")):
            errors.append(f"{prefix} uncovered entries must define audit criteria")
    return errors


def validate_matrix(matrix: dict[str, Any], config_root: Path | None = None) -> list[str]:
    errors: list[str] = []
    references: dict[str, set[str]] | None = None
    if config_root is not None:
        try:
            references = validation_references(config_root)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"registry reference loading failed: {type(exc).__name__}: {exc}")
    if matrix.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if matrix.get("kind") != "engineering_tenet_coverage_matrix":
        errors.append("kind must be engineering_tenet_coverage_matrix")
    if not isinstance(matrix.get("matrix_id"), str) or not matrix["matrix_id"].strip():
        errors.append("matrix_id must be non-empty")
    entries = matrix.get("entries")
    if not isinstance(entries, list):
        errors.append("entries must be a list")
        return errors
    seen: set[str] = set()
    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            errors.append(f"entries[{index}] must be an object")
            continue
        tenet_id = str(item.get("tenet_id") or "")
        if tenet_id in seen:
            errors.append(f"entries[{tenet_id}].tenet_id is duplicated")
        seen.add(tenet_id)
        errors.extend(validate_entry(item, index, config_root=config_root, references=references))
    expected_ids = set(EXPECTED_TENETS)
    missing = sorted(expected_ids - seen)
    unknown = sorted(seen - expected_ids)
    if missing:
        errors.append("missing tenet IDs: " + ", ".join(missing))
    if unknown:
        errors.append("unknown tenet IDs: " + ", ".join(unknown))
    return errors


def status_counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts = {value.value: 0 for value in TenetCoverageStatus}
    for item in entries:
        status = str(item.get("status") or "")
        counts[status] = counts.get(status, 0) + 1
    return counts


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Engineering Tenet Coverage Report",
        "",
        f"- Status: {report['status']}",
        f"- Created at: {report['created_at']}",
        f"- Matrix path: {report['matrix_path']}",
        f"- Tenet count: {report['summary']['tenet_count']}",
        "",
        "## Status Counts",
        "",
        "| Status | Count |",
        "| --- | ---: |",
    ]
    for status, count in report["summary"]["status_counts"].items():
        lines.append(f"| {status} | {count} |")
    lines.extend(["", "## Entries", "", "| Tenet | Status | Tier | Evidence | Gaps |", "| --- | --- | --- | --- | --- |"])
    for item in report["entries"]:
        evidence = "; ".join(item.get("chat_visible_evidence", []))[:260]
        gaps = "; ".join(item.get("known_gaps", []))[:260]
        lines.append(
            f"| {item['tenet_id']} | {item['status']} | {item['minimum_live_validation_tier']} | {evidence} | {gaps} |"
        )
    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {error}" for error in report["errors"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_engineering_tenet_coverage(config: EngineeringTenetCoverageConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    matrix_path = resolve_path(config_root, config.matrix_path)
    output_path = config.output_path or default_report_path(config_root)
    markdown_path = config.markdown_output_path or markdown_path_for(output_path)
    errors: list[str] = []
    matrix: dict[str, Any] = {}
    try:
        matrix = read_json_object(matrix_path)
        errors.extend(validate_matrix(matrix, config_root))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{type(exc).__name__}: {exc}")
    entries = [item for item in matrix.get("entries", []) if isinstance(item, dict)] if isinstance(matrix, dict) else []
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "engineering_tenet_coverage_report",
        "status": "passed" if not errors else "failed",
        "created_at": utc_timestamp(),
        "config_root": str(config_root),
        "matrix_path": str(matrix_path),
        "summary": {
            "tenet_count": len(entries),
            "expected_tenet_count": len(EXPECTED_TENETS),
            "status_counts": status_counts(entries),
        },
        "entries": entries,
        "errors": errors,
        "report_path": str(output_path),
        "markdown_report_path": str(markdown_path),
    }
    write_json(output_path, report)
    write_markdown(markdown_path, report)
    return report
