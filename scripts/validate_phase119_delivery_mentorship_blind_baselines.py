#!/usr/bin/env python3
"""Validate Phase 119 delivery-mentorship blind baselines."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES_PATH = REPO_ROOT / "runtime" / "phase119_delivery_mentorship_prompt_cases.json"
DEFAULT_BASELINES_PATH = REPO_ROOT / "runtime" / "phase119_delivery_mentorship_blind_baselines.json"
REQUIRED_BASELINE_KEYS = {
    "ideal_answer_shape",
    "must_have_topics",
    "safety_boundaries",
    "likely_local_model_failure_modes",
    "prompt_tightening_suggestion",
}
REQUIRED_SAFETY_TERMS = {"read-only", "no source mutation"}


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


def validate_baselines(cases_catalog: dict[str, Any], baselines_catalog: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    if baselines_catalog.get("kind") != "phase119_delivery_mentorship_blind_baselines":
        issues.append(issue("catalog", "kind must be phase119_delivery_mentorship_blind_baselines"))
    if baselines_catalog.get("schema_version") != 1:
        issues.append(issue("catalog", "schema_version must be 1"))
    if baselines_catalog.get("phase") != 119:
        issues.append(issue("catalog", "phase must be 119"))
    if baselines_catalog.get("priority_backlog_id") != "P0-BB-004":
        issues.append(issue("catalog", "priority_backlog_id must be P0-BB-004"))
    policy = baselines_catalog.get("baseline_policy")
    if not isinstance(policy, dict):
        issues.append(issue("baseline_policy", "baseline_policy must be an object"))
    else:
        if policy.get("blind_agent_context") != "contextless":
            issues.append(issue("baseline_policy", "blind_agent_context must be contextless"))
        if policy.get("local_model_output_seen") is not False:
            issues.append(issue("baseline_policy", "local_model_output_seen must be false"))
        if policy.get("source_mutation_allowed") is not False:
            issues.append(issue("baseline_policy", "source_mutation_allowed must be false"))

    case_ids = {
        item["case_id"]
        for item in cases_catalog.get("cases", [])
        if isinstance(item, dict) and isinstance(item.get("case_id"), str)
    }
    baselines = [item for item in baselines_catalog.get("baselines", []) if isinstance(item, dict)]
    baseline_ids = {str(item.get("case_id")) for item in baselines if isinstance(item.get("case_id"), str)}
    missing = sorted(case_ids - baseline_ids)
    extra = sorted(baseline_ids - case_ids)
    if missing:
        issues.append(issue("baselines", f"missing baselines for cases: {missing}"))
    if extra:
        issues.append(issue("baselines", f"baseline ids do not match cases: {extra}"))

    for item in baselines:
        case_id = str(item.get("case_id") or "unknown")
        missing_keys = sorted(key for key in REQUIRED_BASELINE_KEYS if key not in item)
        if missing_keys:
            issues.append(issue(case_id, f"missing required baseline keys: {missing_keys}"))
        if len(string_list(item.get("must_have_topics"))) < 6:
            issues.append(issue(case_id, "must_have_topics must include at least six topics"))
        safety_text = " ".join(string_list(item.get("safety_boundaries"))).lower()
        missing_safety = sorted(term for term in REQUIRED_SAFETY_TERMS if term not in safety_text)
        if missing_safety:
            issues.append(issue(case_id, f"safety boundaries missing terms: {missing_safety}"))
        if len(string_list(item.get("likely_local_model_failure_modes"))) < 3:
            issues.append(issue(case_id, "likely_local_model_failure_modes must include at least three items"))
    rubric = baselines_catalog.get("scoring_rubric_100")
    if not isinstance(rubric, dict) or sum(value for value in rubric.values() if isinstance(value, int)) != 100:
        issues.append(issue("scoring_rubric_100", "scoring_rubric_100 must sum to 100"))
    return {
        "kind": "phase119_delivery_mentorship_blind_baseline_report",
        "schema_version": 1,
        "status": "failed" if issues else "passed",
        "case_count": len(case_ids),
        "baseline_count": len(baselines),
        "issue_count": len(issues),
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-path", default=str(DEFAULT_CASES_PATH))
    parser.add_argument("--baselines-path", default=str(DEFAULT_BASELINES_PATH))
    parser.add_argument("--output-path")
    args = parser.parse_args()
    report = validate_baselines(read_json_object(Path(args.cases_path)), read_json_object(Path(args.baselines_path)))
    if args.output_path:
        output_path = Path(args.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("PHASE119 DELIVERY MENTORSHIP BLIND BASELINES " + json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
