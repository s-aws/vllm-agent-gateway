#!/usr/bin/env python3
"""Thin documenter orchestrator demo.

This is intentionally a controller, not another prompt. It owns file discovery,
chunking, task packet construction, sequencing, and artifact writing. The
documenter role receives one bounded packet at a time and returns a JSON delta.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


DEFAULT_MODEL = "Qwen/Qwen3-Coder-30B-A3B-Instruct"
DEFAULT_ROLE_ID = "documenter/default"
DEFAULT_OUTPUT_DIR = ".agentic_reports"
DEFAULT_VISIBLE_CANDIDATE_LIMIT = 12
DEFAULT_VISIBLE_CANDIDATE_TOKEN_LIMIT = 1200
DEFAULT_MAX_IN_MEMORY_DOC_BYTES = 64 * 1024 * 1024
SCRIPT_CONFIG_ROOT = Path(__file__).resolve().parents[2]
MODES = {"review", "summarize", "full"}
CHANGE_PLAN_CATEGORY_TITLES = {
    "safe_documentation_edit": "Safe Documentation Edits",
    "needs_user_decision": "Needs User Decision",
    "insufficient_evidence": "Insufficient Evidence",
}
DOC_SUFFIXES = {".adoc", ".md", ".rst", ".txt"}
DOCUMENT_SCOPES = {"tracked", "all"}
IGNORED_SCAN_DIRS = {
    ".agentic_reports",
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}
FOLLOWUP_SUFFIXES = {
    ".adoc",
    ".cfg",
    ".ini",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".rst",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
PATH_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_./-])(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+"
    r"\.(?:adoc|cfg|ini|json|md|ps1|py|rst|sh|toml|txt|yaml|yml)(?![A-Za-z0-9_./-])",
    re.IGNORECASE,
)
CANDIDATE_REASON_PRIORITY = {
    "linked_from_chunk": 0,
    "seed_doc": 10,
    "runtime_config": 20,
    "role_prompt": 30,
    "startup_script": 40,
    "same_directory": 50,
    "documentation_index": 60,
    "documentation": 70,
    "in_scope_file": 90,
}
DEFAULT_CRITERIA = [
    "installation steps documented",
    "configuration documented",
    "runtime ports documented",
    "tested environment documented",
]
REQUIRED_RESULT_FIELDS = {
    "chunk_id": str,
    "facts_found": list,
    "criteria_satisfied": list,
    "criteria_remaining": list,
    "doc_gaps": list,
    "followup_files": list,
    "confidence": str,
}
RUN_STATE_SCHEMA_VERSION = 1
RESUMABLE_RUN_STATUSES = {"running", "failed", "paused", "review_complete"}


class OrchestratorError(RuntimeError):
    """Raised for deterministic controller failures."""


class OrchestratorPaused(RuntimeError):
    """Raised after writing a resumable pause state."""


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    start_line: int
    end_line: int
    text: str
    token_estimate: int
    overlap_previous_lines: int


@dataclass(frozen=True)
class ReviewTarget:
    doc_id: str
    source: str
    depth: int
    parent_doc_id: str | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def artifact_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OrchestratorError(f"Missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise OrchestratorError(f"Invalid JSON file: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise OrchestratorError(f"JSON file must contain an object: {path}")
    return value


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
        raise OrchestratorError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def load_role(manifest: dict[str, Any], role_id: str) -> dict[str, Any]:
    roles = manifest.get("roles")
    if not isinstance(roles, list):
        raise OrchestratorError("runtime/roles.json must contain a roles list.")
    for role in roles:
        if isinstance(role, dict) and role.get("id") == role_id:
            return role
    raise OrchestratorError(f"Role not found in runtime/roles.json: {role_id}")


def load_tool_ids(tool_catalog: dict[str, Any]) -> set[str]:
    raw_tools = tool_catalog.get("tools")
    if not isinstance(raw_tools, list):
        raise OrchestratorError("runtime/tools.json must contain a tools list.")
    tool_ids: set[str] = set()
    for tool in raw_tools:
        if not isinstance(tool, dict) or not isinstance(tool.get("id"), str):
            raise OrchestratorError("Every tool catalog entry must contain a string id.")
        tool_ids.add(tool["id"])
    return tool_ids


def role_tool_ids(role: dict[str, Any], known_tool_ids: set[str]) -> set[str]:
    raw_tool_ids = role.get("tool_ids", [])
    if not isinstance(raw_tool_ids, list) or not all(isinstance(item, str) for item in raw_tool_ids):
        raise OrchestratorError(f"Role {role.get('id')} has invalid tool_ids.")
    assigned = set(raw_tool_ids)
    unknown = sorted(assigned - known_tool_ids)
    if unknown:
        raise OrchestratorError(f"Role {role.get('id')} references unknown tools: {', '.join(unknown)}")
    return assigned


def require_tool(assigned_tool_ids: set[str], tool_id: str) -> None:
    if tool_id not in assigned_tool_ids:
        raise OrchestratorError(f"Role tool policy does not allow required controller tool: {tool_id}")


def tracked_files(repo_root: Path, assigned_tool_ids: set[str]) -> list[str]:
    require_tool(assigned_tool_ids, "git_ls_files")
    return [line for line in run_git(repo_root, ["ls-files"]).splitlines() if line]


def tracked_docs(repo_root: Path, assigned_tool_ids: set[str]) -> list[str]:
    return [path for path in tracked_files(repo_root, assigned_tool_ids) if Path(path).suffix.lower() in DOC_SUFFIXES]


def scan_repo_files(repo_root: Path, assigned_tool_ids: set[str]) -> list[str]:
    require_tool(assigned_tool_ids, "scan_files")
    root = repo_root.resolve()
    files: list[str] = []
    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in IGNORED_SCAN_DIRS and not name.endswith(".egg-info") and not name.endswith(".dist-info")
        ]
        current_path = Path(current_root)
        for filename in filenames:
            path = current_path / filename
            if path.is_symlink():
                continue
            try:
                rel_path = path.resolve().relative_to(root)
            except (OSError, ValueError):
                continue
            files.append(rel_path.as_posix())
    return sorted(files)


def discover_files_for_scope(
    repo_root: Path,
    assigned_tool_ids: set[str],
    document_scope: str,
) -> tuple[list[str], list[str], list[dict[str, str]]]:
    if document_scope not in DOCUMENT_SCOPES:
        raise OrchestratorError(f"--document-scope must be one of: {', '.join(sorted(DOCUMENT_SCOPES))}")

    warnings: list[dict[str, str]] = []
    tracked: list[str] = []
    try:
        tracked = tracked_files(repo_root, assigned_tool_ids)
    except OrchestratorError as exc:
        if document_scope == "tracked":
            raise
        warnings.append({"source": "git_ls_files", "reason": "unavailable", "detail": str(exc)})

    if document_scope == "tracked":
        return tracked, tracked, warnings
    return scan_repo_files(repo_root, assigned_tool_ids), tracked, warnings


def doc_paths_from_files(files: list[str]) -> list[str]:
    return [path for path in files if Path(path).suffix.lower() in DOC_SUFFIXES]


def normalize_repo_path(repo_root: Path, value: str) -> str:
    raw_path = Path(value)
    candidate = raw_path.resolve() if raw_path.is_absolute() else (repo_root / raw_path).resolve()
    try:
        rel_path = candidate.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise OrchestratorError(f"Path is outside repo root: {value}") from exc
    return rel_path.as_posix()


def select_document(
    repo_root: Path,
    docs: list[str],
    requested_doc: str | None,
    allow_untracked_doc: bool,
) -> tuple[str, list[str]]:
    if not docs and requested_doc is None:
        raise OrchestratorError("No documentation files found.")
    if requested_doc is None:
        if "README.md" in docs:
            return "README.md", docs
        return docs[0], docs

    doc_id = normalize_repo_path(repo_root, requested_doc)
    if doc_id not in docs:
        candidate = repo_root / doc_id
        if (
            allow_untracked_doc
            and candidate.exists()
            and candidate.is_file()
            and candidate.suffix.lower() in DOC_SUFFIXES
        ):
            return doc_id, docs
        raise OrchestratorError(f"Selected document is not in the discovered documentation manifest: {doc_id}")
    return doc_id, docs


def read_repo_file(
    repo_root: Path,
    assigned_tool_ids: set[str],
    doc_id: str,
    max_in_memory_doc_bytes: int,
    allow_large_in_memory_docs: bool,
) -> str:
    require_tool(assigned_tool_ids, "read_file")
    path = (repo_root / doc_id).resolve()
    try:
        path.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise OrchestratorError(f"Refusing to read outside repo root: {doc_id}") from exc
    size = path.stat().st_size
    if not allow_large_in_memory_docs and size > max_in_memory_doc_bytes:
        raise OrchestratorError(
            f"{doc_id} is {size} bytes, which exceeds --max-in-memory-doc-bytes "
            f"({max_in_memory_doc_bytes}). Use the streaming documenter for large files, "
            "or pass --allow-large-in-memory-docs intentionally."
        )
    return path.read_text(encoding="utf-8", errors="replace")


def chunk_document(doc_id: str, text: str, max_tokens: int, overlap_lines: int) -> list[Chunk]:
    if max_tokens < 128:
        raise OrchestratorError("--chunk-token-limit must be at least 128.")
    if overlap_lines < 0:
        raise OrchestratorError("--chunk-overlap-lines cannot be negative.")
    lines = text.splitlines(keepends=True)
    if not lines:
        return [Chunk(f"{doc_id}:0001", 1, 1, "", 1, 0)]

    chunks: list[Chunk] = []
    start_index = 0
    previous_end_line = 0

    while start_index < len(lines):
        current: list[str] = []
        end_index = start_index
        while end_index < len(lines):
            proposed = "".join([*current, lines[end_index]])
            if current and estimate_tokens(proposed) > max_tokens:
                break
            current.append(lines[end_index])
            end_index += 1

        if not current:
            current.append(lines[start_index])
            end_index = start_index + 1

        start_line = start_index + 1
        end_line = end_index
        overlap_previous = max(0, previous_end_line - start_line + 1)
        chunk_text = "".join(current)
        chunks.append(
            Chunk(
                chunk_id=f"{doc_id}:{len(chunks) + 1:04d}",
                start_line=start_line,
                end_line=end_line,
                text=chunk_text,
                token_estimate=estimate_tokens(chunk_text),
                overlap_previous_lines=overlap_previous,
            )
        )

        if end_index >= len(lines):
            break
        previous_end_line = end_line
        next_start = max(end_index - overlap_lines, start_index + 1)
        start_index = next_start
    return chunks


def build_packet(
    target: ReviewTarget,
    chunk: Chunk,
    criteria_remaining: list[str],
    visible_followup_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "role": "documenter",
        "task": "review_chunk_for_documentation",
        "doc_id": target.doc_id,
        "source": target.source,
        "followup_depth": target.depth,
        "parent_doc_id": target.parent_doc_id,
        "chunk_id": chunk.chunk_id,
        "lines": [chunk.start_line, chunk.end_line],
        "overlap_previous_lines": chunk.overlap_previous_lines,
        "criteria_remaining": criteria_remaining,
        "visible_followup_candidates": visible_followup_candidates,
        "followup_file_policy": "Prefer exact paths from visible_followup_candidates. Use an empty array when no visible candidate is relevant.",
        "required_output": {
            "chunk_id": "string",
            "facts_found": ["string"],
            "criteria_satisfied": ["string"],
            "criteria_remaining": ["string"],
            "doc_gaps": ["string"],
            "followup_files": ["string"],
            "confidence": "low|medium|high",
        },
        "chunk": chunk.text,
    }


def packet_prompt(packet: dict[str, Any]) -> str:
    return (
        "Review exactly one documentation task packet. "
        "Use only the packet content. Return exactly one JSON object matching required_output. "
        "No markdown, no prose, no raw tool calls.\n\n"
        f"{json.dumps(packet, ensure_ascii=True, indent=2)}"
    )


def summary_prompt(packet: dict[str, Any]) -> str:
    return (
        "Prepare a final documentation review summary from the controller aggregate. "
        "Use only the aggregate content. Return Markdown only. "
        "Use these headings exactly: Summary, Satisfied Criteria, Remaining Gaps, "
        "Recommended Follow-Up Files, Validation Notes, Confidence and Caveats.\n\n"
        f"{json.dumps(packet, ensure_ascii=True, indent=2)}"
    )


def post_json(base_url: str, route: str, payload: dict[str, Any], timeout: int) -> tuple[int, str]:
    target = urlsplit(base_url.rstrip("/"))
    if target.scheme not in {"http", "https"} or not target.hostname:
        raise OrchestratorError(f"Invalid role base URL: {base_url}")
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
    conn = connection_cls(target.hostname, port, timeout=timeout)
    try:
        conn.request("POST", request_path, body=body, headers=headers)
        response = conn.getresponse()
        response_body = response.read().decode("utf-8", errors="replace")
        return response.status, response_body
    except OSError as exc:
        raise OrchestratorError(f"HTTP request to {base_url.rstrip('/')}/{route.lstrip('/')} failed: {exc}") from exc
    finally:
        conn.close()


def call_documenter(role_base_url: str, model: str, packet: dict[str, Any], max_tokens: int, timeout: int) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": packet_prompt(packet),
            }
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    status, body = post_json(role_base_url, "/chat/completions", payload, timeout)
    if status >= 400:
        raise OrchestratorError(f"Documenter request failed with HTTP {status}: {body[:1000]}")
    try:
        response = json.loads(body)
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise OrchestratorError(f"Unexpected documenter response shape: {body[:1000]}") from exc
    if not isinstance(content, str):
        raise OrchestratorError("Documenter response content was not a string.")
    return parse_result(content, expected_chunk_id=str(packet["chunk_id"]))


def call_documenter_summary(
    role_base_url: str,
    model: str,
    packet: dict[str, Any],
    max_tokens: int,
    timeout: int,
) -> str:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": summary_prompt(packet),
            }
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    status, body = post_json(role_base_url, "/chat/completions", payload, timeout)
    if status >= 400:
        raise OrchestratorError(f"Documenter summary request failed with HTTP {status}: {body[:1000]}")
    try:
        response = json.loads(body)
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise OrchestratorError(f"Unexpected documenter summary response shape: {body[:1000]}") from exc
    if not isinstance(content, str) or not content.strip():
        raise OrchestratorError("Documenter summary response content was empty or not a string.")
    return content.strip() + "\n"


def parse_result(content: str, expected_chunk_id: str) -> dict[str, Any]:
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
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OrchestratorError(f"Documenter did not return valid JSON: {content[:1000]}") from exc
    if not isinstance(result, dict):
        raise OrchestratorError("Documenter result must be a JSON object.")
    for field, expected_type in REQUIRED_RESULT_FIELDS.items():
        if not isinstance(result.get(field), expected_type):
            raise OrchestratorError(f"Documenter result field {field!r} must be {expected_type.__name__}.")
    if result["chunk_id"] != expected_chunk_id:
        raise OrchestratorError(
            f"Documenter result chunk_id mismatch: expected {expected_chunk_id}, got {result['chunk_id']}"
        )
    if result["confidence"] not in {"low", "medium", "high"}:
        raise OrchestratorError("Documenter confidence must be one of: low, medium, high.")
    return result


def normalize_result_policy(
    result: dict[str, Any],
    known_files: set[str],
    allowed_criteria: list[str],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []

    for field in ("facts_found", "criteria_satisfied", "criteria_remaining", "doc_gaps", "followup_files"):
        original = result[field]
        filtered = [item for item in original if isinstance(item, str)]
        if len(filtered) != len(original):
            warnings.append(
                {
                    "field": field,
                    "reason": "removed_non_string_items",
                    "removed_count": len(original) - len(filtered),
                }
            )
        result[field] = filtered

    allowed = set(allowed_criteria)
    invalid_satisfied = [item for item in result["criteria_satisfied"] if item not in allowed]
    if invalid_satisfied:
        warnings.append(
            {
                "field": "criteria_satisfied",
                "reason": "removed_unknown_criteria",
                "values": invalid_satisfied,
            }
        )
        result["criteria_satisfied"] = [item for item in result["criteria_satisfied"] if item in allowed]

    invalid_remaining = [item for item in result["criteria_remaining"] if item not in allowed]
    if invalid_remaining:
        warnings.append(
            {
                "field": "criteria_remaining",
                "reason": "removed_unknown_criteria",
                "values": invalid_remaining,
            }
        )
        result["criteria_remaining"] = [item for item in result["criteria_remaining"] if item in allowed]

    if result["doc_gaps"] and result["criteria_satisfied"]:
        warnings.append(
            {
                "field": "criteria_satisfied",
                "reason": "blocked_satisfaction_because_doc_gaps_were_reported",
                "values": result["criteria_satisfied"],
            }
        )
        result["criteria_satisfied"] = []

    invalid_followups = [item for item in result["followup_files"] if item not in known_files]
    if invalid_followups:
        warnings.append(
            {
                "field": "followup_files",
                "reason": "reported_untracked_or_unprovided_paths",
                "values": invalid_followups,
            }
        )

    return warnings


def unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def inline_markdown(value: Any) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text or "(blank)"


def chunk_source_ref(chunk: dict[str, Any]) -> str:
    chunk_id = inline_markdown(chunk.get("chunk_id", "unknown-chunk"))
    lines = chunk.get("lines")
    if (
        isinstance(lines, list)
        and len(lines) == 2
        and isinstance(lines[0], int)
        and isinstance(lines[1], int)
    ):
        return f"{chunk_id} lines {lines[0]}-{lines[1]}"
    return chunk_id


def source_from_followup_record(record: dict[str, Any]) -> str:
    source_chunk_id = record.get("source_chunk_id")
    if isinstance(source_chunk_id, str) and source_chunk_id:
        return inline_markdown(source_chunk_id)
    source_doc_id = record.get("source_doc_id")
    if isinstance(source_doc_id, str) and source_doc_id:
        return inline_markdown(source_doc_id)
    return "followup_policy"


def append_change_plan_item(
    items: list[dict[str, Any]],
    category: str,
    doc_id: str,
    source: str,
    confidence: str,
    basis: str,
    text: str,
    chunk: dict[str, Any] | None = None,
) -> None:
    item: dict[str, Any] = {
        "id": f"CP-{len(items) + 1:04d}",
        "category": category,
        "category_title": CHANGE_PLAN_CATEGORY_TITLES.get(category, category),
        "target_file": inline_markdown(doc_id),
        "source": inline_markdown(source),
        "confidence": inline_markdown(confidence),
        "basis": inline_markdown(basis),
        "text": inline_markdown(text),
    }
    if isinstance(chunk, dict):
        if isinstance(chunk.get("doc_id"), str):
            item["source_doc_id"] = chunk["doc_id"]
        if isinstance(chunk.get("chunk_id"), str):
            item["source_chunk_id"] = chunk["chunk_id"]
        lines = chunk.get("lines")
        if (
            isinstance(lines, list)
            and len(lines) == 2
            and isinstance(lines[0], int)
            and isinstance(lines[1], int)
        ):
            item["lines"] = [lines[0], lines[1]]
    items.append(item)


def collect_change_plan_items(report: dict[str, Any]) -> list[dict[str, Any]]:
    seed_doc_id = inline_markdown(report.get("seed_doc_id") or report.get("doc_id") or "unknown")
    items: list[dict[str, Any]] = []
    reviewed_result_count = 0

    for chunk in report.get("chunks", []):
        if not isinstance(chunk, dict):
            continue
        doc_id = inline_markdown(chunk.get("doc_id") or seed_doc_id)
        source = chunk_source_ref(chunk)
        result = chunk.get("result")
        if isinstance(result, dict):
            reviewed_result_count += 1
            confidence = inline_markdown(result.get("confidence", "unknown"))
            facts_found = [item for item in result.get("facts_found", []) if isinstance(item, str)]
            doc_gaps = [item for item in result.get("doc_gaps", []) if isinstance(item, str)]

            category = "safe_documentation_edit" if confidence in {"medium", "high"} else "insufficient_evidence"
            for fact in facts_found:
                if category == "safe_documentation_edit":
                    text = f"Preserve or clarify review-backed fact: {fact}"
                else:
                    text = f"Verify low-confidence fact before proposing an edit: {fact}"
                append_change_plan_item(items, category, doc_id, source, confidence, "facts_found", text, chunk)

            for gap in doc_gaps:
                append_change_plan_item(
                    items,
                    "needs_user_decision",
                    doc_id,
                    source,
                    confidence,
                    "doc_gaps",
                    f"Decide how to address reported documentation gap: {gap}",
                    chunk,
                )

            if confidence == "low" and not facts_found:
                append_change_plan_item(
                    items,
                    "insufficient_evidence",
                    doc_id,
                    source,
                    confidence,
                    "confidence",
                    "Low-confidence review result; do not make edits from this chunk without verification.",
                    chunk,
                )

        for warning in chunk.get("validation_warnings", []):
            if not isinstance(warning, dict):
                continue
            field = inline_markdown(warning.get("field", "unknown_field"))
            reason = inline_markdown(warning.get("reason", "unknown_reason"))
            values = warning.get("values")
            value_detail = ""
            if isinstance(values, list) and values:
                value_detail = f"; values: {', '.join(inline_markdown(item) for item in values)}"
            append_change_plan_item(
                items,
                "insufficient_evidence",
                doc_id,
                source,
                "validation-warning",
                "validation_warnings",
                f"Validation warning from report field {field}: {reason}{value_detail}",
                chunk,
            )

    if reviewed_result_count == 0:
        reason = "dry-run produced packets only" if report.get("dry_run") else "no chunk review results were recorded"
        append_change_plan_item(
            items,
            "insufficient_evidence",
            seed_doc_id,
            "run-level",
            "none",
            "chunk_results",
            f"No model-backed review results are available; {reason}.",
        )
    return items


def group_change_plan_items(items: list[dict[str, Any]], category: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        if item.get("category") != category:
            continue
        target_file = inline_markdown(item.get("target_file", "unknown"))
        grouped.setdefault(target_file, []).append(item)
    return grouped


def append_grouped_change_section(
    lines: list[str],
    title: str,
    intro: str,
    grouped: dict[str, list[dict[str, Any]]],
) -> None:
    lines.append(f"## {title}")
    lines.append("")
    lines.append(intro)
    lines.append("")
    if not any(grouped.values()):
        lines.append("- None recorded.")
        lines.append("")
        return
    for doc_id in sorted(grouped):
        items = grouped[doc_id]
        if not items:
            continue
        lines.append(f"### {inline_markdown(doc_id)}")
        lines.append("")
        for item in items:
            lines.append(
                f"- {inline_markdown(item.get('id', 'CP-????'))} "
                f"[{inline_markdown(item.get('source', 'unknown'))}; "
                f"confidence: {inline_markdown(item.get('confidence', 'unknown'))}; "
                f"basis: {inline_markdown(item.get('basis', 'unknown'))}] "
                f"{inline_markdown(item.get('text', ''))}"
            )
        lines.append("")


def build_doc_change_plan(report: dict[str, Any]) -> str:
    aggregate = report.get("aggregate")
    if not isinstance(aggregate, dict):
        aggregate = aggregate_report(report)

    seed_doc_id = inline_markdown(report.get("seed_doc_id") or report.get("doc_id") or "unknown")
    change_plan_items = collect_change_plan_items(report)
    safe_edits = group_change_plan_items(change_plan_items, "safe_documentation_edit")
    needs_decision = group_change_plan_items(change_plan_items, "needs_user_decision")
    insufficient_evidence = group_change_plan_items(change_plan_items, "insufficient_evidence")

    artifacts = report.get("artifacts", {})
    if not isinstance(artifacts, dict):
        artifacts = {}
    followup_policy = report.get("followup_policy", {})
    if not isinstance(followup_policy, dict):
        followup_policy = {}
    accepted_followups = [
        item for item in followup_policy.get("accepted_followups", []) if isinstance(item, dict)
    ]
    skipped_followups = [
        item for item in followup_policy.get("skipped_followups", []) if isinstance(item, dict)
    ]
    reported_followup_files = [
        item for item in aggregate.get("reported_followup_files", []) if isinstance(item, str)
    ]
    validation_warnings = [
        item for item in aggregate.get("validation_warnings", []) if isinstance(item, dict)
    ]

    lines: list[str] = [
        "# Documentation Change Plan",
        "",
        "Generated by the controller from validated documenter report data. This artifact is non-mutating; target repository files are not modified.",
        "",
        "## Run Context",
        "",
        f"- Generated at: {inline_markdown(report.get('generated_at', 'unknown'))}",
        f"- Target root: {inline_markdown(report.get('target_root', 'unknown'))}",
        f"- Seed document: {seed_doc_id}",
        f"- Mode: {inline_markdown(report.get('mode', 'unknown'))}",
        f"- Dry run: {str(bool(report.get('dry_run'))).lower()}",
        f"- Document scope: {inline_markdown(report.get('document_scope', 'unknown'))}",
        f"- Chunks processed: {inline_markdown(report.get('chunks_processed', 'unknown'))} of {inline_markdown(report.get('chunks_total', 'unknown'))}",
        f"- Truncated after chunks: {str(bool(report.get('truncated_after_chunks'))).lower()}",
        f"- Aggregate confidence: {inline_markdown(aggregate.get('confidence', 'unknown'))}",
        "",
        "### Artifacts",
        "",
    ]

    if artifacts:
        for name in sorted(artifacts):
            lines.append(f"- {inline_markdown(name)}: {inline_markdown(artifacts[name])}")
    else:
        lines.append("- None recorded.")
    lines.append("")

    append_grouped_change_section(
        lines,
        "Safe Documentation Edits",
        "These items are backed by medium- or high-confidence facts found in reviewed chunks. They should still be reviewed, but they do not require inventing new source material.",
        safe_edits,
    )
    append_grouped_change_section(
        lines,
        "Needs User Decision",
        "These items come from reported documentation gaps and require a human decision before drafting text.",
        needs_decision,
    )
    append_grouped_change_section(
        lines,
        "Insufficient Evidence",
        "These items come from low-confidence facts, missing review results, or validation warnings. Do not turn them into edits without more evidence.",
        insufficient_evidence,
    )

    lines.extend(["## Follow-Up Files", ""])
    if not reported_followup_files and not accepted_followups and not skipped_followups:
        lines.append("- None recorded.")
        lines.append("")
    else:
        if reported_followup_files:
            lines.append("### Reported By Documenter")
            lines.append("")
            for path in reported_followup_files:
                lines.append(f"- {inline_markdown(path)}")
            lines.append("")
        if accepted_followups:
            lines.append("### Accepted By Controller")
            lines.append("")
            for item in accepted_followups:
                reasons = item.get("candidate_reasons", [])
                reason_text = ", ".join(inline_markdown(reason) for reason in reasons) if isinstance(reasons, list) else ""
                suffix = f"; reasons: {reason_text}" if reason_text else ""
                lines.append(
                    f"- [{source_from_followup_record(item)}] {inline_markdown(item.get('path', 'unknown'))} accepted via {inline_markdown(item.get('accepted_via', 'unknown'))}{suffix}"
                )
            lines.append("")
        if skipped_followups:
            lines.append("### Skipped By Controller")
            lines.append("")
            for item in skipped_followups:
                lines.append(
                    f"- [{source_from_followup_record(item)}] {inline_markdown(item.get('path', 'unknown'))} skipped: {inline_markdown(item.get('reason', 'unknown'))}"
                )
            lines.append("")

    lines.extend(["## Validation Notes", ""])
    criteria_satisfied = [item for item in aggregate.get("criteria_satisfied", []) if isinstance(item, str)]
    criteria_remaining = [item for item in aggregate.get("criteria_remaining", []) if isinstance(item, str)]
    if criteria_satisfied:
        lines.append(f"- Criteria satisfied: {', '.join(inline_markdown(item) for item in criteria_satisfied)}")
    if criteria_remaining:
        lines.append(f"- Criteria remaining: {', '.join(inline_markdown(item) for item in criteria_remaining)}")
    if not validation_warnings and not report.get("discovery_warnings"):
        if not criteria_satisfied and not criteria_remaining:
            lines.append("- None recorded.")
    else:
        for warning in validation_warnings:
            chunk_id = inline_markdown(warning.get("chunk_id", "unknown-chunk"))
            field = inline_markdown(warning.get("field", "unknown_field"))
            reason = inline_markdown(warning.get("reason", "unknown_reason"))
            lines.append(f"- [{chunk_id}] {field}: {reason}")
        for warning in report.get("discovery_warnings", []):
            if isinstance(warning, dict):
                source = inline_markdown(warning.get("source", "discovery"))
                reason = inline_markdown(warning.get("reason", "unknown_reason"))
                detail = inline_markdown(warning.get("detail", ""))
                lines.append(f"- [{source}] {reason}: {detail}")
    lines.append("")

    lines.extend(
        [
            "## Caveats",
            "",
            "- This plan is generated from processed chunks only; it does not imply unprocessed files were reviewed.",
            "- Proposed changes are grouped by the file whose chunk produced the evidence.",
            "- Safe edits are source-backed facts, not automatic file modifications.",
            "- Low-confidence and validation-warning items require additional verification before drafting.",
            "",
        ]
    )
    return "\n".join(lines)


def require_path_under_directory(path: Path, directory: Path, label: str) -> None:
    try:
        path.resolve().relative_to(directory.resolve())
    except ValueError as exc:
        raise OrchestratorError(f"{label} must stay under configured output directory: {path}") from exc


def draft_path_for_target(draft_files_dir: Path, target_file: str) -> Path:
    relative_target = Path(target_file)
    if relative_target.is_absolute():
        raise OrchestratorError(f"Cannot draft an absolute target path: {target_file}")
    draft_path = (draft_files_dir / relative_target).resolve()
    require_path_under_directory(draft_path, draft_files_dir, "Draft file path")
    return draft_path


def build_draft_notes(
    target_file: str,
    items: list[dict[str, Any]],
    report: dict[str, Any],
    report_path: Path,
    change_plan_path: Path,
) -> str:
    lines = [
        "",
        "",
        "<!-- agentic-documenter-draft-notes:start -->",
        "# Documenter Draft Notes",
        "",
        "This draft is an artifact copy, not an applied edit. Review the notes below before manually applying any change.",
        "",
        f"- Target file: {inline_markdown(target_file)}",
        f"- Source report: {inline_markdown(report_path)}",
        f"- Change plan: {inline_markdown(change_plan_path)}",
        f"- Generated from report timestamp: {inline_markdown(report.get('generated_at', 'unknown'))}",
        "",
    ]
    for category in CHANGE_PLAN_CATEGORY_TITLES:
        category_items = [item for item in items if item.get("category") == category]
        if not category_items:
            continue
        lines.extend([f"## {CHANGE_PLAN_CATEGORY_TITLES[category]}", ""])
        for item in category_items:
            lines.append(
                f"- {inline_markdown(item.get('id', 'CP-????'))} "
                f"[{inline_markdown(item.get('source', 'unknown'))}; "
                f"confidence: {inline_markdown(item.get('confidence', 'unknown'))}; "
                f"basis: {inline_markdown(item.get('basis', 'unknown'))}] "
                f"{inline_markdown(item.get('text', ''))}"
            )
        lines.append("")
    lines.append("<!-- agentic-documenter-draft-notes:end -->")
    lines.append("")
    return "\n".join(lines)


def write_draft_index(draft_root: Path, metadata: dict[str, Any]) -> Path:
    index_path = draft_root / "README.md"
    lines = [
        "# Documenter Draft Artifacts",
        "",
        "These drafts are generated artifacts. They do not modify target repository files and can be removed by deleting this draft directory.",
        "",
        f"- Target root: {inline_markdown(metadata.get('target_root', 'unknown'))}",
        f"- Source report: {inline_markdown(metadata.get('report_path', 'unknown'))}",
        f"- Change plan: {inline_markdown(metadata.get('change_plan_path', 'unknown'))}",
        f"- Draft metadata: {inline_markdown(metadata.get('metadata_path', 'draft-metadata.json'))}",
        "",
        "## Draft Files",
        "",
    ]
    drafts = metadata.get("drafts", [])
    if not isinstance(drafts, list) or not drafts:
        lines.append("- None recorded.")
    else:
        for draft in drafts:
            if not isinstance(draft, dict):
                continue
            item_ids = draft.get("change_plan_item_ids", [])
            item_text = ", ".join(inline_markdown(item) for item in item_ids) if isinstance(item_ids, list) else ""
            suffix = f" ({item_text})" if item_text else ""
            lines.append(
                f"- `{inline_markdown(draft.get('target_file', 'unknown'))}` -> "
                f"`{inline_markdown(draft.get('draft_path', 'unknown'))}`{suffix}"
            )
    lines.append("")
    index_path.write_text("\n".join(lines), encoding="utf-8")
    return index_path


def write_draft_artifacts(
    output_dir: Path,
    target_root: Path,
    report: dict[str, Any],
    report_path: Path,
    change_plan_path: Path,
    assigned_tool_ids: set[str],
    max_in_memory_doc_bytes: int,
    allow_large_in_memory_docs: bool,
) -> dict[str, str]:
    output_root = output_dir.resolve()
    run_id = (
        f"{sanitize_filename(target_root.name)}-"
        f"{sanitize_filename(str(report.get('seed_doc_id') or report.get('doc_id') or 'document'))}-"
        f"{artifact_timestamp()}"
    )
    draft_root = (output_dir / "drafts" / run_id).resolve()
    require_path_under_directory(draft_root, output_root, "Draft root")
    draft_files_dir = (draft_root / "files").resolve()
    require_path_under_directory(draft_files_dir, output_root, "Draft files directory")
    draft_files_dir.mkdir(parents=True, exist_ok=False)

    change_plan_items = collect_change_plan_items(report)
    items_by_target: dict[str, list[dict[str, Any]]] = {}
    for item in change_plan_items:
        target_file = inline_markdown(item.get("target_file", "unknown"))
        items_by_target.setdefault(target_file, []).append(item)

    drafts: list[dict[str, Any]] = []
    for target_file in sorted(items_by_target):
        source_path = (target_root / target_file).resolve()
        try:
            source_path.relative_to(target_root.resolve())
        except ValueError as exc:
            raise OrchestratorError(f"Cannot draft file outside target root: {target_file}") from exc
        content = read_repo_file(
            target_root,
            assigned_tool_ids,
            target_file,
            max_in_memory_doc_bytes,
            allow_large_in_memory_docs,
        )
        draft_path = draft_path_for_target(draft_files_dir, target_file)
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_items = items_by_target[target_file]
        draft_path.write_text(
            content + build_draft_notes(target_file, draft_items, report, report_path, change_plan_path),
            encoding="utf-8",
        )
        drafts.append(
            {
                "target_file": target_file,
                "source_path": str(source_path),
                "draft_path": str(draft_path),
                "change_plan_item_ids": [item["id"] for item in draft_items],
                "change_plan_items": draft_items,
                "report_path": str(report_path),
                "change_plan_path": str(change_plan_path),
            }
        )

    metadata_path = draft_root / "draft-metadata.json"
    require_path_under_directory(metadata_path, output_root, "Draft metadata path")
    metadata: dict[str, Any] = {
        "schema_version": 1,
        "kind": "documenter_draft_metadata",
        "generated_at": utc_now(),
        "target_root": str(target_root),
        "output_dir": str(output_root),
        "draft_root": str(draft_root),
        "report_path": str(report_path),
        "change_plan_path": str(change_plan_path),
        "write_policy": {
            "target_repo_read_only": True,
            "drafts_under_output_dir_only": True,
            "overwrite_target_files": False,
        },
        "draft_count": len(drafts),
        "drafts": drafts,
    }
    metadata["metadata_path"] = str(metadata_path)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    index_path = write_draft_index(draft_root, metadata)
    metadata["index_path"] = str(index_path)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return {
        "draft_root": str(draft_root),
        "draft_index": str(index_path),
        "draft_metadata": str(metadata_path),
    }


def extract_heading_preview(doc_id: str, lines: list[str], limit: int = 20) -> list[dict[str, Any]]:
    suffix = Path(doc_id).suffix.lower()
    headings: list[dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if suffix in {".md", ".adoc"}:
            marker = "=" if suffix == ".adoc" else "#"
            if stripped.startswith(marker):
                level = len(stripped) - len(stripped.lstrip(marker))
                text = stripped[level:].strip()
                if text:
                    headings.append({"line": index, "level": level, "text": text[:160]})
        elif suffix == ".rst":
            if index < len(lines) and set(lines[index].strip()) in [{"="}, {"-"}, {"~"}, {"^"}]:
                headings.append({"line": index, "level": 1, "text": stripped[:160]})
        if len(headings) >= limit:
            break
    return headings


def build_document_manifest(
    repo_root: Path,
    docs: list[str],
    tracked_file_set: set[str],
    document_scope: str,
    seed_doc_id: str,
    discovery_warnings: list[dict[str, str]],
    max_in_memory_doc_bytes: int,
    allow_large_in_memory_docs: bool,
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for doc_id in docs:
        path = repo_root / doc_id
        try:
            stat = path.stat()
            if not allow_large_in_memory_docs and stat.st_size > max_in_memory_doc_bytes:
                entries.append(
                    {
                        "path": doc_id,
                        "suffix": Path(doc_id).suffix.lower(),
                        "tracked": doc_id in tracked_file_set,
                        "selected_seed": doc_id == seed_doc_id,
                        "readable": False,
                        "skipped_reason": "exceeds_in_memory_limit",
                        "bytes": stat.st_size,
                        "max_in_memory_doc_bytes": max_in_memory_doc_bytes,
                    }
                )
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            entries.append(
                {
                    "path": doc_id,
                    "suffix": Path(doc_id).suffix.lower(),
                    "tracked": doc_id in tracked_file_set,
                    "selected_seed": doc_id == seed_doc_id,
                    "readable": False,
                    "error": str(exc),
                }
            )
            continue

        lines = text.splitlines()
        entries.append(
            {
                "path": doc_id,
                "suffix": Path(doc_id).suffix.lower(),
                "tracked": doc_id in tracked_file_set,
                "selected_seed": doc_id == seed_doc_id,
                "readable": True,
                "bytes": stat.st_size,
                "line_count": len(lines),
                "token_estimate": estimate_tokens(text),
                "heading_preview": extract_heading_preview(doc_id, lines),
            }
        )

    return {
        "schema_version": 1,
        "kind": "document_manifest",
        "generated_at": utc_now(),
        "target_root": str(repo_root),
        "document_scope": document_scope,
        "doc_suffixes": sorted(DOC_SUFFIXES),
        "ignored_scan_dirs": sorted(IGNORED_SCAN_DIRS) if document_scope == "all" else [],
        "seed_doc_id": seed_doc_id,
        "document_count": len(entries),
        "tracked_document_count": sum(1 for entry in entries if entry.get("tracked")),
        "untracked_document_count": sum(1 for entry in entries if not entry.get("tracked")),
        "oversized_document_count": sum(
            1 for entry in entries if entry.get("skipped_reason") == "exceeds_in_memory_limit"
        ),
        "in_memory_file_policy": {
            "max_in_memory_doc_bytes": max_in_memory_doc_bytes,
            "allow_large_in_memory_docs": allow_large_in_memory_docs,
        },
        "discovery_warnings": discovery_warnings,
        "documents": entries,
    }


def summarize_document_manifest(manifest: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    return {
        "artifact": str(manifest_path),
        "document_scope": manifest.get("document_scope"),
        "document_count": manifest.get("document_count"),
        "tracked_document_count": manifest.get("tracked_document_count"),
        "untracked_document_count": manifest.get("untracked_document_count"),
        "discovery_warnings": manifest.get("discovery_warnings"),
    }


def candidate_base_reasons(path: str, seed_doc_id: str) -> list[str]:
    reasons: list[str] = []
    path_obj = Path(path)
    seed_parent = Path(seed_doc_id).parent.as_posix()
    parent = path_obj.parent.as_posix()
    name = path_obj.name.lower()
    suffix = path_obj.suffix.lower()
    lower_path = path.lower()

    if path == seed_doc_id:
        reasons.append("seed_doc")
    if parent == seed_parent:
        reasons.append("same_directory")
    if lower_path.startswith("runtime/") or suffix in {".cfg", ".ini", ".json", ".toml", ".yaml", ".yml"}:
        reasons.append("runtime_config")
    if lower_path.startswith("roles/"):
        reasons.append("role_prompt")
    if name.startswith(("start-", "stop-")) or (
        suffix in {".sh", ".ps1"} and ("start" in name or "stop" in name)
    ):
        reasons.append("startup_script")
    if name == "readme.md" or lower_path.endswith("/readme.md"):
        reasons.append("documentation_index")
    if suffix in DOC_SUFFIXES:
        reasons.append("documentation")
    if not reasons:
        reasons.append("in_scope_file")
    return unique_strings(reasons)


def candidate_reason_score(reasons: list[str]) -> int:
    return min((CANDIDATE_REASON_PRIORITY.get(reason, 100) for reason in reasons), default=100)


def metadata_for_candidate(
    repo_root: Path,
    path: str,
    tracked_file_set: set[str],
    document_entries: dict[str, dict[str, Any]],
    seed_doc_id: str,
) -> dict[str, Any] | None:
    suffix = Path(path).suffix.lower()
    if suffix not in FOLLOWUP_SUFFIXES:
        return None
    repo_path = (repo_root / path).resolve()
    try:
        repo_path.relative_to(repo_root.resolve())
        stat = repo_path.stat()
    except (OSError, ValueError):
        return None

    doc_entry = document_entries.get(path, {})
    candidate: dict[str, Any] = {
        "path": path,
        "suffix": suffix,
        "tracked": path in tracked_file_set,
        "reasons": candidate_base_reasons(path, seed_doc_id),
        "bytes": int(doc_entry.get("bytes", stat.st_size)),
    }
    if isinstance(doc_entry.get("line_count"), int):
        candidate["line_count"] = doc_entry["line_count"]
    if isinstance(doc_entry.get("token_estimate"), int):
        candidate["token_estimate"] = doc_entry["token_estimate"]
    if isinstance(doc_entry.get("heading_preview"), list) and doc_entry["heading_preview"]:
        candidate["heading_preview"] = doc_entry["heading_preview"][:5]
    return candidate


def build_review_plan(
    repo_root: Path,
    document_manifest: dict[str, Any],
    known_files: list[str],
    tracked_file_set: set[str],
    seed_doc_id: str,
    document_scope: str,
    controller_tool_dependencies: list[str],
    visible_candidate_limit: int,
    visible_candidate_token_limit: int,
    manifest_path: Path | None,
) -> dict[str, Any]:
    raw_docs = document_manifest.get("documents", [])
    document_entries = {
        entry["path"]: entry
        for entry in raw_docs
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }

    candidate_pool: list[dict[str, Any]] = []
    for path in unique_strings(sorted(known_files)):
        candidate = metadata_for_candidate(repo_root, path, tracked_file_set, document_entries, seed_doc_id)
        if candidate is not None:
            candidate_pool.append(candidate)

    candidate_pool.sort(key=lambda item: (candidate_reason_score(item["reasons"]), item["path"]))
    reason_counts: dict[str, int] = {}
    for candidate in candidate_pool:
        for reason in candidate["reasons"]:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

    return {
        "schema_version": 1,
        "kind": "documenter_review_plan",
        "generated_at": utc_now(),
        "target_root": str(repo_root),
        "document_scope": document_scope,
        "seed_doc_id": seed_doc_id,
        "document_manifest": summarize_document_manifest(document_manifest, manifest_path)
        if manifest_path is not None
        else {
            "document_scope": document_manifest.get("document_scope"),
            "document_count": document_manifest.get("document_count"),
            "tracked_document_count": document_manifest.get("tracked_document_count"),
            "untracked_document_count": document_manifest.get("untracked_document_count"),
            "discovery_warnings": document_manifest.get("discovery_warnings"),
        },
        "candidate_policy": {
            "max_visible_candidates_per_packet": visible_candidate_limit,
            "max_visible_candidate_tokens_per_packet": visible_candidate_token_limit,
            "candidate_reason_priority": CANDIDATE_REASON_PRIORITY,
            "followup_suffixes": sorted(FOLLOWUP_SUFFIXES),
        },
        "tool_dependencies": controller_tool_dependencies,
        "candidate_pool_count": len(candidate_pool),
        "candidate_reason_counts": dict(sorted(reason_counts.items())),
        "candidate_pool": candidate_pool,
    }


def summarize_review_plan(review_plan: dict[str, Any], review_plan_path: Path) -> dict[str, Any]:
    return {
        "artifact": str(review_plan_path),
        "candidate_pool_count": review_plan.get("candidate_pool_count"),
        "candidate_reason_counts": review_plan.get("candidate_reason_counts"),
        "candidate_policy": review_plan.get("candidate_policy"),
        "tool_dependencies": review_plan.get("tool_dependencies"),
    }


def write_review_plan(output_dir: Path, target_label: str, review_plan: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = artifact_timestamp()
    path = output_dir / f"doc-review-plan-{sanitize_filename(target_label)}-{timestamp}.json"
    path.write_text(json.dumps(review_plan, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return path


def extract_linked_candidate_paths(text: str, candidate_paths: set[str]) -> set[str]:
    linked: set[str] = set()
    for match in PATH_TOKEN_RE.finditer(text):
        candidate = match.group(0).strip("`'\".,:;()[]{}<>")
        candidate = candidate.replace("\\", "/")
        if candidate in candidate_paths:
            linked.add(candidate)
    return linked


def select_visible_followup_candidates(
    review_plan: dict[str, Any],
    target: ReviewTarget,
    chunk: Chunk,
    excluded_paths: set[str],
    max_candidates: int,
    max_candidate_tokens: int,
) -> list[dict[str, Any]]:
    if max_candidates <= 0 or max_candidate_tokens <= 0:
        return []

    candidate_pool = [
        item
        for item in review_plan.get("candidate_pool", [])
        if isinstance(item, dict) and isinstance(item.get("path"), str) and isinstance(item.get("reasons"), list)
    ]
    candidate_paths = {item["path"] for item in candidate_pool}
    linked_paths = extract_linked_candidate_paths(chunk.text, candidate_paths)
    current_parent = Path(target.doc_id).parent.as_posix()
    ranked_candidates: list[tuple[int, str, dict[str, Any]]] = []

    for candidate in candidate_pool:
        path = candidate["path"]
        if path in excluded_paths:
            continue
        reasons = [reason for reason in candidate["reasons"] if isinstance(reason, str)]
        if path in linked_paths and "linked_from_chunk" not in reasons:
            reasons = ["linked_from_chunk", *reasons]
        if Path(path).parent.as_posix() == current_parent and "same_directory" not in reasons:
            reasons.append("same_directory")
        visible = {
            "path": path,
            "reasons": unique_strings(reasons),
            "suffix": candidate.get("suffix"),
            "tracked": bool(candidate.get("tracked")),
        }
        for optional_field in ("line_count", "token_estimate"):
            if isinstance(candidate.get(optional_field), int):
                visible[optional_field] = candidate[optional_field]
        ranked_candidates.append((candidate_reason_score(visible["reasons"]), path, visible))

    selected: list[dict[str, Any]] = []
    token_total = 0
    for _, _, candidate in sorted(ranked_candidates, key=lambda item: (item[0], item[1])):
        candidate_tokens = estimate_tokens(json.dumps(candidate, ensure_ascii=True, sort_keys=True))
        if len(selected) >= max_candidates:
            break
        if token_total + candidate_tokens > max_candidate_tokens:
            continue
        selected.append(candidate)
        token_total += candidate_tokens
    return selected


def aggregate_report(report: dict[str, Any]) -> dict[str, Any]:
    facts_found: list[str] = []
    doc_gaps: list[str] = []
    reported_followup_files: list[str] = []
    validation_warnings: list[dict[str, Any]] = []
    confidence_counts = {"low": 0, "medium": 0, "high": 0}

    for chunk in report.get("chunks", []):
        if not isinstance(chunk, dict):
            continue
        result = chunk.get("result")
        if isinstance(result, dict):
            facts_found.extend([item for item in result.get("facts_found", []) if isinstance(item, str)])
            doc_gaps.extend([item for item in result.get("doc_gaps", []) if isinstance(item, str)])
            reported_followup_files.extend([item for item in result.get("followup_files", []) if isinstance(item, str)])
            confidence = result.get("confidence")
            if confidence in confidence_counts:
                confidence_counts[confidence] += 1
        for warning in chunk.get("validation_warnings", []):
            if isinstance(warning, dict):
                validation_warnings.append({"chunk_id": chunk.get("chunk_id"), **warning})

    criteria_initial = [item for item in report.get("criteria_initial", []) if isinstance(item, str)]
    criteria_remaining = [item for item in report.get("criteria_remaining", []) if isinstance(item, str)]
    criteria_satisfied = [item for item in criteria_initial if item not in set(criteria_remaining)]
    aggregate_confidence = "low"
    if confidence_counts["high"] and not confidence_counts["low"]:
        aggregate_confidence = "high" if not confidence_counts["medium"] else "medium"
    elif confidence_counts["medium"] and not confidence_counts["low"]:
        aggregate_confidence = "medium"

    followup_policy = report.get("followup_policy", {})
    accepted_followups: list[str] = []
    if isinstance(followup_policy, dict):
        for item in followup_policy.get("accepted_followups", []):
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                accepted_followups.append(item["path"])
    include_followups = isinstance(followup_policy, dict) and bool(followup_policy.get("include_followups"))
    followup_files = unique_strings(accepted_followups) if include_followups else unique_strings(reported_followup_files)

    return {
        "facts_found": unique_strings(facts_found),
        "criteria_satisfied": criteria_satisfied,
        "criteria_remaining": criteria_remaining,
        "doc_gaps": unique_strings(doc_gaps),
        "followup_files": followup_files,
        "reported_followup_files": unique_strings(reported_followup_files),
        "accepted_followup_files": unique_strings(accepted_followups),
        "validation_warnings": validation_warnings,
        "confidence_counts": confidence_counts,
        "confidence": aggregate_confidence,
    }


def build_summary_packet(report: dict[str, Any], aggregate: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "documenter",
        "task": "summarize_documentation_review",
        "doc_id": report.get("doc_id"),
        "seed_doc_id": report.get("seed_doc_id"),
        "target_root": report.get("target_root"),
        "reviewed_files": report.get("reviewed_files"),
        "review_plan": report.get("review_plan"),
        "followup_policy": report.get("followup_policy"),
        "chunks_processed": report.get("chunks_processed"),
        "chunks_total": report.get("chunks_total"),
        "truncated_after_chunks": report.get("truncated_after_chunks"),
        "criteria_initial": report.get("criteria_initial"),
        "aggregate": aggregate,
        "required_output": {
            "format": "markdown",
            "headings": [
                "Summary",
                "Satisfied Criteria",
                "Remaining Gaps",
                "Recommended Follow-Up Files",
                "Validation Notes",
                "Confidence and Caveats",
            ],
        },
    }


def sanitize_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return sanitized or "document"


def resolve_output_dir(config_root: Path, output_dir: str) -> Path:
    value = Path(output_dir)
    return value if value.is_absolute() else config_root / value


def write_report(output_dir: Path, target_label: str, doc_id: str, report: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = artifact_timestamp()
    path = output_dir / f"documenter-{sanitize_filename(target_label)}-{sanitize_filename(doc_id)}-{timestamp}.json"
    path.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return path


def write_change_plan(output_dir: Path, target_label: str, doc_id: str, change_plan: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = artifact_timestamp()
    path = output_dir / f"doc-change-plan-{sanitize_filename(target_label)}-{sanitize_filename(doc_id)}-{timestamp}.md"
    path.write_text(change_plan, encoding="utf-8")
    return path


def write_document_manifest(output_dir: Path, target_label: str, manifest: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = artifact_timestamp()
    path = output_dir / f"document-manifest-{sanitize_filename(target_label)}-{timestamp}.json"
    path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return path


def write_run_state_artifact(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["schema_version"] = RUN_STATE_SCHEMA_VERSION
    state["kind"] = "documenter_run_state"
    state["updated_at"] = utc_now()
    path.write_text(json.dumps(state, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def make_run_state_path(output_dir: Path, target_label: str, doc_id: str, run_id: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"run-state-{sanitize_filename(target_label)}-{sanitize_filename(doc_id)}-{run_id}.json"


def review_target_to_state(target: ReviewTarget) -> dict[str, Any]:
    return {
        "doc_id": target.doc_id,
        "source": target.source,
        "depth": target.depth,
        "parent_doc_id": target.parent_doc_id,
    }


def review_target_from_state(value: dict[str, Any]) -> ReviewTarget:
    doc_id = value.get("doc_id")
    source = value.get("source")
    depth = value.get("depth")
    parent_doc_id = value.get("parent_doc_id")
    if not isinstance(doc_id, str) or not isinstance(source, str) or not isinstance(depth, int):
        raise OrchestratorError("Run state contains an invalid review target.")
    if parent_doc_id is not None and not isinstance(parent_doc_id, str):
        raise OrchestratorError("Run state contains an invalid parent_doc_id.")
    return ReviewTarget(doc_id=doc_id, source=source, depth=depth, parent_doc_id=parent_doc_id)


def state_list(value: Any, field_name: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise OrchestratorError(f"Run state field {field_name} must be a list.")
    return value


def build_resume_key(
    args: argparse.Namespace,
    config_root: Path,
    target_root: Path,
    output_dir: Path,
    doc_id: str,
    role_base_url: str,
    criteria_initial: list[str],
    max_chunks: int | None,
    include_followups: bool,
    effective_followup_depth: int,
    followup_source_policy: str,
) -> dict[str, Any]:
    return {
        "mode": args.mode,
        "config_root": str(config_root),
        "target_root": str(target_root),
        "output_dir": str(output_dir.resolve()),
        "document_scope": args.document_scope,
        "doc_id": doc_id,
        "allow_untracked_doc": bool(args.allow_untracked_doc),
        "role_id": args.role_id,
        "role_base_url": role_base_url,
        "model": args.model,
        "dry_run": bool(args.dry_run),
        "write_draft": bool(args.write_draft),
        "chunk_token_limit": args.chunk_token_limit,
        "chunk_overlap_lines": args.chunk_overlap_lines,
        "visible_candidate_limit": args.visible_candidate_limit,
        "visible_candidate_token_limit": args.visible_candidate_token_limit,
        "max_chunks_per_file": max_chunks,
        "include_followups": include_followups,
        "followup_depth": effective_followup_depth,
        "max_followup_files": args.max_followup_files,
        "allow_nonvisible_followups": bool(args.allow_nonvisible_followups),
        "followup_source_policy": followup_source_policy,
        "criteria_initial": criteria_initial,
        "max_output_tokens": args.max_output_tokens,
        "max_in_memory_doc_bytes": args.max_in_memory_doc_bytes,
        "allow_large_in_memory_docs": bool(args.allow_large_in_memory_docs),
    }


def resume_key_mismatches(expected: dict[str, Any], current: dict[str, Any]) -> list[str]:
    mismatches: list[str] = []
    for key in sorted(set(expected) | set(current)):
        if expected.get(key) != current.get(key):
            mismatches.append(f"{key}: state={expected.get(key)!r} current={current.get(key)!r}")
    return mismatches


def load_resume_state(resume_path: Path) -> tuple[Path, dict[str, Any]]:
    data = read_json(resume_path)
    if data.get("kind") == "documenter_run_state":
        return resume_path, data
    if data.get("kind") != "documenter_orchestrator_report":
        raise OrchestratorError("--resume must point to a documenter report or run-state JSON artifact.")

    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict) or not isinstance(artifacts.get("run_state"), str):
        raise OrchestratorError("Report does not reference a run_state artifact and cannot be resumed.")
    state_path = Path(artifacts["run_state"])
    if not state_path.is_absolute():
        state_path = (resume_path.parent / state_path).resolve()
    state = read_json(state_path)
    if state.get("kind") != "documenter_run_state":
        raise OrchestratorError(f"Referenced run state is not a documenter_run_state artifact: {state_path}")
    return state_path, state


def validate_resume_state(
    state: dict[str, Any],
    current_resume_key: dict[str, Any],
    allow_arg_changes: bool,
) -> None:
    if state.get("kind") != "documenter_run_state":
        raise OrchestratorError("Resume artifact is not a documenter_run_state.")
    if state.get("schema_version") != RUN_STATE_SCHEMA_VERSION:
        raise OrchestratorError(
            f"Unsupported run state schema_version: {state.get('schema_version')!r}; "
            f"expected {RUN_STATE_SCHEMA_VERSION}."
        )
    status = state.get("status")
    if status not in RESUMABLE_RUN_STATUSES:
        raise OrchestratorError(
            f"Run state is not resumable because status is {status!r}. "
            "Use a running, failed, paused, or review_complete state."
        )
    previous_resume_key = state.get("resume_key")
    if not isinstance(previous_resume_key, dict):
        raise OrchestratorError("Run state is missing a resume_key object.")
    mismatches = resume_key_mismatches(previous_resume_key, current_resume_key)
    if mismatches and not allow_arg_changes:
        detail = "\n".join(f"- {item}" for item in mismatches)
        raise OrchestratorError(
            "Resume arguments are incompatible with the saved run state. "
            "Re-run with --resume-allow-arg-changes only if this is intentional.\n"
            f"{detail}"
        )


def mark_run_state_completed(state_path: Path, report: dict[str, Any]) -> None:
    state = read_json(state_path)
    if state.get("kind") != "documenter_run_state":
        raise OrchestratorError(f"Cannot mark non-state artifact complete: {state_path}")
    state["status"] = "completed"
    state["completed_at"] = utc_now()
    state["failure"] = None
    state["artifacts"] = report.get("artifacts", {})
    state["final_report"] = {
        "json_report": report.get("artifacts", {}).get("json_report")
        if isinstance(report.get("artifacts"), dict)
        else None,
        "chunks_processed": report.get("chunks_processed"),
        "reviewed_file_count": len(report.get("reviewed_files", []))
        if isinstance(report.get("reviewed_files"), list)
        else None,
    }
    write_run_state_artifact(state_path, state)


def mark_run_state_failed(state_path: Path, failure: dict[str, Any]) -> None:
    state = read_json(state_path)
    if state.get("kind") != "documenter_run_state":
        raise OrchestratorError(f"Cannot mark non-state artifact failed: {state_path}")
    state["status"] = "failed"
    state["failure"] = failure
    write_run_state_artifact(state_path, state)


def summary_path_for_report(report_path: Path) -> Path:
    return report_path.with_suffix(".md")


def write_summary(path: Path, summary: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(summary, encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a bounded documenter orchestrator demo.")
    parser.add_argument("--mode", choices=sorted(MODES), default="full")
    parser.add_argument(
        "--config-root",
        default=None,
        help="vllm-agent-gateway repo containing runtime/roles.json and runtime/tools.json.",
    )
    parser.add_argument(
        "--target-root",
        "--repo-root",
        dest="target_root",
        default=".",
        help="Target repository whose docs should be reviewed.",
    )
    parser.add_argument("--doc", default=None, help="Documentation file to review. Defaults to README.md.")
    parser.add_argument(
        "--document-scope",
        choices=sorted(DOCUMENT_SCOPES),
        default="tracked",
        help="Use tracked docs by default, or scan all target files for first-run/bootstrap docs.",
    )
    parser.add_argument("--role-id", default=DEFAULT_ROLE_ID)
    parser.add_argument("--role-base-url", default=None, help="Role proxy base URL. Defaults to role port from manifest.")
    parser.add_argument("--model", default=os.environ.get("AGENTIC_GATEWAY_MODEL", DEFAULT_MODEL))
    parser.add_argument("--chunk-token-limit", type=int, default=1000)
    parser.add_argument("--chunk-overlap-lines", type=int, default=8)
    parser.add_argument(
        "--visible-candidate-limit",
        type=int,
        default=DEFAULT_VISIBLE_CANDIDATE_LIMIT,
        help="Maximum visible follow-up candidates included in each packet.",
    )
    parser.add_argument(
        "--visible-candidate-token-limit",
        type=int,
        default=DEFAULT_VISIBLE_CANDIDATE_TOKEN_LIMIT,
        help="Maximum estimated tokens for visible follow-up candidate metadata in each packet.",
    )
    parser.add_argument("--max-chunks", type=int, default=None, help="Maximum chunks to process. Defaults to all chunks.")
    parser.add_argument("--all-chunks", action="store_true", help="Process all chunks. This is the default.")
    parser.add_argument(
        "--include-followups",
        action="store_true",
        help="Review exact tracked follow-up files returned by the documenter.",
    )
    parser.add_argument(
        "--followup-depth",
        type=int,
        default=0,
        help="Maximum follow-up expansion depth. 0 disables expansion unless --include-followups is set.",
    )
    parser.add_argument(
        "--max-followup-files",
        type=int,
        default=5,
        help="Maximum number of follow-up files to add to the controller queue.",
    )
    parser.add_argument(
        "--allow-nonvisible-followups",
        action="store_true",
        help="Compatibility mode: allow in-scope follow-up paths even when they were not visible in the packet.",
    )
    parser.add_argument("--criteria", action="append", default=None, help="Documentation criterion. Repeatable.")
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Report directory. Relative paths are resolved under --config-root.",
    )
    parser.add_argument("--allow-untracked-doc", action="store_true", help="Allow selected doc if it is inside target root.")
    parser.add_argument("--list-docs", action="store_true", help="List discovered docs in the target repo and exit.")
    parser.add_argument("--report", default=None, help="Existing JSON report to summarize with --mode summarize.")
    parser.add_argument(
        "--resume",
        default=None,
        help="Resume from a documenter report or run-state JSON artifact.",
    )
    parser.add_argument(
        "--resume-allow-arg-changes",
        action="store_true",
        help="Allow resume even when controller arguments changed.",
    )
    parser.add_argument("--summary-output", default=None, help="Markdown summary path. Defaults beside JSON report.")
    parser.add_argument(
        "--write-draft",
        action="store_true",
        help="Write draft artifact copies under the configured output directory. Requires --mode full.",
    )
    parser.add_argument(
        "--stop-after-chunks",
        type=int,
        default=None,
        help="Write state and pause after N newly processed chunks. Intended for resume smoke testing.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Write packets without calling the role endpoint.")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--max-output-tokens", type=int, default=1000)
    parser.add_argument(
        "--max-in-memory-doc-bytes",
        type=int,
        default=DEFAULT_MAX_IN_MEMORY_DOC_BYTES,
        help=(
            "Maximum selected or manifest document size for the in-memory controller path. "
            "Use the streaming documenter for larger files."
        ),
    )
    parser.add_argument(
        "--allow-large-in-memory-docs",
        action="store_true",
        help="Intentionally bypass the in-memory document size guard.",
    )
    return parser.parse_args()


def run_review(args: argparse.Namespace) -> tuple[dict[str, Any], Path, Path]:
    config_root = Path(args.config_root).resolve() if args.config_root else SCRIPT_CONFIG_ROOT
    target_root = Path(args.target_root).resolve()
    manifest = read_json(config_root / "runtime" / "roles.json")
    tool_catalog = read_json(config_root / "runtime" / "tools.json")
    role = load_role(manifest, args.role_id)
    assigned_tool_ids = role_tool_ids(role, load_tool_ids(tool_catalog))
    if args.max_chunks is not None and args.max_chunks < 1:
        raise OrchestratorError("--max-chunks must be at least 1 when provided.")
    if args.followup_depth < 0:
        raise OrchestratorError("--followup-depth cannot be negative.")
    if args.max_followup_files < 0:
        raise OrchestratorError("--max-followup-files cannot be negative.")
    if args.visible_candidate_limit < 0:
        raise OrchestratorError("--visible-candidate-limit cannot be negative.")
    if args.visible_candidate_token_limit < 0:
        raise OrchestratorError("--visible-candidate-token-limit cannot be negative.")
    if args.write_draft and args.mode != "full":
        raise OrchestratorError("--write-draft requires --mode full.")
    if args.stop_after_chunks is not None and args.stop_after_chunks < 1:
        raise OrchestratorError("--stop-after-chunks must be at least 1 when provided.")
    if args.max_in_memory_doc_bytes < 1:
        raise OrchestratorError("--max-in-memory-doc-bytes must be at least 1.")

    include_followups = bool(args.include_followups or args.followup_depth > 0)
    effective_followup_depth = args.followup_depth if args.followup_depth > 0 else (1 if include_followups else 0)
    followup_source_policy = (
        "known_files_compatibility" if args.allow_nonvisible_followups else "visible_followup_candidates"
    )
    max_chunks = None if args.all_chunks or args.max_chunks is None else args.max_chunks
    role_base_url = args.role_base_url or f"http://127.0.0.1:{role['port']}/v1"
    criteria_initial = args.criteria if args.criteria else list(DEFAULT_CRITERIA)

    known_files, tracked_file_list, discovery_warnings = discover_files_for_scope(
        target_root, assigned_tool_ids, args.document_scope
    )
    docs = doc_paths_from_files(known_files)
    doc_id, docs = select_document(target_root, docs, args.doc, args.allow_untracked_doc)
    if doc_id not in docs:
        docs = [doc_id, *docs]
    known_file_set = set(known_files)
    known_file_set.add(doc_id)
    tracked_file_set = set(tracked_file_list)
    controller_tool_dependencies = ["git_ls_files", "read_file"]
    if args.document_scope == "all":
        controller_tool_dependencies.append("scan_files")
    output_dir = resolve_output_dir(config_root, args.output_dir)
    document_manifest = build_document_manifest(
        target_root,
        docs,
        tracked_file_set,
        args.document_scope,
        doc_id,
        discovery_warnings,
        args.max_in_memory_doc_bytes,
        bool(args.allow_large_in_memory_docs),
    )
    resume_key = build_resume_key(
        args,
        config_root,
        target_root,
        output_dir,
        doc_id,
        role_base_url,
        criteria_initial,
        max_chunks,
        include_followups,
        effective_followup_depth,
        followup_source_policy,
    )
    loaded_state: dict[str, Any] | None = None
    resume_state_path: Path | None = None
    if args.resume:
        resume_state_path, loaded_state = load_resume_state(Path(args.resume).resolve())
        validate_resume_state(loaded_state, resume_key, bool(args.resume_allow_arg_changes))

    manifest_path: Path | None = None
    artifacts: dict[str, str] = {}
    if loaded_state is not None:
        raw_artifacts = loaded_state.get("artifacts", {})
        if not isinstance(raw_artifacts, dict):
            raise OrchestratorError("Run state artifacts field must be an object.")
        artifacts = {key: value for key, value in raw_artifacts.items() if isinstance(key, str) and isinstance(value, str)}
        artifacts["run_state"] = str(resume_state_path)
        if isinstance(artifacts.get("document_manifest"), str):
            manifest_path = Path(artifacts["document_manifest"])
    elif args.mode == "full":
        manifest_path = write_document_manifest(output_dir, target_root.name, document_manifest)
        artifacts["document_manifest"] = str(manifest_path)

    review_plan = build_review_plan(
        target_root,
        document_manifest,
        known_files,
        tracked_file_set,
        doc_id,
        args.document_scope,
        controller_tool_dependencies,
        args.visible_candidate_limit,
        args.visible_candidate_token_limit,
        manifest_path,
    )
    if loaded_state is not None:
        if not isinstance(artifacts.get("review_plan"), str):
            raise OrchestratorError("Run state is missing a review_plan artifact path.")
        review_plan_path = Path(artifacts["review_plan"])
    else:
        review_plan_path = write_review_plan(output_dir, target_root.name, review_plan)
        artifacts["review_plan"] = str(review_plan_path)

    if loaded_state is not None:
        run_state_path = resume_state_path
        assert run_state_path is not None
        run_id = loaded_state.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            run_id = artifact_timestamp()
        state_generated_at = loaded_state.get("generated_at") if isinstance(loaded_state.get("generated_at"), str) else utc_now()
        criteria_remaining = [
            item for item in state_list(loaded_state.get("criteria_remaining"), "criteria_remaining") if isinstance(item, str)
        ]
        chunk_reports = [
            item for item in state_list(loaded_state.get("chunk_reports"), "chunk_reports") if isinstance(item, dict)
        ]
        reviewed_file_reports = [
            item
            for item in state_list(loaded_state.get("reviewed_file_reports"), "reviewed_file_reports")
            if isinstance(item, dict)
        ]
        accepted_followups = [
            item for item in state_list(loaded_state.get("accepted_followups"), "accepted_followups") if isinstance(item, dict)
        ]
        skipped_followups = [
            item for item in state_list(loaded_state.get("skipped_followups"), "skipped_followups") if isinstance(item, dict)
        ]
        raw_queue = state_list(loaded_state.get("target_queue"), "target_queue")
        target_queue = [review_target_from_state(item) for item in raw_queue if isinstance(item, dict)]
        if not target_queue:
            raise OrchestratorError("Run state target_queue is empty.")
        queue_index = loaded_state.get("queue_index")
        if not isinstance(queue_index, int) or queue_index < 0:
            raise OrchestratorError("Run state queue_index must be a non-negative integer.")
        if queue_index > len(target_queue):
            raise OrchestratorError("Run state queue_index is beyond target_queue length.")
        queued_files = {
            item for item in state_list(loaded_state.get("queued_files"), "queued_files") if isinstance(item, str)
        }
        reviewed_files = {
            item for item in state_list(loaded_state.get("reviewed_files"), "reviewed_files") if isinstance(item, str)
        }
        completed_chunk_ids = {
            item
            for item in state_list(loaded_state.get("completed_chunk_ids"), "completed_chunk_ids")
            if isinstance(item, str)
        }
        failed_packets = [
            item for item in state_list(loaded_state.get("failed_packets"), "failed_packets") if isinstance(item, dict)
        ]
        queued_files.update(target.doc_id for target in target_queue)
    else:
        run_id = artifact_timestamp()
        run_state_path = make_run_state_path(output_dir, target_root.name, doc_id, run_id)
        state_generated_at = utc_now()
        artifacts["run_state"] = str(run_state_path)
        criteria_remaining = list(criteria_initial)
        chunk_reports: list[dict[str, Any]] = []
        reviewed_file_reports: list[dict[str, Any]] = []
        accepted_followups: list[dict[str, Any]] = []
        skipped_followups: list[dict[str, Any]] = []
        target_queue: list[ReviewTarget] = [ReviewTarget(doc_id=doc_id, source="seed", depth=0)]
        queued_files: set[str] = {doc_id}
        reviewed_files: set[str] = set()
        completed_chunk_ids: set[str] = set()
        failed_packets: list[dict[str, Any]] = []
        queue_index = 0

    review_plan_candidates = {
        item["path"]: item
        for item in review_plan.get("candidate_pool", [])
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }

    def persist_state(status: str, failure: dict[str, Any] | None = None) -> None:
        state = {
            "schema_version": RUN_STATE_SCHEMA_VERSION,
            "kind": "documenter_run_state",
            "generated_at": state_generated_at,
            "status": status,
            "run_id": run_id,
            "mode": args.mode,
            "config_root": str(config_root),
            "target_root": str(target_root),
            "output_dir": str(output_dir.resolve()),
            "role_id": args.role_id,
            "role_base_url": role_base_url,
            "model": args.model,
            "dry_run": bool(args.dry_run),
            "resume_key": resume_key,
            "artifacts": artifacts,
            "doc_id": doc_id,
            "seed_doc_id": doc_id,
            "document_scope": args.document_scope,
            "criteria_initial": criteria_initial,
            "criteria_remaining": criteria_remaining,
            "chunk_token_limit": args.chunk_token_limit,
            "chunk_overlap_lines": args.chunk_overlap_lines,
            "max_chunks_per_file": max_chunks,
            "include_followups": include_followups,
            "followup_depth": effective_followup_depth,
            "max_followup_files": args.max_followup_files,
            "followup_source_policy": followup_source_policy,
            "target_queue": [review_target_to_state(target) for target in target_queue],
            "queue_index": queue_index,
            "queued_files": sorted(queued_files),
            "reviewed_files": sorted(reviewed_files),
            "completed_chunk_ids": sorted(completed_chunk_ids),
            "completed_chunk_count": len(completed_chunk_ids),
            "chunk_reports": chunk_reports,
            "reviewed_file_reports": reviewed_file_reports,
            "accepted_followups": accepted_followups,
            "skipped_followups": skipped_followups,
            "failed_packets": failed_packets,
            "failure": failure,
        }
        if loaded_state is not None:
            state["resumed_from"] = str(resume_state_path)
            state["resume_allow_arg_changes"] = bool(args.resume_allow_arg_changes)
        write_run_state_artifact(run_state_path, state)

    persist_state("running")
    newly_processed_chunks = 0
    while queue_index < len(target_queue):
        target = target_queue[queue_index]

        content = read_repo_file(
            target_root,
            assigned_tool_ids,
            target.doc_id,
            args.max_in_memory_doc_bytes,
            bool(args.allow_large_in_memory_docs),
        )
        chunks = chunk_document(target.doc_id, content, args.chunk_token_limit, args.chunk_overlap_lines)
        selected_chunks = chunks if max_chunks is None else chunks[:max_chunks]

        for chunk in selected_chunks:
            if chunk.chunk_id in completed_chunk_ids:
                continue
            visible_followup_candidates = select_visible_followup_candidates(
                review_plan,
                target,
                chunk,
                reviewed_files | {target.doc_id},
                args.visible_candidate_limit,
                args.visible_candidate_token_limit,
            )
            visible_followup_candidate_by_path = {
                candidate["path"]: candidate
                for candidate in visible_followup_candidates
                if isinstance(candidate.get("path"), str)
            }
            packet = build_packet(target, chunk, criteria_remaining, visible_followup_candidates)
            entry: dict[str, Any] = {
                "doc_id": target.doc_id,
                "source": target.source,
                "depth": target.depth,
                "parent_doc_id": target.parent_doc_id,
                "chunk_id": chunk.chunk_id,
                "lines": [chunk.start_line, chunk.end_line],
                "overlap_previous_lines": chunk.overlap_previous_lines,
                "input_token_estimate": chunk.token_estimate,
                "visible_followup_candidates": visible_followup_candidates,
                "packet": packet if args.dry_run else {"criteria_remaining": criteria_remaining},
            }
            if not args.dry_run:
                try:
                    result = call_documenter(role_base_url, args.model, packet, args.max_output_tokens, args.timeout)
                except OrchestratorError as exc:
                    failed_packet = {
                        "failed_at": utc_now(),
                        "doc_id": target.doc_id,
                        "source": target.source,
                        "depth": target.depth,
                        "parent_doc_id": target.parent_doc_id,
                        "chunk_id": chunk.chunk_id,
                        "lines": [chunk.start_line, chunk.end_line],
                        "overlap_previous_lines": chunk.overlap_previous_lines,
                        "input_token_estimate": chunk.token_estimate,
                        "criteria_remaining": list(criteria_remaining),
                        "visible_followup_candidates": visible_followup_candidates,
                        "packet_summary": {
                            "role": packet.get("role"),
                            "task": packet.get("task"),
                            "doc_id": packet.get("doc_id"),
                            "chunk_id": packet.get("chunk_id"),
                            "source": packet.get("source"),
                            "followup_depth": packet.get("followup_depth"),
                        },
                        "error": str(exc),
                    }
                    failed_packets.append(failed_packet)
                    persist_state("failed", failed_packet)
                    raise
                warnings = normalize_result_policy(result, known_file_set, criteria_remaining)
                satisfied = {item for item in result["criteria_satisfied"] if isinstance(item, str)}
                criteria_remaining = [item for item in criteria_remaining if item not in satisfied]
                entry["result"] = result
                if warnings:
                    entry["validation_warnings"] = warnings

                for followup_file in unique_strings(result["followup_files"]):
                    candidate_depth = target.depth + 1
                    followup_record = {
                        "path": followup_file,
                        "source_doc_id": target.doc_id,
                        "source_chunk_id": chunk.chunk_id,
                        "candidate_depth": candidate_depth,
                        "visible_candidate": followup_file in visible_followup_candidate_by_path,
                        "candidate_reasons": visible_followup_candidate_by_path.get(
                            followup_file, review_plan_candidates.get(followup_file, {})
                        ).get("reasons", []),
                        "source_policy": followup_source_policy,
                    }
                    if not include_followups:
                        skipped_followups.append({**followup_record, "reason": "followups_disabled"})
                        continue
                    if target.depth >= effective_followup_depth:
                        skipped_followups.append({**followup_record, "reason": "depth_limit_reached"})
                        continue
                    if followup_file not in known_file_set:
                        skipped_followups.append({**followup_record, "reason": "not_in_document_scope"})
                        continue
                    if Path(followup_file).suffix.lower() not in FOLLOWUP_SUFFIXES:
                        skipped_followups.append({**followup_record, "reason": "unsupported_extension"})
                        continue
                    if (
                        followup_file not in visible_followup_candidate_by_path
                        and not args.allow_nonvisible_followups
                    ):
                        skipped_followups.append({**followup_record, "reason": "not_visible_to_packet"})
                        continue
                    if followup_file in reviewed_files or followup_file in queued_files:
                        skipped_followups.append({**followup_record, "reason": "already_seen"})
                        continue
                    if len(accepted_followups) >= args.max_followup_files:
                        skipped_followups.append({**followup_record, "reason": "max_followup_files_reached"})
                        continue

                    accepted_via = (
                        "visible_followup_candidates"
                        if followup_file in visible_followup_candidate_by_path
                        else "known_files_compatibility"
                    )
                    accepted_followups.append({**followup_record, "accepted_via": accepted_via})
                    target_queue.append(
                        ReviewTarget(
                            doc_id=followup_file,
                            source="followup",
                            depth=candidate_depth,
                            parent_doc_id=target.doc_id,
                        )
                    )
                    queued_files.add(followup_file)
            chunk_reports.append(entry)
            completed_chunk_ids.add(chunk.chunk_id)
            newly_processed_chunks += 1
            persist_state("running")
            if args.stop_after_chunks is not None and newly_processed_chunks >= args.stop_after_chunks:
                persist_state("paused")
                print(f"Paused after {newly_processed_chunks} newly processed chunk(s). Resume with {run_state_path}")
                raise OrchestratorPaused()

        reviewed_file_reports.append(
            {
                "doc_id": target.doc_id,
                "source": target.source,
                "depth": target.depth,
                "parent_doc_id": target.parent_doc_id,
                "chunks_total": len(chunks),
                "chunks_processed": len(selected_chunks),
                "truncated_after_chunks": len(selected_chunks) < len(chunks),
            }
        )
        reviewed_files.add(target.doc_id)
        queue_index += 1
        persist_state("running")

    chunks_total = sum(item["chunks_total"] for item in reviewed_file_reports)
    chunks_processed = sum(item["chunks_processed"] for item in reviewed_file_reports)

    report = {
        "schema_version": 1,
        "kind": "documenter_orchestrator_report",
        "generated_at": utc_now(),
        "mode": args.mode,
        "config_root": str(config_root),
        "target_root": str(target_root),
        "role_id": args.role_id,
        "role_base_url": role_base_url,
        "model": args.model,
        "dry_run": args.dry_run,
        "tool_policy": {
            "assigned_tool_ids": sorted(assigned_tool_ids),
            "controller_tool_dependencies": controller_tool_dependencies,
            "controller_tools_used": controller_tool_dependencies,
            "review_plan_tool_dependencies": review_plan.get("tool_dependencies", []),
        },
        "document_scope": args.document_scope,
        "known_files_count": len(known_file_set),
        "tracked_files_count": len(tracked_file_set),
        "docs_discovered": docs,
        "doc_id": doc_id,
        "seed_doc_id": doc_id,
        "review_plan": summarize_review_plan(review_plan, review_plan_path),
        "reviewed_files": reviewed_file_reports,
        "followup_policy": {
            "include_followups": include_followups,
            "followup_depth": effective_followup_depth,
            "max_followup_files": args.max_followup_files,
            "source_policy": followup_source_policy,
            "allow_nonvisible_followups": args.allow_nonvisible_followups,
            "allowed_suffixes": sorted(FOLLOWUP_SUFFIXES),
            "skip_reason_codes": [
                "followups_disabled",
                "depth_limit_reached",
                "not_in_document_scope",
                "unsupported_extension",
                "not_visible_to_packet",
                "already_seen",
                "max_followup_files_reached",
            ],
            "accepted_followups": accepted_followups,
            "skipped_followups": skipped_followups,
        },
        "criteria_initial": criteria_initial,
        "criteria_remaining": criteria_remaining,
        "chunk_token_limit": args.chunk_token_limit,
        "chunk_overlap_lines": args.chunk_overlap_lines,
        "in_memory_file_policy": {
            "max_in_memory_doc_bytes": args.max_in_memory_doc_bytes,
            "allow_large_in_memory_docs": bool(args.allow_large_in_memory_docs),
        },
        "max_chunks_per_file": max_chunks,
        "chunks_total": chunks_total,
        "chunks_processed": chunks_processed,
        "truncated_after_chunks": any(item["truncated_after_chunks"] for item in reviewed_file_reports),
        "chunks": chunk_reports,
        "failed_packets": failed_packets,
    }
    if discovery_warnings:
        report["discovery_warnings"] = discovery_warnings
    if manifest_path is not None:
        report["document_manifest"] = summarize_document_manifest(document_manifest, manifest_path)
    report["artifacts"] = artifacts
    report["aggregate"] = aggregate_report(report)
    output_path = write_report(output_dir, target_root.name, doc_id, report)
    report.setdefault("artifacts", {})
    if isinstance(report["artifacts"], dict):
        report["artifacts"]["json_report"] = str(output_path)
        if args.mode == "full":
            change_plan = build_doc_change_plan(report)
            change_plan_path = write_change_plan(output_dir, target_root.name, doc_id, change_plan)
            report["artifacts"]["doc_change_plan"] = str(change_plan_path)
            print(f"Wrote {change_plan_path}")
            if args.write_draft:
                draft_artifacts = write_draft_artifacts(
                    output_dir,
                    target_root,
                    report,
                    output_path,
                    change_plan_path,
                    assigned_tool_ids,
                    args.max_in_memory_doc_bytes,
                    bool(args.allow_large_in_memory_docs),
                )
                report["artifacts"].update(draft_artifacts)
                print(f"Wrote {draft_artifacts['draft_root']}")
    output_path.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output_path}")
    if args.dry_run:
        print("Dry run only; no role endpoint was called.")
    persist_state("review_complete")
    return report, output_path, run_state_path


def run_summary(
    report: dict[str, Any],
    report_path: Path,
    role_base_url: str,
    model: str,
    max_tokens: int,
    timeout: int,
    summary_output: str | None,
) -> Path:
    aggregate = report.get("aggregate")
    if not isinstance(aggregate, dict):
        aggregate = aggregate_report(report)
        report["aggregate"] = aggregate
    if not report.get("chunks") or all(not isinstance(chunk, dict) or "result" not in chunk for chunk in report["chunks"]):
        raise OrchestratorError("Cannot summarize a report without chunk review results.")
    packet = build_summary_packet(report, aggregate)
    summary = call_documenter_summary(role_base_url, model, packet, max_tokens, timeout)
    summary_path = Path(summary_output).resolve() if summary_output else summary_path_for_report(report_path)
    write_summary(summary_path, summary)
    report.setdefault("artifacts", {})
    if isinstance(report["artifacts"], dict):
        report["artifacts"]["markdown_summary"] = str(summary_path)
    report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {summary_path}")
    return summary_path


def main() -> int:
    args = parse_args()
    if args.write_draft and args.mode != "full":
        raise OrchestratorError("--write-draft requires --mode full.")
    if args.resume and args.mode == "summarize":
        raise OrchestratorError("--resume cannot be combined with --mode summarize.")
    if args.resume and args.list_docs:
        raise OrchestratorError("--resume cannot be combined with --list-docs.")
    config_root = Path(args.config_root).resolve() if args.config_root else SCRIPT_CONFIG_ROOT
    manifest = read_json(config_root / "runtime" / "roles.json")
    role = load_role(manifest, args.role_id)
    role_base_url = args.role_base_url or f"http://127.0.0.1:{role['port']}/v1"

    if args.list_docs:
        if args.mode == "summarize":
            raise OrchestratorError("--list-docs cannot be combined with --mode summarize.")
        tool_catalog = read_json(config_root / "runtime" / "tools.json")
        assigned_tool_ids = role_tool_ids(role, load_tool_ids(tool_catalog))
        target_root = Path(args.target_root).resolve()
        known_files, _, _ = discover_files_for_scope(target_root, assigned_tool_ids, args.document_scope)
        for path in doc_paths_from_files(known_files):
            print(path)
        return 0

    if args.mode == "summarize":
        if not args.report:
            raise OrchestratorError("--mode summarize requires --report.")
        report_path = Path(args.report).resolve()
        report = read_json(report_path)
        summary_role_base_url = args.role_base_url or report.get("role_base_url") or role_base_url
        if not isinstance(summary_role_base_url, str):
            raise OrchestratorError("Report role_base_url must be a string when used for summarization.")
        run_summary(
            report,
            report_path,
            summary_role_base_url,
            args.model,
            args.max_output_tokens,
            args.timeout,
            args.summary_output,
        )
        return 0

    try:
        report, report_path, run_state_path = run_review(args)
    except OrchestratorPaused:
        return 0
    try:
        if args.mode == "full" and not args.dry_run:
            run_summary(
                report,
                report_path,
                role_base_url,
                args.model,
                args.max_output_tokens,
                args.timeout,
                args.summary_output,
            )
    except OrchestratorError as exc:
        mark_run_state_failed(
            run_state_path,
            {
                "failed_at": utc_now(),
                "stage": "summary",
                "error": str(exc),
            },
        )
        raise
    mark_run_state_completed(run_state_path, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
