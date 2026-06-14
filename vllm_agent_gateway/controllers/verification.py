"""Shared evidence-backed verification planning helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from vllm_agent_gateway.controllers.natural_query import (
    natural_identifier_queries_from_request,
    strip_filesystem_paths,
)


PYTHON_TEST_RUNNER = "pytest"


def camel_to_snake_identifier(value: str) -> str:
    first_pass = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", first_pass).lower()


def salient_search_terms(*values: str) -> list[str]:
    terms: dict[str, tuple[int, str]] = {}

    def add_term(term: str, *, priority: int) -> None:
        cleaned = term.strip()
        if not cleaned:
            return
        existing = terms.get(cleaned)
        if existing is None or priority < existing[0]:
            terms[cleaned] = (priority, cleaned)

    for value in values:
        query_source = strip_filesystem_paths(value)
        for match in re.findall(r"`([^`]{3,80})`", query_source):
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", match):
                add_term(match, priority=0)
        for match in re.findall(r"\b[A-Z][A-Za-z0-9]+(?:[A-Z][A-Za-z0-9]+)+\b", query_source):
            add_term(match, priority=1)
            add_term(camel_to_snake_identifier(match), priority=1)
        for match in re.findall(r"\b[a-zA-Z_][A-Za-z0-9_]*_[A-Za-z0-9_]+\b", query_source):
            priority = 2 if match.count("_") <= 3 else 3
            add_term(match, priority=priority)
        for match in natural_identifier_queries_from_request(query_source, limit=12):
            add_term(match, priority=3)
    return [
        term
        for _priority, term in sorted(
            terms.values(),
            key=lambda item: (item[0], item[1].count("_"), len(item[1]), item[1].lower()),
        )[:12]
    ]


def related_test_candidate_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    tests_root = root / "tests"
    if tests_root.exists():
        paths.extend(sorted(tests_root.rglob("*.py")))
    paths.extend(sorted(path for path in root.glob("test_*.py") if path.is_file()))
    genai_tools = root / "genai_tools"
    if genai_tools.exists():
        paths.extend(sorted(genai_tools.glob("test_*.py")))
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def stripped_code_line(line: str) -> str:
    return line.strip()


def test_line_evidence(term: str, line: str) -> dict[str, Any]:
    stripped = stripped_code_line(line)
    lowered = stripped.lower()
    term_value = term.lower()
    if re.match(r"def\s+test_", stripped) and term_value in lowered:
        return {
            "kind": "test_definition",
            "confidence": "high",
            "score": 120,
            "reason": "Test function name directly contains the requested behavior term.",
        }
    if "assert" in lowered and term_value in lowered:
        return {
            "kind": "assertion",
            "confidence": "high",
            "score": 110,
            "reason": "Assertion line directly references the requested behavior term.",
        }
    if re.search(rf"\b{re.escape(term)}\s*\(", stripped):
        return {
            "kind": "direct_call",
            "confidence": "high",
            "score": 105,
            "reason": "Test body directly calls the requested symbol.",
        }
    if (stripped.startswith("from ") or stripped.startswith("import ")) and term_value in lowered:
        return {
            "kind": "import_reference",
            "confidence": "medium",
            "score": 75,
            "reason": "Import evidence references the requested term but does not prove assertions.",
        }
    if "pytest.mark" in lowered and term_value in lowered:
        return {
            "kind": "marker_or_parametrize",
            "confidence": "medium",
            "score": 70,
            "reason": "Pytest marker or parametrized case references the requested term.",
        }
    if stripped.startswith("#"):
        return {
            "kind": "comment_reference",
            "confidence": "low",
            "score": 25,
            "reason": "Comment-only evidence is weak and must not be treated as coverage.",
        }
    return {
        "kind": "text_reference",
        "confidence": "medium",
        "score": 55,
        "reason": "Bounded test file text references the requested term.",
    }


def confidence_from_score(score: int) -> str:
    if score >= 100:
        return "high"
    if score >= 60:
        return "medium"
    return "low"


def test_file_status(text: str) -> dict[str, Any]:
    lowered = text.lower()
    markers: list[str] = []
    if "@pytest.mark.skip" in lowered or "pytest.skip(" in lowered:
        markers.append("skip")
    if "@pytest.mark.xfail" in lowered or "xfail(" in lowered:
        markers.append("xfail")
    if "generated" in lowered and "test" in lowered:
        markers.append("possibly_generated")
    return {
        "executable": True,
        "runner": PYTHON_TEST_RUNNER,
        "status_markers": markers,
    }


def discover_related_tests_from_values(
    target_root: Path,
    search_values: list[str],
    max_files: int,
) -> dict[str, Any] | None:
    terms = salient_search_terms(*search_values)
    if not terms:
        return None

    root = target_root.resolve()
    candidates: dict[str, dict[str, Any]] = {}
    for path in related_test_candidate_paths(root):
        if path.is_symlink():
            continue
        try:
            rel_path = path.resolve().relative_to(root).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
        refs: list[str] = []
        evidence_refs: list[dict[str, Any]] = []
        matched_terms: set[str] = set()
        evidence_kinds: set[str] = set()
        best_score = 0
        best_reason = ""
        best_confidence = "low"
        for term in terms:
            for line_no, line in enumerate(text.splitlines(), 1):
                if term in line:
                    evidence = test_line_evidence(term, line)
                    refs.append(f"{rel_path}:{line_no}:{line}")
                    evidence_refs.append(
                        {
                            "path": rel_path,
                            "line": line_no,
                            "term": term,
                            "kind": evidence["kind"],
                            "confidence": evidence["confidence"],
                            "reason": evidence["reason"],
                            "text": line[:300],
                        }
                    )
                    matched_terms.add(term)
                    evidence_kinds.add(str(evidence["kind"]))
                    evidence_score = int(evidence["score"])
                    if evidence_score > best_score:
                        best_score = evidence_score
                        best_reason = str(evidence["reason"])
                        best_confidence = str(evidence["confidence"])
                    break
        if refs:
            status = test_file_status(text)
            score = best_score + (len(matched_terms) * 10)
            if any(kind in evidence_kinds for kind in {"test_definition", "assertion", "direct_call"}):
                relationship = "direct"
            elif any(kind in evidence_kinds for kind in {"import_reference", "marker_or_parametrize", "text_reference"}):
                relationship = "adjacent"
            else:
                relationship = "weak"
            candidates[rel_path] = {
                "path": rel_path,
                "score": score,
                "matched_terms": sorted(matched_terms),
                "confidence": confidence_from_score(score),
                "evidence_kind": relationship,
                "evidence_reason": best_reason or "Bounded test file matched one or more request terms.",
                "source_refs": refs[:10],
                "evidence_refs": evidence_refs[:10],
                "runner": status["runner"],
                "executable": status["executable"],
                "status_markers": status["status_markers"],
            }

    def test_path_priority(path: str) -> int:
        if path.startswith("tests/unit/"):
            return 0
        if path.startswith("tests/regression/"):
            return 1
        if path.startswith("tests/integration/"):
            return 2
        if path.startswith("tests/e2e/"):
            return 3
        if path.startswith("tests/"):
            return 4
        return 5

    selected = sorted(
        candidates.values(),
        key=lambda item: (-int(item["score"]), test_path_priority(str(item["path"])), item["path"]),
    )[:max_files]
    if not selected:
        return None
    direct_count = len([item for item in selected if item.get("evidence_kind") == "direct"])
    return {
        "id": "CTX-TEST-0001",
        "purpose": "related_tests",
        "source": "test_discovery",
        "summary": f"Bounded test discovery matched {len(selected)} test file(s) for request terms.",
        "source_refs": [ref for item in selected for ref in item["source_refs"]][:25],
        "matched_terms": terms,
        "candidate_count": len(candidates),
        "direct_test_count": direct_count,
        "confidence": "high" if direct_count else "medium",
        "runner": PYTHON_TEST_RUNNER,
        "gaps": [] if direct_count else [{"gap": "no_direct_related_test_evidence"}],
        "related_test_files": [
            {
                "path": item["path"],
                "matched_terms": item["matched_terms"],
                "source_refs": item["source_refs"],
                "evidence_refs": item["evidence_refs"],
                "confidence": item["confidence"],
                "evidence_kind": item["evidence_kind"],
                "evidence_reason": item["evidence_reason"],
                "runner": item["runner"],
                "executable": item["executable"],
                "status_markers": item["status_markers"],
            }
            for item in selected
        ],
    }


def discover_related_tests(
    target_root: Path,
    packet_operations: list[dict[str, Any]],
    user_request: str,
    max_files: int,
) -> dict[str, Any] | None:
    search_values = [user_request]
    for operation in packet_operations:
        for key in ("old", "new", "path"):
            value = operation.get(key)
            if isinstance(value, str):
                search_values.append(value)
    return discover_related_tests_from_values(target_root, search_values, max_files)


def controller_verification_commands(context_results: dict[str, Any]) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    for result in context_results.get("results", []):
        if not isinstance(result, dict) or result.get("source") != "test_discovery":
            continue
        for item in result.get("related_test_files", []):
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                continue
            path = item["path"]
            source_refs = item.get("source_refs") if isinstance(item.get("source_refs"), list) else []
            confidence = item.get("confidence") if isinstance(item.get("confidence"), str) else "low"
            evidence_kind = item.get("evidence_kind") if isinstance(item.get("evidence_kind"), str) else "weak"
            commands.append(
                {
                    "id": f"controller-verification-{len(commands) + 1:04d}",
                    "command": ["python", "-m", "pytest", path],
                    "reason": (
                        "Controller-discovered related test file matched request or packet terms "
                        f"with {confidence} confidence ({evidence_kind} evidence)."
                    ),
                    "associated_files": [path],
                    "timeout_seconds": 300,
                    "source_refs": source_refs[:10],
                    "confidence": confidence,
                    "evidence_kind": evidence_kind,
                }
            )
    return commands


def merge_controller_verification_commands(
    verification_plan: dict[str, Any],
    controller_commands: list[dict[str, Any]],
) -> None:
    raw_commands = verification_plan.get("verification_commands")
    if not isinstance(raw_commands, list):
        raw_commands = []
        verification_plan["verification_commands"] = raw_commands
    seen = {
        tuple(item.get("command", []))
        for item in raw_commands
        if isinstance(item, dict) and isinstance(item.get("command"), list)
    }
    for command in controller_commands:
        command_key = tuple(command["command"])
        if command_key in seen:
            continue
        raw_commands.append(command)
        seen.add(command_key)
