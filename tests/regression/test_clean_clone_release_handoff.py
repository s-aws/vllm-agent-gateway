from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.clean_clone_release_handoff import (
    DEFAULT_POLICY_PATH,
    SNAPSHOT_MARKER,
    SourceMode,
    build_clean_clone_release_handoff_report,
    inspect_snapshot,
    prepare_clean_snapshot,
    read_json_object,
    validate_clean_clone_release_handoff_report,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def snapshot_record() -> dict[str, Any]:
    return {
        "path": "/tmp/agentic_agents_phase234_clean_snapshot",
        "exists": True,
        "outside_active_workspace": True,
        "marker_present": True,
        "forbidden_entries_present": [],
        "missing_required_files": [],
        "required_file_count": 16,
        "required_file_hashes": {"README.md": "0" * 64},
        "required_manifest_sha256": "1" * 64,
        "symlink_count": 0,
        "symlink_sample": [],
    }


def source_git(dirty_line_count: int = 4) -> dict[str, Any]:
    return {
        "git_status_returncode": 0,
        "dirty_line_count": dirty_line_count,
        "dirty_status_sha256": "2" * 64,
        "dirty_status_sample": ["?? README.contextless-handoff-dry-run.md"],
    }


def command_results() -> list[dict[str, Any]]:
    return [
        {"id": command_id, "status": "passed", "returncode": 0, "command": ["true"], "stdout_tail": "", "stderr_tail": ""}
        for command_id in policy()["required_command_ids"]
    ]


def managed_stack(from_snapshot: bool = True) -> dict[str, Any]:
    return {
        "state_root": "/mnt/c/private_agentic_agents/runtime-state",
        "expected_cwd": "/tmp/agentic_agents_phase234_clean_snapshot",
        "pids": {},
        "mismatched_cwd": [] if from_snapshot else ["controller_service"],
        "missing_pid_files": [] if from_snapshot else [],
        "all_running_from_snapshot": from_snapshot,
    }


def fixture_checks() -> list[dict[str, Any]]:
    return [
        {"root": "/mnt/c/coinbase_testing_repo_frozen_tmp", "kind": "file_hash", "status": "passed", "unchanged": True},
        {"root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github", "kind": "git", "status": "passed", "unchanged": True},
    ]


def build_report(
    *,
    source_mode: SourceMode = SourceMode.CLEAN_SNAPSHOT,
    dirty_line_count: int = 4,
    stack_from_snapshot: bool = True,
) -> dict[str, Any]:
    return build_clean_clone_release_handoff_report(
        config_root=REPO_ROOT,
        policy=policy(),
        policy_path=POLICY_PATH,
        snapshot_root=Path("/tmp/agentic_agents_phase234_clean_snapshot"),
        source_mode=source_mode,
        prepare_record={"created": True, "path": "/tmp/agentic_agents_phase234_clean_snapshot", "error": ""},
        snapshot_record=snapshot_record(),
        source_git=source_git(dirty_line_count),
        command_results=command_results(),
        managed_stack=managed_stack(stack_from_snapshot),
        runtime_seeds=[],
        fixture_checks=fixture_checks(),
        run_live_minimal=True,
        source_errors=[],
    )


def test_phase234_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase234_clean_snapshot_report_passes_with_dirty_source_disclosed() -> None:
    report = build_report()

    assert report["status"] == "passed"
    assert report["decision"] == "clean_handoff_ready"
    assert report["source_mode"] == "clean_snapshot"
    assert report["source_git"]["dirty_line_count"] == 4
    assert report["summary"]["managed_stack_from_snapshot"] is True


def test_phase234_git_clone_mode_rejects_dirty_source() -> None:
    report = build_report(source_mode=SourceMode.GIT_CLONE, dirty_line_count=1)

    assert report["status"] == "failed"
    assert "source.git_dirty" in {item["id"] for item in report["validation_errors"]}


def test_phase234_rejects_live_proof_when_stack_not_running_from_snapshot() -> None:
    report = build_report(stack_from_snapshot=False)

    assert report["status"] == "failed"
    assert "managed_stack.snapshot_cwd" in {item["id"] for item in report["validation_errors"]}


def test_phase234_rejects_hidden_summary_edit() -> None:
    current_policy = policy()
    report = build_report()
    edited = copy.deepcopy(report)
    edited["summary"]["passed_command_count"] = 999

    errors = validate_clean_clone_release_handoff_report(
        edited,
        config_root=REPO_ROOT,
        policy=current_policy,
        policy_path=POLICY_PATH,
        snapshot_root=Path("/tmp/agentic_agents_phase234_clean_snapshot"),
        source_mode=SourceMode.CLEAN_SNAPSHOT,
        prepare_record={"created": True, "path": "/tmp/agentic_agents_phase234_clean_snapshot", "error": ""},
        snapshot_record=snapshot_record(),
        source_git=source_git(),
        command_results=command_results(),
        managed_stack=managed_stack(),
        runtime_seeds=[],
        fixture_checks=fixture_checks(),
        run_live_minimal=True,
        source_errors=[],
    )

    assert errors == ["report must match rebuilt clean handoff report"]


def test_phase234_snapshot_prepare_excludes_generated_and_git_entries(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / ".git").mkdir()
    (source / "runtime-state").mkdir()
    (source / "README.md").write_text("hello\n", encoding="utf-8")
    (source / "runtime-state" / "old.json").write_text("{}", encoding="utf-8")
    target = tmp_path / "agentic_agents_phase234_clean_snapshot"

    prepare = prepare_clean_snapshot(source, target, [".git", "runtime-state"])

    assert prepare["created"] is True
    assert (target / SNAPSHOT_MARKER).is_file()
    assert (target / "README.md").is_file()
    assert not (target / ".git").exists()
    assert not (target / "runtime-state").exists()


def test_phase234_snapshot_inspection_rejects_symlinks(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    target = tmp_path / "agentic_agents_phase234_clean_snapshot"
    target.mkdir()
    (target / SNAPSHOT_MARKER).write_text("marker\n", encoding="utf-8")
    required = target / "README.md"
    required.write_text("hello\n", encoding="utf-8")
    (target / "linked").symlink_to(required)
    current_policy = {
        **policy(),
        "required_files": ["README.md"],
        "forbidden_snapshot_entries": [".git", "runtime-state"],
    }

    record, errors = inspect_snapshot(source, target, current_policy)

    assert record["symlink_count"] == 1
    assert "snapshot.symlinks" in {item["id"] for item in errors}
