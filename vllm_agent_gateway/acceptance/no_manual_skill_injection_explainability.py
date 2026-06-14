"""Natural-prompt selector explainability gate for Phase 204.

This module adapts prompt-catalog cases to the existing Phase 151 selector
explainability validator. It must not perform independent workflow, skill, or
tool selection; it validates the route-decision and registry artifacts produced
by the live workflow-router path.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.skill_selection_hardening import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    artifact_json,
    assert_fixture_state_unchanged,
    controller_run_record,
    fixture_state,
    json_request,
    text_response,
)
from vllm_agent_gateway.acceptance.skill_tool_selection_explainability_e2e import (
    ExplainabilityStatus,
    response_result,
    run_id_from_text,
    validate_text_against_route,
)
from vllm_agent_gateway.prompt_catalogs import (
    PromptCatalogCase,
    load_prompt_catalog,
    prompt_cases_from_catalog,
    validate_prompt_catalog,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "no_manual_skill_injection_explainability_policy"
EXPECTED_REPORT_KIND = "no_manual_skill_injection_explainability_report"
EXPECTED_PHASE = 204
EXPECTED_BACKLOG_ID = "P0-M3-204"
DEFAULT_POLICY_PATH = Path("runtime") / "no_manual_skill_injection_explainability_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "phase204"


class Phase204Surface(str, Enum):
    GATEWAY = "gateway"
    ANYTHINGLLM = "anythingllm"


@dataclass(frozen=True)
class NoManualSkillInjectionExplainabilityConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    markdown_output_path: Path | None = None
    include_gateway: bool = True
    include_anythingllm: bool = True
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 900
    case_ids: tuple[str, ...] = ()
    allow_partial: bool = False
    live: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path, *, live: bool) -> Path:
    filename = (
        "phase204-no-manual-skill-injection-explainability-report.json"
        if live
        else "phase204-no-manual-skill-injection-explainability-preflight-report.json"
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


def int_value(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 204")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    version = str(policy.get("policy_version") or "")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        errors.append("policy.policy_version must use semantic version x.y.z")
    purpose = str(policy.get("purpose") or "").lower()
    for phrase in ("natural-language prompts", "without manual skill injection", "existing workflow-router path"):
        if phrase not in purpose:
            errors.append(f"policy.purpose must mention {phrase!r}")
    for key in (
        "source_prompt_catalog_path",
        "source_matrix_report_path",
    ):
        if not isinstance(policy.get(key), str) or not str(policy[key]).strip():
            errors.append(f"policy.{key} must be a non-empty string")
    if len(string_list(policy.get("case_ids"))) < int_value(policy.get("minimum_case_count"), 30):
        errors.append("policy.case_ids must satisfy policy.minimum_case_count")
    if set(string_list(policy.get("required_surfaces"))) != {Phase204Surface.GATEWAY.value, Phase204Surface.ANYTHINGLLM.value}:
        errors.append("policy.required_surfaces must be gateway and anythingllm")
    for key in (
        "required_target_roots",
        "required_chat_sections",
        "required_result_markers",
        "required_selection_markers",
        "required_grounding_markers",
        "forbidden_prompt_markers",
        "forbidden_raw_internal_markers",
        "artifact_requirements",
    ):
        if not string_list(policy.get(key)):
            errors.append(f"policy.{key} must be a non-empty string list")
    if int_value(policy.get("minimum_matrix_row_coverage"), 0) < 20:
        errors.append("policy.minimum_matrix_row_coverage must be at least 20")
    if int_value(policy.get("minimum_rejected_candidate_count"), -1) < 1:
        errors.append("policy.minimum_rejected_candidate_count must be at least 1")
    if policy.get("forbidden_prompt_skill_ids_from_matrix") is not True:
        errors.append("policy.forbidden_prompt_skill_ids_from_matrix must be true")
    if policy.get("non_mutation_required") is not True:
        errors.append("policy.non_mutation_required must be true")
    expected_selection_policy = {
        "metadata_only": True,
        "manual_skill_injection_required": False,
        "low_confidence_fails_closed": True,
        "minimum_confidence": "medium",
    }
    selection_policy = dict_value(policy.get("required_selection_policy"))
    for key, expected in expected_selection_policy.items():
        if selection_policy.get(key) != expected:
            errors.append(f"policy.required_selection_policy.{key} must be {expected!r}")
    return errors


def matrix_records(report: dict[str, Any]) -> list[dict[str, Any]]:
    return object_list(report.get("matrix_records"))


def matrix_by_route_rule(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_rule: dict[str, dict[str, Any]] = {}
    for record in matrix_records(report):
        rule = record.get("route_rule")
        if isinstance(rule, str) and rule.strip() and rule not in by_rule:
            by_rule[rule] = record
    return by_rule


def selected_prompt_cases(cases: tuple[PromptCatalogCase, ...], policy: dict[str, Any], override_ids: tuple[str, ...]) -> tuple[PromptCatalogCase, ...]:
    case_ids = override_ids or tuple(string_list(policy.get("case_ids")))
    by_id = {case.case_id: case for case in cases}
    missing = sorted(set(case_ids) - set(by_id))
    if missing:
        raise RuntimeError("unknown prompt catalog case id(s): " + ", ".join(missing))
    return tuple(by_id[case_id] for case_id in case_ids)


def explicit_skill_markers(records: list[dict[str, Any]]) -> set[str]:
    markers: set[str] = set()
    for record in records:
        for key in ("selected_skill_ids", "registered_skills"):
            markers.update(item.lower() for item in string_list(record.get(key)))
    return markers


def prompt_contract_errors(
    *,
    policy: dict[str, Any],
    cases: tuple[PromptCatalogCase, ...],
    matrix_report: dict[str, Any],
    enforce_suite_floor: bool = True,
) -> list[str]:
    errors: list[str] = []
    by_rule = matrix_by_route_rule(matrix_report)
    skill_markers = explicit_skill_markers(matrix_records(matrix_report))
    forbidden_prompt_markers = [marker.lower() for marker in string_list(policy.get("forbidden_prompt_markers"))]
    required_targets = set(string_list(policy.get("required_target_roots")))
    covered_matrix_entries: set[str] = set()
    target_roots: set[str] = set()

    for case in cases:
        target_roots.add(case.target_root)
        prompt_lower = case.prompt.lower()
        found_internal = [marker for marker in forbidden_prompt_markers if marker in prompt_lower]
        if found_internal:
            errors.append(f"{case.case_id} prompt contains forbidden internal marker(s): {found_internal}")
        found_skills = sorted(marker for marker in skill_markers if marker and marker in prompt_lower)
        if found_skills:
            errors.append(f"{case.case_id} prompt explicitly names skill id(s): {found_skills}")
        record = by_rule.get(case.expected_rule)
        if record is None:
            errors.append(f"{case.case_id} expected_rule {case.expected_rule} is missing from Phase 203 matrix")
            continue
        if record.get("expected_workflow") != case.expected_workflow:
            errors.append(
                f"{case.case_id} workflow mismatch between catalog and matrix: "
                f"{case.expected_workflow!r} vs {record.get('expected_workflow')!r}"
            )
        if not string_list(record.get("selected_tool_ids")) and case.expected_workflow != "task.decompose":
            errors.append(f"{case.case_id} matrix record has no selected tools for non-decomposition workflow")
        entry_id = record.get("entry_id")
        if isinstance(entry_id, str):
            covered_matrix_entries.add(entry_id)
    if enforce_suite_floor:
        missing_targets = sorted(required_targets - target_roots)
        if missing_targets:
            errors.append("selected cases do not cover required target roots: " + ", ".join(missing_targets))
        minimum_coverage = int_value(policy.get("minimum_matrix_row_coverage"), 0)
        if len(covered_matrix_entries) < minimum_coverage:
            errors.append(
                f"matrix row coverage {len(covered_matrix_entries)} below policy.minimum_matrix_row_coverage {minimum_coverage}"
            )
    return errors


def phase204_case_from_prompt(case: PromptCatalogCase, matrix_record: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "source": "prompt_catalog",
        "prompt_family": matrix_record.get("prompt_family") or case.expected_rule,
        "prompt": case.prompt,
        "target_root": case.target_root,
        "expected_selected_workflow": case.expected_workflow,
        "expected_route_rules": [case.expected_rule],
        "expected_selected_skills": string_list(matrix_record.get("selected_skill_ids")),
        "expected_selected_tools": string_list(matrix_record.get("selected_tool_ids")),
        "coverage_entry_ids": [str(matrix_record.get("entry_id"))] if isinstance(matrix_record.get("entry_id"), str) else [],
        "matrix_entry_id": matrix_record.get("entry_id"),
    }


def gateway_response(
    config: NoManualSkillInjectionExplainabilityConfig,
    *,
    policy: dict[str, Any],
    case: dict[str, Any],
) -> dict[str, Any]:
    target_root = str(case["target_root"])
    before = fixture_state(target_root)
    status, body = json_request(
        f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": str(case["prompt"])}],
            "role_base_url": config.model_base_url,
            "budgets": {"max_model_calls": 3, "max_selected_skills": 5, "max_selected_tools": 5},
        },
        timeout_seconds=config.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"gateway returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    compact = dict_value(body.get("agentic_controller_response"))
    if not compact:
        raise RuntimeError("gateway response did not include agentic_controller_response")
    text = text_response(body)
    run_id = str(compact.get("run_id") or "unknown")
    route_decision = artifact_json(compact, "route_decision")
    registry_snapshot = artifact_json(compact, "registry_snapshot")
    assert_fixture_state_unchanged(before, target_root, f"gateway {case.get('case_id')}")
    return response_result(
        policy=policy,
        case=case,
        target_root=target_root,
        surface=Phase204Surface.GATEWAY.value,
        text=text,
        run_id=run_id,
        route_decision=route_decision,
        registry_snapshot=registry_snapshot,
    )


def anythingllm_response(
    config: NoManualSkillInjectionExplainabilityConfig,
    *,
    policy: dict[str, Any],
    case: dict[str, Any],
    api_key: str,
) -> dict[str, Any]:
    target_root = str(case["target_root"])
    before = fixture_state(target_root)
    status, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={
            "message": str(case["prompt"]),
            "mode": "chat",
            "sessionId": f"phase204-no-manual-skill-injection-{case.get('case_id', 'case').lower()}-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=config.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"AnythingLLM returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    run_id = run_id_from_text(text)
    if run_id == "unknown":
        raise RuntimeError("AnythingLLM response did not include workflow-router run_id")
    record = controller_run_record(config, run_id)
    route_decision = artifact_json(record, "route_decision")
    registry_snapshot = artifact_json(record, "registry_snapshot")
    assert_fixture_state_unchanged(before, target_root, f"AnythingLLM {case.get('case_id')}")
    return response_result(
        policy=policy,
        case=case,
        target_root=target_root,
        surface=Phase204Surface.ANYTHINGLLM.value,
        text=text,
        run_id=run_id,
        route_decision=route_decision,
        registry_snapshot=registry_snapshot,
    )


def build_summary(
    *,
    selected_cases: tuple[PromptCatalogCase, ...],
    phase_cases: list[dict[str, Any]],
    results: list[dict[str, Any]],
    policy_errors: list[str],
    prompt_errors: list[str],
    matrix_report: dict[str, Any],
) -> dict[str, Any]:
    passed = [item for item in results if item.get("status") == ExplainabilityStatus.PASSED.value]
    failed = [item for item in results if item.get("status") == ExplainabilityStatus.FAILED.value]
    skipped = [item for item in results if item.get("status") == ExplainabilityStatus.SKIPPED.value]
    selected_entry_ids = sorted({str(item.get("matrix_entry_id")) for item in phase_cases if isinstance(item.get("matrix_entry_id"), str)})
    matrix_entry_ids = sorted(
        str(item.get("entry_id")) for item in matrix_records(matrix_report) if isinstance(item.get("entry_id"), str)
    )
    uncovered = sorted(set(matrix_entry_ids) - set(selected_entry_ids))
    return {
        "case_count": len(selected_cases),
        "case_ids": sorted(case.case_id for case in selected_cases),
        "matrix_record_count": len(matrix_entry_ids),
        "matrix_row_coverage_count": len(selected_entry_ids),
        "uncovered_matrix_row_count": len(uncovered),
        "uncovered_matrix_entry_ids": uncovered,
        "target_roots": sorted({case.target_root for case in selected_cases}),
        "surfaces": sorted({str(item.get("surface")) for item in results if isinstance(item.get("surface"), str)}),
        "response_count": len(results),
        "passed_response_count": len(passed),
        "failed_response_count": len(failed),
        "skipped_response_count": len(skipped),
        "policy_error_count": len(policy_errors),
        "prompt_contract_error_count": len(prompt_errors),
        "manual_skill_injection_required": False if not prompt_errors else "unknown",
        "phase205_holdout_replay_still_required": True,
    }


def validate_report(report: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append("report.schema_version must be 1")
    if report.get("kind") != EXPECTED_REPORT_KIND:
        errors.append(f"report.kind must be {EXPECTED_REPORT_KIND}")
    if report.get("phase") != EXPECTED_PHASE:
        errors.append("report.phase must be 204")
    if report.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"report.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    summary = dict_value(report.get("summary"))
    minimum_cases = int_value(policy.get("minimum_case_count"), 30)
    minimum_matrix_coverage = int_value(policy.get("minimum_matrix_row_coverage"), 25)
    partial_case_filter = report.get("partial_case_filter") is True
    if not partial_case_filter and int_value(summary.get("case_count")) < minimum_cases:
        errors.append("report.summary.case_count below policy.minimum_case_count")
    if not partial_case_filter and int_value(summary.get("matrix_row_coverage_count")) < minimum_matrix_coverage:
        errors.append("report.summary.matrix_row_coverage_count below policy.minimum_matrix_row_coverage")
    if int_value(summary.get("policy_error_count")):
        errors.append("report contains policy errors")
    if int_value(summary.get("prompt_contract_error_count")):
        errors.append("report contains prompt contract errors")
    results = object_list(report.get("results"))
    if report.get("mode") == "live":
        if not results:
            errors.append("live report.results must contain response results")
        required_surfaces = set(string_list(policy.get("required_surfaces")))
        actual_surfaces = set(summary.get("surfaces") if isinstance(summary.get("surfaces"), list) else [])
        policy_case_ids = set(string_list(policy.get("case_ids")))
        actual_case_ids = set(summary.get("case_ids") if isinstance(summary.get("case_ids"), list) else [])
        if not partial_case_filter:
            if actual_case_ids != policy_case_ids:
                errors.append("live report must cover all policy case_ids")
            if actual_surfaces != required_surfaces:
                errors.append("live report must cover all required surfaces")
            expected_pairs = {(case_id, surface) for case_id in policy_case_ids for surface in required_surfaces}
            actual_pairs = {
                (str(item.get("case_id")), str(item.get("surface")))
                for item in results
                if isinstance(item.get("case_id"), str) and isinstance(item.get("surface"), str)
            }
            missing_pairs = sorted(expected_pairs - actual_pairs)
            extra_pairs = sorted(actual_pairs - expected_pairs)
            if missing_pairs:
                errors.append("live report missing required case/surface pair(s): " + ", ".join(f"{case}:{surface}" for case, surface in missing_pairs))
            if extra_pairs:
                errors.append("live report contains unexpected case/surface pair(s): " + ", ".join(f"{case}:{surface}" for case, surface in extra_pairs))
            if len(results) != len(expected_pairs):
                errors.append(f"live report response_count {len(results)} must equal required case/surface pair count {len(expected_pairs)}")
        failed = [item for item in results if item.get("status") != ExplainabilityStatus.PASSED.value]
        if failed:
            errors.append("live report cannot contain failed or skipped response results")
    return errors


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    summary = dict_value(report.get("summary"))
    lines = [
        "# No Manual Skill Injection Explainability",
        "",
        f"- Status: {report.get('status')}",
        f"- Mode: {report.get('mode')}",
        f"- Created at: {report.get('created_at')}",
        f"- Cases: {summary.get('case_count')}",
        f"- Matrix rows covered: {summary.get('matrix_row_coverage_count')} / {summary.get('matrix_record_count')}",
        f"- Responses: {summary.get('passed_response_count')} passed / {summary.get('response_count')} total",
        f"- Phase 205 holdout replay still required: {summary.get('phase205_holdout_replay_still_required')}",
        "",
        "## Results",
        "",
        "| Case | Surface | Target | Status | Run ID | Matrix Entry |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    matrix_entry_by_case = {
        str(item.get("case_id")): str(item.get("matrix_entry_id"))
        for item in object_list(report.get("phase_cases"))
        if isinstance(item.get("case_id"), str)
    }
    for item in object_list(report.get("results")):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("case_id")),
                    str(item.get("surface")),
                    Path(str(item.get("target_root"))).name,
                    str(item.get("status")),
                    str(item.get("run_id")),
                    matrix_entry_by_case.get(str(item.get("case_id")), ""),
                ]
            )
            + " |"
        )
    if report.get("errors"):
        lines.extend(["", "## Errors", ""])
        for error in string_list(report.get("errors")):
            lines.append(f"- {error}")
    write_text(path, "\n".join(lines) + "\n")


def validate_no_manual_skill_injection_explainability(
    config: NoManualSkillInjectionExplainabilityConfig,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = config.output_path or default_report_path(config_root, live=config.live)
    markdown_output_path = config.markdown_output_path or markdown_path_for(output_path)
    policy_errors: list[str] = []
    prompt_errors: list[str] = []
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    policy: dict[str, Any] = {}
    prompt_catalog: dict[str, Any] = {}
    matrix_report: dict[str, Any] = {}
    selected_cases: tuple[PromptCatalogCase, ...] = ()
    phase_cases: list[dict[str, Any]] = []

    try:
        policy = read_json_object(policy_path)
        policy_errors = validate_policy(policy)
        prompt_catalog_path = resolve_path(config_root, str(policy.get("source_prompt_catalog_path", "")))
        matrix_report_path = resolve_path(config_root, str(policy.get("source_matrix_report_path", "")))
        prompt_catalog = load_prompt_catalog(config_root, prompt_catalog_path)
        matrix_report = read_json_object(matrix_report_path)
        catalog_errors = validate_prompt_catalog(prompt_catalog)
        if catalog_errors:
            prompt_errors.extend(catalog_errors)
        all_cases = prompt_cases_from_catalog(prompt_catalog) if not catalog_errors else ()
        selected_cases = selected_prompt_cases(all_cases, policy, config.case_ids) if all_cases else ()
        enforce_suite_floor = not (config.case_ids and config.allow_partial)
        prompt_errors.extend(
            prompt_contract_errors(
                policy=policy,
                cases=selected_cases,
                matrix_report=matrix_report,
                enforce_suite_floor=enforce_suite_floor,
            )
        )
        by_rule = matrix_by_route_rule(matrix_report)
        phase_cases = [
            phase204_case_from_prompt(case, by_rule[case.expected_rule])
            for case in selected_cases
            if case.expected_rule in by_rule
        ]
    except Exception as exc:  # noqa: BLE001
        policy_errors.append(f"load failed: {type(exc).__name__}: {exc}")

    errors.extend(policy_errors)
    errors.extend(prompt_errors)

    if not errors and config.live:
        if not config.include_gateway and Phase204Surface.GATEWAY.value in string_list(policy.get("required_surfaces")):
            errors.append("gateway validation is required by policy")
        if not config.include_anythingllm and Phase204Surface.ANYTHINGLLM.value in string_list(policy.get("required_surfaces")):
            errors.append("AnythingLLM validation is required by policy")
        if config.include_gateway:
            for case in phase_cases:
                try:
                    result = gateway_response(config, policy=policy, case=case)
                except Exception as exc:  # noqa: BLE001
                    result = {
                        "case_id": case.get("case_id"),
                        "surface": Phase204Surface.GATEWAY.value,
                        "target_root": case.get("target_root"),
                        "status": ExplainabilityStatus.FAILED.value,
                        "run_id": "unknown",
                        "errors": [f"gateway request failed: {type(exc).__name__}: {exc}"],
                    }
                results.append(result)
                print(
                    "PHASE204 {surface} {case_id} {status} run_id={run_id}".format(
                        surface=Phase204Surface.GATEWAY.value,
                        case_id=case.get("case_id"),
                        status=str(result.get("status")).upper(),
                        run_id=result.get("run_id", "unknown"),
                    )
                )
        api_key = os.environ.get(config.api_key_env) or ""
        if config.include_anythingllm:
            if not api_key:
                errors.append(f"{config.api_key_env} is required for AnythingLLM validation")
            else:
                for case in phase_cases:
                    try:
                        result = anythingllm_response(config, policy=policy, case=case, api_key=api_key)
                    except Exception as exc:  # noqa: BLE001
                        result = {
                            "case_id": case.get("case_id"),
                            "surface": Phase204Surface.ANYTHINGLLM.value,
                            "target_root": case.get("target_root"),
                            "status": ExplainabilityStatus.FAILED.value,
                            "run_id": "unknown",
                            "errors": [f"AnythingLLM request failed: {type(exc).__name__}: {exc}"],
                        }
                    results.append(result)
                    print(
                        "PHASE204 {surface} {case_id} {status} run_id={run_id}".format(
                            surface=Phase204Surface.ANYTHINGLLM.value,
                            case_id=case.get("case_id"),
                            status=str(result.get("status")).upper(),
                            run_id=result.get("run_id", "unknown"),
                        )
                    )

    errors.extend(
        error
        for item in results
        for error in string_list(item.get("errors"))
        if item.get("status") != ExplainabilityStatus.PASSED.value
    )
    summary = build_summary(
        selected_cases=selected_cases,
        phase_cases=phase_cases,
        results=results,
        policy_errors=policy_errors,
        prompt_errors=prompt_errors,
        matrix_report=matrix_report,
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": (
            ExplainabilityStatus.PASSED.value
            if config.live and not errors and results
            else "preflight_passed"
            if not config.live and not errors
            else ExplainabilityStatus.FAILED.value
        ),
        "mode": "live" if config.live else "offline",
        "partial_case_filter": bool(config.case_ids and config.allow_partial),
        "phase_closeout_eligible": bool(config.live and not (config.case_ids and config.allow_partial)),
        "created_at": utc_timestamp(),
        "config_root": str(config_root),
        "policy_path": str(policy_path),
        "policy_sha256": sha256_path(policy_path) if policy_path.is_file() else None,
        "source_prompt_catalog_path": str(resolve_path(config_root, str(policy.get("source_prompt_catalog_path", ""))))
        if policy
        else "",
        "source_matrix_report_path": str(resolve_path(config_root, str(policy.get("source_matrix_report_path", ""))))
        if policy
        else "",
        "policy_errors": policy_errors,
        "prompt_contract_errors": prompt_errors,
        "summary": summary,
        "phase_cases": phase_cases,
        "results": results,
        "errors": errors,
    }
    validation_errors = validate_report(report, policy or {})
    if validation_errors:
        report["status"] = ExplainabilityStatus.FAILED.value
        report["errors"] = errors + validation_errors
    write_json(output_path, report)
    write_markdown(markdown_output_path, report)
    report["report_path"] = str(output_path.resolve())
    report["markdown_report_path"] = str(markdown_output_path.resolve())
    write_json(output_path, report)
    return report


def validate_text_against_phase204_case(
    *,
    policy: dict[str, Any],
    case: dict[str, Any],
    text: str,
    route_decision: dict[str, Any],
    registry_snapshot: dict[str, Any],
) -> list[str]:
    return validate_text_against_route(
        policy=policy,
        case=case,
        target_root=str(case["target_root"]),
        surface="unit",
        text=text,
        route_decision=route_decision,
        registry_snapshot=registry_snapshot,
    )
