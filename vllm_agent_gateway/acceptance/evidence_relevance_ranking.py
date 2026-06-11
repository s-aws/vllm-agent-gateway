"""Acceptance checks for evidence relevance ranking."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vllm_agent_gateway.controllers.code_investigation.plan import (
    evidence_file_records,
    request_flow_steps_from_matches,
)


DEFAULT_POLICY_PATH = Path("runtime/evidence_relevance_ranking_policy.json")
REQUIRED_SYNTHETIC_CASE_IDS = {
    "ERR-001-exact-behavior-over-broad-source",
    "ERR-002-exact-line-over-broad-line",
    "ERR-003-handler-branch-over-path-sorted-match",
}


def object_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def string_list(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def load_policy(path: Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def synthetic_exact_behavior_case() -> dict[str, Any]:
    records = evidence_file_records(
        ["core/stealth_order_manager.py", "tests/unit/test_order_id_and_followup_rules.py"],
        [],
        [
            {
                "path": "core/stealth_order_manager.py",
                "line": 10,
                "query": "lookup",
                "source": "synthetic",
            },
            {
                "path": "tests/unit/test_order_id_and_followup_rules.py",
                "line": 42,
                "query": "placed_order_id_stealth_lookup",
                "source": "synthetic",
            },
            {
                "path": "tests/unit/test_order_id_and_followup_rules.py",
                "line": 45,
                "query": "placed_order_id",
                "source": "synthetic",
            },
        ],
    )
    top = records[0] if records else {}
    return {
        "case_id": "ERR-001-exact-behavior-over-broad-source",
        "status": "passed"
        if top.get("path") == "tests/unit/test_order_id_and_followup_rules.py"
        and top.get("relevance", {}).get("tier") in {"direct", "strong"}
        else "failed",
        "expected_top_path": "tests/unit/test_order_id_and_followup_rules.py",
        "actual_top_path": top.get("path"),
        "ordered_paths": [record.get("path") for record in records],
        "top_relevance": top.get("relevance"),
        "negative_control": "old category/path ordering ranked the broad source file before the exact behavior test.",
    }


def synthetic_exact_line_case() -> dict[str, Any]:
    records = evidence_file_records(
        ["core/stealth_order_manager.py"],
        [],
        [
            {
                "path": "core/stealth_order_manager.py",
                "line": 10,
                "query": "lookup",
                "source": "synthetic",
            },
            {
                "path": "core/stealth_order_manager.py",
                "line": 250,
                "query": "placed_order_id",
                "source": "synthetic",
            },
        ],
    )
    line_refs = records[0].get("line_refs", []) if records else []
    first_ref = line_refs[0] if line_refs else {}
    return {
        "case_id": "ERR-002-exact-line-over-broad-line",
        "status": "passed" if first_ref.get("query") == "placed_order_id" else "failed",
        "expected_top_query": "placed_order_id",
        "actual_top_query": first_ref.get("query"),
        "ordered_queries": [ref.get("query") for ref in object_list(line_refs)],
        "top_relevance": first_ref.get("relevance"),
        "negative_control": "old line-ref ordering preserved broad match order inside the file.",
    }


def synthetic_request_flow_case() -> dict[str, Any]:
    steps = request_flow_steps_from_matches(
        [
            {
                "path": "api/audit.py",
                "line": 8,
                "text": "request audit metadata",
                "query": "request",
                "source": "synthetic",
            },
            {
                "path": "websocket/z_handler.py",
                "line": 91,
                "text": "if msg_type == 'request_stealth_orders':",
                "query": "request_stealth_orders",
                "source": "synthetic",
            },
        ],
        source_paths={"api/audit.py", "websocket/z_handler.py"},
        behavior="request_stealth_orders",
        beginning_path=None,
        max_steps=5,
    )
    top = steps[0] if steps else {}
    return {
        "case_id": "ERR-003-handler-branch-over-path-sorted-match",
        "status": "passed" if top.get("role") == "handler_branch" else "failed",
        "expected_top_role": "handler_branch",
        "actual_top_role": top.get("role"),
        "ordered_paths": [step.get("path") for step in steps],
        "top_relevance": top.get("relevance"),
        "negative_control": "old request-flow sorting allowed path order to outrank direct handler branch evidence.",
    }


def build_synthetic_report(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    active_policy = policy or load_policy()
    cases = [
        synthetic_exact_behavior_case(),
        synthetic_exact_line_case(),
        synthetic_request_flow_case(),
    ]
    failed = [case for case in cases if case.get("status") != "passed"]
    return {
        "schema_version": 1,
        "phase": "182",
        "policy": {
            "path": str(DEFAULT_POLICY_PATH),
            "minimum_score": active_policy.get("minimum_score"),
            "required_case_ids": string_list(active_policy.get("required_case_ids")),
        },
        "blind_baseline_summary": active_policy.get("blind_baseline_summary"),
        "case_count": len(cases),
        "passed_case_count": len(cases) - len(failed),
        "failed_case_count": len(failed),
        "cases": cases,
        "status": "passed" if not failed else "failed",
    }


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != 1:
        errors.append("policy.schema_version must be 1")
    if policy.get("phase") != "182":
        errors.append("policy.phase must be 182")
    required = set(string_list(policy.get("required_case_ids")))
    missing = REQUIRED_SYNTHETIC_CASE_IDS - required
    if missing:
        errors.append("policy.required_case_ids missing: " + ", ".join(sorted(missing)))
    if not isinstance(policy.get("minimum_score"), int) or policy["minimum_score"] < 85:
        errors.append("policy.minimum_score must be an integer >= 85")
    baseline = policy.get("blind_baseline_summary")
    if not isinstance(baseline, dict):
        errors.append("policy.blind_baseline_summary must be an object")
    else:
        for key in ("ideal_answer_shape", "must_have_ranking_rules", "negative_cases", "rubric"):
            if not string_list(baseline.get(key)):
                errors.append(f"policy.blind_baseline_summary.{key} must be a non-empty string list")
    return errors


def validate_evidence_relevance_ranking_report(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != 1:
        errors.append("report.schema_version must be 1")
    if report.get("phase") != "182":
        errors.append("report.phase must be 182")
    case_ids = {str(case.get("case_id")) for case in object_list(report.get("cases"))}
    missing = REQUIRED_SYNTHETIC_CASE_IDS - case_ids
    if missing:
        errors.append("report.cases missing: " + ", ".join(sorted(missing)))
    for case in object_list(report.get("cases")):
        case_id = str(case.get("case_id"))
        if case.get("status") != "passed":
            errors.append(f"{case_id} did not pass")
        relevance = case.get("top_relevance")
        if not isinstance(relevance, dict):
            errors.append(f"{case_id} missing top_relevance")
        elif relevance.get("tier") not in {"direct", "strong", "supporting", "weak"}:
            errors.append(f"{case_id} has unsupported top_relevance.tier")
        if not isinstance(case.get("negative_control"), str) or not case["negative_control"]:
            errors.append(f"{case_id} missing negative_control")
    if report.get("failed_case_count") != 0 or report.get("status") != "passed":
        errors.append("report status must be passed with zero failed cases")
    return errors

