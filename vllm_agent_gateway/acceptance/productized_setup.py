"""Productized setup command surface for first-time local harness use."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from vllm_agent_gateway.acceptance.first_time_user_doctor import (
    DEFAULT_LLM_GATEWAY_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
)
from vllm_agent_gateway.acceptance.stable_handoff import DEFAULT_RELEASE_CANDIDATE_REPORT_PATH
from vllm_agent_gateway.acceptance.v1 import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
)


SCHEMA_VERSION = 1
DEFAULT_REPORT_DIR = Path("runtime-state") / "productized-setup"


class ProductizedSetupAction(str, Enum):
    PLAN = "plan"
    INSTALL = "install"
    START = "start"
    VALIDATE = "validate"
    RESET = "reset"
    RERUN = "rerun"


class ProductizedSetupStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class ProductizedSetupConfig:
    config_root: Path
    action: ProductizedSetupAction = ProductizedSetupAction.PLAN
    output_path: Path | None = None
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    llm_gateway_base_url: str = DEFAULT_LLM_GATEWAY_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    target_roots: tuple[str, ...] = tuple(DEFAULT_TARGET_ROOTS)
    release_candidate_report_path: Path | None = DEFAULT_RELEASE_CANDIDATE_REPORT_PATH
    timeout_seconds: int = 900
    command_timeout_seconds: int = 1800
    python_executable: str | None = None


@dataclass(frozen=True)
class CommandExecutionResult:
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[list[str], int], CommandExecutionResult]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path, action: ProductizedSetupAction) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"{action.value}-{utc_timestamp()}.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def wsl_path(path: Path) -> str:
    value = str(path.resolve()).replace("\\", "/")
    if len(value) >= 3 and value[1:3] == ":/":
        drive = value[0].lower()
        return f"/mnt/{drive}/{value[3:]}"
    return value


def shell_single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def joined_roots(config: ProductizedSetupConfig) -> str:
    roots = [wsl_path(config.config_root), *config.target_roots]
    deduped: list[str] = []
    for root in roots:
        if root not in deduped:
            deduped.append(root)
    return ":".join(deduped)


def python_executable(config: ProductizedSetupConfig) -> str:
    return config.python_executable or sys.executable


def command_spec(
    command_id: str,
    description: str,
    command: list[str],
    *,
    required_files: list[Path],
    reset_guidance: str,
) -> dict[str, Any]:
    return {
        "id": command_id,
        "description": description,
        "command": command,
        "required_files": [str(path) for path in required_files],
        "reset_guidance": reset_guidance,
    }


def install_commands(config: ProductizedSetupConfig) -> list[dict[str, Any]]:
    root = config.config_root.resolve()
    return [
        command_spec(
            "install.import_check",
            "Verify the project package imports from the checkout.",
            [python_executable(config), "-c", "import vllm_agent_gateway; print('vllm_agent_gateway import ok')"],
            required_files=[root / "vllm_agent_gateway" / "__init__.py"],
            reset_guidance="If imports fail, run from the repository root with the project checkout on PYTHONPATH.",
        ),
        command_spec(
            "install.script_check",
            "Verify the Bash start and stop scripts are present.",
            [
                "bash",
                "-lc",
                f"cd {shell_single_quote(wsl_path(root))} && test -f start-agent-prompt-proxies.sh && test -f stop-agent-prompt-proxies.sh",
            ],
            required_files=[root / "start-agent-prompt-proxies.sh", root / "stop-agent-prompt-proxies.sh"],
            reset_guidance="If scripts are missing, restore the project checkout before continuing.",
        ),
    ]


def start_commands(config: ProductizedSetupConfig) -> list[dict[str, Any]]:
    root = config.config_root.resolve()
    allowed_roots = joined_roots(config)
    command = (
        f"cd {shell_single_quote(wsl_path(root))} && "
        f"CONTROLLER_ALLOWED_TARGET_ROOTS={shell_single_quote(allowed_roots)} "
        f"CONTROLLER_DEFAULT_ROLE_BASE_URL={shell_single_quote(config.llm_gateway_base_url)} "
        "./start-agent-prompt-proxies.sh"
    )
    return [
        command_spec(
            "start.local_harness",
            "Start the LLM gateway, workflow-router gateway, controller service, and role prompt proxies.",
            ["bash", "-lc", command],
            required_files=[root / "start-agent-prompt-proxies.sh"],
            reset_guidance="If startup fails, run the reset command, confirm localhost:8000/v1/models is healthy, then start again.",
        )
    ]


def reset_commands(config: ProductizedSetupConfig) -> list[dict[str, Any]]:
    root = config.config_root.resolve()
    return [
        command_spec(
            "reset.stop_local_harness",
            "Stop local harness processes and clear stale PID files via the existing stop script.",
            ["bash", "-lc", f"cd {shell_single_quote(wsl_path(root))} && ./stop-agent-prompt-proxies.sh"],
            required_files=[root / "stop-agent-prompt-proxies.sh"],
            reset_guidance="This reset does not delete artifacts or fixture files; inspect runtime-state logs if stop fails.",
        )
    ]


def validate_commands(config: ProductizedSetupConfig, output_path: Path) -> list[dict[str, Any]]:
    root = config.config_root.resolve()
    python = python_executable(config)
    targets: list[str] = []
    for target_root in config.target_roots:
        targets.extend(["--target-root", target_root])
    return [
        command_spec(
            "validate.first_time_user_doctor",
            "Run setup preflight for ports, controller roots, AnythingLLM config, and fixtures.",
            [
                python,
                str(root / "scripts" / "run_first_time_user_doctor.py"),
                "--config-root",
                str(root),
                "--model-base-url",
                config.model_base_url,
                "--llm-gateway-base-url",
                config.llm_gateway_base_url,
                "--workflow-router-gateway-base-url",
                config.workflow_router_gateway_base_url,
                "--controller-base-url",
                config.controller_base_url,
                "--anythingllm-api-base-url",
                config.anythingllm_api_base_url,
                "--workspace",
                config.workspace,
                "--api-key-env",
                config.api_key_env,
                "--timeout-seconds",
                str(min(60, config.timeout_seconds)),
                *targets,
                "--output-path",
                str(output_path.with_name(f"{output_path.stem}-first-time-user-doctor.json")),
            ],
            required_files=[root / "scripts" / "run_first_time_user_doctor.py"],
            reset_guidance="Fix the reported failed_check_ids before running prompts.",
        ),
        command_spec(
            "validate.release_channels",
            "Validate release-channel metadata and required docs links.",
            [
                python,
                str(root / "scripts" / "validate_release_channels.py"),
                "--config-root",
                str(root),
                "--output-path",
                str(output_path.with_name(f"{output_path.stem}-release-channels.json")),
            ],
            required_files=[root / "scripts" / "validate_release_channels.py"],
            reset_guidance="If this fails, inspect runtime/release_channels.json and docs links.",
        ),
        command_spec(
            "validate.security_policy",
            "Run the security policy preflight for roots, secrets, fixtures, and command fragments.",
            [
                python,
                str(root / "scripts" / "validate_security_policy.py"),
                "--config-root",
                str(root),
                "--output-path",
                str(output_path.with_name(f"{output_path.stem}-security-policy.json")),
            ],
            required_files=[root / "scripts" / "validate_security_policy.py"],
            reset_guidance="If this fails, inspect the failed security check before sharing tester prompts.",
        ),
    ]


def rerun_commands(config: ProductizedSetupConfig, output_path: Path) -> list[dict[str, Any]]:
    root = config.config_root.resolve()
    python = python_executable(config)
    targets: list[str] = []
    for target_root in config.target_roots:
        targets.extend(["--target-root", target_root])
    release_report = config.release_candidate_report_path or DEFAULT_RELEASE_CANDIDATE_REPORT_PATH
    return [
        command_spec(
            "rerun.stable_handoff",
            "Rerun the stable handoff smoke path after reset/start.",
            [
                python,
                str(root / "scripts" / "validate_stable_handoff.py"),
                "--config-root",
                str(root),
                "--release-candidate-report",
                str(release_report),
                "--model-base-url",
                config.model_base_url,
                "--llm-gateway-base-url",
                config.llm_gateway_base_url,
                "--workflow-router-gateway-base-url",
                config.workflow_router_gateway_base_url,
                "--controller-base-url",
                config.controller_base_url,
                "--anythingllm-api-base-url",
                config.anythingllm_api_base_url,
                "--workspace",
                config.workspace,
                "--api-key-env",
                config.api_key_env,
                "--timeout-seconds",
                str(config.timeout_seconds),
                "--command-timeout-seconds",
                str(config.command_timeout_seconds),
                *targets,
                "--output-path",
                str(output_path.with_name(f"{output_path.stem}-stable-handoff.json")),
            ],
            required_files=[root / "scripts" / "validate_stable_handoff.py"],
            reset_guidance="If this fails, inspect the child report paths and rerun the failed validator only.",
        )
    ]


def commands_for_action(config: ProductizedSetupConfig, output_path: Path) -> list[dict[str, Any]]:
    if config.action == ProductizedSetupAction.INSTALL:
        return install_commands(config)
    if config.action == ProductizedSetupAction.START:
        return start_commands(config)
    if config.action == ProductizedSetupAction.VALIDATE:
        return validate_commands(config, output_path)
    if config.action == ProductizedSetupAction.RESET:
        return reset_commands(config)
    if config.action == ProductizedSetupAction.RERUN:
        return rerun_commands(config, output_path)
    commands: list[dict[str, Any]] = []
    for action in (
        ProductizedSetupAction.INSTALL,
        ProductizedSetupAction.START,
        ProductizedSetupAction.VALIDATE,
        ProductizedSetupAction.RESET,
        ProductizedSetupAction.RERUN,
    ):
        commands.extend(commands_for_action(ProductizedSetupConfig(**{**config.__dict__, "action": action}), output_path))
    return commands


def failure_guidance() -> list[dict[str, str]]:
    return [
        {
            "failure_id": "port.*",
            "meaning": "A localhost model, gateway, controller, or role port is not reachable.",
            "next_action": "Run the reset command, confirm vLLM is healthy at 8000, then run the start command.",
        },
        {
            "failure_id": "anythingllm.api_key",
            "meaning": "The AnythingLLM API key is not visible to the validation process.",
            "next_action": "Set ANYTHINGLLM_API_KEY in the Windows user environment and export it into Bash before validate/rerun.",
        },
        {
            "failure_id": "anythingllm.target_url",
            "meaning": "AnythingLLM is not pointed at the natural workflow-router gateway.",
            "next_action": "Set the Generic OpenAI base URL to http://127.0.0.1:8500/v1, not 8300 or 8400.",
        },
        {
            "failure_id": "controller.allowed_roots",
            "meaning": "The controller was started without the repo or fixture roots in its allowlist.",
            "next_action": "Run reset, then start with CONTROLLER_ALLOWED_TARGET_ROOTS including /mnt/c/agentic_agents and both frozen fixtures.",
        },
        {
            "failure_id": "fixtures.*",
            "meaning": "A protected fixture is missing, dirty beyond known line-ending noise, or has changed hashes.",
            "next_action": "Stop prompt testing and inspect fixture manager snapshots before retrying.",
        },
    ]


def missing_required_files(commands: list[dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    for command in commands:
        for path_value in command.get("required_files", []):
            path = Path(path_value)
            if not path.exists():
                missing.append(str(path))
    return sorted(set(missing))


def run_subprocess_command(command: list[str], timeout_seconds: int) -> CommandExecutionResult:
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout_seconds)
        return CommandExecutionResult(result.returncode, result.stdout, result.stderr)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return CommandExecutionResult(124, stdout, f"{stderr}\ncommand timed out after {timeout_seconds} seconds".strip())


def run_productized_setup(
    config: ProductizedSetupConfig,
    *,
    execute: bool = False,
    command_runner: CommandRunner = run_subprocess_command,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root, config.action)
    commands = commands_for_action(config, output_path)
    missing = missing_required_files(commands)
    checks: list[dict[str, Any]] = []
    if missing:
        checks.append({"id": "required_files", "status": ProductizedSetupStatus.FAILED.value, "missing": missing})
    execution_results: list[dict[str, Any]] = []
    if execute and not missing:
        for item in commands:
            result = command_runner(item["command"], config.command_timeout_seconds)
            execution_results.append(
                {
                    "id": item["id"],
                    "status": ProductizedSetupStatus.PASSED.value
                    if result.returncode == 0
                    else ProductizedSetupStatus.FAILED.value,
                    "returncode": result.returncode,
                    "stdout_tail": result.stdout[-4000:],
                    "stderr_tail": result.stderr[-4000:],
                }
            )
    failed_ids = [check["id"] for check in checks if check.get("status") == ProductizedSetupStatus.FAILED.value]
    failed_ids.extend(
        item["id"] for item in execution_results if item.get("status") == ProductizedSetupStatus.FAILED.value
    )
    status = ProductizedSetupStatus.FAILED if failed_ids else ProductizedSetupStatus.PASSED
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "productized_setup_report",
        "status": status.value,
        "created_at": utc_timestamp(),
        "action": config.action.value,
        "execute": execute,
        "config_root": str(config_root),
        "target_roots": list(config.target_roots),
        "commands": commands,
        "checks": checks,
        "execution_results": execution_results,
        "failure_guidance": failure_guidance(),
        "summary": {
            "command_count": len(commands),
            "executed_command_count": len(execution_results),
            "failed_check_ids": failed_ids,
            "missing_required_files": missing,
        },
        "report_path": str(output_path),
    }
    write_json(output_path, report)
    return report
