"""Stable-channel handoff smoke validation."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from vllm_agent_gateway.acceptance.first_time_user_doctor import DEFAULT_LLM_GATEWAY_BASE_URL, DEFAULT_MODEL_BASE_URL
from vllm_agent_gateway.acceptance.release_channels import (
    ReleaseChannelCheckStatus,
    release_candidate_report_check,
    resolve_optional_path,
)
from vllm_agent_gateway.acceptance.v1 import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    fixture_state,
)


SCHEMA_VERSION = 1
DEFAULT_RELEASE_CANDIDATE_REPORT_PATH = Path("runtime") / "release_proofs" / "v1-1-release-candidate-stable-proof.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "stable-handoff"
ONBOARDING_SMOKE_CASE_ID = "ONB-001"


class StableHandoffStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class StableHandoffConfig:
    config_root: Path
    release_candidate_report_path: Path | None = DEFAULT_RELEASE_CANDIDATE_REPORT_PATH
    output_path: Path | None = None
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    llm_gateway_base_url: str = DEFAULT_LLM_GATEWAY_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    expected_anythingllm_llm_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    target_roots: tuple[str, ...] = tuple(DEFAULT_TARGET_ROOTS)
    timeout_seconds: int = 900
    command_timeout_seconds: int = 1800
    python_executable: str | None = None


@dataclass(frozen=True)
class CommandExecutionResult:
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[list[str], int], CommandExecutionResult]
FixtureStateReader = Callable[[tuple[str, ...]], dict[str, dict[str, Any]]]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"stable-handoff-{utc_timestamp()}.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def child_report_path(output_path: Path, suffix: str) -> Path:
    return output_path.with_name(f"{output_path.stem}-{suffix}.json")


def command_check(
    check_id: str,
    status: StableHandoffStatus,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    next_action: str = "",
) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": status.value,
        "message": message,
        "details": details or {},
        "next_action": next_action,
    }


def build_stable_handoff_commands(
    config: StableHandoffConfig,
    *,
    output_path: Path,
    release_candidate_report_path: Path,
) -> list[dict[str, Any]]:
    python = config.python_executable or sys.executable
    config_root = str(config.config_root.resolve())
    targets: list[str] = []
    for target_root in config.target_roots:
        targets.extend(["--target-root", target_root])
    return [
        {
            "id": "first_time_user_doctor",
            "description": "Setup preflight for ports, AnythingLLM, controller roots, and protected fixtures.",
            "report_path": str(child_report_path(output_path, "first-time-user-doctor")),
            "command": [
                python,
                str(config.config_root / "scripts" / "run_first_time_user_doctor.py"),
                "--config-root",
                config_root,
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
                "--expected-anythingllm-llm-base-url",
                config.expected_anythingllm_llm_base_url,
                "--workspace",
                config.workspace,
                "--api-key-env",
                config.api_key_env,
                "--timeout-seconds",
                str(min(60, config.timeout_seconds)),
                *targets,
                "--output-path",
                str(child_report_path(output_path, "first-time-user-doctor")),
            ],
        },
        {
            "id": "stable_release_channel",
            "description": "Stable channel metadata and activation proof validation.",
            "report_path": str(child_report_path(output_path, "release-channel")),
            "command": [
                python,
                str(config.config_root / "scripts" / "validate_release_channels.py"),
                "--config-root",
                config_root,
                "--channel",
                "stable",
                "--release-candidate-report",
                str(release_candidate_report_path),
                "--output-path",
                str(child_report_path(output_path, "release-channel")),
            ],
        },
        {
            "id": "security_policy",
            "description": "Security policy gate for secrets, roots, protected fixtures, commands, and onboarding prompts.",
            "report_path": str(child_report_path(output_path, "security-policy")),
            "command": [
                python,
                str(config.config_root / "scripts" / "validate_security_policy.py"),
                "--config-root",
                config_root,
                "--output-path",
                str(child_report_path(output_path, "security-policy")),
            ],
        },
        {
            "id": "external_tester_onboarding_smoke",
            "description": "One live AnythingLLM onboarding prompt plus linked feedback proof.",
            "report_path": str(child_report_path(output_path, "external-tester-onboarding")),
            "command": [
                python,
                str(config.config_root / "scripts" / "validate_external_tester_onboarding.py"),
                "--config-root",
                config_root,
                "--anythingllm-api-base-url",
                config.anythingllm_api_base_url,
                "--workspace",
                config.workspace,
                "--api-key-env",
                config.api_key_env,
                "--timeout-seconds",
                str(config.timeout_seconds),
                "--case-id",
                ONBOARDING_SMOKE_CASE_ID,
                "--live-anythingllm",
                "--include-feedback",
                "--output-path",
                str(child_report_path(output_path, "external-tester-onboarding")),
            ],
        },
    ]


def run_subprocess_command(command: list[str], timeout_seconds: int) -> CommandExecutionResult:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return CommandExecutionResult(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return CommandExecutionResult(
            returncode=124,
            stdout=stdout,
            stderr=f"{stderr}\ncommand timed out after {timeout_seconds} seconds".strip(),
        )


def run_command_checks(
    commands: list[dict[str, Any]],
    *,
    timeout_seconds: int,
    command_runner: CommandRunner,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for command_spec in commands:
        command = command_spec["command"]
        result = command_runner(command, timeout_seconds)
        status = StableHandoffStatus.PASSED if result.returncode == 0 else StableHandoffStatus.FAILED
        checks.append(
            command_check(
                f"command.{command_spec['id']}",
                status,
                f"{command_spec['id']} passed." if status == StableHandoffStatus.PASSED else f"{command_spec['id']} failed.",
                details={
                    "description": command_spec.get("description"),
                    "command": command,
                    "returncode": result.returncode,
                    "report_path": command_spec.get("report_path"),
                    "stdout_tail": result.stdout[-4000:],
                    "stderr_tail": result.stderr[-4000:],
                },
                next_action="" if status == StableHandoffStatus.PASSED else "Inspect this command output before handing stable to testers.",
            )
        )
    return checks


def release_candidate_proof_check(config_root: Path, report_path: Path | None) -> dict[str, Any]:
    resolved = resolve_optional_path(config_root, report_path)
    status, details, errors = release_candidate_report_check(resolved)
    return command_check(
        "release_candidate_report",
        StableHandoffStatus.PASSED if status == ReleaseChannelCheckStatus.PASSED else StableHandoffStatus.FAILED,
        "Release-candidate proof is usable for stable handoff."
        if status == ReleaseChannelCheckStatus.PASSED
        else "Release-candidate proof is missing or invalid.",
        details={**details, "errors": errors},
        next_action="" if status == ReleaseChannelCheckStatus.PASSED else "Run V1.1 acceptance and pass the report path.",
    )


def fixture_state_check(
    before_state: dict[str, dict[str, Any]],
    after_state: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    changed = before_state != after_state
    return command_check(
        "protected_fixture_state",
        StableHandoffStatus.FAILED if changed else StableHandoffStatus.PASSED,
        "Protected fixture state stayed unchanged." if not changed else "Protected fixture state changed during stable handoff smoke.",
        details={"changed": changed, "before": before_state, "after": after_state},
        next_action="" if not changed else "Stop tester handoff and inspect fixture hashes/status before running more live tests.",
    )


def validate_stable_handoff(
    config: StableHandoffConfig,
    *,
    command_runner: CommandRunner = run_subprocess_command,
    fixture_state_reader: FixtureStateReader = fixture_state,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root)
    release_candidate_report_path = resolve_optional_path(config_root, config.release_candidate_report_path)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "stable_handoff_validation_report",
        "status": StableHandoffStatus.FAILED.value,
        "created_at": utc_timestamp(),
        "config_root": str(config_root),
        "release_candidate_report_path": str(release_candidate_report_path) if release_candidate_report_path else None,
        "target_roots": list(config.target_roots),
        "checks": [],
        "commands": [],
        "summary": {},
    }
    checks: list[dict[str, Any]] = []
    proof_check = release_candidate_proof_check(config_root, config.release_candidate_report_path)
    checks.append(proof_check)
    commands: list[dict[str, Any]] = []
    if proof_check["status"] == StableHandoffStatus.PASSED.value and release_candidate_report_path is not None:
        commands = build_stable_handoff_commands(
            config,
            output_path=output_path,
            release_candidate_report_path=release_candidate_report_path,
        )
        try:
            before_state = fixture_state_reader(config.target_roots)
        except Exception as exc:  # noqa: BLE001
            before_state = None
            commands = []
            checks.append(
                command_check(
                    "protected_fixture_state.preflight",
                    StableHandoffStatus.FAILED,
                    "Protected fixture state could not be captured before stable handoff smoke.",
                    details={"error": f"{type(exc).__name__}: {exc}", "target_roots": list(config.target_roots)},
                    next_action="Run stable handoff from Bash with reachable /mnt/c fixture paths before handing stable to testers.",
                )
            )
        if before_state is not None:
            checks.extend(
                run_command_checks(
                    commands,
                    timeout_seconds=config.command_timeout_seconds,
                    command_runner=command_runner,
                )
            )
            try:
                after_state = fixture_state_reader(config.target_roots)
                checks.append(fixture_state_check(before_state, after_state))
            except Exception as exc:  # noqa: BLE001
                checks.append(
                    command_check(
                        "protected_fixture_state.postflight",
                        StableHandoffStatus.FAILED,
                        "Protected fixture state could not be captured after stable handoff smoke.",
                        details={"error": f"{type(exc).__name__}: {exc}", "target_roots": list(config.target_roots)},
                        next_action="Inspect fixture hashes and git status manually before handing stable to testers.",
                    )
                )
    failed_ids = [item["id"] for item in checks if item.get("status") == StableHandoffStatus.FAILED.value]
    report["checks"] = checks
    report["commands"] = [
        {
            "id": item["id"],
            "description": item["description"],
            "command": item["command"],
            "report_path": item["report_path"],
        }
        for item in commands
    ]
    report["summary"] = {
        "check_count": len(checks),
        "command_count": len(commands),
        "failed_check_ids": failed_ids,
        "child_report_paths": [item["report_path"] for item in commands],
    }
    report["status"] = StableHandoffStatus.PASSED.value if not failed_ids else StableHandoffStatus.FAILED.value
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
