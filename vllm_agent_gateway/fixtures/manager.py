"""Controlled fixture setup, snapshot, and cleanup helpers."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
MANIFEST_KIND = "fixture_manifest"
DEFAULT_MANIFEST_PATH = Path("runtime") / "fixtures.json"
DEFAULT_OUTPUT_ROOT = Path("runtime-state") / "managed-fixtures"
IGNORED_DIR_NAMES = {".git", "__pycache__", ".pytest_cache", ".mypy_cache"}


class FixtureCommand(str, Enum):
    VALIDATE = "validate"
    SNAPSHOT = "snapshot"
    SETUP = "setup"
    CLEANUP = "cleanup"


class FixtureManagerError(RuntimeError):
    pass


@dataclass(frozen=True)
class FixtureEntry:
    fixture_id: str
    source_path: Path
    category: str
    protected: bool
    disposable_only: bool
    watched_paths: tuple[str, ...]
    description: str = ""


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FixtureManagerError(f"manifest root must be an object: {path}")
    return value


def resolve_path(config_root: Path, raw_path: str) -> Path:
    normalized = raw_path.strip().replace("\\", "/")
    if normalized.startswith("/mnt/c/"):
        windows_path = Path("C:/" + normalized[len("/mnt/c/") :])
        if windows_path.exists():
            return windows_path.resolve()
    path = Path(raw_path)
    if path.is_absolute():
        return path.resolve()
    return (config_root / path).resolve()


def validate_relative_path(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    if not normalized or normalized.startswith("/") or normalized.startswith("../") or "/../" in normalized:
        raise FixtureManagerError(f"watched path must be relative and inside the fixture: {value!r}")
    return normalized


def load_fixture_manifest(config_root: Path, manifest_path: Path | None = None) -> dict[str, Any]:
    path = manifest_path or DEFAULT_MANIFEST_PATH
    path = path if path.is_absolute() else config_root / path
    manifest = read_json(path)
    errors = validate_fixture_manifest(manifest, config_root=config_root)
    if errors:
        raise FixtureManagerError("; ".join(errors))
    return manifest


def validate_fixture_manifest(manifest: dict[str, Any], *, config_root: Path) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if manifest.get("kind") != MANIFEST_KIND:
        errors.append(f"kind must be {MANIFEST_KIND}")
    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        errors.append("fixtures must be a non-empty list")
        return errors
    seen: set[str] = set()
    for index, raw in enumerate(fixtures):
        prefix = f"fixtures[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{prefix} must be an object")
            continue
        fixture_id = raw.get("id")
        if not isinstance(fixture_id, str) or not fixture_id.strip():
            errors.append(f"{prefix}.id must be a non-empty string")
            fixture_id = ""
        if fixture_id in seen:
            errors.append(f"{prefix}.id duplicates {fixture_id}")
        seen.add(fixture_id)
        source_path = raw.get("source_path")
        if not isinstance(source_path, str) or not source_path.strip():
            errors.append(f"{prefix}.source_path must be a non-empty string")
        else:
            resolved = resolve_path(config_root, source_path)
            if not resolved.is_dir():
                errors.append(f"{prefix}.source_path does not exist or is not a directory: {source_path}")
        for field_name in ("category", "description"):
            if raw.get(field_name) is not None and not isinstance(raw.get(field_name), str):
                errors.append(f"{prefix}.{field_name} must be a string")
        for field_name in ("protected", "disposable_only"):
            if not isinstance(raw.get(field_name), bool):
                errors.append(f"{prefix}.{field_name} must be a boolean")
        watched_paths = raw.get("watched_paths")
        if not isinstance(watched_paths, list) or not watched_paths:
            errors.append(f"{prefix}.watched_paths must be a non-empty list")
        else:
            for path_index, watched_path in enumerate(watched_paths):
                if not isinstance(watched_path, str):
                    errors.append(f"{prefix}.watched_paths[{path_index}] must be a string")
                    continue
                try:
                    validate_relative_path(watched_path)
                except FixtureManagerError as exc:
                    errors.append(f"{prefix}.watched_paths[{path_index}]: {exc}")
    return errors


def fixture_entries(config_root: Path, manifest: dict[str, Any]) -> tuple[FixtureEntry, ...]:
    entries: list[FixtureEntry] = []
    for raw in manifest["fixtures"]:
        entries.append(
            FixtureEntry(
                fixture_id=raw["id"],
                source_path=resolve_path(config_root, raw["source_path"]),
                category=raw.get("category") or "unspecified",
                protected=raw["protected"],
                disposable_only=raw["disposable_only"],
                watched_paths=tuple(validate_relative_path(path) for path in raw["watched_paths"]),
                description=raw.get("description") or "",
            )
        )
    return tuple(entries)


def selected_entries(entries: tuple[FixtureEntry, ...], selected_ids: tuple[str, ...] = ()) -> tuple[FixtureEntry, ...]:
    if not selected_ids:
        return entries
    wanted = set(selected_ids)
    by_id = {entry.fixture_id: entry for entry in entries}
    missing = sorted(wanted - set(by_id))
    if missing:
        raise FixtureManagerError("unknown fixture id(s): " + ", ".join(missing))
    return tuple(by_id[fixture_id] for fixture_id in selected_ids)


def should_hash_path(path: Path) -> bool:
    return not any(part in IGNORED_DIR_NAMES for part in path.parts)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_tree(root: Path) -> dict[str, str]:
    root = root.resolve()
    if not root.is_dir():
        raise FixtureManagerError(f"fixture root does not exist: {root}")
    hashes: dict[str, str] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file() and should_hash_path(item.relative_to(root))):
        hashes[path.relative_to(root).as_posix()] = sha256_file(path)
    if not hashes:
        raise FixtureManagerError(f"fixture root has no hashable files: {root}")
    return hashes


def watched_hashes(root: Path, watched_paths: tuple[str, ...]) -> dict[str, str]:
    root = root.resolve()
    hashes: dict[str, str] = {}
    for relative_path in watched_paths:
        path = root / relative_path
        if path.exists() and path.is_file():
            hashes[relative_path] = sha256_file(path)
    if not hashes:
        raise FixtureManagerError(f"{root} did not contain any watched fixture files")
    return hashes


def git_status(root: Path) -> dict[str, Any] | None:
    root = root.resolve()
    if not (root / ".git").exists():
        return None
    result = subprocess.run(["git", "-C", str(root), "status", "--short"], check=True, capture_output=True, text=True)
    lines = result.stdout.splitlines()
    return {
        "clean": result.stdout == "",
        "line_count": len(lines),
        "sha256": hashlib.sha256(result.stdout.encode("utf-8")).hexdigest(),
        "sample": lines[:5],
    }


def fixture_snapshot(entry: FixtureEntry, *, include_tree_hashes: bool = False) -> dict[str, Any]:
    snapshot = {
        "fixture_id": entry.fixture_id,
        "source_path": str(entry.source_path),
        "category": entry.category,
        "protected": entry.protected,
        "disposable_only": entry.disposable_only,
        "watched_hashes": watched_hashes(entry.source_path, entry.watched_paths),
        "git_status": git_status(entry.source_path),
    }
    if include_tree_hashes:
        snapshot["tree_hashes"] = hash_tree(entry.source_path)
    return snapshot


def ensure_under_root(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve()
    resolved_root = root.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise FixtureManagerError(f"{label} must stay under {resolved_root}: {resolved}") from exc
    return resolved


def fixture_copy_destination(output_root: Path, run_id: str, fixture_id: str) -> Path:
    safe_run_id = "".join(char if char.isalnum() or char in "._-" else "-" for char in run_id).strip("-")
    safe_fixture_id = "".join(char if char.isalnum() or char in "._-" else "-" for char in fixture_id).strip("-")
    if not safe_run_id or not safe_fixture_id:
        raise FixtureManagerError("run_id and fixture_id must contain at least one safe character")
    return output_root / safe_run_id / safe_fixture_id


def copy_fixture(entry: FixtureEntry, output_root: Path, *, run_id: str) -> dict[str, Any]:
    output_root = output_root.resolve()
    destination = ensure_under_root(fixture_copy_destination(output_root, run_id, entry.fixture_id), output_root, "fixture copy destination")
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    before = fixture_snapshot(entry)
    shutil.copytree(entry.source_path, destination, ignore=shutil.ignore_patterns(*IGNORED_DIR_NAMES))
    copy_hashes = hash_tree(destination)
    after = fixture_snapshot(entry)
    if before["watched_hashes"] != after["watched_hashes"] or before["git_status"] != after["git_status"]:
        raise FixtureManagerError(f"copy changed protected fixture source: {entry.fixture_id}")
    return {
        "fixture_id": entry.fixture_id,
        "source_path": str(entry.source_path),
        "copy_root": str(destination),
        "source_snapshot_before": before,
        "source_snapshot_after": after,
        "source_unchanged": True,
        "copy_hash_count": len(copy_hashes),
        "copy_tree_sha256": hashlib.sha256(json.dumps(copy_hashes, sort_keys=True).encode("utf-8")).hexdigest(),
    }


def cleanup_run(output_root: Path, *, run_id: str) -> dict[str, Any]:
    output_root = output_root.resolve()
    run_root = ensure_under_root(output_root / run_id, output_root, "cleanup run root")
    existed = run_root.exists()
    if existed:
        shutil.rmtree(run_root)
    return {
        "run_id": run_id,
        "run_root": str(run_root),
        "existed": existed,
        "removed": not run_root.exists(),
    }


def default_report_path(config_root: Path, command: FixtureCommand) -> Path:
    return config_root / "runtime-state" / "fixture-manager" / f"fixture-manager-{command.value}-{utc_timestamp()}.json"


def run_fixture_manager(
    *,
    config_root: Path,
    command: FixtureCommand,
    manifest_path: Path | None = None,
    fixture_ids: tuple[str, ...] = (),
    output_root: Path | None = None,
    run_id: str | None = None,
    cleanup_after: bool = False,
    include_tree_hashes: bool = False,
    report_path: Path | None = None,
) -> dict[str, Any]:
    config_root = config_root.resolve()
    output_root = (output_root or config_root / DEFAULT_OUTPUT_ROOT).resolve()
    run_id = run_id or f"fixture-run-{utc_timestamp()}"
    command = FixtureCommand(command)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "fixture_manager_report",
        "status": "failed",
        "command": command.value,
        "created_at": utc_timestamp(),
        "config_root": str(config_root),
        "manifest_path": str((manifest_path or DEFAULT_MANIFEST_PATH)),
        "output_root": str(output_root),
        "run_id": run_id,
        "selected_fixture_ids": list(fixture_ids),
        "fixtures": [],
        "setup": [],
        "cleanup": {},
        "errors": [],
    }
    try:
        manifest = load_fixture_manifest(config_root, manifest_path)
        entries = selected_entries(fixture_entries(config_root, manifest), fixture_ids)
        report["fixtures"] = [
            {
                "fixture_id": entry.fixture_id,
                "source_path": str(entry.source_path),
                "category": entry.category,
                "protected": entry.protected,
                "disposable_only": entry.disposable_only,
                "watched_paths": list(entry.watched_paths),
            }
            for entry in entries
        ]
        if command == FixtureCommand.SNAPSHOT:
            report["snapshots"] = [fixture_snapshot(entry, include_tree_hashes=include_tree_hashes) for entry in entries]
        elif command == FixtureCommand.SETUP:
            report["setup"] = [copy_fixture(entry, output_root, run_id=run_id) for entry in entries]
            if cleanup_after:
                report["cleanup"] = cleanup_run(output_root, run_id=run_id)
        elif command == FixtureCommand.CLEANUP:
            report["cleanup"] = cleanup_run(output_root, run_id=run_id)
        report["status"] = "passed"
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"{type(exc).__name__}: {exc}")
    path = report_path or default_report_path(config_root, command)
    write_json(path, report)
    report["report_path"] = str(path.resolve())
    write_json(path, report)
    return report
