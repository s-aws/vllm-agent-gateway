#!/usr/bin/env python3
"""Validate Phase 116 code-quality blind-baseline prompt cases."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG_PATH = REPO_ROOT / "runtime" / "phase116_code_quality_prompt_cases.json"
REQUIRED_CASE_TYPES = {
    "duplication_review",
    "complexity_review",
    "naming_boundary_review",
    "coupling_review",
    "proposed_patch_self_review",
    "false_positive_guard",
    "standards_review",
    "self_review_checklist",
    "holdout_duplication_review",
    "holdout_patch_review",
}
REQUIRED_BASELINE_REQUIREMENTS = {
    "selected_workflow_expectation",
    "must_have_facts",
    "evidence_expectations",
    "safety_boundaries",
    "output_shape",
    "scoring_rubric",
    "likely_failure_modes",
}
FORBIDDEN_PROMPT_TERMS = {
    "SKILL.md",
    "controller json",
    "workflow envelope",
    "agentic_controller_response",
}


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object at {path}")
    return value


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def issue(case_id: str, message: str) -> dict[str, str]:
    return {"case_id": case_id, "message": message}


def validate_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    if catalog.get("kind") != "phase116_code_quality_prompt_cases":
        issues.append(issue("catalog", "kind must be phase116_code_quality_prompt_cases"))
    if catalog.get("schema_version") != 1:
        issues.append(issue("catalog", "schema_version must be 1"))
    if catalog.get("phase") != 116:
        issues.append(issue("catalog", "phase must be 116"))
    if catalog.get("priority_backlog_id") != "P0-BB-001":
        issues.append(issue("catalog", "priority_backlog_id must be P0-BB-001"))
    threshold = catalog.get("acceptance_threshold")
    if not isinstance(threshold, dict) or threshold.get("minimum_score", 0) < 85:
        issues.append(issue("acceptance_threshold", "minimum_score must be at least 85"))
    baseline_requirements = set(string_list(catalog.get("baseline_requirements")))
    missing_requirements = sorted(REQUIRED_BASELINE_REQUIREMENTS - baseline_requirements)
    if missing_requirements:
        issues.append(issue("baseline_requirements", f"missing required baseline requirements: {missing_requirements}"))
    cases_value = catalog.get("cases")
    cases = [item for item in cases_value if isinstance(item, dict)] if isinstance(cases_value, list) else []
    if len(cases) < 8:
        issues.append(issue("cases", "at least 8 Phase 116 cases are required"))
    case_ids = [str(item.get("case_id")) for item in cases if isinstance(item.get("case_id"), str)]
    if len(case_ids) != len(set(case_ids)):
        issues.append(issue("cases", "case_id values must be unique"))
    case_types = {str(item.get("case_type")) for item in cases if isinstance(item.get("case_type"), str)}
    missing_types = sorted(REQUIRED_CASE_TYPES - case_types)
    if missing_types:
        issues.append(issue("cases", f"missing case types: {missing_types}"))
    holdouts = [item for item in cases if item.get("holdout") is True]
    if len(holdouts) < 2:
        issues.append(issue("cases", "at least two holdout cases are required"))
    target_roots = {str(item.get("target_root")) for item in cases if isinstance(item.get("target_root"), str)}
    required_roots = {
        "/mnt/c/coinbase_testing_repo_frozen_tmp",
        "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
        "/mnt/c/agentic_agents/tests/fixtures/generalization/python_service_fixture",
    }
    missing_roots = sorted(required_roots - target_roots)
    if missing_roots:
        issues.append(issue("cases", f"missing required target roots: {missing_roots}"))
    for item in cases:
        case_id = str(item.get("case_id") or "unknown")
        prompt = item.get("prompt")
        if not isinstance(prompt, str) or len(prompt.split()) < 10:
            issues.append(issue(case_id, "prompt must be a natural-language request with at least 10 words"))
            continue
        lowered = prompt.lower()
        forbidden = [term for term in FORBIDDEN_PROMPT_TERMS if term.lower() in lowered]
        if forbidden:
            issues.append(issue(case_id, f"prompt contains forbidden implementation terms: {forbidden}"))
        if "read only" not in lowered and "read-only" not in lowered:
            issues.append(issue(case_id, "prompt must explicitly be read-only"))
        if item.get("expected_safety") != "read_only_no_source_mutation":
            issues.append(issue(case_id, "expected_safety must be read_only_no_source_mutation"))
        if not isinstance(item.get("expected_scope"), str) or not item["expected_scope"].strip():
            issues.append(issue(case_id, "expected_scope must be non-empty"))
        target_root = item.get("target_root")
        if not isinstance(target_root, str) or not target_root.startswith("/mnt/c/"):
            issues.append(issue(case_id, "target_root must be an absolute /mnt/c path for Bash validation"))
    return {
        "kind": "phase116_code_quality_prompt_case_report",
        "schema_version": 1,
        "status": "failed" if issues else "passed",
        "case_count": len(cases),
        "case_types": sorted(case_types),
        "holdout_count": len(holdouts),
        "target_roots": sorted(target_roots),
        "issue_count": len(issues),
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-path", default=str(DEFAULT_CATALOG_PATH))
    parser.add_argument("--output-path")
    args = parser.parse_args()

    catalog_path = Path(args.catalog_path)
    catalog = read_json_object(catalog_path)
    report = validate_catalog(catalog)
    if args.output_path:
        output_path = Path(args.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("PHASE116 CODE QUALITY CASES " + json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
