#!/usr/bin/env python3
"""Compare Phase 118 local responses against blind engineering-judgment baselines."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES_PATH = REPO_ROOT / "runtime" / "phase118_engineering_judgment_prompt_cases.json"
DEFAULT_BASELINES_PATH = REPO_ROOT / "runtime" / "phase118_engineering_judgment_blind_baselines.json"
DEFAULT_LOCAL_EVAL_PATH = REPO_ROOT / "runtime-state" / "phase118" / "engineering-judgment-local-eval.json"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "runtime-state" / "phase118" / "engineering-judgment-comparison.json"
EVIDENCE_REF_RE = re.compile(r"(?P<path>[A-Za-z0-9_./-]+\.(?:py|go|js))(?::(?P<line>\d+))?")
UNSUPPORTED_WORKFLOWS = {"workflow_router.plan", None, ""}
EXPECTED_WORKFLOW = "code_investigation.plan"
UNSUPPORTED_PREFERENCE_PHRASES = (
    "because it is cleaner",
    "because it is better",
    "best practice",
    "obviously",
)


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object at {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalize_ref(value: str) -> str:
    match = EVIDENCE_REF_RE.search(value)
    if not match:
        return value.strip().lower()
    suffix = f":{match.group('line')}" if match.group("line") else ""
    return f"{match.group('path').lstrip('./')}{suffix}".lower()


def evidence_refs_in_text(text: str) -> set[str]:
    return {
        f"{match.group('path').lstrip('./')}{':' + match.group('line') if match.group('line') else ''}".lower()
        for match in EVIDENCE_REF_RE.finditer(text)
    }


def phrase_hit(text: str, phrase: str) -> bool:
    lowered = text.lower()
    expected = phrase.lower().strip()
    if not expected:
        return False
    if expected in lowered:
        return True
    normalized = normalize_ref(phrase)
    return normalized in evidence_refs_in_text(text)


def baseline_lookup(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["case_id"]: item
        for item in catalog.get("baselines", [])
        if isinstance(item, dict) and isinstance(item.get("case_id"), str)
    }


def case_lookup(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["case_id"]: item
        for item in catalog.get("cases", [])
        if isinstance(item, dict) and isinstance(item.get("case_id"), str)
    }


def selected_workflow(response: dict[str, Any]) -> str | None:
    summary = response.get("route_summary")
    if isinstance(summary, dict):
        value = summary.get("selected_workflow")
        if isinstance(value, str):
            return value
    return None


def classify_route_gap(workflow: str | None, text: str) -> tuple[str, str]:
    if workflow in UNSUPPORTED_WORKFLOWS:
        return "critical", "routing: no supported engineering-judgment workflow selected"
    if workflow == EXPECTED_WORKFLOW and ("Engineering Judgment:" in text or "Answer:" in text):
        return "none", "route selected code_investigation.plan with a chat-visible answer"
    if workflow == EXPECTED_WORKFLOW:
        return "high", "routing: selected code_investigation.plan but did not render a chat-visible answer"
    return "high", f"routing: selected {workflow}, expected {EXPECTED_WORKFLOW}"


def has_direct_recommendation(text: str) -> bool:
    lowered = text.lower()
    return "recommendation" in lowered or "recommend " in lowered or "do not proceed" in lowered or "defer" in lowered


def has_tradeoffs(text: str) -> bool:
    lowered = text.lower()
    return "tradeoff" in lowered or "benefit" in lowered or "cost" in lowered or "alternative" in lowered


def has_risks(text: str) -> bool:
    lowered = text.lower()
    return "risk" in lowered or "blocker" in lowered or "do-not-proceed" in lowered or "do not proceed" in lowered


def has_validation(text: str) -> bool:
    lowered = text.lower()
    return "validation" in lowered or "verify" in lowered or "test" in lowered or "measurement" in lowered


def has_confidence(text: str) -> bool:
    return "confidence" in text.lower()


def has_unknowns(text: str) -> bool:
    lowered = text.lower()
    return "unknown" in lowered or "missing" in lowered or "insufficient" in lowered or "not enough evidence" in lowered


def has_debt_separation(text: str, case: dict[str, Any]) -> bool:
    if "debt" not in str(case.get("case_type", "")) and "debt" not in str(case.get("prompt", "")).lower():
        return True
    lowered = text.lower()
    return "technical debt" in lowered and ("separate" in lowered or "remediation" in lowered or "feature delivery" in lowered)


def has_read_only_boundary(text: str) -> bool:
    lowered = text.lower()
    return "read-only" in lowered or "read only" in lowered or "source mutation: false" in lowered


def has_unsupported_preference(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in UNSUPPORTED_PREFERENCE_PHRASES) and "evidence" not in lowered


def evidence_score(text: str, baseline: dict[str, Any]) -> tuple[int, list[str], int]:
    expected = [item for item in baseline.get("evidence_expectations", []) if isinstance(item, str) and item.strip()]
    if not expected:
        return 0, [], 0
    matched = [item for item in expected if phrase_hit(text, item)]
    return round((len(matched) / len(expected)) * 20), matched, len(expected)


def compare_response(case: dict[str, Any], baseline: dict[str, Any], route: str, response: dict[str, Any]) -> dict[str, Any]:
    text = response.get("text") if isinstance(response.get("text"), str) else ""
    workflow = selected_workflow(response)
    route_severity, route_gap = classify_route_gap(workflow, text)
    evidence_points, matched_evidence, expected_evidence_count = evidence_score(text, baseline)
    recommendation_ok = has_direct_recommendation(text)
    tradeoffs_ok = has_tradeoffs(text)
    risks_ok = has_risks(text)
    validation_ok = has_validation(text)
    confidence_ok = has_confidence(text)
    unknowns_ok = has_unknowns(text)
    debt_ok = has_debt_separation(text, case)
    read_only_ok = has_read_only_boundary(text)
    preference_fail = has_unsupported_preference(text)
    score = 0
    score += 10 if route_severity == "none" else 0
    score += evidence_points
    score += 15 if recommendation_ok else 0
    score += 15 if tradeoffs_ok else 0
    score += 10 if risks_ok else 0
    score += 10 if validation_ok else 0
    score += 5 if confidence_ok else 0
    score += 5 if unknowns_ok else 0
    score += 5 if debt_ok else 0
    score += 5 if read_only_ok else 0
    if preference_fail:
        score = min(score, 45)
    if route_severity == "critical":
        score = min(score, 20)
    elif route_severity == "high":
        score = min(score, 55)
    unresolved: list[dict[str, str]] = []
    if route_severity != "none":
        unresolved.append({"severity": route_severity, "category": "routing", "message": route_gap})
    if expected_evidence_count and not matched_evidence:
        unresolved.append(
            {
                "severity": "high",
                "category": "evidence",
                "message": "response did not include any blind-baseline evidence expectation",
            }
        )
    if not recommendation_ok:
        unresolved.append({"severity": "high", "category": "recommendation", "message": "response did not provide a direct bounded recommendation or do-not-proceed decision"})
    if not tradeoffs_ok:
        unresolved.append({"severity": "high", "category": "tradeoffs", "message": "response did not discuss alternatives, benefits, costs, or tradeoffs"})
    if preference_fail:
        unresolved.append({"severity": "critical", "category": "unsupported_preference", "message": "response used unsupported preference language as the basis for recommendation"})
    if not risks_ok:
        unresolved.append({"severity": "medium", "category": "risk", "message": "response did not identify risk, blockers, or do-not-proceed conditions"})
    if not validation_ok:
        unresolved.append({"severity": "medium", "category": "validation", "message": "response did not provide deterministic validation or measurement steps"})
    if not confidence_ok:
        unresolved.append({"severity": "medium", "category": "confidence", "message": "response did not state confidence"})
    if not unknowns_ok:
        unresolved.append({"severity": "medium", "category": "unknowns", "message": "response did not state unknowns, missing context, or evidence gaps"})
    if not debt_ok:
        unresolved.append({"severity": "medium", "category": "technical_debt", "message": "response did not separate technical debt from feature delivery"})
    if not read_only_ok:
        unresolved.append({"severity": "medium", "category": "safety_boundary", "message": "response did not restate the read-only/no-mutation boundary"})
    return {
        "route": route,
        "selected_workflow": workflow,
        "score": score,
        "pass": score >= 85 and not any(item["severity"] in {"critical", "high"} for item in unresolved),
        "matched_evidence_expectations": matched_evidence,
        "expected_evidence_count": expected_evidence_count,
        "direct_recommendation_present": recommendation_ok,
        "tradeoffs_present": tradeoffs_ok,
        "risks_present": risks_ok,
        "validation_present": validation_ok,
        "confidence_present": confidence_ok,
        "unknowns_present": unknowns_ok,
        "debt_separation_present": debt_ok,
        "read_only_boundary_present": read_only_ok,
        "unsupported_preference_detected": preference_fail,
        "unresolved_findings": unresolved,
    }


def compare(cases_catalog: dict[str, Any], baselines_catalog: dict[str, Any], local_eval: dict[str, Any]) -> dict[str, Any]:
    cases = case_lookup(cases_catalog)
    baselines = baseline_lookup(baselines_catalog)
    case_reports: list[dict[str, Any]] = []
    critical_count = 0
    high_count = 0
    passed_count = 0
    response_count = 0
    gap_categories: dict[str, int] = {}
    for case_result in local_eval.get("checks", {}).get("cases", []):
        if not isinstance(case_result, dict):
            continue
        case_id = str(case_result.get("case_id"))
        case = cases.get(case_id, {})
        baseline = baselines.get(case_id, {})
        route_reports: list[dict[str, Any]] = []
        responses = case_result.get("responses")
        if not isinstance(responses, dict):
            responses = {}
        for route, response in responses.items():
            if not isinstance(response, dict):
                continue
            response_count += 1
            route_report = compare_response(case, baseline, str(route), response)
            route_reports.append(route_report)
            if route_report["pass"]:
                passed_count += 1
            for finding in route_report["unresolved_findings"]:
                gap_categories[finding["category"]] = gap_categories.get(finding["category"], 0) + 1
                if finding["severity"] == "critical":
                    critical_count += 1
                elif finding["severity"] == "high":
                    high_count += 1
        case_reports.append(
            {
                "case_id": case_id,
                "case_type": case_result.get("case_type"),
                "holdout": case_result.get("holdout") is True,
                "target_root": case_result.get("target_root"),
                "routes": route_reports,
            }
        )
    status = "passed" if response_count and passed_count == response_count and critical_count == 0 and high_count == 0 else "failed"
    recommended_next_repairs = (
        []
        if status == "passed"
        else [
            {
                "priority": 1,
                "category": "answer_contract",
                "recommendation": "Extend the existing code_investigation.plan chat answer for engineering-judgment artifacts so it includes direct recommendation, evidence, alternatives, tradeoffs, risks, debt separation, validation, unknowns, confidence, and read-only boundary.",
            },
            {
                "priority": 2,
                "category": "routing",
                "recommendation": "Route read-only tradeoff, technical debt, risk, blocker, review-feedback, and architecture-decision prompts to code_investigation.plan.",
            },
            {
                "priority": 3,
                "category": "evidence",
                "recommendation": "Require chat-visible engineering-judgment answers to include source refs rather than artifact-only links or unsupported preference claims.",
            },
        ]
    )
    return {
        "kind": "phase118_engineering_judgment_blind_baseline_comparison",
        "schema_version": 1,
        "status": status,
        "priority_backlog_id": "P0-BB-003",
        "response_count": response_count,
        "passed_response_count": passed_count,
        "critical_finding_count": critical_count,
        "high_finding_count": high_count,
        "gap_categories": dict(sorted(gap_categories.items())),
        "cases": case_reports,
        "recommended_next_repairs": recommended_next_repairs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-path", default=str(DEFAULT_CASES_PATH))
    parser.add_argument("--baselines-path", default=str(DEFAULT_BASELINES_PATH))
    parser.add_argument("--local-eval-path", default=str(DEFAULT_LOCAL_EVAL_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    args = parser.parse_args()

    report = compare(
        read_json_object(Path(args.cases_path)),
        read_json_object(Path(args.baselines_path)),
        read_json_object(Path(args.local_eval_path)),
    )
    write_json(Path(args.output_path), report)
    print("PHASE118 ENGINEERING JUDGMENT COMPARISON " + json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
