from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.m5_generalization_closeout import (
    DEFAULT_POLICY_PATH,
    M5GeneralizationCloseoutConfig,
    build_report,
    read_json_object,
    run_m5_generalization_closeout,
    validate_policy,
    validate_required_reports,
    write_json,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def test_m5_generalization_closeout_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_m5_generalization_closeout_project_report_passes() -> None:
    report = run_m5_generalization_closeout(M5GeneralizationCloseoutConfig(config_root=REPO_ROOT))

    assert report["status"] == "passed"
    assert report["decision"] == "close_m5_move_to_m6"
    assert report["summary"]["m5_closed"] is True


def test_m5_generalization_closeout_rejects_phase212_gaps(tmp_path: Path) -> None:
    test_policy = copy.deepcopy(policy())
    phase212 = {
        "kind": "multi_repo_live_generalization_rerun_report",
        "phase": 212,
        "status": "passed",
        "summary": {"gap_response_count": 1, "phase213_ready": False, "repository_count": 3, "response_count": 18},
    }
    phase212_path = tmp_path / "phase212.json"
    write_json(phase212_path, phase212)
    for spec in test_policy["required_reports"]:
        if spec["id"] == "phase212_live_generalization_rerun":
            spec["path"] = str(phase212_path)
    sources = {
        spec["id"]: (REPO_ROOT / spec["path"], read_json_object(REPO_ROOT / spec["path"]))
        for spec in test_policy["required_reports"]
        if spec["id"] != "phase212_live_generalization_rerun"
    }
    sources["phase212_live_generalization_rerun"] = (phase212_path, phase212)

    errors = validate_required_reports(test_policy, sources)

    assert any(item["id"] == "reports.phase212_live_generalization_rerun.summary.gap_response_count" for item in errors)


def test_m5_generalization_closeout_blocks_when_validation_errors_exist() -> None:
    report = build_report(
        config_root=REPO_ROOT,
        policy=policy(),
        policy_path=POLICY_PATH,
        sources={},
        validation_errors=[{"id": "x", "severity": "high", "source": "test", "message": "blocked"}],
    )

    assert report["status"] == "failed"
    assert report["decision"] == "blocked"
