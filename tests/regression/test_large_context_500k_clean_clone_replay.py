from __future__ import annotations

import copy
from pathlib import Path

import pytest

import vllm_agent_gateway.acceptance.large_context_500k_clean_clone_replay as phase275
from vllm_agent_gateway.acceptance.large_context_500k_clean_clone_replay import (
    DEFAULT_POLICY_PATH,
    LargeContext500kCleanCloneReplayConfig,
    LargeContext500kCleanCloneReplayStatus,
    read_json_object,
    validate_large_context_500k_clean_clone_replay,
    validate_policy,
    write_json,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def write_doc(path: Path, markers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(markers) + "\n", encoding="utf-8")


def temp_config(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "config"
    value = copy.deepcopy(policy())
    for raw_path in value["required_docs"]:
        write_doc(root / raw_path, value["required_doc_markers"].get(raw_path, []))
    policy_path = root / "policy.json"
    write_json(policy_path, value)
    return root, policy_path


def git_state(*, dirty: int = 0) -> dict:
    return {
        "inside_work_tree": True,
        "branch": "codex/m14-release-clone-proof",
        "commit": "abc123",
        "remote_origin_url": "https://github.com/s-aws/vllm-agent-gateway.git",
        "status_returncode": 0,
        "status_short": " M README.md" if dirty else "",
        "dirty_line_count": dirty,
        "runtime_state_ignored": True,
    }


def gates(*, phase273_status: str = "passed") -> dict[str, dict]:
    return {
        "docs_index": {"status": "passed", "summary": {}},
        "phase270_candidate_rebaseline": {"status": "passed", "summary": {"phase270_ready": True}},
        "phase271_fixture_index_readiness": {"status": "passed", "summary": {"phase272_ready": True}},
        "phase272_stale_index_rejection": {"status": "passed", "summary": {"phase273_ready": True}},
        "phase273_live_acceptance": {
            "status": phase273_status,
            "summary": {
                "response_count": 18,
                "gateway_response_count": 9,
                "anythingllm_response_count": 9,
                "critical_or_high_finding_count": 0,
                "json_default_parity_status": "passed",
            },
        },
        "phase274_answer_quality_repair": {
            "status": "passed",
            "decision": "no_repair_required",
            "summary": {"phase275_ready": True},
        },
    }


def test_phase275_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase275_synthetic_gate_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, policy_path = temp_config(tmp_path)
    monkeypatch.setattr(phase275, "git_state", lambda config_root: git_state())
    monkeypatch.setattr(phase275, "run_gates", lambda config: gates())

    report = validate_large_context_500k_clean_clone_replay(
        LargeContext500kCleanCloneReplayConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase275/report.json",
            markdown_output_path="runtime-state/phase275/report.md",
            live=True,
        )
    )

    assert report["status"] == LargeContext500kCleanCloneReplayStatus.PASSED.value
    assert report["decision"] == "phase275_clean_clone_500k_candidate_ready"
    assert report["summary"]["phase276_ready"] is True


def test_phase275_rejects_dirty_clone_after_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, policy_path = temp_config(tmp_path)
    states = [git_state(), git_state(dirty=1)]
    monkeypatch.setattr(phase275, "git_state", lambda config_root: states.pop(0))
    monkeypatch.setattr(phase275, "run_gates", lambda config: gates())

    report = validate_large_context_500k_clean_clone_replay(
        LargeContext500kCleanCloneReplayConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase275/report.json",
            markdown_output_path="runtime-state/phase275/report.md",
            live=True,
        )
    )

    assert report["status"] == LargeContext500kCleanCloneReplayStatus.FAILED.value
    assert any(item["id"] == "source.clean_after" for item in report["errors"])


def test_phase275_rejects_failed_phase273_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, policy_path = temp_config(tmp_path)
    monkeypatch.setattr(phase275, "git_state", lambda config_root: git_state())
    monkeypatch.setattr(phase275, "run_gates", lambda config: gates(phase273_status="failed"))

    report = validate_large_context_500k_clean_clone_replay(
        LargeContext500kCleanCloneReplayConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase275/report.json",
            markdown_output_path="runtime-state/phase275/report.md",
            live=True,
        )
    )

    assert report["status"] == LargeContext500kCleanCloneReplayStatus.FAILED.value
    assert any(item["id"] == "phase273_live_acceptance.status" for item in report["errors"])


def test_phase275_policy_rejects_runtime_state_tracking() -> None:
    mutated = copy.deepcopy(policy())
    mutated["safety_requirements"]["runtime_state_tracked_allowed"] = True

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.safety_requirements.runtime_state_tracked_allowed" for item in errors)
