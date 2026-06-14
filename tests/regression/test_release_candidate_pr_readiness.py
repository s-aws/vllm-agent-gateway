from __future__ import annotations

from vllm_agent_gateway.acceptance.release_candidate_pr_readiness import (
    build_report,
    validate_policy,
    validate_report,
)


def policy() -> dict:
    return {
        "schema_version": 1,
        "kind": "release_candidate_pr_readiness_policy",
        "phase": 238,
        "priority_backlog_id": "P0-M14-238",
        "required_decision": "release_candidate_reviewable",
        "branch_prefix": "codex/",
        "required_prior_phases": [232, 233],
        "required_docs": ["README.md"],
        "required_scripts": ["scripts/check_docs_index.py"],
        "forbidden_tracked_path_fragments": ["runtime-state/"],
        "required_known_limit_markers": ["advanced refactor"],
        "acceptance_marker": "RELEASE CANDIDATE PR READINESS PASS",
    }


def passing_report() -> dict:
    return build_report(
        policy=policy(),
        branch="codex/m14-release-clone-proof",
        commit="abc123",
        upstream="origin/codex/m14-release-clone-proof",
        status_lines=[],
        docs=[{"path": "README.md", "exists": True, "sha256": "hash"}],
        scripts=[{"path": "scripts/check_docs_index.py", "exists": True, "sha256": "hash"}],
        phase_status_map={"232": "Complete.", "233": "Complete."},
        forbidden_tracked_paths=[],
        known_limits={"markers": {"advanced refactor": True}},
        errors=[],
    )


def test_release_candidate_pr_readiness_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_release_candidate_pr_readiness_report_passes() -> None:
    report = passing_report()
    assert report["status"] == "passed"
    assert report["decision"] == "release_candidate_reviewable"
    assert validate_report(report, policy()) == []


def test_release_candidate_pr_readiness_rejects_dirty_source() -> None:
    report = passing_report()
    report["source"]["source_clean"] = False
    report["source"]["status_lines"] = [" M README.md"]
    errors = validate_report(report, policy())
    assert any("source_clean" in error for error in errors)


def test_release_candidate_pr_readiness_rejects_runtime_state_tracking() -> None:
    report = passing_report()
    report["hygiene"]["forbidden_tracked_paths"] = ["runtime-state/bad.json"]
    errors = validate_report(report, policy())
    assert any("forbidden_tracked_paths" in error for error in errors)


def test_release_candidate_pr_readiness_rejects_incomplete_prior_phase() -> None:
    report = passing_report()
    report["prior_phases"]["incomplete"] = ["233"]
    errors = validate_report(report, policy())
    assert any("prior_phases.incomplete" in error for error in errors)
