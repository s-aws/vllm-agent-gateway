"""Controlled implementation workflow artifacts.

This module turns approved work packets into bounded draft/apply operations with
state and verification capture. It is deliberately controller-side: role prompts
can receive packets later, but path checks, write policy, resume, and
verification decisions live here.
"""

from __future__ import annotations

import hashlib
import difflib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.invocation import (
    InvocationResult,
    WorkflowStatus,
    list_failures,
    string_artifact_paths,
)
from vllm_agent_gateway.structure_index.indexer import (
    DEFAULT_MAX_FILE_BYTES as DEFAULT_STRUCTURE_MAX_FILE_BYTES,
    StructureIndexError,
    build_code_structure_index,
    build_index_slice,
    write_index_artifact,
)
from vllm_agent_gateway.controllers.documenter.orchestrator import collect_change_plan_items


SCHEMA_VERSION = 1
STATE_SCHEMA_VERSION = 1
DEFAULT_OUTPUT_DIR = ".agentic_reports"
DEFAULT_MAX_CONTEXT_TOKENS = 4000
DEFAULT_STRUCTURE_SLICE_RECORDS = 40
DEFAULT_VERIFICATION_TIMEOUT_SECONDS = 120
OUTPUT_EXCERPT_LIMIT = 2000
IMPLEMENTATION_MODES = {"draft", "apply"}
SUPPORTED_OPERATIONS = {"append_text", "replace_text", "create_file"}
RESUMABLE_STATUSES = {"running", "paused", "failed"}


class ImplementationWorkflowError(RuntimeError):
    """Raised for deterministic implementation workflow failures."""


@dataclass(frozen=True)
class WorkflowPaths:
    plan_path: Path
    state_path: Path
    report_path: Path


@dataclass(frozen=True)
class ImplementationWorkflowInvocationRequest:
    target_root: Path | str = "."
    output_dir: Path | str = DEFAULT_OUTPUT_DIR
    mode: str = "draft"
    packet_file: Path | str | None = None
    from_report: Path | str | None = None
    approve_change_plan_item: list[str] = field(default_factory=list)
    approve_all_safe: bool = False
    verification_commands: list[dict[str, Any]] = field(default_factory=list)
    verification_timeout_seconds: int = DEFAULT_VERIFICATION_TIMEOUT_SECONDS
    max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS
    structure_slice_records: int = DEFAULT_STRUCTURE_SLICE_RECORDS
    structure_max_file_bytes: int = DEFAULT_STRUCTURE_MAX_FILE_BYTES
    no_structure_index: bool = False
    resume: Path | str | None = None
    resume_allow_arg_changes: bool = False
    stop_after_packets: int | None = None

    @classmethod
    def from_namespace(
        cls,
        args: Any,
        verification_commands: list[dict[str, Any]] | None = None,
    ) -> "ImplementationWorkflowInvocationRequest":
        names = {item.name for item in fields(cls)}
        values = {name: getattr(args, name) for name in names if hasattr(args, name)}
        values["verification_commands"] = verification_commands if verification_commands is not None else []
        return cls(**values)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def artifact_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def sanitize_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return sanitized or "target"


def estimate_tokens(value: str) -> int:
    return max(1, (len(value) + 3) // 4)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ImplementationWorkflowError(f"Missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ImplementationWorkflowError(f"Invalid JSON file: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ImplementationWorkflowError(f"JSON file must contain an object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def normalize_target_path(target_root: Path, value: str) -> str:
    raw_path = Path(value)
    if raw_path.is_absolute():
        raise ImplementationWorkflowError(f"Target file must be repo-relative: {value}")
    candidate = (target_root / raw_path).resolve()
    try:
        rel_path = candidate.relative_to(target_root.resolve())
    except ValueError as exc:
        raise ImplementationWorkflowError(f"Target file is outside target root: {value}") from exc
    if any(part == ".." for part in rel_path.parts):
        raise ImplementationWorkflowError(f"Target file is outside target root: {value}")
    return rel_path.as_posix()


def require_under_directory(path: Path, directory: Path, label: str) -> None:
    try:
        path.resolve().relative_to(directory.resolve())
    except ValueError as exc:
        raise ImplementationWorkflowError(f"{label} must stay under configured output directory: {path}") from exc


def run_git(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ImplementationWorkflowError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def tracked_files(repo_root: Path) -> set[str]:
    return {line for line in run_git(repo_root, ["ls-files"]).splitlines() if line}


def output_summary(value: str, limit: int = OUTPUT_EXCERPT_LIMIT) -> dict[str, Any]:
    encoded = value.encode("utf-8", errors="replace")
    return {
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "byte_count": len(encoded),
        "excerpt": value[:limit],
        "truncated": len(value) > limit,
    }


def source_signature(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    resolved = path.resolve()
    return {
        "path": str(resolved),
        "sha256": sha256_file(resolved) if resolved.exists() else None,
    }


def operation_target(operation: dict[str, Any]) -> str:
    path = operation.get("path")
    if not isinstance(path, str) or not path:
        raise ImplementationWorkflowError("Implementation operation must contain a string path.")
    return path


def validate_operation(operation: dict[str, Any]) -> None:
    kind = operation.get("kind")
    if kind not in SUPPORTED_OPERATIONS:
        raise ImplementationWorkflowError(
            f"Unsupported implementation operation {kind!r}; expected one of {', '.join(sorted(SUPPORTED_OPERATIONS))}."
        )
    if kind == "append_text":
        if not isinstance(operation.get("content"), str):
            raise ImplementationWorkflowError("append_text operation requires string content.")
    elif kind == "replace_text":
        if not isinstance(operation.get("old"), str) or not isinstance(operation.get("new"), str):
            raise ImplementationWorkflowError("replace_text operation requires string old and new values.")
        if operation["old"] == "":
            raise ImplementationWorkflowError("replace_text operation old value cannot be empty.")
    elif kind == "create_file":
        if not isinstance(operation.get("content"), str):
            raise ImplementationWorkflowError("create_file operation requires string content.")


def apply_operation_to_content(
    existing_content: str | None,
    operation: dict[str, Any],
    target_file_exists: bool,
) -> str:
    kind = operation["kind"]
    if kind == "append_text":
        if existing_content is None:
            raise ImplementationWorkflowError("append_text requires an existing target file.")
        return existing_content + operation["content"]
    if kind == "replace_text":
        if existing_content is None:
            raise ImplementationWorkflowError("replace_text requires an existing target file.")
        count = existing_content.count(operation["old"])
        if count != 1:
            raise ImplementationWorkflowError(
                f"replace_text expected exactly one match in {operation['path']}, found {count}."
            )
        return existing_content.replace(operation["old"], operation["new"], 1)
    if kind == "create_file":
        if target_file_exists:
            raise ImplementationWorkflowError("create_file refuses to overwrite an existing target file.")
        return operation["content"]
    raise ImplementationWorkflowError(f"Unsupported operation kind: {kind}")


def unified_patch_text(target_file: str, before: str | None, after: str) -> str:
    before_lines = [] if before is None else before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{target_file}",
            tofile=f"b/{target_file}",
            lineterm="\n",
        )
    )


def write_patch_preview(patch_root: Path, packet_id: str, target_file: str, before: str | None, after: str) -> Path:
    patch_path = (patch_root / f"{sanitize_filename(packet_id)}-{sanitize_filename(target_file)}.diff").resolve()
    require_under_directory(patch_path, patch_root, "Implementation patch preview path")
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(unified_patch_text(target_file, before, after), encoding="utf-8")
    return patch_path


def rollback_metadata(operation: dict[str, Any], target_file: str) -> dict[str, Any]:
    kind = operation["kind"]
    if kind == "replace_text":
        return {
            "kind": "replace_text",
            "path": target_file,
            "old": operation["new"],
            "new": operation["old"],
            "status": "machine_applicable_if_new_text_is_unique",
        }
    if kind == "append_text":
        return {
            "kind": "manual_remove_appended_suffix",
            "path": target_file,
            "content": operation["content"],
            "status": "manual_or_policy_future",
        }
    return {"kind": "manual_restore", "path": target_file, "status": "manual_or_policy_future"}


def normalize_source_refs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    refs: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        path = item.get("path") or item.get("source_doc_id")
        if not isinstance(path, str):
            continue
        ref: dict[str, Any] = {"path": path}
        line_range = item.get("line_range") or item.get("lines")
        if (
            isinstance(line_range, list)
            and len(line_range) == 2
            and isinstance(line_range[0], int)
            and isinstance(line_range[1], int)
        ):
            ref["line_range"] = [line_range[0], line_range[1]]
        chunk_id = item.get("chunk_id") or item.get("source_chunk_id")
        if isinstance(chunk_id, str):
            ref["chunk_id"] = chunk_id
        refs.append(ref)
    return refs


def validate_packet(packet: dict[str, Any], target_root: Path, max_context_tokens: int) -> dict[str, Any]:
    packet_id = packet.get("id")
    if not isinstance(packet_id, str) or not packet_id:
        raise ImplementationWorkflowError("Every implementation packet requires a string id.")
    raw_target_files = packet.get("target_files")
    if not isinstance(raw_target_files, list) or not raw_target_files:
        raise ImplementationWorkflowError(f"Packet {packet_id} requires a non-empty target_files list.")
    target_files = [
        normalize_target_path(target_root, item)
        for item in raw_target_files
        if isinstance(item, str) and item
    ]
    if len(target_files) != len(raw_target_files):
        raise ImplementationWorkflowError(f"Packet {packet_id} target_files must be non-empty strings.")
    operation = packet.get("operation")
    if not isinstance(operation, dict):
        raise ImplementationWorkflowError(f"Packet {packet_id} requires an operation object.")
    operation = dict(operation)
    operation["path"] = normalize_target_path(target_root, operation_target(operation))
    validate_operation(operation)
    if operation["path"] not in target_files:
        raise ImplementationWorkflowError(
            f"Packet {packet_id} operation path must be listed in target_files: {operation['path']}"
        )
    allowed_operations = packet.get("allowed_operations")
    if allowed_operations is None:
        allowed_operations = [operation["kind"]]
    if not isinstance(allowed_operations, list) or not all(isinstance(item, str) for item in allowed_operations):
        raise ImplementationWorkflowError(f"Packet {packet_id} allowed_operations must be a string list.")
    if operation["kind"] not in allowed_operations:
        raise ImplementationWorkflowError(f"Packet {packet_id} operation kind is not allowed by packet policy.")
    acceptance_criteria = packet.get("acceptance_criteria")
    if not isinstance(acceptance_criteria, list) or not all(isinstance(item, str) for item in acceptance_criteria):
        raise ImplementationWorkflowError(f"Packet {packet_id} requires string acceptance_criteria.")
    packet_max_context = packet.get("max_context_tokens", max_context_tokens)
    if not isinstance(packet_max_context, int) or packet_max_context < 256:
        raise ImplementationWorkflowError(f"Packet {packet_id} max_context_tokens must be an integer >= 256.")
    packet_max_context = min(packet_max_context, max_context_tokens)
    normalized = {
        "id": packet_id,
        "task": packet.get("task", "implementation_packet"),
        "target_files": sorted(set(target_files)),
        "allowed_operations": sorted(set(allowed_operations)),
        "operation": operation,
        "source_refs": normalize_source_refs(packet.get("source_refs")),
        "acceptance_criteria": acceptance_criteria,
        "max_context_tokens": packet_max_context,
        "notes": packet.get("notes") if isinstance(packet.get("notes"), str) else "",
    }
    token_estimate = estimate_tokens(json.dumps(normalized, ensure_ascii=True, sort_keys=True))
    if token_estimate > packet_max_context:
        raise ImplementationWorkflowError(
            f"Packet {packet_id} exceeds max_context_tokens before indexing: {token_estimate} > {packet_max_context}."
        )
    normalized["input_token_estimate"] = token_estimate
    return normalized


def load_explicit_packet_file(packet_file: Path, target_root: Path, max_context_tokens: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = read_json(packet_file)
    raw_packets = data.get("packets")
    if isinstance(raw_packets, dict):
        raw_packets = [raw_packets]
    if not isinstance(raw_packets, list) or not raw_packets:
        raise ImplementationWorkflowError("Packet file must contain a non-empty packets list.")
    packets = [
        validate_packet(packet, target_root, max_context_tokens)
        for packet in raw_packets
        if isinstance(packet, dict)
    ]
    if len(packets) != len(raw_packets):
        raise ImplementationWorkflowError("Every packet file entry must be an object.")
    verification_commands = normalize_verification_commands(data.get("verification_commands"))
    return packets, verification_commands


def append_notes_for_change_item(item: dict[str, Any]) -> str:
    lines = [
        "",
        "",
        "<!-- agentic-implementation-draft:start -->",
        "## Implementation Draft Note",
        "",
        f"- Change plan item: {item.get('id', 'CP-????')}",
        f"- Category: {item.get('category', 'unknown')}",
        f"- Source: {item.get('source', 'unknown')}",
        f"- Confidence: {item.get('confidence', 'unknown')}",
        f"- Basis: {item.get('basis', 'unknown')}",
        "",
        str(item.get("text", "")),
        "",
        "<!-- agentic-implementation-draft:end -->",
        "",
    ]
    return "\n".join(lines)


def packets_from_documenter_report(
    report_path: Path,
    target_root: Path,
    approved_item_ids: list[str],
    approve_all_safe: bool,
    max_context_tokens: int,
) -> list[dict[str, Any]]:
    report = read_json(report_path)
    if report.get("kind") != "documenter_orchestrator_report":
        raise ImplementationWorkflowError("--from-report must point to a documenter_orchestrator_report JSON artifact.")
    approved = set(approved_item_ids)
    packets: list[dict[str, Any]] = []
    for item in collect_change_plan_items(report):
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        category = item.get("category")
        if not isinstance(item_id, str):
            continue
        if item_id not in approved and not (approve_all_safe and category == "safe_documentation_edit"):
            continue
        if category != "safe_documentation_edit":
            raise ImplementationWorkflowError(
                f"Change-plan item {item_id} is {category!r}; only safe_documentation_edit items can become packets."
            )
        target_file = item.get("target_file")
        if not isinstance(target_file, str):
            raise ImplementationWorkflowError(f"Change-plan item {item_id} is missing target_file.")
        source_refs: list[dict[str, Any]] = []
        if isinstance(item.get("source_doc_id"), str):
            ref: dict[str, Any] = {"path": item["source_doc_id"]}
            if isinstance(item.get("source_chunk_id"), str):
                ref["chunk_id"] = item["source_chunk_id"]
            if isinstance(item.get("lines"), list):
                ref["line_range"] = item["lines"]
            source_refs.append(ref)
        packet = {
            "id": f"IMP-{item_id}",
            "task": "draft_documentation_change_from_approved_change_plan_item",
            "target_files": [target_file],
            "allowed_operations": ["append_text"],
            "operation": {
                "kind": "append_text",
                "path": target_file,
                "content": append_notes_for_change_item(item),
            },
            "source_refs": source_refs,
            "acceptance_criteria": [
                "Draft artifact records the approved change-plan item.",
                "Target repository remains unmodified unless apply mode is explicit.",
            ],
            "max_context_tokens": max_context_tokens,
            "notes": f"Derived from {report_path}",
        }
        packets.append(validate_packet(packet, target_root, max_context_tokens))
    if not packets:
        raise ImplementationWorkflowError("No approved safe change-plan items were available to implement.")
    return packets


def normalize_verification_commands(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ImplementationWorkflowError("verification_commands must be a list.")
    commands: list[dict[str, Any]] = []
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict):
            raise ImplementationWorkflowError("Each verification command must be an object.")
        command = item.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command):
            raise ImplementationWorkflowError("Each verification command requires a non-empty string command list.")
        if not is_allowed_verification_command(command):
            raise ImplementationWorkflowError(
                "Verification command is outside controller policy; use pytest or python -m pytest."
            )
        timeout = item.get("timeout_seconds", DEFAULT_VERIFICATION_TIMEOUT_SECONDS)
        if not isinstance(timeout, int) or timeout < 1:
            raise ImplementationWorkflowError("verification timeout_seconds must be an integer >= 1.")
        associated_files = item.get("associated_files", [])
        if associated_files is None:
            associated_files = []
        if not isinstance(associated_files, list) or not all(isinstance(path, str) for path in associated_files):
            raise ImplementationWorkflowError("verification associated_files must be a string list.")
        command_id = item.get("id")
        commands.append(
            {
                "id": command_id if isinstance(command_id, str) and command_id else f"verification-{index:04d}",
                "command": command,
                "timeout_seconds": timeout,
                "associated_files": associated_files,
            }
        )
    return commands


def is_allowed_verification_command(command: list[str]) -> bool:
    if not command:
        return False
    executable = Path(command[0]).name.lower()
    if executable in {"pytest", "pytest.exe"}:
        return True
    python_names = {"python", "python3", "python.exe", "python3.exe", Path(sys.executable).name.lower()}
    return executable in python_names and len(command) >= 3 and command[1] == "-m" and command[2] == "pytest"


def pytest_verification_command(path: str, timeout_seconds: int = DEFAULT_VERIFICATION_TIMEOUT_SECONDS) -> dict[str, Any]:
    return {
        "id": f"pytest:{path}",
        "command": [sys.executable, "-m", "pytest", path],
        "timeout_seconds": timeout_seconds,
        "associated_files": [],
    }


def build_structure_slices(
    target_root: Path,
    output_dir: Path,
    packets: list[dict[str, Any]],
    max_records: int,
    max_file_bytes: int,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    artifacts: dict[str, str] = {}
    warnings: list[dict[str, Any]] = []
    try:
        index = build_code_structure_index(
            target_root=target_root,
            file_scope="tracked",
            max_file_bytes=max_file_bytes,
        )
        index_path = write_index_artifact(output_dir, target_root.name, index)
        artifacts["code_structure_index"] = str(index_path)
    except (ImplementationWorkflowError, StructureIndexError) as exc:
        warnings.append({"source": "code_structure_index", "reason": "unavailable", "detail": str(exc)})
        return artifacts, warnings

    for packet in packets:
        index_slice = build_index_slice(
            index,
            paths=packet["target_files"],
            max_records=max_records,
        )
        packet["structure_index_slice"] = index_slice
        packet["input_token_estimate"] = estimate_tokens(json.dumps(packet, ensure_ascii=True, sort_keys=True))
        if packet["input_token_estimate"] > packet["max_context_tokens"]:
            raise ImplementationWorkflowError(
                f"Packet {packet['id']} exceeds max_context_tokens after structure slice: "
                f"{packet['input_token_estimate']} > {packet['max_context_tokens']}."
            )
    return artifacts, warnings


def build_plan(
    target_root: Path,
    output_dir: Path,
    mode: str,
    packets: list[dict[str, Any]],
    verification_commands: list[dict[str, Any]],
    source: dict[str, Any],
    max_context_tokens: int,
    structure_index_enabled: bool,
    structure_slice_records: int,
    structure_max_file_bytes: int,
) -> dict[str, Any]:
    artifacts: dict[str, str] = {}
    warnings: list[dict[str, Any]] = []
    if structure_index_enabled:
        artifacts, warnings = build_structure_slices(
            target_root,
            output_dir,
            packets,
            structure_slice_records,
            structure_max_file_bytes,
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "implementation_plan",
        "generated_at": utc_now(),
        "target_root": str(target_root.resolve()),
        "mode": mode,
        "source": source,
        "packet_count": len(packets),
        "packets": packets,
        "verification_commands": verification_commands,
        "write_policy": {
            "default_mode": "draft",
            "target_repo_read_only": mode == "draft",
            "direct_apply_requires_explicit_mode": True,
            "apply_requires_tracked_existing_files": True,
            "out_of_scope_writes_refused": True,
        },
        "context_policy": {
            "max_context_tokens": max_context_tokens,
            "structure_index_enabled": structure_index_enabled,
            "structure_slice_max_records": structure_slice_records,
        },
        "tool_dependencies": [
            {"tool_id": "read_file", "purpose": "read_target_files_before_draft_or_apply", "read_only": True},
            {"tool_id": "run_tests", "purpose": "run_controller_declared_verification_commands", "read_only": False},
            {"tool_id": "git_ls_files", "purpose": "enforce_apply_only_to_tracked_files", "read_only": True},
        ],
        "artifacts": artifacts,
        "warnings": warnings,
    }


def make_paths(output_dir: Path, target_label: str, run_id: str) -> WorkflowPaths:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_target = sanitize_filename(target_label)
    return WorkflowPaths(
        plan_path=output_dir / f"implementation-plan-{safe_target}-{run_id}.json",
        state_path=output_dir / f"implementation-state-{safe_target}-{run_id}.json",
        report_path=output_dir / f"implementation-report-{safe_target}-{run_id}.json",
    )


def draft_path_for_packet(draft_root: Path, packet_id: str, target_file: str) -> Path:
    path = (draft_root / "files" / sanitize_filename(packet_id) / target_file).resolve()
    require_under_directory(path, draft_root, "Implementation draft path")
    return path


def process_packet_draft(
    packet: dict[str, Any],
    target_root: Path,
    draft_root: Path,
) -> dict[str, Any]:
    operation = packet["operation"]
    target_file = operation["path"]
    source_path = (target_root / target_file).resolve()
    exists = source_path.exists()
    existing = source_path.read_text(encoding="utf-8", errors="replace") if exists else None
    new_content = apply_operation_to_content(existing, operation, exists)
    draft_path = draft_path_for_packet(draft_root, packet["id"], target_file)
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(new_content, encoding="utf-8")
    patch_path = write_patch_preview(draft_root / "patches", packet["id"], target_file, existing, new_content)
    return {
        "packet_id": packet["id"],
        "mode": "draft",
        "target_file": target_file,
        "source_path": str(source_path),
        "draft_path": str(draft_path),
        "patch_preview": str(patch_path),
        "operation": operation["kind"],
        "target_modified": False,
        "draft_sha256": sha256_text(new_content),
    }


def process_packet_apply(
    packet: dict[str, Any],
    target_root: Path,
    tracked: set[str],
    patch_root: Path,
) -> dict[str, Any]:
    operation = packet["operation"]
    target_file = operation["path"]
    if target_file not in tracked:
        raise ImplementationWorkflowError(f"Refusing apply to untracked file: {target_file}")
    if operation["kind"] == "create_file":
        raise ImplementationWorkflowError("Apply mode refuses create_file until an explicit unsafe create policy exists.")
    target_path = (target_root / target_file).resolve()
    if not target_path.exists():
        raise ImplementationWorkflowError(f"Refusing apply because target file does not exist: {target_file}")
    before = target_path.read_text(encoding="utf-8", errors="replace")
    before_sha = sha256_text(before)
    after = apply_operation_to_content(before, operation, True)
    patch_path = write_patch_preview(patch_root, packet["id"], target_file, before, after)
    target_path.write_text(after, encoding="utf-8")
    after_sha = sha256_text(after)
    return {
        "packet_id": packet["id"],
        "mode": "apply",
        "target_file": target_file,
        "source_path": str(target_path),
        "patch_preview": str(patch_path),
        "operation": operation["kind"],
        "target_modified": True,
        "before_sha256": before_sha,
        "after_sha256": after_sha,
        "rollback_operation": rollback_metadata(operation, target_file),
        "rollback_hint": "Use VCS to restore before_sha256 content if the applied change is rejected.",
    }


def run_verification_command(command: dict[str, Any], target_root: Path) -> dict[str, Any]:
    started_at = utc_now()
    try:
        result = subprocess.run(
            command["command"],
            cwd=target_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=command["timeout_seconds"],
        )
        exit_code = result.returncode
        error = None
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired as exc:
        exit_code = None
        error = f"timeout after {command['timeout_seconds']} seconds"
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
    return {
        "id": command["id"],
        "command": command["command"],
        "working_directory": str(target_root),
        "timeout_seconds": command["timeout_seconds"],
        "started_at": started_at,
        "finished_at": utc_now(),
        "exit_code": exit_code,
        "status": "passed" if exit_code == 0 else "failed",
        "error": error,
        "stdout": output_summary(stdout),
        "stderr": output_summary(stderr),
        "associated_files": command.get("associated_files", []),
    }


def build_resume_key(
    target_root: Path,
    output_dir: Path,
    mode: str,
    source: dict[str, Any],
    max_context_tokens: int,
) -> dict[str, Any]:
    return {
        "target_root": str(target_root.resolve()),
        "output_dir": str(output_dir.resolve()),
        "mode": mode,
        "source": source,
        "max_context_tokens": max_context_tokens,
    }


def resume_key_mismatches(expected: dict[str, Any], current: dict[str, Any]) -> list[str]:
    mismatches: list[str] = []
    for key in sorted(set(expected) | set(current)):
        if expected.get(key) != current.get(key):
            mismatches.append(f"{key}: state={expected.get(key)!r} current={current.get(key)!r}")
    return mismatches


def write_state(path: Path, state: dict[str, Any]) -> None:
    state["schema_version"] = STATE_SCHEMA_VERSION
    state["kind"] = "implementation_state"
    state["updated_at"] = utc_now()
    write_json(path, state)


def build_report(state: dict[str, Any], plan: dict[str, Any], paths: WorkflowPaths) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "implementation_report",
        "generated_at": utc_now(),
        "status": state.get("status"),
        "target_root": plan.get("target_root"),
        "mode": plan.get("mode"),
        "plan": {
            "artifact": str(paths.plan_path),
            "packet_count": plan.get("packet_count"),
            "source": plan.get("source"),
        },
        "artifacts": {
            **plan.get("artifacts", {}),
            "implementation_plan": str(paths.plan_path),
            "implementation_state": str(paths.state_path),
            "implementation_report": str(paths.report_path),
            **({"draft_root": state["draft_root"]} if isinstance(state.get("draft_root"), str) else {}),
        },
        "write_policy": plan.get("write_policy"),
        "tool_dependencies": plan.get("tool_dependencies"),
        "completed_packets": state.get("completed_packets", []),
        "failed_packets": state.get("failed_packets", []),
        "changed_artifacts": state.get("changed_artifacts", []),
        "verification_results": state.get("verification_results", []),
        "implementation_results": state.get("implementation_results", []),
        "failure": state.get("failure"),
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    write_json(path, report)


def create_initial_state(
    run_id: str,
    target_root: Path,
    output_dir: Path,
    paths: WorkflowPaths,
    plan: dict[str, Any],
    resume_key: dict[str, Any],
) -> dict[str, Any]:
    draft_root = (output_dir / "implementation-drafts" / run_id).resolve()
    require_under_directory(draft_root, output_dir.resolve(), "Implementation draft root")
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "kind": "implementation_state",
        "generated_at": utc_now(),
        "run_id": run_id,
        "status": "running",
        "target_root": str(target_root.resolve()),
        "output_dir": str(output_dir.resolve()),
        "mode": plan["mode"],
        "resume_key": resume_key,
        "artifacts": {
            **plan.get("artifacts", {}),
            "implementation_plan": str(paths.plan_path),
            "implementation_state": str(paths.state_path),
        },
        "draft_root": str(draft_root),
        "queue_index": 0,
        "queued_packet_ids": [packet["id"] for packet in plan["packets"]],
        "completed_packets": [],
        "failed_packets": [],
        "changed_artifacts": [],
        "verification_results": [],
        "implementation_results": [],
        "verification_completed": False,
        "failure": None,
    }


def load_resume_state(resume_path: Path) -> tuple[Path, dict[str, Any]]:
    data = read_json(resume_path)
    if data.get("kind") == "implementation_state":
        return resume_path, data
    if data.get("kind") == "implementation_report":
        artifacts = data.get("artifacts")
        if not isinstance(artifacts, dict) or not isinstance(artifacts.get("implementation_state"), str):
            raise ImplementationWorkflowError("Implementation report does not reference implementation_state.")
        state_path = Path(artifacts["implementation_state"])
        if not state_path.is_absolute():
            state_path = (resume_path.parent / state_path).resolve()
        return state_path, read_json(state_path)
    raise ImplementationWorkflowError("--resume must point to an implementation state or report JSON artifact.")


def validate_resume_state(
    state: dict[str, Any],
    current_resume_key: dict[str, Any],
    allow_arg_changes: bool,
) -> None:
    if state.get("kind") != "implementation_state":
        raise ImplementationWorkflowError("Resume artifact is not an implementation_state.")
    if state.get("schema_version") != STATE_SCHEMA_VERSION:
        raise ImplementationWorkflowError(
            f"Unsupported implementation state schema_version: {state.get('schema_version')!r}."
        )
    if state.get("status") not in RESUMABLE_STATUSES:
        raise ImplementationWorkflowError(f"Implementation state is not resumable because status is {state.get('status')!r}.")
    previous = state.get("resume_key")
    if not isinstance(previous, dict):
        raise ImplementationWorkflowError("Implementation state is missing resume_key.")
    mismatches = resume_key_mismatches(previous, current_resume_key)
    if mismatches and not allow_arg_changes:
        detail = "\n".join(f"- {item}" for item in mismatches)
        raise ImplementationWorkflowError(
            "Resume arguments are incompatible with the saved implementation state. "
            "Use --resume-allow-arg-changes only if intentional.\n"
            f"{detail}"
        )


def complete_implementation_results(state: dict[str, Any], verification_decision: str) -> None:
    results: list[dict[str, Any]] = []
    for packet in state.get("completed_packets", []):
        if not isinstance(packet, dict):
            continue
        results.append(
            {
                "packet_id": packet.get("packet_id"),
                "operation_status": packet.get("status"),
                "changed_artifacts": packet.get("changed_artifacts", []),
                "verification_decision": verification_decision,
            }
        )
    state["implementation_results"] = results


def run_implementation_workflow(
    target_root: Path,
    output_dir: Path,
    mode: str,
    packet_file: Path | None = None,
    report_path: Path | None = None,
    approved_item_ids: list[str] | None = None,
    approve_all_safe: bool = False,
    verification_commands: list[dict[str, Any]] | None = None,
    max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
    build_structure_index_enabled: bool = True,
    structure_slice_records: int = DEFAULT_STRUCTURE_SLICE_RECORDS,
    structure_max_file_bytes: int = DEFAULT_STRUCTURE_MAX_FILE_BYTES,
    resume_path: Path | None = None,
    resume_allow_arg_changes: bool = False,
    stop_after_packets: int | None = None,
) -> tuple[dict[str, Any], WorkflowPaths]:
    if mode not in IMPLEMENTATION_MODES:
        raise ImplementationWorkflowError(f"mode must be one of: {', '.join(sorted(IMPLEMENTATION_MODES))}")
    if packet_file is not None and report_path is not None:
        raise ImplementationWorkflowError("Use either --packet-file or --from-report, not both.")
    if packet_file is None and report_path is None and resume_path is None:
        raise ImplementationWorkflowError("Use --packet-file, --from-report, or --resume.")
    target_root = target_root.resolve()
    output_dir = output_dir.resolve()
    verification_commands = verification_commands or []
    approved_item_ids = approved_item_ids or []

    if resume_path is not None:
        state_path, state = load_resume_state(resume_path.resolve())
        plan_path_value = state.get("artifacts", {}).get("implementation_plan") if isinstance(state.get("artifacts"), dict) else None
        if not isinstance(plan_path_value, str):
            raise ImplementationWorkflowError("Implementation state is missing implementation_plan artifact path.")
        plan_path = Path(plan_path_value)
        if not plan_path.is_absolute():
            plan_path = (state_path.parent / plan_path).resolve()
        plan = read_json(plan_path)
        paths = WorkflowPaths(
            plan_path=plan_path,
            state_path=state_path,
            report_path=Path(str(plan_path).replace("implementation-plan-", "implementation-report-", 1)),
        )
        source = plan.get("source") if isinstance(plan.get("source"), dict) else {}
        current_resume_key = build_resume_key(
            target_root,
            output_dir,
            mode,
            source,
            max_context_tokens,
        )
        validate_resume_state(state, current_resume_key, resume_allow_arg_changes)
        if isinstance(state.get("artifacts"), dict) and isinstance(state["artifacts"].get("implementation_report"), str):
            paths = WorkflowPaths(plan_path=plan_path, state_path=state_path, report_path=Path(state["artifacts"]["implementation_report"]))
    else:
        source: dict[str, Any]
        if packet_file is not None:
            packets, packet_verifications = load_explicit_packet_file(packet_file.resolve(), target_root, max_context_tokens)
            source = {"type": "packet_file", **(source_signature(packet_file) or {})}
            verification_commands = [*packet_verifications, *verification_commands]
        else:
            packets = packets_from_documenter_report(
                report_path=report_path.resolve() if report_path is not None else Path(),
                target_root=target_root,
                approved_item_ids=approved_item_ids,
                approve_all_safe=approve_all_safe,
                max_context_tokens=max_context_tokens,
            )
            source = {"type": "documenter_report", **(source_signature(report_path) or {})}
        run_id = artifact_timestamp()
        paths = make_paths(output_dir, target_root.name, run_id)
        plan = build_plan(
            target_root=target_root,
            output_dir=output_dir,
            mode=mode,
            packets=packets,
            verification_commands=verification_commands,
            source=source,
            max_context_tokens=max_context_tokens,
            structure_index_enabled=build_structure_index_enabled,
            structure_slice_records=structure_slice_records,
            structure_max_file_bytes=structure_max_file_bytes,
        )
        write_json(paths.plan_path, plan)
        resume_key = build_resume_key(target_root, output_dir, mode, source, max_context_tokens)
        state = create_initial_state(run_id, target_root, output_dir, paths, plan, resume_key)
        write_state(paths.state_path, state)

    state.setdefault("completed_packets", [])
    state.setdefault("failed_packets", [])
    state.setdefault("changed_artifacts", [])
    state.setdefault("verification_results", [])
    completed_ids = {
        item.get("packet_id")
        for item in state.get("completed_packets", [])
        if isinstance(item, dict) and isinstance(item.get("packet_id"), str)
    }
    queue_index = int(state.get("queue_index", 0)) if isinstance(state.get("queue_index"), int) else 0
    processed_this_run = 0

    tracked = tracked_files(target_root) if mode == "apply" else set()
    draft_root = Path(state["draft_root"]).resolve() if isinstance(state.get("draft_root"), str) else output_dir / "implementation-drafts"

    try:
        for index, packet in enumerate(plan.get("packets", [])):
            if not isinstance(packet, dict):
                continue
            if packet["id"] in completed_ids:
                continue
            if index < queue_index:
                continue
            if mode == "draft":
                changed = process_packet_draft(packet, target_root, draft_root)
            else:
                changed = process_packet_apply(packet, target_root, tracked, draft_root / "patches")
            state["changed_artifacts"].append(changed)
            state["completed_packets"].append(
                {
                    "packet_id": packet["id"],
                    "completed_at": utc_now(),
                    "status": "operation_complete",
                    "target_files": packet["target_files"],
                    "changed_artifacts": [changed],
                    "verification_decision": "pending",
                }
            )
            queue_index = index + 1
            state["queue_index"] = queue_index
            processed_this_run += 1
            write_state(paths.state_path, state)
            if stop_after_packets is not None and processed_this_run >= stop_after_packets:
                state["status"] = "paused"
                write_state(paths.state_path, state)
                report = build_report(state, plan, paths)
                write_report(paths.report_path, report)
                state.setdefault("artifacts", {})["implementation_report"] = str(paths.report_path)
                write_state(paths.state_path, state)
                return report, paths
    except ImplementationWorkflowError as exc:
        failure = {"failed_at": utc_now(), "stage": "packet_processing", "error": str(exc)}
        state["failed_packets"].append({"packet_id": packet.get("id") if isinstance(packet, dict) else None, **failure})
        state["status"] = "failed"
        state["failure"] = failure
        complete_implementation_results(state, "failed_before_verification")
        write_state(paths.state_path, state)
        report = build_report(state, plan, paths)
        write_report(paths.report_path, report)
        state.setdefault("artifacts", {})["implementation_report"] = str(paths.report_path)
        write_state(paths.state_path, state)
        return report, paths

    if not state.get("verification_completed"):
        if plan.get("verification_commands"):
            verification_results = [
                run_verification_command(command, target_root)
                for command in plan["verification_commands"]
                if isinstance(command, dict)
            ]
            state["verification_results"] = verification_results
            failed = [result for result in verification_results if result.get("status") != "passed"]
            decision = "failed" if failed else "passed"
            state["status"] = "failed" if failed else "completed"
            state["failure"] = (
                {
                    "failed_at": utc_now(),
                    "stage": "verification",
                    "failed_command_ids": [result.get("id") for result in failed],
                }
                if failed
                else None
            )
        else:
            decision = "not_run_no_verification_commands"
            state["verification_results"] = []
            state["status"] = "completed"
            state["failure"] = None
        state["verification_completed"] = True
        complete_implementation_results(state, decision)
        write_state(paths.state_path, state)

    report = build_report(state, plan, paths)
    write_report(paths.report_path, report)
    state.setdefault("artifacts", {})["implementation_report"] = str(paths.report_path)
    write_state(paths.state_path, state)
    return report, paths


def implementation_status_from_report(report: dict[str, Any]) -> WorkflowStatus:
    raw_status = report.get("status")
    if raw_status == "completed":
        return WorkflowStatus.COMPLETED
    if raw_status == "failed":
        return WorkflowStatus.FAILED
    return WorkflowStatus.PAUSED


def invoke_implementation_workflow(request: ImplementationWorkflowInvocationRequest) -> InvocationResult:
    report, paths = run_implementation_workflow(
        target_root=Path(request.target_root),
        output_dir=Path(request.output_dir),
        mode=request.mode,
        packet_file=Path(request.packet_file) if request.packet_file else None,
        report_path=Path(request.from_report) if request.from_report else None,
        approved_item_ids=request.approve_change_plan_item,
        approve_all_safe=bool(request.approve_all_safe),
        verification_commands=request.verification_commands,
        max_context_tokens=request.max_context_tokens,
        build_structure_index_enabled=not request.no_structure_index,
        structure_slice_records=request.structure_slice_records,
        structure_max_file_bytes=request.structure_max_file_bytes,
        resume_path=Path(request.resume) if request.resume else None,
        resume_allow_arg_changes=bool(request.resume_allow_arg_changes),
        stop_after_packets=request.stop_after_packets,
    )
    state = read_json(paths.state_path)
    artifact_paths = string_artifact_paths(report.get("artifacts"))
    artifact_paths.setdefault("implementation_plan", str(paths.plan_path))
    artifact_paths.setdefault("implementation_state", str(paths.state_path))
    artifact_paths.setdefault("implementation_report", str(paths.report_path))
    raw_resume_key = state.get("resume_key")
    raw_run_id = state.get("run_id")
    failures = list_failures(report.get("failed_packets"))
    if isinstance(report.get("failure"), dict):
        failures.append(report["failure"])
    return InvocationResult(
        workflow="implementation.workflow",
        status=implementation_status_from_report(report),
        artifact_paths=artifact_paths,
        summary_text=(
            f"status={report.get('status')} "
            f"completed_packets={len(report.get('completed_packets', []))} "
            f"failed_packets={len(report.get('failed_packets', []))}"
        ),
        failures=failures,
        resume_key=raw_resume_key if isinstance(raw_resume_key, dict) else None,
        report=report,
        run_id=raw_run_id if isinstance(raw_run_id, str) else None,
    )
