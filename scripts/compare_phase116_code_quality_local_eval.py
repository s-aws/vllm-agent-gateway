#!/usr/bin/env python3
"""Compare Phase 116 local responses against blind code-quality baselines."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES_PATH = REPO_ROOT / "runtime" / "phase116_code_quality_prompt_cases.json"
DEFAULT_BASELINES_PATH = REPO_ROOT / "runtime" / "phase116_code_quality_blind_baselines.json"
DEFAULT_LOCAL_EVAL_PATH = REPO_ROOT / "runtime-state" / "phase116" / "code-quality-local-eval.json"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "runtime-state" / "phase116" / "code-quality-comparison.json"
EVIDENCE_REF_RE = re.compile(r"(?P<path>[A-Za-z0-9_./-]+\.py):(?P<line>\d+)")
UNSUPPORTED_WORKFLOWS = {"workflow_router.plan", None, ""}
MISROUTED_REVIEW_WORKFLOWS = {"code_context.lookup"}


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
        return value.strip()
    return f"{match.group('path').lstrip('./')}:{match.group('line')}"


def evidence_refs_in_text(text: str) -> set[str]:
    return {
        f"{match.group('path').lstrip('./')}:{match.group('line')}"
        for match in EVIDENCE_REF_RE.finditer(text)
    }


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
        return "critical", "routing: no supported code-quality workflow selected"
    if workflow == "code_investigation.plan" and "Code Quality Review:" in text:
        return "none", "route selected code_investigation.plan with a chat-visible code-quality review artifact"
    if workflow == "code_investigation.plan":
        return "high", "routing: selected code_investigation.plan but did not render a code-quality review answer"
    if workflow in MISROUTED_REVIEW_WORKFLOWS:
        return "high", f"routing: selected {workflow}, which explains or locates code instead of reviewing code quality"
    return "none", "route selected a review-capable workflow"


def compare_response(case: dict[str, Any], baseline: dict[str, Any], route: str, response: dict[str, Any]) -> dict[str, Any]:
    text = response.get("text") if isinstance(response.get("text"), str) else ""
    workflow = selected_workflow(response)
    route_severity, route_gap = classify_route_gap(workflow, text)
    expected_refs = [normalize_ref(ref) for ref in baseline.get("evidence_expectations", []) if isinstance(ref, str)]
    found_refs = evidence_refs_in_text(text)
    matched_refs = sorted(ref for ref in expected_refs if ref in found_refs)
    expected_ref_count = len(expected_refs)
    ref_score = 0 if expected_ref_count == 0 else round((len(matched_refs) / expected_ref_count) * 30)
    has_findings = "finding" in text.lower()
    has_checklist_answer = case.get("case_type") == "self_review_checklist" and "checklist" in text.lower()
    has_false_positive_language = "false positive" in text.lower() or "rejected" in text.lower()
    read_only_ok = "read-only" in text.lower() or "read only" in text.lower() or "source mutation: false" in text.lower()
    unsupported = route_severity == "critical"
    score = 0
    score += 20 if route_severity == "none" else 0
    score += ref_score
    score += 15 if read_only_ok else 0
    score += 15 if has_findings or has_checklist_answer or "no supported" in text.lower() or "no meaningful" in text.lower() else 0
    score += 10 if has_false_positive_language else 0
    if unsupported:
        score = min(score, 20)
    elif route_severity == "high":
        score = min(score, 45)
    unresolved: list[dict[str, str]] = []
    if route_severity != "none":
        unresolved.append({"severity": route_severity, "category": "routing", "message": route_gap})
    if len(matched_refs) == 0:
        unresolved.append(
            {
                "severity": "high",
                "category": "evidence",
                "message": "response did not include any blind-baseline evidence refs",
            }
        )
    if not has_findings and not has_checklist_answer and case.get("case_type") not in {"naming_boundary_review", "false_positive_guard"}:
        unresolved.append(
            {
                "severity": "high",
                "category": "answer_contract",
                "message": "response did not provide code-quality findings or patch-review analysis",
            }
        )
    if not read_only_ok:
        unresolved.append(
            {
                "severity": "medium",
                "category": "safety_boundary",
                "message": "response did not restate the read-only/no-mutation boundary",
            }
        )
    return {
        "route": route,
        "selected_workflow": workflow,
        "score": score,
        "pass": score >= 85 and not any(item["severity"] in {"critical", "high"} for item in unresolved),
        "matched_evidence_refs": matched_refs,
        "expected_evidence_ref_count": expected_ref_count,
        "has_findings_or_no_finding_answer": has_findings
        or has_checklist_answer
        or "no supported" in text.lower()
        or "no meaningful" in text.lower(),
        "has_false_positive_language": has_false_positive_language,
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
                "category": "routing",
                "recommendation": "Add a single controller-owned code-quality/self-review workflow or extend the existing read-only code path so review prompts do not fall through to unsupported workflow_router.plan or explanation-only code_investigation.plan.",
            },
            {
                "priority": 2,
                "category": "answer_contract",
                "recommendation": "Add a deterministic chat-visible code-quality response contract with findings, severity, evidence refs, impact, bounded remediation, rejected false positives, and read-only boundary.",
            },
            {
                "priority": 3,
                "category": "evidence",
                "recommendation": "Require review answers to include line-level refs from gathered source/test evidence rather than artifact-only source summaries.",
            },
        ]
    )
    return {
        "kind": "phase116_code_quality_blind_baseline_comparison",
        "schema_version": 1,
        "status": status,
        "priority_backlog_id": "P0-BB-001",
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
    print("PHASE116 CODE QUALITY COMPARISON " + json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
