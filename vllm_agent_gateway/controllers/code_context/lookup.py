"""Controller-owned read-only code context lookup workflow."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.controllers.code_context.codegraph_adapter import (
    CodeGraphContextAdapterError,
    run_relationship_queries,
)
from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus
from vllm_agent_gateway.structure_index.indexer import build_code_structure_index, build_index_slice


WORKFLOW_ID = "code_context.lookup"
SCHEMA_VERSION = 1
DEFAULT_OUTPUT_DIR = "code-context"
DEFAULT_MAX_RESULTS = 25
DEFAULT_MAX_FILES = 5
DEFAULT_CONTEXT_TOOLS = ["structure_index", "git_grep", "read_file"]
ALLOWED_CONTEXT_TOOLS = {"structure_index", "git_grep", "read_file", "codegraph_context"}
FORBIDDEN_CONTEXT_TERMS = {
    "raw_mcp_cypher",
    "raw_codegraph",
    "cypher",
    "codegraph_index_package",
    "codegraph_watch",
    "codegraph_delete",
    "codegraph_load_bundle",
}
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


class CodeContextLookupError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "code_context_lookup_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class CodeContextLookupRequest:
    config_root: Path | str = "."
    target_root: Path | str = "."
    output_root: Path | str = ".agentic_controller"
    workflow: str = WORKFLOW_ID
    schema_version: int = SCHEMA_VERSION
    query: str = ""
    paths: list[str] = field(default_factory=list)
    allowed_context_tools: list[str] = field(default_factory=lambda: list(DEFAULT_CONTEXT_TOOLS))
    max_results: int = DEFAULT_MAX_RESULTS
    max_files: int = DEFAULT_MAX_FILES
    include_structure: bool = True
    include_grep: bool = True
    include_file_snippets: bool = True
    relationship_queries: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        config_root: Path,
        target_root: Path,
        output_root: Path,
    ) -> "CodeContextLookupRequest":
        values: dict[str, Any] = {
            "config_root": config_root,
            "target_root": target_root,
            "output_root": output_root,
        }
        names = {item.name for item in fields(cls)}
        for key, value in payload.items():
            if key in names:
                values[key] = value
        return cls(**values)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def artifact_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2) + "\n").encode("utf-8")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def bounded_text(value: Any, limit: int = 500) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def normalize_repo_path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def validate_request_basics(request: CodeContextLookupRequest) -> dict[str, Any]:
    if request.workflow != WORKFLOW_ID:
        raise CodeContextLookupError("workflow must be code_context.lookup.", code="unsupported_workflow")
    if request.schema_version != SCHEMA_VERSION:
        raise CodeContextLookupError("schema_version must be 1.")
    if not isinstance(request.query, str) or not request.query.strip():
        raise CodeContextLookupError("query is required.")
    if not isinstance(request.paths, list) or not all(isinstance(item, str) for item in request.paths):
        raise CodeContextLookupError("paths must be a list of strings.")
    if not isinstance(request.allowed_context_tools, list) or not all(
        isinstance(item, str) for item in request.allowed_context_tools
    ):
        raise CodeContextLookupError("allowed_context_tools must be a list of strings.")
    if not isinstance(request.relationship_queries, list) or not all(
        isinstance(item, dict) for item in request.relationship_queries
    ):
        raise CodeContextLookupError("relationship_queries must be a list of objects.")
    if not isinstance(request.max_results, int) or isinstance(request.max_results, bool) or not 1 <= request.max_results <= 100:
        raise CodeContextLookupError("max_results must be an integer from 1 through 100.")
    if not isinstance(request.max_files, int) or isinstance(request.max_files, bool) or not 1 <= request.max_files <= 20:
        raise CodeContextLookupError("max_files must be an integer from 1 through 20.")
    tools = set(request.allowed_context_tools)
    forbidden = sorted(tools & FORBIDDEN_CONTEXT_TERMS)
    raw_text = json.dumps(
        {
            "query": request.query,
            "paths": request.paths,
            "allowed_context_tools": request.allowed_context_tools,
            "relationship_queries": request.relationship_queries,
        },
        ensure_ascii=True,
    ).lower()
    if forbidden or any(term in raw_text for term in FORBIDDEN_CONTEXT_TERMS):
        raise CodeContextLookupError(
            "Raw CodeGraphContext operations are not allowed for code_context.lookup.",
            code="raw_codegraph_not_allowed",
            status=HTTPStatus.BAD_REQUEST,
        )
    unsupported = sorted(tools - ALLOWED_CONTEXT_TOOLS)
    if unsupported:
        raise CodeContextLookupError(
            f"Unsupported context tool(s): {', '.join(unsupported)}",
            code="unsupported_context_tool",
            status=HTTPStatus.BAD_REQUEST,
        )
    if request.relationship_queries and "codegraph_context" not in tools:
        raise CodeContextLookupError(
            "relationship_queries require codegraph_context in allowed_context_tools.",
            code="relationship_tool_required",
            status=HTTPStatus.BAD_REQUEST,
        )
    return {"tools": sorted(tools)}


def require_relative_path(path_value: str, target_root: Path) -> str:
    rel = normalize_repo_path(path_value)
    if not rel:
        raise CodeContextLookupError("paths entries must not be empty.")
    candidate = (target_root / rel).resolve()
    try:
        candidate.relative_to(target_root)
    except ValueError as exc:
        raise CodeContextLookupError(
            f"path is outside target_root: {path_value}",
            code="target_root_not_allowed",
            status=HTTPStatus.FORBIDDEN,
        ) from exc
    return rel


def target_is_git_toplevel(target_root: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=target_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    if result.returncode != 0:
        return False
    try:
        return Path(result.stdout.strip()).resolve() == target_root.resolve()
    except OSError:
        return False


def scan_exact_matches(target_root: Path, query: str, max_results: int) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    root = target_root.resolve()
    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in IGNORED_SCAN_DIRS and not name.endswith(".egg-info") and not name.endswith(".dist-info")
        ]
        current_path = Path(current_root)
        for filename in sorted(filenames):
            path = current_path / filename
            if path.is_symlink():
                continue
            try:
                if path.stat().st_size > 1024 * 1024:
                    continue
                rel_path = path.resolve().relative_to(root).as_posix()
                text = path.read_text(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                continue
            for line_no, line in enumerate(text.splitlines(), 1):
                if query in line:
                    matches.append({"path": rel_path, "line": line_no, "text": line[:500], "source": "scan_files"})
                    if len(matches) >= max_results:
                        return matches
    return matches


def run_git_grep(target_root: Path, query: str, max_results: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not target_is_git_toplevel(target_root):
        return scan_exact_matches(target_root, query, max_results), [
            {"source": "git_grep", "reason": "target_not_git_toplevel", "fallback": "scan_files"}
        ]
    result = subprocess.run(
        ["git", "grep", "-n", "--", query],
        cwd=target_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    if result.returncode not in {0, 1}:
        return scan_exact_matches(target_root, query, max_results), [
            {"source": "git_grep", "reason": "git_grep_failed", "detail": result.stderr, "fallback": "scan_files"}
        ]
    matches: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        path, line_no, text = parts
        try:
            parsed_line = int(line_no)
        except ValueError:
            parsed_line = None
        matches.append({"path": path, "line": parsed_line, "text": text[:500], "source": "git_grep"})
        if len(matches) >= max_results:
            break
    return matches, []


def file_snippets(target_root: Path, paths: list[str], max_files: int) -> list[dict[str, Any]]:
    snippets: list[dict[str, Any]] = []
    for rel in paths[:max_files]:
        path = target_root / rel
        if not path.exists() or not path.is_file():
            snippets.append({"path": rel, "status": "missing"})
            continue
        if path.stat().st_size > 256 * 1024:
            snippets.append({"path": rel, "status": "too_large", "size_bytes": path.stat().st_size})
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        snippets.append(
            {
                "path": rel,
                "status": "read",
                "line_count": len(text.splitlines()),
                "snippet": text[:4000],
                "truncated": len(text) > 4000,
            }
        )
    return snippets


def usage_summary_requested(request: CodeContextLookupRequest) -> bool:
    if request.relationship_queries:
        return any(item.get("kind") in {"callers", "callees", "imports"} for item in request.relationship_queries)
    lowered = request.query.lower()
    return any(term in lowered for term in ("callers", "caller", "usages", "usage", "who uses", "references"))


def usage_target(request: CodeContextLookupRequest) -> str:
    for query in request.relationship_queries:
        symbol = query.get("symbol")
        module = query.get("module")
        path = query.get("path")
        if isinstance(symbol, str) and symbol.strip():
            return symbol.strip()
        if isinstance(module, str) and module.strip():
            return module.strip()
        if isinstance(path, str) and path.strip():
            return normalize_repo_path(path)
    return request.query


def relationship_usage_records(relationship_results: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(relationship_results, dict):
        return []
    records: list[dict[str, Any]] = []
    for query_result in relationship_results.get("queries", []):
        if not isinstance(query_result, dict):
            continue
        query = query_result.get("query") if isinstance(query_result.get("query"), dict) else {}
        relationship_kind = query.get("kind")
        for match in query_result.get("matches", []):
            if not isinstance(match, dict):
                continue
            path = match.get("source_path")
            if not isinstance(path, str):
                continue
            source_symbol = match.get("source_symbol")
            target_symbol = match.get("target_symbol") or match.get("module")
            line = match.get("line")
            explanation = "Relationship evidence found."
            if relationship_kind == "callers":
                explanation = f"{source_symbol or path} calls {target_symbol or query.get('symbol')}."
            elif relationship_kind == "callees":
                explanation = f"{source_symbol or query.get('symbol')} calls {target_symbol or 'a matched callee'}."
            elif relationship_kind == "imports":
                explanation = f"{path} imports {target_symbol or query.get('symbol') or query.get('module')}."
            records.append(
                {
                    "path": path,
                    "line": line if isinstance(line, int) else None,
                    "kind": relationship_kind or match.get("relationship") or "relationship",
                    "source_symbol": source_symbol,
                    "target_symbol": target_symbol,
                    "evidence": match.get("evidence"),
                    "explanation": bounded_text(explanation, 300),
                }
            )
    return records


def grep_usage_records(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for match in matches:
        path = match.get("path")
        if not isinstance(path, str):
            continue
        line = match.get("line")
        text = match.get("text")
        records.append(
            {
                "path": path,
                "line": line if isinstance(line, int) else None,
                "kind": "grep_match",
                "source_symbol": None,
                "target_symbol": None,
                "evidence": match.get("source") or "git_grep",
                "text": bounded_text(text, 300) if isinstance(text, str) else None,
                "explanation": "Exact-text usage evidence from bounded grep.",
            }
        )
    return records


def grouped_usage_summary(
    request: CodeContextLookupRequest,
    *,
    relationship_results: dict[str, Any] | None,
    grep_matches: list[dict[str, Any]],
) -> dict[str, Any]:
    if not usage_summary_requested(request):
        return {"kind": "code_context_usage_summary", "schema_version": SCHEMA_VERSION, "status": "not_requested"}
    target = usage_target(request)
    usage_records = [*relationship_usage_records(relationship_results), *grep_usage_records(grep_matches)]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in usage_records:
        path = record.get("path")
        if isinstance(path, str):
            grouped.setdefault(path, []).append(record)
    groups = [
        {
            "path": path,
            "usage_count": len(items),
            "summary": f"{path} has {len(items)} bounded usage evidence item(s) for {target}.",
            "usages": items[:20],
        }
        for path, items in sorted(grouped.items())
    ]
    if groups:
        status = "ready"
        reason = "Grouped usage evidence was found within the bounded lookup budget."
    else:
        status = "no_usages_found"
        reason = "No usage evidence was found in the bounded lookup. This does not prove absence outside the budget."
    return {
        "kind": "code_context_usage_summary",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "target": target,
        "group_count": len(groups),
        "usage_count": sum(group["usage_count"] for group in groups),
        "groups": groups,
        "gaps": [] if groups else [{"gap": "usage_absence_not_proven", "reason": reason}],
        "reason": reason,
    }


def dependency_lookup_requested(request: CodeContextLookupRequest) -> bool:
    if any(item.get("kind") == "imports" for item in request.relationship_queries):
        return True
    lowered = request.query.lower()
    return any(term in lowered for term in ("imports", "importers", "dependencies", "depends on", "module dependency"))


def dependency_target(request: CodeContextLookupRequest, paths: list[str]) -> str:
    if paths:
        return paths[0]
    for query in request.relationship_queries:
        for key in ("symbol", "module", "path"):
            value = query.get(key)
            if isinstance(value, str) and value.strip():
                return normalize_repo_path(value)
    return request.query


def ast_import_records(text: str, path: str) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    imports: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(
                    {
                        "path": path,
                        "line": node.lineno,
                        "kind": "import",
                        "module": alias.name,
                        "alias": alias.asname,
                        "source": "python_ast",
                    }
                )
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            for alias in node.names:
                imports.append(
                    {
                        "path": path,
                        "line": node.lineno,
                        "kind": "from_import",
                        "module": module,
                        "name": alias.name,
                        "alias": alias.asname,
                        "source": "python_ast",
                    }
                )
    return imports


def fallback_import_records(text: str, path: str) -> list[dict[str, Any]]:
    imports: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not re.match(r"^(?:from\s+\S+\s+import\s+.+|import\s+\S+)", stripped):
            continue
        imports.append(
            {
                "path": path,
                "line": line_no,
                "kind": "import_line",
                "module": bounded_text(stripped, 200),
                "source": "line_scan",
            }
        )
    return imports


def imports_from_snippets(snippets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    imports: list[dict[str, Any]] = []
    for snippet in snippets:
        path = snippet.get("path")
        text = snippet.get("snippet")
        if not isinstance(path, str) or not isinstance(text, str) or snippet.get("status") != "read":
            continue
        path_imports = ast_import_records(text, path) if path.endswith(".py") else []
        if not path_imports:
            path_imports = fallback_import_records(text, path)
        imports.extend(path_imports)
    seen: set[tuple[str, int | None, str, str | None]] = set()
    unique: list[dict[str, Any]] = []
    for item in imports:
        key = (
            str(item.get("path")),
            item.get("line") if isinstance(item.get("line"), int) else None,
            str(item.get("module") or ""),
            str(item.get("name")) if item.get("name") is not None else None,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:100]


def dependency_lookup_summary(
    request: CodeContextLookupRequest,
    *,
    paths: list[str],
    snippets: list[dict[str, Any]],
    grep_matches: list[dict[str, Any]],
    relationship_results: dict[str, Any] | None,
) -> dict[str, Any]:
    if not dependency_lookup_requested(request):
        return {"kind": "dependency_lookup", "schema_version": SCHEMA_VERSION, "status": "not_requested"}
    imports = imports_from_snippets(snippets)
    relationship_records = relationship_usage_records(relationship_results)
    import_relationships = [item for item in relationship_records if item.get("kind") == "imports"]
    if imports or import_relationships:
        status = "ready"
        reason = "Dependency evidence was found from readable import statements or curated import relationships."
    else:
        status = "no_dependencies_found"
        reason = "No dependency evidence was found in the bounded lookup; absence is not proven outside the budget."
    source_refs = [
        {key: value for key, value in {"path": item.get("path"), "line": item.get("line"), "source": item.get("source")}.items() if value is not None}
        for item in imports[:20]
    ]
    if not source_refs:
        source_refs = [
            {key: value for key, value in {"path": item.get("path"), "line": item.get("line"), "source": item.get("evidence")}.items() if value is not None}
            for item in import_relationships[:20]
        ]
    return {
        "kind": "dependency_lookup",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "target": dependency_target(request, paths),
        "import_count": len(imports),
        "imports": imports[:50],
        "relationship_count": len(import_relationships),
        "relationships": import_relationships[:20],
        "grep_match_count": len(grep_matches),
        "source_refs": source_refs,
        "mutation_policy": "read_only_no_source_mutation",
        "gaps": [] if status == "ready" else [{"gap": "dependency_absence_not_proven", "reason": reason}],
        "reason": reason,
    }


def structure_slice(target_root: Path, paths: list[str], max_results: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    try:
        index = build_code_structure_index(target_root=target_root, file_scope="tracked")
    except Exception as exc:  # noqa: BLE001 - copied validation trees may not be Git repos
        index = build_code_structure_index(target_root=target_root, file_scope="all")
        warnings.append(
            {"source": "structure_index", "reason": "tracked_scope_unavailable", "detail": str(exc), "fallback": "all"}
        )
    return build_index_slice(index, paths=paths or None, max_records=max_results), warnings


def invoke_code_context_lookup(request: CodeContextLookupRequest) -> InvocationResult:
    validation = validate_request_basics(request)
    target_root = Path(request.target_root).resolve()
    output_root = Path(request.output_root).resolve()
    run_id = f"code-context-{artifact_timestamp()}"
    run_dir = output_root / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    paths = [require_relative_path(path, target_root) for path in request.paths]
    artifacts: dict[str, str] = {}
    warnings: list[dict[str, Any]] = []
    tools = set(validation["tools"])

    request_artifact = {
        "kind": "code_context_lookup_request",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "target_root": str(target_root),
        "query": request.query,
        "paths": paths,
        "allowed_context_tools": sorted(tools),
        "created_at": utc_now(),
    }
    write_json(run_dir / "request.json", request_artifact)
    artifacts["request"] = str(run_dir / "request.json")

    results: dict[str, Any] = {
        "kind": "code_context_lookup_results",
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "target_root": str(target_root),
        "query": request.query,
        "paths": paths,
        "structure": None,
        "grep_matches": [],
        "file_snippets": [],
        "relationship_results": None,
        "usage_summary": None,
        "dependency_lookup": None,
        "warnings": warnings,
    }
    if request.include_structure and "structure_index" in tools:
        results["structure"], structure_warnings = structure_slice(target_root, paths, request.max_results)
        warnings.extend(structure_warnings)
    if request.include_grep and "git_grep" in tools:
        matches, grep_warnings = run_git_grep(target_root, request.query, request.max_results)
        results["grep_matches"] = matches
        warnings.extend(grep_warnings)
    if request.include_file_snippets and paths and "read_file" in tools:
        results["file_snippets"] = file_snippets(target_root, paths, request.max_files)
    if request.relationship_queries and "codegraph_context" in tools:
        try:
            relationship_results, relationship_warnings = run_relationship_queries(
                target_root,
                request.relationship_queries,
                max_results=request.max_results,
            )
        except CodeGraphContextAdapterError as exc:
            raise CodeContextLookupError(
                str(exc),
                code="invalid_relationship_query",
                status=HTTPStatus.BAD_REQUEST,
            ) from exc
        results["relationship_results"] = relationship_results
        warnings.extend(relationship_warnings)
    usage_summary = grouped_usage_summary(
        request,
        relationship_results=results["relationship_results"] if isinstance(results["relationship_results"], dict) else None,
        grep_matches=results["grep_matches"],
    )
    results["usage_summary"] = usage_summary
    if usage_summary.get("status") != "not_requested":
        write_json(run_dir / "usage-summary.json", usage_summary)
        artifacts["usage_summary"] = str(run_dir / "usage-summary.json")
    dependency_lookup = dependency_lookup_summary(
        request,
        paths=paths,
        snippets=results["file_snippets"],
        grep_matches=results["grep_matches"],
        relationship_results=results["relationship_results"] if isinstance(results["relationship_results"], dict) else None,
    )
    results["dependency_lookup"] = dependency_lookup
    if dependency_lookup.get("status") != "not_requested":
        write_json(run_dir / "dependency-lookup.json", dependency_lookup)
        artifacts["dependency_lookup"] = str(run_dir / "dependency-lookup.json")

    summary = {
        "query": request.query,
        "target_root": str(target_root),
        "path_count": len(paths),
        "grep_match_count": len(results["grep_matches"]),
        "snippet_count": len(results["file_snippets"]),
        "relationship_query_count": (
            results["relationship_results"].get("query_count")
            if isinstance(results["relationship_results"], dict)
            else 0
        ),
        "relationship_result_count": (
            sum(
                item.get("returned_count", 0)
                for item in results["relationship_results"].get("queries", [])
                if isinstance(item, dict)
            )
            if isinstance(results["relationship_results"], dict)
            else 0
        ),
        "usage_summary_status": usage_summary.get("status"),
        "usage_group_count": usage_summary.get("group_count", 0),
        "usage_count": usage_summary.get("usage_count", 0),
        "dependency_lookup_status": dependency_lookup.get("status"),
        "dependency_import_count": dependency_lookup.get("import_count", 0),
        "warning_count": len(warnings),
    }
    write_json(run_dir / "lookup-results.json", results)
    artifacts["lookup_results"] = str(run_dir / "lookup-results.json")
    if isinstance(results["relationship_results"], dict):
        write_json(run_dir / "relationship-results.json", results["relationship_results"])
        artifacts["relationship_results"] = str(run_dir / "relationship-results.json")
    run_state = {
        "kind": "code_context_lookup_run_state",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "target_root": str(target_root),
        "summary": summary,
        "artifacts": artifacts,
        "updated_at": utc_now(),
    }
    write_json(run_dir / "run-state.json", run_state)
    artifacts["run_state"] = str(run_dir / "run-state.json")
    report = {
        "kind": "code_context_lookup_report",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "summary": summary,
        "warnings": warnings,
        "artifacts": artifacts,
    }
    return InvocationResult(
        workflow=WORKFLOW_ID,
        status=WorkflowStatus.COMPLETED,
        artifact_paths=artifacts,
        summary_text=f"{WORKFLOW_ID} completed: {summary['grep_match_count']} grep match(es)",
        failures=[],
        resume_key={"schema_version": SCHEMA_VERSION, "run_state": str(run_dir / "run-state.json")},
        report=report,
        run_id=run_id,
    )
