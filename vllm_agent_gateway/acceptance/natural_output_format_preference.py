"""Natural output-format preference checks for Priority 0 chat-quality proof."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.output_format_parity import (
    DEFAULT_CASES_PATH as DEFAULT_OUTPUT_FORMAT_PARITY_CASES_PATH,
    REQUIRED_TARGET_ROOTS,
    OutputFormatParityCase,
    load_output_format_parity_cases,
    read_json_object,
    validate_format_a_text,
    validate_json_contract,
    validate_output_format_pair,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES_PATH = REPO_ROOT / "runtime" / "natural_output_format_preference_cases.json"

REQUIRED_GATEWAY_PREFERENCES = (
    "default_format_a",
    "natural_format_a",
    "natural_json",
    "explicit_output_format_json",
    "openai_response_format_json",
    "unsupported_explicit_output_format",
    "unsupported_response_format",
)
REQUIRED_ANYTHINGLLM_PREFERENCES = (
    "default_format_a",
    "natural_format_a",
    "natural_json",
)
NATURAL_JSON_SELECTOR_KIND = "natural_text_json"


@dataclass(frozen=True)
class NaturalOutputFormatPreferenceCase:
    case_id: str
    source_case_id: str
    natural_json_instruction: str
    source: OutputFormatParityCase

    @property
    def prompt(self) -> str:
        return self.source.prompt

    @property
    def prompt_family(self) -> str:
        return self.source.prompt_family

    @property
    def target_root(self) -> str:
        return self.source.target_root


def _string_list(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty list")
    strings = [item for item in value if isinstance(item, str) and item]
    if len(strings) != len(value):
        raise ValueError(f"{field} must contain only strings")
    return strings


def load_natural_output_format_preference_cases(
    cases_path: Path = DEFAULT_CASES_PATH,
    *,
    repo_root: Path = REPO_ROOT,
) -> list[NaturalOutputFormatPreferenceCase]:
    catalog = read_json_object(cases_path)
    if catalog.get("kind") != "natural_output_format_preference_cases":
        raise ValueError(f"{cases_path} kind must be natural_output_format_preference_cases")
    if int(catalog.get("schema_version", 0)) != 1:
        raise ValueError(f"{cases_path} schema_version must be 1")

    source_cases_path_value = catalog.get("source_output_format_parity_cases_path")
    if not isinstance(source_cases_path_value, str) or not source_cases_path_value:
        source_cases_path = DEFAULT_OUTPUT_FORMAT_PARITY_CASES_PATH
    else:
        source_cases_path = repo_root / source_cases_path_value
    source_cases = {
        case.case_id: case
        for case in load_output_format_parity_cases(source_cases_path, repo_root=repo_root)
    }

    required_gateway_preferences = tuple(_string_list(catalog.get("required_gateway_preferences"), field="required_gateway_preferences"))
    required_anythingllm_preferences = tuple(
        _string_list(catalog.get("required_anythingllm_preferences"), field="required_anythingllm_preferences")
    )
    if required_gateway_preferences != REQUIRED_GATEWAY_PREFERENCES:
        raise ValueError(
            "required_gateway_preferences must be "
            f"{list(REQUIRED_GATEWAY_PREFERENCES)!r}; got {list(required_gateway_preferences)!r}"
        )
    if required_anythingllm_preferences != REQUIRED_ANYTHINGLLM_PREFERENCES:
        raise ValueError(
            "required_anythingllm_preferences must be "
            f"{list(REQUIRED_ANYTHINGLLM_PREFERENCES)!r}; got {list(required_anythingllm_preferences)!r}"
        )

    raw_cases = catalog.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError(f"{cases_path} must contain at least one case")

    loaded: list[NaturalOutputFormatPreferenceCase] = []
    seen: set[str] = set()
    for item in raw_cases:
        if not isinstance(item, dict):
            raise ValueError("natural output format preference cases must be objects")
        case_id = item.get("case_id")
        source_case_id = item.get("source_case_id")
        instruction = item.get("natural_json_instruction")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("natural output format preference case_id is required")
        if case_id in seen:
            raise ValueError(f"duplicate natural output format preference case_id: {case_id}")
        seen.add(case_id)
        if not isinstance(source_case_id, str) or not source_case_id:
            raise ValueError(f"{case_id} source_case_id is required")
        if source_case_id not in source_cases:
            raise ValueError(f"{case_id} source_case_id {source_case_id!r} was not found in {source_cases_path}")
        if not isinstance(instruction, str) or "json" not in instruction.lower():
            raise ValueError(f"{case_id} natural_json_instruction must request JSON")
        loaded.append(
            NaturalOutputFormatPreferenceCase(
                case_id=case_id,
                source_case_id=source_case_id,
                natural_json_instruction=instruction.strip(),
                source=source_cases[source_case_id],
            )
        )
    return loaded


def validate_preference_case_catalog(cases: list[NaturalOutputFormatPreferenceCase]) -> list[str]:
    errors: list[str] = []
    if not cases:
        return ["natural output format preference catalog has no cases"]
    target_roots = {case.target_root for case in cases}
    missing_targets = sorted(REQUIRED_TARGET_ROOTS - target_roots)
    if missing_targets:
        errors.append(f"missing required target roots: {', '.join(missing_targets)}")
    families = {case.prompt_family for case in cases}
    required_families = {
        "code_quality_and_self_review",
        "testing_and_defect_diagnosis",
        "tradeoffs_debt_and_engineering_judgment",
        "delivery_and_mentorship",
    }
    missing_families = sorted(required_families - families)
    if missing_families:
        errors.append(f"missing required prompt families: {', '.join(missing_families)}")
    return errors


def validate_default_format_a_response(
    case: NaturalOutputFormatPreferenceCase,
    *,
    text: str,
    selected_output_format: str | None = None,
) -> list[str]:
    errors = validate_format_a_text(case.source, text)
    if selected_output_format is not None and selected_output_format != "format_a":
        errors.append(f"{case.case_id} default selected output_format was {selected_output_format!r}")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict) and parsed.get("output_format") == "json":
        errors.append(f"{case.case_id} default FormatA response was JSON")
    return errors


def validate_json_preference_response(
    case: NaturalOutputFormatPreferenceCase,
    *,
    format_a_text: str,
    json_object: dict[str, Any],
    selector_kind: str,
    selected_output_format: str | None = None,
    require_natural_selector: bool = False,
) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_json_contract(case.source, json_object))
    errors.extend(
        validate_output_format_pair(
            case.source,
            format_a_text=format_a_text,
            json_object=json_object,
            require_exact_inline_match=False,
        )
    )
    if selected_output_format is not None and selected_output_format != "json":
        errors.append(f"{case.case_id} JSON preference selected output_format was {selected_output_format!r}")
    if require_natural_selector and selector_kind != NATURAL_JSON_SELECTOR_KIND:
        errors.append(f"{case.case_id} natural JSON selector_kind was {selector_kind!r}")
    return errors


def validate_natural_output_format_preference_report(report: dict[str, Any]) -> list[str]:
    if report.get("kind") != "natural_output_format_preference_live_report":
        return ["report kind must be natural_output_format_preference_live_report"]
    errors: list[str] = []
    case_reports = report.get("cases")
    if not isinstance(case_reports, list) or not case_reports:
        return ["report must contain at least one case"]
    for case_report in case_reports:
        if not isinstance(case_report, dict):
            errors.append("case report must be an object")
            continue
        case_id = case_report.get("case_id")
        case_errors = case_report.get("errors")
        if isinstance(case_errors, list):
            errors.extend(str(error) for error in case_errors if error)
        responses = case_report.get("responses")
        if not isinstance(responses, dict):
            errors.append(f"{case_id} missing responses")
            continue
        for surface, required_preferences in (
            ("gateway", REQUIRED_GATEWAY_PREFERENCES),
            ("anythingllm", REQUIRED_ANYTHINGLLM_PREFERENCES),
        ):
            surface_report = responses.get(surface)
            if not isinstance(surface_report, dict):
                errors.append(f"{case_id} missing {surface} response")
                continue
            if surface_report.get("status") != "passed":
                errors.append(f"{case_id} {surface} status was {surface_report.get('status')!r}")
            preferences = surface_report.get("preferences")
            if not isinstance(preferences, dict):
                errors.append(f"{case_id} {surface} missing preferences")
                continue
            for preference in required_preferences:
                preference_report = preferences.get(preference)
                if not isinstance(preference_report, dict):
                    errors.append(f"{case_id} {surface} missing preference {preference}")
                    continue
                if preference_report.get("status") != "passed":
                    errors.append(
                        f"{case_id} {surface} {preference} status was {preference_report.get('status')!r}"
                    )
                if preference == "natural_json":
                    request = preference_report.get("request")
                    if not isinstance(request, dict):
                        errors.append(f"{case_id} {surface} natural_json missing request proof")
                    else:
                        if request.get("selector_kind") != NATURAL_JSON_SELECTOR_KIND:
                            errors.append(
                                f"{case_id} {surface} natural_json selector_kind was {request.get('selector_kind')!r}"
                            )
                        if request.get("explicit_output_format_fields"):
                            errors.append(
                                f"{case_id} {surface} natural_json used explicit selector fields: "
                                f"{request.get('explicit_output_format_fields')!r}"
                            )
    mutation = report.get("mutation_proof")
    if not isinstance(mutation, dict):
        errors.append("report missing mutation_proof")
    else:
        if mutation.get("runtime_changed_files"):
            errors.append(f"runtime metadata mutated: {mutation.get('runtime_changed_files')!r}")
        target_changed = mutation.get("target_changed_files")
        if isinstance(target_changed, dict):
            changed = {root: paths for root, paths in target_changed.items() if paths}
            if changed:
                errors.append(f"target files mutated: {changed!r}")
        else:
            errors.append("mutation_proof.target_changed_files must be an object")
        git_changed = mutation.get("target_git_changed")
        if isinstance(git_changed, dict):
            changed_git = {root: status for root, status in git_changed.items() if status}
            if changed_git:
                errors.append(f"target git status changed: {changed_git!r}")
        else:
            errors.append("mutation_proof.target_git_changed must be an object")
    return errors
