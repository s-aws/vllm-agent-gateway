from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from scripts.validate_related_test_discovery_reliability import main as validate_main
from vllm_agent_gateway.acceptance.related_test_discovery_reliability import (
    build_synthetic_report,
    load_policy,
    validate_policy,
    validate_related_test_discovery_reliability_report,
)


def test_related_test_discovery_reliability_policy_passes() -> None:
    assert validate_policy(load_policy()) == []


def test_related_test_discovery_reliability_synthetic_report_passes() -> None:
    report = build_synthetic_report()

    assert report["status"] == "passed"
    assert report["passed_case_count"] == report["case_count"] == 3
    assert validate_related_test_discovery_reliability_report(report) == []


def test_related_test_discovery_reliability_rejects_failed_direct_case() -> None:
    report = build_synthetic_report()
    broken = deepcopy(report)
    broken["cases"][0]["status"] = "failed"
    broken["failed_case_count"] = 1
    broken["status"] = "failed"

    errors = validate_related_test_discovery_reliability_report(broken)

    assert any("RTD-001-direct-test-outranks-comment did not pass" in error for error in errors)


def test_related_test_discovery_reliability_rejects_missing_policy_baseline() -> None:
    policy = load_policy()
    broken = deepcopy(policy)
    broken["blind_baseline_summary"]["negative_cases"] = []

    errors = validate_policy(broken)

    assert "policy.blind_baseline_summary.negative_cases must be a non-empty string list" in errors


def test_validate_related_test_discovery_reliability_script_writes_outputs(tmp_path: Path) -> None:
    output_path = tmp_path / "report.json"
    markdown_path = tmp_path / "report.md"

    assert validate_main(["--output-path", str(output_path), "--markdown-output-path", str(markdown_path)]) == 0

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert markdown_path.read_text(encoding="utf-8").startswith("# Related-Test Discovery Reliability Report")

