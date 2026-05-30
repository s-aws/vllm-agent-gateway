#!/usr/bin/env python3
"""Streaming document processing primitives for large documenter inputs."""

from __future__ import annotations

import http.client
import json
import os
import re
import time
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlsplit

from vllm_agent_gateway.invocation import (
    InvocationResult,
    WorkflowStatus,
    list_failures,
    string_artifact_paths,
)


STREAMING_SCHEMA_VERSION = 1
DEFAULT_CHUNK_BYTES = 64 * 1024
DEFAULT_READ_BLOCK_BYTES = 8 * 1024
DEFAULT_HEADING_SAMPLE_BYTES = 64 * 1024
DEFAULT_MAX_QUERY_MATCHES = 1000
DEFAULT_MAX_OUTLINE_ENTRIES = 2000
DEFAULT_MAX_MODEL_RECORDS = 1000
DEFAULT_MODEL_OUTPUT_TOKENS = 2000
DEFAULT_MAX_SUMMARIES = 8
DEFAULT_MAX_SUMMARY_DEPTH = 3
DEFAULT_MODEL = "Qwen3-Coder-30B-A3B-Instruct"
SUMMARY_DERIVED_QUALITY_LABEL = "summary_derived"
SUMMARY_CAVEATS = (
    "Summaries are lossy orientation, not evidence by themselves.",
    "Use source_verified records for evidence-backed claims or decisions.",
)
DEFAULT_CLASSIFICATION_LABELS = (
    "overview",
    "installation",
    "configuration",
    "runtime",
    "risk",
    "reference",
    "other",
)
VALID_CONFIDENCE_LABELS = {"low", "medium", "high"}
SOURCE_VERIFIED_CONFIDENCE = {"medium", "high"}
DETERMINISTIC_MODES = {"context_presence", "coverage", "outline", "token_count"}
MODEL_ASSISTED_MODES = {"classify", "extract_facts", "summarize"}
STREAMING_MODES = DETERMINISTIC_MODES | MODEL_ASSISTED_MODES
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
    "extract_facts": {
        "input_type": "text",
        "chunking_strategy": "byte_stream",
        "output_schema": {
            "facts": [
                {
                    "text": "string",
                    "confidence": "low|medium|high",
                    "evidence_refs": ["source reference object"],
                    "quality_label": "source_verified|insufficient_evidence",
                }
            ],
            "gaps": [
                {
                    "text": "string",
                    "confidence": "low|medium|high",
                    "evidence_refs": ["source reference object"],
                    "quality_label": "source_verified|insufficient_evidence",
                }
            ],
            "quality_label": "source_verified|insufficient_evidence",
        },
        "lossy": False,
        "requires_source_refs": True,
        "source_reference_requirements": ["doc_id", "chunk_id", "byte_range", "line_range"],
        "aggregation": "source_validated_fact_and_gap_lists",
        "budget_limits": ["max_bytes", "max_chunks", "max_elapsed_seconds", "max_model_records"],
        "budget_controls": ["max_bytes", "max_chunks", "max_elapsed_seconds", "max_model_records"],
        "model_assisted": True,
    },
    "classify": {
        "input_type": "text",
        "chunking_strategy": "byte_stream",
        "output_schema": {
            "classifications": [
                {
                    "label": "allowed classification label",
                    "confidence": "low|medium|high",
                    "evidence_refs": ["source reference object"],
                    "quality_label": "source_verified|insufficient_evidence",
                }
            ],
            "risks": [
                {
                    "label": "string",
                    "severity": "low|medium|high",
                    "confidence": "low|medium|high",
                    "evidence_refs": ["source reference object"],
                    "quality_label": "source_verified|insufficient_evidence",
                }
            ],
            "quality_label": "source_verified|insufficient_evidence",
        },
        "lossy": False,
        "requires_source_refs": True,
        "source_reference_requirements": ["doc_id", "chunk_id", "byte_range", "line_range"],
        "aggregation": "source_validated_classification_and_risk_lists",
        "budget_limits": ["max_bytes", "max_chunks", "max_elapsed_seconds", "max_model_records"],
        "budget_controls": ["max_bytes", "max_chunks", "max_elapsed_seconds", "max_model_records"],
        "model_assisted": True,
    },
    "summarize": {
        "input_type": "text",
        "chunking_strategy": "byte_stream",
        "output_schema": {
            "summary_derived": [
                {
                    "summary": "lossy prose summary string",
                    "source_refs": ["source reference object"],
                    "caveats": ["string"],
                    "quality_label": "summary_derived|insufficient_evidence",
                }
            ],
            "source_verified_records": [
                {
                    "text": "source-backed supporting record string",
                    "confidence": "low|medium|high",
                    "evidence_refs": ["source reference object"],
                    "quality_label": "source_verified|insufficient_evidence",
                }
            ],
            "quality_label": "summary_derived|insufficient_evidence",
        },
        "lossy": True,
        "requires_source_refs": True,
        "source_reference_requirements": ["doc_id", "chunk_id", "byte_range", "line_range"],
        "aggregation": "recursive_lossy_summary_with_separate_source_verified_records",
        "budget_limits": [
            "max_bytes",
            "max_chunks",
            "max_elapsed_seconds",
            "max_summaries",
            "max_summary_depth",
        ],
        "budget_controls": [
            "max_bytes",
            "max_chunks",
            "max_elapsed_seconds",
            "max_summaries",
            "max_summary_depth",
        ],
        "model_assisted": True,
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


@dataclass(frozen=True)
class StreamingDocumenterInvocationRequest:
    target_root: Path | str = "."
    doc: str = ""
    mode: str = "context_presence"
    query: str | None = None
    output_dir: Path | str = ".agentic_reports"
    chunk_bytes: int = DEFAULT_CHUNK_BYTES
    read_block_bytes: int = DEFAULT_READ_BLOCK_BYTES
    max_bytes: int | None = None
    max_chunks: int | None = None
    max_elapsed_seconds: float | None = None
    stop_after_chunks: int | None = None
    resume: Path | str | None = None
    resume_allow_arg_changes: bool = False
    max_outline_entries: int = DEFAULT_MAX_OUTLINE_ENTRIES
    max_query_matches: int = DEFAULT_MAX_QUERY_MATCHES
    role_base_url: str | None = None
    model: str = field(default_factory=lambda: os.environ.get("AGENTIC_GATEWAY_MODEL", DEFAULT_MODEL))
    timeout: int = 600
    max_output_tokens: int = DEFAULT_MODEL_OUTPUT_TOKENS
    max_model_records: int = DEFAULT_MAX_MODEL_RECORDS
    classification_label: list[str] | None = None
    max_summaries: int = DEFAULT_MAX_SUMMARIES
    max_summary_depth: int = DEFAULT_MAX_SUMMARY_DEPTH

    @classmethod
    def from_namespace(cls, args: Any) -> "StreamingDocumenterInvocationRequest":
        names = {item.name for item in fields(cls)}
        return cls(**{name: getattr(args, name) for name in names})


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


def build_model_packet(mode: str, chunk: StreamingChunk, classification_labels: list[str]) -> dict[str, Any]:
    if mode == "extract_facts":
        required_output: dict[str, Any] = {
            "chunk_id": chunk.chunk_id,
            "facts": [
                {
                    "text": "source-backed fact string",
                    "confidence": "low|medium|high",
                    "evidence_refs": [
                        {
                            "doc_id": chunk.doc_id,
                            "chunk_id": chunk.chunk_id,
                            "byte_range": [chunk.start_byte, chunk.end_byte],
                            "line_range": [chunk.start_line, chunk.end_line],
                        }
                    ],
                }
            ],
            "gaps": [
                {
                    "text": "documentation gap string",
                    "confidence": "low|medium|high",
                    "evidence_refs": [
                        {
                            "doc_id": chunk.doc_id,
                            "chunk_id": chunk.chunk_id,
                            "byte_range": [chunk.start_byte, chunk.end_byte],
                            "line_range": [chunk.start_line, chunk.end_line],
                        }
                    ],
                }
            ],
        }
        task = "extract_source_backed_facts_and_gaps"
    elif mode == "classify":
        required_output = {
            "chunk_id": chunk.chunk_id,
            "classifications": [
                {
                    "label": classification_labels[0] if classification_labels else "other",
                    "confidence": "low|medium|high",
                    "evidence_refs": [
                        {
                            "doc_id": chunk.doc_id,
                            "chunk_id": chunk.chunk_id,
                            "byte_range": [chunk.start_byte, chunk.end_byte],
                            "line_range": [chunk.start_line, chunk.end_line],
                        }
                    ],
                }
            ],
            "risks": [
                {
                    "label": "risk label string",
                    "severity": "low|medium|high",
                    "confidence": "low|medium|high",
                    "evidence_refs": [
                        {
                            "doc_id": chunk.doc_id,
                            "chunk_id": chunk.chunk_id,
                            "byte_range": [chunk.start_byte, chunk.end_byte],
                            "line_range": [chunk.start_line, chunk.end_line],
                        }
                    ],
                }
            ],
        }
        task = "classify_chunk_with_source_backed_evidence"
    elif mode == "summarize":
        required_output = {
            "chunk_id": chunk.chunk_id,
            "summary": "lossy chunk summary string",
            "source_refs": [
                {
                    "doc_id": chunk.doc_id,
                    "chunk_id": chunk.chunk_id,
                    "byte_range": [chunk.start_byte, chunk.end_byte],
                    "line_range": [chunk.start_line, chunk.end_line],
                }
            ],
            "source_verified_records": [
                {
                    "text": "optional source-backed support record string",
                    "confidence": "low|medium|high",
                    "evidence_refs": [
                        {
                            "doc_id": chunk.doc_id,
                            "chunk_id": chunk.chunk_id,
                            "byte_range": [chunk.start_byte, chunk.end_byte],
                            "line_range": [chunk.start_line, chunk.end_line],
                        }
                    ],
                }
            ],
            "caveats": ["summary is lossy and not evidence"],
        }
        task = "summarize_chunk_lossy"
    else:
        raise StreamingDocumenterError(f"Unsupported model-assisted streaming mode: {mode}")

    return {
        "schema_version": STREAMING_SCHEMA_VERSION,
        "role": "documenter",
        "mode": mode,
        "task": task,
        "doc_id": chunk.doc_id,
        "chunk_id": chunk.chunk_id,
        "chunk_index": chunk.chunk_index,
        "byte_range": [chunk.start_byte, chunk.end_byte],
        "line_range": [chunk.start_line, chunk.end_line],
        "classification_labels": classification_labels if mode == "classify" else [],
        "quality_policy": {
            "valid_evidence_required": True,
            "source_verified_confidence": sorted(SOURCE_VERIFIED_CONFIDENCE),
            "low_confidence_label": "insufficient_evidence",
            "evidence_ref_must_be_inside_chunk": True,
            "summary_quality_label": SUMMARY_DERIVED_QUALITY_LABEL,
            "summary_is_evidence": False,
        },
        "required_output": required_output,
        "chunk": chunk.data.decode("utf-8", errors="replace"),
    }


def model_packet_prompt(packet: dict[str, Any]) -> str:
    return (
        "Process exactly one streaming documenter packet. "
        "Use only the packet content. Return exactly one JSON object matching required_output. "
        "Every claim must include source references using absolute doc byte_range and line_range allowed by the packet. "
        "Do not return markdown, prose, or raw tool calls.\n\n"
        f"{json.dumps(packet, ensure_ascii=True, indent=2)}"
    )


def post_json(base_url: str, route: str, payload: dict[str, Any], timeout: int) -> tuple[int, str]:
    target = urlsplit(base_url.rstrip("/"))
    if target.scheme not in {"http", "https"} or not target.hostname:
        raise StreamingDocumenterError(f"Invalid role base URL: {base_url}")
    connection_cls = http.client.HTTPSConnection if target.scheme == "https" else http.client.HTTPConnection
    port = target.port or (443 if target.scheme == "https" else 80)
    base_path = target.path.rstrip("/")
    request_path = f"{base_path}/{route.lstrip('/')}"
    body = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {os.environ.get('AGENTIC_GATEWAY_API_KEY', 'dummy')}",
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
    }
    connection = connection_cls(target.hostname, port, timeout=timeout)
    try:
        connection.request("POST", request_path, body=body, headers=headers)
        response = connection.getresponse()
        response_body = response.read().decode("utf-8", errors="replace")
        return response.status, response_body
    except OSError as exc:
        raise StreamingDocumenterError(
            f"HTTP request to {base_url.rstrip('/')}/{route.lstrip('/')} failed: {exc}"
        ) from exc
    finally:
        connection.close()


def parse_model_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise StreamingDocumenterError(f"Model-assisted mode returned invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise StreamingDocumenterError("Model-assisted mode result must be a JSON object.")
    return value


def call_model_assisted_chunk(
    role_base_url: str,
    model: str,
    packet: dict[str, Any],
    max_output_tokens: int,
    timeout: int,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": model_packet_prompt(packet),
            }
        ],
        "temperature": 0,
        "max_tokens": max_output_tokens,
    }
    status, body = post_json(role_base_url, "/chat/completions", payload, timeout)
    if status >= 400:
        raise StreamingDocumenterError(f"Model-assisted request failed with HTTP {status}: {body[:1000]}")
    try:
        response = json.loads(body)
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise StreamingDocumenterError(f"Unexpected model-assisted response shape: {body[:1000]}") from exc
    if not isinstance(content, str):
        raise StreamingDocumenterError("Model-assisted response content was not a string.")
    return parse_model_json_content(content)


def compact_warning_value(value: Any, limit: int = 160) -> str:
    try:
        text = json.dumps(value, ensure_ascii=True, sort_keys=True)
    except TypeError:
        text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def append_validation_warning(
    state: dict[str, Any],
    mode: str,
    chunk: StreamingChunk,
    field: str,
    reason: str,
    index: int | None = None,
    value: Any = None,
) -> None:
    warnings = state_list(state, "validation_warnings")
    warning: dict[str, Any] = {
        "mode": mode,
        "doc_id": chunk.doc_id,
        "chunk_id": chunk.chunk_id,
        "chunk_index": chunk.chunk_index,
        "field": field,
        "reason": reason,
    }
    if index is not None:
        warning["index"] = index
    if value is not None:
        warning["value"] = compact_warning_value(value)
    warnings.append(warning)


def parse_int_pair(value: Any) -> list[int] | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    if not isinstance(value[0], int) or not isinstance(value[1], int):
        return None
    return [value[0], value[1]]


def validate_evidence_refs(
    state: dict[str, Any],
    mode: str,
    chunk: StreamingChunk,
    field: str,
    index: int,
    raw_refs: Any,
) -> list[dict[str, Any]]:
    if not isinstance(raw_refs, list):
        append_validation_warning(state, mode, chunk, field, "evidence_refs_not_list", index, raw_refs)
        return []
    if not raw_refs:
        append_validation_warning(state, mode, chunk, field, "evidence_refs_empty", index, raw_refs)
        return []

    valid_refs: list[dict[str, Any]] = []
    for ref_index, raw_ref in enumerate(raw_refs):
        warning_index = index if len(raw_refs) == 1 else ref_index
        if not isinstance(raw_ref, dict):
            append_validation_warning(state, mode, chunk, field, "evidence_ref_not_object", warning_index, raw_ref)
            continue
        if raw_ref.get("doc_id") != chunk.doc_id or raw_ref.get("chunk_id") != chunk.chunk_id:
            append_validation_warning(
                state,
                mode,
                chunk,
                field,
                "evidence_ref_wrong_source",
                warning_index,
                {"doc_id": raw_ref.get("doc_id"), "chunk_id": raw_ref.get("chunk_id")},
            )
            continue
        byte_range = parse_int_pair(raw_ref.get("byte_range"))
        line_range = parse_int_pair(raw_ref.get("line_range"))
        if byte_range is None or line_range is None:
            append_validation_warning(state, mode, chunk, field, "evidence_ref_invalid_range_shape", warning_index, raw_ref)
            continue
        byte_start, byte_end = byte_range
        line_start, line_end = line_range
        if byte_start < chunk.start_byte or byte_end > chunk.end_byte or byte_start >= byte_end:
            append_validation_warning(state, mode, chunk, field, "evidence_ref_byte_range_outside_chunk", warning_index, raw_ref)
            continue
        if line_start < chunk.start_line or line_end > chunk.end_line or line_start > line_end:
            append_validation_warning(state, mode, chunk, field, "evidence_ref_line_range_outside_chunk", warning_index, raw_ref)
            continue
        valid_refs.append(
            {
                "doc_id": chunk.doc_id,
                "chunk_id": chunk.chunk_id,
                "byte_range": byte_range,
                "line_range": line_range,
            }
        )
    return valid_refs


def normalize_confidence(
    state: dict[str, Any],
    mode: str,
    chunk: StreamingChunk,
    field: str,
    index: int,
    raw_value: Any,
) -> str:
    if isinstance(raw_value, str) and raw_value in VALID_CONFIDENCE_LABELS:
        return raw_value
    append_validation_warning(state, mode, chunk, field, "invalid_confidence", index, raw_value)
    return "low"


def record_quality_label(confidence: str, evidence_refs: list[dict[str, Any]], blocked: bool = False) -> str:
    if blocked:
        return "insufficient_evidence"
    if confidence in SOURCE_VERIFIED_CONFIDENCE and evidence_refs:
        return "source_verified"
    return "insufficient_evidence"


def validate_result_shape(mode: str, result: dict[str, Any], expected_chunk_id: str) -> None:
    if result.get("chunk_id") != expected_chunk_id:
        raise StreamingDocumenterError(
            f"Model-assisted result chunk_id mismatch: expected {expected_chunk_id!r}, got {result.get('chunk_id')!r}"
        )
    if mode == "summarize":
        if not isinstance(result.get("summary"), str) or not result.get("summary", "").strip():
            raise StreamingDocumenterError("Model-assisted summarize result field 'summary' must be a non-empty string.")
        if not isinstance(result.get("source_refs"), list):
            raise StreamingDocumenterError("Model-assisted summarize result field 'source_refs' must be a list.")
        if not isinstance(result.get("source_verified_records"), list):
            raise StreamingDocumenterError(
                "Model-assisted summarize result field 'source_verified_records' must be a list."
            )
        if not isinstance(result.get("caveats"), list):
            raise StreamingDocumenterError("Model-assisted summarize result field 'caveats' must be a list.")
        return
    required_lists = {
        "extract_facts": ("facts", "gaps"),
        "classify": ("classifications", "risks"),
    }.get(mode)
    if required_lists is None:
        raise StreamingDocumenterError(f"Unsupported model-assisted streaming mode: {mode}")
    for field in required_lists:
        if not isinstance(result.get(field), list):
            raise StreamingDocumenterError(f"Model-assisted result field {field!r} must be a list.")


def add_limited_records(
    records: list[dict[str, Any]],
    section: dict[str, Any],
    field: str,
    count_fields: tuple[str, ...],
    max_model_records: int,
) -> None:
    existing = sum(len(section.get(name, [])) for name in count_fields if isinstance(section.get(name), list))
    room = max(0, max_model_records - existing)
    target = section.setdefault(field, [])
    if not isinstance(target, list):
        raise StreamingDocumenterError(f"Streaming state {field} must be a list.")
    target.extend(records[:room])
    section["records_omitted"] = int(section.get("records_omitted", 0) or 0) + max(0, len(records) - room)


def normalize_fact_records(
    state: dict[str, Any],
    mode: str,
    chunk: StreamingChunk,
    field: str,
    raw_records: list[Any],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, raw_record in enumerate(raw_records):
        if not isinstance(raw_record, dict):
            append_validation_warning(state, mode, chunk, field, "record_not_object", index, raw_record)
            continue
        text = raw_record.get("text")
        if not isinstance(text, str) or not text.strip():
            append_validation_warning(state, mode, chunk, field, "missing_text", index, raw_record)
            continue
        confidence = normalize_confidence(state, mode, chunk, field, index, raw_record.get("confidence"))
        evidence_refs = validate_evidence_refs(state, mode, chunk, field, index, raw_record.get("evidence_refs"))
        normalized.append(
            {
                "doc_id": chunk.doc_id,
                "chunk_id": chunk.chunk_id,
                "chunk_index": chunk.chunk_index,
                "text": text.strip(),
                "confidence": confidence,
                "evidence_refs": evidence_refs,
                "quality_label": record_quality_label(confidence, evidence_refs),
            }
        )
    return normalized


def normalize_classification_records(
    state: dict[str, Any],
    mode: str,
    chunk: StreamingChunk,
    raw_records: list[Any],
    allowed_labels: set[str],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, raw_record in enumerate(raw_records):
        if not isinstance(raw_record, dict):
            append_validation_warning(state, mode, chunk, "classifications", "record_not_object", index, raw_record)
            continue
        label = raw_record.get("label")
        if not isinstance(label, str) or not label.strip():
            append_validation_warning(state, mode, chunk, "classifications", "missing_label", index, raw_record)
            continue
        label = label.strip()
        invalid_label = label not in allowed_labels
        if invalid_label:
            append_validation_warning(state, mode, chunk, "classifications", "label_not_allowed", index, label)
        confidence = normalize_confidence(state, mode, chunk, "classifications", index, raw_record.get("confidence"))
        evidence_refs = validate_evidence_refs(
            state,
            mode,
            chunk,
            "classifications",
            index,
            raw_record.get("evidence_refs"),
        )
        normalized.append(
            {
                "doc_id": chunk.doc_id,
                "chunk_id": chunk.chunk_id,
                "chunk_index": chunk.chunk_index,
                "label": label,
                "confidence": confidence,
                "evidence_refs": evidence_refs,
                "quality_label": record_quality_label(confidence, evidence_refs, blocked=invalid_label),
            }
        )
    return normalized


def normalize_risk_records(
    state: dict[str, Any],
    mode: str,
    chunk: StreamingChunk,
    raw_records: list[Any],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, raw_record in enumerate(raw_records):
        if not isinstance(raw_record, dict):
            append_validation_warning(state, mode, chunk, "risks", "record_not_object", index, raw_record)
            continue
        label = raw_record.get("label")
        if not isinstance(label, str) or not label.strip():
            append_validation_warning(state, mode, chunk, "risks", "missing_label", index, raw_record)
            continue
        severity = raw_record.get("severity")
        invalid_severity = not isinstance(severity, str) or severity not in VALID_CONFIDENCE_LABELS
        if invalid_severity:
            append_validation_warning(state, mode, chunk, "risks", "invalid_severity", index, severity)
            severity = "low"
        confidence = normalize_confidence(state, mode, chunk, "risks", index, raw_record.get("confidence"))
        evidence_refs = validate_evidence_refs(state, mode, chunk, "risks", index, raw_record.get("evidence_refs"))
        normalized.append(
            {
                "doc_id": chunk.doc_id,
                "chunk_id": chunk.chunk_id,
                "chunk_index": chunk.chunk_index,
                "label": label.strip(),
                "severity": severity,
                "confidence": confidence,
                "evidence_refs": evidence_refs,
                "quality_label": record_quality_label(confidence, evidence_refs, blocked=invalid_severity),
            }
        )
    return normalized


def initial_summarize_state() -> dict[str, Any]:
    return {
        "lossy": True,
        "caveats": list(SUMMARY_CAVEATS),
        "chunk_summaries": [],
        "summary_frontier": [],
        "summary_aggregate": None,
        "summary_reductions": [],
        "source_verified_records": [],
        "records_omitted": 0,
        "summary_depth": 0,
    }


def normalize_string_list(raw_values: Any) -> list[str]:
    if not isinstance(raw_values, list):
        return []
    values: list[str] = []
    for value in raw_values:
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return values


def source_ref_key(ref: dict[str, Any]) -> tuple[str, str, tuple[int, int], tuple[int, int]] | None:
    doc_id = ref.get("doc_id")
    chunk_id = ref.get("chunk_id")
    byte_range = parse_int_pair(ref.get("byte_range"))
    line_range = parse_int_pair(ref.get("line_range"))
    if not isinstance(doc_id, str) or not isinstance(chunk_id, str):
        return None
    if byte_range is None or line_range is None:
        return None
    return doc_id, chunk_id, (byte_range[0], byte_range[1]), (line_range[0], line_range[1])


def append_summary_validation_warning(
    state: dict[str, Any],
    summary_id: str,
    field: str,
    reason: str,
    index: int | None = None,
    value: Any = None,
) -> None:
    warnings = state_list(state, "validation_warnings")
    warning: dict[str, Any] = {
        "mode": "summarize",
        "summary_id": summary_id,
        "field": field,
        "reason": reason,
    }
    if index is not None:
        warning["index"] = index
    if value is not None:
        warning["value"] = compact_warning_value(value)
    warnings.append(warning)


def summary_quality_label(source_refs: list[dict[str, Any]]) -> str:
    return SUMMARY_DERIVED_QUALITY_LABEL if source_refs else "insufficient_evidence"


def merge_caveats(section: dict[str, Any], caveats: list[str]) -> None:
    current = section.setdefault("caveats", list(SUMMARY_CAVEATS))
    if not isinstance(current, list):
        section["caveats"] = list(SUMMARY_CAVEATS)
        current = section["caveats"]
    seen = {item for item in current if isinstance(item, str)}
    for caveat in caveats:
        if caveat not in seen:
            current.append(caveat)
            seen.add(caveat)


def add_summarized_range(state: dict[str, Any], chunk: StreamingChunk, quality_label: str) -> None:
    ranges = state_list(state, "summarized_ranges")
    ranges.append(
        {
            "doc_id": chunk.doc_id,
            "chunk_id": chunk.chunk_id,
            "chunk_index": chunk.chunk_index,
            "byte_range": [chunk.start_byte, chunk.end_byte],
            "line_range": [chunk.start_line, chunk.end_line],
            "quality_label": quality_label,
        }
    )


def normalize_summary_chunk_result(
    state: dict[str, Any],
    chunk: StreamingChunk,
    result: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    validate_result_shape("summarize", result, chunk.chunk_id)
    source_refs = validate_evidence_refs(state, "summarize", chunk, "source_refs", 0, result.get("source_refs"))
    caveats = normalize_string_list(result.get("caveats"))
    support_records = normalize_fact_records(
        state,
        "summarize",
        chunk,
        "source_verified_records",
        result["source_verified_records"],
    )
    summary_record = {
        "summary_id": f"{chunk.chunk_id}:summary",
        "doc_id": chunk.doc_id,
        "chunk_id": chunk.chunk_id,
        "chunk_index": chunk.chunk_index,
        "summary_depth": 0,
        "summary": result["summary"].strip(),
        "source_refs": source_refs,
        "source_summary_ids": [],
        "caveats": caveats,
        "quality_label": summary_quality_label(source_refs),
    }
    return summary_record, support_records


def add_summary_result(
    state: dict[str, Any],
    chunk: StreamingChunk,
    result: dict[str, Any],
    max_model_records: int,
) -> None:
    section = state.setdefault("summarize", initial_summarize_state())
    if not isinstance(section, dict):
        raise StreamingDocumenterError("Streaming state summarize must be an object.")
    summary_record, support_records = normalize_summary_chunk_result(state, chunk, result)
    chunk_summaries = section.setdefault("chunk_summaries", [])
    frontier = section.setdefault("summary_frontier", [])
    if not isinstance(chunk_summaries, list) or not isinstance(frontier, list):
        raise StreamingDocumenterError("Streaming state summarize summary lists must be lists.")
    chunk_summaries.append(summary_record)
    frontier.append(summary_record)
    add_limited_records(
        support_records,
        section,
        "source_verified_records",
        ("source_verified_records",),
        max_model_records,
    )
    merge_caveats(section, summary_record["caveats"])
    add_summarized_range(state, chunk, summary_record["quality_label"])


def build_summary_merge_packet(
    doc_id: str,
    merge_id: str,
    input_summaries: list[dict[str, Any]],
    summary_depth: int,
) -> dict[str, Any]:
    allowed_refs: list[dict[str, Any]] = []
    seen_refs: set[tuple[str, str, tuple[int, int], tuple[int, int]]] = set()
    for summary in input_summaries:
        refs = summary.get("source_refs", [])
        if not isinstance(refs, list):
            continue
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            key = source_ref_key(ref)
            if key is None or key in seen_refs:
                continue
            seen_refs.add(key)
            allowed_refs.append(ref)

    return {
        "schema_version": STREAMING_SCHEMA_VERSION,
        "role": "documenter",
        "mode": "summarize",
        "task": "merge_lossy_summaries",
        "doc_id": doc_id,
        "merge_id": merge_id,
        "summary_depth": summary_depth,
        "input_summary_ids": [str(summary.get("summary_id")) for summary in input_summaries],
        "quality_policy": {
            "summary_quality_label": SUMMARY_DERIVED_QUALITY_LABEL,
            "summary_is_evidence": False,
            "source_refs_must_come_from_input_summaries": True,
        },
        "allowed_source_refs": allowed_refs,
        "required_output": {
            "merge_id": merge_id,
            "summary": "lossy merged summary string",
            "source_refs": allowed_refs[:1],
            "caveats": ["merged summary is lossy and not evidence"],
        },
        "input_summaries": [
            {
                "summary_id": summary.get("summary_id"),
                "summary": summary.get("summary"),
                "source_refs": summary.get("source_refs", []),
                "caveats": summary.get("caveats", []),
                "quality_label": summary.get("quality_label"),
            }
            for summary in input_summaries
        ],
    }


def validate_summary_merge_refs(
    state: dict[str, Any],
    merge_id: str,
    raw_refs: Any,
    allowed_refs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(raw_refs, list):
        append_summary_validation_warning(state, merge_id, "source_refs", "source_refs_not_list", value=raw_refs)
        return []
    if not raw_refs:
        append_summary_validation_warning(state, merge_id, "source_refs", "source_refs_empty", value=raw_refs)
        return []
    allowed_by_key = {
        key: ref
        for ref in allowed_refs
        if isinstance(ref, dict)
        for key in [source_ref_key(ref)]
        if key is not None
    }
    valid_refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, tuple[int, int], tuple[int, int]]] = set()
    for index, raw_ref in enumerate(raw_refs):
        if not isinstance(raw_ref, dict):
            append_summary_validation_warning(state, merge_id, "source_refs", "source_ref_not_object", index, raw_ref)
            continue
        key = source_ref_key(raw_ref)
        if key is None:
            append_summary_validation_warning(state, merge_id, "source_refs", "source_ref_invalid_shape", index, raw_ref)
            continue
        if key not in allowed_by_key:
            append_summary_validation_warning(
                state,
                merge_id,
                "source_refs",
                "source_ref_not_from_input_summaries",
                index,
                raw_ref,
            )
            continue
        if key in seen:
            continue
        seen.add(key)
        valid_refs.append(allowed_by_key[key])
    return valid_refs


def normalize_summary_merge_result(
    state: dict[str, Any],
    doc_id: str,
    merge_id: str,
    summary_depth: int,
    input_summaries: list[dict[str, Any]],
    result: dict[str, Any],
) -> dict[str, Any]:
    if result.get("merge_id") != merge_id:
        raise StreamingDocumenterError(
            f"Summary merge result merge_id mismatch: expected {merge_id!r}, got {result.get('merge_id')!r}"
        )
    if not isinstance(result.get("summary"), str) or not result.get("summary", "").strip():
        raise StreamingDocumenterError("Summary merge result field 'summary' must be a non-empty string.")
    allowed_refs: list[dict[str, Any]] = []
    for summary in input_summaries:
        refs = summary.get("source_refs", [])
        if isinstance(refs, list):
            allowed_refs.extend(ref for ref in refs if isinstance(ref, dict))
    source_refs = validate_summary_merge_refs(state, merge_id, result.get("source_refs"), allowed_refs)
    caveats = normalize_string_list(result.get("caveats"))
    return {
        "summary_id": merge_id,
        "doc_id": doc_id,
        "chunk_id": None,
        "chunk_index": None,
        "summary_depth": summary_depth,
        "summary": result["summary"].strip(),
        "source_refs": source_refs,
        "source_summary_ids": [str(summary.get("summary_id")) for summary in input_summaries],
        "caveats": caveats,
        "quality_label": summary_quality_label(source_refs),
    }


def merge_summary_batch(
    state: dict[str, Any],
    doc_id: str,
    role_base_url: str,
    model: str,
    input_summaries: list[dict[str, Any]],
    summary_depth: int,
    max_output_tokens: int,
    timeout: int,
) -> dict[str, Any]:
    merge_id = f"{doc_id}:summary:depth-{summary_depth}:merge-{len(state.get('summarize', {}).get('summary_reductions', [])) + 1:08d}"
    packet = build_summary_merge_packet(doc_id, merge_id, input_summaries, summary_depth)
    result = call_model_assisted_chunk(
        role_base_url=role_base_url,
        model=model,
        packet=packet,
        max_output_tokens=max_output_tokens,
        timeout=timeout,
    )
    return normalize_summary_merge_result(state, doc_id, merge_id, summary_depth, input_summaries, result)


def reduce_summary_frontier(
    state: dict[str, Any],
    doc_id: str,
    role_base_url: str,
    model: str,
    max_output_tokens: int,
    timeout: int,
    max_summaries: int,
    max_summary_depth: int,
    final: bool = False,
) -> None:
    section = state.setdefault("summarize", initial_summarize_state())
    if not isinstance(section, dict):
        raise StreamingDocumenterError("Streaming state summarize must be an object.")
    frontier = section.setdefault("summary_frontier", [])
    reductions = section.setdefault("summary_reductions", [])
    if not isinstance(frontier, list) or not isinstance(reductions, list):
        raise StreamingDocumenterError("Streaming state summarize reduction fields must be lists.")
    depth = int(section.get("summary_depth", 0) or 0)

    while len(frontier) > max_summaries and depth < max_summary_depth:
        input_count = len(frontier)
        next_depth = depth + 1
        next_frontier: list[dict[str, Any]] = []
        for start in range(0, len(frontier), max_summaries):
            batch = frontier[start : start + max_summaries]
            if len(batch) == 1:
                next_frontier.append(batch[0])
                continue
            merged = merge_summary_batch(
                state,
                doc_id,
                role_base_url,
                model,
                batch,
                next_depth,
                max_output_tokens,
                timeout,
            )
            next_frontier.append(merged)
            merge_caveats(section, merged["caveats"])
        frontier[:] = next_frontier
        depth = next_depth
        section["summary_depth"] = depth
        reductions.append(
            {
                "summary_depth": depth,
                "input_count": input_count,
                "output_count": len(frontier),
                "quality_label": SUMMARY_DERIVED_QUALITY_LABEL if frontier else "insufficient_evidence",
            }
        )

    if not final:
        return
    if len(frontier) == 1:
        section["summary_aggregate"] = frontier[0]
        return
    if len(frontier) > 1 and depth < max_summary_depth:
        next_depth = depth + 1
        merged = merge_summary_batch(
            state,
            doc_id,
            role_base_url,
            model,
            frontier,
            next_depth,
            max_output_tokens,
            timeout,
        )
        merge_caveats(section, merged["caveats"])
        reductions.append(
            {
                "summary_depth": next_depth,
                "input_count": len(frontier),
                "output_count": 1,
                "quality_label": merged["quality_label"],
                "final_aggregate": True,
            }
        )
        frontier[:] = [merged]
        section["summary_depth"] = next_depth
        section["summary_aggregate"] = merged
        return
    if len(frontier) > 1:
        merge_caveats(section, ["Summary depth budget was exhausted before a single aggregate could be produced."])
        section["summary_aggregate"] = None


def add_model_assisted_result(
    state: dict[str, Any],
    mode: str,
    chunk: StreamingChunk,
    result: dict[str, Any],
    classification_labels: list[str],
    max_model_records: int,
) -> None:
    validate_result_shape(mode, result, chunk.chunk_id)
    if mode == "summarize":
        add_summary_result(state, chunk, result, max_model_records)
        return
    if mode == "extract_facts":
        section = state.setdefault("extract_facts", initial_extract_facts_state())
        if not isinstance(section, dict):
            raise StreamingDocumenterError("Streaming state extract_facts must be an object.")
        facts = normalize_fact_records(state, mode, chunk, "facts", result["facts"])
        gaps = normalize_fact_records(state, mode, chunk, "gaps", result["gaps"])
        add_limited_records(facts, section, "facts", ("facts", "gaps"), max_model_records)
        add_limited_records(gaps, section, "gaps", ("facts", "gaps"), max_model_records)
        return

    section = state.setdefault("classify", initial_classify_state(classification_labels))
    if not isinstance(section, dict):
        raise StreamingDocumenterError("Streaming state classify must be an object.")
    section["allowed_labels"] = classification_labels
    allowed_labels = set(classification_labels)
    classifications = normalize_classification_records(state, mode, chunk, result["classifications"], allowed_labels)
    risks = normalize_risk_records(state, mode, chunk, result["risks"])
    add_limited_records(classifications, section, "classifications", ("classifications", "risks"), max_model_records)
    add_limited_records(risks, section, "risks", ("classifications", "risks"), max_model_records)


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


def initial_extract_facts_state() -> dict[str, Any]:
    return {
        "facts": [],
        "gaps": [],
        "records_omitted": 0,
    }


def initial_classify_state(classification_labels: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    labels = list(classification_labels or DEFAULT_CLASSIFICATION_LABELS)
    return {
        "allowed_labels": labels,
        "classifications": [],
        "risks": [],
        "records_omitted": 0,
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
        "extract_facts": initial_extract_facts_state(),
        "classify": initial_classify_state(),
        "summarize": initial_summarize_state(),
        "summarized_ranges": [],
        "validation_warnings": [],
        "failed_ranges": [],
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
    raw_failed_ranges = state.get("failed_ranges", [])
    failed_ranges = raw_failed_ranges if isinstance(raw_failed_ranges, list) else []
    raw_summarized_ranges = state.get("summarized_ranges", [])
    summarized_ranges = raw_summarized_ranges if isinstance(raw_summarized_ranges, list) else []
    summarized_bytes = 0
    for item in summarized_ranges:
        if not isinstance(item, dict):
            continue
        byte_range = parse_int_pair(item.get("byte_range"))
        if byte_range is not None:
            summarized_bytes += max(0, byte_range[1] - byte_range[0])
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
        "summarized_bytes": summarized_bytes,
        "reviewed_chunks": reviewed_chunks,
        "failed_chunks": failed_chunks,
        "reviewed_ranges": reviewed_ranges,
        "reviewed_chunk_ranges": chunk_ranges,
        "skipped_ranges": skipped_ranges,
        "summarized_ranges": summarized_ranges,
        "failed_ranges": failed_ranges,
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
    if mode == "extract_facts":
        section = state.get("extract_facts", {})
        if isinstance(section, dict):
            records = []
            for field in ("facts", "gaps"):
                values = section.get(field, [])
                if isinstance(values, list):
                    records.extend(values)
            if any(isinstance(record, dict) and record.get("quality_label") == "source_verified" for record in records):
                return "source_verified"
        return "insufficient_evidence"
    if mode == "classify":
        section = state.get("classify", {})
        if isinstance(section, dict):
            records = []
            for field in ("classifications", "risks"):
                values = section.get(field, [])
                if isinstance(values, list):
                    records.extend(values)
            if any(isinstance(record, dict) and record.get("quality_label") == "source_verified" for record in records):
                return "source_verified"
        return "insufficient_evidence"
    if mode == "summarize":
        section = state.get("summarize", {})
        if isinstance(section, dict):
            aggregate = section.get("summary_aggregate")
            if isinstance(aggregate, dict) and aggregate.get("quality_label") == SUMMARY_DERIVED_QUALITY_LABEL:
                return SUMMARY_DERIVED_QUALITY_LABEL
            summaries = section.get("chunk_summaries", [])
            if isinstance(summaries, list) and any(
                isinstance(record, dict) and record.get("quality_label") == SUMMARY_DERIVED_QUALITY_LABEL
                for record in summaries
            ):
                return SUMMARY_DERIVED_QUALITY_LABEL
        return "insufficient_evidence"
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
        "validation_warnings": state.get("validation_warnings", [])
        if isinstance(state.get("validation_warnings"), list)
        else [],
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
    elif mode == "extract_facts":
        section = state.get("extract_facts", initial_extract_facts_state())
        if not isinstance(section, dict):
            section = initial_extract_facts_state()
        report["extract_facts"] = {
            "facts": section.get("facts", []) if isinstance(section.get("facts"), list) else [],
            "gaps": section.get("gaps", []) if isinstance(section.get("gaps"), list) else [],
            "records_omitted": int(section.get("records_omitted", 0) or 0),
        }
    elif mode == "classify":
        section = state.get("classify", initial_classify_state())
        if not isinstance(section, dict):
            section = initial_classify_state()
        classifications = (
            section.get("classifications", []) if isinstance(section.get("classifications"), list) else []
        )
        class_counts: dict[str, int] = {}
        for record in classifications:
            if not isinstance(record, dict) or record.get("quality_label") != "source_verified":
                continue
            label = record.get("label")
            if isinstance(label, str):
                class_counts[label] = class_counts.get(label, 0) + 1
        report["classify"] = {
            "allowed_labels": section.get("allowed_labels", [])
            if isinstance(section.get("allowed_labels"), list)
            else [],
            "classifications": classifications,
            "risks": section.get("risks", []) if isinstance(section.get("risks"), list) else [],
            "class_counts": class_counts,
            "records_omitted": int(section.get("records_omitted", 0) or 0),
        }
    elif mode == "summarize":
        section = state.get("summarize", initial_summarize_state())
        if not isinstance(section, dict):
            section = initial_summarize_state()
        report["summarize"] = {
            "lossy": True,
            "caveats": section.get("caveats", list(SUMMARY_CAVEATS))
            if isinstance(section.get("caveats"), list)
            else list(SUMMARY_CAVEATS),
            "summary_aggregate": section.get("summary_aggregate"),
            "summary_derived": section.get("chunk_summaries", [])
            if isinstance(section.get("chunk_summaries"), list)
            else [],
            "summary_frontier": section.get("summary_frontier", [])
            if isinstance(section.get("summary_frontier"), list)
            else [],
            "summary_reductions": section.get("summary_reductions", [])
            if isinstance(section.get("summary_reductions"), list)
            else [],
            "summary_depth": int(section.get("summary_depth", 0) or 0),
            "source_verified_records": section.get("source_verified_records", [])
            if isinstance(section.get("source_verified_records"), list)
            else [],
            "records_omitted": int(section.get("records_omitted", 0) or 0),
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
    role_base_url: str | None,
    model: str | None,
    max_output_tokens: int,
    max_model_records: int,
    classification_labels: list[str],
    max_summaries: int,
    max_summary_depth: int,
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
        "role_base_url": role_base_url if mode in MODEL_ASSISTED_MODES else None,
        "model": model if mode in MODEL_ASSISTED_MODES else None,
        "max_output_tokens": max_output_tokens if mode in MODEL_ASSISTED_MODES else None,
        "max_model_records": max_model_records if mode in MODEL_ASSISTED_MODES else None,
        "classification_labels": classification_labels if mode == "classify" else [],
        "max_summaries": max_summaries if mode == "summarize" else None,
        "max_summary_depth": max_summary_depth if mode == "summarize" else None,
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
    role_base_url: str | None,
    model: str | None,
    max_output_tokens: int,
    max_model_records: int,
    classification_labels: list[str],
    max_summaries: int,
    max_summary_depth: int,
) -> None:
    if mode not in STREAMING_MODES:
        raise StreamingDocumenterError(f"Unknown streaming mode: {mode}")
    if mode in MODEL_ASSISTED_MODES:
        if not role_base_url:
            raise StreamingDocumenterError(f"--role-base-url is required for {mode}.")
        if not model:
            raise StreamingDocumenterError(f"--model is required for {mode}.")
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
    if max_output_tokens < 1:
        raise StreamingDocumenterError("--max-output-tokens must be at least 1.")
    if max_model_records < 0:
        raise StreamingDocumenterError("--max-model-records cannot be negative.")
    if mode == "classify" and not classification_labels:
        raise StreamingDocumenterError("--classification-label must provide at least one label for classify.")
    if any(not isinstance(label, str) or not label.strip() for label in classification_labels):
        raise StreamingDocumenterError("--classification-label values cannot be empty.")
    if max_summaries < 2:
        raise StreamingDocumenterError("--max-summaries must be at least 2.")
    if max_summary_depth < 0:
        raise StreamingDocumenterError("--max-summary-depth cannot be negative.")


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
    role_base_url: str | None = None,
    model: str | None = None,
    timeout: int = 600,
    max_output_tokens: int = DEFAULT_MODEL_OUTPUT_TOKENS,
    max_model_records: int = DEFAULT_MAX_MODEL_RECORDS,
    classification_labels: list[str] | None = None,
    max_summaries: int = DEFAULT_MAX_SUMMARIES,
    max_summary_depth: int = DEFAULT_MAX_SUMMARY_DEPTH,
) -> tuple[dict[str, Any], Path, Path]:
    repo_root = repo_root.resolve()
    doc_id = normalize_repo_path(repo_root, doc_id)
    active_classification_labels = [label.strip() for label in (classification_labels or DEFAULT_CLASSIFICATION_LABELS)]
    if timeout < 1:
        raise StreamingDocumenterError("--timeout must be at least 1.")
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
        role_base_url,
        model,
        max_output_tokens,
        max_model_records,
        active_classification_labels,
        max_summaries,
        max_summary_depth,
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
        role_base_url,
        model,
        max_output_tokens,
        max_model_records,
        active_classification_labels,
        max_summaries,
        max_summary_depth,
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
        if mode == "classify":
            state["classify"] = initial_classify_state(active_classification_labels)
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
        if mode in MODEL_ASSISTED_MODES:
            if role_base_url is None or model is None:
                raise StreamingDocumenterError(f"--role-base-url and --model are required for {mode}.")
            packet = build_model_packet(mode, chunk, active_classification_labels)
            try:
                result = call_model_assisted_chunk(
                    role_base_url=role_base_url,
                    model=model,
                    packet=packet,
                    max_output_tokens=max_output_tokens,
                    timeout=timeout,
                )
                add_model_assisted_result(
                    state=state,
                    mode=mode,
                    chunk=chunk,
                    result=result,
                    classification_labels=active_classification_labels,
                    max_model_records=max_model_records,
                )
                if mode == "summarize":
                    reduce_summary_frontier(
                        state=state,
                        doc_id=doc_id,
                        role_base_url=role_base_url,
                        model=model,
                        max_output_tokens=max_output_tokens,
                        timeout=timeout,
                        max_summaries=max_summaries,
                        max_summary_depth=max_summary_depth,
                    )
            except StreamingDocumenterError:
                state["failed_chunks"] = int(state.get("failed_chunks", 0) or 0) + 1
                failed_ranges = state_list(state, "failed_ranges")
                failed_ranges.append(
                    {
                        "doc_id": chunk.doc_id,
                        "chunk_id": chunk.chunk_id,
                        "chunk_index": chunk.chunk_index,
                        "byte_range": [chunk.start_byte, chunk.end_byte],
                        "line_range": [chunk.start_line, chunk.end_line],
                        "quality_label": "insufficient_evidence",
                    }
                )
                state["status"] = "failed"
                state["updated_at"] = utc_now()
                state["coverage"] = coverage_from_state(
                    state,
                    doc_id,
                    file_size,
                    "failed",
                    max_read_block_seen,
                    chunk_bytes,
                )
                state["quality_label"] = mode_quality_label(state, mode, state["coverage"])
                write_json(state_path, state)
                raise
        elif mode == "context_presence":
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
    if mode == "summarize" and state.get("status") == "completed":
        if role_base_url is None or model is None:
            raise StreamingDocumenterError("--role-base-url and --model are required for summarize.")
        try:
            reduce_summary_frontier(
                state=state,
                doc_id=doc_id,
                role_base_url=role_base_url,
                model=model,
                max_output_tokens=max_output_tokens,
                timeout=timeout,
                max_summaries=max_summaries,
                max_summary_depth=max_summary_depth,
                final=True,
            )
        except StreamingDocumenterError:
            state["status"] = "failed"
            state["updated_at"] = utc_now()
            write_json(state_path, state)
            raise
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


def streaming_status_from_state(state: dict[str, Any]) -> WorkflowStatus:
    raw_status = state.get("status")
    if raw_status == "completed":
        return WorkflowStatus.COMPLETED
    if raw_status == "failed":
        return WorkflowStatus.FAILED
    return WorkflowStatus.PAUSED


def invoke_streaming_documenter(request: StreamingDocumenterInvocationRequest) -> InvocationResult:
    if not request.doc:
        raise StreamingDocumenterError("--doc is required.")
    target_root = Path(request.target_root).resolve()
    output_dir = Path(request.output_dir)
    if not output_dir.is_absolute():
        output_dir = Path.cwd() / output_dir
    report, report_path, state_path = run_streaming_mode(
        repo_root=target_root,
        doc_id=request.doc,
        mode=request.mode,
        query=request.query,
        output_dir=output_dir,
        chunk_bytes=request.chunk_bytes,
        read_block_bytes=request.read_block_bytes,
        max_bytes=request.max_bytes,
        max_chunks=request.max_chunks,
        max_elapsed_seconds=request.max_elapsed_seconds,
        stop_after_chunks=request.stop_after_chunks,
        resume_state_path=Path(request.resume).resolve() if request.resume else None,
        resume_allow_arg_changes=bool(request.resume_allow_arg_changes),
        max_outline_entries=request.max_outline_entries,
        max_query_matches=request.max_query_matches,
        role_base_url=request.role_base_url,
        model=request.model,
        timeout=request.timeout,
        max_output_tokens=request.max_output_tokens,
        max_model_records=request.max_model_records,
        classification_labels=request.classification_label or list(DEFAULT_CLASSIFICATION_LABELS),
        max_summaries=request.max_summaries,
        max_summary_depth=request.max_summary_depth,
    )
    state = read_json(state_path)
    failures = list_failures(report.get("failed_ranges"))
    failures.extend(list_failures(report.get("validation_warnings")))
    raw_resume_key = state.get("resume_key")
    raw_run_id = state.get("run_id")
    artifact_paths = string_artifact_paths(report.get("artifacts"))
    artifact_paths.setdefault("streaming_report", str(report_path))
    artifact_paths.setdefault("streaming_state", str(state_path))
    return InvocationResult(
        workflow=f"streaming_documenter.{request.mode}",
        status=streaming_status_from_state(state),
        artifact_paths=artifact_paths,
        summary_text=(
            f"quality_label={report.get('quality_label')} "
            f"reviewed_bytes={report.get('coverage', {}).get('reviewed_bytes')} "
            f"skipped_bytes={report.get('coverage', {}).get('skipped_bytes')}"
        ),
        failures=failures,
        resume_key=raw_resume_key if isinstance(raw_resume_key, dict) else None,
        report=report,
        run_id=raw_run_id if isinstance(raw_run_id, str) else None,
    )


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
