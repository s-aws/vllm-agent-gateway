"""Versioned prompt catalog loading and validation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


DEFAULT_FOUNDER_FIELD_CATALOG = Path("runtime") / "prompt_catalogs" / "founder_field_v1.json"
CASE_ID_RE = re.compile(r"^P\d{2}$")


class PromptCatalogKind(str, Enum):
    PROMPT_CATALOG = "prompt_catalog"


@dataclass(frozen=True)
class PromptCatalogCase:
    case_id: str
    prompt: str
    target_root: str
    baseline_target: str
    expected_workflow: str
    expected_rule: str
    expected_markers: tuple[str, ...]
    semantic_markers: tuple[str, ...]
    forbidden_markers: tuple[str, ...]
    miss_suggestion: str
    tags: tuple[str, ...]
    refined_prompt: str = ""
    prompt_risk: str = ""
    expected_skill_id: str = ""
    expected_artifact_key: str = ""
    refined_expected_rule: str = ""
    refined_expected_markers: tuple[str, ...] = ()
    refined_semantic_markers: tuple[str, ...] = ()
    refined_expected_skill_id: str = ""
    refined_expected_artifact_key: str = ""


class PromptCatalogError(RuntimeError):
    """Raised when a prompt catalog fixture is missing or invalid."""


def _require_string(value: dict[str, Any], key: str, problems: list[str]) -> str:
    raw = value.get(key)
    if not isinstance(raw, str) or not raw.strip():
        problems.append(f"{key} must be a non-empty string")
        return ""
    return raw


def _optional_string(value: dict[str, Any], key: str, problems: list[str]) -> str:
    raw = value.get(key, "")
    if not isinstance(raw, str):
        problems.append(f"{key} must be a string")
        return ""
    return raw


def _require_string_list(value: dict[str, Any], key: str, problems: list[str]) -> tuple[str, ...]:
    raw = value.get(key)
    if not isinstance(raw, list) or not raw or not all(isinstance(item, str) and item for item in raw):
        problems.append(f"{key} must be a non-empty string list")
        return ()
    return tuple(raw)


def _optional_string_list(value: dict[str, Any], key: str, problems: list[str]) -> tuple[str, ...]:
    raw = value.get(key, [])
    if raw in (None, ""):
        return ()
    if not isinstance(raw, list) or not all(isinstance(item, str) and item for item in raw):
        problems.append(f"{key} must be a string list")
        return ()
    return tuple(raw)


def _require_history(value: dict[str, Any], key: str, problems: list[str]) -> None:
    history = value.get(key)
    if not isinstance(history, list) or not history:
        problems.append(f"{key} must contain at least one change-history entry")
        return
    for index, item in enumerate(history):
        if not isinstance(item, dict):
            problems.append(f"{key}[{index}] must be an object")
            continue
        for field in ("version", "date", "summary"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                problems.append(f"{key}[{index}].{field} must be a non-empty string")


def resolve_catalog_path(config_root: Path, catalog_path: Path | None = None) -> Path:
    path = catalog_path or DEFAULT_FOUNDER_FIELD_CATALOG
    if path.is_absolute():
        return path
    return config_root / path


def load_prompt_catalog(config_root: Path, catalog_path: Path | None = None) -> dict[str, Any]:
    path = resolve_catalog_path(config_root, catalog_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PromptCatalogError(f"prompt catalog not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PromptCatalogError(f"prompt catalog is not valid JSON: {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise PromptCatalogError(f"prompt catalog root must be an object: {path}")
    return raw


def validate_prompt_catalog(catalog: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if catalog.get("schema_version") != 1:
        problems.append("schema_version must be 1")
    if catalog.get("kind") != PromptCatalogKind.PROMPT_CATALOG.value:
        problems.append(f"kind must be {PromptCatalogKind.PROMPT_CATALOG.value}")
    for key in ("catalog_id", "version", "description", "owner", "created_at"):
        _require_string(catalog, key, problems)
    _require_history(catalog, "change_history", problems)
    _require_string_list(catalog, "common_format_a_markers", problems)
    _require_string_list(catalog, "common_forbidden_markers", problems)

    raw_cases = catalog.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        problems.append("cases must be a non-empty list")
        return problems

    seen: set[str] = set()
    for index, raw_case in enumerate(raw_cases):
        if not isinstance(raw_case, dict):
            problems.append(f"cases[{index}] must be an object")
            continue
        prefix = f"cases[{index}]"
        case_problems: list[str] = []
        case_id = _require_string(raw_case, "case_id", case_problems)
        if case_id and not CASE_ID_RE.match(case_id):
            case_problems.append(f"case_id must match {CASE_ID_RE.pattern}")
        if case_id in seen:
            case_problems.append(f"duplicate case_id {case_id}")
        seen.add(case_id)
        for key in (
            "prompt",
            "target_root",
            "baseline_target",
            "expected_workflow",
            "expected_rule",
            "miss_suggestion",
        ):
            _require_string(raw_case, key, case_problems)
        for key in (
            "expected_skill_id",
            "expected_artifact_key",
            "refined_prompt",
            "prompt_risk",
            "refined_expected_rule",
            "refined_expected_skill_id",
            "refined_expected_artifact_key",
        ):
            _optional_string(raw_case, key, case_problems)
        for key in ("expected_markers", "semantic_markers", "forbidden_markers", "tags"):
            _require_string_list(raw_case, key, case_problems)
        for key in ("refined_expected_markers", "refined_semantic_markers"):
            _optional_string_list(raw_case, key, case_problems)
        _require_history(raw_case, "change_history", case_problems)
        if raw_case.get("refined_prompt") and not raw_case.get("prompt_risk"):
            case_problems.append("prompt_risk is required when refined_prompt is present")
        if raw_case.get("prompt_risk") and not raw_case.get("refined_prompt"):
            case_problems.append("refined_prompt is required when prompt_risk is present")
        refined_expectation_keys = (
            "refined_expected_rule",
            "refined_expected_markers",
            "refined_semantic_markers",
            "refined_expected_skill_id",
            "refined_expected_artifact_key",
        )
        if any(raw_case.get(key) for key in refined_expectation_keys) and not raw_case.get("refined_prompt"):
            case_problems.append("refined_prompt is required when refined expected fields are present")
        for problem in case_problems:
            problems.append(f"{prefix}: {problem}")
    return problems


def prompt_cases_from_catalog(catalog: dict[str, Any]) -> tuple[PromptCatalogCase, ...]:
    problems = validate_prompt_catalog(catalog)
    if problems:
        raise PromptCatalogError("; ".join(problems))
    cases: list[PromptCatalogCase] = []
    for raw_case in catalog["cases"]:
        cases.append(
            PromptCatalogCase(
                case_id=raw_case["case_id"],
                prompt=raw_case["prompt"],
                target_root=raw_case["target_root"],
                baseline_target=raw_case["baseline_target"],
                expected_workflow=raw_case["expected_workflow"],
                expected_rule=raw_case["expected_rule"],
                expected_markers=tuple(raw_case["expected_markers"]),
                semantic_markers=tuple(raw_case["semantic_markers"]),
                forbidden_markers=tuple(raw_case["forbidden_markers"]),
                miss_suggestion=raw_case["miss_suggestion"],
                tags=tuple(raw_case["tags"]),
                refined_prompt=raw_case.get("refined_prompt", ""),
                prompt_risk=raw_case.get("prompt_risk", ""),
                expected_skill_id=raw_case.get("expected_skill_id", ""),
                expected_artifact_key=raw_case.get("expected_artifact_key", ""),
                refined_expected_rule=raw_case.get("refined_expected_rule", ""),
                refined_expected_markers=tuple(raw_case.get("refined_expected_markers") or ()),
                refined_semantic_markers=tuple(raw_case.get("refined_semantic_markers") or ()),
                refined_expected_skill_id=raw_case.get("refined_expected_skill_id", ""),
                refined_expected_artifact_key=raw_case.get("refined_expected_artifact_key", ""),
            )
        )
    return tuple(cases)


def load_founder_field_catalog(config_root: Path, catalog_path: Path | None = None) -> dict[str, Any]:
    return load_prompt_catalog(config_root, catalog_path)


def load_founder_field_prompts(config_root: Path, catalog_path: Path | None = None) -> tuple[PromptCatalogCase, ...]:
    return prompt_cases_from_catalog(load_founder_field_catalog(config_root, catalog_path))


def prompt_refinements_from_cases(cases: tuple[PromptCatalogCase, ...]) -> dict[str, dict[str, str]]:
    return {
        case.case_id: {"refined_prompt": case.refined_prompt, "prompt_risk": case.prompt_risk}
        for case in cases
        if case.refined_prompt
    }


def expected_rules_from_cases(cases: tuple[PromptCatalogCase, ...]) -> dict[str, str]:
    return {case.case_id: case.expected_rule for case in cases}
