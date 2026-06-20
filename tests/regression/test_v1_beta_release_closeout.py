from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from vllm_agent_gateway.acceptance import v1_beta_release_closeout as closeout
from vllm_agent_gateway.acceptance.v1_beta_release_closeout import (
    DEFAULT_POLICY_PATH,
    V1BetaReleaseCloseoutConfig,
    build_v1_beta_release_closeout_report,
    read_json_object,
    run_v1_beta_release_closeout,
    validate_policy,
    validate_v1_beta_release_closeout_report,
    write_json,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH
pytestmark = pytest.mark.serial


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def source_payload(report_id: str) -> dict[str, Any]:
    payloads = {
        "release_candidate_founder_trial_pack": {
            "kind": "release_candidate_founder_trial_pack_report",
            "phase": 195,
            "status": "passed",
            "summary": {"validation_error_count": 0},
            "validation_errors": [],
        },
        "v1_product_readiness_reassessment": {
            "kind": "v1_product_readiness_reassessment_report",
            "phase": 196,
            "status": "passed",
            "recommendation": "release_for_broader_founder_beta",
            "summary": {"validation_error_count": 0},
            "validation_errors": [],
        },
        "v1_product_readiness_live_proof": {
            "kind": "v1_product_readiness_reassessment_live_proof",
            "phase": 196,
            "status": "passed",
            "summary": {"validation_error_count": 0, "error_count": 0, "fixture_integrity": "passed"},
            "validation_errors": [],
        },
        "founder_trial_execution_round": {
            "kind": "founder_trial_execution_round_report",
            "phase": 197,
            "status": "passed",
            "quality_status": "advisory",
            "summary": {
                "validation_error_count": 0,
                "classification_counts": {"pass": 10, "advisory": 4, "blocker": 0},
            },
            "validation_errors": [],
        },
        "founder_feedback_intake_repair": {
            "kind": "founder_feedback_intake_repair_report",
            "phase": 198,
            "status": "passed",
            "summary": {
                "validation_error_count": 0,
                "phase199_blocked": False,
                "phase199_ready_after_intake": True,
                "release_blocker_count": 0,
                "open_required_repair_count": 0,
            },
            "validation_errors": [],
        },
    }
    return copy.deepcopy(payloads[report_id])


def fake_sources(tmp_path: Path, custom: dict[str, dict[str, Any]] | None = None) -> dict[str, tuple[Path, dict[str, Any]]]:
    sources: dict[str, tuple[Path, dict[str, Any]]] = {}
    custom = custom or {}
    for item in closeout.object_list(policy().get("required_reports")):
        report_id = str(item["id"])
        payload = custom.get(report_id) or source_payload(report_id)
        path = tmp_path / f"{report_id}.json"
        write_json(path, payload)
        sources[report_id] = (path, read_json_object(path))
    return sources


def clean_fixtures() -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    return (
        [
            {"root": "/mnt/c/coinbase_testing_repo_frozen_tmp", "exists": True, "clean": True},
            {"root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github", "exists": True, "clean": True, "git_status": ""},
        ],
        [],
    )


def build_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, custom: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    monkeypatch.setattr(closeout, "fixture_records", lambda _policy: clean_fixtures())
    return build_v1_beta_release_closeout_report(
        config_root=REPO_ROOT,
        policy=policy(),
        sources=fake_sources(tmp_path, custom),
        source_load_errors=[],
        policy_path=POLICY_PATH,
    )


def error_ids(report: dict[str, Any]) -> set[str]:
    return {str(item.get("id")) for item in report["validation_errors"]}


def test_v1_beta_release_closeout_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_v1_beta_release_closeout_report_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = build_report(tmp_path, monkeypatch)

    assert report["status"] == "passed"
    assert report["decision"] == "release_for_founder_beta"
    assert report["summary"]["phase199_blocked"] is False
    assert report["summary"]["required_report_count"] == 5


def test_v1_beta_release_closeout_blocks_when_phase198_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    phase198 = source_payload("founder_feedback_intake_repair")
    phase198["summary"]["phase199_blocked"] = True

    report = build_report(tmp_path, monkeypatch, {"founder_feedback_intake_repair": phase198})

    assert report["status"] == "failed"
    assert report["decision"] == "blocked"
    assert "phase198.phase199_blocked" in error_ids(report)


def test_v1_beta_release_closeout_rejects_wrong_readiness_recommendation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readiness = source_payload("v1_product_readiness_reassessment")
    readiness["recommendation"] = "priority0_repair_cycle_required"

    report = build_report(tmp_path, monkeypatch, {"v1_product_readiness_reassessment": readiness})

    assert report["status"] == "failed"
    assert "reports.v1_product_readiness_reassessment.recommendation" in error_ids(report)


def test_v1_beta_release_closeout_rejects_missing_doc_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_policy = copy.deepcopy(policy())
    test_policy["required_doc_markers"]["README.release-notes.md"] = ["not-present-marker"]
    monkeypatch.setattr(closeout, "fixture_records", lambda _policy: clean_fixtures())

    report = build_v1_beta_release_closeout_report(
        config_root=REPO_ROOT,
        policy=test_policy,
        sources=fake_sources(tmp_path),
        source_load_errors=[],
        policy_path=POLICY_PATH,
    )

    assert report["status"] == "failed"
    assert "docs.README.release-notes.md.markers" in error_ids(report)


def test_v1_beta_release_closeout_rejects_dirty_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def dirty_fixtures() -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        return (
            [{"root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github", "exists": True, "clean": False, "git_status": " M README.md"}],
            [closeout.validation_error("fixtures.git.dirty", "git fixture must be clean", "critical", "fixtures")],
        )

    monkeypatch.setattr(closeout, "fixture_records", lambda _policy: dirty_fixtures())

    report = build_v1_beta_release_closeout_report(
        config_root=REPO_ROOT,
        policy=policy(),
        sources=fake_sources(tmp_path),
        source_load_errors=[],
        policy_path=POLICY_PATH,
    )

    assert report["status"] == "failed"
    assert "fixtures.git.dirty" in error_ids(report)


def test_v1_beta_release_closeout_rejects_hidden_report_edit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = build_report(tmp_path, monkeypatch)
    report["summary"]["required_report_count"] = 999
    sources = fake_sources(tmp_path)

    errors = validate_v1_beta_release_closeout_report(
        report,
        config_root=REPO_ROOT,
        policy=policy(),
        sources=sources,
        source_load_errors=[],
        policy_path=POLICY_PATH,
    )

    assert errors == ["report must match rebuilt V1 beta release closeout report"]


def test_v1_beta_release_closeout_project_report_passes_when_artifacts_exist() -> None:
    required_artifacts = [
        REPO_ROOT / str(item["path"])
        for item in closeout.object_list(policy().get("required_reports"))
    ]
    if not all(path.is_file() for path in required_artifacts):
        return

    report = run_v1_beta_release_closeout(
        V1BetaReleaseCloseoutConfig(config_root=REPO_ROOT, policy_path=DEFAULT_POLICY_PATH)
    )

    assert report["status"] == "passed"
    assert report["decision"] == "release_for_founder_beta"
