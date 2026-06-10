"""Stable-release reset and recovery rehearsal validation."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from vllm_agent_gateway.acceptance.productized_setup import (
    CommandExecutionResult as ProductizedCommandExecutionResult,
)
from vllm_agent_gateway.acceptance.productized_setup import (
    ProductizedSetupAction,
    ProductizedSetupConfig,
    commands_for_action,
    run_productized_setup,
)
from vllm_agent_gateway.acceptance.runtime_state_hygiene import (
    RuntimeStateHygieneConfig,
    validate_runtime_state_hygiene,
)
from vllm_agent_gateway.acceptance.stable_handoff import DEFAULT_RELEASE_CANDIDATE_REPORT_PATH
from vllm_agent_gateway.acceptance.v1 import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    fixture_state,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "stable_release_reset_rehearsal_policy"
EXPECTED_REPORT_KIND = "stable_release_reset_rehearsal_report"
EXPECTED_PHASE = 153
DEFAULT_POLICY_PATH = Path("runtime") / "stable_release_reset_rehearsal_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "stable-release-reset-rehearsal" / "phase153"
DEFAULT_DISPOSABLE_RUNTIME_STATE_ROOT = DEFAULT_OUTPUT_DIR / "disposable-runtime-state"
DEFAULT_SOURCE_WATCH_PATHS = (
    Path("start-agent-prompt-proxies.sh"),
    Path("stop-agent-prompt-proxies.sh"),
    Path("README.productized-setup.md"),
    Path("README.stable-handoff.md"),
    Path("README.runtime-state.md"),
    Path("runtime") / "release_channels.json",
    Path("runtime") / "release_proofs" / "v1-1-release-candidate-stable-proof.json",
    Path("vllm_agent_gateway") / "acceptance" / "productized_setup.py",
    Path("vllm_agent_gateway") / "acceptance" / "stable_handoff.py",
    Path("vllm_agent_gateway") / "acceptance" / "runtime_state_hygiene.py",
)
FORBIDDEN_RESET_FRAGMENTS = (
    "rm -rf",
    "Remove-Item",
    "git reset",
    "git checkout",
    "del /",
    "rmdir /s",
)


class StableReleaseResetRehearsalStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


CommandRunner = Callable[[list[str], int], ProductizedCommandExecutionResult]
FixtureStateReader = Callable[[tuple[str, ...]], dict[str, dict[str, Any]]]


@dataclass(frozen=True)
class StableReleaseResetRehearsalConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    release_candidate_report_path: Path | None = DEFAULT_RELEASE_CANDIDATE_REPORT_PATH
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    llm_gateway_base_url: str = "http://127.0.0.1:8300/v1"
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    target_roots: tuple[str, ...] = tuple(DEFAULT_TARGET_ROOTS)
    timeout_seconds: int = 900
    command_timeout_seconds: int = 1800
    python_executable: str | None = None
    execute_reset_start: bool = False
    execute_recovery: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"stable-release-reset-rehearsal-{utc_timestamp()}.json"


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object at {path}")
    return value


def default_command_runner(command: list[str], timeout_seconds: int) -> ProductizedCommandExecutionResult:
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout_seconds)
        return ProductizedCommandExecutionResult(result.returncode, result.stdout, result.stderr)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return ProductizedCommandExecutionResult(
            124,
            stdout,
            f"{stderr}\ncommand timed out after {timeout_seconds} seconds".strip(),
        )


def check(
    check_id: str,
    status: StableReleaseResetRehearsalStatus,
    message: str,
    *,
    category: str,
    details: dict[str, Any] | None = None,
    next_action: str = "",
) -> dict[str, Any]:
    return {
        "id": check_id,
        "category": category,
        "status": status.value,
        "message": message,
        "details": details or {},
        "next_action": next_action,
    }


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_state(config_root: Path, source_paths: tuple[Path, ...]) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    for relative_path in source_paths:
        path = resolve_path(config_root, relative_path)
        exists = path.exists()
        state[relative_path.as_posix()] = {
            "exists": exists,
            "sha256": sha256_file(path) if exists and path.is_file() else None,
        }
    return state


def git_state(config_root: Path) -> dict[str, Any]:
    status = subprocess.run(
        ["git", "-C", str(config_root), "status", "--short"],
        check=False,
        capture_output=True,
        text=True,
    )
    diff = subprocess.run(
        ["git", "-C", str(config_root), "diff", "--name-only"],
        check=False,
        capture_output=True,
        text=True,
    )
    untracked = subprocess.run(
        ["git", "-C", str(config_root), "ls-files", "--others", "--exclude-standard"],
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "status_returncode": status.returncode,
        "diff_returncode": diff.returncode,
        "untracked_returncode": untracked.returncode,
        "status_sha256": hashlib.sha256(status.stdout.encode("utf-8")).hexdigest(),
        "diff_sha256": hashlib.sha256(diff.stdout.encode("utf-8")).hexdigest(),
        "untracked_sha256": hashlib.sha256(untracked.stdout.encode("utf-8")).hexdigest(),
        "status_line_count": len(status.stdout.splitlines()),
        "diff_line_count": len(diff.stdout.splitlines()),
        "untracked_line_count": len(untracked.stdout.splitlines()),
        "status_sample": status.stdout.splitlines()[:10],
        "diff_sample": diff.stdout.splitlines()[:10],
        "untracked_sample": untracked.stdout.splitlines()[:10],
        "stderr": "\n".join(item for item in (status.stderr.strip(), diff.stderr.strip(), untracked.stderr.strip()) if item),
    }


def source_state_check(
    before_state: dict[str, dict[str, Any]],
    after_state: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    changed = before_state != after_state
    return check(
        "source_state.unchanged",
        StableReleaseResetRehearsalStatus.FAILED if changed else StableReleaseResetRehearsalStatus.PASSED,
        "Watched source and release files stayed unchanged."
        if not changed
        else "Watched source or release files changed during reset rehearsal.",
        category="source_integrity",
        details={"changed": changed, "before": before_state, "after": after_state},
        next_action="" if not changed else "Inspect the changed watched files before continuing release reset practice.",
    )


def git_state_check(before_state: dict[str, Any], after_state: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if before_state.get("status_returncode") != 0 or after_state.get("status_returncode") != 0:
        errors.append("git status must succeed before and after rehearsal")
    if before_state.get("diff_returncode") != 0 or after_state.get("diff_returncode") != 0:
        errors.append("git diff --name-only must succeed before and after rehearsal")
    if before_state.get("untracked_returncode") != 0 or after_state.get("untracked_returncode") != 0:
        errors.append("git ls-files --others --exclude-standard must succeed before and after rehearsal")
    for key in ("status_sha256", "diff_sha256", "untracked_sha256"):
        if before_state.get(key) != after_state.get(key):
            errors.append(f"{key} changed during reset rehearsal")
    return check(
        "source_state.git_snapshot_unchanged",
        StableReleaseResetRehearsalStatus.PASSED if not errors else StableReleaseResetRehearsalStatus.FAILED,
        "Git source snapshot stayed unchanged; pre-existing dirtiness did not grow."
        if not errors
        else "Git source snapshot changed during reset rehearsal.",
        category="source_integrity",
        details={"errors": errors, "before": before_state, "after": after_state},
        next_action="" if not errors else "Inspect git status/diff and separate any new source changes from pre-existing worktree dirtiness.",
    )


def fixture_state_check(
    before_state: dict[str, dict[str, Any]],
    after_state: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    changed = before_state != after_state
    return check(
        "protected_fixture_state.unchanged",
        StableReleaseResetRehearsalStatus.FAILED if changed else StableReleaseResetRehearsalStatus.PASSED,
        "Protected fixture state stayed unchanged."
        if not changed
        else "Protected fixture state changed during reset rehearsal.",
        category="fixture_integrity",
        details={"changed": changed, "before": before_state, "after": after_state},
        next_action="" if not changed else "Stop release reset practice and inspect fixture hashes/status.",
    )


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 153")
    target_roots = string_list(policy.get("required_target_roots"))
    if set(target_roots) != set(DEFAULT_TARGET_ROOTS):
        errors.append("policy.required_target_roots must include both frozen Coinbase fixture roots")
    source_paths = string_list(policy.get("source_watch_paths"))
    if set(source_paths) != {path.as_posix() for path in DEFAULT_SOURCE_WATCH_PATHS}:
        errors.append("policy.source_watch_paths must match the governed Phase 153 watch list")
    required_gates = set(string_list(policy.get("required_existing_gates")))
    if required_gates != {"runtime_state_hygiene", "productized_setup_reset_start", "stable_handoff"}:
        errors.append("policy.required_existing_gates must require runtime-state hygiene, productized reset/start, and stable handoff")
    reset_contract = dict_value(policy.get("reset_contract"))
    for flag in (
        "must_use_existing_stop_script",
        "must_not_delete_real_runtime_state",
        "must_not_mutate_protected_fixtures",
        "must_not_reset_git_state",
    ):
        if reset_contract.get(flag) is not True:
            errors.append(f"policy.reset_contract.{flag} must be true")
    forbidden = set(string_list(reset_contract.get("forbidden_command_fragments")))
    if forbidden != set(FORBIDDEN_RESET_FRAGMENTS):
        errors.append("policy.reset_contract.forbidden_command_fragments must match the governed list")
    disposable = dict_value(policy.get("disposable_runtime_state_rehearsal"))
    if disposable.get("relative_root") != DEFAULT_DISPOSABLE_RUNTIME_STATE_ROOT.as_posix():
        errors.append("policy.disposable_runtime_state_rehearsal.relative_root must match the governed path")
    artifacts = string_list(disposable.get("required_regenerated_artifacts"))
    if artifacts != ["regenerated-reset-proof.json"]:
        errors.append("policy.disposable_runtime_state_rehearsal.required_regenerated_artifacts must match the governed artifact list")
    recovery = dict_value(policy.get("recovery_contract"))
    if recovery.get("required_recovery_gate") != "stable_handoff":
        errors.append("policy.recovery_contract.required_recovery_gate must be stable_handoff")
    for flag in ("must_run_against_localhost_model", "must_cover_anythingllm", "must_cover_both_frozen_target_roots"):
        if recovery.get(flag) is not True:
            errors.append(f"policy.recovery_contract.{flag} must be true")
    return errors


def policy_check(policy: dict[str, Any]) -> dict[str, Any]:
    errors = validate_policy(policy)
    return check(
        "policy.contract",
        StableReleaseResetRehearsalStatus.PASSED if not errors else StableReleaseResetRehearsalStatus.FAILED,
        "Phase 153 reset rehearsal policy is valid."
        if not errors
        else "Phase 153 reset rehearsal policy is invalid.",
        category="policy",
        details={"errors": errors},
        next_action="" if not errors else "Fix runtime/stable_release_reset_rehearsal_policy.json before running reset rehearsal.",
    )


def command_text(command: list[str]) -> str:
    return " ".join(command)


def forbidden_fragments_in_command(command: list[str], forbidden_fragments: tuple[str, ...] = FORBIDDEN_RESET_FRAGMENTS) -> list[str]:
    lowered = command_text(command).lower()
    return [fragment for fragment in forbidden_fragments if fragment.lower() in lowered]


def productized_config(
    config: StableReleaseResetRehearsalConfig,
    *,
    action: ProductizedSetupAction,
    output_path: Path,
) -> ProductizedSetupConfig:
    return ProductizedSetupConfig(
        config_root=config.config_root,
        action=action,
        output_path=output_path,
        model_base_url=config.model_base_url,
        llm_gateway_base_url=config.llm_gateway_base_url,
        workflow_router_gateway_base_url=config.workflow_router_gateway_base_url,
        controller_base_url=config.controller_base_url,
        anythingllm_api_base_url=config.anythingllm_api_base_url,
        workspace=config.workspace,
        api_key_env=config.api_key_env,
        target_roots=config.target_roots,
        release_candidate_report_path=config.release_candidate_report_path,
        timeout_seconds=config.timeout_seconds,
        command_timeout_seconds=config.command_timeout_seconds,
        python_executable=config.python_executable,
    )


def reset_command_contract_check(config: StableReleaseResetRehearsalConfig, output_path: Path) -> dict[str, Any]:
    reset_commands = commands_for_action(
        productized_config(config, action=ProductizedSetupAction.RESET, output_path=output_path),
        output_path,
    )
    start_commands = commands_for_action(
        productized_config(config, action=ProductizedSetupAction.START, output_path=output_path),
        output_path,
    )
    rerun_commands = commands_for_action(
        productized_config(config, action=ProductizedSetupAction.RERUN, output_path=output_path),
        output_path,
    )
    errors: list[str] = []
    if len(reset_commands) != 1:
        errors.append("reset action must produce exactly one command")
    reset_text = command_text(reset_commands[0]["command"]) if reset_commands else ""
    if "stop-agent-prompt-proxies.sh" not in reset_text:
        errors.append("reset command must use stop-agent-prompt-proxies.sh")
    forbidden = forbidden_fragments_in_command(reset_commands[0]["command"]) if reset_commands else []
    if forbidden:
        errors.append(f"reset command includes forbidden destructive fragments: {forbidden}")
    start_text = command_text(start_commands[0]["command"]) if start_commands else ""
    if "start-agent-prompt-proxies.sh" not in start_text:
        errors.append("start command must use start-agent-prompt-proxies.sh")
    for target_root in config.target_roots:
        if target_root not in start_text:
            errors.append(f"start command must include allowed target root {target_root}")
    rerun_text = command_text(rerun_commands[0]["command"]) if rerun_commands else ""
    if "validate_stable_handoff.py" not in rerun_text:
        errors.append("rerun command must use validate_stable_handoff.py")
    return check(
        "productized_setup.command_contract",
        StableReleaseResetRehearsalStatus.PASSED if not errors else StableReleaseResetRehearsalStatus.FAILED,
        "Productized reset/start/rerun commands use the stable single code path."
        if not errors
        else "Productized reset/start/rerun command contract failed.",
        category="reset_contract",
        details={
            "errors": errors,
            "reset_commands": reset_commands,
            "start_commands": start_commands,
            "rerun_commands": rerun_commands,
        },
        next_action="" if not errors else "Fix productized setup commands instead of adding a second reset path.",
    )


def safe_disposable_root(config_root: Path, output_path: Path) -> Path:
    root = resolve_path(config_root, DEFAULT_DISPOSABLE_RUNTIME_STATE_ROOT).resolve()
    allowed_parent = resolve_path(config_root, DEFAULT_OUTPUT_DIR).resolve()
    if not root.is_relative_to(allowed_parent):
        raise RuntimeError(f"disposable runtime-state root {root} is outside {allowed_parent}")
    return root


def disposable_runtime_state_rehearsal(config_root: Path, output_path: Path) -> dict[str, Any]:
    root = safe_disposable_root(config_root, output_path)
    stale_file = root / "stale-controller-artifacts" / "request.json"
    regenerated_file = root / "regenerated-reset-proof.json"
    stale_file.parent.mkdir(parents=True, exist_ok=True)
    stale_file.write_text('{"stale": true}\n', encoding="utf-8")
    stale_exists_before = stale_file.exists()
    shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    proof = {
        "schema_version": SCHEMA_VERSION,
        "kind": "stable_release_reset_rehearsal_disposable_runtime_state_proof",
        "status": StableReleaseResetRehearsalStatus.PASSED.value,
        "created_at": utc_timestamp(),
        "message": "Disposable runtime-state was cleared and regenerated without touching real runtime-state root.",
    }
    write_json(regenerated_file, proof)
    stale_exists_after = stale_file.exists()
    regenerated_exists = regenerated_file.exists()
    errors: list[str] = []
    if not stale_exists_before:
        errors.append("stale disposable file was not created before rehearsal")
    if stale_exists_after:
        errors.append("stale disposable file still exists after rehearsal")
    if not regenerated_exists:
        errors.append("regenerated proof artifact was not written")
    return check(
        "runtime_state.disposable_rehearsal",
        StableReleaseResetRehearsalStatus.PASSED if not errors else StableReleaseResetRehearsalStatus.FAILED,
        "Disposable runtime-state reset rehearsal regenerated proof artifacts."
        if not errors
        else "Disposable runtime-state reset rehearsal failed.",
        category="runtime_state",
        details={
            "errors": errors,
            "disposable_runtime_state_root": str(root),
            "stale_file": str(stale_file),
            "stale_exists_before": stale_exists_before,
            "stale_exists_after": stale_exists_after,
            "regenerated_file": str(regenerated_file),
            "regenerated_exists": regenerated_exists,
        },
        next_action="" if not errors else "Inspect the disposable rehearsal path before running real reset/start recovery.",
    )


def runtime_state_hygiene_check(
    config: StableReleaseResetRehearsalConfig,
    *,
    output_path: Path,
    command_runner: CommandRunner,
) -> dict[str, Any]:
    report = validate_runtime_state_hygiene(
        RuntimeStateHygieneConfig(
            config_root=config.config_root,
            output_path=output_path.with_name(f"{output_path.stem}-runtime-state-hygiene.json"),
            command_timeout_seconds=min(120, config.command_timeout_seconds),
        ),
        command_runner=command_runner,
    )
    passed = report.get("status") == StableReleaseResetRehearsalStatus.PASSED.value
    return check(
        "runtime_state.hygiene_gate",
        StableReleaseResetRehearsalStatus.PASSED if passed else StableReleaseResetRehearsalStatus.FAILED,
        "Runtime-state hygiene gate passed."
        if passed
        else "Runtime-state hygiene gate failed.",
        category="runtime_state",
        details={
            "report_path": report.get("report_path"),
            "status": report.get("status"),
            "failed_check_ids": report.get("summary", {}).get("failed_check_ids", []),
        },
        next_action="" if passed else "Fix runtime-state tracking/ignore/proof hygiene before reset rehearsal.",
    )


def productized_reset_start_execution_check(
    config: StableReleaseResetRehearsalConfig,
    *,
    output_path: Path,
    command_runner: CommandRunner,
) -> dict[str, Any]:
    child_reports: list[dict[str, Any]] = []
    for action in (ProductizedSetupAction.RESET, ProductizedSetupAction.START):
        report = run_productized_setup(
            productized_config(
                config,
                action=action,
                output_path=output_path.with_name(f"{output_path.stem}-productized-{action.value}.json"),
            ),
            execute=config.execute_reset_start,
            command_runner=command_runner,
        )
        child_reports.append(
            {
                "action": action.value,
                "status": report.get("status"),
                "execute": report.get("execute"),
                "report_path": report.get("report_path"),
                "failed_check_ids": report.get("summary", {}).get("failed_check_ids", []),
                "executed_command_count": report.get("summary", {}).get("executed_command_count"),
            }
        )
    failed = [item for item in child_reports if item.get("status") != StableReleaseResetRehearsalStatus.PASSED.value]
    return check(
        "productized_setup.reset_start_execution",
        StableReleaseResetRehearsalStatus.FAILED if failed else StableReleaseResetRehearsalStatus.PASSED,
        "Productized reset/start execution passed."
        if config.execute_reset_start and not failed
        else "Productized reset/start plan passed without execution."
        if not failed
        else "Productized reset/start execution failed.",
        category="reset_contract",
        details={
            "execute_reset_start": config.execute_reset_start,
            "child_reports": child_reports,
            "failed": failed,
        },
        next_action="" if not failed else "Inspect the productized reset/start child report before running stable handoff.",
    )


def stable_handoff_recovery_check(
    config: StableReleaseResetRehearsalConfig,
    *,
    output_path: Path,
    command_runner: CommandRunner,
    fixture_state_reader: FixtureStateReader,
) -> dict[str, Any]:
    if not config.execute_recovery:
        rerun_commands = commands_for_action(
            productized_config(config, action=ProductizedSetupAction.RERUN, output_path=output_path),
            output_path,
        )
        return check(
            "stable_handoff.recovery_gate",
            StableReleaseResetRehearsalStatus.PASSED,
            "Stable handoff recovery gate is planned but not executed.",
            category="recovery",
            details={"execute_recovery": False, "rerun_commands": rerun_commands},
            next_action="Run with --execute-recovery for live release reset proof.",
        )
    report = run_productized_setup(
        productized_config(
            config,
            action=ProductizedSetupAction.RERUN,
            output_path=output_path.with_name(f"{output_path.stem}-productized-rerun.json"),
        ),
        execute=True,
        command_runner=command_runner,
    )
    passed = report.get("status") == StableReleaseResetRehearsalStatus.PASSED.value
    return check(
        "stable_handoff.recovery_gate",
        StableReleaseResetRehearsalStatus.PASSED if passed else StableReleaseResetRehearsalStatus.FAILED,
        "Stable handoff recovery gate passed after reset/start."
        if passed
        else "Stable handoff recovery gate failed after reset/start.",
        category="recovery",
        details={
            "execute_recovery": True,
            "report_path": report.get("report_path"),
            "status": report.get("status"),
            "failed_check_ids": report.get("summary", {}).get("failed_check_ids", []),
            "commands": report.get("commands", []),
            "execution_results": report.get("execution_results", []),
        },
        next_action="" if passed else "Inspect the stable handoff child reports before declaring stable reset practice usable.",
    )


def status_counts(checks: list[dict[str, Any]]) -> dict[str, int]:
    counts = {status.value: 0 for status in StableReleaseResetRehearsalStatus}
    for item in checks:
        status = str(item.get("status") or StableReleaseResetRehearsalStatus.FAILED.value)
        counts[status] = counts.get(status, 0) + 1
    return counts


def source_watch_paths_from_policy(policy: dict[str, Any]) -> tuple[Path, ...]:
    values = string_list(policy.get("source_watch_paths"))
    if not values:
        return DEFAULT_SOURCE_WATCH_PATHS
    return tuple(Path(value) for value in values)


def run_stable_release_reset_rehearsal(
    config: StableReleaseResetRehearsalConfig,
    *,
    command_runner: CommandRunner = default_command_runner,
    fixture_state_reader: FixtureStateReader = fixture_state,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root)
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    source_watch_paths = source_watch_paths_from_policy(policy)
    before_source_state = source_state(config_root, source_watch_paths)
    before_git_state = git_state(config_root)
    checks: list[dict[str, Any]] = [policy_check(policy)]
    try:
        before_fixture_state = fixture_state_reader(config.target_roots)
    except Exception as exc:  # noqa: BLE001
        before_fixture_state = None
        checks.append(
            check(
                "protected_fixture_state.preflight",
                StableReleaseResetRehearsalStatus.FAILED,
                "Protected fixture state could not be captured before reset rehearsal.",
                category="fixture_integrity",
                details={"error": f"{type(exc).__name__}: {exc}", "target_roots": list(config.target_roots)},
                next_action="Run the rehearsal from Bash with reachable /mnt/c fixture paths.",
            )
        )
    if before_fixture_state is not None:
        checks.extend(
            [
                runtime_state_hygiene_check(config, output_path=output_path, command_runner=command_runner),
                reset_command_contract_check(config, output_path),
                disposable_runtime_state_rehearsal(config_root, output_path),
                productized_reset_start_execution_check(config, output_path=output_path, command_runner=command_runner),
                stable_handoff_recovery_check(
                    config,
                    output_path=output_path,
                    command_runner=command_runner,
                    fixture_state_reader=fixture_state_reader,
                ),
            ]
        )
        try:
            after_fixture_state = fixture_state_reader(config.target_roots)
            checks.append(fixture_state_check(before_fixture_state, after_fixture_state))
        except Exception as exc:  # noqa: BLE001
            checks.append(
                check(
                    "protected_fixture_state.postflight",
                    StableReleaseResetRehearsalStatus.FAILED,
                    "Protected fixture state could not be captured after reset rehearsal.",
                    category="fixture_integrity",
                    details={"error": f"{type(exc).__name__}: {exc}", "target_roots": list(config.target_roots)},
                    next_action="Inspect fixture hashes/status manually before continuing stable release practice.",
                )
            )
    after_source_state = source_state(config_root, source_watch_paths)
    checks.append(source_state_check(before_source_state, after_source_state))
    checks.append(git_state_check(before_git_state, git_state(config_root)))
    failed_ids = [item["id"] for item in checks if item.get("status") == StableReleaseResetRehearsalStatus.FAILED.value]
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "status": StableReleaseResetRehearsalStatus.PASSED.value
        if not failed_ids
        else StableReleaseResetRehearsalStatus.FAILED.value,
        "created_at": utc_timestamp(),
        "phase": EXPECTED_PHASE,
        "config_root": str(config_root),
        "policy_path": str(policy_path),
        "target_roots": list(config.target_roots),
        "execute_reset_start": config.execute_reset_start,
        "execute_recovery": config.execute_recovery,
        "checks": checks,
        "summary": {
            "check_count": len(checks),
            "status_counts": status_counts(checks),
            "failed_check_ids": failed_ids,
            "source_watch_path_count": len(source_watch_paths),
        },
    }
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
