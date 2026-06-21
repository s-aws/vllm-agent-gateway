from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from vllm_agent_gateway.acceptance.productized_setup import CommandExecutionResult
from vllm_agent_gateway.acceptance.stable_release_reset_rehearsal import (
    DEFAULT_DISPOSABLE_RUNTIME_STATE_ROOT,
    DEFAULT_POLICY_PATH,
    ProductizedSetupAction,
    StableReleaseResetRehearsalConfig,
    commands_for_action,
    productized_config,
    read_json_object,
    reset_command_contract_check,
    run_stable_release_reset_rehearsal,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH
pytestmark = pytest.mark.serial


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def successful_git_runner(command: list[str], _timeout: int) -> CommandExecutionResult:
    if command[-2:] == ["ls-files", "runtime-state"]:
        return CommandExecutionResult(0, "", "")
    if command[-3:-1] == ["check-ignore", "-v"]:
        sample_path = command[-1]
        return CommandExecutionResult(0, f".gitignore:1:runtime-state/ {sample_path}\n", "")
    return CommandExecutionResult(0, "ok", "")


def fixture_snapshot() -> dict[str, dict[str, Any]]:
    return {
        "/mnt/c/coinbase_testing_repo_frozen_tmp": {
            "hashes": {"core/stealth_order_manager.py": "abc"},
            "git_status": None,
        },
        "/mnt/c/coinbase_testing_repo_frozen_tmp.github": {
            "hashes": {"core/stealth_order_manager.py": "def"},
            "git_status": {"clean": True, "line_count": 0, "sha256": "empty", "sample": []},
        },
    }


def rehearsal_config(
    tmp_path: Path,
    *,
    execute_reset_start: bool = False,
    execute_recovery: bool = False,
) -> StableReleaseResetRehearsalConfig:
    return StableReleaseResetRehearsalConfig(
        config_root=REPO_ROOT,
        output_path=tmp_path / "phase153-report.json",
        target_roots=(
            "/mnt/c/coinbase_testing_repo_frozen_tmp",
            "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
        ),
        python_executable="python-test",
        execute_reset_start=execute_reset_start,
        execute_recovery=execute_recovery,
    )


def test_phase153_policy_contract_passes() -> None:
    assert validate_policy(policy()) == []


def test_productized_reset_contract_is_stop_only_and_recovery_uses_stable_handoff(tmp_path: Path) -> None:
    config = rehearsal_config(tmp_path)
    check = reset_command_contract_check(config, tmp_path / "phase153-report.json")

    assert check["status"] == "passed"
    reset_text = " ".join(check["details"]["reset_commands"][0]["command"])
    rerun_text = " ".join(check["details"]["rerun_commands"][0]["command"])
    assert "stop-agent-prompt-proxies.sh" in reset_text
    assert "rm -rf" not in reset_text.lower()
    assert "git reset" not in reset_text.lower()
    assert "validate_stable_handoff.py" in rerun_text


def test_rehearsal_dry_run_passes_without_executing_live_stack(tmp_path: Path) -> None:
    report = run_stable_release_reset_rehearsal(
        rehearsal_config(tmp_path),
        command_runner=successful_git_runner,
        fixture_state_reader=lambda _roots: fixture_snapshot(),
    )

    assert report["status"] == "passed"
    assert report["execute_reset_start"] is False
    assert report["execute_recovery"] is False
    assert report["summary"]["failed_check_ids"] == []
    by_id = {item["id"]: item for item in report["checks"]}
    assert by_id["runtime_state.hygiene_gate"]["status"] == "passed"
    assert by_id["runtime_state.disposable_rehearsal"]["status"] == "passed"
    assert by_id["productized_setup.reset_start_execution"]["details"]["execute_reset_start"] is False
    assert by_id["stable_handoff.recovery_gate"]["details"]["execute_recovery"] is False
    disposable_root = REPO_ROOT / DEFAULT_DISPOSABLE_RUNTIME_STATE_ROOT
    assert (disposable_root / "regenerated-reset-proof.json").exists()
    assert Path(report["report_path"]).exists()


def test_rehearsal_executes_reset_start_when_requested(tmp_path: Path) -> None:
    commands_seen: list[list[str]] = []

    def runner(command: list[str], _timeout: int) -> CommandExecutionResult:
        commands_seen.append(command)
        return successful_git_runner(command, _timeout)

    report = run_stable_release_reset_rehearsal(
        rehearsal_config(tmp_path, execute_reset_start=True),
        command_runner=runner,
        fixture_state_reader=lambda _roots: fixture_snapshot(),
    )

    assert report["status"] == "passed"
    command_text = "\n".join(" ".join(command) for command in commands_seen)
    assert "stop-agent-prompt-proxies.sh" in command_text
    assert "start-agent-prompt-proxies.sh" in command_text


def test_rehearsal_executes_stable_handoff_when_requested(tmp_path: Path) -> None:
    commands_seen: list[list[str]] = []

    def runner(command: list[str], _timeout: int) -> CommandExecutionResult:
        commands_seen.append(command)
        return successful_git_runner(command, _timeout)

    report = run_stable_release_reset_rehearsal(
        rehearsal_config(tmp_path, execute_recovery=True),
        command_runner=runner,
        fixture_state_reader=lambda _roots: fixture_snapshot(),
    )

    assert report["status"] == "passed"
    command_text = "\n".join(" ".join(command) for command in commands_seen)
    assert "validate_stable_handoff.py" in command_text
    by_id = {item["id"]: item for item in report["checks"]}
    assert by_id["stable_handoff.recovery_gate"]["details"]["execute_recovery"] is True


def test_rehearsal_rejects_tracked_runtime_state_files(tmp_path: Path) -> None:
    def runner(command: list[str], _timeout: int) -> CommandExecutionResult:
        if command[-2:] == ["ls-files", "runtime-state"]:
            return CommandExecutionResult(0, "runtime-state/old-report.json\n", "")
        if command[-3:-1] == ["check-ignore", "-v"]:
            return CommandExecutionResult(0, ".gitignore:1:runtime-state/ runtime-state/sample.json\n", "")
        return CommandExecutionResult(0, "ok", "")

    report = run_stable_release_reset_rehearsal(
        rehearsal_config(tmp_path),
        command_runner=runner,
        fixture_state_reader=lambda _roots: fixture_snapshot(),
    )

    assert report["status"] == "failed"
    assert "runtime_state.hygiene_gate" in report["summary"]["failed_check_ids"]


def test_rehearsal_rejects_protected_fixture_mutation(tmp_path: Path) -> None:
    states = [
        fixture_snapshot(),
        {
            **fixture_snapshot(),
            "/mnt/c/coinbase_testing_repo_frozen_tmp.github": {
                "hashes": {"core/stealth_order_manager.py": "changed"},
                "git_status": {"clean": False, "line_count": 1, "sha256": "dirty", "sample": [" M file.py"]},
            },
        },
    ]

    def state_reader(_roots: tuple[str, ...]) -> dict[str, dict[str, Any]]:
        return states.pop(0)

    report = run_stable_release_reset_rehearsal(
        rehearsal_config(tmp_path),
        command_runner=successful_git_runner,
        fixture_state_reader=state_reader,
    )

    assert report["status"] == "failed"
    assert "protected_fixture_state.unchanged" in report["summary"]["failed_check_ids"]


def test_rehearsal_rejects_destructive_reset_command(monkeypatch: Any, tmp_path: Path) -> None:
    from vllm_agent_gateway.acceptance import stable_release_reset_rehearsal as module

    def bad_commands_for_action(
        config: Any,
        output_path: Path,
    ) -> list[dict[str, Any]]:
        if config.action == ProductizedSetupAction.RESET:
            return [
                {
                    "id": "reset.bad",
                    "description": "bad",
                    "command": ["bash", "-lc", "rm -rf runtime-state && ./stop-agent-prompt-proxies.sh"],
                    "required_files": [],
                    "reset_guidance": "bad",
                }
            ]
        return commands_for_action(productized_config(rehearsal_config(tmp_path), action=config.action, output_path=output_path), output_path)

    monkeypatch.setattr(module, "commands_for_action", bad_commands_for_action)
    check = module.reset_command_contract_check(rehearsal_config(tmp_path), tmp_path / "phase153-report.json")

    assert check["status"] == "failed"
    assert any("forbidden destructive fragments" in error for error in check["details"]["errors"])


def test_policy_rejects_missing_second_fixture_root() -> None:
    broken = copy.deepcopy(policy())
    broken["required_target_roots"] = ["/mnt/c/coinbase_testing_repo_frozen_tmp"]

    assert any("both frozen Coinbase fixture roots" in error for error in validate_policy(broken))


def test_policy_file_is_json_object() -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
