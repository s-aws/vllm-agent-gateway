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
DOC_SUFFIXES = {".adoc", ".md", ".rst", ".txt"}
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


class OrchestratorError(RuntimeError):
    """Raised for deterministic controller failures."""


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    start_line: int
    end_line: int
    text: str
    token_estimate: int


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def normalize_repo_path(repo_root: Path, value: str) -> str:
    raw_path = Path(value)
    candidate = raw_path.resolve() if raw_path.is_absolute() else (repo_root / raw_path).resolve()
    try:
        rel_path = candidate.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise OrchestratorError(f"Path is outside repo root: {value}") from exc
    return rel_path.as_posix()


def select_document(repo_root: Path, assigned_tool_ids: set[str], requested_doc: str | None) -> tuple[str, list[str]]:
    docs = tracked_docs(repo_root, assigned_tool_ids)
    if not docs:
        raise OrchestratorError("No tracked documentation files found.")
    if requested_doc is None:
        if "README.md" in docs:
            return "README.md", docs
        return docs[0], docs

    doc_id = normalize_repo_path(repo_root, requested_doc)
    if doc_id not in docs:
        raise OrchestratorError(f"Selected document is not a tracked documentation file: {doc_id}")
    return doc_id, docs


def read_repo_file(repo_root: Path, assigned_tool_ids: set[str], doc_id: str) -> str:
    require_tool(assigned_tool_ids, "read_file")
    path = (repo_root / doc_id).resolve()
    try:
        path.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise OrchestratorError(f"Refusing to read outside repo root: {doc_id}") from exc
    return path.read_text(encoding="utf-8", errors="replace")


def chunk_document(doc_id: str, text: str, max_tokens: int) -> list[Chunk]:
    if max_tokens < 128:
        raise OrchestratorError("--chunk-token-limit must be at least 128.")
    lines = text.splitlines(keepends=True)
    if not lines:
        return [Chunk(f"{doc_id}:0001", 1, 1, "", 1)]

    chunks: list[Chunk] = []
    current: list[str] = []
    start_line = 1

    def flush(end_line: int) -> None:
        if not current:
            return
        chunk_text = "".join(current)
        index = len(chunks) + 1
        chunks.append(
            Chunk(
                chunk_id=f"{doc_id}:{index:04d}",
                start_line=start_line,
                end_line=end_line,
                text=chunk_text,
                token_estimate=estimate_tokens(chunk_text),
            )
        )

    for line_number, line in enumerate(lines, start=1):
        proposed = "".join([*current, line])
        if current and estimate_tokens(proposed) > max_tokens:
            flush(line_number - 1)
            current = [line]
            start_line = line_number
        else:
            current.append(line)
    flush(len(lines))
    return chunks


def build_packet(doc_id: str, chunk: Chunk, criteria_remaining: list[str]) -> dict[str, Any]:
    return {
        "role": "documenter",
        "task": "review_chunk_for_documentation",
        "doc_id": doc_id,
        "chunk_id": chunk.chunk_id,
        "lines": [chunk.start_line, chunk.end_line],
        "criteria_remaining": criteria_remaining,
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

    invalid_followups = [item for item in result["followup_files"] if item not in known_files]
    if invalid_followups:
        warnings.append(
            {
                "field": "followup_files",
                "reason": "removed_untracked_or_unprovided_paths",
                "values": invalid_followups,
            }
        )
        result["followup_files"] = [item for item in result["followup_files"] if item in known_files]

    return warnings


def sanitize_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return sanitized or "document"


def write_report(output_dir: Path, doc_id: str, report: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = utc_now().replace(":", "").replace("-", "")
    path = output_dir / f"documenter-{sanitize_filename(doc_id)}-{timestamp}.json"
    path.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a bounded documenter orchestrator demo.")
    parser.add_argument("--repo-root", default=".", help="Repository root to inspect.")
    parser.add_argument("--doc", default=None, help="Tracked documentation file to review. Defaults to README.md.")
    parser.add_argument("--role-id", default=DEFAULT_ROLE_ID)
    parser.add_argument("--role-base-url", default=None, help="Role proxy base URL. Defaults to role port from manifest.")
    parser.add_argument("--model", default=os.environ.get("AGENTIC_GATEWAY_MODEL", DEFAULT_MODEL))
    parser.add_argument("--chunk-token-limit", type=int, default=1000)
    parser.add_argument("--max-chunks", type=int, default=1, help="Maximum chunks to process. Use --all-chunks for all.")
    parser.add_argument("--all-chunks", action="store_true")
    parser.add_argument("--criteria", action="append", default=None, help="Documentation criterion. Repeatable.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run", action="store_true", help="Write packets without calling the role endpoint.")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--max-output-tokens", type=int, default=1000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    manifest = read_json(repo_root / "runtime" / "roles.json")
    tool_catalog = read_json(repo_root / "runtime" / "tools.json")
    role = load_role(manifest, args.role_id)
    assigned_tool_ids = role_tool_ids(role, load_tool_ids(tool_catalog))
    doc_id, docs = select_document(repo_root, assigned_tool_ids, args.doc)
    all_tracked_files = tracked_files(repo_root, assigned_tool_ids)
    content = read_repo_file(repo_root, assigned_tool_ids, doc_id)
    chunks = chunk_document(doc_id, content, args.chunk_token_limit)
    max_chunks = None if args.all_chunks else args.max_chunks
    selected_chunks = chunks if max_chunks is None else chunks[:max_chunks]
    role_base_url = args.role_base_url or f"http://127.0.0.1:{role['port']}/v1"
    criteria_initial = args.criteria if args.criteria else list(DEFAULT_CRITERIA)
    criteria_remaining = list(criteria_initial)
    chunk_reports: list[dict[str, Any]] = []

    for chunk in selected_chunks:
        packet = build_packet(doc_id, chunk, criteria_remaining)
        entry: dict[str, Any] = {
            "chunk_id": chunk.chunk_id,
            "lines": [chunk.start_line, chunk.end_line],
            "input_token_estimate": chunk.token_estimate,
            "packet": packet if args.dry_run else {"criteria_remaining": criteria_remaining},
        }
        if not args.dry_run:
            result = call_documenter(role_base_url, args.model, packet, args.max_output_tokens, args.timeout)
            warnings = normalize_result_policy(result, set(all_tracked_files), criteria_remaining)
            satisfied = {item for item in result["criteria_satisfied"] if isinstance(item, str)}
            criteria_remaining = [item for item in criteria_remaining if item not in satisfied]
            entry["result"] = result
            if warnings:
                entry["validation_warnings"] = warnings
        chunk_reports.append(entry)

    report = {
        "schema_version": 1,
        "kind": "documenter_orchestrator_report",
        "generated_at": utc_now(),
        "repo_root": str(repo_root),
        "role_id": args.role_id,
        "role_base_url": role_base_url,
        "model": args.model,
        "dry_run": args.dry_run,
        "tool_policy": {
            "assigned_tool_ids": sorted(assigned_tool_ids),
            "controller_tools_used": ["git_ls_files", "read_file"],
        },
        "tracked_files_count": len(all_tracked_files),
        "docs_discovered": docs,
        "doc_id": doc_id,
        "criteria_initial": criteria_initial,
        "criteria_remaining": criteria_remaining,
        "chunk_token_limit": args.chunk_token_limit,
        "chunks_total": len(chunks),
        "chunks_processed": len(selected_chunks),
        "truncated_after_chunks": len(selected_chunks) < len(chunks),
        "chunks": chunk_reports,
    }
    output_path = write_report(repo_root / args.output_dir, doc_id, report)
    print(f"Wrote {output_path}")
    if args.dry_run:
        print("Dry run only; no role endpoint was called.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
