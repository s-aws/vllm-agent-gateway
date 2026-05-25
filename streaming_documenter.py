#!/usr/bin/env python3
"""Streaming document processing primitives for large documenter inputs."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


STREAMING_SCHEMA_VERSION = 1
DEFAULT_CHUNK_BYTES = 64 * 1024
DEFAULT_READ_BLOCK_BYTES = 8 * 1024
DEFAULT_HEADING_SAMPLE_BYTES = 64 * 1024
MODE_REGISTRY: dict[str, dict[str, Any]] = {
    "context_presence": {
        "input_type": "text",
        "chunking_strategy": "byte_stream",
        "output_schema": {
            "query": "string",
            "matches": [
                {
                    "doc_id": "string",
                    "chunk_id": "string",
                    "byte_range": ["integer", "integer"],
                    "line_range": ["integer", "integer"],
                    "preview": "string",
                    "quality_label": "source_verified|insufficient_evidence",
                }
            ],
            "quality_label": "source_verified|insufficient_evidence",
        },
        "lossy": False,
        "requires_source_refs": True,
        "source_reference_requirements": ["doc_id", "chunk_id", "byte_range", "line_range"],
        "aggregation": "union_source_verified_matches",
        "budget_limits": ["max_bytes", "max_chunks", "max_elapsed_seconds"],
        "budget_controls": ["max_bytes", "max_chunks", "max_elapsed_seconds"],
    }
}
IGNORED_STREAMING_SCAN_DIRS = {
    ".agentic_reports",
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tmp_pytest",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}


class StreamingDocumenterError(RuntimeError):
    """Raised for deterministic streaming documenter failures."""


@dataclass(frozen=True)
class StreamingChunk:
    doc_id: str
    chunk_id: str
    chunk_index: int
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    data: bytes
    read_operations: int
    max_read_block_bytes: int


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def artifact_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def sanitize_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return sanitized or "document"


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StreamingDocumenterError(f"Missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise StreamingDocumenterError(f"Invalid JSON file: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StreamingDocumenterError(f"JSON file must contain an object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def normalize_repo_path(repo_root: Path, value: str) -> str:
    raw_path = Path(value)
    if raw_path.is_absolute():
        candidate = raw_path.resolve()
    else:
        candidate = (repo_root / raw_path).resolve()
    try:
        rel_path = candidate.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise StreamingDocumenterError(f"Path is outside repo root: {value}") from exc
    return rel_path.as_posix()


def mode_definition(mode: str) -> dict[str, Any]:
    definition = MODE_REGISTRY.get(mode)
    if definition is None:
        raise StreamingDocumenterError(f"Unknown streaming mode: {mode}")
    return {"name": mode, **definition}


def document_type(doc_id: str) -> str:
    suffix = Path(doc_id).suffix.lower()
    return {
        ".adoc": "asciidoc",
        ".md": "markdown",
        ".rst": "restructuredtext",
        ".txt": "text",
    }.get(suffix, "text")


def extract_heading_preview_from_sample(doc_id: str, data: bytes, limit: int = 20) -> list[dict[str, Any]]:
    suffix = Path(doc_id).suffix.lower()
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    headings: list[dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if suffix in {".md", ".adoc"}:
            marker = "=" if suffix == ".adoc" else "#"
            if stripped.startswith(marker):
                level = len(stripped) - len(stripped.lstrip(marker))
                value = stripped[level:].strip()
                if value:
                    headings.append({"line": index, "level": level, "text": value[:160]})
        elif suffix == ".rst":
            if index < len(lines) and set(lines[index].strip()) in [{"="}, {"-"}, {"~"}, {"^"}]:
                headings.append({"line": index, "level": 1, "text": stripped[:160]})
        if len(headings) >= limit:
            break
    return headings


def build_streaming_manifest_entry(
    repo_root: Path,
    doc_id: str,
    heading_sample_bytes: int = DEFAULT_HEADING_SAMPLE_BYTES,
) -> dict[str, Any]:
    path = (repo_root / doc_id).resolve()
    try:
        path.relative_to(repo_root.resolve())
        stat = path.stat()
    except (OSError, ValueError) as exc:
        return {
            "path": doc_id,
            "readable": False,
            "error": str(exc),
        }
    sample_size = max(0, min(heading_sample_bytes, stat.st_size))
    with path.open("rb") as handle:
        sample = handle.read(sample_size)
    return {
        "path": doc_id,
        "suffix": path.suffix.lower(),
        "document_type": document_type(doc_id),
        "readable": True,
        "bytes": stat.st_size,
        "byte_range": [0, stat.st_size],
        "line_range": None,
        "heading_sample_bytes": sample_size,
        "heading_preview": extract_heading_preview_from_sample(doc_id, sample),
        "streaming": True,
        "full_content_read": False,
    }


def build_streaming_manifest(
    repo_root: Path,
    doc_id: str,
    mode: str,
    heading_sample_bytes: int = DEFAULT_HEADING_SAMPLE_BYTES,
) -> dict[str, Any]:
    entry = build_streaming_manifest_entry(repo_root, doc_id, heading_sample_bytes)
    return {
        "schema_version": STREAMING_SCHEMA_VERSION,
        "kind": "streaming_document_manifest",
        "generated_at": utc_now(),
        "target_root": str(repo_root),
        "mode": mode,
        "documents": [entry],
        "document_count": 1,
        "full_content_read": False,
    }


def iter_streaming_chunks(
    repo_root: Path,
    doc_id: str,
    chunk_bytes: int = DEFAULT_CHUNK_BYTES,
    read_block_bytes: int = DEFAULT_READ_BLOCK_BYTES,
    start_byte: int = 0,
    start_line: int = 1,
    start_chunk_index: int = 1,
    end_byte_limit: int | None = None,
) -> Iterator[StreamingChunk]:
    if chunk_bytes < 1:
        raise StreamingDocumenterError("chunk_bytes must be at least 1.")
    if read_block_bytes < 1:
        raise StreamingDocumenterError("read_block_bytes must be at least 1.")
    path = (repo_root / doc_id).resolve()
    file_size = path.stat().st_size
    if start_byte < 0 or start_byte > file_size:
        raise StreamingDocumenterError("start_byte must be inside the file byte range.")
    if end_byte_limit is not None and end_byte_limit < 0:
        raise StreamingDocumenterError("end_byte_limit cannot be negative.")
    byte_limit = file_size if end_byte_limit is None else min(file_size, max(start_byte, end_byte_limit))
    current_byte = start_byte
    current_line = max(1, start_line)
    chunk_index = max(1, start_chunk_index)

    with path.open("rb") as handle:
        handle.seek(start_byte)
        while current_byte < byte_limit:
            chunk_start_byte = current_byte
            chunk_start_line = current_line
            buffer = bytearray()
            read_operations = 0
            max_read_block = 0
            while len(buffer) < chunk_bytes and current_byte < byte_limit:
                requested = min(read_block_bytes, chunk_bytes - len(buffer), byte_limit - current_byte)
                data = handle.read(requested)
                if not data:
                    break
                read_operations += 1
                max_read_block = max(max_read_block, len(data))
                buffer.extend(data)
                current_byte += len(data)
                current_line += data.count(b"\n")

            if not buffer:
                break
            chunk_end_line = max(chunk_start_line, current_line)
            yield StreamingChunk(
                doc_id=doc_id,
                chunk_id=f"{doc_id}:{chunk_index:08d}",
                chunk_index=chunk_index,
                start_byte=chunk_start_byte,
                end_byte=current_byte,
                start_line=chunk_start_line,
                end_line=chunk_end_line,
                data=bytes(buffer),
                read_operations=read_operations,
                max_read_block_bytes=max_read_block,
            )
            chunk_index += 1


def line_preview(data: bytes, match_start: int, match_end: int) -> str:
    line_start = data.rfind(b"\n", 0, match_start) + 1
    line_end = data.find(b"\n", match_end)
    if line_end == -1:
        line_end = len(data)
    preview = data[line_start:line_end].decode("utf-8", errors="replace")
    return re.sub(r"\s+", " ", preview).strip()[:240]


def context_presence_matches(chunk: StreamingChunk, query: str) -> list[dict[str, Any]]:
    if not query:
        raise StreamingDocumenterError("context_presence query cannot be empty.")
    query_bytes = query.encode("utf-8")
    if not query_bytes:
        raise StreamingDocumenterError("context_presence query cannot be empty after encoding.")
    haystack = chunk.data.lower()
    needle = query_bytes.lower()
    matches: list[dict[str, Any]] = []
    position = 0
    while True:
        match_start = haystack.find(needle, position)
        if match_start == -1:
            break
        match_end = match_start + len(needle)
        line_number = chunk.start_line + chunk.data[:match_start].count(b"\n")
        matches.append(
            {
                "doc_id": chunk.doc_id,
                "chunk_id": chunk.chunk_id,
                "chunk_index": chunk.chunk_index,
                "byte_range": [chunk.start_byte + match_start, chunk.start_byte + match_end],
                "line_range": [line_number, line_number],
                "preview": line_preview(chunk.data, match_start, match_end),
                "quality_label": "source_verified",
            }
        )
        position = match_end
    return matches


def initial_streaming_state(
    state_path: Path,
    run_id: str,
    resume_key: dict[str, Any],
    manifest_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": STREAMING_SCHEMA_VERSION,
        "kind": "streaming_documenter_state",
        "generated_at": utc_now(),
        "updated_at": utc_now(),
        "status": "running",
        "run_id": run_id,
        "resume_key": resume_key,
        "artifacts": {
            "streaming_manifest": str(manifest_path),
            "streaming_report": str(report_path),
            "streaming_state": str(state_path),
        },
        "next_start_byte": 0,
        "next_start_line": 1,
        "next_chunk_index": 1,
        "reviewed_bytes": 0,
        "reviewed_chunks": 0,
        "failed_chunks": 0,
        "skipped_bytes": 0,
        "matches": [],
        "quality_label": "insufficient_evidence",
        "coverage": {},
    }


def validate_resume_key(state: dict[str, Any], resume_key: dict[str, Any], allow_arg_changes: bool = False) -> None:
    previous = state.get("resume_key")
    if not isinstance(previous, dict):
        raise StreamingDocumenterError("Streaming state is missing resume_key.")
    mismatches = [
        f"{key}: state={previous.get(key)!r} current={resume_key.get(key)!r}"
        for key in sorted(set(previous) | set(resume_key))
        if previous.get(key) != resume_key.get(key)
    ]
    if mismatches and not allow_arg_changes:
        raise StreamingDocumenterError("Resume arguments are incompatible with streaming state.\n" + "\n".join(mismatches))


def coverage_from_state(
    state: dict[str, Any],
    doc_id: str,
    file_size: int,
    stop_reason: str,
    max_read_block_bytes: int,
    chunk_bytes: int,
) -> dict[str, Any]:
    reviewed_bytes = int(state.get("reviewed_bytes", 0))
    reviewed_chunks = int(state.get("reviewed_chunks", 0))
    failed_chunks = int(state.get("failed_chunks", 0))
    skipped_bytes = max(0, file_size - reviewed_bytes)
    next_start_line = int(state.get("next_start_line", 1))
    reviewed_ranges = []
    if reviewed_bytes > 0:
        reviewed_ranges.append(
            {
                "doc_id": doc_id,
                "byte_range": [0, min(reviewed_bytes, file_size)],
                "line_range": [1, max(1, next_start_line)],
            }
        )
    skipped_ranges = []
    if skipped_bytes > 0:
        skipped_ranges.append(
            {
                "doc_id": doc_id,
                "byte_range": [min(reviewed_bytes, file_size), file_size],
                "reason": stop_reason,
            }
        )
    return {
        "doc_id": doc_id,
        "file_bytes": file_size,
        "reviewed_bytes": reviewed_bytes,
        "skipped_bytes": skipped_bytes,
        "summarized_bytes": 0,
        "reviewed_chunks": reviewed_chunks,
        "failed_chunks": failed_chunks,
        "reviewed_ranges": reviewed_ranges,
        "skipped_ranges": skipped_ranges,
        "summarized_ranges": [],
        "failed_ranges": [],
        "review_complete": reviewed_bytes >= file_size,
        "stop_reason": stop_reason,
        "max_read_block_bytes": max_read_block_bytes,
        "chunk_bytes": chunk_bytes,
        "full_content_read": False,
    }


def build_streaming_report(
    state: dict[str, Any],
    manifest: dict[str, Any],
    mode: str,
    query: str,
    doc_id: str,
    file_size: int,
    stop_reason: str,
    max_read_block_bytes: int,
    chunk_bytes: int,
) -> dict[str, Any]:
    matches = state.get("matches", [])
    if not isinstance(matches, list):
        matches = []
    quality_label = "source_verified" if matches else "insufficient_evidence"
    coverage = coverage_from_state(state, doc_id, file_size, stop_reason, max_read_block_bytes, chunk_bytes)
    return {
        "schema_version": STREAMING_SCHEMA_VERSION,
        "kind": "streaming_context_presence_report",
        "generated_at": utc_now(),
        "mode": mode,
        "mode_definition": mode_definition(mode),
        "doc_id": doc_id,
        "query": query,
        "quality_label": quality_label,
        "matches": matches,
        "coverage": coverage,
        "manifest": manifest,
        "artifacts": state.get("artifacts", {}),
    }


def run_context_presence_stream(
    repo_root: Path,
    doc_id: str,
    query: str,
    output_dir: Path,
    chunk_bytes: int = DEFAULT_CHUNK_BYTES,
    read_block_bytes: int = DEFAULT_READ_BLOCK_BYTES,
    max_bytes: int | None = None,
    max_chunks: int | None = None,
    max_elapsed_seconds: float | None = None,
    stop_after_chunks: int | None = None,
    resume_state_path: Path | None = None,
    resume_allow_arg_changes: bool = False,
) -> tuple[dict[str, Any], Path, Path]:
    mode = "context_presence"
    repo_root = repo_root.resolve()
    doc_id = normalize_repo_path(repo_root, doc_id)
    if not query:
        raise StreamingDocumenterError("--query is required for context_presence.")
    if chunk_bytes < 1:
        raise StreamingDocumenterError("--chunk-bytes must be at least 1.")
    if read_block_bytes < 1:
        raise StreamingDocumenterError("--read-block-bytes must be at least 1.")
    if max_bytes is not None and max_bytes < 1:
        raise StreamingDocumenterError("--max-bytes must be at least 1 when provided.")
    if max_chunks is not None and max_chunks < 1:
        raise StreamingDocumenterError("--max-chunks must be at least 1 when provided.")
    if max_elapsed_seconds is not None and max_elapsed_seconds <= 0:
        raise StreamingDocumenterError("--max-elapsed-seconds must be positive when provided.")
    if stop_after_chunks is not None and stop_after_chunks < 1:
        raise StreamingDocumenterError("--stop-after-chunks must be at least 1 when provided.")
    path = (repo_root / doc_id).resolve()
    file_size = path.stat().st_size
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = artifact_timestamp()
    resume_key = {
        "repo_root": str(repo_root),
        "doc_id": doc_id,
        "query": query,
        "mode": mode,
        "chunk_bytes": chunk_bytes,
        "read_block_bytes": read_block_bytes,
        "max_bytes": max_bytes,
        "max_chunks": max_chunks,
    }

    if resume_state_path is not None:
        state_path = resume_state_path.resolve()
        state = read_json(state_path)
        if state.get("kind") != "streaming_documenter_state":
            raise StreamingDocumenterError("Resume path is not a streaming_documenter_state artifact.")
        if state.get("status") not in {"running", "paused", "failed"}:
            raise StreamingDocumenterError(f"Streaming state is not resumable: {state.get('status')!r}")
        validate_resume_key(state, resume_key, resume_allow_arg_changes)
        raw_artifacts = state.get("artifacts", {})
        if not isinstance(raw_artifacts, dict):
            raise StreamingDocumenterError("Streaming state artifacts must be an object.")
        manifest_path = Path(raw_artifacts["streaming_manifest"])
        report_path = Path(raw_artifacts["streaming_report"])
        manifest = read_json(manifest_path)
        run_id = str(state.get("run_id") or run_id)
    else:
        manifest = build_streaming_manifest(repo_root, doc_id, mode)
        manifest_path = output_dir / f"streaming-manifest-{sanitize_filename(repo_root.name)}-{sanitize_filename(doc_id)}-{run_id}.json"
        report_path = output_dir / f"streaming-context-presence-{sanitize_filename(repo_root.name)}-{sanitize_filename(doc_id)}-{run_id}.json"
        state_path = output_dir / f"streaming-state-{sanitize_filename(repo_root.name)}-{sanitize_filename(doc_id)}-{run_id}.json"
        state = initial_streaming_state(state_path, run_id, resume_key, manifest_path, report_path)
        write_json(manifest_path, manifest)
        write_json(state_path, state)

    start_time = time.monotonic()
    stop_reason = "complete"
    previous_coverage = state.get("coverage", {})
    if isinstance(previous_coverage, dict):
        max_read_block_seen = int(previous_coverage.get("max_read_block_bytes", 0) or 0)
    else:
        max_read_block_seen = 0
    chunks_this_run = 0
    next_start_byte = int(state.get("next_start_byte", 0))
    next_start_line = int(state.get("next_start_line", 1))
    next_chunk_index = int(state.get("next_chunk_index", 1))
    end_byte_limit = min(file_size, max_bytes) if max_bytes is not None else None
    overlap_size = max(0, len(query.encode("utf-8")) - 1)
    tail_data = b""
    tail_start_byte = next_start_byte
    tail_start_line = next_start_line
    if overlap_size and next_start_byte > 0:
        tail_start_byte = max(0, next_start_byte - overlap_size)
        with path.open("rb") as handle:
            handle.seek(tail_start_byte)
            tail_data = handle.read(next_start_byte - tail_start_byte)
        tail_start_line = max(1, next_start_line - tail_data.count(b"\n"))

    if max_bytes is not None and next_start_byte >= min(file_size, max_bytes):
        stop_reason = "max_bytes"
    elif max_chunks is not None and int(state.get("reviewed_chunks", 0)) >= max_chunks:
        stop_reason = "max_chunks"

    if stop_reason == "complete":
        chunk_iter = iter_streaming_chunks(
            repo_root,
            doc_id,
            chunk_bytes=chunk_bytes,
            read_block_bytes=read_block_bytes,
            start_byte=next_start_byte,
            start_line=next_start_line,
            start_chunk_index=next_chunk_index,
            end_byte_limit=end_byte_limit,
        )
    else:
        chunk_iter = iter(())

    for chunk in chunk_iter:
        if max_bytes is not None and int(state.get("reviewed_bytes", 0)) >= max_bytes:
            stop_reason = "max_bytes"
            break
        if max_chunks is not None and int(state.get("reviewed_chunks", 0)) >= max_chunks:
            stop_reason = "max_chunks"
            break
        if max_elapsed_seconds is not None and time.monotonic() - start_time >= max_elapsed_seconds:
            stop_reason = "max_elapsed_seconds"
            break

        if tail_data:
            combined_data = tail_data + chunk.data
            combined_chunk = StreamingChunk(
                doc_id=chunk.doc_id,
                chunk_id=chunk.chunk_id,
                chunk_index=chunk.chunk_index,
                start_byte=tail_start_byte,
                end_byte=chunk.end_byte,
                start_line=tail_start_line,
                end_line=chunk.end_line,
                data=combined_data,
                read_operations=chunk.read_operations,
                max_read_block_bytes=chunk.max_read_block_bytes,
            )
            matches = [
                match
                for match in context_presence_matches(combined_chunk, query)
                if match["byte_range"][1] > chunk.start_byte
            ]
        else:
            matches = context_presence_matches(chunk, query)
        state_matches = state.setdefault("matches", [])
        if not isinstance(state_matches, list):
            raise StreamingDocumenterError("Streaming state matches must be a list.")
        state_matches.extend(matches)
        state["reviewed_bytes"] = int(state.get("reviewed_bytes", 0)) + (chunk.end_byte - chunk.start_byte)
        state["reviewed_chunks"] = int(state.get("reviewed_chunks", 0)) + 1
        state["next_start_byte"] = chunk.end_byte
        state["next_start_line"] = chunk.end_line
        state["next_chunk_index"] = chunk.chunk_index + 1
        state["quality_label"] = "source_verified" if state_matches else "insufficient_evidence"
        state["status"] = "running"
        state["updated_at"] = utc_now()
        max_read_block_seen = max(max_read_block_seen, chunk.max_read_block_bytes)
        chunks_this_run += 1
        state["coverage"] = coverage_from_state(state, doc_id, file_size, stop_reason, max_read_block_seen, chunk_bytes)
        write_json(state_path, state)

        if overlap_size:
            combined_tail_source = (tail_data + chunk.data)[-overlap_size:]
            tail_data = combined_tail_source
            tail_start_byte = chunk.end_byte - len(tail_data)
            combined_for_line = tail_data
            tail_start_line = max(1, chunk.end_line - combined_for_line.count(b"\n"))

        if stop_after_chunks is not None and chunks_this_run >= stop_after_chunks:
            stop_reason = "paused"
            state["status"] = "paused"
            state["updated_at"] = utc_now()
            write_json(state_path, state)
            break

    if int(state.get("next_start_byte", 0)) >= file_size:
        stop_reason = "complete"
        state["status"] = "completed"
    elif max_bytes is not None and int(state.get("next_start_byte", 0)) >= min(file_size, max_bytes):
        stop_reason = "max_bytes"
        if state.get("status") != "paused":
            state["status"] = "paused"
    elif max_chunks is not None and int(state.get("reviewed_chunks", 0)) >= max_chunks:
        stop_reason = "max_chunks"
        if state.get("status") != "paused":
            state["status"] = "paused"
    elif state.get("status") != "paused":
        state["status"] = "paused" if stop_reason != "complete" else "running"
    state["updated_at"] = utc_now()
    state["coverage"] = coverage_from_state(state, doc_id, file_size, stop_reason, max_read_block_seen, chunk_bytes)
    write_json(state_path, state)
    report = build_streaming_report(
        state,
        manifest,
        mode,
        query,
        doc_id,
        file_size,
        stop_reason,
        max_read_block_seen,
        chunk_bytes,
    )
    write_json(report_path, report)
    return report, report_path, state_path
