"""Phase 234 clean-clone or clean-snapshot release handoff gate."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "clean_clone_release_handoff_policy"
EXPECTED_REPORT_KIND = "clean_clone_release_handoff_report"
EXPECTED_PHASE = 234
EXPECTED_BACKLOG_ID = "P0-M14-234"
EXPECTED_MILESTONE_ID = "M14"
DEFAULT_POLICY_PATH = Path("runtime") / "clean_clone_release_handoff_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase234" / "phase234-clean-clone-release-handoff-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase234" / "phase234-clean-clone-release-handoff-report.md"
DEFAULT_SNAPSHOT_ROOT = Path(tempfile.gettempdir()) / "agentic_agents_phase234_clean_snapshot"
SNAPSHOT_MARKER = ".phase234_clean_snapshot"


class CleanHandoffStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class CleanHandoffDecision(str, Enum):
    READY = "clean_handoff_ready"
    BLOCKED = "blocked"


class SourceMode(str, Enum):
    GIT_CLONE = "git_clone"
    CLEAN_SNAPSHOT = "clean_snapshot"


@dataclass(frozen=True)
class CleanCloneReleaseHandoffConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path | None = DEFAULT_MARKDOWN_OUTPUT_PATH
    snapshot_root: Path = DEFAULT_SNAPSHOT_ROOT
    source_mode: SourceMode = SourceMode.CLEAN_SNAPSHOT
    prepare_snapshot: bool = False
    run_commands: bool = False
    run_live_minimal: bool = False
    timeout_seconds: int = 120


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object at {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def artifact_hash(path: Path | None) -> str | None:
    return sha256_file(path) if path is not None and path.is_file() else None


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def validation_error(error_id: str, message: str, *, source: str = "policy", severity: str = "high") -> dict[str, str]:
    return {"id": error_id, "message": message, "severity": severity, "source": source}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "phase must be 234"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if policy.get("milestone_id") != EXPECTED_MILESTONE_ID:
        errors.append(validation_error("policy.milestone_id", "milestone_id must be M14"))
    if SourceMode.CLEAN_SNAPSHOT.value not in string_list(policy.get("allowed_source_modes")):
        errors.append(validation_error("policy.allowed_source_modes", "clean_snapshot source mode must be allowed"))
    if not string_list(policy.get("forbidden_snapshot_entries")):
        errors.append(validation_error("policy.forbidden_snapshot_entries", "forbidden_snapshot_entries must be non-empty"))
    if not string_list(policy.get("required_files")):
        errors.append(validation_error("policy.required_files", "required_files must be non-empty"))
    seeds = policy.get("required_runtime_seeds")
    if not isinstance(seeds, list):
        errors.append(validation_error("policy.required_runtime_seeds", "required_runtime_seeds must be a list"))
    else:
        for index, seed in enumerate(seeds):
            seed_value = dict_value(seed)
            if not seed_value.get("id") or not seed_value.get("source_path") or not seed_value.get("snapshot_path"):
                errors.append(validation_error(f"policy.required_runtime_seeds.{index}", "seed entries require id, source_path, and snapshot_path"))
    required_commands = set(string_list(policy.get("required_command_ids")))
    expected_commands = {
        "docs_index",
        "phase232_handoff",
        "release_channels",
        "security_policy",
        "managed_stack_restart_from_snapshot",
        "first_time_user_doctor",
        "external_onboarding_live",
    }
    if required_commands != expected_commands:
        errors.append(validation_error("policy.required_command_ids", "required_command_ids must match the Phase 234 handoff command set"))
    if policy.get("live_minimal_required") is not True:
        errors.append(validation_error("policy.live_minimal_required", "live_minimal_required must be true"))
    if set(string_list(policy.get("required_target_roots"))) != {
        "/mnt/c/coinbase_testing_repo_frozen_tmp",
        "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    }:
        errors.append(validation_error("policy.required_target_roots", "both frozen Coinbase fixtures are required"))
    anythingllm = dict_value(policy.get("required_anythingllm"))
    if anythingllm.get("workflow_router_base_url") != "http://127.0.0.1:8500/v1":
        errors.append(validation_error("policy.required_anythingllm.workflow_router_base_url", "AnythingLLM must target workflow-router 8500/v1"))
    if anythingllm.get("api_base_url") != "http://127.0.0.1:3001":
        errors.append(validation_error("policy.required_anythingllm.api_base_url", "AnythingLLM API base URL must be 3001"))
    if anythingllm.get("workspace") != "my-workspace":
        errors.append(validation_error("policy.required_anythingllm.workspace", "workspace must be my-workspace"))
    return errors


def command_specs(snapshot_root: Path) -> dict[str, list[str]]:
    return {
        "docs_index": ["python3", "scripts/check_docs_index.py"],
        "phase232_handoff": [
            "python3",
            "scripts/validate_onboarding_release_handoff_refresh.py",
            "--output-path",
            "runtime-state/phase234/phase234-phase232-handoff.json",
            "--markdown-output-path",
            "runtime-state/phase234/phase234-phase232-handoff.md",
        ],
        "release_channels": [
            "python3",
            "scripts/validate_release_channels.py",
            "--output-path",
            "runtime-state/phase234/phase234-release-channels.json",
            "--skip-runtime-state-hygiene",
        ],
        "security_policy": [
            "python3",
            "scripts/validate_security_policy.py",
            "--output-path",
            "runtime-state/phase234/phase234-security-policy.json",
        ],
        "managed_stack_restart_from_snapshot": [
            "bash",
            "-lc",
            "./stop-agent-prompt-proxies.sh && ./start-agent-prompt-proxies.sh",
        ],
        "first_time_user_doctor": [
            "python3",
            "scripts/run_first_time_user_doctor.py",
            "--output-path",
            "runtime-state/phase234/phase234-first-time-user-doctor.json",
        ],
        "external_onboarding_live": [
            "python3",
            "scripts/validate_external_tester_onboarding.py",
            "--live-anythingllm",
            "--include-feedback",
            "--case-id",
            "ONB-001",
            "--output-path",
            "runtime-state/phase234/phase234-external-onboarding-live.json",
        ],
    }


def safe_snapshot_root(source_root: Path, snapshot_root: Path) -> tuple[bool, str]:
    source = source_root.resolve()
    target = snapshot_root.resolve()
    if target == source:
        return False, "snapshot root cannot equal source root"
    if source in target.parents:
        return False, "snapshot root must not be inside the active workspace"
    if target == target.anchor or str(target) in {"/", "/tmp", tempfile.gettempdir()}:
        return False, "snapshot root is too broad"
    if "phase234" not in target.name and "agentic_agents" not in target.name:
        return False, "snapshot root must be clearly phase/project scoped"
    return True, ""


def ignore_factory(forbidden_entries: set[str]):
    def ignore(_directory: str, names: list[str]) -> set[str]:
        ignored: set[str] = set()
        for name in names:
            if name in forbidden_entries or name.endswith(".pyc") or name.endswith(".pyo"):
                ignored.add(name)
        return ignored

    return ignore


def prepare_clean_snapshot(source_root: Path, snapshot_root: Path, forbidden_entries: list[str]) -> dict[str, Any]:
    ok, reason = safe_snapshot_root(source_root, snapshot_root)
    if not ok:
        return {"created": False, "path": str(snapshot_root), "error": reason}
    target = snapshot_root.resolve()
    marker = target / SNAPSHOT_MARKER
    if target.exists():
        temp_root = Path(tempfile.gettempdir()).resolve()
        known_temp_snapshot = target.parent == temp_root and target.name.startswith("agentic_agents_phase234_")
        if not marker.is_file() and not known_temp_snapshot:
            return {"created": False, "path": str(target), "error": "existing snapshot root is missing the Phase 234 marker"}
        shutil.rmtree(target)
    shutil.copytree(source_root.resolve(), target, ignore=ignore_factory(set(forbidden_entries)))
    marker.write_text("phase234 clean snapshot\n", encoding="utf-8")
    return {"created": True, "path": str(target), "error": ""}


def inspect_snapshot(config_root: Path, snapshot_root: Path, policy: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    safe, safety_error = safe_snapshot_root(config_root, snapshot_root)
    exists = snapshot_root.is_dir()
    forbidden_entries = string_list(policy.get("forbidden_snapshot_entries"))
    required_files = string_list(policy.get("required_files"))
    forbidden_present = [entry for entry in forbidden_entries if (snapshot_root / entry).exists()]
    missing_files = [entry for entry in required_files if not (snapshot_root / entry).is_file()]
    symlinks: list[str] = []
    required_hashes: dict[str, str] = {}
    content_digest = hashlib.sha256()
    if snapshot_root.is_dir():
        for path in snapshot_root.rglob("*"):
            if path.is_symlink():
                symlinks.append(str(path.relative_to(snapshot_root)))
                if len(symlinks) >= 20:
                    break
        for entry in required_files:
            path = snapshot_root / entry
            if path.is_file():
                digest = sha256_file(path)
                required_hashes[entry] = digest
                content_digest.update(entry.encode("utf-8"))
                content_digest.update(b"\0")
                content_digest.update(digest.encode("ascii"))
                content_digest.update(b"\0")
    if not safe:
        errors.append(validation_error("snapshot.safety", safety_error, source="snapshot"))
    if not exists:
        errors.append(validation_error("snapshot.exists", "snapshot root must exist", source="snapshot"))
    if forbidden_present:
        errors.append(validation_error("snapshot.forbidden_entries", "snapshot contains forbidden generated/source-control entries", source="snapshot"))
    if missing_files:
        errors.append(validation_error("snapshot.required_files", "snapshot is missing required release handoff files", source="snapshot"))
    if symlinks:
        errors.append(validation_error("snapshot.symlinks", "snapshot must not contain symlinks", source="snapshot"))
    record = {
        "path": str(snapshot_root),
        "exists": exists,
        "outside_active_workspace": safe,
        "marker_present": (snapshot_root / SNAPSHOT_MARKER).is_file(),
        "forbidden_entries_present": forbidden_present,
        "missing_required_files": missing_files,
        "required_file_count": len(required_files),
        "required_file_hashes": required_hashes,
        "required_manifest_sha256": content_digest.hexdigest() if required_hashes else None,
        "symlink_count": len(symlinks),
        "symlink_sample": symlinks,
    }
    return record, errors


def active_state_root(config_root: Path) -> Path:
    return config_root.parent / "private_agentic_agents" / "runtime-state"


def run_command(command_id: str, argv: list[str], *, cwd: Path, timeout_seconds: int, env: dict[str, str]) -> dict[str, Any]:
    started = utc_timestamp()
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "id": command_id,
            "command": argv,
            "started_at": started,
            "returncode": result.returncode,
            "status": CleanHandoffStatus.PASSED.value if result.returncode == 0 else CleanHandoffStatus.FAILED.value,
            "stdout_tail": result.stdout[-4000:],
            "stderr_tail": result.stderr[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "id": command_id,
            "command": argv,
            "started_at": started,
            "returncode": None,
            "status": CleanHandoffStatus.FAILED.value,
            "stdout_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            "error": f"command timed out after {timeout_seconds}s",
        }


def run_required_commands(
    *,
    config_root: Path,
    snapshot_root: Path,
    policy: dict[str, Any],
    run_live_minimal: bool,
    timeout_seconds: int,
) -> list[dict[str, Any]]:
    specs = command_specs(snapshot_root)
    command_ids = string_list(policy.get("required_command_ids"))
    if not run_live_minimal:
        command_ids = [command_id for command_id in command_ids if command_id != "external_onboarding_live"]
    env = os.environ.copy()
    env["AGENTIC_AGENTS_STATE_ROOT"] = str(active_state_root(config_root))
    return [
        run_command(command_id, specs[command_id], cwd=snapshot_root, timeout_seconds=timeout_seconds, env=env)
        for command_id in command_ids
    ]


def pid_cwd(pid_file: Path) -> dict[str, Any]:
    record: dict[str, Any] = {"pid_file": str(pid_file), "exists": pid_file.is_file()}
    if not pid_file.is_file():
        return record
    pid = pid_file.read_text(encoding="utf-8").strip()
    record["pid"] = pid
    proc_cwd = Path("/proc") / pid / "cwd"
    try:
        record["cwd"] = str(proc_cwd.resolve())
    except OSError as exc:
        record["error"] = str(exc)
    return record


def managed_stack_record(config_root: Path, snapshot_root: Path) -> dict[str, Any]:
    state = active_state_root(config_root)
    pids = {
        "llm_gateway": pid_cwd(state / "llm-gateway.pid"),
        "workflow_router_gateway": pid_cwd(state / "workflow-router-gateway.pid"),
        "controller_service": pid_cwd(state / "controller-service.pid"),
        "role_proxy": pid_cwd(state / "agent-prompt-proxy.pid"),
    }
    expected = str(snapshot_root.resolve())
    mismatched = [
        name
        for name, record in pids.items()
        if record.get("exists") is True and record.get("cwd") and str(record.get("cwd")) != expected
    ]
    missing = [name for name, record in pids.items() if record.get("exists") is not True]
    return {
        "state_root": str(state),
        "expected_cwd": expected,
        "pids": pids,
        "mismatched_cwd": mismatched,
        "missing_pid_files": missing,
        "all_running_from_snapshot": not mismatched and not missing,
    }


def git_status_short(path: Path) -> tuple[int | None, str]:
    result = subprocess.run(["git", "-C", str(path), "status", "--short"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        return result.returncode, result.stderr.strip()
    return result.returncode, result.stdout.strip()


def source_git_record(config_root: Path) -> dict[str, Any]:
    code, status = git_status_short(config_root)
    lines = [line for line in status.splitlines() if line.strip()] if code == 0 else []
    return {
        "git_status_returncode": code,
        "dirty_line_count": len(lines),
        "dirty_status_sha256": sha256_text(status),
        "dirty_status_sample": lines[:20],
    }


def fixture_state(root: Path) -> dict[str, Any]:
    record: dict[str, Any] = {"root": str(root), "exists": root.exists()}
    if not root.exists():
        record["status"] = CleanHandoffStatus.FAILED.value
        record["error"] = "fixture root is missing"
        return record
    if (root / ".git").is_dir():
        code, status = git_status_short(root)
        record["kind"] = "git"
        record["git_status_returncode"] = code
        record["git_status_sha256"] = sha256_text(status)
        record["git_status_line_count"] = len([line for line in status.splitlines() if line.strip()]) if code == 0 else None
        record["status_text"] = status[:1000]
        return record
    selected_files = [
        root / "core" / "stealth_order_manager.py",
        root / "README.md",
    ]
    file_hashes: dict[str, str] = {}
    for path in selected_files:
        if path.is_file():
            file_hashes[str(path.relative_to(root))] = sha256_file(path)
    record["kind"] = "file_hash"
    record["file_hashes"] = file_hashes
    return record


def collect_fixture_states(policy: dict[str, Any]) -> list[dict[str, Any]]:
    return [fixture_state(Path(root)) for root in string_list(policy.get("required_target_roots"))]


def compare_fixture_states(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    after_by_root = {item.get("root"): item for item in after}
    for item in before:
        root = item.get("root")
        final = after_by_root.get(root, {})
        unchanged = item == final
        status = CleanHandoffStatus.PASSED.value if unchanged and item.get("exists") is True else CleanHandoffStatus.FAILED.value
        records.append(
            {
                "root": root,
                "kind": item.get("kind"),
                "status": status,
                "unchanged": unchanged,
                "before": item,
                "after": final,
            }
        )
    return records


def seed_runtime_artifacts(config_root: Path, snapshot_root: Path, policy: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw_seed in policy.get("required_runtime_seeds", []):
        seed = dict_value(raw_seed)
        seed_id = str(seed.get("id") or "")
        source_path = resolve_path(config_root, str(seed.get("source_path") or ""))
        snapshot_path = resolve_path(snapshot_root, str(seed.get("snapshot_path") or ""))
        expected_kind = str(seed.get("expected_kind") or "")
        record: dict[str, Any] = {
            "id": seed_id,
            "source_path": str(source_path),
            "snapshot_path": str(snapshot_path),
            "expected_kind": expected_kind,
            "status": CleanHandoffStatus.FAILED.value,
        }
        if not source_path.is_file():
            record["error"] = "source seed file is missing"
            records.append(record)
            continue
        try:
            payload = read_json_object(source_path)
        except Exception as exc:  # noqa: BLE001
            record["error"] = f"source seed file is not valid JSON: {type(exc).__name__}: {exc}"
            records.append(record)
            continue
        if expected_kind and payload.get("kind") != expected_kind:
            record["error"] = f"source seed kind must be {expected_kind}"
            record["actual_kind"] = payload.get("kind")
            records.append(record)
            continue
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, snapshot_path)
        record.update(
            {
                "status": CleanHandoffStatus.PASSED.value,
                "source_sha256": sha256_file(source_path),
                "snapshot_sha256": sha256_file(snapshot_path),
                "kind": payload.get("kind"),
            }
        )
        records.append(record)
    return records


def validate_command_results(policy: dict[str, Any], command_results: list[dict[str, Any]], *, run_live_minimal: bool) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    required_ids = set(string_list(policy.get("required_command_ids")))
    actual_by_id = {str(item.get("id")): item for item in command_results}
    missing = sorted(required_ids - set(actual_by_id))
    if missing:
        errors.append(validation_error("commands.missing", "missing required command result(s): " + ", ".join(missing), source="commands"))
    failed = sorted(command_id for command_id, item in actual_by_id.items() if item.get("status") != CleanHandoffStatus.PASSED.value)
    if failed:
        errors.append(validation_error("commands.failed", "required command(s) failed: " + ", ".join(failed), source="commands"))
    if policy.get("live_minimal_required") is True and not run_live_minimal:
        errors.append(validation_error("commands.live_minimal", "external_onboarding_live must run for Phase 234", source="commands"))
    return errors


def build_clean_clone_release_handoff_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    policy_path: Path | None,
    snapshot_root: Path,
    source_mode: SourceMode,
    prepare_record: dict[str, Any] | None,
    snapshot_record: dict[str, Any],
    source_git: dict[str, Any],
    command_results: list[dict[str, Any]],
    managed_stack: dict[str, Any],
    runtime_seeds: list[dict[str, Any]],
    fixture_checks: list[dict[str, Any]],
    run_live_minimal: bool,
    source_errors: list[dict[str, str]],
) -> dict[str, Any]:
    errors = validate_policy(policy)
    errors.extend(source_errors)
    if source_mode.value not in string_list(policy.get("allowed_source_modes")):
        errors.append(validation_error("source_mode", f"source_mode {source_mode.value} is not allowed", source="source"))
    if source_mode == SourceMode.GIT_CLONE and source_git.get("dirty_line_count") != 0:
        errors.append(validation_error("source.git_dirty", "git_clone mode requires a clean source worktree", source="source"))
    if snapshot_record.get("exists") is not True or snapshot_record.get("outside_active_workspace") is not True:
        errors.append(validation_error("snapshot.ready", "snapshot must exist outside active workspace", source="snapshot"))
    if snapshot_record.get("forbidden_entries_present"):
        errors.append(validation_error("snapshot.forbidden_entries_present", "snapshot contains forbidden entries", source="snapshot"))
    if snapshot_record.get("missing_required_files"):
        errors.append(validation_error("snapshot.missing_required_files", "snapshot is missing required files", source="snapshot"))
    errors.extend(validate_command_results(policy, command_results, run_live_minimal=run_live_minimal))
    failed_seeds = [item for item in runtime_seeds if item.get("status") != CleanHandoffStatus.PASSED.value]
    if failed_seeds:
        errors.append(validation_error("runtime_seeds.failed", "required runtime seed artifact(s) failed", source="runtime_seeds"))
    if run_live_minimal and managed_stack.get("all_running_from_snapshot") is not True:
        errors.append(validation_error("managed_stack.snapshot_cwd", "managed stack must run from the clean snapshot before live proof", source="managed_stack"))
    failed_fixtures = [item for item in fixture_checks if item.get("status") != CleanHandoffStatus.PASSED.value or item.get("unchanged") is not True]
    if failed_fixtures:
        errors.append(validation_error("fixtures.mutated", "protected fixture state changed or could not be verified", source="fixtures"))
    status = CleanHandoffStatus.FAILED.value if errors else CleanHandoffStatus.PASSED.value
    decision = CleanHandoffDecision.READY.value if status == CleanHandoffStatus.PASSED.value else CleanHandoffDecision.BLOCKED.value
    passed_command_count = sum(1 for item in command_results if item.get("status") == CleanHandoffStatus.PASSED.value)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_id": EXPECTED_MILESTONE_ID,
        "generated_at": utc_timestamp(),
        "status": status,
        "decision": decision,
        "policy_path": str(policy_path.resolve()) if policy_path else None,
        "policy_sha256": artifact_hash(policy_path),
        "source_mode": source_mode.value,
        "source_mode_limitation": "clean_snapshot validates the current release-candidate workspace, not a committed remote clone"
        if source_mode == SourceMode.CLEAN_SNAPSHOT
        else "",
        "source_git": source_git,
        "snapshot_prepare": prepare_record or {},
        "snapshot": snapshot_record,
        "commands": command_results,
        "managed_stack": managed_stack,
        "runtime_seeds": runtime_seeds,
        "fixture_checks": fixture_checks,
        "validation_errors": errors,
        "summary": {
            "decision": decision,
            "source_mode": source_mode.value,
            "source_dirty_line_count": source_git.get("dirty_line_count"),
            "snapshot_ready": snapshot_record.get("exists") is True
            and snapshot_record.get("outside_active_workspace") is True
            and not snapshot_record.get("forbidden_entries_present")
            and not snapshot_record.get("missing_required_files"),
            "command_count": len(command_results),
            "passed_command_count": passed_command_count,
            "failed_command_count": len(command_results) - passed_command_count,
            "runtime_seed_count": len(runtime_seeds),
            "failed_runtime_seed_count": len(failed_seeds),
            "fixture_check_count": len(fixture_checks),
            "fixture_mutation_count": len(failed_fixtures),
            "live_minimal_ran": any(item.get("id") == "external_onboarding_live" for item in command_results),
            "managed_stack_from_snapshot": managed_stack.get("all_running_from_snapshot") is True,
            "validation_error_count": len(errors),
            "handoff_ready": not errors,
            "next_action": "work next approved milestone-aligned phase" if not errors else "repair clean handoff proof",
        },
    }


def stable_report(value: dict[str, Any]) -> dict[str, Any]:
    stable = json.loads(json.dumps(value))
    stable.pop("generated_at", None)
    stable.pop("report_path", None)
    return stable


def validate_clean_clone_release_handoff_report(
    report: dict[str, Any],
    *,
    config_root: Path,
    policy: dict[str, Any],
    policy_path: Path | None,
    snapshot_root: Path,
    source_mode: SourceMode,
    prepare_record: dict[str, Any] | None,
    snapshot_record: dict[str, Any],
    source_git: dict[str, Any],
    command_results: list[dict[str, Any]],
    managed_stack: dict[str, Any],
    runtime_seeds: list[dict[str, Any]],
    fixture_checks: list[dict[str, Any]],
    run_live_minimal: bool,
    source_errors: list[dict[str, str]],
) -> list[str]:
    expected = build_clean_clone_release_handoff_report(
        config_root=config_root,
        policy=policy,
        policy_path=policy_path,
        snapshot_root=snapshot_root,
        source_mode=source_mode,
        prepare_record=prepare_record,
        snapshot_record=snapshot_record,
        source_git=source_git,
        command_results=command_results,
        managed_stack=managed_stack,
        runtime_seeds=runtime_seeds,
        fixture_checks=fixture_checks,
        run_live_minimal=run_live_minimal,
        source_errors=source_errors,
    )
    return [] if stable_report(report) == stable_report(expected) else ["report must match rebuilt clean handoff report"]


def markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Phase 234 Clean Clone Release Handoff",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Decision: `{report.get('decision')}`",
        f"- Source mode: `{report.get('source_mode')}`",
        f"- Snapshot: `{dict_value(report.get('snapshot')).get('path')}`",
        f"- Commands passed: `{summary.get('passed_command_count')}/{summary.get('command_count')}`",
        f"- Fixture mutation count: `{summary.get('fixture_mutation_count')}`",
        f"- Validation errors: `{summary.get('validation_error_count')}`",
        "",
    ]
    limitation = report.get("source_mode_limitation")
    if limitation:
        lines.extend(["## Limitation", "", str(limitation), ""])
    if report.get("validation_errors"):
        lines.extend(["## Validation Errors", ""])
        for item in report["validation_errors"]:
            lines.append(f"- `{item.get('id')}`: {item.get('message')}")
        lines.append("")
    return "\n".join(lines)


def run_clean_clone_release_handoff(config: CleanCloneReleaseHandoffConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    source_errors: list[dict[str, str]] = []
    prepare_record: dict[str, Any] | None = None
    snapshot_root = config.snapshot_root.resolve()
    if config.prepare_snapshot:
        prepare_record = prepare_clean_snapshot(config_root, snapshot_root, string_list(policy.get("forbidden_snapshot_entries")))
        if prepare_record.get("created") is not True:
            source_errors.append(validation_error("snapshot.prepare", str(prepare_record.get("error")), source="snapshot"))
    before_fixtures = collect_fixture_states(policy)
    snapshot_record, snapshot_errors = inspect_snapshot(config_root, snapshot_root, policy)
    source_errors.extend(snapshot_errors)
    source_git = source_git_record(config_root)
    command_results: list[dict[str, Any]] = []
    runtime_seeds: list[dict[str, Any]] = []
    if config.run_commands and snapshot_record.get("exists") is True:
        runtime_seeds = seed_runtime_artifacts(config_root, snapshot_root, policy)
        command_results = run_required_commands(
            config_root=config_root,
            snapshot_root=snapshot_root,
            policy=policy,
            run_live_minimal=config.run_live_minimal,
            timeout_seconds=config.timeout_seconds,
        )
    managed_stack = managed_stack_record(config_root, snapshot_root)
    after_fixtures = collect_fixture_states(policy)
    fixture_checks = compare_fixture_states(before_fixtures, after_fixtures)
    report = build_clean_clone_release_handoff_report(
        config_root=config_root,
        policy=policy,
        policy_path=policy_path,
        snapshot_root=snapshot_root,
        source_mode=config.source_mode,
        prepare_record=prepare_record,
        snapshot_record=snapshot_record,
        source_git=source_git,
        command_results=command_results,
        managed_stack=managed_stack,
        runtime_seeds=runtime_seeds,
        fixture_checks=fixture_checks,
        run_live_minimal=config.run_live_minimal,
        source_errors=source_errors,
    )
    report_path = resolve_path(config_root, config.output_path)
    report["report_path"] = str(report_path)
    write_json(report_path, report)
    if config.markdown_output_path:
        write_text(resolve_path(config_root, config.markdown_output_path), markdown_report(report))
    return report
