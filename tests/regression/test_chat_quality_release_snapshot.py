from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.chat_quality_release_snapshot import (
    build_snapshot_report,
    read_json_object,
    validate_policy,
    validate_snapshot_report,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "chat_quality_release_snapshot_policy.json"


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def project_report(policy_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return build_snapshot_report(config_root=REPO_ROOT, policy=policy_payload or policy(), policy_path=POLICY_PATH)


def validate_report(report: dict[str, Any], policy_payload: dict[str, Any] | None = None) -> list[str]:
    return validate_snapshot_report(report, config_root=REPO_ROOT, policy=policy_payload or policy(), policy_path=POLICY_PATH)


def test_project_chat_quality_release_snapshot_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_project_chat_quality_release_snapshot_passes() -> None:
    report = project_report()
    assert validate_report(report) == []
    assert report["status"] == "passed"
    assert report["summary"]["release_readiness"] == "ready_for_founder_testing"
    assert report["summary"]["founder_smoke_failed"] == 0
    assert report["summary"]["actionable_feedback_count"] == 0


def test_snapshot_rejects_missing_required_artifact() -> None:
    broken = policy()
    broken["required_artifacts"][0]["path"] = "runtime-state/missing-release.json"
    report = project_report(broken)
    assert "required artifact missing: stable_chat_quality_release" in report["errors"]
    assert report["status"] == "failed"


def test_snapshot_rejects_unready_release_report() -> None:
    broken = policy()
    broken["required_artifacts"][0]["path"] = "runtime-state/stable-chat-quality-release/phase130/missing-ready.json"
    report = project_report(broken)
    assert any("stable_chat_quality_release.readiness" in error for error in report["errors"])


def test_snapshot_rejects_hidden_summary_change() -> None:
    report = project_report()
    report["summary"]["artifact_count"] = 999
    errors = validate_report(report)
    assert any("report.summary must match rebuilt release snapshot" in error for error in errors)


def test_snapshot_rejects_missing_doc() -> None:
    broken = copy.deepcopy(policy())
    broken["required_docs"].append("docs/does-not-exist.md")
    report = project_report(broken)
    assert any("required doc missing" in error for error in report["errors"])
