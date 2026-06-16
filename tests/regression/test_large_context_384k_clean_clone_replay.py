from __future__ import annotations

import copy
from pathlib import Path

import pytest

from vllm_agent_gateway.acceptance import large_context_384k_clean_clone_replay as phase264
from vllm_agent_gateway.acceptance.large_context_384k_clean_clone_replay import (
    DEFAULT_POLICY_PATH,
    LargeContext384kCleanCloneReplayConfig,
    LargeContext384kCleanCloneReplayStatus,
    read_json_object,
    validate_large_context_384k_clean_clone_replay,
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


def static_gates() -> dict[str, dict]:
    return {
        "docs_index": {"status": "passed", "summary": {}},
        "phase251_objective_rebaseline": {"status": "passed", "summary": {"phase251_ready": True}},
        "phase258_acceptance_contract": {"status": "passed", "summary": {"phase258_ready": True}},
        "phase259_fixture_index_readiness": {
            "status": "passed",
            "summary": {"phase260_ready": True, "estimated_indexed_token_count": 384000},
        },
        "phase260_stale_index_rejection": {"status": "passed", "summary": {"phase261_ready": True}},
    }


def phase261_report(*, failed_small: int = 0) -> dict:
    return {
        "status": "passed",
        "decision": "phase261_current_384k_live_acceptance_proof",
        "summary": {
            "target_estimated_project_tokens": 384000,
            "response_count": 18,
            "gateway_response_count": 9,
            "anythingllm_response_count": 9,
            "failed_small_repo_regression_count": failed_small,
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
        },
    }


def test_phase264_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase264_synthetic_gate_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, policy_path = temp_config(tmp_path)
    monkeypatch.setattr(phase264, "git_state", lambda config_root: git_state())
    monkeypatch.setattr(phase264, "run_static_gates", lambda config_root, output_dir: static_gates())
    monkeypatch.setattr(phase264, "run_live_gate", lambda config, output_dir: phase261_report())

    report = validate_large_context_384k_clean_clone_replay(
        LargeContext384kCleanCloneReplayConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase264/report.json",
            markdown_output_path="runtime-state/phase264/report.md",
            live=True,
        )
    )

    assert report["status"] == LargeContext384kCleanCloneReplayStatus.PASSED.value
    assert report["decision"] == "phase264_clean_clone_384k_usability_ready"
    assert report["summary"]["phase265_ready"] is True
    assert report["summary"]["source_dirty_line_count_before"] == 0
    assert report["summary"]["source_dirty_line_count_after"] == 0


def test_phase264_rejects_dirty_clone_after_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, policy_path = temp_config(tmp_path)
    states = [git_state(), git_state(dirty=1)]
    monkeypatch.setattr(phase264, "git_state", lambda config_root: states.pop(0))
    monkeypatch.setattr(phase264, "run_static_gates", lambda config_root, output_dir: static_gates())
    monkeypatch.setattr(phase264, "run_live_gate", lambda config, output_dir: phase261_report())

    report = validate_large_context_384k_clean_clone_replay(
        LargeContext384kCleanCloneReplayConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase264/report.json",
            markdown_output_path="runtime-state/phase264/report.md",
            live=True,
        )
    )

    assert report["status"] == LargeContext384kCleanCloneReplayStatus.FAILED.value
    assert any(item["id"] == "source.clean_after" for item in report["errors"])


def test_phase264_rejects_phase261_small_repo_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, policy_path = temp_config(tmp_path)
    monkeypatch.setattr(phase264, "git_state", lambda config_root: git_state())
    monkeypatch.setattr(phase264, "run_static_gates", lambda config_root, output_dir: static_gates())
    monkeypatch.setattr(phase264, "run_live_gate", lambda config, output_dir: phase261_report(failed_small=1))

    report = validate_large_context_384k_clean_clone_replay(
        LargeContext384kCleanCloneReplayConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase264/report.json",
            markdown_output_path="runtime-state/phase264/report.md",
            live=True,
        )
    )

    assert report["status"] == LargeContext384kCleanCloneReplayStatus.FAILED.value
    assert any(item["id"] == "phase261.failed_small_repo_regression_count" for item in report["errors"])


def test_phase264_reports_static_gate_exception(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, policy_path = temp_config(tmp_path)
    monkeypatch.setattr(phase264, "git_state", lambda config_root: git_state())

    def boom(config_root: Path, output_dir: Path) -> dict:
        raise RuntimeError("fixture bootstrap failed")

    monkeypatch.setattr(phase264, "run_static_gates", boom)
    monkeypatch.setattr(phase264, "run_live_gate", lambda config, output_dir: phase261_report())

    with pytest.raises(RuntimeError):
        boom(root, root)

    report = phase264.run_gate("phase259_fixture_index_readiness", lambda: boom(root, root))

    assert report["status"] == LargeContext384kCleanCloneReplayStatus.FAILED.value
    assert report["errors"][0]["id"] == "phase259_fixture_index_readiness.exception"


def test_phase264_runs_phase259_and_phase260_at_canonical_paths_before_mirroring(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "config"
    output_dir = root / "runtime-state" / "phase264"
    phase259_report = {"status": "passed", "summary": {"phase260_ready": True}}
    phase260_report = {"status": "passed", "summary": {"phase261_ready": True}}

    def fake_phase259(config: phase264.LargeContext384kFixtureIndexReadinessConfig) -> dict:
        canonical = root / phase264.PHASE259_DEFAULT_OUTPUT_PATH
        markdown = root / phase264.PHASE259_DEFAULT_MARKDOWN_OUTPUT_PATH
        phase264.write_json(canonical, phase259_report)
        phase264.write_text(markdown, "phase259 canonical markdown\n")
        return dict(phase259_report)

    def fake_phase260(config: phase264.LargeContext384kStaleIndexRejectionConfig) -> dict:
        assert (root / phase264.PHASE259_DEFAULT_OUTPUT_PATH).is_file()
        canonical = root / phase264.PHASE260_DEFAULT_OUTPUT_PATH
        markdown = root / phase264.PHASE260_DEFAULT_MARKDOWN_OUTPUT_PATH
        phase264.write_json(canonical, phase260_report)
        phase264.write_text(markdown, "phase260 canonical markdown\n")
        return dict(phase260_report)

    monkeypatch.setattr(phase264, "validate_large_context_384k_fixture_index_readiness", fake_phase259)
    monkeypatch.setattr(phase264, "validate_large_context_384k_stale_index_rejection", fake_phase260)

    observed259 = phase264.run_phase259_canonical_with_phase264_mirror(root, output_dir)
    observed260 = phase264.run_phase260_canonical_with_phase264_mirror(root, output_dir)

    phase259_mirror = output_dir / "phase264-phase259-large-context-384k-fixture-index-readiness-report.json"
    phase260_mirror = output_dir / "phase264-phase260-large-context-384k-stale-index-rejection-report.json"
    assert (root / phase264.PHASE259_DEFAULT_OUTPUT_PATH).is_file()
    assert (root / phase264.PHASE260_DEFAULT_OUTPUT_PATH).is_file()
    assert phase259_mirror.is_file()
    assert phase260_mirror.is_file()
    assert observed259["canonical_report_path"] == str((root / phase264.PHASE259_DEFAULT_OUTPUT_PATH).resolve())
    assert observed260["canonical_report_path"] == str((root / phase264.PHASE260_DEFAULT_OUTPUT_PATH).resolve())
    assert phase259_mirror.read_text(encoding="utf-8")
    assert (output_dir / "phase264-phase259-large-context-384k-fixture-index-readiness-report.md").read_text(
        encoding="utf-8"
    ) == "phase259 canonical markdown\n"


def test_phase264_policy_rejects_post_384k_expansion() -> None:
    mutated = copy.deepcopy(policy())
    mutated["safety_requirements"]["post_384k_expansion_allowed"] = True

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.safety_requirements.post_384k_expansion_allowed" for item in errors)
