from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.multi_repo_baseline_comparison import (
    DEFAULT_POLICY_PATH,
    MultiRepoBaselineComparisonConfig,
    classify_gap,
    read_json_object,
    validate_multi_repo_baseline_comparison,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def policy() -> dict:
    return read_json_object(REPO_ROOT / DEFAULT_POLICY_PATH)


def phase209_policy() -> dict:
    return read_json_object(REPO_ROOT / "runtime" / "multi_repo_fixture_baseline_pack_policy.json")


def test_phase210_policy_preflight_passes() -> None:
    errors, source_policy, source_report = validate_policy(policy(), config_root=REPO_ROOT)

    assert errors == []
    assert source_policy["phase"] == 209
    assert source_report["status"] == "passed"


def test_phase210_validator_writes_preflight_report(tmp_path: Path) -> None:
    report = validate_multi_repo_baseline_comparison(
        MultiRepoBaselineComparisonConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase210-report.json",
            markdown_output_path=tmp_path / "phase210-report.md",
            live=False,
        )
    )

    assert report["status"] == "preflight_passed"
    assert report["summary"]["case_count"] == 5
    assert report["summary"]["response_count"] == 0
    assert (tmp_path / "phase210-report.json").is_file()
    assert (tmp_path / "phase210-report.md").read_text(encoding="utf-8").startswith("# Multi-Repo Baseline Comparison")


def test_phase210_policy_rejects_missing_phase209_report(tmp_path: Path) -> None:
    mutated = copy.deepcopy(policy())
    mutated["phase209_report_path"] = str(tmp_path / "missing.json")

    errors, _, _ = validate_policy(mutated, config_root=REPO_ROOT)

    assert any("phase209 report missing" in error for error in errors)


def test_phase210_policy_rejects_missing_surface() -> None:
    mutated = copy.deepcopy(policy())
    mutated["required_surfaces"] = ["gateway"]

    errors, _, _ = validate_policy(mutated, config_root=REPO_ROOT)

    assert any("required_surfaces must include gateway and anythingllm" in error for error in errors)


def test_phase210_classify_gap_passes_clean_response() -> None:
    case = phase209_policy()["cases"][0]
    text = "\n".join(
        [
            "Answer:",
            "actions/gateway.py",
            "tests/regression/test_action_gateway.py",
            "Source mutation: false",
        ]
    )
    run_record = {
        "status": "completed",
        "summary": {
            "selected_workflow": "code_investigation.plan",
            "downstream_status": "completed",
            "source_changed": False,
        },
    }

    score, gaps, errors = classify_gap(case=case, text=text, run_record=run_record, required_markers=["Answer:", "Source mutation: false"])

    assert score == 100
    assert gaps == ["none"]
    assert errors == []


def test_phase210_classify_gap_detects_evidence_and_formatter_gap() -> None:
    case = phase209_policy()["cases"][0]
    run_record = {
        "status": "completed",
        "summary": {
            "selected_workflow": "code_investigation.plan",
            "downstream_status": "completed",
            "source_changed": False,
        },
    }

    score, gaps, errors = classify_gap(case=case, text="Answer:\nNo direct paths.", run_record=run_record, required_markers=["Answer:", "Source mutation: false"])

    assert score < 100
    assert "formatter_gap" in gaps
    assert "evidence_gap" in gaps
    assert errors


def test_phase210_classify_gap_detects_route_gap() -> None:
    case = phase209_policy()["cases"][0]
    text = "Answer:\nactions/gateway.py\nSource mutation: false"
    run_record = {
        "status": "completed",
        "summary": {
            "selected_workflow": "task.decompose",
            "downstream_status": "completed",
            "source_changed": False,
        },
    }

    _, gaps, errors = classify_gap(case=case, text=text, run_record=run_record, required_markers=["Answer:", "Source mutation: false"])

    assert "route_gap" in gaps
    assert any("selected_workflow expected" in error for error in errors)


def test_phase211_start_script_includes_approved_staterail_fixture_root() -> None:
    script = (REPO_ROOT / "start-agent-prompt-proxies.sh").read_text(encoding="utf-8")

    assert "/mnt/c/staterail_testing_repo_frozen_tmp.github" in script
    assert "DEFAULT_CONTROLLER_ALLOWED_TARGET_ROOTS" in script
