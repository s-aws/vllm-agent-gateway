from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from scripts.validate_evidence_relevance_ranking import main as validate_main
from vllm_agent_gateway.acceptance.evidence_relevance_ranking import (
    build_synthetic_report,
    load_policy,
    validate_evidence_relevance_ranking_report,
    validate_policy,
)


def test_evidence_relevance_ranking_policy_passes() -> None:
    policy = load_policy()

    assert validate_policy(policy) == []


def test_evidence_relevance_ranking_synthetic_report_passes() -> None:
    report = build_synthetic_report()

    assert report["status"] == "passed"
    assert validate_evidence_relevance_ranking_report(report) == []
    assert report["passed_case_count"] == report["case_count"] == 3


def test_evidence_relevance_ranking_rejects_broad_source_as_top_case() -> None:
    report = build_synthetic_report()
    broken = deepcopy(report)
    broken["cases"][0]["actual_top_path"] = "core/stealth_order_manager.py"
    broken["cases"][0]["status"] = "failed"
    broken["failed_case_count"] = 1
    broken["status"] = "failed"

    errors = validate_evidence_relevance_ranking_report(broken)

    assert any("ERR-001-exact-behavior-over-broad-source did not pass" in error for error in errors)


def test_evidence_relevance_ranking_rejects_missing_blind_baseline_policy() -> None:
    policy = load_policy()
    broken = deepcopy(policy)
    broken["blind_baseline_summary"]["negative_cases"] = []

    errors = validate_policy(broken)

    assert "policy.blind_baseline_summary.negative_cases must be a non-empty string list" in errors


def test_validate_evidence_relevance_ranking_script_writes_outputs(tmp_path: Path) -> None:
    output_path = tmp_path / "report.json"
    markdown_path = tmp_path / "report.md"

    assert validate_main(["--output-path", str(output_path), "--markdown-output-path", str(markdown_path)]) == 0

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert markdown_path.read_text(encoding="utf-8").startswith("# Evidence Relevance Ranking Report")

