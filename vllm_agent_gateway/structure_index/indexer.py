"""Deterministic code/document structure indexing.

The indexer is controller-side only. It reads target files, parses structure with
stdlib parsers or line scanners, and writes source ranges without executing
target code or asking a model to infer repository layout.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import warnings
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus


SCHEMA_VERSION = 1
DEFAULT_OUTPUT_DIR = ".agentic_reports"
DEFAULT_MAX_FILE_BYTES = 4 * 1024 * 1024
FILE_SCOPES = {"tracked", "all"}
SUPPORTED_SUFFIXES = {".adoc", ".json", ".md", ".py", ".rst", ".yaml", ".yml"}
MARKDOWN_SUFFIXES = {".adoc", ".md", ".rst"}
CONFIG_SUFFIXES = {".json", ".yaml", ".yml"}
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

ATX_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
ASCIIDOC_HEADING_RE = re.compile(r"^(={1,6})\s+(.+?)\s*$")
RST_UNDERLINE_CHARS = set("=-~^\"'")
INLINE_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
REFERENCE_LINK_RE = re.compile(r"\[([^\]]+)\]\[([^\]]+)\]")
REFERENCE_DEF_RE = re.compile(r"^\s*\[([^\]]+)\]:\s+(\S+)")
JSON_KEY_RE = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:')
YAML_KEY_RE = re.compile(r"^(\s*)(?:-\s*)?([^#:\[\]{},][^:#]*?):(?:\s*(.*))?$")


class StructureIndexError(RuntimeError):
    """Raised for deterministic structure index failures."""


@dataclass(frozen=True)
class FileSelection:
    files: list[str]
    tracked_files: list[str]
    warnings: list[dict[str, Any]]
    tool_dependencies: list[dict[str, Any]]


@dataclass(frozen=True)
class CodeStructureIndexInvocationRequest:
    target_root: Path | str = "."
    file_scope: str = "tracked"
    output_dir: Path | str = DEFAULT_OUTPUT_DIR
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    slice_path: list[str] | None = None
    slice_symbol: str | None = None
    slice_key_path: str | None = None
    slice_reference_target: str | None = None
    slice_max_records: int = 50

    @classmethod
    def from_namespace(cls, args: Any) -> "CodeStructureIndexInvocationRequest":
        names = {item.name for item in fields(cls)}
        return cls(**{name: getattr(args, name) for name in names})


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def artifact_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def sanitize_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return sanitized or "target"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def text_preview(value: str | None, limit: int = 160) -> str | None:
    if value is None:
        return None
    text = " ".join(value.strip().split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def normalize_repo_path(repo_root: Path, value: str | Path) -> str:
    raw_path = Path(value)
    candidate = raw_path.resolve() if raw_path.is_absolute() else (repo_root / raw_path).resolve()
    try:
        rel_path = candidate.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise StructureIndexError(f"Path is outside target root: {value}") from exc
    return rel_path.as_posix()


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
        raise StructureIndexError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def tracked_files(repo_root: Path) -> list[str]:
    return [line for line in run_git(repo_root, ["ls-files"]).splitlines() if line]


def scan_repo_files(repo_root: Path) -> list[str]:
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


def select_index_files(repo_root: Path, file_scope: str) -> FileSelection:
    if file_scope not in FILE_SCOPES:
        raise StructureIndexError(f"--file-scope must be one of: {', '.join(sorted(FILE_SCOPES))}")

    warnings: list[dict[str, Any]] = []
    tool_dependencies: list[dict[str, Any]] = [
        {
            "tool_id": "git_ls_files",
            "purpose": "discover_tracked_files",
            "read_only": True,
        }
    ]
    try:
        tracked = tracked_files(repo_root)
    except StructureIndexError as exc:
        if file_scope == "tracked":
            raise
        tracked = []
        warnings.append({"source": "git_ls_files", "reason": "unavailable", "detail": str(exc)})

    if file_scope == "tracked":
        files = tracked
    else:
        files = scan_repo_files(repo_root)
        tool_dependencies.append(
            {
                "tool_id": "scan_files",
                "purpose": "discover_all_supported_files",
                "read_only": True,
            }
        )

    supported = sorted(path for path in files if Path(path).suffix.lower() in SUPPORTED_SUFFIXES)
    return FileSelection(
        files=supported,
        tracked_files=tracked,
        warnings=warnings,
        tool_dependencies=tool_dependencies,
    )


def module_name_from_path(path: str) -> str:
    without_suffix = Path(path).with_suffix("").as_posix()
    parts = [part for part in without_suffix.split("/") if part and part != "__init__"]
    return ".".join(parts) or Path(path).stem


def decorator_name(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return node.__class__.__name__


def index_python_file(path: str, text: str) -> dict[str, Any]:
    line_count = len(text.splitlines()) or 1
    parse_warnings: list[dict[str, Any]] = []
    try:
        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always", SyntaxWarning)
            tree = ast.parse(text, filename=path)
        parse_warnings = [
            {
                "message": str(warning.message),
                "category": warning.category.__name__,
                "line": warning.lineno,
                "filename": warning.filename,
            }
            for warning in caught_warnings
            if issubclass(warning.category, SyntaxWarning)
        ]
    except SyntaxError as exc:
        return {
            "parser": "python_ast",
            "status": "parse_error",
            "language": "python",
            "symbols": [],
            "imports": [],
            "parse_warnings": parse_warnings,
            "parse_errors": [
                {
                    "message": exc.msg,
                    "line": exc.lineno,
                    "offset": exc.offset,
                    "text": text_preview(exc.text),
                }
            ],
        }

    module_name = module_name_from_path(path)
    symbols: list[dict[str, Any]] = [
        {
            "kind": "module",
            "name": module_name,
            "qualified_name": module_name,
            "line_range": [1, line_count],
            "docstring_preview": text_preview(ast.get_docstring(tree)),
        }
    ]
    imports: list[dict[str, Any]] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.parents: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> Any:
            qualified = ".".join([module_name, *self.parents, node.name])
            symbols.append(
                {
                    "kind": "class",
                    "name": node.name,
                    "qualified_name": qualified,
                    "line_range": [node.lineno, getattr(node, "end_lineno", node.lineno) or node.lineno],
                    "decorators": [decorator_name(item) for item in node.decorator_list],
                    "docstring_preview": text_preview(ast.get_docstring(node)),
                }
            )
            self.parents.append(node.name)
            self.generic_visit(node)
            self.parents.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
            self._visit_function(node, "function")

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
            self._visit_function(node, "async_function")

        def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, kind: str) -> None:
            qualified = ".".join([module_name, *self.parents, node.name])
            symbols.append(
                {
                    "kind": kind,
                    "name": node.name,
                    "qualified_name": qualified,
                    "line_range": [node.lineno, getattr(node, "end_lineno", node.lineno) or node.lineno],
                    "decorators": [decorator_name(item) for item in node.decorator_list],
                    "docstring_preview": text_preview(ast.get_docstring(node)),
                }
            )
            self.parents.append(node.name)
            self.generic_visit(node)
            self.parents.pop()

        def visit_Import(self, node: ast.Import) -> Any:
            imports.append(
                {
                    "kind": "import",
                    "line": node.lineno,
                    "module": None,
                    "level": 0,
                    "names": [{"name": item.name, "asname": item.asname} for item in node.names],
                }
            )

        def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
            imports.append(
                {
                    "kind": "import_from",
                    "line": node.lineno,
                    "module": node.module,
                    "level": node.level,
                    "names": [{"name": item.name, "asname": item.asname} for item in node.names],
                }
            )

    Visitor().visit(tree)
    symbols.sort(key=lambda item: (item["line_range"][0], item["kind"], item["qualified_name"]))
    imports.sort(key=lambda item: (item["line"], item["kind"], item.get("module") or ""))
    return {
        "parser": "python_ast",
        "status": "indexed",
        "language": "python",
        "symbols": symbols,
        "imports": imports,
        "parse_warnings": parse_warnings,
        "parse_errors": [],
    }


def slug_anchor(title: str, existing: dict[str, int]) -> str:
    slug = re.sub(r"[^\w\s-]", "", title.lower(), flags=re.UNICODE)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = slug or "section"
    count = existing.get(slug, 0)
    existing[slug] = count + 1
    if count:
        return f"{slug}-{count}"
    return slug


def line_heading(line: str, next_line: str | None, existing_anchors: dict[str, int]) -> dict[str, Any] | None:
    match = ATX_HEADING_RE.match(line)
    if match:
        title = match.group(2).strip()
        return {
            "style": "markdown_atx",
            "level": len(match.group(1)),
            "title": title,
            "anchor": slug_anchor(title, existing_anchors),
        }
    match = ASCIIDOC_HEADING_RE.match(line)
    if match:
        title = match.group(2).strip()
        return {
            "style": "asciidoc",
            "level": len(match.group(1)),
            "title": title,
            "anchor": slug_anchor(title, existing_anchors),
        }
    if next_line and line.strip() and len(set(next_line.strip())) == 1 and next_line.strip()[0] in RST_UNDERLINE_CHARS:
        title = line.strip()
        underline = next_line.strip()[0]
        level = 1 if underline == "=" else 2
        return {
            "style": "rst_underline",
            "level": level,
            "title": title,
            "anchor": slug_anchor(title, existing_anchors),
        }
    return None


def is_external_link(target: str) -> bool:
    parsed = urlsplit(target)
    return bool(parsed.scheme) or target.startswith("mailto:")


def normalize_link_target(target_root: Path, source_path: str, raw_target: str) -> dict[str, Any]:
    clean = unquote(raw_target.strip().strip("<>"))
    path_part, separator, anchor = clean.partition("#")
    if is_external_link(clean):
        return {
            "target": clean,
            "target_path": None,
            "target_anchor": None,
            "link_type": "external",
            "file_exists": None,
        }
    if clean.startswith("#") or (not path_part and separator):
        target_path = source_path
    else:
        path_without_query = path_part.split("?", 1)[0]
        candidate = (target_root / source_path).parent / path_without_query
        try:
            target_path = candidate.resolve().relative_to(target_root.resolve()).as_posix()
        except ValueError:
            target_path = None
    file_exists = (target_root / target_path).exists() if target_path else False
    return {
        "target": clean,
        "target_path": target_path,
        "target_anchor": anchor or None,
        "link_type": "relative",
        "file_exists": file_exists,
    }


def index_markdown_file(path: str, text: str, target_root: Path) -> dict[str, Any]:
    lines = text.splitlines()
    headings: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    reference_defs: dict[str, str] = {}
    existing_anchors: dict[str, int] = {}

    for index, line in enumerate(lines):
        definition = REFERENCE_DEF_RE.match(line)
        if definition:
            reference_defs[definition.group(1).strip().lower()] = definition.group(2).strip()

    for index, line in enumerate(lines):
        line_no = index + 1
        heading = line_heading(line, lines[index + 1] if index + 1 < len(lines) else None, existing_anchors)
        if heading is not None:
            headings.append({**heading, "line_range": [line_no, line_no]})

        for match in INLINE_LINK_RE.finditer(line):
            target = normalize_link_target(target_root, path, match.group(2))
            links.append(
                {
                    "text": match.group(1),
                    "raw_target": match.group(2),
                    "line": line_no,
                    **target,
                }
            )
        for match in REFERENCE_LINK_RE.finditer(line):
            ref = match.group(2).strip().lower()
            if ref in reference_defs:
                target = normalize_link_target(target_root, path, reference_defs[ref])
                links.append(
                    {
                        "text": match.group(1),
                        "raw_target": reference_defs[ref],
                        "reference_id": ref,
                        "line": line_no,
                        **target,
                    }
                )

    return {
        "parser": "markdown_reference_scanner",
        "status": "indexed",
        "language": "markdown",
        "headings": headings,
        "anchors": [item["anchor"] for item in headings],
        "links": links,
        "parse_errors": [],
    }


def json_key_line_map(text: str) -> dict[str, list[int]]:
    by_key: dict[str, list[int]] = {}
    for line_no, line in enumerate(text.splitlines(), 1):
        for match in JSON_KEY_RE.finditer(line):
            try:
                key = json.loads(f'"{match.group(1)}"')
            except json.JSONDecodeError:
                key = match.group(1)
            by_key.setdefault(str(key), []).append(line_no)
    return by_key


def scalar_preview(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {"value_type": "object", "child_count": len(value), "scalar_preview": None}
    if isinstance(value, list):
        return {"value_type": "array", "child_count": len(value), "scalar_preview": None}
    if value is None:
        return {"value_type": "null", "scalar_preview": "null"}
    if isinstance(value, bool):
        return {"value_type": "boolean", "scalar_preview": str(value).lower()}
    if isinstance(value, (int, float)):
        return {"value_type": "number", "scalar_preview": str(value)}
    return {"value_type": "string", "scalar_preview": text_preview(str(value), 120)}


def walk_json_paths(value: Any, key_lines: dict[str, list[int]], prefix: str = "") -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key in sorted(value):
            child = value[key]
            path = f"{prefix}.{key}" if prefix else str(key)
            line_hits = key_lines.get(str(key), [])
            records.append(
                {
                    "path": path,
                    "key": str(key),
                    "line_range": [line_hits[0], line_hits[0]] if line_hits else None,
                    **scalar_preview(child),
                }
            )
            records.extend(walk_json_paths(child, key_lines, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            records.append({"path": path, "key": str(index), "line_range": None, **scalar_preview(child)})
            records.extend(walk_json_paths(child, key_lines, path))
    return records


def index_json_file(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return {
            "parser": "json",
            "status": "parse_error",
            "language": "json",
            "key_paths": [],
            "parse_errors": [{"message": exc.msg, "line": exc.lineno, "column": exc.colno}],
        }
    return {
        "parser": "json",
        "status": "indexed",
        "language": "json",
        "key_paths": walk_json_paths(parsed, json_key_line_map(text)),
        "parse_errors": [],
    }


def yaml_value_type(value: str | None) -> dict[str, Any]:
    if value is None or value == "":
        return {"value_type": "object", "scalar_preview": None}
    trimmed = value.strip()
    if trimmed in {"|", ">"}:
        return {"value_type": "block_scalar", "scalar_preview": trimmed}
    if trimmed.lower() in {"true", "false"}:
        return {"value_type": "boolean", "scalar_preview": trimmed.lower()}
    if trimmed.lower() in {"null", "~"}:
        return {"value_type": "null", "scalar_preview": "null"}
    if re.fullmatch(r"-?\d+(?:\.\d+)?", trimmed):
        return {"value_type": "number", "scalar_preview": trimmed}
    if trimmed.startswith("[") and trimmed.endswith("]"):
        return {"value_type": "array", "scalar_preview": text_preview(trimmed, 120)}
    if trimmed.startswith("{") and trimmed.endswith("}"):
        return {"value_type": "object", "scalar_preview": text_preview(trimmed, 120)}
    return {"value_type": "string", "scalar_preview": text_preview(trimmed.strip("\"'"), 120)}


def index_yaml_file(text: str) -> dict[str, Any]:
    stack: list[tuple[int, str]] = []
    key_paths: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []

    for line_no, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped in {"---", "..."}:
            continue
        match = YAML_KEY_RE.match(line)
        if not match:
            continue
        indent = len(match.group(1).replace("\t", "    "))
        key = match.group(2).strip().strip("\"'")
        value = (match.group(3) or "").strip()
        if value.count("[") != value.count("]") or value.count("{") != value.count("}"):
            parse_errors.append({"message": "unbalanced inline collection", "line": line_no})

        while stack and stack[-1][0] >= indent:
            stack.pop()
        path_parts = [item[1] for item in stack] + [key]
        path = ".".join(path_parts)
        key_paths.append(
            {
                "path": path,
                "key": key,
                "line_range": [line_no, line_no],
                **yaml_value_type(value),
            }
        )
        if value == "" or value in {"|", ">"}:
            stack.append((indent, key))

    return {
        "parser": "yaml_line_scanner",
        "status": "parse_error" if parse_errors else "indexed",
        "language": "yaml",
        "key_paths": key_paths,
        "parse_errors": parse_errors,
    }


def index_file(repo_root: Path, rel_path: str, max_file_bytes: int) -> dict[str, Any]:
    path = (repo_root / rel_path).resolve()
    try:
        path.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise StructureIndexError(f"Refusing to index outside target root: {rel_path}") from exc

    suffix = path.suffix.lower()
    base_record: dict[str, Any] = {
        "path": rel_path,
        "suffix": suffix,
        "size_bytes": None,
        "sha256": None,
        "status": "pending",
    }
    try:
        size = path.stat().st_size
        base_record["size_bytes"] = size
        if size > max_file_bytes:
            return {
                **base_record,
                "status": "skipped_large",
                "parser": None,
                "reason": f"size exceeds max_file_bytes ({max_file_bytes})",
            }
        base_record["sha256"] = file_sha256(path)
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {**base_record, "status": "read_error", "parser": None, "error": str(exc)}

    if suffix == ".py":
        details = index_python_file(rel_path, text)
    elif suffix in MARKDOWN_SUFFIXES:
        details = index_markdown_file(rel_path, text, repo_root)
    elif suffix == ".json":
        details = index_json_file(text)
    elif suffix in {".yaml", ".yml"}:
        details = index_yaml_file(text)
    else:
        details = {"status": "skipped_unsupported", "parser": None, "language": None}
    return {**base_record, **details}


def finalize_markdown_links(index: dict[str, Any], repo_root: Path) -> None:
    anchors_by_path = {
        file_record["path"]: set(file_record.get("anchors", []))
        for file_record in index["files"]
        if file_record.get("parser") == "markdown_reference_scanner"
    }
    edges: list[dict[str, Any]] = []
    inbound_counts: dict[str, int] = {}
    outbound_counts: dict[str, int] = {}
    unresolved_count = 0

    for file_record in index["files"]:
        links = file_record.get("links")
        if not isinstance(links, list):
            continue
        source_path = file_record["path"]
        for link in links:
            target_path = link.get("target_path")
            target_anchor = link.get("target_anchor")
            unresolved = False
            if link.get("link_type") == "relative":
                if not isinstance(target_path, str) or not (repo_root / target_path).exists():
                    unresolved = True
                elif isinstance(target_anchor, str) and target_anchor not in anchors_by_path.get(target_path, set()):
                    unresolved = True
            link["unresolved"] = unresolved
            if unresolved:
                unresolved_count += 1
            if isinstance(target_path, str):
                outbound_counts[source_path] = outbound_counts.get(source_path, 0) + 1
                inbound_counts[target_path] = inbound_counts.get(target_path, 0) + 1
            edges.append(
                {
                    "source_path": source_path,
                    "target_path": target_path,
                    "target_anchor": target_anchor,
                    "line": link.get("line"),
                    "link_type": link.get("link_type"),
                    "unresolved": unresolved,
                }
            )

    for file_record in index["files"]:
        if file_record.get("parser") == "markdown_reference_scanner":
            path = file_record["path"]
            file_record["outbound_edge_count"] = outbound_counts.get(path, 0)
            file_record["inbound_edge_count"] = inbound_counts.get(path, 0)
            file_record["unresolved_link_count"] = sum(1 for link in file_record.get("links", []) if link.get("unresolved"))

    index["reference_graph"] = {
        "edge_count": len(edges),
        "unresolved_edge_count": unresolved_count,
        "edges": sorted(edges, key=lambda item: (item["source_path"], item.get("line") or 0, item.get("target_path") or "")),
    }


def summarize_index(files: list[dict[str, Any]], selected_files: list[str]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    parser_counts: dict[str, int] = {}
    symbol_counts: dict[str, int] = {}
    for file_record in files:
        status = str(file_record.get("status"))
        status_counts[status] = status_counts.get(status, 0) + 1
        parser = file_record.get("parser")
        if isinstance(parser, str):
            parser_counts[parser] = parser_counts.get(parser, 0) + 1
        for symbol in file_record.get("symbols", []):
            if isinstance(symbol, dict):
                kind = str(symbol.get("kind"))
                symbol_counts[kind] = symbol_counts.get(kind, 0) + 1
    return {
        "selected_file_count": len(selected_files),
        "indexed_file_count": status_counts.get("indexed", 0),
        "status_counts": dict(sorted(status_counts.items())),
        "parser_counts": dict(sorted(parser_counts.items())),
        "symbol_counts": dict(sorted(symbol_counts.items())),
    }


def build_code_structure_index(
    target_root: Path,
    file_scope: str = "tracked",
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> dict[str, Any]:
    root = target_root.resolve()
    selection = select_index_files(root, file_scope)
    files = [index_file(root, rel_path, max_file_bytes) for rel_path in selection.files]
    index: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "code_structure_index",
        "generated_at": utc_now(),
        "target_root": str(root),
        "file_scope": file_scope,
        "selected_files": selection.files,
        "tracked_file_count": len(selection.tracked_files),
        "selected_file_count": len(selection.files),
        "max_file_bytes": max_file_bytes,
        "parser_versions": {
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "python_ast": "stdlib_ast",
            "json": "stdlib_json",
            "markdown_reference_scanner": "line_scanner_v1",
            "yaml_line_scanner": "line_scanner_v1",
        },
        "selection_policy": {
            "prefer_structure_index_for_suffixes": sorted(SUPPORTED_SUFFIXES),
            "fallback": "existing_document_or_streaming_chunk_paths",
            "read_only": True,
            "executes_target_code": False,
        },
        "tool_dependencies": [
            *selection.tool_dependencies,
            {
                "tool_id": "read_file",
                "purpose": "read_selected_supported_files_for_static_parse",
                "read_only": True,
            },
        ],
        "parser_dependencies": [
            {"id": "python_ast", "kind": "stdlib_parser", "read_only": True, "executes_target_code": False},
            {"id": "markdown_reference_scanner", "kind": "line_scanner", "read_only": True, "executes_target_code": False},
            {"id": "json", "kind": "stdlib_parser", "read_only": True, "executes_target_code": False},
            {"id": "yaml_line_scanner", "kind": "line_scanner", "read_only": True, "executes_target_code": False},
        ],
        "discovery_warnings": selection.warnings,
        "files": files,
    }
    finalize_markdown_links(index, root)
    index["summary"] = summarize_index(files, selection.files)
    return index


def record_matches_symbol(record: dict[str, Any], symbol_query: str | None) -> bool:
    if not symbol_query:
        return True
    haystack = " ".join(str(record.get(field, "")) for field in ("name", "qualified_name", "kind")).lower()
    return symbol_query.lower() in haystack


def build_index_slice(
    index: dict[str, Any],
    paths: list[str] | None = None,
    symbol_query: str | None = None,
    key_path_prefix: str | None = None,
    reference_target: str | None = None,
    max_records: int = 50,
) -> dict[str, Any]:
    if max_records < 1:
        raise StructureIndexError("max_records must be at least 1.")
    path_filter = set(paths or [])
    records: list[dict[str, Any]] = []
    category_filter_active = any([symbol_query, key_path_prefix, reference_target])
    include_symbols = bool(symbol_query) or not category_filter_active
    include_key_paths = bool(key_path_prefix) or not category_filter_active
    include_references = bool(reference_target) or not category_filter_active
    include_parse_errors = not category_filter_active

    for file_record in index.get("files", []):
        if not isinstance(file_record, dict):
            continue
        file_path = file_record.get("path")
        if not isinstance(file_path, str):
            continue
        if path_filter and file_path not in path_filter:
            continue

        if include_symbols:
            for symbol in file_record.get("symbols", []):
                if isinstance(symbol, dict) and record_matches_symbol(symbol, symbol_query):
                    records.append({"record_type": "symbol", "path": file_path, **symbol})

        if include_key_paths:
            for key_path in file_record.get("key_paths", []):
                if not isinstance(key_path, dict):
                    continue
                key_path_value = str(key_path.get("path", ""))
                if key_path_prefix and not key_path_value.startswith(key_path_prefix):
                    continue
                records.append({"record_type": "key_path", "path": file_path, **key_path})

        if include_references:
            for link in file_record.get("links", []):
                if not isinstance(link, dict):
                    continue
                target_path = str(link.get("target_path") or "")
                raw_target = str(link.get("raw_target") or "")
                if reference_target and reference_target not in target_path and reference_target not in raw_target:
                    continue
                records.append({"record_type": "reference_edge", "path": file_path, **link})

        if include_parse_errors:
            for parse_error in file_record.get("parse_errors", []):
                if isinstance(parse_error, dict):
                    records.append({"record_type": "parse_error", "path": file_path, **parse_error})

    truncated = len(records) > max_records
    selected = records[:max_records]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "code_structure_index_slice",
        "source_index_kind": index.get("kind"),
        "target_root": index.get("target_root"),
        "filters": {
            "paths": sorted(path_filter),
            "symbol_query": symbol_query,
            "key_path_prefix": key_path_prefix,
            "reference_target": reference_target,
        },
        "max_records": max_records,
        "record_count": len(selected),
        "available_record_count": len(records),
        "truncated": truncated,
        "packet_field": "structure_index_slice",
        "records": selected,
    }


def write_index_artifact(output_dir: Path, target_label: str, index: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"code-structure-index-{sanitize_filename(target_label)}-{artifact_timestamp()}.json"
    path.write_text(json.dumps(index, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return path


def write_slice_artifact(output_dir: Path, target_label: str, index_slice: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"code-structure-slice-{sanitize_filename(target_label)}-{artifact_timestamp()}.json"
    path.write_text(json.dumps(index_slice, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return path


def invoke_code_structure_index(request: CodeStructureIndexInvocationRequest) -> InvocationResult:
    target_root = Path(request.target_root).resolve()
    output_dir = Path(request.output_dir)
    if not output_dir.is_absolute():
        output_dir = Path.cwd() / output_dir
    slice_paths = request.slice_path or []
    index = build_code_structure_index(
        target_root=target_root,
        file_scope=request.file_scope,
        max_file_bytes=request.max_file_bytes,
    )
    index_path = write_index_artifact(output_dir, target_root.name, index)
    index["artifact_path"] = str(index_path)
    index_path.write_text(json.dumps(index, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    artifact_paths = {"code_structure_index": str(index_path)}
    summary_text = (
        f"selected_files={index.get('selected_file_count')} "
        f"indexed_files={index.get('summary', {}).get('indexed_file_count')}"
    )
    if slice_paths or request.slice_symbol or request.slice_key_path or request.slice_reference_target:
        index_slice = build_index_slice(
            index,
            paths=slice_paths or None,
            symbol_query=request.slice_symbol,
            key_path_prefix=request.slice_key_path,
            reference_target=request.slice_reference_target,
            max_records=request.slice_max_records,
        )
        slice_path = write_slice_artifact(output_dir, target_root.name, index_slice)
        artifact_paths["code_structure_slice"] = str(slice_path)
    return InvocationResult(
        workflow="code_structure.index",
        status=WorkflowStatus.COMPLETED,
        artifact_paths=artifact_paths,
        summary_text=summary_text,
        report=index,
    )
