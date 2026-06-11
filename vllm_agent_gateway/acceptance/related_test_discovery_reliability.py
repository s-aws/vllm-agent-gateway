"""Acceptance checks for related-test discovery reliability."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from vllm_agent_gateway.controllers.verification import (
    controller_verification_commands,
    discover_related_tests_from_values,
)


DEFAULT_POLICY_PATH = Path("runtime/related_test_discovery_reliability_policy.json")
REQUIRED_CASE_IDS = {
    "RTD-001-direct-test-outranks-comment",
    "RTD-002-command-carries-evidence",
    "RTD-003-no-bounded-test-evidence",
}


def string_list(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def object_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_policy(path: Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != 1:
        errors.append("policy.schema_version must be 1")
    if policy.get("phase") != "183":
        errors.append("policy.phase must be 183")
    missing = REQUIRED_CASE_IDS - set(string_list(policy.get("required_case_ids")))
    if missing:
        errors.append("policy.required_case_ids missing: " + ", ".join(sorted(missing)))
    if not isinstance(policy.get("minimum_score"), int) or policy["minimum_score"] < 85:
        errors.append("policy.minimum_score must be an integer >= 85")
    baseline = policy.get("blind_baseline_summary")
    if not isinstance(baseline, dict):
        errors.append("policy.blind_baseline_summary must be an object")
    else:
        for key in ("ideal_answer_shape", "must_have_rules", "negative_cases", "rubric"):
            if not string_list(baseline.get(key)):
                errors.append(f"policy.blind_baseline_summary.{key} must be a non-empty string list")
    return errors


def build_fixture(root: Path) -> Path:
    target = root / "repo"
    write_text(
        target / "tests" / "unit" / "test_direct_lookup.py",
        "def test_placed_order_id_stealth_lookup_uses_manager_index():\n"
        "    assert 'placed_order_id'\n",
    )
    write_text(
        target / "tests" / "unit" / "test_incidental_lookup.py",
        "# placed_order_id appears here, but this is not behavior coverage.\n"
        "def test_unrelated_behavior():\n"
        "    assert True\n",
    )
    write_text(target / "tests" / "unit" / "test_unrelated.py", "def test_unrelated():\n    assert True\n")
    return target


def build_synthetic_report(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    active_policy = policy or load_policy()
    with tempfile.TemporaryDirectory() as tmp:
        target = build_fixture(Path(tmp))
        context = discover_related_tests_from_values(
            target,
            ["Find tests related to placed_order_id stealth lookup."],
            max_files=5,
        )
        related = context.get("related_test_files", []) if isinstance(context, dict) else []
        commands = controller_verification_commands({"results": [context]} if context else {"results": []})
        no_context = discover_related_tests_from_values(
            target,
            ["Find tests related to resolve_payment_timeout."],
            max_files=5,
        )
    first = related[0] if related else {}
    cases = [
        {
            "case_id": "RTD-001-direct-test-outranks-comment",
            "status": "passed"
            if first.get("path") == "tests/unit/test_direct_lookup.py"
            and first.get("evidence_kind") == "direct"
            and first.get("confidence") == "high"
            else "failed",
            "actual_top_path": first.get("path"),
            "actual_top_evidence_kind": first.get("evidence_kind"),
            "actual_top_confidence": first.get("confidence"),
            "negative_control": "comment-only evidence must not outrank a direct test definition.",
        },
        {
            "case_id": "RTD-002-command-carries-evidence",
            "status": "passed"
            if commands
            and commands[0].get("command") == ["python", "-m", "pytest", "tests/unit/test_direct_lookup.py"]
            and commands[0].get("confidence") == "high"
            and commands[0].get("evidence_kind") == "direct"
            and commands[0].get("source_refs")
            else "failed",
            "actual_command": commands[0].get("command") if commands else None,
            "actual_confidence": commands[0].get("confidence") if commands else None,
            "negative_control": "verification commands must carry evidence and confidence, not only a path.",
        },
        {
            "case_id": "RTD-003-no-bounded-test-evidence",
            "status": "passed" if no_context is None else "failed",
            "actual_context": no_context,
            "negative_control": "no-test cases must not invent a related test file.",
        },
    ]
    failed = [case for case in cases if case["status"] != "passed"]
    return {
        "schema_version": 1,
        "phase": "183",
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


def validate_related_test_discovery_reliability_report(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != 1:
        errors.append("report.schema_version must be 1")
    if report.get("phase") != "183":
        errors.append("report.phase must be 183")
    case_ids = {str(case.get("case_id")) for case in object_list(report.get("cases"))}
    missing = REQUIRED_CASE_IDS - case_ids
    if missing:
        errors.append("report.cases missing: " + ", ".join(sorted(missing)))
    for case in object_list(report.get("cases")):
        if case.get("status") != "passed":
            errors.append(f"{case.get('case_id')} did not pass")
        if not isinstance(case.get("negative_control"), str) or not case["negative_control"]:
            errors.append(f"{case.get('case_id')} missing negative_control")
    if report.get("failed_case_count") != 0 or report.get("status") != "passed":
        errors.append("report status must be passed with zero failed cases")
    return errors

