from __future__ import annotations

from pathlib import Path

from vllm_agent_gateway.acceptance.productized_setup import (
    CommandExecutionResult,
    ProductizedSetupAction,
    ProductizedSetupConfig,
    commands_for_action,
    failure_guidance,
    run_productized_setup,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def config(tmp_path: Path, action: ProductizedSetupAction = ProductizedSetupAction.PLAN) -> ProductizedSetupConfig:
    return ProductizedSetupConfig(
        config_root=REPO_ROOT,
        action=action,
        output_path=tmp_path / f"{action.value}.json",
        target_roots=("/mnt/c/coinbase_testing_repo_frozen_tmp", "/mnt/c/coinbase_testing_repo_frozen_tmp.github"),
        python_executable="python-test",
    )


def test_productized_setup_plan_covers_install_start_validate_reset_and_rerun(tmp_path: Path) -> None:
    report = run_productized_setup(config(tmp_path))

    assert report["status"] == "passed"
    command_ids = [item["id"] for item in report["commands"]]
    assert command_ids == [
        "install.import_check",
        "install.script_check",
        "start.local_harness",
        "validate.first_time_user_doctor",
        "validate.release_channels",
        "validate.security_policy",
        "reset.stop_local_harness",
        "rerun.stable_handoff",
    ]
    assert Path(report["report_path"]).exists()


def test_productized_start_command_uses_existing_start_script_and_allowed_roots(tmp_path: Path) -> None:
    commands = commands_for_action(config(tmp_path, ProductizedSetupAction.START), tmp_path / "start.json")
    command_text = " ".join(commands[0]["command"])

    assert "start-agent-prompt-proxies.sh" in command_text
    assert "CONTROLLER_ALLOWED_TARGET_ROOTS" in command_text
    assert "/mnt/c/agentic_agents" in command_text
    assert "/mnt/c/coinbase_testing_repo_frozen_tmp" in command_text
    assert "/mnt/c/coinbase_testing_repo_frozen_tmp.github" in command_text
    assert "http://127.0.0.1:8300/v1" in command_text


def test_productized_reset_command_is_stop_only_not_destructive_delete(tmp_path: Path) -> None:
    commands = commands_for_action(config(tmp_path, ProductizedSetupAction.RESET), tmp_path / "reset.json")
    command_text = " ".join(commands[0]["command"]).lower()

    assert "stop-agent-prompt-proxies.sh" in command_text
    assert "rm -rf" not in command_text
    assert "remove-item" not in command_text
    assert "git reset" not in command_text


def test_productized_validate_and_rerun_use_existing_validation_surfaces(tmp_path: Path) -> None:
    validate_commands = commands_for_action(config(tmp_path, ProductizedSetupAction.VALIDATE), tmp_path / "validate.json")
    rerun_commands = commands_for_action(config(tmp_path, ProductizedSetupAction.RERUN), tmp_path / "rerun.json")

    validate_text = " ".join(" ".join(item["command"]) for item in validate_commands)
    rerun_text = " ".join(rerun_commands[0]["command"])
    assert "run_first_time_user_doctor.py" in validate_text
    assert "validate_release_channels.py" in validate_text
    assert "validate_security_policy.py" in validate_text
    assert "validate_stable_handoff.py" in rerun_text
    assert "--target-root /mnt/c/coinbase_testing_repo_frozen_tmp" in rerun_text
    assert "--target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github" in rerun_text


def test_productized_cli_entrypoints_exist() -> None:
    assert (REPO_ROOT / "scripts" / "run_productized_setup.py").exists()
    assert (REPO_ROOT / "scripts" / "manage_productized_setup.py").exists()


def test_productized_execute_records_command_failures(tmp_path: Path) -> None:
    def runner(command: list[str], _timeout: int) -> CommandExecutionResult:
        if "validate_release_channels.py" in " ".join(command):
            return CommandExecutionResult(1, "", "release channel failed")
        return CommandExecutionResult(0, "ok", "")

    report = run_productized_setup(
        config(tmp_path, ProductizedSetupAction.VALIDATE),
        execute=True,
        command_runner=runner,
    )

    assert report["status"] == "failed"
    assert report["summary"]["executed_command_count"] == 3
    assert report["summary"]["failed_check_ids"] == ["validate.release_channels"]
    failed = [item for item in report["execution_results"] if item["status"] == "failed"]
    assert failed[0]["stderr_tail"] == "release channel failed"


def test_productized_failure_guidance_covers_known_setup_failures() -> None:
    by_id = {item["failure_id"]: item for item in failure_guidance()}

    assert "port.*" in by_id
    assert "anythingllm.api_key" in by_id
    assert "anythingllm.target_url" in by_id
    assert "controller.allowed_roots" in by_id
    assert "fixtures.*" in by_id
    assert "8500" in by_id["anythingllm.target_url"]["next_action"]
