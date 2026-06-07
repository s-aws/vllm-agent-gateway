"""Versioned release channel validation for tester setup."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.profiles import ReleaseGateProfile, release_gate_profile_values
from vllm_agent_gateway.acceptance.runtime_state_hygiene import (
    RuntimeStateHygieneConfig,
    RuntimeStateHygieneStatus,
    collect_runtime_state_hygiene_checks,
    status_counts as runtime_state_status_counts,
)
from vllm_agent_gateway.acceptance.v1 import DEFAULT_TARGET_ROOTS, HEALTH_TARGETS


SCHEMA_VERSION = 1
DEFAULT_MANIFEST_PATH = Path("runtime") / "release_channels.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "release-channels"
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?$")


class ReleaseChannelId(str, Enum):
    DEV = "dev"
    RELEASE_CANDIDATE = "release-candidate"
    STABLE = "stable"


class ReleaseChannelStatus(str, Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"


class ReleaseChannelCheckStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ReleaseChannelValidationConfig:
    config_root: Path
    manifest_path: Path = DEFAULT_MANIFEST_PATH
    output_path: Path | None = None
    channel: str | None = None
    release_candidate_report_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"release-channels-{utc_timestamp()}.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_manifest_path(config_root: Path, manifest_path: Path) -> Path:
    return manifest_path if manifest_path.is_absolute() else config_root / manifest_path


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object at {path}")
    return value


def resolve_optional_path(config_root: Path, path: Path | None) -> Path | None:
    if path is None:
        return None
    return path if path.is_absolute() else config_root / path


def check(
    check_id: str,
    status: ReleaseChannelCheckStatus,
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


def failed_check(
    check_id: str,
    message: str,
    *,
    category: str,
    details: dict[str, Any] | None = None,
    next_action: str,
) -> dict[str, Any]:
    return check(
        check_id,
        ReleaseChannelCheckStatus.FAILED,
        message,
        category=category,
        details=details,
        next_action=next_action,
    )


def relative_path_exists(config_root: Path, raw_path: object) -> bool:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return False
    path = Path(raw_path)
    if path.is_absolute():
        return path.exists()
    return (config_root / path).exists()


def command_script_paths(command: object) -> list[str]:
    if not isinstance(command, list):
        return []
    scripts: list[str] = []
    for arg in command:
        if isinstance(arg, str) and arg.endswith(".py"):
            scripts.append(arg)
    return scripts


def channel_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    raw_channels = manifest.get("channels")
    if not isinstance(raw_channels, list):
        return []
    return [item for item in raw_channels if isinstance(item, dict)]


def selected_channel_entries(manifest: dict[str, Any], channel: str | None) -> list[dict[str, Any]]:
    entries = channel_entries(manifest)
    if channel is None:
        return entries
    return [item for item in entries if item.get("id") == channel]


def status_counts(checks: list[dict[str, Any]]) -> dict[str, int]:
    counts = {status.value: 0 for status in ReleaseChannelCheckStatus}
    for item in checks:
        status = str(item.get("status") or ReleaseChannelCheckStatus.FAILED.value)
        counts[status] = counts.get(status, 0) + 1
    return counts


def manifest_shape_checks(manifest: dict[str, Any], *, config_root: Path, manifest_path: Path, channel: str | None) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    shape_errors: list[str] = []
    if manifest.get("schema_version") != SCHEMA_VERSION:
        shape_errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if manifest.get("kind") != "release_channel_manifest":
        shape_errors.append("kind must be release_channel_manifest")
    version = manifest.get("harness_version")
    if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
        shape_errors.append("harness_version must be semantic version x.y.z or x.y.z-prerelease")
    components = manifest.get("component_versions")
    if not isinstance(components, dict):
        shape_errors.append("component_versions must be an object")
    else:
        for key in ("gateway_controller", "skill_registry", "skill_pack_policy", "docs"):
            component_version = components.get(key)
            if not isinstance(component_version, str) or not SEMVER_RE.fullmatch(component_version):
                shape_errors.append(f"component_versions.{key} must be semantic version x.y.z")
    entries = channel_entries(manifest)
    ids = [str(item.get("id")) for item in entries]
    expected_ids = [item.value for item in ReleaseChannelId]
    if ids != expected_ids:
        shape_errors.append(f"channels must be ordered as {expected_ids}")
    if channel is not None and channel not in expected_ids:
        shape_errors.append(f"unknown channel {channel!r}; expected one of {expected_ids}")
    checks.append(
        check(
            "manifest.shape",
            ReleaseChannelCheckStatus.PASSED if not shape_errors else ReleaseChannelCheckStatus.FAILED,
            "Release channel manifest shape is valid." if not shape_errors else "Release channel manifest shape is invalid.",
            category="manifest",
            details={
                "manifest_path": str(manifest_path),
                "config_root": str(config_root),
                "harness_version": version,
                "channel_ids": ids,
                "errors": shape_errors,
            },
            next_action="" if not shape_errors else "Fix runtime/release_channels.json before using a release channel.",
        )
    )
    return checks


def channel_contract_checks(manifest: dict[str, Any], *, config_root: Path, channel: str | None) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    entries = selected_channel_entries(manifest, channel)
    if channel is not None and not entries:
        checks.append(
            failed_check(
                f"channel.{channel}",
                "Requested release channel is not present in the manifest.",
                category="channel_contract",
                details={"channel": channel},
                next_action="Choose dev, release-candidate, or stable.",
            )
        )
        return checks

    allowed_profiles = set(release_gate_profile_values())
    required_ports = {int(item["port"]) for item in HEALTH_TARGETS if isinstance(item.get("port"), int)}
    default_roots = set(DEFAULT_TARGET_ROOTS)
    for entry in entries:
        channel_id = str(entry.get("id"))
        errors: list[str] = []
        status = entry.get("status")
        if status not in {item.value for item in ReleaseChannelStatus}:
            errors.append("status must be active or blocked")
        profile = entry.get("release_gate_profile")
        if profile not in allowed_profiles:
            errors.append("release_gate_profile must match a known release gate profile")
        setup_validator = entry.get("setup_validator")
        if not isinstance(setup_validator, dict):
            errors.append("setup_validator must be an object")
        else:
            command = setup_validator.get("command")
            if not isinstance(command, list) or not all(isinstance(arg, str) for arg in command):
                errors.append("setup_validator.command must be a string array")
            for script in command_script_paths(command):
                if not relative_path_exists(config_root, script):
                    errors.append(f"setup_validator command script is missing: {script}")
        acceptance_validator = entry.get("acceptance_validator")
        if not isinstance(acceptance_validator, dict):
            errors.append("acceptance_validator must be an object")
        else:
            command = acceptance_validator.get("command")
            if not isinstance(command, list) or not all(isinstance(arg, str) for arg in command):
                errors.append("acceptance_validator.command must be a string array")
            for script in command_script_paths(command):
                if not relative_path_exists(config_root, script):
                    errors.append(f"acceptance_validator command script is missing: {script}")
        for field_name in ("required_docs", "required_examples", "required_runtime_files"):
            raw_items = entry.get(field_name)
            if not isinstance(raw_items, list) or not all(isinstance(item, str) for item in raw_items):
                errors.append(f"{field_name} must be a string array")
                continue
            missing = [item for item in raw_items if not relative_path_exists(config_root, item)]
            if missing:
                errors.append(f"{field_name} missing files: {missing}")
        raw_ports = entry.get("required_ports")
        ports = {int(item.get("port")) for item in raw_ports if isinstance(item, dict) and isinstance(item.get("port"), int)} if isinstance(raw_ports, list) else set()
        if channel_id in {ReleaseChannelId.RELEASE_CANDIDATE.value, ReleaseChannelId.STABLE.value} and ports != required_ports:
            errors.append("release-candidate and stable required_ports must match all featured localhost ports")
        raw_env = entry.get("required_env_vars")
        env_vars = set(raw_env) if isinstance(raw_env, list) and all(isinstance(item, str) for item in raw_env) else set()
        if channel_id in {ReleaseChannelId.RELEASE_CANDIDATE.value, ReleaseChannelId.STABLE.value} and "ANYTHINGLLM_API_KEY" not in env_vars:
            errors.append("release-candidate and stable must require ANYTHINGLLM_API_KEY")
        raw_fixtures = entry.get("required_fixtures")
        fixtures = set(raw_fixtures) if isinstance(raw_fixtures, list) and all(isinstance(item, str) for item in raw_fixtures) else set()
        if channel_id in {ReleaseChannelId.RELEASE_CANDIDATE.value, ReleaseChannelId.STABLE.value} and fixtures != default_roots:
            errors.append("release-candidate and stable required_fixtures must match both frozen Coinbase roots")
        rollback = entry.get("rollback")
        if not isinstance(rollback, dict):
            errors.append("rollback must be an object")
        else:
            rollback_docs = rollback.get("docs")
            if not isinstance(rollback_docs, list) or not all(isinstance(item, str) for item in rollback_docs):
                errors.append("rollback.docs must be a string array")
            else:
                missing_docs = [item for item in rollback_docs if not relative_path_exists(config_root, item)]
                if missing_docs:
                    errors.append(f"rollback.docs missing files: {missing_docs}")
        checks.append(
            check(
                f"channel.{channel_id}.contract",
                ReleaseChannelCheckStatus.PASSED if not errors else ReleaseChannelCheckStatus.FAILED,
                f"Release channel {channel_id} contract is valid."
                if not errors
                else f"Release channel {channel_id} contract is invalid.",
                category="channel_contract",
                details={
                    "channel": channel_id,
                    "status": status,
                    "release_gate_profile": profile,
                    "errors": errors,
                },
                next_action="" if not errors else "Fix the channel metadata before publishing this channel.",
            )
        )
    return checks


def release_candidate_report_check(path: Path | None) -> tuple[ReleaseChannelCheckStatus, dict[str, Any], list[str]]:
    if path is None:
        return ReleaseChannelCheckStatus.FAILED, {}, ["release-candidate report path was not provided"]
    if not path.exists():
        return ReleaseChannelCheckStatus.FAILED, {"report_path": str(path)}, ["release-candidate report path does not exist"]
    try:
        report = read_json_object(path)
    except Exception as exc:  # noqa: BLE001
        return ReleaseChannelCheckStatus.FAILED, {"report_path": str(path)}, [f"report could not be read: {type(exc).__name__}: {exc}"]
    errors: list[str] = []
    if report.get("kind") != "v1_acceptance_report":
        errors.append("release-candidate report kind must be v1_acceptance_report")
    if report.get("status") != "passed":
        errors.append("release-candidate report status must be passed")
    accepted_profiles = {
        ReleaseGateProfile.RELEASE_CANDIDATE.value,
        ReleaseGateProfile.V1_1_RELEASE_CANDIDATE.value,
    }
    if report.get("profile") not in accepted_profiles:
        errors.append("release-candidate report profile must be release-candidate or v1.1-release-candidate")
    return (
        ReleaseChannelCheckStatus.PASSED if not errors else ReleaseChannelCheckStatus.FAILED,
        {
            "report_path": str(path),
            "kind": report.get("kind"),
            "status": report.get("status"),
            "profile": report.get("profile"),
        },
        errors,
    )


def stable_activation_report_path(config_root: Path, stable: dict[str, Any]) -> Path | None:
    readiness = stable.get("stable_readiness")
    if not isinstance(readiness, dict):
        return None
    raw_path = readiness.get("activated_from_report")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    path = Path(raw_path)
    return path if path.is_absolute() else config_root / path


def stable_readiness_checks(
    manifest: dict[str, Any],
    *,
    config_root: Path,
    release_candidate_report_path: Path | None,
    channel: str | None,
) -> list[dict[str, Any]]:
    if channel is not None and channel != ReleaseChannelId.STABLE.value:
        return []
    stable = next((item for item in channel_entries(manifest) if item.get("id") == ReleaseChannelId.STABLE.value), None)
    if not isinstance(stable, dict):
        return [
            failed_check(
                "stable.readiness",
                "Stable channel is missing.",
                category="stable_readiness",
                next_action="Add a stable channel entry to runtime/release_channels.json.",
            )
        ]
    if stable.get("status") != ReleaseChannelStatus.ACTIVE.value:
        return [
            check(
                "stable.readiness",
                ReleaseChannelCheckStatus.PASSED,
                "Stable channel is blocked until release-candidate validation passes.",
                category="stable_readiness",
                details={"stable_status": stable.get("status")},
            )
        ]
    explicit_report_path = resolve_optional_path(config_root, release_candidate_report_path)
    activation_report_path = stable_activation_report_path(config_root, stable)
    selected_report_path = explicit_report_path or activation_report_path
    status, details, errors = release_candidate_report_check(selected_report_path)
    if explicit_report_path is None and activation_report_path is not None:
        details["proof_source"] = "stable.stable_readiness.activated_from_report"
    elif explicit_report_path is not None:
        details["proof_source"] = "cli.release_candidate_report"
    else:
        details["proof_source"] = "missing"
    return [
        check(
            "stable.readiness",
            status,
            "Stable channel has passing release-candidate proof."
            if status == ReleaseChannelCheckStatus.PASSED
            else "Stable channel cannot be active without passing release-candidate proof.",
            category="stable_readiness",
            details={**details, "errors": errors},
            next_action=""
            if status == ReleaseChannelCheckStatus.PASSED
            else "Run scripts/validate_v1_acceptance.py --profile v1.1-release-candidate and pass the report path.",
        )
    ]


def runtime_state_hygiene_release_check(config_root: Path) -> dict[str, Any]:
    try:
        hygiene_checks = collect_runtime_state_hygiene_checks(RuntimeStateHygieneConfig(config_root=config_root))
    except Exception as exc:  # noqa: BLE001
        return failed_check(
            "runtime_state.hygiene",
            f"Runtime-state hygiene could not be validated: {type(exc).__name__}: {exc}",
            category="runtime_state",
            next_action="Run scripts/check_runtime_state_hygiene.py and fix the failed repository hygiene condition.",
        )
    failed_ids = [item["id"] for item in hygiene_checks if item.get("status") == RuntimeStateHygieneStatus.FAILED.value]
    return check(
        "runtime_state.hygiene",
        ReleaseChannelCheckStatus.PASSED if not failed_ids else ReleaseChannelCheckStatus.FAILED,
        "Runtime-state generated reports are ignored and durable proof metadata is retained."
        if not failed_ids
        else "Runtime-state hygiene failed; release-channel validation cannot pass.",
        category="runtime_state",
        details={
            "check_count": len(hygiene_checks),
            "status_counts": runtime_state_status_counts(hygiene_checks),
            "failed_check_ids": failed_ids,
            "checks": hygiene_checks,
        },
        next_action=""
        if not failed_ids
        else "Run scripts/check_runtime_state_hygiene.py and fix tracked runtime-state files, ignore coverage, proof metadata, or docs links.",
    )


def validate_release_channels(config: ReleaseChannelValidationConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    manifest_path = resolve_manifest_path(config_root, config.manifest_path)
    output_path = config.output_path or default_report_path(config_root)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "release_channel_validation_report",
        "status": ReleaseChannelCheckStatus.FAILED.value,
        "created_at": utc_timestamp(),
        "config_root": str(config_root),
        "manifest_path": str(manifest_path),
        "selected_channel": config.channel,
        "release_candidate_report_path": str(resolve_optional_path(config_root, config.release_candidate_report_path))
        if config.release_candidate_report_path
        else None,
        "harness_version": None,
        "channel_ids": [],
        "checks": [],
        "summary": {},
    }
    try:
        manifest = read_json_object(manifest_path)
        report["harness_version"] = manifest.get("harness_version")
        report["channel_ids"] = [str(item.get("id")) for item in channel_entries(manifest)]
        checks = [
            *manifest_shape_checks(manifest, config_root=config_root, manifest_path=manifest_path, channel=config.channel),
            *channel_contract_checks(manifest, config_root=config_root, channel=config.channel),
            *stable_readiness_checks(
                manifest,
                config_root=config_root,
                release_candidate_report_path=config.release_candidate_report_path,
                channel=config.channel,
            ),
            runtime_state_hygiene_release_check(config_root),
        ]
    except Exception as exc:  # noqa: BLE001
        checks = [
            failed_check(
                "manifest.load",
                f"Release channel manifest could not be loaded: {type(exc).__name__}: {exc}",
                category="manifest",
                next_action="Create runtime/release_channels.json before validating release channels.",
            )
        ]
    failed_ids = [item["id"] for item in checks if item.get("status") == ReleaseChannelCheckStatus.FAILED.value]
    warning_ids = [item["id"] for item in checks if item.get("status") == ReleaseChannelCheckStatus.WARNING.value]
    report["checks"] = checks
    report["summary"] = {
        "check_count": len(checks),
        "status_counts": status_counts(checks),
        "failed_check_ids": failed_ids,
        "warning_check_ids": warning_ids,
    }
    report["status"] = ReleaseChannelCheckStatus.PASSED.value if not failed_ids else ReleaseChannelCheckStatus.FAILED.value
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
