"""Curated read-only relationship lookup for code context.

This is intentionally not a raw CodeGraphContext/MCP bridge. It exposes a small
controller-owned relationship schema and derives the first slice from Python AST
source analysis plus the existing structure index.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vllm_agent_gateway.structure_index.indexer import build_code_structure_index


ADAPTER_ID = "curated_codegraph_context"
ALLOWED_RELATIONSHIP_KINDS = {"callers", "callees", "imports"}
MAX_RELATIONSHIP_QUERIES = 8
DEFAULT_QUERY_LIMIT = 25


@dataclass(frozen=True)
class RelationshipQuery:
    kind: str
    symbol: str | None = None
    path: str | None = None
    module: str | None = None
    max_results: int = DEFAULT_QUERY_LIMIT


class CodeGraphContextAdapterError(RuntimeError):
    """Raised when a curated relationship query is invalid."""


def bounded_text(value: Any, limit: int = 500) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def normalize_repo_path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def validate_relative_path(path_value: str, target_root: Path) -> str:
    rel = normalize_repo_path(path_value)
    if not rel:
        raise CodeGraphContextAdapterError("relationship_queries.path must not be empty.")
    candidate = (target_root / rel).resolve()
    try:
        candidate.relative_to(target_root)
    except ValueError as exc:
        raise CodeGraphContextAdapterError(f"relationship_queries.path is outside target_root: {path_value}") from exc
    return rel


def int_limit(value: Any, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 100:
        raise CodeGraphContextAdapterError("relationship_queries.max_results must be an integer from 1 through 100.")
    return value


def normalize_relationship_queries(
    raw_queries: list[dict[str, Any]],
    *,
    target_root: Path,
    default_limit: int,
) -> list[RelationshipQuery]:
    if len(raw_queries) > MAX_RELATIONSHIP_QUERIES:
        raise CodeGraphContextAdapterError(f"relationship_queries may contain at most {MAX_RELATIONSHIP_QUERIES} entries.")
    queries: list[RelationshipQuery] = []
    allowed_fields = {"kind", "symbol", "path", "module", "max_results"}
    for index, raw_query in enumerate(raw_queries):
        unknown = sorted(set(raw_query) - allowed_fields)
        if unknown:
            raise CodeGraphContextAdapterError(
                f"relationship_queries[{index}] has unsupported field(s): {', '.join(unknown)}"
            )
        kind = raw_query.get("kind")
        if not isinstance(kind, str) or kind not in ALLOWED_RELATIONSHIP_KINDS:
            raise CodeGraphContextAdapterError(
                f"relationship_queries[{index}].kind must be one of: {', '.join(sorted(ALLOWED_RELATIONSHIP_KINDS))}."
            )
        symbol = raw_query.get("symbol")
        if symbol is not None and (not isinstance(symbol, str) or not symbol.strip()):
            raise CodeGraphContextAdapterError(f"relationship_queries[{index}].symbol must be a non-empty string.")
        module = raw_query.get("module")
        if module is not None and (not isinstance(module, str) or not module.strip()):
            raise CodeGraphContextAdapterError(f"relationship_queries[{index}].module must be a non-empty string.")
        path = raw_query.get("path")
        rel_path = validate_relative_path(path, target_root) if isinstance(path, str) else None
        if kind in {"callers", "callees"} and not (symbol or rel_path):
            raise CodeGraphContextAdapterError(
                f"relationship_queries[{index}] requires symbol or path for {kind}."
            )
        if kind == "imports" and not (symbol or module or rel_path):
            raise CodeGraphContextAdapterError(
                f"relationship_queries[{index}] requires symbol, module, or path for imports."
            )
        queries.append(
            RelationshipQuery(
                kind=kind,
                symbol=symbol.strip() if isinstance(symbol, str) else None,
                path=rel_path,
                module=module.strip() if isinstance(module, str) else None,
                max_results=int_limit(raw_query.get("max_results"), default_limit),
            )
        )
    return queries


def expression_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = expression_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return expression_name(node.func)
    try:
        return ast.unparse(node)
    except Exception:
        return None


def simple_name(value: str) -> str:
    return value.rsplit(".", 1)[-1]


def symbol_matches(candidate: str | None, target: str | None) -> bool:
    if not candidate or not target:
        return False
    candidate_simple = simple_name(candidate)
    target_simple = simple_name(target)
    return candidate == target or candidate.endswith(f".{target}") or candidate_simple == target_simple


def module_name_from_path(path: str) -> str:
    without_suffix = Path(path).with_suffix("").as_posix()
    parts = [part for part in without_suffix.split("/") if part and part != "__init__"]
    return ".".join(parts) or Path(path).stem


class CallCollector(ast.NodeVisitor):
    def __init__(self, path: str):
        self.path = path
        self.module = module_name_from_path(path)
        self.scope_stack: list[str] = [self.module]
        self.class_stack: list[str] = []
        self.calls: list[dict[str, Any]] = []
        self.symbols: list[dict[str, Any]] = []

    @property
    def scope(self) -> str:
        return self.scope_stack[-1]

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        qualified = ".".join([self.module, *self.class_stack, node.name])
        self.symbols.append(
            {
                "path": self.path,
                "kind": "class",
                "name": node.name,
                "qualified_name": qualified,
                "line_range": [node.lineno, getattr(node, "end_lineno", node.lineno) or node.lineno],
            }
        )
        self.class_stack.append(node.name)
        self.scope_stack.append(qualified)
        self.generic_visit(node)
        self.scope_stack.pop()
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._visit_function(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._visit_function(node, "async_function")

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, kind: str) -> None:
        qualified = ".".join([self.module, *self.class_stack, node.name])
        self.symbols.append(
            {
                "path": self.path,
                "kind": kind,
                "name": node.name,
                "qualified_name": qualified,
                "line_range": [node.lineno, getattr(node, "end_lineno", node.lineno) or node.lineno],
            }
        )
        self.scope_stack.append(qualified)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_Call(self, node: ast.Call) -> Any:
        callee = expression_name(node.func)
        self.calls.append(
            {
                "path": self.path,
                "line": node.lineno,
                "caller": self.scope,
                "callee": bounded_text(callee, 300) if callee else None,
                "callee_name": simple_name(callee) if callee else None,
            }
        )
        self.generic_visit(node)


def collect_python_relationship_source(target_root: Path, index: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []
    symbols: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    files = index.get("files") if isinstance(index.get("files"), list) else []
    for file_record in files:
        if not isinstance(file_record, dict) or file_record.get("suffix") != ".py":
            continue
        path = file_record.get("path")
        if not isinstance(path, str):
            continue
        raw_imports = file_record.get("imports") if isinstance(file_record.get("imports"), list) else []
        for item in raw_imports:
            if isinstance(item, dict):
                imports.append({"path": path, **item})
        if file_record.get("status") != "indexed":
            continue
        try:
            text = (target_root / path).read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text, filename=path)
        except (OSError, SyntaxError) as exc:
            warnings.append({"source": ADAPTER_ID, "reason": "python_parse_unavailable", "path": path, "detail": str(exc)})
            continue
        collector = CallCollector(path)
        collector.visit(tree)
        calls.extend(collector.calls)
        symbols.extend(collector.symbols)
    return calls, symbols, imports, warnings


def query_as_dict(query: RelationshipQuery) -> dict[str, Any]:
    return {
        "kind": query.kind,
        "symbol": query.symbol,
        "path": query.path,
        "module": query.module,
        "max_results": query.max_results,
    }


def apply_limit(matches: list[dict[str, Any]], limit: int) -> tuple[list[dict[str, Any]], bool]:
    return matches[:limit], len(matches) > limit


def caller_matches(query: RelationshipQuery, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches = [
        {
            "relationship": "calls",
            "source_path": call.get("path"),
            "source_symbol": call.get("caller"),
            "target_symbol": call.get("callee"),
            "line": call.get("line"),
            "evidence": "python_ast_call",
        }
        for call in calls
        if symbol_matches(call.get("callee"), query.symbol) or symbol_matches(call.get("callee_name"), query.symbol)
    ]
    return sorted(matches, key=lambda item: (str(item.get("source_path")), int(item.get("line") or 0)))


def callee_matches(query: RelationshipQuery, calls: list[dict[str, Any]], symbols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    target_scopes: set[str] = set()
    if query.symbol:
        for symbol in symbols:
            if query.path and symbol.get("path") != query.path:
                continue
            if symbol_matches(symbol.get("qualified_name"), query.symbol) or symbol_matches(symbol.get("name"), query.symbol):
                qualified = symbol.get("qualified_name")
                if isinstance(qualified, str):
                    target_scopes.add(qualified)
    matches = []
    for call in calls:
        if query.path and call.get("path") != query.path:
            continue
        if target_scopes and call.get("caller") not in target_scopes:
            continue
        if query.symbol and not target_scopes and not symbol_matches(call.get("caller"), query.symbol):
            continue
        matches.append(
            {
                "relationship": "calls",
                "source_path": call.get("path"),
                "source_symbol": call.get("caller"),
                "target_symbol": call.get("callee"),
                "line": call.get("line"),
                "evidence": "python_ast_call",
            }
        )
    return sorted(matches, key=lambda item: (str(item.get("source_path")), int(item.get("line") or 0), str(item.get("target_symbol"))))


def import_matches(query: RelationshipQuery, imports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for item in imports:
        if query.path and item.get("path") != query.path:
            continue
        module = item.get("module")
        names = item.get("names") if isinstance(item.get("names"), list) else []
        imported_names = [name.get("name") for name in names if isinstance(name, dict) and isinstance(name.get("name"), str)]
        if query.module and not (isinstance(module, str) and (module == query.module or module.endswith(f".{query.module}"))):
            continue
        if query.symbol and not any(symbol_matches(name, query.symbol) for name in imported_names):
            continue
        matches.append(
            {
                "relationship": "imports",
                "source_path": item.get("path"),
                "module": module,
                "names": imported_names,
                "line": item.get("line"),
                "evidence": "python_ast_import",
            }
        )
    return sorted(matches, key=lambda record: (str(record.get("source_path")), int(record.get("line") or 0)))


def run_relationship_queries(
    target_root: Path,
    raw_queries: list[dict[str, Any]],
    *,
    max_results: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    target_root = target_root.resolve()
    queries = normalize_relationship_queries(raw_queries, target_root=target_root, default_limit=max_results)
    warnings: list[dict[str, Any]] = []
    try:
        index = build_code_structure_index(target_root=target_root, file_scope="tracked")
        file_scope = "tracked"
    except Exception as exc:  # noqa: BLE001 - copied validation trees may not be Git repos
        index = build_code_structure_index(target_root=target_root, file_scope="all")
        file_scope = "all"
        warnings.append({"source": ADAPTER_ID, "reason": "tracked_scope_unavailable", "detail": str(exc), "fallback": "all"})
    calls, symbols, imports, source_warnings = collect_python_relationship_source(target_root, index)
    warnings.extend(source_warnings)

    query_results: list[dict[str, Any]] = []
    for query in queries:
        if query.kind == "callers":
            matches = caller_matches(query, calls)
        elif query.kind == "callees":
            matches = callee_matches(query, calls, symbols)
        else:
            matches = import_matches(query, imports)
        selected, truncated = apply_limit(matches, query.max_results)
        query_results.append(
            {
                "query": query_as_dict(query),
                "match_count": len(matches),
                "returned_count": len(selected),
                "truncated": truncated,
                "matches": selected,
            }
        )
    results = {
        "kind": "codegraph_context_relationship_results",
        "schema_version": 1,
        "adapter": ADAPTER_ID,
        "source": "python_ast_relationships",
        "target_root": str(target_root),
        "file_scope": file_scope,
        "query_count": len(query_results),
        "queries": query_results,
        "warnings": warnings,
    }
    return results, warnings
