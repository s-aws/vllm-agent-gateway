#!/usr/bin/env python3
"""Validate founder field prompt routing and classifier priority offline."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_founder_field_prompt_eval import FIELD_PROMPTS, PROMPT_REFINEMENTS  # noqa: E402
from vllm_agent_gateway.prompt_catalogs import expected_rules_from_cases  # noqa: E402
from vllm_agent_gateway.controllers.workflow_router.plan import workflow_kind_for_request  # noqa: E402


DEFAULT_REPORT_DIR = Path("runtime-state") / "founder-field-tests"

EXPECTED_RULES_BY_CASE = expected_rules_from_cases(FIELD_PROMPTS)



@dataclass(frozen=True)
class MatrixPrompt:
    case_id: str
    prompt: str
    expected_workflow: str
    expected_rule: str
    source_case_id: str
    variant_kind: str
    note: str


def case_by_id() -> dict[str, Any]:
    return {case.case_id: case for case in FIELD_PROMPTS}


def build_variant_prompts() -> tuple[MatrixPrompt, ...]:
    cases = case_by_id()
    variants: list[MatrixPrompt] = []
    for source_case_id in sorted(PROMPT_REFINEMENTS):
        source_case = cases[source_case_id]
        expected_rule = source_case.refined_expected_rule or source_case.expected_rule
        refinement = PROMPT_REFINEMENTS[source_case_id]
        variants.append(
            MatrixPrompt(
                case_id=f"{source_case_id}-V1",
                prompt=refinement["refined_prompt"],
                expected_workflow=source_case.expected_workflow,
                expected_rule=expected_rule,
                source_case_id=source_case_id,
                variant_kind="refined",
                note=refinement["prompt_risk"],
            )
        )
    return tuple(variants)


VARIANT_PROMPTS: tuple[MatrixPrompt, ...] = build_variant_prompts()


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def catalog_matrix_prompts() -> tuple[MatrixPrompt, ...]:
    prompts: list[MatrixPrompt] = []
    for case in FIELD_PROMPTS:
        expected_rule = case.expected_rule
        prompts.append(
            MatrixPrompt(
                case_id=case.case_id,
                prompt=case.prompt,
                expected_workflow=case.expected_workflow,
                expected_rule=expected_rule,
                source_case_id=case.case_id,
                variant_kind="original",
                note=case.baseline_target,
            )
        )
    prompts.extend(VARIANT_PROMPTS)
    return tuple(prompts)


def router_rules(evidence: list[dict[str, Any]]) -> list[str]:
    return [
        str(item["rule"])
        for item in evidence
        if isinstance(item, dict) and item.get("source") == "router_rule" and isinstance(item.get("rule"), str)
    ]


def evaluate_matrix_prompt(case: MatrixPrompt) -> dict[str, Any]:
    actual_workflow, status_reason, evidence = workflow_kind_for_request(case.prompt)
    rules = router_rules(evidence)
    actual_rule = rules[0] if rules else ""
    problems: list[str] = []
    if status_reason != "ready":
        problems.append(f"status_reason={status_reason}")
    if actual_workflow != case.expected_workflow:
        problems.append(f"workflow expected {case.expected_workflow} got {actual_workflow}")
    if actual_rule != case.expected_rule:
        problems.append(f"primary rule expected {case.expected_rule} got {actual_rule or 'none'}")
    conflict = ""
    if actual_rule != case.expected_rule and case.expected_rule in rules:
        conflict = "expected rule appeared after another router rule; classifier priority conflict"
    elif actual_workflow == case.expected_workflow and actual_rule != case.expected_rule:
        conflict = "workflow matched but classifier explainability rule did not"
    return {
        "case_id": case.case_id,
        "source_case_id": case.source_case_id,
        "variant_kind": case.variant_kind,
        "status": "passed" if not problems else "failed",
        "prompt": case.prompt,
        "expected_workflow": case.expected_workflow,
        "actual_workflow": actual_workflow,
        "expected_rule": case.expected_rule,
        "actual_rule": actual_rule,
        "all_rules": rules,
        "status_reason": status_reason,
        "problems": problems,
        "conflict": conflict,
        "note": case.note,
    }


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"prompt-matrix-{utc_timestamp()}.json"


def markdown_path_for(report_path: Path) -> Path:
    return report_path.with_suffix(".md")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Founder Field Prompt Matrix",
        "",
        f"- Status: {report['status']}",
        f"- Created at: {report['created_at']}",
        f"- Prompt count: {len(report['cases'])}",
        f"- Passed: {report['summary']['passed']}",
        f"- Failed: {report['summary']['failed']}",
        "",
        "## Results",
        "",
        "| Case | Variant | Status | Expected workflow | Actual workflow | Expected rule | Actual rule | Conflict |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in report["cases"]:
        lines.append(
            "| {case_id} | {variant} | {status} | {expected_workflow} | {actual_workflow} | {expected_rule} | {actual_rule} | {conflict} |".format(
                case_id=item["case_id"],
                variant=item["variant_kind"],
                status=item["status"],
                expected_workflow=item["expected_workflow"],
                actual_workflow=item.get("actual_workflow") or "",
                expected_rule=item["expected_rule"],
                actual_rule=item.get("actual_rule") or "",
                conflict=str(item.get("conflict") or "").replace("\n", " "),
            )
        )
    lines.extend(["", "## Prompt Notes", ""])
    for item in report["cases"]:
        lines.extend(
            [
                f"### {item['case_id']}",
                "",
                f"Prompt: {item['prompt']}",
                "",
                f"Note: {item['note']}",
                "",
                f"Rules: `{', '.join(item.get('all_rules') or [])}`",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_report(cases: tuple[MatrixPrompt, ...], config_root: Path) -> dict[str, Any]:
    results = [evaluate_matrix_prompt(case) for case in cases]
    passed = sum(1 for item in results if item["status"] == "passed")
    failed = len(results) - passed
    return {
        "schema_version": 1,
        "kind": "founder_field_prompt_matrix",
        "status": "passed" if failed == 0 else "failed",
        "created_at": utc_timestamp(),
        "config_root": str(config_root),
        "summary": {"passed": passed, "failed": failed},
        "cases": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--markdown-output-path", default=None)
    parser.add_argument("--list-cases", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root).resolve()
    cases = catalog_matrix_prompts()
    if args.list_cases:
        print(json.dumps([case.__dict__ for case in cases], ensure_ascii=True, indent=2, sort_keys=True))
        return 0
    report = build_report(cases, config_root)
    report_path = Path(args.output_path) if args.output_path else default_report_path(config_root)
    markdown_path = Path(args.markdown_output_path) if args.markdown_output_path else markdown_path_for(report_path)
    write_json(report_path, report)
    write_markdown(markdown_path, report)
    print(f"PROMPT MATRIX REPORT {report_path.resolve()}")
    print(f"PROMPT MATRIX MARKDOWN {markdown_path.resolve()}")
    print("PROMPT MATRIX SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("PROMPT MATRIX FAILURES " + json.dumps([item for item in report["cases"] if item["status"] != "passed"], ensure_ascii=True, sort_keys=True))
        return 1
    print("PROMPT MATRIX PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
