"""Route stability holdout replay gate for Phase 205."""

from __future__ import annotations

import json
import os
import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.no_manual_skill_injection_explainability import (
    NoManualSkillInjectionExplainabilityConfig,
    anythingllm_response,
    gateway_response,
    phase204_case_from_prompt,
    validate_policy as validate_phase204_policy,
    validate_report as validate_phase204_report,
)
from vllm_agent_gateway.acceptance.skill_selection_hardening import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
)
from vllm_agent_gateway.acceptance.skill_tool_selection_explainability_e2e import ExplainabilityStatus
from vllm_agent_gateway.prompt_catalogs import (
    PromptCatalogCase,
    load_prompt_catalog,
    prompt_cases_from_catalog,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "route_stability_holdout_replay_policy"
EXPECTED_REPORT_KIND = "route_stability_holdout_replay_report"
EXPECTED_PHASE = 205
EXPECTED_BACKLOG_ID = "P0-M3-205"
DEFAULT_POLICY_PATH = Path("runtime") / "route_stability_holdout_replay_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "phase205"


class RouteReplayStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class RouteStabilityHoldoutReplayConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    markdown_output_path: Path | None = None
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 900
    live: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path, *, live: bool) -> Path:
    filename = (
        "phase205-route-stability-holdout-replay-report.json"
        if live
        else "phase205-route-stability-holdout-replay-preflight-report.json"
    )
    return config_root / DEFAULT_OUTPUT_DIR / filename


def markdown_path_for(report_path: Path) -> Path:
    return report_path.with_suffix(".md")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object at {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def valid_signature(value: object) -> bool:
    signature = dict_value(value)
    return (
        isinstance(signature.get("selected_workflow"), str)
        and bool(signature.get("selected_workflow"))
        and bool(string_list(signature.get("route_rules")))
        and bool(string_list(signature.get("selected_skills")))
        and isinstance(signature.get("selected_tools"), list)
    )


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 205")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    for key in (
        "phase204_report_path",
        "selector_contract_policy_path",
        "source_matrix_report_path",
        "target_prompt_catalog_path",
        "holdout_prompt_catalog_path",
    ):
        if not isinstance(policy.get(key), str) or not str(policy[key]).strip():
            errors.append(f"policy.{key} must be a non-empty string")
    if policy.get("target_case_ids_from_phase204") is not True:
        errors.append("policy.target_case_ids_from_phase204 must be true")
    if len(string_list(policy.get("holdout_case_ids"))) < int(policy.get("minimum_holdout_case_count", 4)):
        errors.append("policy.holdout_case_ids below policy.minimum_holdout_case_count")
    if int(policy.get("required_target_case_count", 0)) < int(policy.get("minimum_target_case_count", 30)):
        errors.append("policy.required_target_case_count must be at least policy.minimum_target_case_count")
    if int(policy.get("required_holdout_case_count", 0)) != len(string_list(policy.get("holdout_case_ids"))):
        errors.append("policy.required_holdout_case_count must equal policy.holdout_case_ids count")
    required_surfaces = string_list(policy.get("required_surfaces"))
    expected_live_count = (
        int(policy.get("required_target_case_count", 0)) + int(policy.get("required_holdout_case_count", 0))
    ) * len(required_surfaces)
    if int(policy.get("required_live_response_count", 0)) != expected_live_count:
        errors.append("policy.required_live_response_count must equal target plus holdout cases times required surfaces")
    if set(required_surfaces) != {"gateway", "anythingllm"}:
        errors.append("policy.required_surfaces must be gateway and anythingllm")
    if set(string_list(policy.get("required_target_roots"))) != {
        "/mnt/c/coinbase_testing_repo_frozen_tmp",
        "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    }:
        errors.append("policy.required_target_roots must match both frozen Coinbase fixtures")
    if policy.get("required_status") != "passed":
        errors.append("policy.required_status must be passed")
    if policy.get("compare_target_to_phase204") is not True:
        errors.append("policy.compare_target_to_phase204 must be true")
    if policy.get("compare_holdout_to_matrix") is not True:
        errors.append("policy.compare_holdout_to_matrix must be true")
    if policy.get("holdout_exact_signature_required") is not True:
        errors.append("policy.holdout_exact_signature_required must be true")
    holdout_signatures = dict_value(policy.get("holdout_expected_signatures"))
    for case_id in string_list(policy.get("holdout_case_ids")):
        if not valid_signature(holdout_signatures.get(case_id)):
            errors.append(f"policy.holdout_expected_signatures.{case_id} must contain a full route signature")
    if not string_list(policy.get("forbidden_drift_classes")):
        errors.append("policy.forbidden_drift_classes must be a non-empty list")
    return errors


def matrix_by_route_rule(matrix_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_rule: dict[str, dict[str, Any]] = {}
    for record in object_list(matrix_report.get("matrix_records")):
        rule = record.get("route_rule")
        if isinstance(rule, str) and rule not in by_rule:
            by_rule[rule] = record
    return by_rule


def registered_selection_ids(matrix_report: dict[str, Any]) -> tuple[set[str], set[str]]:
    skills: set[str] = set()
    tools: set[str] = set()
    for record in object_list(matrix_report.get("matrix_records")):
        skills.update(string_list(record.get("registered_skills")))
        skills.update(string_list(record.get("selected_skill_ids")))
        tools.update(string_list(record.get("registered_tools")))
        tools.update(string_list(record.get("selected_tool_ids")))
    source_refs = dict_value(matrix_report.get("source_refs"))
    skill_ref = dict_value(source_refs.get("skills"))
    tool_ref = dict_value(source_refs.get("tools"))
    skill_path = skill_ref.get("path")
    tool_path = tool_ref.get("path")
    if isinstance(skill_path, str) and skill_path:
        try:
            skill_registry = read_json_object(Path(skill_path))
            for item in object_list(skill_registry.get("skills")):
                skill_id = item.get("id")
                if isinstance(skill_id, str) and skill_id:
                    skills.add(skill_id)
        except Exception:  # noqa: BLE001
            pass
    if isinstance(tool_path, str) and tool_path:
        try:
            tool_registry = read_json_object(Path(tool_path))
            for item in object_list(tool_registry.get("tools")):
                tool_id = item.get("id")
                if isinstance(tool_id, str) and tool_id:
                    tools.add(tool_id)
        except Exception:  # noqa: BLE001
            pass
    return skills, tools


def cases_by_id(cases: tuple[PromptCatalogCase, ...]) -> dict[str, PromptCatalogCase]:
    return {case.case_id: case for case in cases}


def phase204_signature_by_case_surface(phase204_report: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    signatures: dict[tuple[str, str], dict[str, Any]] = {}
    for item in object_list(phase204_report.get("results")):
        case_id = item.get("case_id")
        surface = item.get("surface")
        if isinstance(case_id, str) and isinstance(surface, str):
            signatures[(case_id, surface)] = {
                "selected_workflow": item.get("selected_workflow"),
                "selected_skills": string_list(item.get("selected_skills")),
                "selected_tools": string_list(item.get("selected_tools")),
                "route_rules": string_list(item.get("route_rules")),
            }
    return signatures


def phase204_case_by_id(phase204_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases: dict[str, dict[str, Any]] = {}
    for item in object_list(phase204_report.get("phase_cases")):
        case_id = item.get("case_id")
        if isinstance(case_id, str) and case_id not in cases:
            cases[case_id] = copy.deepcopy(item)
    return cases


def validate_phase204_source_report(phase204_report: dict[str, Any], selector_contract_policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    errors.extend(f"selector contract policy invalid: {error}" for error in validate_phase204_policy(selector_contract_policy))
    errors.extend(f"phase204 report invalid: {error}" for error in validate_phase204_report(phase204_report, selector_contract_policy))
    if phase204_report.get("status") != "passed" or phase204_report.get("mode") != "live":
        errors.append("phase204 report must be a passing live report")
    if phase204_report.get("phase_closeout_eligible") is not True:
        errors.append("phase204 report must be closeout eligible")
    if object_list(phase204_report.get("prompt_contract_errors")):
        errors.append("phase204 report must not contain prompt contract errors")
    if object_list(phase204_report.get("policy_errors")):
        errors.append("phase204 report must not contain policy errors")
    if string_list(phase204_report.get("errors")):
        errors.append("phase204 report must not contain errors")
    phase_cases = object_list(phase204_report.get("phase_cases"))
    if not phase_cases:
        errors.append("phase204 report must contain phase_cases for exact target replay")
    phase_case_ids = {str(item.get("case_id")) for item in phase_cases if isinstance(item.get("case_id"), str)}
    result_case_ids = {str(item.get("case_id")) for item in object_list(phase204_report.get("results")) if isinstance(item.get("case_id"), str)}
    missing = sorted(result_case_ids - phase_case_ids)
    if missing:
        errors.append("phase204 phase_cases missing result case id(s): " + ", ".join(missing))
    return errors


def validate_matrix_source_report(matrix_report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if matrix_report.get("kind") != "workflow_skill_tool_selection_matrix_report":
        errors.append("matrix report kind must be workflow_skill_tool_selection_matrix_report")
    if matrix_report.get("phase") != 203:
        errors.append("matrix report phase must be 203")
    if matrix_report.get("status") != "passed":
        errors.append("matrix report status must be passed")
    if string_list(matrix_report.get("validation_errors")):
        errors.append("matrix report validation_errors must be empty")
    summary = dict_value(matrix_report.get("summary"))
    if int(summary.get("validation_error_count") or 0) != 0:
        errors.append("matrix report summary.validation_error_count must be 0")
    if not object_list(matrix_report.get("matrix_records")):
        errors.append("matrix report matrix_records must be non-empty")
    source_refs = dict_value(matrix_report.get("source_refs"))
    for source_key in ("skills", "tools"):
        source_ref = dict_value(source_refs.get(source_key))
        if source_ref.get("exists") is not True:
            errors.append(f"matrix report source_refs.{source_key}.exists must be true")
        source_path = source_ref.get("path")
        if not isinstance(source_path, str) or not source_path:
            errors.append(f"matrix report source_refs.{source_key}.path must be non-empty")
        elif not Path(source_path).is_file():
            errors.append(f"matrix report source_refs.{source_key}.path must exist")
    return errors


def route_signature(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "selected_workflow": item.get("selected_workflow"),
        "selected_skills": string_list(item.get("selected_skills")),
        "selected_tools": string_list(item.get("selected_tools")),
        "route_rules": string_list(item.get("route_rules")),
    }


def signature_errors(
    *,
    label: str,
    actual: dict[str, Any],
    expected: dict[str, Any],
    compare_exact_rules: bool,
    compare_exact_skills: bool,
    compare_exact_tools: bool,
) -> list[str]:
    errors: list[str] = []
    if actual.get("selected_workflow") != expected.get("selected_workflow"):
        errors.append(f"{label} workflow_drift expected {expected.get('selected_workflow')} got {actual.get('selected_workflow')}")
    expected_rules = set(string_list(expected.get("route_rules")))
    actual_rules = set(string_list(actual.get("route_rules")))
    if compare_exact_rules:
        if string_list(actual.get("route_rules")) != string_list(expected.get("route_rules")):
            errors.append(
                f"{label} route_rule_drift expected {string_list(expected.get('route_rules'))} got {string_list(actual.get('route_rules'))}"
            )
    elif not expected_rules <= actual_rules:
        errors.append(f"{label} route_rule_drift missing {sorted(expected_rules - actual_rules)}")
    expected_skills = string_list(expected.get("selected_skills"))
    actual_skills = string_list(actual.get("selected_skills"))
    if compare_exact_skills:
        if actual_skills != expected_skills:
            errors.append(f"{label} skill_selection_drift expected {expected_skills} got {actual_skills}")
    elif not set(expected_skills) <= set(actual_skills):
        errors.append(f"{label} skill_selection_drift missing {sorted(set(expected_skills) - set(actual_skills))}")
    expected_tools = string_list(expected.get("selected_tools"))
    actual_tools = string_list(actual.get("selected_tools"))
    if compare_exact_tools:
        if actual_tools != expected_tools:
            errors.append(f"{label} tool_selection_drift expected {expected_tools} got {actual_tools}")
    elif not set(expected_tools) <= set(actual_tools):
        errors.append(f"{label} tool_selection_drift missing {sorted(set(expected_tools) - set(actual_tools))}")
    return errors


def holdout_signature_alignment_errors(
    *,
    label: str,
    signature: dict[str, Any],
    matrix_expectation: dict[str, Any],
    registered_skills: set[str],
    registered_tools: set[str],
) -> list[str]:
    errors = signature_errors(
        label=label,
        actual=signature,
        expected=matrix_expectation,
        compare_exact_rules=True,
        compare_exact_skills=False,
        compare_exact_tools=False,
    )
    extra_skills = sorted(set(string_list(signature.get("selected_skills"))) - set(string_list(matrix_expectation.get("selected_skills"))))
    extra_tools = sorted(set(string_list(signature.get("selected_tools"))) - set(string_list(matrix_expectation.get("selected_tools"))))
    unregistered_skills = sorted(set(extra_skills) - registered_skills)
    unregistered_tools = sorted(set(extra_tools) - registered_tools)
    if unregistered_skills:
        errors.append(f"{label} skill_selection_drift unregistered extras {unregistered_skills}")
    if unregistered_tools:
        errors.append(f"{label} tool_selection_drift unregistered extras {unregistered_tools}")
    return errors


def build_replay_cases(
    *,
    policy: dict[str, Any],
    phase204_report: dict[str, Any],
    matrix_report: dict[str, Any],
    target_catalog: dict[str, Any],
    holdout_catalog: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    matrix = matrix_by_route_rule(matrix_report)
    registered_skills, registered_tools = registered_selection_ids(matrix_report)
    target_cases = cases_by_id(prompt_cases_from_catalog(target_catalog))
    holdout_cases = cases_by_id(prompt_cases_from_catalog(holdout_catalog))
    phase204_case_ids = string_list(dict_value(phase204_report.get("summary")).get("case_ids"))
    phase204_cases = phase204_case_by_id(phase204_report)
    holdout_signatures = dict_value(policy.get("holdout_expected_signatures"))
    replay_cases: list[dict[str, Any]] = []
    if len(phase204_case_ids) < int(policy.get("minimum_target_case_count", 30)):
        errors.append("phase204 target case count below policy.minimum_target_case_count")
    if len(phase204_case_ids) != int(policy.get("required_target_case_count", 0)):
        errors.append("phase204 target case count must equal policy.required_target_case_count")
    if len(string_list(policy.get("holdout_case_ids"))) != int(policy.get("required_holdout_case_count", 0)):
        errors.append("holdout case count must equal policy.required_holdout_case_count")
    for case_id in phase204_case_ids:
        if case_id not in target_cases:
            errors.append(f"phase204 target case {case_id} missing from target catalog")
            continue
        replay_case = phase204_cases.get(case_id)
        if replay_case is None:
            errors.append(f"phase204 target case {case_id} missing from phase204 phase_cases")
            continue
        replay_case["replay_set"] = "target"
        replay_cases.append(replay_case)
    for case_id in string_list(policy.get("holdout_case_ids")):
        case = holdout_cases.get(case_id)
        if case is None:
            errors.append(f"holdout case {case_id} missing from holdout catalog")
            continue
        matrix_record = matrix.get(case.expected_rule)
        if matrix_record is None:
            errors.append(f"holdout case {case_id} rule {case.expected_rule} missing from matrix")
            continue
        replay_case = phase204_case_from_prompt(case, matrix_record)
        replay_case["case_id"] = f"H-{case.case_id}"
        replay_case["source_case_id"] = case.case_id
        replay_case["replay_set"] = "holdout"
        exact_signature = dict_value(holdout_signatures.get(case.case_id))
        replay_case["expected_holdout_signature"] = exact_signature
        signature_matrix_errors = holdout_signature_alignment_errors(
            label=f"holdout {case.case_id} policy signature",
            signature=exact_signature,
            matrix_expectation={
                "selected_workflow": replay_case.get("expected_selected_workflow"),
                "route_rules": replay_case.get("expected_route_rules"),
                "selected_skills": replay_case.get("expected_selected_skills"),
                "selected_tools": replay_case.get("expected_selected_tools"),
            },
            registered_skills=registered_skills,
            registered_tools=registered_tools,
        )
        errors.extend(signature_matrix_errors)
        replay_cases.append(replay_case)
    target_roots = {str(item.get("target_root")) for item in replay_cases if isinstance(item.get("target_root"), str)}
    missing_roots = sorted(set(string_list(policy.get("required_target_roots"))) - target_roots)
    if missing_roots:
        errors.append("replay cases missing required target roots: " + ", ".join(missing_roots))
    return replay_cases, errors


def compare_replay_result(
    *,
    item: dict[str, Any],
    phase204_signatures: dict[tuple[str, str], dict[str, Any]],
) -> list[str]:
    if item.get("status") != ExplainabilityStatus.PASSED.value:
        return [f"{item.get('case_id')}.{item.get('surface')} replay response failed"]
    label = f"{item.get('case_id')}.{item.get('surface')}"
    errors: list[str] = []
    if not isinstance(item.get("run_id"), str) or not str(item.get("run_id")).strip() or item.get("run_id") == "unknown":
        errors.append(f"{label} missing_run_id")
    replay_set = item.get("replay_set")
    actual = route_signature(item)
    if replay_set == "target":
        expected = phase204_signatures.get((str(item.get("case_id")), str(item.get("surface"))))
        if expected is None:
            return [f"{label} missing Phase 204 baseline signature"]
        errors.extend(
            signature_errors(
                label=label,
                actual=actual,
                expected=expected,
                compare_exact_rules=True,
                compare_exact_skills=True,
                compare_exact_tools=True,
            )
        )
        return errors
    expected = dict_value(item.get("expected_holdout_signature"))
    if not expected:
        errors.append(f"{label} missing holdout expected signature")
        return errors
    errors.extend(
        signature_errors(
            label=label,
            actual=actual,
            expected=expected,
            compare_exact_rules=True,
            compare_exact_skills=True,
            compare_exact_tools=True,
        )
    )
    return errors


def decorate_result(item: dict[str, Any], replay_case: dict[str, Any]) -> dict[str, Any]:
    return {
        **item,
        "replay_set": replay_case.get("replay_set"),
        "source_case_id": replay_case.get("source_case_id", replay_case.get("case_id")),
        "expected_workflow": replay_case.get("expected_selected_workflow"),
        "expected_route_rule": string_list(replay_case.get("expected_route_rules"))[0]
        if string_list(replay_case.get("expected_route_rules"))
        else "",
        "expected_selected_skills": string_list(replay_case.get("expected_selected_skills")),
        "expected_selected_tools": string_list(replay_case.get("expected_selected_tools")),
        "expected_holdout_signature": dict_value(replay_case.get("expected_holdout_signature")),
    }


def validate_live_result_coverage(
    *,
    policy: dict[str, Any],
    replay_cases: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    required_surfaces = set(string_list(policy.get("required_surfaces")))
    expected_pairs = {
        (str(case.get("case_id")), surface)
        for case in replay_cases
        if isinstance(case.get("case_id"), str)
        for surface in required_surfaces
    }
    actual_pairs = {
        (str(item.get("case_id")), str(item.get("surface")))
        for item in results
        if isinstance(item.get("case_id"), str) and isinstance(item.get("surface"), str)
    }
    missing_pairs = sorted(expected_pairs - actual_pairs)
    extra_pairs = sorted(actual_pairs - expected_pairs)
    if missing_pairs:
        errors.append("live replay missing required case/surface pair(s): " + ", ".join(f"{case}:{surface}" for case, surface in missing_pairs))
    if extra_pairs:
        errors.append("live replay contains unexpected case/surface pair(s): " + ", ".join(f"{case}:{surface}" for case, surface in extra_pairs))
    if len(results) != len(expected_pairs):
        errors.append(f"live replay response_count {len(results)} must equal required case/surface pair count {len(expected_pairs)}")
    required_live_response_count = int(policy.get("required_live_response_count", 0))
    if len(results) != required_live_response_count:
        errors.append(f"live replay response_count {len(results)} must equal policy.required_live_response_count {required_live_response_count}")
    actual_surfaces = {str(item.get("surface")) for item in results if isinstance(item.get("surface"), str)}
    if actual_surfaces != required_surfaces:
        errors.append(f"live replay surfaces expected {sorted(required_surfaces)} got {sorted(actual_surfaces)}")
    target_roots = {str(item.get("target_root")) for item in replay_cases if isinstance(item.get("target_root"), str)}
    required_roots = set(string_list(policy.get("required_target_roots")))
    if not required_roots <= target_roots:
        errors.append("live replay missing required target roots: " + ", ".join(sorted(required_roots - target_roots)))
    for item in results:
        run_id = item.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip() or run_id == "unknown":
            errors.append(f"{item.get('case_id')}.{item.get('surface')} missing_run_id")
    return errors


def run_live_replay(
    *,
    config: RouteStabilityHoldoutReplayConfig,
    policy: dict[str, Any],
    selector_contract_policy: dict[str, Any],
    replay_cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    phase204_config = NoManualSkillInjectionExplainabilityConfig(
        config_root=config.config_root,
        model_base_url=config.model_base_url,
        workflow_router_gateway_base_url=config.workflow_router_gateway_base_url,
        controller_base_url=config.controller_base_url,
        anythingllm_api_base_url=config.anythingllm_api_base_url,
        workspace=config.workspace,
        api_key_env=config.api_key_env,
        timeout_seconds=config.timeout_seconds,
        live=True,
    )
    api_key = os.environ.get(config.api_key_env) or ""
    results: list[dict[str, Any]] = []
    for replay_case in replay_cases:
        for surface in string_list(policy.get("required_surfaces")):
            try:
                if surface == "gateway":
                    item = gateway_response(phase204_config, policy=selector_contract_policy, case=replay_case)
                elif surface == "anythingllm":
                    if not api_key:
                        raise RuntimeError(f"{config.api_key_env} is required for AnythingLLM validation")
                    item = anythingllm_response(
                        phase204_config,
                        policy=selector_contract_policy,
                        case=replay_case,
                        api_key=api_key,
                    )
                else:
                    raise RuntimeError(f"unsupported surface: {surface}")
            except Exception as exc:  # noqa: BLE001
                item = {
                    "case_id": replay_case.get("case_id"),
                    "surface": surface,
                    "target_root": replay_case.get("target_root"),
                    "status": ExplainabilityStatus.FAILED.value,
                    "run_id": "unknown",
                    "errors": [f"{surface} replay failed: {type(exc).__name__}: {exc}"],
                }
            decorated = decorate_result(item, replay_case)
            results.append(decorated)
            print(
                "PHASE205 {surface} {case_id} {status} run_id={run_id}".format(
                    surface=surface,
                    case_id=decorated.get("case_id"),
                    status=str(decorated.get("status")).upper(),
                    run_id=decorated.get("run_id", "unknown"),
                )
            )
    return results


def build_summary(*, replay_cases: list[dict[str, Any]], results: list[dict[str, Any]], errors: list[str]) -> dict[str, Any]:
    target_cases = [item for item in replay_cases if item.get("replay_set") == "target"]
    holdout_cases = [item for item in replay_cases if item.get("replay_set") == "holdout"]
    passed = [item for item in results if item.get("status") == ExplainabilityStatus.PASSED.value]
    failed = [item for item in results if item.get("status") != ExplainabilityStatus.PASSED.value]
    return {
        "target_case_count": len(target_cases),
        "holdout_case_count": len(holdout_cases),
        "response_count": len(results),
        "passed_response_count": len(passed),
        "failed_response_count": len(failed),
        "route_drift_count": len([error for error in errors if "_drift" in error]),
        "error_count": len(errors),
        "surfaces": sorted({str(item.get("surface")) for item in results if isinstance(item.get("surface"), str)}),
        "target_roots": sorted({str(item.get("target_root")) for item in replay_cases if isinstance(item.get("target_root"), str)}),
        "phase206_ready": not errors and bool(results),
    }


def validate_route_stability_holdout_replay(config: RouteStabilityHoldoutReplayConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = config.output_path or default_report_path(config_root, live=config.live)
    markdown_output_path = config.markdown_output_path or markdown_path_for(output_path)
    errors: list[str] = []
    policy: dict[str, Any] = {}
    selector_contract_policy: dict[str, Any] = {}
    phase204_report: dict[str, Any] = {}
    matrix_report: dict[str, Any] = {}
    replay_cases: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    try:
        policy = read_json_object(policy_path)
        errors.extend(validate_policy(policy))
        selector_contract_policy = read_json_object(
            resolve_path(config_root, str(policy.get("selector_contract_policy_path", "")))
        )
        phase204_report = read_json_object(resolve_path(config_root, str(policy.get("phase204_report_path", ""))))
        matrix_report = read_json_object(resolve_path(config_root, str(policy.get("source_matrix_report_path", ""))))
        target_catalog = load_prompt_catalog(config_root, resolve_path(config_root, str(policy.get("target_prompt_catalog_path", ""))))
        holdout_catalog = load_prompt_catalog(config_root, resolve_path(config_root, str(policy.get("holdout_prompt_catalog_path", ""))))
        errors.extend(validate_phase204_source_report(phase204_report, selector_contract_policy))
        errors.extend(validate_matrix_source_report(matrix_report))
        replay_cases, case_errors = build_replay_cases(
            policy=policy,
            phase204_report=phase204_report,
            matrix_report=matrix_report,
            target_catalog=target_catalog,
            holdout_catalog=holdout_catalog,
        )
        errors.extend(case_errors)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"load failed: {type(exc).__name__}: {exc}")

    if config.live and not errors:
        results = run_live_replay(
            config=config,
            policy=policy,
            selector_contract_policy=selector_contract_policy,
            replay_cases=replay_cases,
        )
        phase204_signatures = phase204_signature_by_case_surface(phase204_report)
        for item in results:
            errors.extend(compare_replay_result(item=item, phase204_signatures=phase204_signatures))
            errors.extend(str(error) for error in string_list(item.get("errors")) if item.get("status") != ExplainabilityStatus.PASSED.value)
        errors.extend(validate_live_result_coverage(policy=policy, replay_cases=replay_cases, results=results))
    elif not config.live and not errors:
        results = []

    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": RouteReplayStatus.PASSED.value if config.live and not errors and results else "preflight_passed" if not config.live and not errors else RouteReplayStatus.FAILED.value,
        "mode": "live" if config.live else "offline",
        "created_at": utc_timestamp(),
        "policy_path": str(policy_path),
        "summary": build_summary(replay_cases=replay_cases, results=results, errors=errors),
        "replay_cases": replay_cases,
        "results": results,
        "errors": errors,
    }
    write_json(output_path, report)
    write_text(markdown_output_path, markdown_report(report))
    report["report_path"] = str(output_path.resolve())
    report["markdown_report_path"] = str(markdown_output_path.resolve())
    write_json(output_path, report)
    return report


def markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Route Stability Holdout Replay",
        "",
        f"- Status: {report.get('status')}",
        f"- Mode: {report.get('mode')}",
        f"- Target cases: {summary.get('target_case_count')}",
        f"- Holdout cases: {summary.get('holdout_case_count')}",
        f"- Responses: {summary.get('passed_response_count')} passed / {summary.get('response_count')} total",
        f"- Route drift count: {summary.get('route_drift_count')}",
        "",
        "## Results",
        "",
        "| Set | Case | Surface | Status | Run ID |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in object_list(report.get("results")):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("replay_set")),
                    str(item.get("case_id")),
                    str(item.get("surface")),
                    str(item.get("status")),
                    str(item.get("run_id")),
                ]
            )
            + " |"
        )
    if report.get("errors"):
        lines.extend(["", "## Errors", ""])
        for error in string_list(report.get("errors")):
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"
