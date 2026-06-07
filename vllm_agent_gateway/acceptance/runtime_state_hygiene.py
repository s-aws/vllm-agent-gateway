"""Repository hygiene checks for local runtime-state artifacts."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from vllm_agent_gateway.acceptance.profiles import ReleaseGateProfile
from vllm_agent_gateway.docs_index import docs_index_report


SCHEMA_VERSION = 1
DEFAULT_REPORT_DIR = Path("runtime-state") / "runtime-state-hygiene"
DEFAULT_STABLE_PROOF_PATH = Path("runtime") / "release_proofs" / "v1-1-release-candidate-stable-proof.json"
DEFAULT_RELEASE_CHANNELS_PATH = Path("runtime") / "release_channels.json"
DEFAULT_IGNORE_SAMPLE_PATHS = (
    Path("runtime-state") / "hygiene-sample.json",
    Path("runtime-state") / "runtime-state-hygiene" / "current.json",
    Path("runtime-state") / "controller-artifacts" / "sample" / "request.json",
)
REQUIRED_POLICY_DOCS = (
    Path("README.runtime-state.md"),
    Path("docs") / "examples" / "runtime-state.md",
)


class RuntimeStateHygieneStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class CommandExecutionResult:
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[list[str], int], CommandExecutionResult]


@dataclass(frozen=True)
class RuntimeStateHygieneConfig:
    config_root: Path
    output_path: Path | None = None
    stable_proof_path: Path = DEFAULT_STABLE_PROOF_PATH
    release_channels_path: Path = DEFAULT_RELEASE_CHANNELS_PATH
    ignore_sample_paths: tuple[Path, ...] = DEFAULT_IGNORE_SAMPLE_PATHS
    command_timeout_seconds: int = 30


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"runtime-state-hygiene-{utc_timestamp()}.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_path(config_root: Path, raw_path: Path) -> Path:
    return raw_path if raw_path.is_absolute() else config_root / raw_path


def resolved_path_equal(left: Path, right: Path) -> bool:
    return left.resolve() == right.resolve()


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object at {path}")
    return value


def run_subprocess_command(command: list[str], timeout_seconds: int) -> CommandExecutionResult:
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout_seconds)
        return CommandExecutionResult(result.returncode, result.stdout, result.stderr)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return CommandExecutionResult(
            124,
            stdout,
            f"{stderr}\ncommand timed out after {timeout_seconds} seconds".strip(),
        )


def check(
    check_id: str,
    status: RuntimeStateHygieneStatus,
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


def git_command(
    config_root: Path,
    args: list[str],
    *,
    command_runner: CommandRunner,
    timeout_seconds: int,
) -> CommandExecutionResult:
    return command_runner(["git", "-C", str(config_root), *args], timeout_seconds)


def runtime_state_tracking_check(
    config_root: Path,
    *,
    command_runner: CommandRunner,
    timeout_seconds: int,
) -> dict[str, Any]:
    result = git_command(
        config_root,
        ["ls-files", "runtime-state"],
        command_runner=command_runner,
        timeout_seconds=timeout_seconds,
    )
    tracked_files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    errors: list[str] = []
    if result.returncode != 0:
        errors.append(f"git ls-files failed with return code {result.returncode}")
    if tracked_files:
        errors.append("runtime-state contains tracked files")
    return check(
        "runtime_state.tracked_files",
        RuntimeStateHygieneStatus.PASSED if not errors else RuntimeStateHygieneStatus.FAILED,
        "No generated runtime-state files are tracked."
        if not errors
        else "Generated runtime-state files are still tracked.",
        category="git",
        details={
            "command": ["git", "-C", str(config_root), "ls-files", "runtime-state"],
            "returncode": result.returncode,
            "tracked_files": tracked_files,
            "stderr": result.stderr.strip(),
            "errors": errors,
        },
        next_action=""
        if not errors
        else "Run git rm --cached -r runtime-state after confirming local reports should remain only on disk.",
    )


def runtime_state_ignore_check(
    config_root: Path,
    sample_paths: tuple[Path, ...],
    *,
    command_runner: CommandRunner,
    timeout_seconds: int,
) -> dict[str, Any]:
    sample_results: list[dict[str, Any]] = []
    unignored: list[str] = []
    for sample_path in sample_paths:
        sample = sample_path.as_posix()
        result = git_command(
            config_root,
            ["check-ignore", "-v", sample],
            command_runner=command_runner,
            timeout_seconds=timeout_seconds,
        )
        ignored = result.returncode == 0 and bool(result.stdout.strip())
        sample_results.append(
            {
                "sample_path": sample,
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "ignored": ignored,
            }
        )
        if not ignored:
            unignored.append(sample)
    return check(
        "runtime_state.gitignore",
        RuntimeStateHygieneStatus.PASSED if not unignored else RuntimeStateHygieneStatus.FAILED,
        "runtime-state generated report paths are covered by git ignore rules."
        if not unignored
        else "Some runtime-state generated report paths are not covered by git ignore rules.",
        category="git",
        details={
            "sample_results": sample_results,
            "unignored": unignored,
        },
        next_action="" if not unignored else "Add runtime-state/ to .gitignore and rerun this validator.",
    )


def stable_proof_check(config_root: Path, stable_proof_path: Path, release_channels_path: Path) -> dict[str, Any]:
    proof_path = resolve_path(config_root, stable_proof_path)
    manifest_path = resolve_path(config_root, release_channels_path)
    errors: list[str] = []
    details: dict[str, Any] = {"proof_path": str(proof_path), "release_channels_path": str(manifest_path)}
    try:
        proof = read_json_object(proof_path)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"stable proof could not be read: {type(exc).__name__}: {exc}")
        proof = {}
    accepted_profiles = {
        ReleaseGateProfile.RELEASE_CANDIDATE.value,
        ReleaseGateProfile.V1_1_RELEASE_CANDIDATE.value,
    }
    if proof:
        details.update(
            {
                "kind": proof.get("kind"),
                "status": proof.get("status"),
                "profile": proof.get("profile"),
                "proof_kind": proof.get("proof_kind"),
                "source_report": proof.get("source_report"),
            }
        )
        if proof.get("kind") != "v1_acceptance_report":
            errors.append("stable proof kind must be v1_acceptance_report")
        if proof.get("status") != RuntimeStateHygieneStatus.PASSED.value:
            errors.append("stable proof status must be passed")
        if proof.get("profile") not in accepted_profiles:
            errors.append("stable proof profile must be release-candidate or v1.1-release-candidate")
        if proof.get("proof_kind") != "stable_channel_activation_proof":
            errors.append("stable proof_kind must be stable_channel_activation_proof")
        for field_name in ("source_report", "retention_reason", "known_boundary"):
            if not isinstance(proof.get(field_name), str) or not str(proof.get(field_name)).strip():
                errors.append(f"stable proof {field_name} must be a non-empty string")
    try:
        manifest = read_json_object(manifest_path)
        stable = next(
            (
                item
                for item in manifest.get("channels", [])
                if isinstance(item, dict) and item.get("id") == "stable"
            ),
            None,
        )
        readiness = stable.get("stable_readiness") if isinstance(stable, dict) else None
        if not isinstance(readiness, dict):
            errors.append("release channel stable_readiness metadata is missing")
        else:
            raw_activated_from_report = readiness.get("activated_from_report")
            raw_activated_profile = readiness.get("activated_profile")
            details["manifest_activated_from_report"] = raw_activated_from_report
            details["manifest_activated_profile"] = raw_activated_profile
            if not isinstance(raw_activated_from_report, str) or not raw_activated_from_report.strip():
                errors.append("stable channel activated_from_report must be a non-empty string")
            elif not resolved_path_equal(resolve_path(config_root, Path(raw_activated_from_report)), proof_path):
                errors.append("stable channel activated_from_report must point to the committed stable proof")
            if proof and raw_activated_profile != proof.get("profile"):
                errors.append("stable channel activated_profile must match the committed stable proof profile")
            if proof and readiness.get("known_boundary") != proof.get("known_boundary"):
                errors.append("stable channel known_boundary must match the committed stable proof boundary")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"release channel manifest could not be read: {type(exc).__name__}: {exc}")
    details["errors"] = errors
    return check(
        "proof.stable_activation",
        RuntimeStateHygieneStatus.PASSED if not errors else RuntimeStateHygieneStatus.FAILED,
        "Committed stable activation proof is valid."
        if not errors
        else "Committed stable activation proof is missing or invalid.",
        category="proof_retention",
        details=details,
        next_action=""
        if not errors
        else "Commit a compact stable activation proof under runtime/release_proofs/ before relying on stable channel metadata.",
    )


def policy_docs_check(config_root: Path, required_docs: tuple[Path, ...] = REQUIRED_POLICY_DOCS) -> dict[str, Any]:
    missing = [path.as_posix() for path in required_docs if not resolve_path(config_root, path).exists()]
    docs_index = resolve_path(config_root, Path("docs") / "README.md")
    examples_index = resolve_path(config_root, Path("docs") / "examples" / "README.md")
    index_text = docs_index.read_text(encoding="utf-8") if docs_index.exists() else ""
    examples_text = examples_index.read_text(encoding="utf-8") if examples_index.exists() else ""
    unlinked: list[str] = []
    if "README.runtime-state.md" not in index_text:
        unlinked.append("docs/README.md missing README.runtime-state.md")
    if "examples/runtime-state.md" not in index_text:
        unlinked.append("docs/README.md missing docs/examples/runtime-state.md")
    if "runtime-state.md" not in examples_text:
        unlinked.append("docs/examples/README.md missing runtime-state.md")
    docs_report: dict[str, Any] = {}
    docs_index_errors: list[str] = []
    try:
        docs_report = docs_index_report(config_root)
        if docs_report.get("status") != RuntimeStateHygieneStatus.PASSED.value:
            docs_index_errors.append("docs index validation did not pass")
    except Exception as exc:  # noqa: BLE001
        docs_index_errors.append(f"docs index validation failed: {type(exc).__name__}: {exc}")
    errors = [*missing, *unlinked, *docs_index_errors]
    return check(
        "docs.runtime_state_policy",
        RuntimeStateHygieneStatus.PASSED if not errors else RuntimeStateHygieneStatus.FAILED,
        "Runtime-state retention docs exist and are indexed."
        if not errors
        else "Runtime-state retention docs are missing or unindexed.",
        category="documentation",
        details={
            "required_docs": [path.as_posix() for path in required_docs],
            "missing": missing,
            "unlinked": unlinked,
            "docs_index_report": docs_report,
            "docs_index_errors": docs_index_errors,
            "errors": errors,
        },
        next_action="" if not errors else "Add README.runtime-state.md, docs/examples/runtime-state.md, and index links.",
    )


def status_counts(checks: list[dict[str, Any]]) -> dict[str, int]:
    counts = {status.value: 0 for status in RuntimeStateHygieneStatus}
    for item in checks:
        status = str(item.get("status") or RuntimeStateHygieneStatus.FAILED.value)
        counts[status] = counts.get(status, 0) + 1
    return counts


def collect_runtime_state_hygiene_checks(
    config: RuntimeStateHygieneConfig,
    *,
    command_runner: CommandRunner = run_subprocess_command,
) -> list[dict[str, Any]]:
    config_root = config.config_root.resolve()
    return [
        runtime_state_tracking_check(
            config_root,
            command_runner=command_runner,
            timeout_seconds=config.command_timeout_seconds,
        ),
        runtime_state_ignore_check(
            config_root,
            config.ignore_sample_paths,
            command_runner=command_runner,
            timeout_seconds=config.command_timeout_seconds,
        ),
        stable_proof_check(config_root, config.stable_proof_path, config.release_channels_path),
        policy_docs_check(config_root),
    ]


def validate_runtime_state_hygiene(
    config: RuntimeStateHygieneConfig,
    *,
    command_runner: CommandRunner = run_subprocess_command,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root)
    checks = collect_runtime_state_hygiene_checks(config, command_runner=command_runner)
    failed_ids = [item["id"] for item in checks if item.get("status") == RuntimeStateHygieneStatus.FAILED.value]
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "runtime_state_hygiene_report",
        "status": RuntimeStateHygieneStatus.PASSED.value
        if not failed_ids
        else RuntimeStateHygieneStatus.FAILED.value,
        "created_at": utc_timestamp(),
        "config_root": str(config_root),
        "stable_proof_path": str(resolve_path(config_root, config.stable_proof_path)),
        "release_channels_path": str(resolve_path(config_root, config.release_channels_path)),
        "ignore_sample_paths": [path.as_posix() for path in config.ignore_sample_paths],
        "checks": checks,
        "summary": {
            "check_count": len(checks),
            "status_counts": status_counts(checks),
            "failed_check_ids": failed_ids,
        },
    }
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
