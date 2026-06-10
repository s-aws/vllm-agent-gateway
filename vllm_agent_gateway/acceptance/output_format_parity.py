"""Output-format parity checks for Priority 0 chat-quality proof."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES_PATH = REPO_ROOT / "runtime" / "output_format_parity_cases.json"
REQUIRED_TARGET_ROOTS = {
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
}


@dataclass(frozen=True)
class OutputFormatParityCase:
    case_id: str
    prompt: str
    target_root: str
    prompt_family: str
    expected_selected_workflow: str
    expected_heading: str
    expected_artifact_kind: str
    expected_artifact_keys: tuple[str, ...]
    required_text_markers: tuple[str, ...]
    required_json_markers: tuple[str, ...]


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return value


def _case_lookup(source_cases_path: Path) -> dict[str, dict[str, Any]]:
    catalog = read_json_object(source_cases_path)
    cases = catalog.get("cases")
    if not isinstance(cases, list):
        raise ValueError(f"{source_cases_path} did not contain a cases list")
    return {
        str(item.get("case_id")): item
        for item in cases
        if isinstance(item, dict) and isinstance(item.get("case_id"), str)
    }


def _string_tuple(value: Any, *, field: str, case_id: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{case_id} {field} must be a non-empty list")
    values = tuple(item for item in value if isinstance(item, str) and item)
    if len(values) != len(value):
        raise ValueError(f"{case_id} {field} must contain only strings")
    return values


def load_output_format_parity_cases(
    cases_path: Path = DEFAULT_CASES_PATH,
    *,
    repo_root: Path = REPO_ROOT,
) -> list[OutputFormatParityCase]:
    catalog = read_json_object(cases_path)
    if catalog.get("kind") != "output_format_parity_cases":
        raise ValueError(f"{cases_path} kind must be output_format_parity_cases")
    raw_cases = catalog.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError(f"{cases_path} must contain at least one case")

    source_cache: dict[Path, dict[str, dict[str, Any]]] = {}
    loaded: list[OutputFormatParityCase] = []
    seen: set[str] = set()
    for item in raw_cases:
        if not isinstance(item, dict):
            raise ValueError("output format parity cases must be objects")
        case_id = item.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("output format parity case_id is required")
        if case_id in seen:
            raise ValueError(f"duplicate output format parity case_id: {case_id}")
        seen.add(case_id)

        source_cases_path = item.get("source_cases_path")
        if not isinstance(source_cases_path, str) or not source_cases_path:
            raise ValueError(f"{case_id} source_cases_path is required")
        resolved_source_path = (repo_root / source_cases_path).resolve()
        if resolved_source_path not in source_cache:
            source_cache[resolved_source_path] = _case_lookup(resolved_source_path)
        source_case = source_cache[resolved_source_path].get(case_id)
        if source_case is None:
            raise ValueError(f"{case_id} was not found in {source_cases_path}")

        prompt = source_case.get("prompt")
        target_root = source_case.get("target_root")
        prompt_family = item.get("prompt_family")
        expected_selected_workflow = item.get("expected_selected_workflow")
        expected_heading = item.get("expected_heading")
        expected_artifact_kind = item.get("expected_artifact_kind")
        for field, value in (
            ("prompt", prompt),
            ("target_root", target_root),
            ("prompt_family", prompt_family),
            ("expected_selected_workflow", expected_selected_workflow),
            ("expected_heading", expected_heading),
            ("expected_artifact_kind", expected_artifact_kind),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{case_id} {field} is required")

        loaded.append(
            OutputFormatParityCase(
                case_id=case_id,
                prompt=prompt,
                target_root=target_root,
                prompt_family=prompt_family,
                expected_selected_workflow=expected_selected_workflow,
                expected_heading=expected_heading,
                expected_artifact_kind=expected_artifact_kind,
                expected_artifact_keys=_string_tuple(
                    item.get("expected_artifact_keys"),
                    field="expected_artifact_keys",
                    case_id=case_id,
                ),
                required_text_markers=_string_tuple(
                    item.get("required_text_markers"),
                    field="required_text_markers",
                    case_id=case_id,
                ),
                required_json_markers=_string_tuple(
                    item.get("required_json_markers"),
                    field="required_json_markers",
                    case_id=case_id,
                ),
            )
        )
    return loaded


def validate_case_catalog(cases: list[OutputFormatParityCase]) -> list[str]:
    errors: list[str] = []
    if not cases:
        return ["output format parity catalog has no cases"]
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


def assistant_text_from_body(body: dict[str, Any]) -> str:
    for key in ("textResponse", "response", "message"):
        value = body.get(key)
        if isinstance(value, str):
            return value
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
    raise ValueError("response did not include assistant text")


def parse_assistant_json(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"assistant content was not parseable JSON: {text[:500]}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("assistant JSON content was not an object")
    return parsed


def _contains(text: str, marker: str) -> bool:
    return marker.lower() in text.lower()


def validate_format_a_text(case: OutputFormatParityCase, text: str) -> list[str]:
    errors: list[str] = []
    for marker in case.required_text_markers:
        if not _contains(text, marker):
            errors.append(f"{case.case_id} FormatA missing marker: {marker}")
    if "Result:" not in text:
        errors.append(f"{case.case_id} FormatA missing Result section")
    if case.expected_heading not in text:
        errors.append(f"{case.case_id} FormatA missing expected heading {case.expected_heading}")
    return errors


def validate_json_contract(case: OutputFormatParityCase, parsed: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if parsed.get("output_format") != "json":
        errors.append(f"{case.case_id} JSON output_format was {parsed.get('output_format')!r}")
    if parsed.get("workflow") != "workflow_router.plan":
        errors.append(f"{case.case_id} JSON workflow was {parsed.get('workflow')!r}")
    if parsed.get("status") != "completed":
        errors.append(f"{case.case_id} JSON status was {parsed.get('status')!r}")

    chat_contract = parsed.get("chat_contract")
    if not isinstance(chat_contract, dict):
        errors.append(f"{case.case_id} JSON missing chat_contract")
    elif chat_contract.get("selected_workflow") != case.expected_selected_workflow:
        errors.append(
            f"{case.case_id} JSON selected_workflow was {chat_contract.get('selected_workflow')!r}; "
            f"expected {case.expected_selected_workflow!r}"
        )

    inline_contract = parsed.get("inline_answer_contract")
    if not isinstance(inline_contract, dict):
        errors.append(f"{case.case_id} JSON missing inline_answer_contract")
        return errors
    if inline_contract.get("artifact_kind") != case.expected_artifact_kind:
        errors.append(
            f"{case.case_id} JSON inline artifact_kind was {inline_contract.get('artifact_kind')!r}; "
            f"expected {case.expected_artifact_kind!r}"
        )
    if inline_contract.get("artifact_key") not in case.expected_artifact_keys:
        errors.append(
            f"{case.case_id} JSON inline artifact_key was {inline_contract.get('artifact_key')!r}; "
            f"expected one of {list(case.expected_artifact_keys)!r}"
        )
    if inline_contract.get("heading") != case.expected_heading:
        errors.append(
            f"{case.case_id} JSON inline heading was {inline_contract.get('heading')!r}; "
            f"expected {case.expected_heading!r}"
        )
    text = inline_contract.get("text")
    if not isinstance(text, str) or not text:
        errors.append(f"{case.case_id} JSON inline text was empty")
        return errors
    for marker in case.required_json_markers:
        if not _contains(text, marker):
            errors.append(f"{case.case_id} JSON inline text missing marker: {marker}")
    return errors


def validate_output_format_pair(
    case: OutputFormatParityCase,
    *,
    format_a_text: str,
    json_object: dict[str, Any],
    require_exact_inline_match: bool = True,
    minimum_shared_line_count: int = 4,
) -> list[str]:
    errors = validate_format_a_text(case, format_a_text)
    errors.extend(validate_json_contract(case, json_object))
    inline_contract = json_object.get("inline_answer_contract")
    if isinstance(inline_contract, dict) and isinstance(inline_contract.get("text"), str):
        inline_text = inline_contract["text"]
        if require_exact_inline_match and inline_text not in format_a_text:
            errors.append(f"{case.case_id} JSON inline text did not match the FormatA answer body")
        elif not require_exact_inline_match:
            shared_lines = shared_stable_answer_lines(format_a_text, inline_text)
            if len(shared_lines) < minimum_shared_line_count:
                errors.append(
                    f"{case.case_id} JSON inline text shared only {len(shared_lines)} stable line(s) "
                    f"with FormatA; expected at least {minimum_shared_line_count}"
                )
    return errors


VOLATILE_INLINE_LINE_PREFIXES = (
    "- Target:",
    "- Related tests:",
    "- Evidence files:",
    "- Source refs:",
    "- Medium test:",
    "- Broader regression test:",
)


def stable_answer_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.endswith(":") and not line.startswith("-"):
            continue
        if any(line.startswith(prefix) for prefix in VOLATILE_INLINE_LINE_PREFIXES):
            continue
        lines.append(line)
    return lines


def shared_stable_answer_lines(format_a_text: str, inline_text: str) -> list[str]:
    format_a_lines = set(stable_answer_lines(format_a_text))
    return [line for line in stable_answer_lines(inline_text) if line in format_a_lines]


def validate_output_format_parity_report(report: dict[str, Any]) -> list[str]:
    if report.get("kind") != "output_format_parity_live_report":
        return ["report kind must be output_format_parity_live_report"]
    errors: list[str] = []
    case_reports = report.get("cases")
    if not isinstance(case_reports, list) or not case_reports:
        return ["report must contain at least one case"]
    for case_report in case_reports:
        if not isinstance(case_report, dict):
            errors.append("case report must be an object")
            continue
        case_errors = case_report.get("errors")
        if isinstance(case_errors, list):
            errors.extend(str(error) for error in case_errors if error)
        responses = case_report.get("responses")
        if not isinstance(responses, dict):
            errors.append(f"{case_report.get('case_id')} missing responses")
            continue
        for surface in ("gateway", "anythingllm"):
            surface_report = responses.get(surface)
            if not isinstance(surface_report, dict):
                errors.append(f"{case_report.get('case_id')} missing {surface} response")
                continue
            if surface_report.get("status") != "passed":
                errors.append(
                    f"{case_report.get('case_id')} {surface} status was {surface_report.get('status')!r}"
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
