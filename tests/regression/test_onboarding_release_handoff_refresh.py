from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.onboarding_release_handoff_refresh import (
    DEFAULT_POLICY_PATH,
    build_onboarding_release_handoff_refresh_report,
    read_json_object,
    validate_onboarding_release_handoff_refresh_report,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def error_ids(report: dict[str, Any]) -> set[str]:
    return {str(item.get("id")) for item in report["validation_errors"]}


def test_phase232_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase232_report_passes_current_docs() -> None:
    report = build_onboarding_release_handoff_refresh_report(
        config_root=REPO_ROOT,
        policy=policy(),
        policy_path=POLICY_PATH,
    )

    assert report["status"] == "passed"
    assert report["decision"] == "handoff_ready"
    assert report["summary"]["missing_doc_count"] == 0
    assert report["summary"]["docs_with_missing_marker_count"] == 0
    assert report["summary"]["docs_with_forbidden_marker_count"] == 0
    assert report["summary"]["missing_command_count"] == 0


def test_phase232_rejects_missing_required_marker() -> None:
    mutated = copy.deepcopy(policy())
    mutated["required_doc_markers"]["README.getting-started.md"].append("not-present-phase232-marker")

    report = build_onboarding_release_handoff_refresh_report(
        config_root=REPO_ROOT,
        policy=mutated,
        policy_path=POLICY_PATH,
    )

    assert report["status"] == "failed"
    assert "docs.README.getting-started.md.required_markers" in error_ids(report)


def test_phase232_rejects_forbidden_stale_marker() -> None:
    mutated = copy.deepcopy(policy())
    mutated["forbidden_doc_markers"]["README.getting-started.md"].append("Phase 232")

    report = build_onboarding_release_handoff_refresh_report(
        config_root=REPO_ROOT,
        policy=mutated,
        policy_path=POLICY_PATH,
    )

    assert report["status"] == "failed"
    assert "docs.README.getting-started.md.forbidden_markers" in error_ids(report)


def test_phase232_rejects_missing_required_command() -> None:
    mutated = copy.deepcopy(policy())
    mutated["required_commands"].append("python3 scripts/not_a_real_phase232_command.py")

    report = build_onboarding_release_handoff_refresh_report(
        config_root=REPO_ROOT,
        policy=mutated,
        policy_path=POLICY_PATH,
    )

    assert report["status"] == "failed"
    assert any(error_id.startswith("commands.python3 scripts/not_a_real_phase232_command.py") for error_id in error_ids(report))


def test_phase232_rejects_hidden_summary_edit() -> None:
    current_policy = policy()
    report = build_onboarding_release_handoff_refresh_report(
        config_root=REPO_ROOT,
        policy=current_policy,
        policy_path=POLICY_PATH,
    )
    edited = copy.deepcopy(report)
    edited["summary"]["doc_count"] = 999

    errors = validate_onboarding_release_handoff_refresh_report(
        edited,
        config_root=REPO_ROOT,
        policy=current_policy,
        policy_path=POLICY_PATH,
    )

    assert errors == ["report must match rebuilt onboarding release handoff refresh report"]
