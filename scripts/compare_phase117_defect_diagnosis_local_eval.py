#!/usr/bin/env python3
"""Compare Phase 117 local responses against blind defect-diagnosis baselines."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES_PATH = REPO_ROOT / "runtime" / "phase117_defect_diagnosis_prompt_cases.json"
DEFAULT_BASELINES_PATH = REPO_ROOT / "runtime" / "phase117_defect_diagnosis_blind_baselines.json"
DEFAULT_LOCAL_EVAL_PATH = REPO_ROOT / "runtime-state" / "phase117" / "defect-diagnosis-local-eval.json"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "runtime-state" / "phase117" / "defect-diagnosis-comparison.json"
EVIDENCE_REF_RE = re.compile(r"(?P<path>[A-Za-z0-9_./-]+\.py)(?::(?P<line>\d+))?")
UNSUPPORTED_WORKFLOWS = {"workflow_router.plan", None, ""}
EXPECTED_WORKFLOW = "code_investigation.plan"


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
        return "critical", "routing: no supported defect-diagnosis workflow selected"
    if workflow == EXPECTED_WORKFLOW and ("Answer:" in text or "Defect Diagnosis:" in text):
        return "none", "route selected code_investigation.plan with a chat-visible answer"
    if workflow == EXPECTED_WORKFLOW:
        return "high", "routing: selected code_investigation.plan but did not render a chat-visible answer"
    return "high", f"routing: selected {workflow}, expected {EXPECTED_WORKFLOW}"


def has_root_cause(text: str) -> bool:
    lowered = text.lower()
    return "likely cause" in lowered or "root cause" in lowered


def has_reproduction(text: str) -> bool:
    lowered = text.lower()
    return "reproduction" in lowered or "reproduce" in lowered or "re-run" in lowered or "rerun" in lowered


def has_test_level(text: str) -> bool:
    lowered = text.lower()
    return (
        "smallest" in lowered
        and ("test" in lowered or "command" in lowered or "pytest" in lowered)
        and ("broad" in lowered or "regression" in lowered or "medium" in lowered)
    )


def has_observability(text: str) -> bool:
    lowered = text.lower()
    return "observability" in lowered or "log" in lowered or "trace" in lowered or "artifact" in lowered


def has_missing_data(text: str) -> bool:
    lowered = text.lower()
    return "missing" in lowered or "gap" in lowered or "insufficient" in lowered or "not enough evidence" in lowered


def has_read_only_boundary(text: str) -> bool:
    lowered = text.lower()
    return "read-only" in lowered or "read only" in lowered or "source mutation: false" in lowered


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
    root_cause_ok = has_root_cause(text)
    reproduction_ok = has_reproduction(text)
    test_level_ok = has_test_level(text)
    observability_ok = has_observability(text)
    missing_data_ok = has_missing_data(text)
    read_only_ok = has_read_only_boundary(text)
    if case.get("case_type") == "test_level_selection":
        root_cause_ok = True
        reproduction_ok = True
    score = 0
    score += 15 if route_severity == "none" else 0
    score += evidence_points
    score += 15 if root_cause_ok else 0
    score += 10 if reproduction_ok else 0
    score += 15 if test_level_ok else 0
    score += 10 if observability_ok else 0
    score += 10 if missing_data_ok else 0
    score += 5 if read_only_ok else 0
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
    if not root_cause_ok:
        unresolved.append({"severity": "high", "category": "root_cause", "message": "response did not name a likely/root-cause hypothesis or insufficiency boundary"})
    if not test_level_ok:
        unresolved.append({"severity": "high", "category": "test_level", "message": "response did not justify smallest plus broader validation"})
    if not reproduction_ok:
        unresolved.append({"severity": "medium", "category": "reproduction", "message": "response did not provide reproduction or rerun steps"})
    if not observability_ok:
        unresolved.append({"severity": "medium", "category": "observability", "message": "response did not cite logs, traces, artifacts, or observability evidence"})
    if not missing_data_ok:
        unresolved.append({"severity": "medium", "category": "missing_data", "message": "response did not identify missing data or evidence gaps"})
    if not read_only_ok:
        unresolved.append({"severity": "medium", "category": "safety_boundary", "message": "response did not restate the read-only/no-mutation boundary"})
    return {
        "route": route,
        "selected_workflow": workflow,
        "score": score,
        "pass": score >= 85 and not any(item["severity"] in {"critical", "high"} for item in unresolved),
        "matched_evidence_expectations": matched_evidence,
        "expected_evidence_count": expected_evidence_count,
        "root_cause_present": root_cause_ok,
        "reproduction_present": reproduction_ok,
        "test_level_present": test_level_ok,
        "observability_present": observability_ok,
        "missing_data_present": missing_data_ok,
        "read_only_boundary_present": read_only_ok,
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
                "recommendation": "Extend the existing code_investigation.plan chat answer for defect-diagnosis artifacts so it always includes reproduction, likely/root cause with confidence, smallest plus broader validation, observability evidence, and missing data.",
            },
            {
                "priority": 2,
                "category": "routing",
                "recommendation": "Route incomplete bug reports, proposed-fix regression checks, and observability-before-change prompts to the existing read-only code_investigation.plan path instead of falling back to unsupported or implementation planning routes.",
            },
            {
                "priority": 3,
                "category": "evidence",
                "recommendation": "Require chat-visible defect answers to include at least one prompt/source/test/log evidence expectation so AnythingLLM users can review the result without opening artifacts.",
            },
        ]
    )
    return {
        "kind": "phase117_defect_diagnosis_blind_baseline_comparison",
        "schema_version": 1,
        "status": status,
        "priority_backlog_id": "P0-BB-002",
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
    print("PHASE117 DEFECT DIAGNOSIS COMPARISON " + json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
