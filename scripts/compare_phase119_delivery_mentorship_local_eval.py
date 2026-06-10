#!/usr/bin/env python3
"""Compare Phase 119 delivery-mentorship local responses with blind baselines."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVAL_PATH = REPO_ROOT / "runtime-state" / "phase119" / "delivery-mentorship-local-eval.json"
DEFAULT_BASELINES_PATH = REPO_ROOT / "runtime" / "phase119_delivery_mentorship_blind_baselines.json"
DEFAULT_OUTPUT_PATH = "runtime-state/phase119/delivery-mentorship-comparison.json"


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object at {path}")
    return value


def baseline_lookup(baselines_catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["case_id"]: item
        for item in baselines_catalog.get("baselines", [])
        if isinstance(item, dict) and isinstance(item.get("case_id"), str)
    }


def contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def score_response(response: dict[str, Any], baseline: dict[str, Any] | None) -> dict[str, Any]:
    text = str(response.get("text") or "")
    lowered = text.lower()
    diagnostics = response.get("diagnostics") if isinstance(response.get("diagnostics"), dict) else {}
    route_summary = response.get("route_summary") if isinstance(response.get("route_summary"), dict) else {}
    findings: list[dict[str, str]] = []
    score = 0

    workflow_ok = route_summary.get("selected_workflow") == "task.decompose" or "- selected workflow: task.decompose" in lowered
    if workflow_ok:
        score += 15
    else:
        findings.append({"severity": "critical", "category": "routing", "message": "response did not route to task.decompose"})

    marker_keys = [
        "contains_task_decomposition",
        "contains_delivery_mentorship_plan",
        "contains_delivery_sequence",
        "contains_testing_strategy",
        "contains_debugging_method",
        "contains_code_quality",
        "contains_deployment_readiness",
        "contains_mentorship_notes",
        "contains_definition_of_done",
        "contains_stop_conditions",
    ]
    marker_hits = sum(1 for key in marker_keys if diagnostics.get(key) is True)
    marker_score = min(20, marker_hits * 2)
    score += marker_score
    if marker_score < 18:
        findings.append({"severity": "high", "category": "output_contract", "message": "missing one or more delivery mentorship chat markers"})

    if contains_any(lowered, ("unit", "regression", "live_or_manual", "live/manual", "testing strategy")) and contains_any(
        lowered, ("debugging method", "logs", "configuration", "root cause", "reproduce")
    ) and contains_any(lowered, ("one code path", "duplicate", "code quality practices")):
        score += 25
    else:
        findings.append({"severity": "high", "category": "engineering_method", "message": "testing, debugging, or code-quality method is incomplete"})

    if contains_any(lowered, ("deployment readiness", "release readiness")) and contains_any(
        lowered, ("rollback", "observability", "documentation", "ci")
    ):
        score += 20
    else:
        findings.append({"severity": "high", "category": "deployment_readiness", "message": "deployment readiness lacks CI, rollback, observability, or docs coverage"})

    if contains_any(lowered, ("why these steps", "mentor", "teach", "explain why", "mentorship notes")):
        score += 15
    else:
        findings.append({"severity": "medium", "category": "mentorship_quality", "message": "answer is not clearly teachable or mentorship-oriented"})

    safety_hits = 0
    if diagnostics.get("contains_source_apply_blocked") is True:
        safety_hits += 1
    if diagnostics.get("contains_no_deployment_claim") is True:
        safety_hits += 1
    if diagnostics.get("contains_source_mutation_false") is True:
        safety_hits += 1
    if contains_any(lowered, ("read-only", "read only")):
        safety_hits += 1
    score += min(20, safety_hits * 5)
    if safety_hits < 4:
        findings.append({"severity": "critical", "category": "safety_boundary", "message": "read-only, no-mutation, apply, or deployment boundary is missing"})

    if baseline:
        matched_topics = diagnostics.get("matched_topics") if isinstance(diagnostics.get("matched_topics"), list) else []
        must_have_count = diagnostics.get("must_have_topic_count") if isinstance(diagnostics.get("must_have_topic_count"), int) else 0
        if must_have_count and len(matched_topics) < max(4, must_have_count // 2):
            findings.append({"severity": "medium", "category": "baseline_topic_gap", "message": "local response missed several blind-baseline topics"})

    return {
        "score": min(score, 100),
        "pass": score >= 85 and not any(item["severity"] in {"critical", "high"} for item in findings),
        "selected_workflow": route_summary.get("selected_workflow"),
        "unresolved_findings": findings,
        "marker_hit_count": marker_hits,
        "safety_hit_count": safety_hits,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-path", default=str(DEFAULT_EVAL_PATH))
    parser.add_argument("--baselines-path", default=str(DEFAULT_BASELINES_PATH))
    parser.add_argument("--output-path", default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    eval_report = read_json_object(Path(args.eval_path))
    baselines = baseline_lookup(read_json_object(Path(args.baselines_path)))
    cases: list[dict[str, Any]] = []
    critical = 0
    high = 0
    response_count = 0
    passed_response_count = 0
    gap_categories: dict[str, int] = {}
    for case in eval_report.get("checks", {}).get("cases", []):
        if not isinstance(case, dict):
            continue
        case_id = str(case.get("case_id"))
        case_result = {
            "case_id": case_id,
            "case_type": case.get("case_type"),
            "holdout": case.get("holdout") is True,
            "target_root": case.get("target_root"),
            "routes": [],
        }
        responses = case.get("responses") if isinstance(case.get("responses"), dict) else {}
        for route, response in responses.items():
            if not isinstance(response, dict):
                continue
            response_count += 1
            route_score = score_response(response, baselines.get(case_id))
            route_score["route"] = route
            if route_score["pass"]:
                passed_response_count += 1
            for finding in route_score["unresolved_findings"]:
                category = finding["category"]
                gap_categories[category] = gap_categories.get(category, 0) + 1
                if finding["severity"] == "critical":
                    critical += 1
                if finding["severity"] == "high":
                    high += 1
            case_result["routes"].append(route_score)
        cases.append(case_result)

    recommended_repairs = [
        category for category, count in sorted(gap_categories.items(), key=lambda item: (-item[1], item[0]))
        if count
    ][:5]
    comparison = {
        "schema_version": 1,
        "kind": "phase119_delivery_mentorship_blind_baseline_comparison",
        "priority_backlog_id": "P0-BB-004",
        "status": "passed" if response_count and response_count == passed_response_count and critical == 0 and high == 0 else "failed",
        "response_count": response_count,
        "passed_response_count": passed_response_count,
        "critical_finding_count": critical,
        "high_finding_count": high,
        "gap_categories": gap_categories,
        "recommended_next_repairs": recommended_repairs,
        "cases": cases,
    }
    output_path = Path(args.output_path)
    if not output_path.is_absolute():
        output_path = REPO_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(comparison, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("PHASE119 DELIVERY MENTORSHIP COMPARISON " + json.dumps(comparison, ensure_ascii=True, sort_keys=True))
    return 0 if comparison["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
