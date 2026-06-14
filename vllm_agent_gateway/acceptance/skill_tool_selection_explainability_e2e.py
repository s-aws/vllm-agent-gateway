"""Skill/tool selection explainability E2E gate for Priority 0.

Phase 151 validates the user-visible selector explanation in normal chat. It
does not perform an independent selector pass; it compares the rendered chat
response with the route-decision and registry-snapshot artifacts produced by
the existing workflow-router path.
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
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    artifact_json,
    assert_fixture_state_unchanged,
    controller_run_record,
    fixture_state,
    json_request,
    prompt_for_case,
    selection_signature,
    text_response,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "skill_tool_selection_explainability_e2e_policy"
EXPECTED_REPORT_KIND = "skill_tool_selection_explainability_e2e_report"
EXPECTED_PHASE = 151
EXPECTED_BACKLOG_ID = "P0-BB-020"
DEFAULT_POLICY_PATH = Path("runtime") / "skill_tool_selection_explainability_e2e_policy.json"
DEFAULT_CASES_PATH = Path("runtime") / "skill_selection_hardening_cases.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "skill-tool-selection-explainability-e2e" / "phase151"


class ExplainabilityStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class SkillToolSelectionExplainabilityE2EConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    markdown_output_path: Path | None = None
    target_roots: tuple[str, ...] = DEFAULT_TARGET_ROOTS
    include_gateway: bool = True
    include_anythingllm: bool = True
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 900


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"skill-tool-selection-explainability-e2e-{utc_timestamp()}.json"


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


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def marker_present(text: str, marker: str) -> bool:
    return marker.lower() in text.lower()


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 151")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    version = policy.get("policy_version")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        errors.append("policy.policy_version must use semantic version x.y.z")
    purpose = str(policy.get("purpose") or "").lower()
    for required_phrase in ("existing workflow-router path", "without manual skill injection"):
        if required_phrase not in purpose:
            errors.append(f"policy.purpose must mention {required_phrase!r}")
    if policy.get("source_case_catalog_path") != str(DEFAULT_CASES_PATH).replace("\\", "/"):
        errors.append("policy.source_case_catalog_path must point to runtime/skill_selection_hardening_cases.json")
    if len(string_list(policy.get("case_ids"))) < 3:
        errors.append("policy.case_ids must include at least three ready selector cases")
    if set(string_list(policy.get("required_surfaces"))) != {"gateway", "anythingllm"}:
        errors.append("policy.required_surfaces must be gateway and anythingllm")
    required_targets = set(string_list(policy.get("required_target_roots")))
    if required_targets != set(DEFAULT_TARGET_ROOTS):
        errors.append("policy.required_target_roots must match both frozen Coinbase fixtures")
    for key in (
        "required_chat_sections",
        "required_result_markers",
        "required_selection_markers",
        "required_grounding_markers",
        "forbidden_raw_internal_markers",
        "artifact_requirements",
    ):
        if not string_list(policy.get(key)):
            errors.append(f"policy.{key} must be a non-empty string list")
    if int_value(policy.get("minimum_rejected_candidate_count"), -1) < 1:
        errors.append("policy.minimum_rejected_candidate_count must be at least 1")
    selection_policy = dict_value(policy.get("required_selection_policy"))
    expected_policy = {
        "metadata_only": True,
        "manual_skill_injection_required": False,
        "low_confidence_fails_closed": True,
        "minimum_confidence": "medium",
    }
    for key, expected in expected_policy.items():
        if selection_policy.get(key) != expected:
            errors.append(f"policy.required_selection_policy.{key} must be {expected!r}")
    if policy.get("non_mutation_required") is not True:
        errors.append("policy.non_mutation_required must be true")
    return errors


def load_cases(config_root: Path, policy: dict[str, Any]) -> list[dict[str, Any]]:
    cases_path = resolve_path(config_root, policy.get("source_case_catalog_path", DEFAULT_CASES_PATH))
    catalog = read_json_object(cases_path)
    if catalog.get("kind") != "skill_selection_hardening_cases":
        raise RuntimeError("source case catalog kind must be skill_selection_hardening_cases")
    by_id = {
        str(item.get("case_id")): item
        for item in object_list(catalog.get("cases"))
        if isinstance(item.get("case_id"), str)
    }
    selected: list[dict[str, Any]] = []
    missing: list[str] = []
    not_ready: list[str] = []
    for case_id in string_list(policy.get("case_ids")):
        case = by_id.get(case_id)
        if case is None:
            missing.append(case_id)
            continue
        if case.get("expected_route_status") != "ready":
            not_ready.append(case_id)
            continue
        selected.append(case)
    if missing:
        raise RuntimeError(f"policy case_ids missing from source catalog: {missing}")
    if not_ready:
        raise RuntimeError(f"policy case_ids must refer only to ready cases: {not_ready}")
    return selected


def selected_policy_from_route(route_decision: dict[str, Any]) -> dict[str, Any]:
    audit = dict_value(route_decision.get("selection_audit"))
    return dict_value(audit.get("selection_policy"))


def selection_has_registry_grounding(route_decision: dict[str, Any], registry_snapshot: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    evidence = object_list(route_decision.get("evidence"))
    sources = {str(item.get("source")) for item in evidence if isinstance(item.get("source"), str)}
    if "workflow_registry" not in sources:
        errors.append("route_decision.evidence missing workflow_registry source")
    if "skill_registry" not in sources:
        errors.append("route_decision.evidence missing skill_registry source")
    if not dict_value(registry_snapshot.get("skills")):
        errors.append("registry_snapshot.skills missing or empty")
    if not dict_value(registry_snapshot.get("tools")):
        errors.append("registry_snapshot.tools missing or empty")
    registry_skills = dict_value(registry_snapshot.get("skills"))
    registry_tools = dict_value(registry_snapshot.get("tools"))
    for skill_id in string_list(route_decision.get("selected_skills")):
        if skill_id not in registry_skills:
            errors.append(f"registry_snapshot.skills missing selected skill {skill_id}")
    for tool_id in string_list(route_decision.get("selected_tools")):
        if tool_id not in registry_tools:
            errors.append(f"registry_snapshot.tools missing selected tool {tool_id}")
    return errors


def validate_text_against_route(
    *,
    policy: dict[str, Any],
    case: dict[str, Any],
    target_root: str,
    surface: str,
    text: str,
    route_decision: dict[str, Any],
    registry_snapshot: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    expected_workflow = str(case.get("expected_selected_workflow"))
    expected_skills = string_list(case.get("expected_selected_skills"))
    expected_tools = string_list(case.get("expected_selected_tools"))
    expected_rules = string_list(case.get("expected_route_rules"))
    label = f"{surface}.{case.get('case_id')}.{Path(target_root).name}"

    for marker in string_list(policy.get("required_chat_sections")):
        if not marker_present(text, marker):
            errors.append(f"{label}.text missing section marker {marker}")
    for marker in string_list(policy.get("required_result_markers")):
        if not marker_present(text, marker):
            errors.append(f"{label}.text missing result marker {marker}")
    for marker in string_list(policy.get("required_selection_markers")):
        if not marker_present(text, marker):
            errors.append(f"{label}.text missing selection marker {marker}")
    for marker in string_list(policy.get("required_grounding_markers")):
        if marker not in text:
            errors.append(f"{label}.text missing grounding marker {marker}")
    for marker in string_list(policy.get("forbidden_raw_internal_markers")):
        if marker in text:
            errors.append(f"{label}.text exposed raw internal marker {marker}")

    if f"- Selected workflow: {expected_workflow}" not in text:
        errors.append(f"{label}.text missing expected selected workflow {expected_workflow}")
    for skill_id in expected_skills:
        if skill_id not in text:
            errors.append(f"{label}.text missing expected selected skill {skill_id}")
    for tool_id in expected_tools:
        if tool_id not in text:
            errors.append(f"{label}.text missing expected selected tool {tool_id}")
    for rule in expected_rules:
        if rule not in text:
            errors.append(f"{label}.text missing expected route rule {rule}")

    signature = selection_signature(route_decision)
    if signature["selected_workflow"] != expected_workflow:
        errors.append(f"{label}.route selected_workflow mismatch: {signature['selected_workflow']!r}")
    for skill_id in expected_skills:
        if skill_id not in signature["selected_skills"]:
            errors.append(f"{label}.route missing expected selected skill {skill_id}")
    for tool_id in expected_tools:
        if tool_id not in signature["selected_tools"]:
            errors.append(f"{label}.route missing expected selected tool {tool_id}")
    for rule in expected_rules:
        if rule not in signature["route_rules"]:
            errors.append(f"{label}.route missing expected route rule {rule}")

    minimum_rejected = int_value(policy.get("minimum_rejected_candidate_count"), 1)
    rejected_fragments = {
        "workflow_rejected_count": f"workflows {signature['workflow_rejected_count']}",
        "skill_rejected_count": f"skills {signature['skill_rejected_count']}",
        "tool_rejected_count": f"tools {signature['tool_rejected_count']}",
    }
    for count_key, fragment in rejected_fragments.items():
        if signature[count_key] < minimum_rejected:
            errors.append(f"{label}.route {count_key} below minimum {minimum_rejected}")
        if fragment not in text:
            errors.append(f"{label}.text missing rejected candidate fragment {fragment}")

    required_selection_policy = dict_value(policy.get("required_selection_policy"))
    actual_selection_policy = selected_policy_from_route(route_decision)
    for key, expected in required_selection_policy.items():
        if actual_selection_policy.get(key) != expected:
            errors.append(
                f"{label}.route selection_policy.{key} expected {expected!r} got {actual_selection_policy.get(key)!r}"
            )
    if "manual skill injection" in text.lower() and "manual skill injection required" in text.lower():
        errors.append(f"{label}.text implies manual skill injection is required")
    errors.extend(f"{label}.{item}" for item in selection_has_registry_grounding(route_decision, registry_snapshot))
    return errors


def response_result(
    *,
    policy: dict[str, Any],
    case: dict[str, Any],
    target_root: str,
    surface: str,
    text: str,
    run_id: str,
    route_decision: dict[str, Any],
    registry_snapshot: dict[str, Any],
) -> dict[str, Any]:
    errors = validate_text_against_route(
        policy=policy,
        case=case,
        target_root=target_root,
        surface=surface,
        text=text,
        route_decision=route_decision,
        registry_snapshot=registry_snapshot,
    )
    signature = selection_signature(route_decision)
    return {
        "case_id": case.get("case_id"),
        "surface": surface,
        "target_root": target_root,
        "status": ExplainabilityStatus.PASSED.value if not errors else ExplainabilityStatus.FAILED.value,
        "run_id": run_id,
        "selected_workflow": signature["selected_workflow"],
        "selected_skills": signature["selected_skills"],
        "selected_tools": signature["selected_tools"],
        "route_rules": signature["route_rules"],
        "rejected_candidate_counts": {
            "workflows": signature["workflow_rejected_count"],
            "skills": signature["skill_rejected_count"],
            "tools": signature["tool_rejected_count"],
        },
        "grounding_markers": [marker for marker in string_list(policy.get("required_grounding_markers")) if marker in text],
        "assistant_text_sha256": sha256_text(text),
        "assistant_text_excerpt": text[:3000],
        "errors": errors,
    }


def gateway_response(
    config: SkillToolSelectionExplainabilityE2EConfig,
    *,
    policy: dict[str, Any],
    case: dict[str, Any],
    target_root: str,
) -> dict[str, Any]:
    before = fixture_state(target_root)
    status, body = json_request(
        f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": prompt_for_case(case, target_root)}],
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
        surface="gateway",
        text=text,
        run_id=run_id,
        route_decision=route_decision,
        registry_snapshot=registry_snapshot,
    )


def run_id_from_text(text: str) -> str:
    match = re.search(r"\brun_id:\s*(workflow-router-[A-Za-z0-9]+)", text)
    if not match:
        return "unknown"
    return match.group(1)


def anythingllm_response(
    config: SkillToolSelectionExplainabilityE2EConfig,
    *,
    policy: dict[str, Any],
    case: dict[str, Any],
    target_root: str,
    api_key: str,
) -> dict[str, Any]:
    before = fixture_state(target_root)
    status, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={
            "message": prompt_for_case(case, target_root),
            "mode": "chat",
            "sessionId": f"phase151-explainability-{case.get('case_id', 'case').lower()}-{uuid.uuid4().hex}",
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
        surface="anythingllm",
        text=text,
        run_id=run_id,
        route_decision=route_decision,
        registry_snapshot=registry_snapshot,
    )


def skipped_response(case: dict[str, Any], target_root: str, surface: str, reason: str) -> dict[str, Any]:
    return {
        "case_id": case.get("case_id"),
        "surface": surface,
        "target_root": target_root,
        "status": ExplainabilityStatus.SKIPPED.value,
        "run_id": "not_run",
        "errors": [reason],
    }


def build_summary(results: list[dict[str, Any]], policy_errors: list[str]) -> dict[str, Any]:
    failed = [item for item in results if item.get("status") == ExplainabilityStatus.FAILED.value]
    skipped = [item for item in results if item.get("status") == ExplainabilityStatus.SKIPPED.value]
    passed = [item for item in results if item.get("status") == ExplainabilityStatus.PASSED.value]
    surfaces = sorted({str(item.get("surface")) for item in results if isinstance(item.get("surface"), str)})
    case_ids = sorted({str(item.get("case_id")) for item in results if isinstance(item.get("case_id"), str)})
    target_roots = sorted({str(item.get("target_root")) for item in results if isinstance(item.get("target_root"), str)})
    return {
        "case_count": len(case_ids),
        "target_root_count": len(target_roots),
        "surface_count": len(surfaces),
        "response_count": len(results),
        "passed_response_count": len(passed),
        "failed_response_count": len(failed),
        "skipped_response_count": len(skipped),
        "policy_error_count": len(policy_errors),
        "surfaces": surfaces,
        "case_ids": case_ids,
        "target_roots": target_roots,
        "required_surfaces": ["anythingllm", "gateway"],
        "required_target_roots": list(DEFAULT_TARGET_ROOTS),
    }


def validate_report(report: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append("report.schema_version must be 1")
    if report.get("kind") != EXPECTED_REPORT_KIND:
        errors.append(f"report.kind must be {EXPECTED_REPORT_KIND}")
    if report.get("phase") != EXPECTED_PHASE:
        errors.append("report.phase must be 151")
    if report.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"report.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    results = object_list(report.get("results"))
    if not results:
        errors.append("report.results must contain at least one response result")
    summary = dict_value(report.get("summary"))
    expected_summary = build_summary(results, string_list(report.get("policy_errors")))
    for key, expected in expected_summary.items():
        if summary.get(key) != expected:
            errors.append(f"report.summary.{key} mismatch")
    failed = [item for item in results if item.get("status") != ExplainabilityStatus.PASSED.value]
    if report.get("status") == ExplainabilityStatus.PASSED.value and failed:
        errors.append("passed report cannot contain failed or skipped results")
    required_surfaces = set(string_list(policy.get("required_surfaces")))
    required_targets = set(string_list(policy.get("required_target_roots")))
    required_case_ids = set(string_list(policy.get("case_ids")))
    actual_surfaces = set(summary.get("surfaces") if isinstance(summary.get("surfaces"), list) else [])
    actual_targets = set(summary.get("target_roots") if isinstance(summary.get("target_roots"), list) else [])
    actual_case_ids = set(summary.get("case_ids") if isinstance(summary.get("case_ids"), list) else [])
    if report.get("status") == ExplainabilityStatus.PASSED.value:
        if actual_surfaces != required_surfaces:
            errors.append("passed report must cover all required surfaces")
        if actual_targets != required_targets:
            errors.append("passed report must cover all required target roots")
        if actual_case_ids != required_case_ids:
            errors.append("passed report must cover all policy case_ids")
    return errors


def markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Skill/Tool Selection Explainability E2E",
        "",
        f"Status: {report.get('status')}",
        f"Phase: {report.get('phase')}",
        f"Created: {report.get('created_at')}",
        "",
        "## Summary",
        "",
        f"- Cases: {summary.get('case_count')}",
        f"- Responses: {summary.get('passed_response_count')} passed / {summary.get('response_count')} total",
        f"- Surfaces: {', '.join(string_list(summary.get('surfaces')))}",
        f"- Targets: {', '.join(string_list(summary.get('target_roots')))}",
        f"- Policy errors: {summary.get('policy_error_count')}",
        "",
        "## Results",
        "",
        "| Case | Surface | Target | Status | Run ID | Rejected Candidates |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in object_list(report.get("results")):
        rejected = dict_value(item.get("rejected_candidate_counts"))
        rejected_text = (
            f"workflows {rejected.get('workflows', 'n/a')}; "
            f"skills {rejected.get('skills', 'n/a')}; "
            f"tools {rejected.get('tools', 'n/a')}"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("case_id")),
                    str(item.get("surface")),
                    Path(str(item.get("target_root"))).name,
                    str(item.get("status")),
                    str(item.get("run_id")),
                    rejected_text,
                ]
            )
            + " |"
        )
    if report.get("errors"):
        lines.extend(["", "## Errors", ""])
        for error in string_list(report.get("errors")):
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"


def run_skill_tool_selection_explainability_e2e(
    config: SkillToolSelectionExplainabilityE2EConfig,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root)
    policy_path = resolve_path(config_root, config.policy_path)
    policy_errors: list[str] = []
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    policy: dict[str, Any] = {}
    cases: list[dict[str, Any]] = []

    try:
        policy = read_json_object(policy_path)
        policy_errors = validate_policy(policy)
        if not policy_errors:
            cases = load_cases(config_root, policy)
    except Exception as exc:  # noqa: BLE001 - acceptance gate reports all failures
        policy_errors.append(f"policy load failed: {type(exc).__name__}: {exc}")

    if policy_errors:
        errors.extend(policy_errors)
    else:
        if not config.include_gateway and "gateway" in string_list(policy.get("required_surfaces")):
            errors.append("gateway validation is required by policy")
        if not config.include_anythingllm and "anythingllm" in string_list(policy.get("required_surfaces")):
            errors.append("AnythingLLM validation is required by policy")
        for target_root in config.target_roots:
            for case in cases:
                if config.include_gateway:
                    try:
                        results.append(gateway_response(config, policy=policy, case=case, target_root=target_root))
                    except Exception as exc:  # noqa: BLE001
                        results.append(
                            {
                                "case_id": case.get("case_id"),
                                "surface": "gateway",
                                "target_root": target_root,
                                "status": ExplainabilityStatus.FAILED.value,
                                "run_id": "unknown",
                                "errors": [f"gateway request failed: {type(exc).__name__}: {exc}"],
                            }
                        )
                else:
                    results.append(skipped_response(case, target_root, "gateway", "gateway validation disabled"))
        if config.include_anythingllm:
            api_key = os.environ.get(config.api_key_env)
            if not api_key:
                errors.append(f"{config.api_key_env} is required for AnythingLLM validation")
            else:
                for target_root in config.target_roots:
                    for case in cases:
                        try:
                            results.append(
                                anythingllm_response(
                                    config,
                                    policy=policy,
                                    case=case,
                                    target_root=target_root,
                                    api_key=api_key,
                                )
                            )
                        except Exception as exc:  # noqa: BLE001
                            results.append(
                                {
                                    "case_id": case.get("case_id"),
                                    "surface": "anythingllm",
                                    "target_root": target_root,
                                    "status": ExplainabilityStatus.FAILED.value,
                                    "run_id": "unknown",
                                    "errors": [f"AnythingLLM request failed: {type(exc).__name__}: {exc}"],
                                }
                            )
        else:
            for target_root in config.target_roots:
                for case in cases:
                    results.append(skipped_response(case, target_root, "anythingllm", "AnythingLLM validation disabled"))

    errors.extend(
        error
        for item in results
        for error in string_list(item.get("errors"))
        if item.get("status") != ExplainabilityStatus.PASSED.value
    )
    summary = build_summary(results, policy_errors)
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": ExplainabilityStatus.PASSED.value if not errors and results else ExplainabilityStatus.FAILED.value,
        "created_at": utc_timestamp(),
        "config_root": str(config_root),
        "policy_path": str(policy_path),
        "policy_sha256": hashlib.sha256(policy_path.read_bytes()).hexdigest() if policy_path.is_file() else None,
        "policy_errors": policy_errors,
        "summary": summary,
        "results": results,
        "errors": errors,
    }
    validation_errors = validate_report(report, policy or {})
    if validation_errors:
        report["status"] = ExplainabilityStatus.FAILED.value
        report["errors"] = errors + validation_errors
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    if config.markdown_output_path:
        write_text(config.markdown_output_path, markdown_report(report))
        report["markdown_report_path"] = str(config.markdown_output_path.resolve())
        write_json(output_path, report)
    return report
