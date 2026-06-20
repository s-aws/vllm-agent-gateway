from __future__ import annotations

import json
from pathlib import Path

from vllm_agent_gateway.acceptance.eig_pr_merge_readiness import (
    build_report,
    validate_policy,
    validate_report,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "eig_pr_merge_readiness_policy.json"


def load_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def passing_report() -> dict:
    policy = load_policy()
    return build_report(
        policy=policy,
        branch="codex/eig-stable-handoff",
        commit="abc123",
        upstream="origin/codex/eig-stable-handoff",
        status_lines=[],
        docs=[{"path": path, "exists": True, "sha256": "hash"} for path in policy["required_docs"]],
        scripts=[{"path": path, "exists": True, "sha256": "hash"} for path in policy["required_scripts"]],
        phase_status_map={str(phase): "Complete." for phase in policy["required_phases"]},
        tracked_forbidden_paths=[],
        pr={
            "number": 1,
            "state": "OPEN",
            "mergeStateStatus": "CLEAN",
            "headRefName": "codex/eig-stable-handoff",
            "baseRefName": "main",
            "url": "https://github.com/s-aws/vllm-agent-gateway/pull/1",
            "body": "\n".join(policy["required_pr_body_markers"]),
        },
        errors=[],
    )


def test_eig_pr_merge_readiness_policy_passes() -> None:
    assert validate_policy(load_policy()) == []


def test_eig_pr_merge_readiness_report_passes() -> None:
    report = passing_report()

    assert report["status"] == "passed"
    assert report["summary"]["ready_for_founder_merge_decision"] is True
    assert report["summary"]["merge_allowed"] is False
    assert validate_report(report) == []


def test_eig_pr_merge_readiness_rejects_dirty_source() -> None:
    report = passing_report()
    policy = load_policy()
    dirty_report = build_report(
        policy=policy,
        branch="codex/eig-stable-handoff",
        commit="abc123",
        upstream="origin/codex/eig-stable-handoff",
        status_lines=[" M README.md"],
        docs=[{"path": path, "exists": True, "sha256": "hash"} for path in policy["required_docs"]],
        scripts=[{"path": path, "exists": True, "sha256": "hash"} for path in policy["required_scripts"]],
        phase_status_map={str(phase): "Complete." for phase in policy["required_phases"]},
        tracked_forbidden_paths=[],
        pr={
            "number": 1,
            "state": "OPEN",
            "mergeStateStatus": "CLEAN",
            "headRefName": "codex/eig-stable-handoff",
            "baseRefName": "main",
            "body": "\n".join(policy["required_pr_body_markers"]),
        },
        errors=[],
    )

    assert report["status"] == "passed"
    assert dirty_report["status"] == "failed"
    assert any("source must be clean" in error for error in dirty_report["validation_errors"])


def test_eig_pr_merge_readiness_rejects_wrong_branch() -> None:
    policy = load_policy()
    report = build_report(
        policy=policy,
        branch="main",
        commit="abc123",
        upstream="origin/main",
        status_lines=[],
        docs=[{"path": path, "exists": True, "sha256": "hash"} for path in policy["required_docs"]],
        scripts=[{"path": path, "exists": True, "sha256": "hash"} for path in policy["required_scripts"]],
        phase_status_map={str(phase): "Complete." for phase in policy["required_phases"]},
        tracked_forbidden_paths=[],
        pr={
            "number": 1,
            "state": "OPEN",
            "mergeStateStatus": "CLEAN",
            "headRefName": "codex/eig-stable-handoff",
            "baseRefName": "main",
            "body": "\n".join(policy["required_pr_body_markers"]),
        },
        errors=[],
    )

    assert report["status"] == "failed"
    assert any("source.branch must be codex/eig-stable-handoff" in error for error in report["validation_errors"])


def test_eig_pr_merge_readiness_rejects_missing_pr_body_marker() -> None:
    policy = load_policy()
    report = build_report(
        policy=policy,
        branch="codex/eig-stable-handoff",
        commit="abc123",
        upstream="origin/codex/eig-stable-handoff",
        status_lines=[],
        docs=[{"path": path, "exists": True, "sha256": "hash"} for path in policy["required_docs"]],
        scripts=[{"path": path, "exists": True, "sha256": "hash"} for path in policy["required_scripts"]],
        phase_status_map={str(phase): "Complete." for phase in policy["required_phases"]},
        tracked_forbidden_paths=[],
        pr={
            "number": 1,
            "state": "OPEN",
            "mergeStateStatus": "CLEAN",
            "headRefName": "codex/eig-stable-handoff",
            "baseRefName": "main",
            "body": "Phase 307 baseline-candidate intake",
        },
        errors=[],
    )

    assert report["status"] == "failed"
    assert report["pr_body"]["missing_markers"]
