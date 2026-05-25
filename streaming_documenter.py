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
DEFAULT_MAX_QUERY_MATCHES = 1000
DEFAULT_MAX_OUTLINE_ENTRIES = 2000
DETERMINISTIC_MODES = {"context_presence", "coverage", "outline", "token_count"}
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
        "budget_limits": ["max_bytes", "max_chunks", "max_elapsed_seconds", "max_query_matches"],
        "budget_controls": ["max_bytes", "max_chunks", "max_elapsed_seconds", "max_query_matches"],
    },
    "coverage": {
        "input_type": "text",
        "chunking_strategy": "byte_stream",
        "output_schema": {
            "coverage": "coverage object with reviewed/skipped/summarized/failed ranges",
            "chunk_ranges": ["source range object"],
            "quality_label": "source_verified|insufficient_evidence",
        },
        "lossy": False,
        "requires_source_refs": True,
        "source_reference_requirements": ["doc_id", "chunk_id", "byte_range", "line_range"],
        "aggregation": "coverage_union",
        "budget_limits": ["max_bytes", "max_chunks", "max_elapsed_seconds"],
        "budget_controls": ["max_bytes", "max_chunks", "max_elapsed_seconds"],
    },
    "outline": {
        "input_type": "text",
        "chunking_strategy": "byte_stream",
        "output_schema": {
            "headings": [
                {
                    "doc_id": "string",
                    "chunk_id": "string",
                    "heading_id": "string",
                    "level": "integer",
                    "text": "string",
                    "byte_range": ["integer", "integer"],
                    "line_range": ["integer", "integer"],
                    "quality_label": "source_verified",
                }
            ],
            "sections": ["heading-derived source range object"],
            "quality_label": "source_verified|insufficient_evidence",
        },
        "lossy": False,
        "requires_source_refs": True,
        "source_reference_requirements": ["doc_id", "chunk_id", "byte_range", "line_range"],
        "aggregation": "ordered_heading_index",
        "budget_limits": ["max_bytes", "max_chunks", "max_elapsed_seconds", "max_outline_entries"],
        "budget_controls": ["max_bytes", "max_chunks", "max_elapsed_seconds", "max_outline_entries"],
    },
    "token_count": {
        "input_type": "text",
        "chunking_strategy": "byte_stream",
        "output_schema": {
            "file": "total byte/character/token estimates for reviewed ranges",
            "chunks": ["chunk token estimate object with source range"],
            "sections": ["heading-derived token estimate object with source range"],
            "query_matches": ["query match token estimate object with source range"],
            "quality_label": "source_verified|insufficient_evidence",
        },
        "lossy": False,
        "requires_source_refs": True,
        "source_reference_requirements": ["doc_id", "chunk_id", "byte_range", "line_range"],
        "aggregation": "sum_estimated_tokens",
        "budget_limits": [
            "max_bytes",
            "max_chunks",
            "max_elapsed_seconds",
            "max_outline_entries",
            "max_query_matches",
        ],
        "budget_controls": [
            "max_bytes",
            "max_chunks",
            "max_elapsed_seconds",
            "max_outline_entries",
            "max_query_matches",
        ],
    },
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


def artifact_mode_name(mode: str) -> str:
    return mode.replace("_", "-")


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


def estimate_tokens_text(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def estimate_tokens_bytes(data: bytes) -> int:
    return estimate_tokens_text(data.decode("utf-8", errors="replace"))


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
        elif suffix == ".rst" and index < len(lines):
            underline = lines[index].strip()
            if underline and len(underline) >= len(stripped) and len(set(underline)) == 1:
                if underline[0] in "=-~^":
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


def iter_chunk_lines(chunk: StreamingChunk) -> Iterator[tuple[bytes, int, int, int]]:
    byte_cursor = 0
    line_number = chunk.start_line
    for line in chunk.data.splitlines(keepends=True):
        start_byte = chunk.start_byte + byte_cursor
        end_byte = start_byte + len(line)
        yield line, start_byte, end_byte, line_number
        byte_cursor += len(line)
        line_number += line.count(b"\n")


def parse_markdown_heading(line_text: str) -> tuple[int, str] | None:
    stripped = line_text.strip()
    if not stripped.startswith("#"):
        return None
    level = len(stripped) - len(stripped.lstrip("#"))
    if level < 1 or level > 6:
        return None
    text = stripped[level:].strip()
    if not text:
        return None
    return level, text[:240]


def parse_asciidoc_heading(line_text: str) -> tuple[int, str] | None:
    stripped = line_text.strip()
    if not stripped.startswith("="):
        return None
    level = len(stripped) - len(stripped.lstrip("="))
    if level < 1 or level > 6:
        return None
    text = stripped[level:].strip()
    if not text:
        return None
    return level, text[:240]


def rst_heading_level(underline: str) -> int | None:
    stripped = underline.strip()
    if not stripped or len(set(stripped)) != 1:
        return None
    return {"=": 1, "-": 2, "~": 3, "^": 4}.get(stripped[0])


def extract_outline_entries(chunk: StreamingChunk) -> list[dict[str, Any]]:
    suffix = Path(chunk.doc_id).suffix.lower()
    raw_lines = list(iter_chunk_lines(chunk))
    headings: list[dict[str, Any]] = []
    for index, (line_bytes, start_byte, end_byte, line_number) in enumerate(raw_lines):
        line_text = line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
        parsed: tuple[int, str] | None = None
        if suffix == ".md":
            parsed = parse_markdown_heading(line_text)
        elif suffix == ".adoc":
            parsed = parse_asciidoc_heading(line_text)
        elif suffix == ".rst" and index + 1 < len(raw_lines):
            next_line = raw_lines[index + 1][0].decode("utf-8", errors="replace").rstrip("\r\n")
            level = rst_heading_level(next_line)
            if level is not None and line_text.strip() and len(next_line.strip()) >= len(line_text.strip()):
                parsed = (level, line_text.strip()[:240])

        if parsed is None:
            continue
        level, text = parsed
        headings.append(
            {
                "doc_id": chunk.doc_id,
                "chunk_id": chunk.chunk_id,
                "chunk_index": chunk.chunk_index,
                "heading_id": f"{chunk.doc_id}:heading:{start_byte}",
                "level": level,
                "text": text,
                "byte_range": [start_byte, end_byte],
                "line_range": [line_number, line_number],
                "quality_label": "source_verified",
            }
        )
    return headings


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


def initial_token_count_state() -> dict[str, Any]:
    return {
        "estimate_method": "utf8_character_count_div_4_rounded_up",
        "file": {
            "byte_count": 0,
            "character_count": 0,
            "estimated_tokens": 0,
        },
        "chunks": [],
        "query_matches": [],
        "query_matches_omitted": 0,
    }


def initial_streaming_state(
    state_path: Path,
    run_id: str,
    mode: str,
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
        "mode": mode,
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
        "chunk_ranges": [],
        "matches": [],
        "outline": {
            "headings": [],
            "headings_omitted": 0,
        },
        "token_count": initial_token_count_state(),
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


def state_list(state: dict[str, Any], key: str) -> list[Any]:
    value = state.setdefault(key, [])
    if not isinstance(value, list):
        raise StreamingDocumenterError(f"Streaming state field {key} must be a list.")
    return value


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
    raw_chunk_ranges = state.get("chunk_ranges", [])
    chunk_ranges = raw_chunk_ranges if isinstance(raw_chunk_ranges, list) else []
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
                "line_range": [max(1, next_start_line), None],
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
        "reviewed_chunk_ranges": chunk_ranges,
        "skipped_ranges": skipped_ranges,
        "summarized_ranges": [],
        "failed_ranges": [],
        "review_complete": reviewed_bytes >= file_size,
        "stop_reason": stop_reason,
        "max_read_block_bytes": max_read_block_bytes,
        "chunk_bytes": chunk_bytes,
        "full_content_read": False,
    }


def mode_quality_label(state: dict[str, Any], mode: str, coverage: dict[str, Any]) -> str:
    if mode == "context_presence":
        matches = state.get("matches", [])
        return "source_verified" if isinstance(matches, list) and matches else "insufficient_evidence"
    if mode == "outline":
        outline = state.get("outline", {})
        headings = outline.get("headings", []) if isinstance(outline, dict) else []
        if isinstance(headings, list) and headings:
            return "source_verified"
        return "source_verified" if coverage.get("review_complete") else "insufficient_evidence"
    return "source_verified" if int(coverage.get("reviewed_bytes", 0) or 0) > 0 else "insufficient_evidence"


def derive_outline_sections(headings: list[dict[str, Any]], coverage: dict[str, Any]) -> list[dict[str, Any]]:
    sorted_headings = sorted(
        [heading for heading in headings if isinstance(heading.get("byte_range"), list)],
        key=lambda heading: (heading["byte_range"][0], heading.get("level", 99)),
    )
    reviewed_ranges = coverage.get("reviewed_ranges", [])
    reviewed_end_byte = int(coverage.get("reviewed_bytes", 0) or 0)
    reviewed_end_line = None
    if reviewed_ranges and isinstance(reviewed_ranges[0], dict):
        line_range = reviewed_ranges[0].get("line_range")
        if isinstance(line_range, list) and len(line_range) == 2:
            reviewed_end_line = line_range[1]
    sections: list[dict[str, Any]] = []
    for index, heading in enumerate(sorted_headings):
        byte_range = heading["byte_range"]
        line_range = heading.get("line_range")
        if not isinstance(byte_range, list) or len(byte_range) != 2:
            continue
        if not isinstance(line_range, list) or len(line_range) != 2:
            line_range = [None, None]
        next_heading = sorted_headings[index + 1] if index + 1 < len(sorted_headings) else None
        end_byte = reviewed_end_byte
        end_line = reviewed_end_line
        if next_heading is not None:
            next_byte_range = next_heading.get("byte_range")
            next_line_range = next_heading.get("line_range")
            if isinstance(next_byte_range, list) and len(next_byte_range) == 2:
                end_byte = next_byte_range[0]
            if isinstance(next_line_range, list) and next_line_range and isinstance(next_line_range[0], int):
                end_line = max(int(line_range[0] or 1), int(next_line_range[0]) - 1)
        sections.append(
            {
                "doc_id": heading.get("doc_id"),
                "heading_id": heading.get("heading_id"),
                "title": heading.get("text"),
                "level": heading.get("level"),
                "byte_range": [byte_range[0], max(byte_range[0], end_byte)],
                "line_range": [line_range[0], end_line],
                "quality_label": "source_verified",
            }
        )
    return sections


def token_sections_from_outline(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    token_sections: list[dict[str, Any]] = []
    for section in sections:
        byte_range = section.get("byte_range")
        if not isinstance(byte_range, list) or len(byte_range) != 2:
            continue
        byte_count = max(0, int(byte_range[1]) - int(byte_range[0]))
        token_sections.append(
            {
                **section,
                "byte_count": byte_count,
                "estimated_tokens": 0 if byte_count == 0 else max(1, (byte_count + 3) // 4),
                "estimate_method": "byte_count_div_4_rounded_up",
            }
        )
    return token_sections


def add_outline_entries(state: dict[str, Any], headings: list[dict[str, Any]], max_outline_entries: int) -> None:
    outline = state.setdefault("outline", {"headings": [], "headings_omitted": 0})
    if not isinstance(outline, dict):
        raise StreamingDocumenterError("Streaming state outline must be an object.")
    stored = outline.setdefault("headings", [])
    if not isinstance(stored, list):
        raise StreamingDocumenterError("Streaming state outline.headings must be a list.")
    room = max(0, max_outline_entries - len(stored))
    stored.extend(headings[:room])
    omitted = max(0, len(headings) - room)
    outline["headings_omitted"] = int(outline.get("headings_omitted", 0) or 0) + omitted


def add_token_count_chunk(
    state: dict[str, Any],
    chunk: StreamingChunk,
    query_matches: list[dict[str, Any]],
    query: str | None,
    max_query_matches: int,
) -> None:
    token_count = state.setdefault("token_count", initial_token_count_state())
    if not isinstance(token_count, dict):
        raise StreamingDocumenterError("Streaming state token_count must be an object.")
    file_summary = token_count.setdefault("file", {"byte_count": 0, "character_count": 0, "estimated_tokens": 0})
    chunks = token_count.setdefault("chunks", [])
    stored_query_matches = token_count.setdefault("query_matches", [])
    if not isinstance(file_summary, dict) or not isinstance(chunks, list) or not isinstance(stored_query_matches, list):
        raise StreamingDocumenterError("Streaming state token_count has invalid fields.")

    text = chunk.data.decode("utf-8", errors="replace")
    estimated_tokens = estimate_tokens_text(text)
    character_count = len(text)
    byte_count = len(chunk.data)
    file_summary["byte_count"] = int(file_summary.get("byte_count", 0) or 0) + byte_count
    file_summary["character_count"] = int(file_summary.get("character_count", 0) or 0) + character_count
    file_summary["estimated_tokens"] = int(file_summary.get("estimated_tokens", 0) or 0) + estimated_tokens
    chunks.append(
        {
            "doc_id": chunk.doc_id,
            "chunk_id": chunk.chunk_id,
            "chunk_index": chunk.chunk_index,
            "byte_range": [chunk.start_byte, chunk.end_byte],
            "line_range": [chunk.start_line, chunk.end_line],
            "byte_count": byte_count,
            "character_count": character_count,
            "estimated_tokens": estimated_tokens,
            "quality_label": "source_verified",
        }
    )

    if query is None:
        return
    room = max(0, max_query_matches - len(stored_query_matches))
    query_token_estimate = estimate_tokens_text(query)
    for match in query_matches[:room]:
        stored_query_matches.append(
            {
                **match,
                "query": query,
                "estimated_tokens": query_token_estimate,
                "estimate_method": "query_utf8_character_count_div_4_rounded_up",
            }
        )
    token_count["query_matches_omitted"] = int(token_count.get("query_matches_omitted", 0) or 0) + max(
        0, len(query_matches) - room
    )


def matches_for_chunk(
    chunk: StreamingChunk,
    query: str | None,
    tail_data: bytes,
    tail_start_byte: int,
    tail_start_line: int,
) -> list[dict[str, Any]]:
    if query is None:
        return []
    if tail_data:
        combined_chunk = StreamingChunk(
            doc_id=chunk.doc_id,
            chunk_id=chunk.chunk_id,
            chunk_index=chunk.chunk_index,
            start_byte=tail_start_byte,
            end_byte=chunk.end_byte,
            start_line=tail_start_line,
            end_line=chunk.end_line,
            data=tail_data + chunk.data,
            read_operations=chunk.read_operations,
            max_read_block_bytes=chunk.max_read_block_bytes,
        )
        return [
            match
            for match in context_presence_matches(combined_chunk, query)
            if match["byte_range"][1] > chunk.start_byte
        ]
    return context_presence_matches(chunk, query)


def outline_entries_for_chunk(
    chunk: StreamingChunk,
    line_tail_data: bytes,
    line_tail_start_byte: int,
    line_tail_start_line: int,
    file_size: int,
) -> list[dict[str, Any]]:
    def is_complete_heading(heading: dict[str, Any], data: bytes) -> bool:
        byte_range = heading.get("byte_range")
        if not isinstance(byte_range, list) or len(byte_range) != 2:
            return False
        if byte_range[1] < chunk.end_byte:
            return True
        if chunk.end_byte >= file_size:
            return True
        return data.endswith(b"\n")

    if not line_tail_data:
        return [heading for heading in extract_outline_entries(chunk) if is_complete_heading(heading, chunk.data)]
    combined_chunk = StreamingChunk(
        doc_id=chunk.doc_id,
        chunk_id=chunk.chunk_id,
        chunk_index=chunk.chunk_index,
        start_byte=line_tail_start_byte,
        end_byte=chunk.end_byte,
        start_line=line_tail_start_line,
        end_line=chunk.end_line,
        data=line_tail_data + chunk.data,
        read_operations=chunk.read_operations,
        max_read_block_bytes=chunk.max_read_block_bytes,
    )
    combined_data = line_tail_data + chunk.data
    return [
        heading
        for heading in extract_outline_entries(combined_chunk)
        if isinstance(heading.get("byte_range"), list)
        and heading["byte_range"][1] > chunk.start_byte
        and is_complete_heading(heading, combined_data)
    ]


def update_line_tail(
    previous_tail: bytes,
    previous_tail_start_byte: int,
    previous_tail_start_line: int,
    chunk: StreamingChunk,
) -> tuple[bytes, int, int]:
    combined = previous_tail + chunk.data
    if not combined:
        return b"", chunk.end_byte, chunk.end_line
    combined_start_byte = previous_tail_start_byte if previous_tail else chunk.start_byte
    combined_start_line = previous_tail_start_line if previous_tail else chunk.start_line
    last_newline = combined.rfind(b"\n")
    if last_newline == -1:
        return combined, combined_start_byte, combined_start_line
    if last_newline == len(combined) - 1:
        return b"", chunk.end_byte, chunk.end_line
    tail = combined[last_newline + 1 :]
    tail_start_byte = combined_start_byte + last_newline + 1
    tail_start_line = combined_start_line + combined[: last_newline + 1].count(b"\n")
    return tail, tail_start_byte, tail_start_line


def update_tail(
    query: str | None,
    previous_tail: bytes,
    chunk: StreamingChunk,
) -> tuple[bytes, int, int]:
    if query is None:
        return b"", chunk.end_byte, chunk.end_line
    overlap_size = max(0, len(query.encode("utf-8")) - 1)
    if not overlap_size:
        return b"", chunk.end_byte, chunk.end_line
    tail_data = (previous_tail + chunk.data)[-overlap_size:]
    tail_start_byte = chunk.end_byte - len(tail_data)
    tail_start_line = max(1, chunk.end_line - tail_data.count(b"\n"))
    return tail_data, tail_start_byte, tail_start_line


def build_streaming_report(
    state: dict[str, Any],
    manifest: dict[str, Any],
    mode: str,
    query: str | None,
    doc_id: str,
    file_size: int,
    stop_reason: str,
    max_read_block_bytes: int,
    chunk_bytes: int,
) -> dict[str, Any]:
    coverage = coverage_from_state(state, doc_id, file_size, stop_reason, max_read_block_bytes, chunk_bytes)
    quality_label = mode_quality_label(state, mode, coverage)
    outline = state.get("outline", {})
    headings = outline.get("headings", []) if isinstance(outline, dict) else []
    if not isinstance(headings, list):
        headings = []
    sections = derive_outline_sections(headings, coverage)

    report: dict[str, Any] = {
        "schema_version": STREAMING_SCHEMA_VERSION,
        "kind": f"streaming_{mode}_report",
        "generated_at": utc_now(),
        "mode": mode,
        "mode_definition": mode_definition(mode),
        "doc_id": doc_id,
        "query": query,
        "quality_label": quality_label,
        "coverage": coverage,
        "manifest": manifest,
        "artifacts": state.get("artifacts", {}),
    }
    if mode == "context_presence":
        matches = state.get("matches", [])
        report["matches"] = matches if isinstance(matches, list) else []
    elif mode == "coverage":
        report["coverage_report"] = {
            "reviewed_ranges": coverage["reviewed_ranges"],
            "reviewed_chunk_ranges": coverage["reviewed_chunk_ranges"],
            "skipped_ranges": coverage["skipped_ranges"],
            "summarized_ranges": coverage["summarized_ranges"],
            "failed_ranges": coverage["failed_ranges"],
        }
    elif mode == "outline":
        report["outline"] = {
            "headings": headings,
            "sections": sections,
            "headings_omitted": int(outline.get("headings_omitted", 0) or 0) if isinstance(outline, dict) else 0,
        }
    elif mode == "token_count":
        token_count = state.get("token_count", initial_token_count_state())
        if not isinstance(token_count, dict):
            token_count = initial_token_count_state()
        file_summary = token_count.get("file", {})
        if isinstance(file_summary, dict):
            file_summary = {**file_summary, "doc_id": doc_id, "byte_range": [0, coverage["reviewed_bytes"]]}
        else:
            file_summary = {"doc_id": doc_id, "byte_range": [0, coverage["reviewed_bytes"]]}
        report["token_count"] = {
            "estimate_method": token_count.get("estimate_method", "utf8_character_count_div_4_rounded_up"),
            "file": file_summary,
            "chunks": token_count.get("chunks", []) if isinstance(token_count.get("chunks"), list) else [],
            "sections": token_sections_from_outline(sections),
            "query_matches": token_count.get("query_matches", [])
            if isinstance(token_count.get("query_matches"), list)
            else [],
            "query_matches_omitted": int(token_count.get("query_matches_omitted", 0) or 0),
            "section_source": "outline_headings",
        }
    return report


def build_resume_key(
    repo_root: Path,
    doc_id: str,
    mode: str,
    query: str | None,
    chunk_bytes: int,
    read_block_bytes: int,
    max_bytes: int | None,
    max_chunks: int | None,
    max_elapsed_seconds: float | None,
    max_outline_entries: int,
    max_query_matches: int,
) -> dict[str, Any]:
    return {
        "repo_root": str(repo_root),
        "doc_id": doc_id,
        "query": query,
        "mode": mode,
        "chunk_bytes": chunk_bytes,
        "read_block_bytes": read_block_bytes,
        "max_bytes": max_bytes,
        "max_chunks": max_chunks,
        "max_elapsed_seconds": max_elapsed_seconds,
        "max_outline_entries": max_outline_entries,
        "max_query_matches": max_query_matches,
    }


def validate_run_args(
    mode: str,
    query: str | None,
    chunk_bytes: int,
    read_block_bytes: int,
    max_bytes: int | None,
    max_chunks: int | None,
    max_elapsed_seconds: float | None,
    stop_after_chunks: int | None,
    max_outline_entries: int,
    max_query_matches: int,
) -> None:
    if mode not in DETERMINISTIC_MODES:
        raise StreamingDocumenterError(f"Unknown deterministic streaming mode: {mode}")
    if mode == "context_presence" and not query:
        raise StreamingDocumenterError("--query is required for context_presence.")
    if query == "":
        raise StreamingDocumenterError("--query cannot be empty when provided.")
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
    if max_outline_entries < 0:
        raise StreamingDocumenterError("--max-outline-entries cannot be negative.")
    if max_query_matches < 0:
        raise StreamingDocumenterError("--max-query-matches cannot be negative.")


def run_streaming_mode(
    repo_root: Path,
    doc_id: str,
    mode: str,
    output_dir: Path,
    query: str | None = None,
    chunk_bytes: int = DEFAULT_CHUNK_BYTES,
    read_block_bytes: int = DEFAULT_READ_BLOCK_BYTES,
    max_bytes: int | None = None,
    max_chunks: int | None = None,
    max_elapsed_seconds: float | None = None,
    stop_after_chunks: int | None = None,
    resume_state_path: Path | None = None,
    resume_allow_arg_changes: bool = False,
    max_outline_entries: int = DEFAULT_MAX_OUTLINE_ENTRIES,
    max_query_matches: int = DEFAULT_MAX_QUERY_MATCHES,
) -> tuple[dict[str, Any], Path, Path]:
    repo_root = repo_root.resolve()
    doc_id = normalize_repo_path(repo_root, doc_id)
    validate_run_args(
        mode,
        query,
        chunk_bytes,
        read_block_bytes,
        max_bytes,
        max_chunks,
        max_elapsed_seconds,
        stop_after_chunks,
        max_outline_entries,
        max_query_matches,
    )
    path = (repo_root / doc_id).resolve()
    file_size = path.stat().st_size
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = artifact_timestamp()
    resume_key = build_resume_key(
        repo_root,
        doc_id,
        mode,
        query,
        chunk_bytes,
        read_block_bytes,
        max_bytes,
        max_chunks,
        max_elapsed_seconds,
        max_outline_entries,
        max_query_matches,
    )

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
        mode_name = artifact_mode_name(mode)
        manifest_path = output_dir / (
            f"streaming-manifest-{sanitize_filename(repo_root.name)}-{sanitize_filename(doc_id)}-{run_id}.json"
        )
        report_path = output_dir / (
            f"streaming-{mode_name}-{sanitize_filename(repo_root.name)}-{sanitize_filename(doc_id)}-{run_id}.json"
        )
        state_path = output_dir / (
            f"streaming-state-{sanitize_filename(repo_root.name)}-{sanitize_filename(doc_id)}-{run_id}.json"
        )
        state = initial_streaming_state(state_path, run_id, mode, resume_key, manifest_path, report_path)
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
    tail_data = b""
    tail_start_byte = next_start_byte
    tail_start_line = next_start_line
    line_tail_data = b""
    line_tail_start_byte = next_start_byte
    line_tail_start_line = next_start_line
    if query is not None:
        overlap_size = max(0, len(query.encode("utf-8")) - 1)
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

        query_matches = matches_for_chunk(chunk, query, tail_data, tail_start_byte, tail_start_line)
        headings = (
            outline_entries_for_chunk(chunk, line_tail_data, line_tail_start_byte, line_tail_start_line, file_size)
            if mode in {"outline", "token_count"}
            else []
        )
        if mode == "context_presence":
            matches = state_list(state, "matches")
            room = max(0, max_query_matches - len(matches))
            matches.extend(query_matches[:room])
            state["query_matches_omitted"] = int(state.get("query_matches_omitted", 0) or 0) + max(
                0, len(query_matches) - room
            )
        elif mode == "outline":
            add_outline_entries(state, headings, max_outline_entries)
        elif mode == "token_count":
            add_outline_entries(state, headings, max_outline_entries)
            add_token_count_chunk(state, chunk, query_matches, query, max_query_matches)

        state["reviewed_bytes"] = int(state.get("reviewed_bytes", 0)) + (chunk.end_byte - chunk.start_byte)
        state["reviewed_chunks"] = int(state.get("reviewed_chunks", 0)) + 1
        state["next_start_byte"] = chunk.end_byte
        state["next_start_line"] = chunk.end_line
        state["next_chunk_index"] = chunk.chunk_index + 1
        chunk_ranges = state_list(state, "chunk_ranges")
        chunk_ranges.append(
            {
                "doc_id": chunk.doc_id,
                "chunk_id": chunk.chunk_id,
                "chunk_index": chunk.chunk_index,
                "byte_range": [chunk.start_byte, chunk.end_byte],
                "line_range": [chunk.start_line, chunk.end_line],
                "quality_label": "source_verified",
            }
        )
        state["status"] = "running"
        state["updated_at"] = utc_now()
        max_read_block_seen = max(max_read_block_seen, chunk.max_read_block_bytes)
        chunks_this_run += 1
        state["coverage"] = coverage_from_state(state, doc_id, file_size, stop_reason, max_read_block_seen, chunk_bytes)
        state["quality_label"] = mode_quality_label(state, mode, state["coverage"])
        write_json(state_path, state)

        tail_data, tail_start_byte, tail_start_line = update_tail(query, tail_data, chunk)
        if mode in {"outline", "token_count"}:
            line_tail_data, line_tail_start_byte, line_tail_start_line = update_line_tail(
                line_tail_data,
                line_tail_start_byte,
                line_tail_start_line,
                chunk,
            )

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
    state["quality_label"] = mode_quality_label(state, mode, state["coverage"])
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
    max_query_matches: int = DEFAULT_MAX_QUERY_MATCHES,
) -> tuple[dict[str, Any], Path, Path]:
    return run_streaming_mode(
        repo_root=repo_root,
        doc_id=doc_id,
        mode="context_presence",
        query=query,
        output_dir=output_dir,
        chunk_bytes=chunk_bytes,
        read_block_bytes=read_block_bytes,
        max_bytes=max_bytes,
        max_chunks=max_chunks,
        max_elapsed_seconds=max_elapsed_seconds,
        stop_after_chunks=stop_after_chunks,
        resume_state_path=resume_state_path,
        resume_allow_arg_changes=resume_allow_arg_changes,
        max_query_matches=max_query_matches,
    )
