"""Shared evidence-backed verification planning helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def salient_search_terms(*values: str) -> list[str]:
    terms: set[str] = set()
    for value in values:
        for match in re.findall(r"`([^`]{3,80})`", value):
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", match):
                terms.add(match)
        for match in re.findall(r"\b[A-Z][A-Za-z0-9]+(?:[A-Z][A-Za-z0-9]+)+\b", value):
            terms.add(match)
        for match in re.findall(r"\b[a-zA-Z_][A-Za-z0-9_]*_[A-Za-z0-9_]+\b", value):
            terms.add(match)
    return sorted(terms, key=lambda item: (-len(item), item.lower()))[:8]


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
        matched_terms: set[str] = set()
        for term in terms:
            for line_no, line in enumerate(text.splitlines(), 1):
                if term in line:
                    refs.append(f"{rel_path}:{line_no}:{line}")
                    matched_terms.add(term)
                    break
        if refs:
            candidates[rel_path] = {
                "path": rel_path,
                "score": len(matched_terms),
                "matched_terms": sorted(matched_terms),
                "source_refs": refs[:10],
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
    return {
        "id": "CTX-TEST-0001",
        "purpose": "related_tests",
        "source": "test_discovery",
        "summary": f"Bounded test discovery matched {len(selected)} test file(s) for request terms.",
        "source_refs": [ref for item in selected for ref in item["source_refs"]][:25],
        "matched_terms": terms,
        "related_test_files": [
            {
                "path": item["path"],
                "matched_terms": item["matched_terms"],
                "source_refs": item["source_refs"],
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
            commands.append(
                {
                    "id": f"controller-verification-{len(commands) + 1:04d}",
                    "command": ["python", "-m", "pytest", path],
                    "reason": "Controller-discovered related test file matched request or packet terms.",
                    "associated_files": [path],
                    "timeout_seconds": 300,
                    "source_refs": source_refs[:10],
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
