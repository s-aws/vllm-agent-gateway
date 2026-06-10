from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.founder_smoke_feedback import (
    build_founder_smoke_feedback_report,
    read_json_object,
    validate_founder_smoke_feedback_report,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE_REPORT_PATH = REPO_ROOT / "runtime-state" / "founder-field-tests" / "phase134-founder-smoke.json"


def smoke_report() -> dict[str, Any]:
    return read_json_object(SMOKE_REPORT_PATH)


def project_report(smoke: dict[str, Any] | None = None) -> dict[str, Any]:
    return build_founder_smoke_feedback_report(
        smoke_report=smoke or smoke_report(),
        smoke_report_path=SMOKE_REPORT_PATH,
    )


def validate_report(report: dict[str, Any], smoke: dict[str, Any] | None = None) -> list[str]:
    return validate_founder_smoke_feedback_report(
        report,
        smoke_report=smoke or smoke_report(),
        smoke_report_path=SMOKE_REPORT_PATH,
    )


def test_project_founder_smoke_feedback_has_no_current_actionable_items() -> None:
    report = project_report()
    assert validate_report(report) == []
    assert report["status"] == "passed"
    assert report["summary"]["smoke_case_count"] == 4
    assert report["summary"]["failed_smoke_case_count"] == 0
    assert report["summary"]["classification_count"] == 0
    assert report["summary"]["actionable_feedback_count"] == 0


def test_founder_smoke_feedback_classifies_output_contract_miss() -> None:
    smoke = copy.deepcopy(smoke_report())
    smoke["status"] = "failed"
    smoke["summary"] = {"passed": 3, "failed": 1}
    smoke["cases"][0]["status"] = "failed"
    smoke["cases"][0]["missing_markers"] = ["Answer:"]
    report = project_report(smoke)
    assert validate_report(report, smoke) == []
    assert report["summary"]["classification_count"] == 1
    assert report["classifications"][0]["decision_kind"] == "repair_followup"
    assert report["classifications"][0]["gap_class"] == "deterministic_formatter"


def test_founder_smoke_feedback_classifies_semantic_miss() -> None:
    smoke = copy.deepcopy(smoke_report())
    smoke["status"] = "failed"
    smoke["summary"] = {"passed": 3, "failed": 1}
    smoke["cases"][0]["status"] = "failed"
    smoke["cases"][0]["missing_semantic_markers"] = ["Related tests:"]
    report = project_report(smoke)
    assert report["classifications"][0]["gap_class"] == "model_capability"


def test_founder_smoke_feedback_rejects_fixture_mutation() -> None:
    smoke = copy.deepcopy(smoke_report())
    smoke["fixture_state_after"] = {"changed": True}
    report = project_report(smoke)
    assert "smoke report fixture state changed" in report["errors"]
    assert report["status"] == "failed"


def test_founder_smoke_feedback_rejects_hidden_classification_change() -> None:
    report = project_report()
    report["summary"]["classification_count"] = 99
    errors = validate_report(report)
    assert any("must match rebuilt founder smoke feedback classification" in error for error in errors)
