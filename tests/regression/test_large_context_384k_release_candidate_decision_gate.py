from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance import large_context_384k_release_candidate_decision_gate as phase265
from vllm_agent_gateway.acceptance.large_context_384k_release_candidate_decision_gate import (
    DEFAULT_POLICY_PATH,
    LargeContext384kReleaseCandidateDecisionGateConfig,
    read_json_object,
    validate_large_context_384k_release_candidate_decision_gate,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def write_doc(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        text
        or "\n".join(
            [
                "usable 384k-token projects",
                "raw 384k prompt stuffing",
                "Work above 384k tokens remains paused",
                "Advanced broad refactor orchestration is not released",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def write_roadmap(config_root: Path, *, missing_phase: int | None = None) -> None:
    lines = []
    for phase in range(258, 265):
        lines.extend(
            [
                f"### Approved Phase {phase}: Synthetic Phase {phase}",
                "",
                "Status: Approved." if phase == missing_phase else "Status: Complete.",
                "",
            ]
        )
    write_doc(config_root / "docs" / "ACTIONABLE_WORKFLOW_ROADMAP.md", "\n".join(lines))


def phase264_report(**summary_overrides: object) -> dict:
    summary = {
        "target_estimated_project_tokens": 384000,
        "response_count": 18,
        "gateway_response_count": 9,
        "anythingllm_response_count": 9,
        "failed_small_repo_regression_count": 0,
        "critical_or_high_finding_count": 0,
        "json_default_parity_status": "passed",
        "target_settings_status": "passed",
        "strategy_ids": [
            "artifact_paging",
            "chunked_investigation",
            "refusal",
            "retrieval",
            "summarization",
        ],
        "static_gate_count": 5,
        "passed_static_gate_count": 5,
        "runtime_state_ignored": True,
        "source_branch": "codex/m14-release-clone-proof",
        "source_remote_origin_url": "https://github.com/s-aws/vllm-agent-gateway.git",
        "source_dirty_line_count_before": 0,
        "source_dirty_line_count_after": 0,
        "phase265_ready": True,
    }
    summary.update(summary_overrides)
    return {
        "kind": "large_context_384k_clean_clone_replay_report",
        "status": "passed",
        "decision": "phase264_clean_clone_384k_usability_ready",
        "summary": summary,
        "static_gates": {
            "docs_index": {"status": "passed", "summary": {}},
            "phase251_objective_rebaseline": {"status": "passed", "summary": {}},
            "phase258_acceptance_contract": {"status": "passed", "summary": {}},
            "phase259_fixture_index_readiness": {"status": "passed", "summary": {}},
            "phase260_stale_index_rejection": {"status": "passed", "summary": {}},
        },
    }


def config_root(
    tmp_path: Path,
    *,
    missing_phase: int | None = None,
    missing_phase264: bool = False,
    phase264_summary_overrides: dict[str, object] | None = None,
) -> tuple[Path, Path, Path]:
    root = tmp_path / "config"
    policy_value = copy.deepcopy(policy())
    write_roadmap(root, missing_phase=missing_phase)
    for raw_path in policy_value["required_docs"]:
        if raw_path == "docs/ACTIONABLE_WORKFLOW_ROADMAP.md":
            continue
        write_doc(root / raw_path)
    phase264_path = root / "runtime-state" / "phase264" / "phase264-report.json"
    if not missing_phase264:
        phase265.write_json(phase264_path, phase264_report(**(phase264_summary_overrides or {})))
    policy_path = root / "policy.json"
    phase265.write_json(policy_path, policy_value)
    return root, policy_path, phase264_path


def test_phase265_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase265_synthetic_ship_when_phase264_proof_and_health_pass(tmp_path: Path, monkeypatch) -> None:
    root, policy_path, phase264_path = config_root(tmp_path)
    monkeypatch.setattr(phase265, "probe_url", lambda url, timeout_seconds: {"url": url, "status_code": 200, "passed": True})

    report = validate_large_context_384k_release_candidate_decision_gate(
        LargeContext384kReleaseCandidateDecisionGateConfig(
            config_root=root,
            policy_path=policy_path,
            phase264_report_path=phase264_path,
            output_path="runtime-state/phase265/report.json",
            markdown_output_path="runtime-state/phase265/report.md",
        )
    )

    assert report["status"] == "passed"
    assert report["decision"] == "ship"
    assert report["summary"]["phase266_ready"] is True
    assert report["blockers"] == []


def test_phase265_synthetic_hold_when_only_runtime_health_fails(tmp_path: Path, monkeypatch) -> None:
    root, policy_path, phase264_path = config_root(tmp_path)
    monkeypatch.setattr(phase265, "probe_url", lambda url, timeout_seconds: {"url": url, "status_code": None, "passed": False, "error": "down"})

    report = validate_large_context_384k_release_candidate_decision_gate(
        LargeContext384kReleaseCandidateDecisionGateConfig(
            config_root=root,
            policy_path=policy_path,
            phase264_report_path=phase264_path,
            output_path="runtime-state/phase265/report.json",
            markdown_output_path="runtime-state/phase265/report.md",
        )
    )

    assert report["decision"] == "hold"
    assert report["summary"]["runtime_health_blocker_count"] == len(policy()["required_runtime_health"])


def test_phase265_synthetic_repair_when_phase264_report_missing(tmp_path: Path, monkeypatch) -> None:
    root, policy_path, phase264_path = config_root(tmp_path, missing_phase264=True)
    monkeypatch.setattr(phase265, "probe_url", lambda url, timeout_seconds: {"url": url, "status_code": 200, "passed": True})

    report = validate_large_context_384k_release_candidate_decision_gate(
        LargeContext384kReleaseCandidateDecisionGateConfig(
            config_root=root,
            policy_path=policy_path,
            phase264_report_path=phase264_path,
            output_path="runtime-state/phase265/report.json",
            markdown_output_path="runtime-state/phase265/report.md",
        )
    )

    assert report["decision"] == "repair_required"
    assert any(item["id"] == "phase264_report.missing" for item in report["blockers"])


def test_phase265_synthetic_repair_when_phase264_strategy_missing(tmp_path: Path, monkeypatch) -> None:
    root, policy_path, phase264_path = config_root(tmp_path, phase264_summary_overrides={"strategy_ids": ["retrieval"]})
    monkeypatch.setattr(phase265, "probe_url", lambda url, timeout_seconds: {"url": url, "status_code": 200, "passed": True})

    report = validate_large_context_384k_release_candidate_decision_gate(
        LargeContext384kReleaseCandidateDecisionGateConfig(
            config_root=root,
            policy_path=policy_path,
            phase264_report_path=phase264_path,
            output_path="runtime-state/phase265/report.json",
            markdown_output_path="runtime-state/phase265/report.md",
        )
    )

    assert report["decision"] == "repair_required"
    assert any(item["id"] == "phase264.summary.strategy_ids" for item in report["blockers"])


def test_phase265_synthetic_repair_when_required_phase_incomplete(tmp_path: Path, monkeypatch) -> None:
    root, policy_path, phase264_path = config_root(tmp_path, missing_phase=264)
    monkeypatch.setattr(phase265, "probe_url", lambda url, timeout_seconds: {"url": url, "status_code": 200, "passed": True})

    report = validate_large_context_384k_release_candidate_decision_gate(
        LargeContext384kReleaseCandidateDecisionGateConfig(
            config_root=root,
            policy_path=policy_path,
            phase264_report_path=phase264_path,
            output_path="runtime-state/phase265/report.json",
            markdown_output_path="runtime-state/phase265/report.md",
        )
    )

    assert report["decision"] == "repair_required"
    assert any(item["id"] == "phase.264.status" for item in report["blockers"])


def test_phase265_policy_rejects_post_384k_target() -> None:
    mutated = copy.deepcopy(policy())
    mutated["required_phase264_report"]["required_target_estimated_project_tokens"] = 1_000_000

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.required_phase264_report.target" for item in errors)
