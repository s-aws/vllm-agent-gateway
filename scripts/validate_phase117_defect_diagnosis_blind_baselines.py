#!/usr/bin/env python3
"""Validate Phase 117 defect-diagnosis blind baselines."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINES_PATH = REPO_ROOT / "runtime" / "phase117_defect_diagnosis_blind_baselines.json"
DEFAULT_CASES_PATH = REPO_ROOT / "runtime" / "phase117_defect_diagnosis_prompt_cases.json"
REQUIRED_BASELINE_KEYS = {
    "ideal_answer_shape",
    "must_have_facts",
    "evidence_expectations",
    "safety_boundaries",
    "scoring_rubric_100",
    "likely_local_model_failure_modes",
    "prompt_tightening_suggestion",
}
REQUIRED_RUBRIC_TOPICS = (
    "evidence",
    "test",
    "read",
)


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object at {path}")
    return value


def non_empty_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def issue(case_id: str, message: str) -> dict[str, str]:
    return {"case_id": case_id, "message": message}


def validate_baselines(cases_catalog: dict[str, Any], baselines_catalog: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    if baselines_catalog.get("kind") != "phase117_defect_diagnosis_blind_baselines":
        issues.append(issue("catalog", "kind must be phase117_defect_diagnosis_blind_baselines"))
    if baselines_catalog.get("schema_version") != 1:
        issues.append(issue("catalog", "schema_version must be 1"))
    if baselines_catalog.get("phase") != 117:
        issues.append(issue("catalog", "phase must be 117"))
    if baselines_catalog.get("priority_backlog_id") != "P0-BB-002":
        issues.append(issue("catalog", "priority_backlog_id must be P0-BB-002"))
    policy = baselines_catalog.get("baseline_policy")
    if not isinstance(policy, dict):
        issues.append(issue("baseline_policy", "baseline_policy must be an object"))
    else:
        expected_policy = {
            "blind_agent_context": "contextless",
            "local_model_output_seen": False,
            "source_mutation_allowed": False,
        }
        for key, expected in expected_policy.items():
            if policy.get(key) != expected:
                issues.append(issue("baseline_policy", f"{key} must be {expected!r}"))
        blind_agent_id = policy.get("blind_agent_id")
        if not isinstance(blind_agent_id, str) or not blind_agent_id.strip():
            issues.append(issue("baseline_policy", "blind_agent_id must identify the contextless baseline source"))

    cases = [item for item in cases_catalog.get("cases", []) if isinstance(item, dict)]
    case_ids = [item.get("case_id") for item in cases if isinstance(item.get("case_id"), str)]
    baselines = [item for item in baselines_catalog.get("baselines", []) if isinstance(item, dict)]
    baseline_by_case = {item.get("case_id"): item for item in baselines if isinstance(item.get("case_id"), str)}
    missing = sorted(case_id for case_id in case_ids if case_id not in baseline_by_case)
    extra = sorted(str(case_id) for case_id in baseline_by_case if case_id not in set(case_ids))
    if missing:
        issues.append(issue("baselines", f"missing baselines for cases: {missing}"))
    if extra:
        issues.append(issue("baselines", f"baselines without prompt cases: {extra}"))
    if len(baseline_by_case) != len(baselines):
        issues.append(issue("baselines", "baseline case_id values must be unique"))

    for case_id in case_ids:
        baseline = baseline_by_case.get(case_id)
        if not isinstance(baseline, dict):
            continue
        missing_keys = sorted(REQUIRED_BASELINE_KEYS - set(baseline))
        if missing_keys:
            issues.append(issue(case_id, f"missing baseline keys: {missing_keys}"))
        for key in ("must_have_facts", "evidence_expectations", "safety_boundaries", "likely_local_model_failure_modes"):
            values = non_empty_string_list(baseline.get(key))
            if len(values) < 2:
                issues.append(issue(case_id, f"{key} must include at least two non-empty strings"))
        ideal = baseline.get("ideal_answer_shape")
        if not isinstance(ideal, str) or len(ideal.split()) < 10:
            issues.append(issue(case_id, "ideal_answer_shape must be a useful sentence"))
        suggestion = baseline.get("prompt_tightening_suggestion")
        if not isinstance(suggestion, str) or len(suggestion.split()) < 6:
            issues.append(issue(case_id, "prompt_tightening_suggestion must be a useful sentence"))
        rubric = baseline.get("scoring_rubric_100")
        if not isinstance(rubric, dict) or not rubric:
            issues.append(issue(case_id, "scoring_rubric_100 must be a non-empty object"))
        else:
            total = sum(value for value in rubric.values() if isinstance(value, int))
            if total != 100:
                issues.append(issue(case_id, f"scoring_rubric_100 must total 100, got {total}"))
            rubric_text = " ".join(str(key).lower() for key in rubric)
            missing_topics = [topic for topic in REQUIRED_RUBRIC_TOPICS if topic not in rubric_text]
            if missing_topics:
                issues.append(issue(case_id, f"scoring_rubric_100 missing rubric topics: {missing_topics}"))

    return {
        "kind": "phase117_defect_diagnosis_blind_baseline_report",
        "schema_version": 1,
        "status": "failed" if issues else "passed",
        "case_count": len(case_ids),
        "baseline_count": len(baseline_by_case),
        "issue_count": len(issues),
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-path", default=str(DEFAULT_CASES_PATH))
    parser.add_argument("--baselines-path", default=str(DEFAULT_BASELINES_PATH))
    parser.add_argument("--output-path")
    args = parser.parse_args()

    cases_catalog = read_json_object(Path(args.cases_path))
    baselines_catalog = read_json_object(Path(args.baselines_path))
    report = validate_baselines(cases_catalog, baselines_catalog)
    if args.output_path:
        output_path = Path(args.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("PHASE117 DEFECT DIAGNOSIS BLIND BASELINES " + json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
