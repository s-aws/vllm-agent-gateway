"""Controller-owned read-only code investigation workflow."""

from __future__ import annotations

import ast
import json
import re
import subprocess
from dataclasses import dataclass, field, fields
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.controllers.code_context.lookup import (
    ALLOWED_CONTEXT_TOOLS as CODE_CONTEXT_ALLOWED_CONTEXT_TOOLS,
    DEFAULT_CONTEXT_TOOLS,
    FORBIDDEN_CONTEXT_TERMS,
    artifact_timestamp,
    file_snippets,
    require_relative_path,
    run_git_grep,
    structure_slice,
    utc_now,
    write_json,
)
from vllm_agent_gateway.controllers.natural_query import (
    change_subject_queries_from_request,
    configuration_queries_from_request,
)
from vllm_agent_gateway.controllers.verification import (
    controller_verification_commands,
    discover_related_tests_from_values,
)
from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus


WORKFLOW_ID = "code_investigation.plan"
SCHEMA_VERSION = 1
DEFAULT_OUTPUT_DIR = "code-investigation"
DEFAULT_MAX_RESULTS = 50
DEFAULT_MAX_FILES = 10
TABLE_ACCESS_SCAN_FILE_LIMIT = 500
TABLE_ACCESS_SCAN_EXTENSIONS = {".go", ".js", ".jsx", ".py", ".sql", ".ts", ".tsx"}
MAX_QUERY_COUNT = 8
ALLOWED_CONTEXT_TOOLS = CODE_CONTEXT_ALLOWED_CONTEXT_TOOLS - {"codegraph_context"}
IGNORED_SCAN_DIRS = {
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
    "runtime-state",
    "vendor",
}


class CodeInvestigationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "code_investigation_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class CodeInvestigationRequest:
    config_root: Path | str = "."
    target_root: Path | str = "."
    output_root: Path | str = ".agentic_controller"
    workflow: str = WORKFLOW_ID
    schema_version: int = SCHEMA_VERSION
    user_request: str = ""
    behavior: str = ""
    entrypoint_hints: list[dict[str, Any]] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    allowed_context_tools: list[str] = field(default_factory=lambda: list(DEFAULT_CONTEXT_TOOLS))
    max_results: int = DEFAULT_MAX_RESULTS
    max_files: int = DEFAULT_MAX_FILES
    include_tests: bool = True
    include_structure: bool = True
    include_grep: bool = True
    include_file_snippets: bool = True

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        config_root: Path,
        target_root: Path,
        output_root: Path,
    ) -> "CodeInvestigationRequest":
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


def bounded_text(value: Any, limit: int = 500) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def append_unique(values: list[str], candidate: str, *, limit: int | None = None) -> None:
    item = candidate.strip()
    if not item or item in values:
        return
    if limit is not None and len(values) >= limit:
        return
    values.append(item)


def validate_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CodeInvestigationError(f"{label} must be a list of strings.")
    return value


def validate_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise CodeInvestigationError(f"{label} must be a boolean.")
    return value


def raw_codegraph_forbidden(value: dict[str, Any]) -> bool:
    raw_text = json.dumps(value, ensure_ascii=True).lower()
    return any(term in raw_text for term in FORBIDDEN_CONTEXT_TERMS)


def validate_request_basics(request: CodeInvestigationRequest) -> dict[str, Any]:
    if request.workflow != WORKFLOW_ID:
        raise CodeInvestigationError("workflow must be code_investigation.plan.", code="unsupported_workflow")
    if request.schema_version != SCHEMA_VERSION:
        raise CodeInvestigationError("schema_version must be 1.")
    if not Path(request.target_root).resolve().is_dir():
        raise CodeInvestigationError("target_root must be an existing directory.")
    if not isinstance(request.user_request, str):
        raise CodeInvestigationError("user_request must be a string.")
    if not isinstance(request.behavior, str):
        raise CodeInvestigationError("behavior must be a string.")
    if not isinstance(request.entrypoint_hints, list) or not all(
        isinstance(item, dict) for item in request.entrypoint_hints
    ):
        raise CodeInvestigationError("entrypoint_hints must be a list of objects.")
    validate_string_list(request.queries, "queries")
    validate_string_list(request.paths, "paths")
    validate_string_list(request.allowed_context_tools, "allowed_context_tools")
    validate_bool(request.include_tests, "include_tests")
    validate_bool(request.include_structure, "include_structure")
    validate_bool(request.include_grep, "include_grep")
    validate_bool(request.include_file_snippets, "include_file_snippets")
    if not isinstance(request.max_results, int) or isinstance(request.max_results, bool) or not 1 <= request.max_results <= 200:
        raise CodeInvestigationError("max_results must be an integer from 1 through 200.")
    if not isinstance(request.max_files, int) or isinstance(request.max_files, bool) or not 1 <= request.max_files <= 30:
        raise CodeInvestigationError("max_files must be an integer from 1 through 30.")

    if raw_codegraph_forbidden(
        {
            "user_request": request.user_request,
            "behavior": request.behavior,
            "entrypoint_hints": request.entrypoint_hints,
            "queries": request.queries,
            "paths": request.paths,
            "allowed_context_tools": request.allowed_context_tools,
        }
    ):
        raise CodeInvestigationError(
            "Raw CodeGraphContext operations are not allowed for code_investigation.plan.",
            code="raw_codegraph_not_allowed",
            status=HTTPStatus.BAD_REQUEST,
        )

    tools = set(request.allowed_context_tools)
    unsupported = sorted(tools - ALLOWED_CONTEXT_TOOLS)
    if unsupported:
        raise CodeInvestigationError(
            f"Unsupported context tool(s): {', '.join(unsupported)}",
            code="unsupported_context_tool",
            status=HTTPStatus.BAD_REQUEST,
        )
    if not (
        request.user_request.strip()
        or request.behavior.strip()
        or request.queries
        or request.paths
        or request.entrypoint_hints
    ):
        raise CodeInvestigationError("At least one of user_request, behavior, queries, paths, or entrypoint_hints is required.")
    return {"tools": sorted(tools)}


def normalize_entrypoint_hints(
    request: CodeInvestigationRequest,
    target_root: Path,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, hint in enumerate(request.entrypoint_hints):
        path_value = hint.get("path")
        symbol = hint.get("symbol")
        reason = hint.get("reason")
        if path_value is not None and not isinstance(path_value, str):
            raise CodeInvestigationError(f"entrypoint_hints[{index}].path must be a string when present.")
        if symbol is not None and not isinstance(symbol, str):
            raise CodeInvestigationError(f"entrypoint_hints[{index}].symbol must be a string or null.")
        if reason is not None and not isinstance(reason, str):
            raise CodeInvestigationError(f"entrypoint_hints[{index}].reason must be a string when present.")
        rel_path = require_relative_path(path_value, target_root) if isinstance(path_value, str) else None
        exists = bool(rel_path and (target_root / rel_path).is_file())
        normalized.append(
            {
                "path": rel_path,
                "symbol": symbol.strip() if isinstance(symbol, str) and symbol.strip() else None,
                "reason": bounded_text(reason, 500) if isinstance(reason, str) and reason.strip() else None,
                "status": "exists" if exists else "missing" if rel_path else "symbol_only",
            }
        )
    return normalized


def extract_query_terms(text: str) -> list[str]:
    candidates: list[str] = []
    for pattern in (r"`([^`]{3,120})`", r'"([^"]{3,120})"', r"'([^']{3,120})'"):
        for match in re.finditer(pattern, text):
            append_unique(candidates, match.group(1), limit=MAX_QUERY_COUNT)
    for match in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]{3,}\b", text):
        token = match.group(0)
        if "_" in token or any(char.isupper() for char in token[1:]):
            append_unique(candidates, token, limit=MAX_QUERY_COUNT)
    return candidates


def query_candidates(request: CodeInvestigationRequest, hints: list[dict[str, Any]]) -> list[str]:
    candidates: list[str] = []
    if is_change_surface_summary_request(request.user_request):
        for query in change_subject_queries_from_request(request.user_request, limit=MAX_QUERY_COUNT):
            append_unique(candidates, query, limit=MAX_QUERY_COUNT)
    if is_configuration_lookup_request(request.user_request) or is_configuration_effect_summary_request(request.user_request):
        for query in configuration_queries_from_request(request.user_request, limit=MAX_QUERY_COUNT):
            append_unique(candidates, query, limit=MAX_QUERY_COUNT)
    for query in request.queries:
        append_unique(candidates, query, limit=MAX_QUERY_COUNT)
    append_unique(candidates, request.behavior, limit=MAX_QUERY_COUNT)
    for hint in hints:
        symbol = hint.get("symbol")
        if isinstance(symbol, str):
            append_unique(candidates, symbol, limit=MAX_QUERY_COUNT)
    for query in extract_query_terms(request.user_request):
        append_unique(candidates, query, limit=MAX_QUERY_COUNT)
    return candidates


def category_for_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    name = Path(normalized).name
    if normalized.startswith("tests/") or "/tests/" in normalized or name.startswith("test_") or name.endswith("_test.py"):
        return "test"
    if normalized.endswith((".md", ".rst", ".txt")):
        return "documentation"
    if normalized.endswith((".json", ".yaml", ".yml", ".toml", ".ini")):
        return "configuration"
    return "source"


def file_record_sort_key(record: dict[str, Any]) -> tuple[int, int, str]:
    category_priority = {"source": 0, "configuration": 1, "documentation": 2, "test": 3}
    return (
        0 if record.get("hinted") else 1,
        category_priority.get(str(record.get("category")), 9),
        str(record.get("path", "")),
    )


def collect_grep_matches(
    target_root: Path,
    queries: list[str],
    max_results: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    matches: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not queries:
        return matches, warnings
    per_query = max(1, max_results // len(queries))
    for query in queries:
        remaining = max_results - len(matches)
        if remaining <= 0:
            break
        query_matches, query_warnings = run_git_grep(target_root, query, min(per_query, remaining))
        for warning in query_warnings:
            warnings.append({"query": query, **warning})
        for match in query_matches:
            matches.append({"query": query, **match, "category": category_for_path(str(match.get("path", "")))})
            if len(matches) >= max_results:
                break
    return matches, warnings


def collect_paths(
    request: CodeInvestigationRequest,
    target_root: Path,
    hints: list[dict[str, Any]],
    matches: list[dict[str, Any]],
) -> list[str]:
    selected: list[str] = []
    for path in request.paths:
        append_unique(selected, require_relative_path(path, target_root), limit=request.max_files)
    for hint in hints:
        path = hint.get("path")
        if isinstance(path, str):
            append_unique(selected, path, limit=request.max_files)
    for match in matches:
        path = match.get("path")
        if isinstance(path, str):
            append_unique(selected, path, limit=request.max_files)
    return selected


def evidence_file_records(
    paths: list[str],
    hints: list[dict[str, Any]],
    matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for path in paths:
        records[path] = {
            "path": path,
            "category": category_for_path(path),
            "hinted": False,
            "queries": [],
            "match_count": 0,
            "line_refs": [],
        }
    for hint in hints:
        path = hint.get("path")
        if isinstance(path, str):
            records.setdefault(
                path,
                {
                    "path": path,
                    "category": category_for_path(path),
                    "hinted": False,
                    "queries": [],
                    "match_count": 0,
                    "line_refs": [],
                },
            )
            records[path]["hinted"] = True
            if hint.get("symbol"):
                append_unique(records[path]["queries"], str(hint["symbol"]))
    for match in matches:
        path = match.get("path")
        if not isinstance(path, str):
            continue
        records.setdefault(
            path,
            {
                "path": path,
                "category": category_for_path(path),
                "hinted": False,
                "queries": [],
                "match_count": 0,
                "line_refs": [],
            },
        )
        records[path]["match_count"] += 1
        query = match.get("query")
        if isinstance(query, str):
            append_unique(records[path]["queries"], query)
        line = match.get("line")
        if isinstance(line, int):
            records[path]["line_refs"].append({"line": line, "query": query, "source": match.get("source")})
    ordered = sorted(records.values(), key=file_record_sort_key)
    for record in ordered:
        record["queries"] = sorted(record["queries"])
        record["line_refs"] = record["line_refs"][:10]
    return ordered


def likely_beginning_point(records: list[dict[str, Any]], hints: list[dict[str, Any]]) -> dict[str, Any]:
    for hint in hints:
        if hint.get("status") == "exists" and isinstance(hint.get("path"), str):
            return {
                "status": "hinted",
                "path": hint["path"],
                "symbol": hint.get("symbol"),
                "reason": hint.get("reason") or "Explicit entrypoint hint was supplied.",
            }
    source_records = [record for record in records if record.get("category") == "source" and record.get("match_count")]
    if source_records:
        record = source_records[0]
        first_line = record.get("line_refs", [{}])[0] if isinstance(record.get("line_refs"), list) else {}
        return {
            "status": "match_based",
            "path": record.get("path"),
            "line": first_line.get("line"),
            "reason": "First source file with bounded exact-text evidence.",
        }
    if records:
        record = records[0]
        return {
            "status": "path_only",
            "path": record.get("path"),
            "reason": "No source match was found; using the first selected path as the investigation start.",
        }
    return {"status": "insufficient_evidence", "reason": "No entrypoint hint, selected path, or grep match was found."}


def multiple_path_assessment(records: list[dict[str, Any]]) -> dict[str, Any]:
    source_records = [
        record
        for record in records
        if record.get("category") == "source" and (record.get("hinted") or int(record.get("match_count") or 0) > 0)
    ]
    source_paths = [str(record["path"]) for record in source_records if isinstance(record.get("path"), str)]
    if len(source_paths) > 1:
        return {
            "status": "possible_multiple_paths",
            "confidence": "low",
            "source_file_count": len(source_paths),
            "source_files": source_paths,
            "reason": "The same behavior terms appear in more than one source file. This is a refactor risk, not proof of duplication.",
        }
    if len(source_paths) == 1:
        return {
            "status": "single_source_path_observed",
            "confidence": "medium",
            "source_file_count": 1,
            "source_files": source_paths,
            "reason": "Only one source file was found in bounded evidence. This does not prove uniqueness outside the budget.",
        }
    return {
        "status": "insufficient_source_evidence",
        "confidence": "low",
        "source_file_count": 0,
        "source_files": [],
        "reason": "No source file evidence was found in the bounded investigation.",
    }


def is_multi_file_behavior_investigation_request(text: str) -> bool:
    lowered = text.lower()
    if any(term in lowered for term in ("fix failing", "fix this test", "fix test", "update test", "apply", "mutate")):
        return False
    if is_request_flow_map_request(text):
        return False
    if any(term in lowered for term in ("dependency impact", "impact summary", "impact scan", "impacted files")):
        return False
    investigation_terms = ("investigate", "trace", "map", "summarize")
    multi_file_terms = (
        "multi-file",
        "multi file",
        "across source files",
        "across files",
        "participating files",
        "call chain",
        "callers/usages",
        "callers and usages",
        "usage evidence",
        "flows across",
    )
    read_only_terms = ("read only", "read-only", "do not edit", "do not mutate", "no source changes")
    return (
        any(term in lowered for term in investigation_terms)
        and any(term in lowered for term in multi_file_terms)
        and any(term in lowered for term in read_only_terms)
    )


def is_dependency_impact_summary_request(text: str) -> bool:
    lowered = text.lower()
    if any(term in lowered for term in ("fix failing", "fix this test", "fix test", "update test", "apply", "mutate")):
        return False
    if is_change_surface_summary_request(text):
        return False
    impact_terms = (
        "dependency impact",
        "impact summary",
        "impact scan",
        "impacted files",
        "what is impacted",
        "what would be impacted",
    )
    change_terms = ("behavior changes", "change", "changes", "changed", "proposed change")
    read_only_terms = ("read only", "read-only", "do not edit", "do not mutate", "no source changes")
    return (
        any(term in lowered for term in impact_terms)
        and any(term in lowered for term in change_terms)
        and any(term in lowered for term in read_only_terms)
    )


def is_test_selection_plan_request(text: str) -> bool:
    lowered = text.lower()
    if any(term in lowered for term in ("run the test", "run tests", "execute tests", "fix failing", "fix test", "apply", "mutate")):
        return False
    selection_terms = (
        "test selection",
        "choose the smallest",
        "smallest, medium, and broad",
        "smallest medium and broad",
        "validation commands",
        "validation command tiers",
        "test command tiers",
    )
    rationale_terms = (
        "rationale",
        "why each command",
        "why that command",
        "why each command matters",
        "command matters",
        "risk it covers",
        "what risk remains",
        "gaps remain",
        "confidence",
    )
    read_only_terms = ("read only", "read-only", "do not edit", "do not mutate", "no source changes")
    return (
        any(term in lowered for term in selection_terms)
        and any(term in lowered for term in rationale_terms)
        and any(term in lowered for term in read_only_terms)
    )


def is_runtime_error_diagnosis_request(text: str) -> bool:
    lowered = text.lower()
    if any(term in lowered for term in ("fix failing", "fix this test", "fix test", "update test", "apply", "mutate", "refactor")):
        return False
    if is_reproduction_checklist_request(text):
        return True
    runtime_terms = ("runtime error", "stack trace", "traceback", "exception")
    diagnosis_terms = ("diagnose", "observed error", "likely cause", "next inspection", "why")
    read_only_terms = ("read only", "read-only", "do not edit", "do not mutate", "no source changes")
    return (
        any(term in lowered for term in runtime_terms)
        and any(term in lowered for term in diagnosis_terms)
        and any(term in lowered for term in read_only_terms)
    )


def is_reproduction_checklist_request(text: str) -> bool:
    lowered = text.lower()
    if any(term in lowered for term in ("fix failing", "fix this test", "fix test", "update test", "apply", "mutate", "refactor")):
        return False
    runtime_terms = ("runtime error", "stack trace", "traceback", "exception")
    repro_terms = (
        "minimal reproduction checklist",
        "reproduction checklist",
        "repro checklist",
        "minimal repro",
        "turn this stack trace",
        "reproduce",
    )
    read_only_terms = ("read only", "read-only", "do not edit", "do not mutate", "no source changes")
    return any(term in lowered for term in runtime_terms) and any(term in lowered for term in repro_terms) and any(
        term in lowered for term in read_only_terms
    )


def is_request_flow_map_request(text: str) -> bool:
    lowered = text.lower()
    if any(term in lowered for term in ("fix failing", "fix this test", "fix test", "update test", "apply", "mutate", "refactor")):
        return False
    flow_terms = ("request flow", "data flow", "message flow", "map the request", "map request", "flow steps")
    output_terms = ("flow steps", "participating files", "risks", "gaps", "verification")
    read_only_terms = ("read only", "read-only", "do not edit", "do not mutate", "no source changes")
    return (
        any(term in lowered for term in flow_terms)
        and any(term in lowered for term in output_terms)
        and any(term in lowered for term in read_only_terms)
    )


def is_code_path_comparison_request(text: str) -> bool:
    lowered = text.lower()
    if any(term in lowered for term in ("fix failing", "fix this test", "fix test", "update test", "apply", "mutate", "refactor")):
        return False
    comparison_terms = ("compare two candidate", "compare the", "candidate code paths", "candidate paths", "compare code paths")
    path_terms = ("path", "code path", "lookup path", "index path")
    read_only_terms = ("read only", "read-only", "do not edit", "do not mutate", "no source changes")
    return (
        any(term in lowered for term in comparison_terms)
        and any(term in lowered for term in path_terms)
        and any(term in lowered for term in read_only_terms)
    )


def is_change_surface_summary_request(text: str) -> bool:
    lowered = text.lower()
    if any(term in lowered for term in ("fix failing", "fix this test", "fix test", "update test", "apply", "mutate", "refactor")):
        return False
    surface_terms = (
        "minimal safe change surface",
        "change surface",
        "files that would need review",
        "files need review",
        "files needing review",
    )
    stop_terms = ("stop before implementation", "before implementation", "read only", "read-only")
    return any(term in lowered for term in surface_terms) and any(term in lowered for term in stop_terms)


def usage_evidence_from_records(
    records: list[dict[str, Any]],
    beginning: dict[str, Any],
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    beginning_path = beginning.get("path") if isinstance(beginning.get("path"), str) else None
    source_records = [
        record
        for record in records
        if record.get("category") == "source" and isinstance(record.get("path"), str)
    ]
    matched_records = [record for record in source_records if int(record.get("match_count") or 0) > 0]
    candidates = matched_records or source_records
    evidence: list[dict[str, Any]] = []
    for record in candidates[:limit]:
        path = str(record["path"])
        line_refs = record.get("line_refs") if isinstance(record.get("line_refs"), list) else []
        evidence.append(
            {
                "path": path,
                "role": "beginning_point_candidate" if path == beginning_path else "bounded_usage_reference",
                "match_count": int(record.get("match_count") or 0),
                "queries": record.get("queries") if isinstance(record.get("queries"), list) else [],
                "source_refs": [
                    {
                        "path": path,
                        "line": line_ref.get("line"),
                        "query": line_ref.get("query"),
                        "source": line_ref.get("source") or "bounded_investigation",
                    }
                    for line_ref in line_refs[:3]
                    if isinstance(line_ref, dict)
                ],
            }
        )
    return evidence


def multi_file_risks(
    path_assessment: dict[str, Any],
    related_tests: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    if path_assessment.get("status") == "possible_multiple_paths":
        risks.append(
            {
                "risk": "multiple_source_paths",
                "level": "medium",
                "reason": path_assessment.get("reason"),
            }
        )
    if not related_tests:
        risks.append(
            {
                "risk": "verification_tests_not_found",
                "level": "medium",
                "reason": "No related test files were found inside the bounded discovery budget.",
            }
        )
    if gaps:
        risks.append(
            {
                "risk": "investigation_gaps_present",
                "level": "medium",
                "reason": f"{len(gaps)} investigation gap(s) were recorded.",
            }
        )
    if warnings:
        risks.append(
            {
                "risk": "tool_warnings_present",
                "level": "low",
                "reason": f"{len(warnings)} bounded lookup warning(s) were recorded.",
            }
        )
    risks.append(
        {
            "risk": "bounded_usage_evidence_only",
            "level": "low",
            "reason": "Callers/usages are bounded source references from exact-text evidence, not a complete static call graph.",
        }
    )
    return risks[:5]


def dependency_risk_level(
    path_assessment: dict[str, Any],
    related_tests: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> str:
    if path_assessment.get("status") == "possible_multiple_paths":
        return "medium"
    if not related_tests:
        return "medium"
    if warnings:
        return "low"
    return "low"


def build_dependency_impact_summary(
    request: CodeInvestigationRequest,
    *,
    records: list[dict[str, Any]],
    related_tests: list[dict[str, Any]],
    path_assessment: dict[str, Any],
    verification_commands: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_dependency_impact_summary_request(request.user_request):
        return {"kind": "dependency_impact_summary", "schema_version": SCHEMA_VERSION, "status": "not_requested"}
    impacted_records = [
        record
        for record in records
        if record.get("category") in {"source", "configuration", "documentation"}
        and isinstance(record.get("path"), str)
    ]
    status = "ready" if impacted_records else "insufficient_evidence"
    risks = multi_file_risks(path_assessment, related_tests, gaps, warnings)
    risks.append(
        {
            "risk": "bounded_impact_scan_only",
            "level": "low",
            "reason": "Impact is based on bounded exact-text evidence and related-test discovery, not a full dependency graph.",
        }
    )
    return {
        "kind": "dependency_impact_summary",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "target": request.behavior or bounded_text(request.user_request, 240),
        "risk_level": dependency_risk_level(path_assessment, related_tests, warnings),
        "impacted_files": compact_evidence_records(impacted_records[: request.max_files]),
        "callers_usages": usage_evidence_from_records(records, {}, limit=request.max_files),
        "related_tests": compact_related_tests(related_tests),
        "risks": risks[:5],
        "verification_commands": verification_commands[:5],
        "mutation_policy": "read_only_no_source_mutation",
        "source_refs": source_refs_from_records(impacted_records[: request.max_files]),
        "gaps": gaps,
    }


def command_record(command: list[str], *, reason: str, associated_files: list[str]) -> dict[str, Any]:
    return {
        "command": command,
        "reason": reason,
        "associated_files": associated_files,
        "timeout_seconds": 300,
    }


def test_selection_tiers(
    verification_commands: list[dict[str, Any]],
    related_tests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    commands = [
        command
        for command in verification_commands
        if isinstance(command, dict) and isinstance(command.get("command"), list)
    ]
    test_paths = [
        str(item.get("path"))
        for item in related_tests
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    ]
    tiers: list[dict[str, Any]] = []
    if commands:
        first = commands[0]
        associated_files = first.get("associated_files") if isinstance(first.get("associated_files"), list) else []
        tiers.append(
            {
                "tier": "smallest",
                "commands": [first],
                "rationale": "Run the highest-ranked related test file first to validate the behavior with the smallest bounded command.",
                "covered_risk": "Direct behavior regression near the requested lookup.",
                "confidence": "medium",
                "gaps": [],
            }
        )
        selected_medium = commands[: min(3, len(commands))]
        medium_files = [
            str(path)
            for command in selected_medium
            for path in (command.get("associated_files") if isinstance(command.get("associated_files"), list) else [])
            if isinstance(path, str)
        ]
        tiers.append(
            {
                "tier": "medium",
                "commands": selected_medium,
                "rationale": "Run the top related test files to cover nearby unit and regression evidence without broad suite cost.",
                "covered_risk": "Behavior regression plus adjacent caller or follow-up paths found by bounded test discovery.",
                "confidence": "medium" if len(selected_medium) > 1 else "low",
                "gaps": [] if len(selected_medium) > 1 else [{"gap": "only_one_related_command_found"}],
                "associated_files": medium_files,
            }
        )
        broad_files = test_paths[:5] or [
            str(path)
            for path in associated_files
            if isinstance(path, str)
        ]
        broad_command = ["python", "-m", "pytest", *broad_files] if broad_files else []
        if broad_command:
            tiers.append(
                {
                    "tier": "broad",
                    "commands": [
                        command_record(
                            broad_command,
                            reason="Run the bounded set of discovered related tests as the broadest safe command for this behavior.",
                            associated_files=broad_files,
                        )
                    ],
                    "rationale": "Run all bounded related test files discovered for the behavior before escalating to a full suite.",
                    "covered_risk": "Cross-file behavior regressions inside the discovered related-test set.",
                    "confidence": "medium" if len(broad_files) > 1 else "low",
                    "gaps": [{"gap": "bounded_related_tests_only"}],
                    "associated_files": broad_files,
                }
            )
    return tiers


def build_test_selection_plan(
    request: CodeInvestigationRequest,
    *,
    related_tests: list[dict[str, Any]],
    verification_commands: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_test_selection_plan_request(request.user_request):
        return {"kind": "test_selection_plan", "schema_version": SCHEMA_VERSION, "status": "not_requested"}
    tiers = test_selection_tiers(verification_commands, related_tests)
    status = "ready" if tiers else "not_ready_no_related_tests"
    plan_gaps = list(gaps)
    if not tiers:
        plan_gaps.append({"gap": "verification_tests_not_found"})
    else:
        plan_gaps.append({"gap": "tiers_are_bounded_related_tests_not_full_suite"})
    return {
        "kind": "test_selection_plan",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "target": request.behavior or bounded_text(request.user_request, 240),
        "command_tiers": tiers,
        "related_tests": compact_related_tests(related_tests),
        "confidence": "medium" if tiers else "low",
        "mutation_policy": "read_only_no_source_mutation",
        "gaps": plan_gaps,
    }


def build_multi_file_behavior_investigation(
    request: CodeInvestigationRequest,
    *,
    beginning: dict[str, Any],
    records: list[dict[str, Any]],
    related_tests: list[dict[str, Any]],
    path_assessment: dict[str, Any],
    verification_commands: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_multi_file_behavior_investigation_request(request.user_request):
        return {"kind": "multi_file_behavior_investigation", "schema_version": SCHEMA_VERSION, "status": "not_requested"}
    source_records = [record for record in records if record.get("category") == "source"]
    status = "ready" if source_records else "insufficient_evidence"
    return {
        "kind": "multi_file_behavior_investigation",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "behavior": request.behavior or bounded_text(request.user_request, 240),
        "beginning_point": beginning,
        "participating_files": compact_evidence_records(records[: request.max_files]),
        "usage_evidence": usage_evidence_from_records(records, beginning, limit=request.max_files),
        "related_tests": compact_related_tests(related_tests),
        "risks": multi_file_risks(path_assessment, related_tests, gaps, warnings),
        "verification_commands": verification_commands[:5],
        "mutation_policy": "read_only_no_source_mutation",
        "source_refs": source_refs_from_records(source_records[: request.max_files]),
        "gaps": gaps,
    }


def project_traceback_frame(text: str) -> dict[str, Any] | None:
    for line in text.splitlines():
        match = re.search(r'File ["\']([^"\']+)["\'], line (\d+)(?:, in ([A-Za-z_][A-Za-z0-9_]*))?', line)
        if not match:
            continue
        return {
            "path": match.group(1).replace("\\", "/"),
            "line": int(match.group(2)),
            "symbol": match.group(3),
            "raw": bounded_text(line.strip(), 300),
        }
    return None


def runtime_likely_cause(error: dict[str, Any], frame: dict[str, Any] | None) -> dict[str, Any]:
    error_type = error.get("type")
    message = str(error.get("message") or "")
    lowered = message.lower()
    if "missing 'type' field" in lowered or 'missing "type" field' in lowered:
        summary = (
            "The dashboard message handler appears to require a message `type` field before dispatching; "
            "inspect the caller payload and handler guard before planning any change."
        )
        confidence = "medium"
    elif isinstance(error_type, str) and error_type:
        summary = f"The stack trace raised {error_type}; inspect the nearest project-code frame before drafting a fix."
        confidence = "low"
    else:
        summary = "The request did not expose a specific runtime exception; inspect the first project-code frame and reproduced input."
        confidence = "low"
    if frame and isinstance(frame.get("path"), str):
        summary = f"{summary} Nearest observed frame: {frame['path']}."
    return {"summary": summary, "confidence": confidence}


def matching_records_for_terms(
    records: list[dict[str, Any]],
    terms: list[str],
    *,
    categories: set[str] | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    lowered_terms = [term.lower() for term in terms if term]
    selected: list[dict[str, Any]] = []
    for record in records:
        if categories is not None and record.get("category") not in categories:
            continue
        path = str(record.get("path") or "")
        queries = " ".join(str(item) for item in record.get("queries", []) if isinstance(item, str))
        haystack = f"{path} {queries}".lower()
        if not lowered_terms or any(term in haystack for term in lowered_terms):
            selected.append(record)
        if len(selected) >= limit:
            break
    return selected


def build_runtime_error_diagnosis(
    request: CodeInvestigationRequest,
    *,
    records: list[dict[str, Any]],
    related_tests: list[dict[str, Any]],
    verification_commands: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_runtime_error_diagnosis_request(request.user_request):
        return {"kind": "runtime_error_diagnosis", "schema_version": SCHEMA_VERSION, "status": "not_requested"}
    error = extract_failure_error(request.user_request)
    frame = project_traceback_frame(request.user_request)
    frame_path = frame.get("path") if isinstance(frame, dict) else None
    terms = [str(error.get("type") or ""), str(error.get("message") or "")]
    if isinstance(frame_path, str):
        terms.append(Path(frame_path).name)
        terms.append(frame_path)
    evidence_records = matching_records_for_terms(records, terms, categories={"source", "test"}, limit=request.max_files)
    if frame_path and not any(record.get("path") == frame_path for record in evidence_records):
        evidence_records.insert(
            0,
            {
                "path": frame_path,
                "category": category_for_path(frame_path),
                "hinted": True,
                "queries": terms[:3],
                "match_count": 0,
                "line_refs": [{"line": frame.get("line"), "source": "traceback"}] if isinstance(frame, dict) else [],
            },
        )
    diagnosis_gaps = list(gaps)
    if error.get("type") is None:
        diagnosis_gaps.append({"gap": "runtime_error_type_not_found"})
    if frame is None:
        diagnosis_gaps.append({"gap": "project_traceback_frame_not_found"})
    if warnings:
        diagnosis_gaps.append({"gap": "fallback_or_warning_present", "warning_count": len(warnings)})
    next_steps = []
    if frame_path:
        next_steps.append({"step": "Inspect the nearest project-code traceback frame.", "path": frame_path, "line": frame.get("line")})
    next_steps.append({"step": "Confirm the input payload or runtime state that triggered the exception.", "path": frame_path})
    return {
        "kind": "runtime_error_diagnosis",
        "schema_version": SCHEMA_VERSION,
        "status": "ready" if error.get("type") or evidence_records else "unknown",
        "target": request.behavior or bounded_text(request.user_request, 240),
        "observed_error": error,
        "traceback_frame": frame,
        "likely_cause": runtime_likely_cause(error, frame),
        "evidence_files": compact_evidence_records(evidence_records[: request.max_files]),
        "related_tests": compact_related_tests(related_tests),
        "next_inspection_steps": next_steps,
        "risks": [
            {
                "risk": "diagnosis_is_hypothesis_until_reproduced",
                "level": "medium",
                "reason": "The artifact uses bounded stack-trace and source evidence; it does not execute the runtime path.",
            }
        ],
        "verification_commands": verification_commands[:5],
        "mutation_policy": "read_only_no_source_mutation",
        "source_refs": source_refs_from_records(evidence_records[: request.max_files]),
        "gaps": diagnosis_gaps,
    }


def build_reproduction_checklist(
    request: CodeInvestigationRequest,
    *,
    runtime_error_diagnosis: dict[str, Any],
    related_tests: list[dict[str, Any]],
    verification_commands: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_reproduction_checklist_request(request.user_request):
        return {"kind": "reproduction_checklist", "schema_version": SCHEMA_VERSION, "status": "not_requested"}
    error = (
        runtime_error_diagnosis.get("observed_error")
        if isinstance(runtime_error_diagnosis.get("observed_error"), dict)
        else extract_failure_error(request.user_request)
    )
    frame = (
        runtime_error_diagnosis.get("traceback_frame")
        if isinstance(runtime_error_diagnosis.get("traceback_frame"), dict)
        else project_traceback_frame(request.user_request)
    )
    frame_path = frame.get("path") if isinstance(frame, dict) and isinstance(frame.get("path"), str) else None
    command = verification_commands[0] if verification_commands else None
    checklist = [
        {
            "step": "Capture the exact runtime input or message that produced the observed exception.",
            "evidence": error.get("raw") if isinstance(error, dict) else None,
        },
        {
            "step": "Inspect the nearest project-code traceback frame before choosing a code change.",
            "path": frame_path,
            "line": frame.get("line") if isinstance(frame, dict) else None,
        },
        {
            "step": "Reproduce with the smallest related test or local command found by bounded evidence.",
            "command": command.get("command") if isinstance(command, dict) else None,
        },
        {
            "step": "Confirm whether the reproduced error matches the pasted stack trace before broadening tests.",
            "expected_error": error.get("type") if isinstance(error, dict) else None,
        },
    ]
    checklist_gaps = list(gaps)
    if not frame_path:
        checklist_gaps.append({"gap": "project_traceback_frame_not_found"})
    if command is None:
        checklist_gaps.append({"gap": "reproduction_command_not_found"})
    return {
        "kind": "reproduction_checklist",
        "schema_version": SCHEMA_VERSION,
        "status": "ready" if error.get("type") or frame_path else "unknown",
        "observed_error": error,
        "traceback_frame": frame,
        "minimal_reproduction_checklist": checklist,
        "related_tests": compact_related_tests(related_tests),
        "next_local_command": command,
        "mutation_policy": "read_only_no_source_mutation",
        "gaps": checklist_gaps,
    }


def build_request_flow_map(
    request: CodeInvestigationRequest,
    *,
    beginning: dict[str, Any],
    records: list[dict[str, Any]],
    related_tests: list[dict[str, Any]],
    verification_commands: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_request_flow_map_request(request.user_request):
        return {"kind": "request_flow_map", "schema_version": SCHEMA_VERSION, "status": "not_requested"}
    source_records = [
        record
        for record in records
        if record.get("category") == "source" and isinstance(record.get("path"), str)
    ]
    flow_steps: list[dict[str, Any]] = []
    for index, record in enumerate(source_records[: request.max_files], 1):
        line_refs = record.get("line_refs") if isinstance(record.get("line_refs"), list) else []
        first_line = line_refs[0].get("line") if line_refs and isinstance(line_refs[0], dict) else None
        role = "entrypoint" if record.get("path") == beginning.get("path") or index == 1 else "downstream_or_supporting_step"
        flow_steps.append(
            {
                "step": index,
                "path": record["path"],
                "line": first_line,
                "role": role,
                "evidence": f"Bounded exact-text evidence matched {record.get('match_count', 0)} time(s).",
            }
        )
    flow_gaps = list(gaps)
    if not flow_steps:
        flow_gaps.append({"gap": "source_flow_steps_not_found"})
    if warnings:
        flow_gaps.append({"gap": "fallback_or_warning_present", "warning_count": len(warnings)})
    return {
        "kind": "request_flow_map",
        "schema_version": SCHEMA_VERSION,
        "status": "ready" if flow_steps else "insufficient_evidence",
        "target_flow": request.behavior or bounded_text(request.user_request, 180),
        "beginning_point": beginning,
        "flow_steps": flow_steps,
        "participating_files": compact_evidence_records(records[: request.max_files]),
        "related_tests": compact_related_tests(related_tests),
        "risks": [
            {
                "risk": "bounded_flow_not_full_call_graph",
                "level": "low",
                "reason": "Flow steps are ordered from bounded source evidence, not from a complete dynamic trace.",
            }
        ],
        "verification_commands": verification_commands[:5],
        "mutation_policy": "read_only_no_source_mutation",
        "source_refs": source_refs_from_records(source_records[: request.max_files]),
        "gaps": flow_gaps,
    }


def comparison_candidates_from_request(text: str) -> list[str]:
    lowered = text.lower()
    candidates: list[str] = []
    if "placed_order_id" in lowered:
        candidates.append("placed_order_id stealth lookup path")
    if "client_order_id" in lowered:
        candidates.append("client_order_id index path")
    for match in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]*_[A-Za-z0-9_]+\b", text):
        token = match.group(0)
        if not any(token in candidate for candidate in candidates):
            append_unique(candidates, token, limit=2)
    while len(candidates) < 2:
        candidates.append(f"candidate_path_{len(candidates) + 1}")
    return candidates[:2]


def build_code_path_comparison(
    request: CodeInvestigationRequest,
    *,
    records: list[dict[str, Any]],
    related_tests: list[dict[str, Any]],
    verification_commands: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_code_path_comparison_request(request.user_request):
        return {"kind": "code_path_comparison", "schema_version": SCHEMA_VERSION, "status": "not_requested"}
    candidate_names = comparison_candidates_from_request(request.user_request)
    source_records = [record for record in records if record.get("category") == "source"]
    candidate_paths: list[dict[str, Any]] = []
    for name in candidate_names:
        terms = [part for part in re.split(r"[^A-Za-z0-9_]+", name) if len(part) > 3]
        evidence_records = matching_records_for_terms(source_records, terms, categories={"source"}, limit=request.max_files)
        if not evidence_records and source_records:
            evidence_records = source_records[:1]
        candidate_paths.append(
            {
                "name": name,
                "evidence": compact_evidence_records(evidence_records[: request.max_files]),
                "evidence_count": len(evidence_records),
                "related_tests": compact_related_tests(related_tests),
                "risks": [
                    {
                        "risk": "bounded_candidate_evidence",
                        "level": "low",
                        "reason": "Candidate path evidence is based on bounded exact-text matches.",
                    }
                ],
                "gaps": [] if evidence_records else [{"gap": "candidate_path_evidence_not_found"}],
            }
        )
    recommended = "unknown"
    confidence = "low"
    client_candidate = next((item for item in candidate_paths if "client_order_id" in item["name"]), None)
    if client_candidate and int(client_candidate.get("evidence_count") or 0) > 0:
        recommended = client_candidate["name"]
        confidence = "medium" if related_tests else "low"
    return {
        "kind": "code_path_comparison",
        "schema_version": SCHEMA_VERSION,
        "status": "ready" if source_records else "insufficient_evidence",
        "target": request.behavior or bounded_text(request.user_request, 180),
        "candidate_paths": candidate_paths,
        "comparison_summary": "The comparison is based on bounded source and test evidence; treat missing evidence as a gap, not proof of absence.",
        "recommended_path": {"name": recommended, "confidence": confidence},
        "related_tests": compact_related_tests(related_tests),
        "risks": [
            {
                "risk": "comparison_not_refactor_approval",
                "level": "medium",
                "reason": "A comparison result does not authorize implementation or refactor packet generation.",
            }
        ],
        "verification_commands": verification_commands[:5],
        "mutation_policy": "read_only_no_source_mutation",
        "source_refs": source_refs_from_records(source_records[: request.max_files]),
        "gaps": gaps,
    }


def change_surface_role(record: dict[str, Any]) -> str:
    category = record.get("category")
    if category == "test":
        return "validation_surface"
    if category == "configuration":
        return "configuration_review_surface"
    if category == "documentation":
        return "documentation_review_surface"
    return "source_change_surface"


def change_surface_risk_level(records: list[dict[str, Any]], related_tests: list[dict[str, Any]], gaps: list[dict[str, Any]]) -> str:
    source_count = len([record for record in records if record.get("category") == "source"])
    if source_count > 1 or not related_tests or gaps:
        return "medium"
    return "low"


def change_surface_sort_key(record: dict[str, Any]) -> tuple[int, int, str]:
    category_priority = {"source": 0, "test": 1, "configuration": 2, "documentation": 3}
    return (
        category_priority.get(str(record.get("category")), 9),
        -int(record.get("match_count") or 0),
        str(record.get("path", "")),
    )


def build_change_surface_summary(
    request: CodeInvestigationRequest,
    *,
    records: list[dict[str, Any]],
    related_tests: list[dict[str, Any]],
    verification_commands: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_change_surface_summary_request(request.user_request):
        return {"kind": "change_surface_summary", "schema_version": SCHEMA_VERSION, "status": "not_requested"}
    relevant_records = [
        record
        for record in records
        if record.get("category") in {"source", "configuration", "documentation", "test"}
        and isinstance(record.get("path"), str)
    ]
    relevant_records = sorted(relevant_records, key=change_surface_sort_key)[: request.max_files]
    files = []
    for record in compact_evidence_records(relevant_records):
        files.append({**record, "role": change_surface_role(record)})
    surface_gaps = list(gaps)
    if not relevant_records:
        surface_gaps.append({"gap": "change_surface_files_not_found"})
    if warnings:
        surface_gaps.append({"gap": "fallback_or_warning_present", "warning_count": len(warnings)})
    risk_level = change_surface_risk_level(relevant_records, related_tests, surface_gaps)
    return {
        "kind": "change_surface_summary",
        "schema_version": SCHEMA_VERSION,
        "status": "ready" if relevant_records else "insufficient_evidence",
        "target": request.behavior or bounded_text(request.user_request, 180),
        "change_surface_files": files,
        "related_tests": compact_related_tests(related_tests),
        "risk_level": risk_level,
        "risks": [
            {
                "risk": "requires_approval_before_packet_design",
                "level": "medium",
                "reason": "This artifact identifies review scope only; implementation packet generation still requires explicit approval.",
            }
        ],
        "implementation_status": "not_ready_without_approval",
        "verification_commands": verification_commands[:5],
        "mutation_policy": "read_only_no_source_mutation",
        "source_refs": source_refs_from_records(relevant_records),
        "gaps": surface_gaps,
    }


def is_code_explanation_request(text: str) -> bool:
    lowered = text.lower()
    if is_test_selection_plan_request(text):
        return False
    if "explain each usage" in lowered or "callers/usages" in lowered or "callers and usages" in lowered:
        return False
    if (
        any(term in lowered for term in ("test command", "test commands", "validation command", "validation commands"))
        and any(term in lowered for term in ("explain why", "why that command", "why each command"))
    ):
        return False
    config_terms = ("config", "configuration", "setting", "env var", "environment variable", "coinbase_api_key")
    effect_terms = (
        "runtime effect of",
        "affect at runtime",
        "affects at runtime",
        "what does it affect",
        "does at runtime",
    )
    if any(term in lowered for term in config_terms) and any(term in lowered for term in effect_terms):
        return False
    explain_terms = (
        "explain ",
        "explain what",
        "explain this function",
        "explain this file",
        "what does",
        "what do",
        "summarize what",
    )
    return any(term in lowered for term in explain_terms)


def ast_text(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:  # noqa: BLE001 - AST snippets may come from partial files
        return None


def function_arguments(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    args: list[str] = []
    for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
        append_unique(args, arg.arg)
    if node.args.vararg is not None:
        append_unique(args, f"*{node.args.vararg.arg}")
    if node.args.kwarg is not None:
        append_unique(args, f"**{node.args.kwarg.arg}")
    return args


def return_values(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    values: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Return):
            expression = ast_text(child.value) or "None"
            append_unique(values, expression, limit=10)
    return values


def assignment_targets(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    values: list[str] = []
    for child in ast.walk(node):
        targets: list[ast.AST] = []
        if isinstance(child, ast.Assign):
            targets = list(child.targets)
        elif isinstance(child, ast.AnnAssign):
            targets = [child.target]
        elif isinstance(child, ast.AugAssign):
            targets = [child.target]
        for target in targets:
            text = ast_text(target)
            if text:
                append_unique(values, text, limit=10)
    return values


def call_targets(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    values: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            text = ast_text(child.func)
            if text:
                append_unique(values, text, limit=10)
    return values


def python_definitions(snippet: str, path: str) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(snippet)
    except SyntaxError:
        return []
    definitions: list[dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            definitions.append(
                {
                    "kind": "class",
                    "name": node.name,
                    "qualified_name": node.name,
                    "path": path,
                    "line": node.lineno,
                    "end_line": getattr(node, "end_lineno", None),
                    "methods": [
                        child.name
                        for child in node.body
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                    ],
                }
            )
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    definitions.append(
                        {
                            "kind": "method",
                            "name": child.name,
                            "qualified_name": f"{node.name}.{child.name}",
                            "path": path,
                            "line": child.lineno,
                            "end_line": getattr(child, "end_lineno", None),
                            "arguments": function_arguments(child),
                            "returns": return_values(child),
                            "assignments": assignment_targets(child),
                            "calls": call_targets(child),
                        }
                    )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            definitions.append(
                {
                    "kind": "function",
                    "name": node.name,
                    "qualified_name": node.name,
                    "path": path,
                    "line": node.lineno,
                    "end_line": getattr(node, "end_lineno", None),
                    "arguments": function_arguments(node),
                    "returns": return_values(node),
                    "assignments": assignment_targets(node),
                    "calls": call_targets(node),
                }
            )
    return definitions


def python_definitions_from_selected_files(
    target_root: Path,
    selected_paths: list[str],
    max_files: int,
) -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    for rel_path in selected_paths[:max_files]:
        if category_for_path(rel_path) != "source" or not rel_path.endswith(".py"):
            continue
        path = target_root / rel_path
        try:
            if not path.is_file() or path.stat().st_size > 256 * 1024:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        definitions.extend(python_definitions(text, rel_path))
    return definitions


def selected_definition(definitions: list[dict[str, Any]], queries: list[str]) -> dict[str, Any] | None:
    identifier_queries = [
        query
        for query in queries
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?", query)
    ]
    for query in identifier_queries:
        for definition in definitions:
            if query in {definition.get("name"), definition.get("qualified_name")}:
                return definition
    for query in identifier_queries:
        for definition in definitions:
            qualified_name = str(definition.get("qualified_name", ""))
            if qualified_name.endswith(f".{query}"):
                return definition
    return None


def input_records(definition: dict[str, Any]) -> list[dict[str, Any]]:
    args = definition.get("arguments")
    if not isinstance(args, list):
        return []
    records: list[dict[str, Any]] = []
    for arg in args:
        if not isinstance(arg, str):
            continue
        role = "instance" if arg == "self" else "argument"
        records.append({"name": arg, "role": role, "source": "python_ast"})
    return records


def output_records(definition: dict[str, Any]) -> list[dict[str, Any]]:
    returns = definition.get("returns")
    if not isinstance(returns, list):
        return [{"kind": "definition", "description": "This target defines code but has no callable return value in the bounded AST evidence."}]
    if not returns:
        return [{"kind": "return", "description": "No explicit return statement was found in the selected definition."}]
    return [{"kind": "return", "value": item, "source": "python_ast"} for item in returns if isinstance(item, str)]


def side_effect_records(definition: dict[str, Any]) -> list[dict[str, Any]]:
    effects: list[dict[str, Any]] = []
    assignments = definition.get("assignments")
    if isinstance(assignments, list):
        for item in assignments:
            if isinstance(item, str):
                effects.append({"kind": "assignment", "target": item, "source": "python_ast"})
    calls = definition.get("calls")
    if isinstance(calls, list):
        for item in calls:
            if isinstance(item, str):
                effects.append({"kind": "call", "target": item, "source": "python_ast"})
    if effects:
        return effects
    return [
        {
            "kind": "none_observed",
            "description": "No assignments or call expressions were found inside the selected definition in the bounded snippet.",
            "source": "python_ast",
        }
    ]


def compact_related_tests(related_tests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for item in related_tests:
        path = item.get("path")
        if not isinstance(path, str):
            continue
        compact.append(
            {
                "path": path,
                "matched_terms": item.get("matched_terms") if isinstance(item.get("matched_terms"), list) else [],
                "source": item.get("source"),
            }
        )
    return compact


def source_refs_for_explanation(
    records: list[dict[str, Any]],
    target_path: str | None,
    definition: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if isinstance(definition, dict) and isinstance(definition.get("path"), str):
        ref: dict[str, Any] = {
            "path": definition["path"],
            "source": "python_ast",
            "symbol": definition.get("qualified_name") or definition.get("name"),
        }
        if isinstance(definition.get("line"), int):
            ref["line"] = definition["line"]
        refs.append(ref)
    for record in records:
        path = record.get("path")
        if not isinstance(path, str) or (target_path and path != target_path):
            continue
        line_refs = record.get("line_refs")
        if not isinstance(line_refs, list):
            continue
        for line_ref in line_refs[:5]:
            if not isinstance(line_ref, dict):
                continue
            ref = {"path": path, "source": line_ref.get("source") or "bounded_investigation"}
            if isinstance(line_ref.get("line"), int):
                ref["line"] = line_ref["line"]
            if isinstance(line_ref.get("query"), str):
                ref["query"] = line_ref["query"]
            refs.append(ref)
    if not refs and target_path:
        refs.append({"path": target_path, "source": "selected_path"})
    return refs


def build_code_explanation(
    request: CodeInvestigationRequest,
    *,
    target_root: Path,
    selected_paths: list[str],
    queries: list[str],
    records: list[dict[str, Any]],
    snippets: list[dict[str, Any]],
    beginning: dict[str, Any],
    related_tests: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_code_explanation_request(request.user_request):
        return {"kind": "code_explanation", "schema_version": SCHEMA_VERSION, "status": "not_requested"}

    source_snippets = [
        snippet
        for snippet in snippets
        if isinstance(snippet.get("path"), str)
        and snippet.get("status") == "read"
        and category_for_path(str(snippet.get("path"))) == "source"
        and isinstance(snippet.get("snippet"), str)
    ]
    if not source_snippets:
        target_path = beginning.get("path") if isinstance(beginning.get("path"), str) else (selected_paths[0] if selected_paths else None)
        return {
            "kind": "code_explanation",
            "schema_version": SCHEMA_VERSION,
            "status": "insufficient_evidence",
            "target": {"path": target_path, "symbol": queries[0] if queries else None, "definition_kind": None},
            "summary": "No readable source snippet was available inside the bounded investigation budget.",
            "key_inputs": [],
            "outputs": [],
            "side_effects": [],
            "related_tests": compact_related_tests(related_tests),
            "source_refs": source_refs_for_explanation(records, target_path, None),
        }

    all_definitions = python_definitions_from_selected_files(target_root, selected_paths, request.max_files)
    for snippet in source_snippets:
        all_definitions.extend(python_definitions(str(snippet["snippet"]), str(snippet["path"])))
    definition = selected_definition(all_definitions, queries)
    target_path = (
        str(definition["path"])
        if isinstance(definition, dict) and isinstance(definition.get("path"), str)
        else str(source_snippets[0]["path"])
    )
    if definition is not None:
        target = {
            "path": target_path,
            "symbol": definition.get("qualified_name") or definition.get("name"),
            "definition_kind": definition.get("kind"),
            "line": definition.get("line"),
        }
        returns = definition.get("returns") if isinstance(definition.get("returns"), list) else []
        return_summary = f" It returns {', '.join(str(item) for item in returns)}." if returns else ""
        summary = (
            f"{target['symbol']} is a {definition.get('kind')} in {target_path}."
            f"{return_summary}"
        )
        return {
            "kind": "code_explanation",
            "schema_version": SCHEMA_VERSION,
            "status": "ready",
            "target": target,
            "summary": summary,
            "key_inputs": input_records(definition),
            "outputs": output_records(definition),
            "side_effects": side_effect_records(definition),
            "related_tests": compact_related_tests(related_tests),
            "source_refs": source_refs_for_explanation(records, target_path, definition),
        }

    definitions_by_path = [item for item in all_definitions if item.get("path") == target_path]
    symbols = [
        str(item.get("qualified_name") or item.get("name"))
        for item in definitions_by_path[:10]
        if item.get("qualified_name") or item.get("name")
    ]
    symbol_summary = ", ".join(symbols) if symbols else "no Python definitions found in the bounded snippet"
    return {
        "kind": "code_explanation",
        "schema_version": SCHEMA_VERSION,
        "status": "ready",
        "target": {"path": target_path, "symbol": None, "definition_kind": "file"},
        "summary": f"{target_path} contains {symbol_summary}.",
        "key_inputs": [],
        "outputs": [
            {
                "kind": "definitions",
                "description": "The file output is its defined classes, functions, constants, and module-level values.",
                "symbols": symbols,
            }
        ],
        "side_effects": [
            {
                "kind": "bounded_file_review",
                "description": "The explanation is based on the readable snippet and does not claim whole-file behavior beyond that evidence.",
            }
        ],
        "related_tests": compact_related_tests(related_tests),
        "source_refs": source_refs_for_explanation(records, target_path, None),
    }


def is_behavior_existence_request(text: str) -> bool:
    lowered = text.lower()
    existence_terms = (
        "already exists",
        "already exist",
        "already have",
        "does the repo already have",
        "does this repo already have",
        "whether",
        "check if",
        "check whether",
        "does this exist",
        "does it exist",
        "is there",
    )
    outcome_terms = ("exists", "exist", "present", "implemented", "already")
    return any(term in lowered for term in existence_terms) and any(term in lowered for term in outcome_terms)


def compact_evidence_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for record in records:
        path = record.get("path")
        if not isinstance(path, str):
            continue
        compact.append(
            {
                "path": path,
                "category": record.get("category"),
                "match_count": record.get("match_count", 0),
                "queries": record.get("queries") if isinstance(record.get("queries"), list) else [],
                "line_refs": record.get("line_refs") if isinstance(record.get("line_refs"), list) else [],
            }
        )
    return compact


def source_refs_from_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for record in records:
        path = record.get("path")
        if not isinstance(path, str):
            continue
        line_refs = record.get("line_refs")
        if not isinstance(line_refs, list):
            refs.append({"path": path, "source": "bounded_investigation"})
            continue
        for line_ref in line_refs[:5]:
            if not isinstance(line_ref, dict):
                continue
            ref = {"path": path, "source": line_ref.get("source") or "bounded_investigation"}
            if isinstance(line_ref.get("line"), int):
                ref["line"] = line_ref["line"]
            if isinstance(line_ref.get("query"), str):
                ref["query"] = line_ref["query"]
            refs.append(ref)
    return refs


def build_behavior_existence(
    request: CodeInvestigationRequest,
    *,
    queries: list[str],
    records: list[dict[str, Any]],
    matches: list[dict[str, Any]],
    related_tests: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_behavior_existence_request(request.user_request):
        return {"kind": "behavior_existence", "schema_version": SCHEMA_VERSION, "status": "not_requested"}

    source_records = [
        record
        for record in records
        if record.get("category") == "source" and int(record.get("match_count") or 0) > 0
    ]
    non_source_records = [
        record
        for record in records
        if record.get("category") != "source" and int(record.get("match_count") or 0) > 0
    ]
    if source_records:
        status = "exists"
        answer = "yes"
        confidence = "medium"
        reason = "Bounded exact-text evidence found matching source files."
        evidence_records = source_records
        gaps: list[dict[str, Any]] = []
    else:
        status = "unknown"
        answer = "unknown"
        confidence = "low"
        evidence_records = non_source_records
        reason = (
            "No matching source evidence was found in the bounded investigation. "
            "This is not proof that the behavior is absent."
        )
        gaps = [{"gap": "absence_not_proven", "reason": reason}]
    if not queries:
        gaps.append({"gap": "query_not_derived", "reason": "No bounded search query was derived from the request."})
    if warnings:
        gaps.append({"gap": "fallback_or_warning_present", "warning_count": len(warnings)})

    return {
        "kind": "behavior_existence",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "answer": answer,
        "confidence": confidence,
        "reason": reason,
        "queries": queries,
        "match_count": len(matches),
        "evidence_files": compact_evidence_records(evidence_records),
        "related_tests": compact_related_tests(related_tests),
        "source_refs": source_refs_from_records(evidence_records),
        "gaps": gaps,
    }


def is_configuration_lookup_request(text: str) -> bool:
    lowered = text.lower()
    config_terms = (
        "config",
        "configuration",
        "setting",
        "env var",
        "environment variable",
        "environment setting",
    )
    lookup_terms = ("defined", "used", "where", "locate", "runtime effect", "current value", "override")
    return any(term in lowered for term in config_terms) and any(term in lowered for term in lookup_terms)


def config_reference_role(query: str, path: str, text: str) -> str:
    stripped = text.strip()
    if "getenv(" in stripped or "os.environ" in stripped:
        return "environment_read"
    if category_for_path(path) == "configuration":
        return "definition"
    if re.search(rf"\b{re.escape(query)}\b\s*[:=]", stripped):
        return "definition"
    if re.search(rf"\b[A-Za-z_][A-Za-z0-9_]*\b\s*=\s*.*\b{re.escape(query)}\b", stripped):
        return "derived_definition"
    return "usage"


def visible_config_value(query: str, role: str, text: str) -> str | None:
    if role == "environment_read":
        return "not_visible_environment"
    match = re.search(rf"\b{re.escape(query)}\b\s*[:=]\s*(.+)$", text.strip())
    if match:
        return bounded_text(match.group(1), 200)
    return None


def build_configuration_lookup(
    request: CodeInvestigationRequest,
    *,
    queries: list[str],
    matches: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_configuration_lookup_request(request.user_request):
        return {"kind": "configuration_lookup", "schema_version": SCHEMA_VERSION, "status": "not_requested"}
    query = queries[0] if queries else request.behavior.strip()
    references: list[dict[str, Any]] = []
    for match in matches:
        path = match.get("path")
        text = match.get("text")
        if not isinstance(path, str) or not isinstance(text, str):
            continue
        role = config_reference_role(query, path, text)
        reference = {
            "path": path,
            "line": match.get("line") if isinstance(match.get("line"), int) else None,
            "role": role,
            "query": match.get("query") if isinstance(match.get("query"), str) else query,
            "text": bounded_text(text, 300),
            "source": match.get("source") or "bounded_investigation",
            "likely_runtime_effect": "Reference participates in runtime behavior; inspect nearby code for precedence and defaults.",
        }
        value = visible_config_value(query, role, text)
        if value is not None:
            reference["current_value"] = value
        if role == "environment_read":
            reference["likely_runtime_effect"] = "Runtime value is read from the process environment; the actual value is not visible in source."
        elif role in {"definition", "derived_definition"}:
            reference["likely_runtime_effect"] = "This line appears to define or derive the setting used by runtime code."
        references.append(reference)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for reference in references:
        path = reference.get("path")
        if isinstance(path, str):
            grouped.setdefault(path, []).append(reference)
    groups = [
        {
            "path": path,
            "roles": sorted({str(item.get("role")) for item in items if item.get("role")}),
            "reference_count": len(items),
            "references": items[:20],
        }
        for path, items in sorted(grouped.items())
    ]
    if groups:
        status = "ready"
        reason = "Configuration references were found in bounded exact-text evidence."
    else:
        status = "unknown"
        reason = "No configuration references were found in the bounded investigation; absence is not proven."
    gaps = [] if groups else [{"gap": "configuration_reference_not_found", "reason": reason}]
    if warnings:
        gaps.append({"gap": "fallback_or_warning_present", "warning_count": len(warnings)})
    return {
        "kind": "configuration_lookup",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "target": query,
        "group_count": len(groups),
        "reference_count": len(references),
        "groups": groups,
        "gaps": gaps,
        "reason": reason,
    }


def is_endpoint_route_lookup_request(text: str) -> bool:
    lowered = text.lower()
    if is_local_change_summary_request(text):
        return False
    if is_cli_entrypoint_lookup_request(text):
        return False
    route_terms = (
        "endpoint",
        "route handler",
        "request handler",
        "message handler",
        "websocket handler",
        "handler for",
        "handles",
    )
    lookup_terms = ("find", "locate", "where", "which", "show")
    return any(term in lowered for term in route_terms) and any(term in lowered for term in lookup_terms)


def handler_role_for_text(text: str) -> str:
    stripped = text.strip()
    if "msg_type" in stripped:
        return "websocket_message_handler"
    if re.search(r"@\w+\.(?:route|get|post|put|delete|patch)\b", stripped):
        return "decorated_http_route"
    if re.search(r"\b(?:GET|POST|PUT|DELETE|PATCH)\s+/", stripped):
        return "documented_http_endpoint"
    if "handler" in stripped.lower():
        return "handler_reference"
    return "route_or_handler_reference"


def route_handler_records(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    handlers: list[dict[str, Any]] = []
    seen: set[tuple[str, int | None, str]] = set()
    for match in matches:
        path = match.get("path")
        text = match.get("text")
        if not isinstance(path, str) or not isinstance(text, str):
            continue
        if category_for_path(path) != "source":
            continue
        line = match.get("line") if isinstance(match.get("line"), int) else None
        role = handler_role_for_text(text)
        key = (path, line, text.strip())
        if key in seen:
            continue
        seen.add(key)
        handlers.append(
            {
                "path": path,
                "line": line,
                "role": role,
                "query": match.get("query"),
                "evidence": bounded_text(text, 300),
                "source": match.get("source") or "bounded_investigation",
            }
        )
    role_priority = {
        "decorated_http_route": 0,
        "websocket_message_handler": 0,
        "documented_http_endpoint": 1,
        "handler_reference": 2,
        "route_or_handler_reference": 3,
    }
    handlers.sort(
        key=lambda item: (
            role_priority.get(str(item.get("role")), 9),
            1 if str(item.get("path", "")).startswith("docs/") else 0,
            1 if not str(item.get("path", "")).endswith(".py") else 0,
            str(item.get("path", "")),
            item.get("line") if isinstance(item.get("line"), int) else 0,
        )
    )
    return handlers[:20]


def build_endpoint_route_lookup(
    request: CodeInvestigationRequest,
    *,
    queries: list[str],
    matches: list[dict[str, Any]],
    related_tests: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_endpoint_route_lookup_request(request.user_request):
        return {"kind": "endpoint_route_lookup", "schema_version": SCHEMA_VERSION, "status": "not_requested"}
    handlers = route_handler_records(matches)
    target = queries[0] if queries else request.behavior.strip()
    if handlers:
        status = "ready"
        reason = "Route or handler evidence was found in bounded source matches."
    else:
        status = "unknown"
        reason = "No route or handler source evidence was found in the bounded investigation."
    gaps = [] if handlers else [{"gap": "handler_not_found", "reason": reason}]
    if warnings:
        gaps.append({"gap": "fallback_or_warning_present", "warning_count": len(warnings)})
    return {
        "kind": "endpoint_route_lookup",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "target": target,
        "handler_count": len(handlers),
        "handlers": handlers,
        "related_tests": compact_related_tests(related_tests),
        "source_refs": [
            {key: value for key, value in {"path": item.get("path"), "line": item.get("line"), "source": item.get("source")}.items() if value is not None}
            for item in handlers[:10]
        ],
        "mutation_policy": "read_only_no_source_mutation",
        "gaps": gaps,
        "reason": reason,
    }


def is_message_source_lookup_request(text: str) -> bool:
    lowered = text.lower()
    if is_user_facing_message_test_target_request(text):
        return True
    message_terms = ("error message", "log message", "logged", "logger", "exception message", "comes from", "source of")
    lookup_terms = ("find", "locate", "where", "which", "source", "comes from")
    return any(term in lowered for term in message_terms) and any(term in lowered for term in lookup_terms)


def is_user_facing_message_test_target_request(text: str) -> bool:
    lowered = text.lower()
    if any(term in lowered for term in ("add", "create", "implement", "fix failing", "fix test", "update test", "apply", "mutate")):
        return False
    message_terms = ("error message", "log message", "exception message")
    user_terms = ("user-facing", "user facing", "shown to user", "visible to user")
    test_terms = ("where it should be tested", "where should it be tested", "tested", "test target", "related tests")
    return any(term in lowered for term in message_terms) and any(term in lowered for term in user_terms) and any(
        term in lowered for term in test_terms
    )


def message_reference_role(text: str) -> str:
    stripped = text.strip()
    if "logger." in stripped or ".error(" in stripped or ".warning(" in stripped or ".info(" in stripped:
        return "log_call"
    if "raise " in stripped:
        return "raised_exception"
    if "print(" in stripped:
        return "print_output"
    return "message_reference"


def build_message_source_lookup(
    request: CodeInvestigationRequest,
    *,
    queries: list[str],
    matches: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    related_tests: list[dict[str, Any]] | None = None,
    verification_commands: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not is_message_source_lookup_request(request.user_request):
        return {"kind": "message_source_lookup", "schema_version": SCHEMA_VERSION, "status": "not_requested"}
    target = queries[0] if queries else request.behavior.strip()
    sources: list[dict[str, Any]] = []
    for match in matches:
        path = match.get("path")
        text = match.get("text")
        if not isinstance(path, str) or not isinstance(text, str):
            continue
        sources.append(
            {
                "path": path,
                "line": match.get("line") if isinstance(match.get("line"), int) else None,
                "role": message_reference_role(text),
                "query": match.get("query"),
                "text": bounded_text(text, 300),
                "source": match.get("source") or "bounded_investigation",
            }
        )
    if sources:
        status = "ready"
        reason = "Message source evidence was found in bounded exact-text matches."
    else:
        status = "unknown"
        reason = "No source line matched the requested message in the bounded investigation."
    gaps = [] if sources else [{"gap": "message_source_not_found", "reason": reason}]
    if warnings:
        gaps.append({"gap": "fallback_or_warning_present", "warning_count": len(warnings)})
    user_facing_assessment: dict[str, Any] | None = None
    if is_user_facing_message_test_target_request(request.user_request):
        roles = {str(item.get("role")) for item in sources if isinstance(item.get("role"), str)}
        recommended_test_targets = compact_related_tests(related_tests or [])
        for source in sources:
            path = source.get("path")
            if not isinstance(path, str) or category_for_path(path) != "test":
                continue
            if any(item.get("path") == path for item in recommended_test_targets):
                continue
            recommended_test_targets.append(
                {
                    "path": path,
                    "matched_terms": [target],
                    "source": "message_source_lookup",
                }
            )
        if "raised_exception" in roles:
            assessment_status = "unknown"
            assessment_reason = (
                "The message is raised from project code; bounded evidence does not prove whether the exception is rendered to an end user."
            )
        elif "print_output" in roles or "log_call" in roles:
            assessment_status = "not_proven_user_facing"
            assessment_reason = "Bounded evidence found logging/output source, not user-interface rendering."
        else:
            assessment_status = "unknown"
            assessment_reason = "No bounded message source proved user-facing behavior."
        user_facing_assessment = {
            "status": assessment_status,
            "reason": assessment_reason,
            "message_roles": sorted(roles),
            "recommended_test_targets": recommended_test_targets[:20],
            "verification_commands": (verification_commands or [])[:5],
        }
    return {
        "kind": "message_source_lookup",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "target": target,
        "source_count": len(sources),
        "sources": sources[:20],
        "source_refs": [
            {key: value for key, value in {"path": item.get("path"), "line": item.get("line"), "source": item.get("source")}.items() if value is not None}
            for item in sources[:10]
        ],
        "mutation_policy": "read_only_no_source_mutation",
        "user_facing_assessment": user_facing_assessment,
        "gaps": gaps,
        "reason": reason,
    }


def is_module_summary_request(text: str) -> bool:
    lowered = text.lower()
    if is_test_failure_summary_request(text) or is_ci_failure_summary_request(text):
        return False
    summary_terms = ("summarize module", "summarize this module", "summarize file", "module summary", "file summary")
    return any(term in lowered for term in summary_terms) or (
        "summarize " in lowered
        and re.search(
            r"(?<![\w./\\-])(?:[A-Za-z0-9_.-]+[\\/])+[A-Za-z0-9_.-]+\.(?:py|md|rst|txt|json|yaml|yml)\b",
            text,
            flags=re.IGNORECASE,
        )
        is not None
    )


def module_doc_summary(target_root: Path, rel_path: str) -> str | None:
    path = target_root / rel_path
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(text)
    except (OSError, SyntaxError):
        return None
    docstring = ast.get_docstring(tree)
    if not docstring:
        return None
    first_line = " ".join(docstring.strip().splitlines()[0].split())
    return bounded_text(first_line, 300)


def build_module_summary(
    request: CodeInvestigationRequest,
    *,
    target_root: Path,
    selected_paths: list[str],
    queries: list[str],
    related_tests: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_module_summary_request(request.user_request):
        return {"kind": "module_summary", "schema_version": SCHEMA_VERSION, "status": "not_requested"}
    target_path = selected_paths[0] if selected_paths else (request.paths[0] if request.paths else None)
    definitions = python_definitions_from_selected_files(target_root, selected_paths, request.max_files)
    visible_definitions = [
        {
            "path": item.get("path"),
            "name": item.get("qualified_name") or item.get("name"),
            "kind": item.get("kind"),
            "line": item.get("line"),
        }
        for item in definitions[:20]
    ]
    doc_summary = module_doc_summary(target_root, target_path) if isinstance(target_path, str) else None
    if definitions or target_path:
        status = "ready"
        reason = "Module summary was produced from bounded file path and AST evidence."
    else:
        status = "insufficient_evidence"
        reason = "No readable module path or definitions were found in the bounded investigation."
    responsibilities = []
    if doc_summary:
        responsibilities.append({"source": "module_docstring", "description": doc_summary})
    if definitions:
        names = [str(item.get("qualified_name") or item.get("name")) for item in definitions[:8] if item.get("qualified_name") or item.get("name")]
        responsibilities.append(
            {
                "source": "python_ast",
                "description": f"Defines {', '.join(names)}.",
            }
        )
    gaps = [] if status == "ready" else [{"gap": "module_summary_evidence_missing", "reason": reason}]
    return {
        "kind": "module_summary",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "target": {"path": target_path, "query": queries[0] if queries else None},
        "summary": doc_summary or reason,
        "definition_count": len(definitions),
        "definitions": visible_definitions,
        "responsibilities": responsibilities,
        "related_tests": compact_related_tests(related_tests),
        "source_refs": [{"path": target_path, "source": "selected_path"}] if isinstance(target_path, str) else [],
        "mutation_policy": "read_only_no_source_mutation",
        "gaps": gaps,
        "reason": reason,
    }


def is_data_model_lookup_request(text: str) -> bool:
    lowered = text.lower()
    model_terms = ("data model", "schema", "table schema", "database schema", "dataclass", "fields", "columns")
    lookup_terms = ("find", "locate", "where", "show", "summarize", "list")
    return any(term in lowered for term in model_terms) and any(term in lowered for term in lookup_terms)


def table_schema_fields(target_root: Path, rel_path: str, table_name: str) -> list[dict[str, Any]]:
    path = target_root / rel_path
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    fields: list[dict[str, Any]] = []
    in_table = False
    for line_no, line in enumerate(lines, 1):
        stripped = line.strip()
        if not in_table and re.search(rf"\bCREATE\s+TABLE\b.*\b{re.escape(table_name)}\b", stripped, re.IGNORECASE):
            in_table = True
            continue
        if not in_table:
            continue
        if stripped.startswith(");") or stripped == ");":
            break
        field_match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s+(.+?)(?:,)?$", stripped)
        if not field_match:
            continue
        column_name = field_match.group(1)
        if column_name.upper() in {"PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "CONSTRAINT"}:
            continue
        fields.append(
            {
                "name": column_name,
                "definition": bounded_text(field_match.group(2).rstrip(","), 240),
                "path": rel_path,
                "line": line_no,
                "source": "sql_schema_block",
            }
        )
    return fields[:80]


def canonical_data_model_target(candidate: str) -> str:
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", candidate)
    leading_stop_words = {"a", "an", "the"}
    trailing_stop_words = {"any", "fields", "gaps", "include", "model", "only", "read", "return", "source"}
    while words and words[0].lower() in leading_stop_words:
        words.pop(0)
    while words and words[-1].lower() in trailing_stop_words:
        words.pop()
    if not words:
        return candidate.strip()
    if len(words) == 1:
        return words[0]
    return "_".join(word.lower() for word in words)


def data_model_target_from_request(user_request: str, queries: list[str], fallback: str) -> str:
    text = re.sub(r"(?:/[^\s,]+|[A-Za-z]:\\[^\s,]+)", " ", user_request)
    normalized = re.sub(r"[^A-Za-z0-9_ ]+", " ", text)
    skip = {
        "data",
        "database",
        "model",
        "schema",
        "table",
        "fields",
        "field",
        "only",
        "read",
        "return",
        "source",
        "refs",
        "runtime",
        "the",
        "a",
        "an",
    }
    patterns = (
        r"\bdatabase\s+schema\s+fields\s+(?:for|of)\s+([A-Za-z_][A-Za-z0-9_]*(?:\s+[A-Za-z_][A-Za-z0-9_]*)?)\b",
        r"\bschema\s+fields\s+(?:for|of)\s+([A-Za-z_][A-Za-z0-9_]*(?:\s+[A-Za-z_][A-Za-z0-9_]*)?)\b",
        r"\bfields\s+(?:for|of)\s+([A-Za-z_][A-Za-z0-9_]*(?:\s+[A-Za-z_][A-Za-z0-9_]*)?)\b",
        r"\bwhere\s+(?:the\s+)?([A-Za-z_][A-Za-z0-9_]*(?:\s+[A-Za-z_][A-Za-z0-9_]*)?)\s+table\b",
        r"\bfind\s+where\s+(?:the\s+)?([A-Za-z_][A-Za-z0-9_]*(?:\s+[A-Za-z_][A-Za-z0-9_]*)?)\s+table\b",
        r"\blocate\s+(?:the\s+)?([A-Za-z_][A-Za-z0-9_]*(?:\s+[A-Za-z_][A-Za-z0-9_]*)?)\s+table\b",
        r"\b([A-Za-z_][A-Za-z0-9_]*(?:\s+[A-Za-z_][A-Za-z0-9_]*)?)\s+table\s+(?:is\s+)?(?:defined|read|written|created|used)\b",
        r"\b([A-Za-z_][A-Za-z0-9_]*(?:\s+[A-Za-z_][A-Za-z0-9_]*)?)\s+table\s+schema\b",
        r"\btable\s+schema\s+(?:for|of)\s+([A-Za-z_][A-Za-z0-9_]*(?:\s+[A-Za-z_][A-Za-z0-9_]*)?)\b",
        r"\btable\s+(?:for|of)\s+([A-Za-z_][A-Za-z0-9_]*(?:\s+[A-Za-z_][A-Za-z0-9_]*)?)\b",
        r"\b([A-Za-z_][A-Za-z0-9_]*(?:\s+[A-Za-z_][A-Za-z0-9_]*)?)\s+database\s+schema\b",
        r"\b([A-Za-z_][A-Za-z0-9_]*(?:\s+[A-Za-z_][A-Za-z0-9_]*)?)\s+schema\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, normalized, re.IGNORECASE):
            candidate = match.group(1)
            if candidate.lower() not in skip:
                return canonical_data_model_target(candidate)
    for query in queries:
        candidate = query.strip()
        if candidate and "/" not in candidate and "\\" not in candidate and candidate.lower() not in skip:
            return candidate
    return fallback.strip()


def build_data_model_lookup(
    request: CodeInvestigationRequest,
    *,
    target_root: Path,
    queries: list[str],
    matches: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_data_model_lookup_request(request.user_request):
        return {"kind": "data_model_lookup", "schema_version": SCHEMA_VERSION, "status": "not_requested"}
    table_name = data_model_target_from_request(request.user_request, queries, request.behavior)
    schema_paths = [
        str(match["path"])
        for match in matches
        if isinstance(match.get("path"), str) and category_for_path(str(match["path"])) == "source"
    ]
    fields: list[dict[str, Any]] = []
    for rel_path in schema_paths[: request.max_files]:
        if table_name:
            fields.extend(table_schema_fields(target_root, rel_path, table_name))
        if fields:
            break
    canonical_schema_paths = ["database/order.py", "database/schema.py", "models.py", "schema.py"]
    for rel_path in canonical_schema_paths:
        if fields or rel_path in schema_paths or not (target_root / rel_path).is_file():
            continue
        fields.extend(table_schema_fields(target_root, rel_path, table_name))
        if fields:
            schema_paths.insert(0, rel_path)
    if not fields:
        for path in sorted(target_root.rglob("*.py")):
            rel_path = path.relative_to(target_root).as_posix()
            lowered = rel_path.lower()
            if rel_path in schema_paths or not any(term in lowered for term in ("schema", "model", "database")):
                continue
            fields.extend(table_schema_fields(target_root, rel_path, table_name))
            if fields:
                schema_paths.insert(0, rel_path)
                break
    field_paths: list[str] = []
    field_source_refs: list[dict[str, Any]] = []
    seen_field_refs: set[tuple[str, int | None]] = set()
    for field in fields:
        path = field.get("path") if isinstance(field, dict) else None
        if not isinstance(path, str):
            continue
        append_unique(field_paths, path)
        line = field.get("line")
        ref_key = (path, line if isinstance(line, int) else None)
        if ref_key in seen_field_refs:
            continue
        seen_field_refs.add(ref_key)
        ref = {"path": path, "source": field.get("source") or "schema_field"}
        if isinstance(line, int):
            ref["line"] = line
        field_source_refs.append(ref)
    model_file_candidates: list[str] = []
    for rel_path in [*field_paths, *schema_paths]:
        append_unique(model_file_candidates, rel_path)
    model_files = model_file_candidates[: request.max_files]
    source_refs: list[dict[str, Any]] = []
    seen_source_refs: set[tuple[str, int | None, str]] = set()
    for ref in [
        *field_source_refs,
        *source_refs_from_records(evidence_file_records(model_files, [], matches)),
    ]:
        path = ref.get("path")
        if not isinstance(path, str):
            continue
        line = ref.get("line")
        source = ref.get("source")
        ref_key = (path, line if isinstance(line, int) else None, str(source))
        if ref_key in seen_source_refs:
            continue
        seen_source_refs.add(ref_key)
        source_refs.append(ref)
    if fields:
        status = "ready"
        reason = "Schema fields were extracted from a bounded table creation block."
    elif schema_paths:
        status = "partial"
        reason = "Schema-related source files were found, but no bounded table field block was extracted."
    else:
        status = "unknown"
        reason = "No schema source evidence was found in the bounded investigation."
    gaps = [] if fields else [{"gap": "schema_fields_not_extracted", "reason": reason}]
    if warnings:
        gaps.append({"gap": "fallback_or_warning_present", "warning_count": len(warnings)})
    return {
        "kind": "data_model_lookup",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "target": table_name,
        "field_count": len(fields),
        "fields": fields,
        "model_files": model_files,
        "source_refs": source_refs[:20],
        "mutation_policy": "read_only_no_source_mutation",
        "gaps": gaps,
        "reason": reason,
    }


def is_table_read_write_lookup_request(text: str) -> bool:
    lowered = text.lower()
    if any(term in lowered for term in ("add", "create", "implement", "fix failing", "fix test", "refactor", "apply", "mutate")):
        return False
    table_terms = ("database table", "table", "db table")
    access_terms = (
        "read and written",
        "reads and writes",
        "definition, reads, and writes",
        "definition reads and writes",
        "definition sites, read sites, write sites",
        "definition sites read sites write sites",
        "read/write",
        "read write",
        "defined, read, and written",
        "defined read and written",
    )
    return any(term in lowered for term in table_terms) and any(term in lowered for term in access_terms)


def table_access_role(text: str, table_name: str) -> str | None:
    lowered = text.lower()
    table = table_name.lower()
    if "create table" in lowered and table in lowered:
        return "definition"
    if re.search(rf"\b(?:insert\s+into|update|delete\s+from)\s+{re.escape(table)}\b", lowered):
        return "write"
    if re.search(rf"\b(?:from|join)\s+{re.escape(table)}\b", lowered) and "select" in lowered:
        return "read"
    if re.search(rf"\b{re.escape(table)}\b", lowered) and any(term in lowered for term in ("select", "fetch", "load", "query")):
        return "read"
    if re.search(rf"\b{re.escape(table)}\b", lowered) and any(term in lowered for term in ("insert", "update", "delete", "save")):
        return "write"
    return None


def table_access_sites(matches: list[dict[str, Any]], table_name: str) -> dict[str, list[dict[str, Any]]]:
    sites: dict[str, list[dict[str, Any]]] = {"definition": [], "read": [], "write": []}
    seen: set[tuple[str, int | None, str]] = set()
    for match in matches:
        path = match.get("path")
        text = match.get("text")
        if not isinstance(path, str) or not isinstance(text, str):
            continue
        if category_for_path(path) != "source":
            continue
        role = table_access_role(text, table_name)
        if role is None:
            continue
        line = match.get("line") if isinstance(match.get("line"), int) else None
        key = (path, line, role)
        if key in seen:
            continue
        seen.add(key)
        sites[role].append(
            {
                "path": path,
                "line": line,
                "role": role,
                "evidence": bounded_text(text, 320),
                "source": match.get("source") or "bounded_investigation",
            }
        )
    return {key: value[:20] for key, value in sites.items()}


def table_access_sites_from_files(
    target_root: Path,
    table_name: str,
    existing_sites: dict[str, list[dict[str, Any]]],
    *,
    max_files: int = TABLE_ACCESS_SCAN_FILE_LIMIT,
) -> dict[str, list[dict[str, Any]]]:
    sites = {role: list(existing_sites.get(role, [])) for role in ("definition", "read", "write")}
    seen: set[tuple[str, int | None, str]] = set()
    for role, role_sites in sites.items():
        for site in role_sites:
            path = site.get("path")
            line = site.get("line") if isinstance(site.get("line"), int) else None
            if isinstance(path, str):
                seen.add((path, line, role))
    scanned = 0
    for path in sorted(target_root.rglob("*")):
        if scanned >= max_files:
            break
        if not path.is_file() or path.suffix.lower() not in TABLE_ACCESS_SCAN_EXTENSIONS:
            continue
        try:
            rel_path = path.relative_to(target_root).as_posix()
        except ValueError:
            continue
        if any(part in IGNORED_SCAN_DIRS for part in path.parts):
            continue
        if category_for_path(rel_path) != "source":
            continue
        scanned += 1
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line_no, line in enumerate(lines, 1):
            role = table_access_role(line, table_name)
            if role is None and table_name.lower() in line.lower():
                context_start = max(0, line_no - 3)
                context_end = min(len(lines), line_no + 2)
                role = table_access_role(" ".join(lines[context_start:context_end]), table_name)
            if role is None:
                continue
            key = (rel_path, line_no, role)
            if key in seen:
                continue
            seen.add(key)
            sites[role].append(
                {
                    "path": rel_path,
                    "line": line_no,
                    "role": role,
                    "evidence": bounded_text(line.strip(), 320),
                    "source": "table_access_file_scan",
                }
            )
            if all(sites[item] for item in ("definition", "read", "write")):
                return {role_key: role_sites[:20] for role_key, role_sites in sites.items()}
    return {role_key: role_sites[:20] for role_key, role_sites in sites.items()}


def build_table_read_write_lookup(
    request: CodeInvestigationRequest,
    *,
    target_root: Path,
    queries: list[str],
    matches: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_table_read_write_lookup_request(request.user_request):
        return {"kind": "table_read_write_lookup", "schema_version": SCHEMA_VERSION, "status": "not_requested"}
    table_name = data_model_target_from_request(request.user_request, queries, request.behavior)
    sites = table_access_sites(matches, table_name)
    if not all(sites[role] for role in ("definition", "read", "write")):
        sites = table_access_sites_from_files(target_root, table_name, sites)
    gaps: list[dict[str, Any]] = []
    if not sites["definition"]:
        gaps.append({"gap": "table_definition_not_found"})
    if not sites["read"]:
        gaps.append({"gap": "table_read_site_not_found"})
    if not sites["write"]:
        gaps.append({"gap": "table_write_site_not_found"})
    if warnings:
        gaps.append({"gap": "fallback_or_warning_present", "warning_count": len(warnings)})
    all_sites = [site for role_sites in sites.values() for site in role_sites]
    status = "ready" if all_sites else "unknown"
    return {
        "kind": "table_read_write_lookup",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "target_table": table_name,
        "definition_sites": sites["definition"],
        "read_sites": sites["read"],
        "write_sites": sites["write"],
        "access_summary": {
            "definition_count": len(sites["definition"]),
            "read_count": len(sites["read"]),
            "write_count": len(sites["write"]),
        },
        "mutation_policy": "read_only_no_source_mutation",
        "source_refs": [
            {key: value for key, value in {"path": site.get("path"), "line": site.get("line"), "source": site.get("source")}.items() if value is not None}
            for site in all_sites[:20]
        ],
        "gaps": gaps,
    }


def is_coverage_gap_summary_request(text: str) -> bool:
    lowered = text.lower()
    coverage_terms = ("coverage gap", "coverage gaps", "test coverage", "covered tests", "uncovered")
    target_terms = ("test", "tests", "source", "behavior", "verification")
    return any(term in lowered for term in coverage_terms) and any(term in lowered for term in target_terms)


def build_coverage_gap_summary(
    request: CodeInvestigationRequest,
    *,
    queries: list[str],
    records: list[dict[str, Any]],
    related_tests: list[dict[str, Any]],
    verification_commands: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_coverage_gap_summary_request(request.user_request):
        return {"kind": "coverage_gap_summary", "schema_version": SCHEMA_VERSION, "status": "not_requested"}
    target = queries[0] if queries else request.behavior.strip()
    source_records = [record for record in records if record.get("category") == "source"]
    test_records = [record for record in records if record.get("category") == "test"]
    covered_tests = compact_related_tests(related_tests)
    for record in test_records:
        path = record.get("path")
        if isinstance(path, str) and not any(item.get("path") == path for item in covered_tests):
            covered_tests.append(
                {
                    "path": path,
                    "matched_terms": record.get("queries") if isinstance(record.get("queries"), list) else [],
                    "source": "bounded_investigation",
                }
            )
    source_files = [
        {
            "path": record.get("path"),
            "match_count": record.get("match_count", 0),
            "queries": record.get("queries") if isinstance(record.get("queries"), list) else [],
        }
        for record in source_records
        if isinstance(record.get("path"), str)
    ][: request.max_files]
    source_files_without_direct_tests = [
        record
        for record in source_files
        if not any(str(test.get("path", "")).startswith("tests/") for test in covered_tests)
    ]
    coverage_gaps: list[dict[str, Any]] = [
        {
            "gap": "line_or_branch_coverage_not_measured",
            "reason": "Bounded repository evidence found related tests, but it did not execute coverage instrumentation.",
        }
    ]
    if not covered_tests:
        coverage_gaps.append(
            {
                "gap": "related_tests_not_found",
                "reason": "No direct related tests were found in the bounded investigation.",
            }
        )
    if source_files_without_direct_tests:
        coverage_gaps.append(
            {
                "gap": "source_files_without_direct_test_evidence",
                "source_files": [item["path"] for item in source_files_without_direct_tests if isinstance(item.get("path"), str)],
            }
        )
    if warnings:
        coverage_gaps.append({"gap": "fallback_or_warning_present", "warning_count": len(warnings)})
    status = "ready" if source_files or covered_tests else "unknown"
    reason = (
        "Coverage gaps were summarized from bounded source, test, and verification evidence."
        if status == "ready"
        else "No bounded source or test coverage evidence was found."
    )
    return {
        "kind": "coverage_gap_summary",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "target": target,
        "source_files": source_files,
        "covered_tests": covered_tests[:20],
        "source_files_without_direct_tests": source_files_without_direct_tests,
        "coverage_gaps": coverage_gaps,
        "verification_commands": verification_commands,
        "source_refs": source_refs_from_records(source_records)[:20],
        "mutation_policy": "read_only_no_source_mutation",
        "reason": reason,
    }


def is_documentation_lookup_request(text: str) -> bool:
    lowered = text.lower()
    doc_terms = ("documentation", "docs", "readme", "documented")
    lookup_terms = ("find", "locate", "where", "which", "show")
    return any(term in lowered for term in doc_terms) and any(term in lowered for term in lookup_terms)


def build_documentation_lookup(
    request: CodeInvestigationRequest,
    *,
    queries: list[str],
    records: list[dict[str, Any]],
    matches: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_documentation_lookup_request(request.user_request):
        return {"kind": "documentation_lookup", "schema_version": SCHEMA_VERSION, "status": "not_requested"}
    target = queries[0] if queries else request.behavior.strip()
    docs: list[dict[str, Any]] = []
    seen: set[tuple[str, int | None, str]] = set()
    for match in matches:
        path = match.get("path")
        text = match.get("text")
        if not isinstance(path, str) or category_for_path(path) != "documentation":
            continue
        line = match.get("line") if isinstance(match.get("line"), int) else None
        snippet = bounded_text(text, 300) if isinstance(text, str) else ""
        key = (path, line, snippet)
        if key in seen:
            continue
        seen.add(key)
        docs.append(
            {
                "path": path,
                "line": line,
                "role": "documentation_match",
                "query": match.get("query") if isinstance(match.get("query"), str) else target,
                "snippet": snippet,
                "source": match.get("source") or "bounded_investigation",
            }
        )
    for record in records:
        path = record.get("path")
        if not isinstance(path, str) or category_for_path(path) != "documentation":
            continue
        if any(item.get("path") == path for item in docs):
            continue
        docs.append(
            {
                "path": path,
                "line": None,
                "role": "documentation_file",
                "query": target,
                "snippet": "",
                "source": "bounded_investigation",
            }
        )
    status = "ready" if docs else "unknown"
    reason = (
        "Documentation evidence was found in bounded documentation files."
        if docs
        else "No documentation evidence was found in the bounded investigation; absence is not proven."
    )
    gaps = [] if docs else [{"gap": "documentation_not_found_in_bounded_evidence", "reason": reason}]
    if warnings:
        gaps.append({"gap": "fallback_or_warning_present", "warning_count": len(warnings)})
    return {
        "kind": "documentation_lookup",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "target": target,
        "documentation_files": docs[:20],
        "documentation_count": len(docs),
        "source_refs": [
            {key: value for key, value in {"path": item.get("path"), "line": item.get("line"), "source": item.get("source")}.items() if value is not None}
            for item in docs[:20]
        ],
        "mutation_policy": "read_only_no_source_mutation",
        "gaps": gaps,
        "reason": reason,
    }


def is_cli_entrypoint_lookup_request(text: str) -> bool:
    lowered = text.lower()
    if is_test_failure_summary_request(text):
        return False
    has_cli_word = re.search(r"\bcli\b", lowered) is not None
    entry_terms = ("script", "entrypoint", "entry point", "main.py", "__main__", "run command")
    lookup_terms = ("find", "locate", "where", "which", "show", "command")
    return (has_cli_word or any(term in lowered for term in entry_terms)) and any(term in lowered for term in lookup_terms)


def python_entrypoint_records(target_root: Path, rel_path: str) -> list[dict[str, Any]]:
    path = target_root / rel_path
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(lines, 1):
        stripped = line.strip()
        if re.match(r"def\s+main\s*\(", stripped):
            records.append(
                {
                    "path": rel_path,
                    "line": line_no,
                    "kind": "python_main_function",
                    "command": f"python {rel_path}",
                    "evidence": bounded_text(stripped, 200),
                    "source": "file_scan",
                }
            )
        if "__name__" in stripped and "__main__" in stripped:
            records.append(
                {
                    "path": rel_path,
                    "line": line_no,
                    "kind": "python_main_guard",
                    "command": f"python {rel_path}",
                    "evidence": bounded_text(stripped, 200),
                    "source": "file_scan",
                }
            )
    if not records and Path(rel_path).name == "main.py":
        records.append(
            {
                "path": rel_path,
                "line": None,
                "kind": "python_main_module",
                "command": f"python {rel_path}",
                "evidence": "File name is main.py.",
                "source": "path_name",
            }
        )
    return records[:10]


def build_cli_entrypoint_lookup(
    request: CodeInvestigationRequest,
    *,
    target_root: Path,
    selected_paths: list[str],
    queries: list[str],
    records: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_cli_entrypoint_lookup_request(request.user_request):
        return {"kind": "cli_entrypoint_lookup", "schema_version": SCHEMA_VERSION, "status": "not_requested"}
    target = queries[0] if queries else request.behavior.strip()
    if "main.py" in request.user_request.lower():
        target = "main.py"
    candidate_paths: list[str] = []
    for rel_path in selected_paths:
        if rel_path.endswith(".py"):
            append_unique(candidate_paths, rel_path, limit=request.max_files)
    for record in records:
        path = record.get("path")
        if isinstance(path, str) and path.endswith(".py"):
            append_unique(candidate_paths, path, limit=request.max_files)
    if (target_root / "main.py").is_file():
        append_unique(candidate_paths, "main.py", limit=request.max_files)
    entrypoints: list[dict[str, Any]] = []
    for rel_path in candidate_paths[: request.max_files]:
        for entrypoint in python_entrypoint_records(target_root, rel_path):
            if not any(item.get("path") == entrypoint.get("path") and item.get("line") == entrypoint.get("line") for item in entrypoints):
                entrypoints.append(entrypoint)
    status = "ready" if entrypoints else "unknown"
    reason = (
        "CLI or script entrypoint evidence was found in bounded Python files."
        if entrypoints
        else "No CLI or script entrypoint evidence was found in bounded files."
    )
    gaps = [] if entrypoints else [{"gap": "entrypoint_not_found", "reason": reason}]
    if warnings:
        gaps.append({"gap": "fallback_or_warning_present", "warning_count": len(warnings)})
    return {
        "kind": "cli_entrypoint_lookup",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "target": target,
        "entrypoint_count": len(entrypoints),
        "entrypoints": entrypoints[:20],
        "source_refs": [
            {key: value for key, value in {"path": item.get("path"), "line": item.get("line"), "source": item.get("source")}.items() if value is not None}
            for item in entrypoints[:20]
        ],
        "mutation_policy": "read_only_no_source_mutation",
        "gaps": gaps,
        "reason": reason,
    }


def is_configuration_effect_summary_request(text: str) -> bool:
    lowered = text.lower()
    if "defined or used" in lowered or "find where" in lowered:
        return False
    config_terms = ("config", "configuration", "setting", "env var", "environment variable", "coinbase_api_key")
    effect_terms = (
        "runtime effect of",
        "affect at runtime",
        "affects at runtime",
        "what does it affect",
        "explain",
        "used by",
        "does at runtime",
    )
    return any(term in lowered for term in config_terms) and any(term in lowered for term in effect_terms)


def configuration_effect_role(query: str, path: str, text: str) -> str:
    stripped = text.strip()
    if "getenv(" in stripped or "os.environ" in stripped:
        return "environment_read"
    if "RESTClient" in stripped or "api_key=" in stripped or "api_secret=" in stripped:
        return "client_configuration_input"
    if "from configuration import" in stripped or "import configuration" in stripped:
        return "runtime_consumer"
    return config_reference_role(query, path, text)


def build_configuration_effect_summary(
    request: CodeInvestigationRequest,
    *,
    target_root: Path,
    selected_paths: list[str],
    queries: list[str],
    matches: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_configuration_effect_summary_request(request.user_request):
        return {"kind": "configuration_effect_summary", "schema_version": SCHEMA_VERSION, "status": "not_requested"}
    target = queries[0] if queries else request.behavior.strip()
    candidate_paths: list[str] = []
    for match in matches:
        path = match.get("path")
        if isinstance(path, str):
            append_unique(candidate_paths, path, limit=request.max_files)
    for rel_path in selected_paths:
        append_unique(candidate_paths, rel_path, limit=request.max_files)
    if (target_root / "configuration.py").is_file():
        append_unique(candidate_paths, "configuration.py", limit=request.max_files)
    references: list[dict[str, Any]] = []
    seen: set[tuple[str, int | None, str]] = set()
    target_aliases = {target}
    if target.startswith("COINBASE_"):
        target_aliases.add(target.removeprefix("COINBASE_"))
    for rel_path in candidate_paths[: request.max_files]:
        path = target_root / rel_path
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line_no, line in enumerate(lines, 1):
            if not any(alias and alias in line for alias in target_aliases) and "RESTClient" not in line:
                continue
            role = configuration_effect_role(target, rel_path, line)
            key = (rel_path, line_no, line.strip())
            if key in seen:
                continue
            seen.add(key)
            reference = {
                "path": rel_path,
                "line": line_no,
                "role": role,
                "query": target,
                "text": bounded_text(line, 300),
                "source": "file_scan",
            }
            value = visible_config_value(target, role, line)
            if value is not None:
                reference["current_value"] = value
            references.append(reference)
    runtime_effects: list[dict[str, Any]] = []
    if any(item.get("role") == "environment_read" for item in references):
        runtime_effects.append(
            {
                "effect": "environment_read",
                "summary": "Runtime reads the value from the process environment; the secret value is not visible in source.",
            }
        )
    if any(item.get("role") == "client_configuration_input" for item in references):
        runtime_effects.append(
            {
                "effect": "client_configuration_input",
                "summary": "The configuration value flows into client construction or authentication-related parameters.",
            }
        )
    if any(item.get("role") == "runtime_consumer" for item in references):
        runtime_effects.append(
            {
                "effect": "runtime_consumer",
                "summary": "Runtime code imports or consumes the configuration value.",
            }
        )
    if references and not runtime_effects:
        runtime_effects.append(
            {
                "effect": "configuration_reference",
                "summary": "The setting is referenced in bounded source evidence; inspect nearby code for exact runtime precedence.",
            }
        )
    status = "ready" if references else "unknown"
    reason = (
        "Configuration runtime effects were summarized from bounded source references."
        if references
        else "No configuration runtime-effect evidence was found in bounded source references."
    )
    gaps = [] if references else [{"gap": "configuration_effect_not_found", "reason": reason}]
    if warnings:
        gaps.append({"gap": "fallback_or_warning_present", "warning_count": len(warnings)})
    return {
        "kind": "configuration_effect_summary",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "target": target,
        "references": references[:30],
        "runtime_effects": runtime_effects,
        "source_refs": [
            {key: value for key, value in {"path": item.get("path"), "line": item.get("line"), "source": item.get("source")}.items() if value is not None}
            for item in references[:20]
        ],
        "mutation_policy": "read_only_no_source_mutation",
        "gaps": gaps,
        "reason": reason,
    }


def is_local_change_summary_request(text: str) -> bool:
    lowered = text.lower()
    return any(
        term in lowered
        for term in (
            "recent changes",
            "local changes",
            "git status",
            "changed files",
            "recent commits",
            "what changed",
        )
    )


def run_read_only_git(target_root: Path, args: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(target_root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "failed", "args": args, "returncode": None, "stdout": "", "stderr": str(exc)}
    return {
        "status": "ok" if completed.returncode == 0 else "failed",
        "args": args,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def changed_files_from_status(status_output: str) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for line in status_output.splitlines():
        if not line.strip():
            continue
        status = line[:2].strip() or "unknown"
        path = line[3:].strip() if len(line) > 3 else line.strip()
        if not path:
            continue
        files.append({"path": path, "status": status})
    return files


def build_local_change_summary(
    request: CodeInvestigationRequest,
    *,
    target_root: Path,
) -> dict[str, Any]:
    if not is_local_change_summary_request(request.user_request):
        return {"kind": "local_change_summary", "schema_version": SCHEMA_VERSION, "status": "not_requested"}
    if not (target_root / ".git").exists():
        reason = "Target root is not a git repository, so local git status and recent commit history are unavailable."
        return {
            "kind": "local_change_summary",
            "schema_version": SCHEMA_VERSION,
            "status": "limited_non_git",
            "target": str(target_root),
            "git_status": "not_available_non_git_target",
            "recent_commits": [],
            "changed_files": [],
            "diff_stat": "",
            "mutation_policy": "read_only_no_source_mutation",
            "gaps": [{"gap": "git_history_unavailable", "reason": reason}],
            "reason": reason,
        }
    status_result = run_read_only_git(target_root, ["status", "--short", "--untracked-files=no"])
    log_result = run_read_only_git(target_root, ["log", "--oneline", "-5"])
    diff_result = run_read_only_git(target_root, ["diff", "--stat", "--"])
    status_output = str(status_result.get("stdout") or "").strip()
    log_output = str(log_result.get("stdout") or "").strip()
    diff_output = str(diff_result.get("stdout") or "").strip()
    changed_files = changed_files_from_status(status_output)
    recent_commits = [
        {"summary": bounded_text(line, 240)}
        for line in log_output.splitlines()
        if line.strip()
    ]
    command_errors = [
        result
        for result in (status_result, log_result, diff_result)
        if result.get("status") != "ok"
    ]
    status = "ready" if not command_errors else "partial"
    reason = (
        "Local change summary was produced from non-mutating git status, log, and diff commands."
        if status == "ready"
        else "Some non-mutating git commands failed; returned partial local-change evidence."
    )
    gaps = [{"gap": "git_command_failed", "commands": command_errors}] if command_errors else []
    return {
        "kind": "local_change_summary",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "target": str(target_root),
        "git_status": status_output or "clean",
        "recent_commits": recent_commits[:5],
        "changed_files": changed_files[:50],
        "diff_stat": diff_output,
        "mutation_policy": "read_only_no_source_mutation",
        "source_refs": [{"path": ".", "source": "git_status"}],
        "gaps": gaps,
        "reason": reason,
    }


def is_test_failure_summary_request(text: str) -> bool:
    lowered = text.lower()
    if any(term in lowered for term in ("fix failing", "fix this test", "fix test", "update test")):
        return False
    if is_ci_failure_summary_request(text):
        return False
    if is_runtime_error_diagnosis_request(text) and not any(
        term in lowered
        for term in (
            "test failure",
            "pytest failure",
            "failing test",
            "failed tests/",
            "failed test_",
            "assertionerror",
        )
    ):
        return False
    failure_terms = (
        "pasted test failure",
        "test failure",
        "pytest failure",
        "failed ",
        "traceback",
        "assertionerror",
        "modulenotfounderror",
        "importerror",
    )
    summary_terms = ("summarize", "summary", "what failed", "likely cause", "next inspection", "next bounded")
    investigation_terms = (
        "diagnose",
        "investigate",
        "root cause",
        "why did",
        "why does",
        "why is",
        "what caused",
        "safe fix plan",
        "smallest safe fix",
        "proposed fix",
        "verification command",
    )
    return any(term in lowered for term in failure_terms) and any(
        term in lowered for term in (*summary_terms, *investigation_terms)
    )


def extract_failed_tests(text: str) -> list[dict[str, Any]]:
    failed: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        match = re.search(r"\bFAILED\s+([^\s]+?\.py(?:::[^\s]+)?)", stripped)
        if not match:
            continue
        target = match.group(1)
        path, _, test_name = target.partition("::")
        record = {"raw": bounded_text(stripped, 500), "path": path}
        if test_name:
            record["test_name"] = test_name
        failed.append(record)
    return failed


def extract_failure_error(text: str) -> dict[str, Any]:
    for line in text.splitlines():
        stripped = line.strip()
        match = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))\b:?\s*(.*)$", stripped)
        if match:
            return {
                "type": match.group(1),
                "message": bounded_text(match.group(2), 500) if match.group(2) else None,
                "raw": bounded_text(stripped, 500),
            }
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("E   "):
            return {"type": "pytest_error_line", "message": bounded_text(stripped[4:], 500), "raw": bounded_text(stripped, 500)}
    return {"type": None, "message": None, "raw": None}


def likely_failure_cause(error: dict[str, Any]) -> str:
    error_type = error.get("type")
    if error_type == "AssertionError":
        return "The failing assertion observed an unexpected value; inspect the asserted expectation and the code path that produced the actual value."
    if error_type in {"ModuleNotFoundError", "ImportError"}:
        return "The test could not import required code; inspect import paths, package configuration, and renamed modules before editing behavior."
    if isinstance(error_type, str) and error_type.endswith("Error"):
        return f"The failure raised {error_type}; inspect the traceback frame closest to project code before planning a fix."
    return "The pasted output did not expose a specific error type; inspect the failing test and nearest traceback frame first."


def failure_root_cause_hypothesis(error: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    message = str(error.get("message") or "").lower()
    source_paths = [
        str(record.get("path"))
        for record in records
        if record.get("category") == "source" and isinstance(record.get("path"), str)
    ]
    if "docstring" in message and "client_order_id" in message:
        summary = (
            "The failing assertion expects the public function documentation to name the client_order_id lookup contract, "
            "but the current evidence points to a missing or stale docstring detail."
        )
        confidence = "medium"
    elif "client_order_id" in message and "index" in message:
        summary = (
            "The failure is centered on the client_order_id index expectation; inspect the lookup implementation and test "
            "assertion before changing behavior."
        )
        confidence = "medium"
    elif error.get("type") == "AssertionError":
        summary = (
            "The assertion failed after project code returned or described a value different from the test expectation. "
            "The safest next step is to compare the exact assertion with the source path that owns the behavior."
        )
        confidence = "low"
    else:
        summary = likely_failure_cause(error)
        confidence = "low"
    return {
        "summary": summary,
        "confidence": confidence,
        "evidence_files": source_paths[:5],
    }


def failed_test_verification_commands(
    failed_tests: list[dict[str, Any]],
    verification_commands: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for failed in failed_tests:
        path = failed.get("path")
        if not isinstance(path, str) or not path:
            continue
        test_name = failed.get("test_name")
        pytest_target = f"{path}::{test_name}" if isinstance(test_name, str) and test_name else path
        command = ("python", "-m", "pytest", pytest_target)
        if command in seen:
            continue
        commands.append(
            {
                "id": f"failing-test-verification-{len(commands) + 1:04d}",
                "command": list(command),
                "reason": "Run the exact failing pytest node after reviewing the proposed fix plan.",
                "associated_files": [path],
                "timeout_seconds": 300,
            }
        )
        seen.add(command)
    for item in verification_commands:
        if not isinstance(item, dict) or not isinstance(item.get("command"), list):
            continue
        command_tuple = tuple(str(part) for part in item["command"])
        if command_tuple in seen:
            continue
        commands.append(item)
        seen.add(command_tuple)
    return commands[:5]


def smallest_safe_fix_plan(
    failed_tests: list[dict[str, Any]],
    error: dict[str, Any],
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source_paths = [
        str(record.get("path"))
        for record in records
        if record.get("category") == "source" and isinstance(record.get("path"), str)
    ]
    failed_path = failed_tests[0].get("path") if failed_tests else None
    message = str(error.get("message") or "").lower()
    target = source_paths[0] if source_paths else failed_path
    if "docstring" in message and isinstance(target, str):
        return [
            {
                "step": "Open the failing assertion and confirm the expected docstring wording.",
                "path": failed_path,
            },
            {
                "step": "Update only the documented contract text for the target function if the implementation behavior is already correct.",
                "path": target,
            },
            {
                "step": "Run the exact failing pytest node before broadening validation.",
                "path": failed_path,
            },
        ]
    return [
        {
            "step": "Open the failing assertion and identify the expected value or behavior.",
            "path": failed_path,
        },
        {
            "step": "Inspect the smallest source file that owns the behavior before drafting a change.",
            "path": target,
        },
        {
            "step": "Prefer a one-file behavior fix and run the exact failing pytest node before broader tests.",
            "path": failed_path,
        },
    ]


def is_ci_failure_summary_request(text: str) -> bool:
    lowered = text.lower()
    if any(term in lowered for term in ("fix failing", "fix this test", "fix test", "update test", "apply", "mutate")):
        return False
    ci_terms = (
        "ci log",
        "failing ci",
        "github actions",
        "workflow run",
        "ci failure",
        "pipeline failure",
        "build log",
    )
    output_terms = (
        "first failing command",
        "likely cause",
        "next local command",
        "summarize",
        "summary",
    )
    return any(term in lowered for term in ci_terms) and any(term in lowered for term in output_terms)


def extract_ci_commands(text: str) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    command_patterns = (
        r"\bpython\s+-m\s+pytest\b.*",
        r"\bpytest\b.*",
        r"\bnpm\s+(?:run\s+)?(?:test|build)\b.*",
        r"\bpnpm\s+(?:test|build)\b.*",
        r"\byarn\s+(?:test|build)\b.*",
        r"\b(?:ruff|mypy|tsc|vite)\b.*",
    )
    for index, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        raw_command = None
        if stripped.lower().startswith("run "):
            raw_command = stripped[4:].strip()
        elif stripped.startswith(("$", ">")):
            raw_command = stripped[1:].strip()
        else:
            for pattern in command_patterns:
                match = re.search(pattern, stripped)
                if match:
                    raw_command = match.group(0).strip()
                    break
        if not raw_command:
            continue
        if raw_command.lower().startswith("failed "):
            continue
        commands.append(
            {
                "command": raw_command,
                "line": index,
                "source": "ci_log",
            }
        )
    return commands[:10]


def ci_primary_error(text: str) -> dict[str, Any]:
    error = extract_failure_error(text)
    if error.get("type"):
        return error
    for line in text.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if not stripped:
            continue
        if "exit code" in lowered or lowered.startswith(("error:", "error ", "failed ")):
            return {"type": "ci_failure_line", "message": bounded_text(stripped, 500), "raw": bounded_text(stripped, 500)}
    return {"type": None, "message": None, "raw": None}


def ci_next_local_command(
    commands: list[dict[str, Any]],
    failed_tests: list[dict[str, Any]],
    verification_commands: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if failed_tests:
        generated = failed_test_verification_commands(failed_tests, verification_commands)
        if generated:
            return generated[0]
    if commands:
        return {
            "command": str(commands[0]["command"]).split(),
            "reason": "Re-run the first failing CI command locally before broadening validation.",
            "associated_files": [],
            "timeout_seconds": 300,
        }
    for command in verification_commands:
        if isinstance(command, dict) and isinstance(command.get("command"), list):
            return command
    return None


def build_ci_failure_summary(
    request: CodeInvestigationRequest,
    *,
    records: list[dict[str, Any]],
    verification_commands: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_ci_failure_summary_request(request.user_request):
        return {"kind": "ci_failure_summary", "schema_version": SCHEMA_VERSION, "status": "not_requested"}
    commands = extract_ci_commands(request.user_request)
    failed_tests = extract_failed_tests(request.user_request)
    error = ci_primary_error(request.user_request)
    next_command = ci_next_local_command(commands, failed_tests, verification_commands)
    evidence_records = [
        record
        for record in records
        if int(record.get("match_count") or 0) > 0
        or any(record.get("path") == failed.get("path") for failed in failed_tests)
    ]
    gaps: list[dict[str, Any]] = []
    if not commands:
        gaps.append({"gap": "first_failing_command_not_found"})
    if not next_command:
        gaps.append({"gap": "next_local_command_not_found"})
    if not error.get("type"):
        gaps.append({"gap": "primary_ci_error_not_found"})
    status = "ready" if commands or failed_tests or error.get("type") else "unknown"
    return {
        "kind": "ci_failure_summary",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "first_failing_command": commands[0] if commands else None,
        "observed_commands": commands,
        "failed_tests": failed_tests,
        "primary_error": error,
        "likely_cause": likely_failure_cause(error),
        "next_local_command": next_command,
        "evidence_files": compact_evidence_records(evidence_records[: request.max_files]),
        "mutation_policy": "read_only_no_source_mutation",
        "source_refs": source_refs_from_records(evidence_records[: request.max_files]),
        "gaps": gaps,
    }


def build_test_failure_summary(
    request: CodeInvestigationRequest,
    *,
    records: list[dict[str, Any]],
    verification_commands: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_test_failure_summary_request(request.user_request):
        return {"kind": "test_failure_summary", "schema_version": SCHEMA_VERSION, "status": "not_requested"}
    failed_tests = extract_failed_tests(request.user_request)
    error = extract_failure_error(request.user_request)
    status = "ready" if failed_tests or error.get("type") else "unknown"
    next_steps: list[dict[str, Any]] = []
    if failed_tests:
        first = failed_tests[0]
        next_steps.append(
            {
                "step": "Inspect the failing test body and its fixtures.",
                "path": first.get("path"),
                "test_name": first.get("test_name"),
            }
        )
    next_steps.append(
        {
            "step": "Inspect the nearest project-code traceback frame or exact assertion input before drafting any fix.",
            "path": None,
        }
    )
    source_records = [
        record
        for record in records
        if any(record.get("path") == failed.get("path") for failed in failed_tests)
        or int(record.get("match_count") or 0) > 0
    ]
    commands = failed_test_verification_commands(failed_tests, verification_commands)
    return {
        "kind": "test_failure_summary",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "failed_tests": failed_tests,
        "primary_error": error,
        "likely_cause": likely_failure_cause(error),
        "root_cause_hypothesis": failure_root_cause_hypothesis(error, source_records[:10]),
        "smallest_safe_fix_plan": smallest_safe_fix_plan(failed_tests, error, source_records[:10]),
        "verification_commands": commands,
        "mutation_policy": "read_only_no_source_mutation",
        "next_inspection_steps": next_steps,
        "source_refs": source_refs_from_records(source_records[:10]),
        "gaps": [] if status == "ready" else [{"gap": "failure_details_not_found"}],
    }


def investigation_gaps(
    beginning_point: dict[str, Any],
    records: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    related_test_count: int = 0,
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    if beginning_point.get("status") == "insufficient_evidence":
        gaps.append({"gap": "entrypoint_unresolved", "reason": beginning_point.get("reason")})
    if not any(record.get("category") == "test" for record in records) and related_test_count == 0:
        gaps.append({"gap": "tests_not_found", "reason": "No test file references were found in bounded evidence."})
    if not any(record.get("category") == "source" for record in records):
        gaps.append({"gap": "source_files_not_found", "reason": "No source file references were found in bounded evidence."})
    if warnings:
        gaps.append({"gap": "fallback_or_warning_present", "warning_count": len(warnings)})
    return gaps


def invoke_code_investigation(request: CodeInvestigationRequest) -> InvocationResult:
    validation = validate_request_basics(request)
    target_root = Path(request.target_root).resolve()
    output_root = Path(request.output_root).resolve()
    run_id = f"code-investigation-{artifact_timestamp()}"
    run_dir = output_root / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {}
    warnings: list[dict[str, Any]] = []
    tools = set(validation["tools"])

    hints = normalize_entrypoint_hints(request, target_root)
    queries = query_candidates(request, hints)
    if not queries and not request.paths and not hints:
        raise CodeInvestigationError("Unable to derive a bounded lookup query. Provide queries, paths, or entrypoint_hints.")

    request_artifact = {
        "kind": "code_investigation_request",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "target_root": str(target_root),
        "user_request": request.user_request,
        "behavior": request.behavior,
        "queries": queries,
        "paths": request.paths,
        "entrypoint_hints": hints,
        "allowed_context_tools": sorted(tools),
        "created_at": utc_now(),
    }
    write_json(run_dir / "request.json", request_artifact)
    artifacts["request"] = str(run_dir / "request.json")

    matches: list[dict[str, Any]] = []
    if request.include_grep and "git_grep" in tools and queries:
        matches, grep_warnings = collect_grep_matches(target_root, queries, request.max_results)
        warnings.extend(grep_warnings)
    selected_paths = collect_paths(request, target_root, hints, matches)
    snippets: list[dict[str, Any]] = []
    if request.include_file_snippets and selected_paths and "read_file" in tools:
        snippets = file_snippets(target_root, selected_paths, request.max_files)
    structure: dict[str, Any] | None = None
    if request.include_structure and "structure_index" in tools:
        structure, structure_warnings = structure_slice(target_root, selected_paths, request.max_results)
        warnings.extend(structure_warnings)

    records = evidence_file_records(selected_paths, hints, matches)
    if not request.include_tests:
        records = [record for record in records if record.get("category") != "test"]
    beginning = likely_beginning_point(records, hints)
    path_assessment = multiple_path_assessment(records)
    test_refs = [record for record in records if record.get("category") == "test"]
    source_refs = [record for record in records if record.get("category") == "source"]
    related_test_context = (
        discover_related_tests_from_values(
            target_root,
            [
                request.user_request,
                request.behavior,
                *queries,
                *request.paths,
                *[str(record.get("path")) for record in source_refs if isinstance(record.get("path"), str)],
            ],
            request.max_files,
        )
        if request.include_tests
        else None
    )
    related_tests = (
        related_test_context.get("related_test_files", [])
        if isinstance(related_test_context, dict) and isinstance(related_test_context.get("related_test_files"), list)
        else []
    )
    verification_commands = controller_verification_commands(
        {"results": [related_test_context] if related_test_context is not None else []}
    )
    related_test_paths = [
        item["path"]
        for item in related_tests
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    ]
    code_explanation = build_code_explanation(
        request,
        target_root=target_root,
        selected_paths=selected_paths,
        queries=queries,
        records=records,
        snippets=snippets,
        beginning=beginning,
        related_tests=related_tests,
    )
    if code_explanation.get("status") != "not_requested":
        write_json(run_dir / "code-explanation.json", code_explanation)
        artifacts["code_explanation"] = str(run_dir / "code-explanation.json")
    behavior_existence = build_behavior_existence(
        request,
        queries=queries,
        records=records,
        matches=matches,
        related_tests=related_tests,
        warnings=warnings,
    )
    if behavior_existence.get("status") != "not_requested":
        write_json(run_dir / "behavior-existence.json", behavior_existence)
        artifacts["behavior_existence"] = str(run_dir / "behavior-existence.json")
    configuration_lookup = build_configuration_lookup(
        request,
        queries=queries,
        matches=matches,
        warnings=warnings,
    )
    if configuration_lookup.get("status") != "not_requested":
        write_json(run_dir / "configuration-lookup.json", configuration_lookup)
        artifacts["configuration_lookup"] = str(run_dir / "configuration-lookup.json")
    endpoint_route_lookup = build_endpoint_route_lookup(
        request,
        queries=queries,
        matches=matches,
        related_tests=related_tests,
        warnings=warnings,
    )
    if endpoint_route_lookup.get("status") != "not_requested":
        write_json(run_dir / "endpoint-route-lookup.json", endpoint_route_lookup)
        artifacts["endpoint_route_lookup"] = str(run_dir / "endpoint-route-lookup.json")
    message_source_lookup = build_message_source_lookup(
        request,
        queries=queries,
        matches=matches,
        warnings=warnings,
        related_tests=related_tests,
        verification_commands=verification_commands,
    )
    if message_source_lookup.get("status") != "not_requested":
        write_json(run_dir / "message-source-lookup.json", message_source_lookup)
        artifacts["message_source_lookup"] = str(run_dir / "message-source-lookup.json")
    module_summary = build_module_summary(
        request,
        target_root=target_root,
        selected_paths=selected_paths,
        queries=queries,
        related_tests=related_tests,
    )
    if module_summary.get("status") != "not_requested":
        write_json(run_dir / "module-summary.json", module_summary)
        artifacts["module_summary"] = str(run_dir / "module-summary.json")
    data_model_lookup = build_data_model_lookup(
        request,
        target_root=target_root,
        queries=queries,
        matches=matches,
        warnings=warnings,
    )
    if data_model_lookup.get("status") != "not_requested":
        write_json(run_dir / "data-model-lookup.json", data_model_lookup)
        artifacts["data_model_lookup"] = str(run_dir / "data-model-lookup.json")
    table_read_write_lookup = build_table_read_write_lookup(
        request,
        target_root=target_root,
        queries=queries,
        matches=matches,
        warnings=warnings,
    )
    if table_read_write_lookup.get("status") != "not_requested":
        write_json(run_dir / "table-read-write-lookup.json", table_read_write_lookup)
        artifacts["table_read_write_lookup"] = str(run_dir / "table-read-write-lookup.json")
    coverage_gap_summary = build_coverage_gap_summary(
        request,
        queries=queries,
        records=records,
        related_tests=related_tests,
        verification_commands=verification_commands,
        warnings=warnings,
    )
    if coverage_gap_summary.get("status") != "not_requested":
        write_json(run_dir / "coverage-gap-summary.json", coverage_gap_summary)
        artifacts["coverage_gap_summary"] = str(run_dir / "coverage-gap-summary.json")
    documentation_lookup = build_documentation_lookup(
        request,
        queries=queries,
        records=records,
        matches=matches,
        warnings=warnings,
    )
    if documentation_lookup.get("status") != "not_requested":
        write_json(run_dir / "documentation-lookup.json", documentation_lookup)
        artifacts["documentation_lookup"] = str(run_dir / "documentation-lookup.json")
    cli_entrypoint_lookup = build_cli_entrypoint_lookup(
        request,
        target_root=target_root,
        selected_paths=selected_paths,
        queries=queries,
        records=records,
        warnings=warnings,
    )
    if cli_entrypoint_lookup.get("status") != "not_requested":
        write_json(run_dir / "cli-entrypoint-lookup.json", cli_entrypoint_lookup)
        artifacts["cli_entrypoint_lookup"] = str(run_dir / "cli-entrypoint-lookup.json")
    configuration_effect_summary = build_configuration_effect_summary(
        request,
        target_root=target_root,
        selected_paths=selected_paths,
        queries=queries,
        matches=matches,
        warnings=warnings,
    )
    if configuration_effect_summary.get("status") != "not_requested":
        write_json(run_dir / "configuration-effect-summary.json", configuration_effect_summary)
        artifacts["configuration_effect_summary"] = str(run_dir / "configuration-effect-summary.json")
    local_change_summary = build_local_change_summary(
        request,
        target_root=target_root,
    )
    if local_change_summary.get("status") != "not_requested":
        write_json(run_dir / "local-change-summary.json", local_change_summary)
        artifacts["local_change_summary"] = str(run_dir / "local-change-summary.json")
    ci_failure_summary = build_ci_failure_summary(
        request,
        records=records,
        verification_commands=verification_commands,
    )
    if ci_failure_summary.get("status") != "not_requested":
        write_json(run_dir / "ci-failure-summary.json", ci_failure_summary)
        artifacts["ci_failure_summary"] = str(run_dir / "ci-failure-summary.json")
    test_failure_summary = build_test_failure_summary(
        request,
        records=records,
        verification_commands=verification_commands,
    )
    if test_failure_summary.get("status") != "not_requested":
        write_json(run_dir / "test-failure-summary.json", test_failure_summary)
        artifacts["test_failure_summary"] = str(run_dir / "test-failure-summary.json")
    gaps = investigation_gaps(beginning, records, warnings, len(related_test_paths))
    multi_file_behavior_investigation = build_multi_file_behavior_investigation(
        request,
        beginning=beginning,
        records=records,
        related_tests=related_tests,
        path_assessment=path_assessment,
        verification_commands=verification_commands,
        gaps=gaps,
        warnings=warnings,
    )
    if multi_file_behavior_investigation.get("status") != "not_requested":
        write_json(run_dir / "multi-file-behavior-investigation.json", multi_file_behavior_investigation)
        artifacts["multi_file_behavior_investigation"] = str(run_dir / "multi-file-behavior-investigation.json")
    dependency_impact_summary = build_dependency_impact_summary(
        request,
        records=records,
        related_tests=related_tests,
        path_assessment=path_assessment,
        verification_commands=verification_commands,
        gaps=gaps,
        warnings=warnings,
    )
    if dependency_impact_summary.get("status") != "not_requested":
        write_json(run_dir / "dependency-impact-summary.json", dependency_impact_summary)
        artifacts["dependency_impact_summary"] = str(run_dir / "dependency-impact-summary.json")
    test_selection_plan = build_test_selection_plan(
        request,
        related_tests=related_tests,
        verification_commands=verification_commands,
        gaps=gaps,
    )
    if test_selection_plan.get("status") != "not_requested":
        write_json(run_dir / "test-selection-plan.json", test_selection_plan)
        artifacts["test_selection_plan"] = str(run_dir / "test-selection-plan.json")
    runtime_error_diagnosis = build_runtime_error_diagnosis(
        request,
        records=records,
        related_tests=related_tests,
        verification_commands=verification_commands,
        gaps=gaps,
        warnings=warnings,
    )
    if runtime_error_diagnosis.get("status") != "not_requested":
        write_json(run_dir / "runtime-error-diagnosis.json", runtime_error_diagnosis)
        artifacts["runtime_error_diagnosis"] = str(run_dir / "runtime-error-diagnosis.json")
    reproduction_checklist = build_reproduction_checklist(
        request,
        runtime_error_diagnosis=runtime_error_diagnosis,
        related_tests=related_tests,
        verification_commands=verification_commands,
        gaps=gaps,
    )
    if reproduction_checklist.get("status") != "not_requested":
        write_json(run_dir / "reproduction-checklist.json", reproduction_checklist)
        artifacts["reproduction_checklist"] = str(run_dir / "reproduction-checklist.json")
    request_flow_map = build_request_flow_map(
        request,
        beginning=beginning,
        records=records,
        related_tests=related_tests,
        verification_commands=verification_commands,
        gaps=gaps,
        warnings=warnings,
    )
    if request_flow_map.get("status") != "not_requested":
        write_json(run_dir / "request-flow-map.json", request_flow_map)
        artifacts["request_flow_map"] = str(run_dir / "request-flow-map.json")
    code_path_comparison = build_code_path_comparison(
        request,
        records=records,
        related_tests=related_tests,
        verification_commands=verification_commands,
        gaps=gaps,
    )
    if code_path_comparison.get("status") != "not_requested":
        write_json(run_dir / "code-path-comparison.json", code_path_comparison)
        artifacts["code_path_comparison"] = str(run_dir / "code-path-comparison.json")
    change_surface_summary = build_change_surface_summary(
        request,
        records=records,
        related_tests=related_tests,
        verification_commands=verification_commands,
        gaps=gaps,
        warnings=warnings,
    )
    if change_surface_summary.get("status") != "not_requested":
        write_json(run_dir / "change-surface-summary.json", change_surface_summary)
        artifacts["change_surface_summary"] = str(run_dir / "change-surface-summary.json")

    evidence = {
        "kind": "code_investigation_evidence",
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "target_root": str(target_root),
        "queries": queries,
        "selected_paths": selected_paths,
        "entrypoint_hints": hints,
        "grep_matches": matches,
        "file_snippets": snippets,
        "structure": structure,
        "participating_files": records,
        "related_test_context": related_test_context,
        "warnings": warnings,
    }
    write_json(run_dir / "investigation-evidence.json", evidence)
    artifacts["investigation_evidence"] = str(run_dir / "investigation-evidence.json")

    plan = {
        "kind": "code_investigation_plan",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "target_root": str(target_root),
        "user_request": request.user_request,
        "behavior": request.behavior,
        "likely_beginning_point": beginning,
        "participating_files": records,
        "test_references": test_refs,
        "related_tests": related_tests,
        "code_explanation": code_explanation,
        "behavior_existence": behavior_existence,
        "configuration_lookup": configuration_lookup,
        "endpoint_route_lookup": endpoint_route_lookup,
        "message_source_lookup": message_source_lookup,
        "module_summary": module_summary,
        "data_model_lookup": data_model_lookup,
        "table_read_write_lookup": table_read_write_lookup,
        "coverage_gap_summary": coverage_gap_summary,
        "documentation_lookup": documentation_lookup,
        "cli_entrypoint_lookup": cli_entrypoint_lookup,
        "configuration_effect_summary": configuration_effect_summary,
        "local_change_summary": local_change_summary,
        "ci_failure_summary": ci_failure_summary,
        "test_failure_summary": test_failure_summary,
        "multi_file_behavior_investigation": multi_file_behavior_investigation,
        "dependency_impact_summary": dependency_impact_summary,
        "test_selection_plan": test_selection_plan,
        "runtime_error_diagnosis": runtime_error_diagnosis,
        "reproduction_checklist": reproduction_checklist,
        "request_flow_map": request_flow_map,
        "code_path_comparison": code_path_comparison,
        "change_surface_summary": change_surface_summary,
        "multiple_path_assessment": path_assessment,
        "implementation_packet_seed": {
            "target_workflow": "implementation.workflow",
            "status": "not_ready_without_user_approval",
            "candidate_target_files": [record["path"] for record in source_refs[: request.max_files]],
            "candidate_test_files": [
                *[record["path"] for record in test_refs[: request.max_files]],
                *[path for path in related_test_paths if path not in {record["path"] for record in test_refs}],
            ][: request.max_files],
            "required_before_apply": [
                "Founder/tester approves the exact behavior change.",
                "Implementation packets name exact files and operations.",
                "Verification commands are explicit and bounded.",
            ],
        },
        "verification_plan": {
            "status": "ready" if verification_commands else "not_ready_no_related_tests",
            "source": "test_discovery" if verification_commands else "bounded_investigation",
            "verification_commands": verification_commands,
            "gaps": [] if verification_commands else [{"gap": "verification_tests_not_found"}],
        },
        "gaps": gaps,
        "next_steps": [
            "Review the investigation evidence artifact before drafting implementation packets.",
            "If multiple source paths are present, decide which path is authoritative before refactoring.",
            "Use execution_planning.plan for approved packet design; do not apply edits from this investigation artifact.",
        ],
    }
    write_json(run_dir / "investigation-plan.json", plan)
    artifacts["investigation_plan"] = str(run_dir / "investigation-plan.json")

    summary = {
        "target_root": str(target_root),
        "query_count": len(queries),
        "participating_file_count": len(records),
        "source_file_count": len(source_refs),
        "test_file_count": len(test_refs),
        "related_test_file_count": len(related_test_paths),
        "verification_command_count": len(verification_commands),
        "code_explanation_status": code_explanation.get("status"),
        "behavior_existence_status": behavior_existence.get("status"),
        "configuration_lookup_status": configuration_lookup.get("status"),
        "endpoint_route_lookup_status": endpoint_route_lookup.get("status"),
        "message_source_lookup_status": message_source_lookup.get("status"),
        "module_summary_status": module_summary.get("status"),
        "data_model_lookup_status": data_model_lookup.get("status"),
        "table_read_write_lookup_status": table_read_write_lookup.get("status"),
        "coverage_gap_summary_status": coverage_gap_summary.get("status"),
        "documentation_lookup_status": documentation_lookup.get("status"),
        "cli_entrypoint_lookup_status": cli_entrypoint_lookup.get("status"),
        "configuration_effect_summary_status": configuration_effect_summary.get("status"),
        "local_change_summary_status": local_change_summary.get("status"),
        "ci_failure_summary_status": ci_failure_summary.get("status"),
        "test_failure_summary_status": test_failure_summary.get("status"),
        "multi_file_behavior_investigation_status": multi_file_behavior_investigation.get("status"),
        "dependency_impact_summary_status": dependency_impact_summary.get("status"),
        "test_selection_plan_status": test_selection_plan.get("status"),
        "runtime_error_diagnosis_status": runtime_error_diagnosis.get("status"),
        "reproduction_checklist_status": reproduction_checklist.get("status"),
        "request_flow_map_status": request_flow_map.get("status"),
        "code_path_comparison_status": code_path_comparison.get("status"),
        "change_surface_summary_status": change_surface_summary.get("status"),
        "grep_match_count": len(matches),
        "beginning_point_status": beginning.get("status"),
        "multiple_path_status": path_assessment.get("status"),
        "gap_count": len(gaps),
        "warning_count": len(warnings),
    }
    run_state = {
        "kind": "code_investigation_run_state",
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
        "kind": "code_investigation_report",
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
        summary_text=f"{WORKFLOW_ID} completed: {summary['participating_file_count']} participating file(s)",
        failures=[],
        resume_key={"schema_version": SCHEMA_VERSION, "run_state": str(run_dir / "run-state.json")},
        report=report,
        run_id=run_id,
    )
