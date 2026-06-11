"""Phase 190 unsupported-scope refusal quality validation."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.generic_chat_vague_prompt_contract import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    assistant_text_from_body,
    compact_response,
    fixture_state,
    fixture_state_changed,
    json_request,
    response_artifact_count,
    response_run_id,
    response_summary,
    write_json,
)
from vllm_agent_gateway.controller_service.server import (
    ControllerServiceConfig,
    handle_workflow_router_chat_completion,
)


SCHEMA_VERSION = 1
EXPECTED_REPORT_KIND = "unsupported_scope_refusal_quality_report"
EXPECTED_POLICY_KIND = "unsupported_scope_refusal_quality_policy"
EXPECTED_PHASE = 190
DEFAULT_POLICY_PATH = Path("runtime") / "unsupported_scope_refusal_quality_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "unsupported-scope-refusal-quality" / "phase190"


class Phase190Status(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class UnsupportedScopeRefusalQualityConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    target_roots: tuple[str, ...] = DEFAULT_TARGET_ROOTS
    timeout_seconds: int = 180
    run_live: bool = False
    include_anythingllm: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"unsupported-scope-refusal-quality-{utc_timestamp()}.json"


def resolve_path(config_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else config_root / path


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object at {path}")
    return value


def load_policy(config_root: Path, policy_path: Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    return read_json_object(resolve_path(config_root, policy_path))


def case_prompt(case: dict[str, Any], target_root: str | None = None) -> str:
    template = case.get("prompt_template")
    if isinstance(template, str):
        return template.format(target_root=target_root or "")
    prompt = case.get("prompt")
    if not isinstance(prompt, str):
        raise RuntimeError(f"case {case.get('case_id')} must include prompt or prompt_template")
    return prompt


def direct_messages_for_prompt(prompt: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": prompt}]


def expanded_cases(policy: dict[str, Any], target_roots: tuple[str, ...]) -> list[tuple[dict[str, Any], str | None]]:
    records: list[tuple[dict[str, Any], str | None]] = []
    for case in policy.get("cases", []):
        if not isinstance(case, dict):
            continue
        target_mode = case.get("target_root_mode")
        if target_mode == "each_required":
            for target_root in target_roots:
                records.append((case, target_root))
        elif target_mode == "first_required":
            if target_roots:
                records.append((case, target_roots[0]))
        else:
            records.append((case, None))
    return records


def forbidden_workflow_markers(workflows: list[str]) -> list[str]:
    markers: list[str] = []
    for workflow in workflows:
        markers.extend(
            [
                f"Selected workflow: {workflow}",
                f"selected_workflow: {workflow}",
                f"{workflow} completed",
            ]
        )
    return markers


def selected_workflow_display(summary: dict[str, Any], text: str) -> Any:
    selected = summary.get("selected_workflow")
    if selected is None and "Selected workflow: none" in text:
        return "none"
    return selected


def expected_items_missing(actual: Any, expected: Any) -> list[str]:
    if not isinstance(expected, list):
        return []
    actual_values = [str(item) for item in actual] if isinstance(actual, list) else []
    return [str(item) for item in expected if str(item) not in actual_values]


def summary_field_present(summary: dict[str, Any], field: str) -> bool:
    value = summary.get(field)
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(str(item).strip() for item in value)
    return value is not None


def split_recovery_values(value: str) -> list[str]:
    normalized = value.strip()
    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [item.strip().strip('"') for item in normalized.replace(",", ";").split(";") if item.strip().strip('"')]


def text_summary_fallback(text: str) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    in_summary = False
    in_recovery = False
    recovery_seen = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("- ") and ":" in line:
            label, raw_value = line[2:].split(":", 1)
            normalized_label = label.strip().lower().replace(" ", "_")
            value = raw_value.strip()
            if normalized_label in {"route_status", "selected_workflow", "next_action"} and value:
                summary.setdefault(normalized_label, value)
        if line == "Summary:":
            in_summary = True
            in_recovery = False
            continue
        if line == "Recovery:":
            recovery_seen = True
            in_recovery = True
            in_summary = False
            continue
        if line.endswith(":") and not line.startswith("- "):
            in_summary = False
            in_recovery = False
            continue
        if in_summary and line.startswith("- ") and ":" in line:
            key, value = line[2:].split(":", 1)
            normalized_key = key.strip()
            normalized_value = value.strip()
            if normalized_key:
                if normalized_key in {"blocker_reasons", "missing_information", "safe_alternatives", "evidence_expectations"}:
                    summary[normalized_key] = split_recovery_values(normalized_value)
                elif normalized_key not in summary:
                    summary[normalized_key] = normalized_value
            continue
        if in_recovery and line.startswith("- ") and ":" in line:
            key, value = line[2:].split(":", 1)
            normalized_key = key.strip().lower()
            normalized_value = value.strip()
            if normalized_key == "blocking reason":
                summary["blocker_reasons"] = split_recovery_values(normalized_value)
            elif normalized_key == "missing information":
                summary["missing_information"] = split_recovery_values(normalized_value)
            elif normalized_key == "bounded next step":
                summary["bounded_next_step"] = normalized_value
            elif normalized_key == "safe alternatives":
                summary["safe_alternatives"] = split_recovery_values(normalized_value)
            elif normalized_key == "evidence expected":
                summary["evidence_expectations"] = split_recovery_values(normalized_value)
            elif normalized_key == "mutation policy":
                summary["mutation_policy"] = normalized_value
    if recovery_seen:
        summary["refusal_quality_status"] = "actionable"
    if summary.get("selected_workflow") == "none":
        summary["selected_workflow"] = "none"
    return summary


def response_summary_with_text_fallback(body: dict[str, Any], text: str) -> dict[str, Any]:
    summary = dict(response_summary(body))
    fallback = text_summary_fallback(text)
    for key, value in fallback.items():
        if not summary_field_present(summary, key):
            summary[key] = value
    return summary


def classify_case_response(
    *,
    policy: dict[str, Any],
    case: dict[str, Any],
    surface: str,
    prompt: str,
    target_root: str | None,
    http_status: int,
    body: dict[str, Any],
) -> dict[str, Any]:
    text = assistant_text_from_body(body)
    summary = response_summary_with_text_fallback(body, text)
    selected_workflow = selected_workflow_display(summary, text)
    findings: list[dict[str, str]] = []
    if http_status != 200:
        findings.append({"severity": "blocker", "code": "http_not_ok", "message": f"HTTP status was {http_status}."})
    if not text.strip():
        findings.append({"severity": "blocker", "code": "missing_chat_text", "message": "Assistant text was empty."})
    if len(text) > 12000:
        findings.append({"severity": "blocker", "code": "unbounded_chat_text", "message": "Assistant text was too long."})
    expected_route_status = case.get("expected_route_status")
    if isinstance(expected_route_status, str):
        route_status = summary.get("route_status")
        if route_status is not None and route_status != expected_route_status:
            findings.append(
                {
                    "severity": "blocker",
                    "code": "wrong_route_status",
                    "message": f"Expected route_status {expected_route_status!r}, got {route_status!r}.",
                }
            )
        elif route_status is None and expected_route_status not in text:
            findings.append(
                {
                    "severity": "blocker",
                    "code": "missing_route_status",
                    "message": f"Missing route status marker {expected_route_status!r}.",
                }
            )
    expected_selected_workflow = case.get("expected_selected_workflow")
    if isinstance(expected_selected_workflow, str) and selected_workflow != expected_selected_workflow:
        findings.append(
            {
                "severity": "blocker",
                "code": "wrong_selected_workflow",
                "message": f"Expected selected_workflow {expected_selected_workflow!r}, got {selected_workflow!r}.",
            }
        )
    for marker in case.get("required_markers", []):
        if isinstance(marker, str) and marker not in text:
            findings.append(
                {
                    "severity": "blocker",
                    "code": "missing_required_marker",
                    "message": f"Missing required marker {marker!r}.",
                }
            )
    for marker in case.get("forbidden_markers", []):
        if isinstance(marker, str) and marker in text:
            findings.append(
                {
                    "severity": "blocker",
                    "code": "forbidden_marker_present",
                    "message": f"Forbidden marker appeared: {marker!r}.",
                }
            )
    expect_refusal_quality = case.get("expect_refusal_quality") is True
    if expect_refusal_quality:
        for marker in policy.get("required_recovery_markers", []):
            if isinstance(marker, str) and marker not in text:
                findings.append(
                    {
                        "severity": "blocker",
                        "code": "missing_recovery_marker",
                        "message": f"Missing recovery marker {marker!r}.",
                    }
                )
        for field in policy.get("required_summary_fields", []):
            if isinstance(field, str) and not summary_field_present(summary, field):
                findings.append(
                    {
                        "severity": "blocker",
                        "code": "missing_refusal_summary_field",
                        "message": f"Missing refusal-quality summary field {field!r}.",
                    }
                )
        if summary.get("refusal_quality_status") not in {None, "actionable"}:
            findings.append(
                {
                    "severity": "blocker",
                    "code": "wrong_refusal_quality_status",
                    "message": f"Unexpected refusal_quality_status {summary.get('refusal_quality_status')!r}.",
                }
            )
        missing_blockers = expected_items_missing(summary.get("blocker_reasons"), case.get("expected_blocker_reasons"))
        if missing_blockers:
            findings.append(
                {
                    "severity": "blocker",
                    "code": "missing_blocker_reason",
                    "message": f"Missing blocker reason(s): {missing_blockers}.",
                }
            )
        if any(phrase in text for phrase in ("I inspected ", "I ran ", "I verified ", "I changed ")):
            findings.append(
                {
                    "severity": "blocker",
                    "code": "overclaimed_blocked_work",
                    "message": "Blocked refusal text claimed inspection, test execution, verification, or mutation.",
                }
            )
    else:
        if "Recovery:" in text or summary.get("refusal_quality_status") == "actionable":
            findings.append(
                {
                    "severity": "blocker",
                    "code": "supported_prompt_was_refused",
                    "message": "Supported holdout received unsupported-scope recovery/refusal formatting.",
                }
            )
    forbidden = forbidden_workflow_markers(
        [str(item) for item in policy.get("forbidden_repository_workflows", []) if isinstance(item, str)]
    )
    if expect_refusal_quality:
        for marker in forbidden:
            if marker in text:
                findings.append(
                    {
                        "severity": "blocker",
                        "code": "repository_workflow_started",
                        "message": f"Forbidden workflow marker appeared: {marker}.",
                    }
                )
        compact = compact_response(body)
        artifacts = compact.get("artifacts") if isinstance(compact.get("artifacts"), dict) else {}
        if case.get("target_root_mode") == "none" and artifacts:
            findings.append(
                {
                    "severity": "blocker",
                    "code": "no_target_case_created_artifacts",
                    "message": "No-target refusal guidance must not create route or downstream artifacts.",
                }
            )
        if summary.get("source_changed") is True or summary.get("source_tree_changed") is True:
            findings.append(
                {
                    "severity": "blocker",
                    "code": "refusal_mutated_source",
                    "message": "Refusal/clarification response reported source mutation.",
                }
            )
    return {
        "case_id": case.get("case_id"),
        "prompt_class": case.get("prompt_class"),
        "surface": surface,
        "target_root": target_root,
        "prompt": prompt,
        "status": Phase190Status.PASSED.value if not findings else Phase190Status.FAILED.value,
        "http_status": http_status,
        "run_id": response_run_id(body),
        "route_status": summary.get("route_status"),
        "selected_workflow": selected_workflow,
        "blocker_reasons": summary.get("blocker_reasons") if isinstance(summary.get("blocker_reasons"), list) else [],
        "refusal_quality_status": summary.get("refusal_quality_status"),
        "artifact_count": response_artifact_count(body),
        "text_sample": text[:1800],
        "finding_count": len(findings),
        "findings": findings,
    }


def direct_case(
    *,
    config_root: Path,
    output_root: Path,
    allowed_target_roots: tuple[str, ...],
    policy: dict[str, Any],
    case: dict[str, Any],
    target_root: str | None,
) -> dict[str, Any]:
    prompt = case_prompt(case, target_root)
    service_config = ControllerServiceConfig(
        config_root=config_root,
        output_root=output_root,
        allowed_target_roots=tuple(Path(root) for root in allowed_target_roots),
        port=0,
    )
    body = handle_workflow_router_chat_completion(
        {"model": "agentic-workflow-router", "messages": direct_messages_for_prompt(prompt)},
        service_config,
    )
    return classify_case_response(
        policy=policy,
        case=case,
        surface="direct_controller",
        prompt=prompt,
        target_root=target_root,
        http_status=200,
        body=body,
    )


def gateway_case(
    *,
    config: UnsupportedScopeRefusalQualityConfig,
    policy: dict[str, Any],
    case: dict[str, Any],
    target_root: str | None,
) -> dict[str, Any]:
    prompt = case_prompt(case, target_root)
    status, body = json_request(
        f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={"model": "agentic-workflow-router", "messages": direct_messages_for_prompt(prompt)},
        timeout_seconds=config.timeout_seconds,
    )
    return classify_case_response(
        policy=policy,
        case=case,
        surface="workflow_router_gateway",
        prompt=prompt,
        target_root=target_root,
        http_status=status,
        body=body,
    )


def anythingllm_preflight(config: UnsupportedScopeRefusalQualityConfig, api_key: str) -> dict[str, Any]:
    base_url = config.anythingllm_api_base_url.rstrip("/")
    ping_status, ping_body = json_request(f"{base_url}/api/ping", timeout_seconds=min(30, config.timeout_seconds))
    workspace_status, workspace_body = json_request(
        f"{base_url}/api/v1/workspaces",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=min(30, config.timeout_seconds),
    )
    workspaces = workspace_body.get("workspaces") if isinstance(workspace_body, dict) else []
    slugs = [item.get("slug") for item in workspaces if isinstance(item, dict)]
    return {
        "status": "passed" if ping_status == 200 and workspace_status == 200 and config.workspace in slugs else "failed",
        "ping_status": ping_status,
        "workspace_status": workspace_status,
        "workspace": config.workspace,
        "workspace_found": config.workspace in slugs,
        "ping": ping_body,
    }


def anythingllm_case(
    *,
    config: UnsupportedScopeRefusalQualityConfig,
    policy: dict[str, Any],
    case: dict[str, Any],
    target_root: str | None,
    api_key: str,
) -> dict[str, Any]:
    prompt = case_prompt(case, target_root)
    session_id = f"phase190-{str(case.get('case_id')).lower()}-{uuid.uuid4().hex}"
    status, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={"message": prompt, "mode": "chat", "sessionId": session_id},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=config.timeout_seconds,
    )
    return classify_case_response(
        policy=policy,
        case=case,
        surface="anythingllm",
        prompt=prompt,
        target_root=target_root,
        http_status=status,
        body=body,
    )


def build_report(
    *,
    policy: dict[str, Any],
    cases: list[dict[str, Any]],
    fixture_before: dict[str, Any],
    fixture_after: dict[str, Any],
    anythingllm_preflight_result: dict[str, Any] | None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    current_errors = list(errors or [])
    failed_cases = [case for case in cases if case.get("status") != Phase190Status.PASSED.value]
    blocker_findings = [
        finding
        for case in cases
        for finding in case.get("findings", [])
        if isinstance(finding, dict) and finding.get("severity") == "blocker"
    ]
    changed = fixture_state_changed(fixture_before, fixture_after)
    if changed:
        current_errors.append("protected fixture state changed")
    if anythingllm_preflight_result and anythingllm_preflight_result.get("status") != "passed":
        current_errors.append("AnythingLLM preflight failed")
    surfaces = sorted({str(case.get("surface")) for case in cases if isinstance(case.get("surface"), str)})
    target_roots = sorted({str(case.get("target_root")) for case in cases if isinstance(case.get("target_root"), str)})
    refusal_cases = [case for case in cases if case.get("refusal_quality_status") == "actionable"]
    summary = {
        "case_count": len(cases),
        "passed_case_count": len(cases) - len(failed_cases),
        "failed_case_count": len(failed_cases),
        "blocker_finding_count": len(blocker_findings),
        "refusal_quality_case_count": len(refusal_cases),
        "surfaces": surfaces,
        "surface_count": len(surfaces),
        "target_roots": target_roots,
        "target_root_count": len(target_roots),
        "fixture_state_changed": changed,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "status": Phase190Status.PASSED.value
        if not failed_cases and not blocker_findings and not current_errors
        else Phase190Status.FAILED.value,
        "generated_at": utc_timestamp(),
        "policy_ref": {
            "kind": policy.get("kind"),
            "schema_version": policy.get("schema_version"),
            "phase": policy.get("phase"),
        },
        "blind_baseline": policy.get("blind_baseline") if isinstance(policy.get("blind_baseline"), dict) else {},
        "anythingllm_preflight": anythingllm_preflight_result or {},
        "summary": summary,
        "cases": cases,
        "fixture_state": {"before": fixture_before, "after": fixture_after, "changed": changed},
        "errors": current_errors,
    }


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 190")
    cases = policy.get("cases")
    if not isinstance(cases, list) or len(cases) < 7:
        errors.append("policy.cases must include at least seven cases")
    baseline = policy.get("blind_baseline")
    if not isinstance(baseline, dict) or baseline.get("source") != "contextless_blind_agent":
        errors.append("policy.blind_baseline must record contextless blind-agent source")
    for key in ("required_recovery_markers", "required_summary_fields", "required_surfaces"):
        if not isinstance(policy.get(key), list) or not policy[key]:
            errors.append(f"policy.{key} must be a non-empty list")
    return errors


def validate_unsupported_scope_refusal_quality_report(report: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors = validate_policy(policy)
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append("report.schema_version must be 1")
    if report.get("kind") != EXPECTED_REPORT_KIND:
        errors.append(f"report.kind must be {EXPECTED_REPORT_KIND}")
    if report.get("phase") != EXPECTED_PHASE:
        errors.append("report.phase must be 190")
    cases = [case for case in report.get("cases", []) if isinstance(case, dict)]
    fixture_state_record = report.get("fixture_state") if isinstance(report.get("fixture_state"), dict) else {}
    rebuilt = build_report(
        policy=policy,
        cases=cases,
        fixture_before=fixture_state_record.get("before") if isinstance(fixture_state_record.get("before"), dict) else {},
        fixture_after=fixture_state_record.get("after") if isinstance(fixture_state_record.get("after"), dict) else {},
        anythingllm_preflight_result=report.get("anythingllm_preflight")
        if isinstance(report.get("anythingllm_preflight"), dict)
        else {},
        errors=report.get("errors") if isinstance(report.get("errors"), list) else [],
    )
    for key in ("status", "summary"):
        if report.get(key) != rebuilt.get(key):
            errors.append(f"report.{key} must match rebuilt Phase 190 report")
    actual_surfaces = {case.get("surface") for case in cases}
    live_surface_present = bool(actual_surfaces & {"workflow_router_gateway", "anythingllm"}) or bool(
        report.get("anythingllm_preflight")
    )
    if live_surface_present:
        required_surfaces = set(policy.get("required_surfaces", []))
        missing_surfaces = sorted(str(surface) for surface in required_surfaces - actual_surfaces)
        if missing_surfaces:
            errors.append(f"report missing required surfaces: {missing_surfaces}")
    required_case_ids = {case.get("case_id") for case in policy.get("cases", []) if isinstance(case, dict)}
    actual_case_ids = {case.get("case_id") for case in cases}
    missing_cases = sorted(str(case_id) for case_id in required_case_ids - actual_case_ids)
    if missing_cases:
        errors.append(f"report missing required case ids: {missing_cases}")
    return errors


def run_unsupported_scope_refusal_quality(config: UnsupportedScopeRefusalQualityConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy = load_policy(config_root, config.policy_path)
    target_roots = tuple(config.target_roots)
    fixture_before = fixture_state(target_roots)
    cases: list[dict[str, Any]] = []
    errors = validate_policy(policy)
    direct_output = config_root / DEFAULT_OUTPUT_DIR / "direct-controller-artifacts"
    for case, target_root in expanded_cases(policy, target_roots):
        cases.append(
            direct_case(
                config_root=config_root,
                output_root=direct_output,
                allowed_target_roots=target_roots,
                policy=policy,
                case=case,
                target_root=target_root,
            )
        )
    preflight: dict[str, Any] = {}
    api_key = os.environ.get(config.api_key_env)
    if config.run_live:
        for case, target_root in expanded_cases(policy, target_roots):
            cases.append(gateway_case(config=config, policy=policy, case=case, target_root=target_root))
        if config.include_anythingllm:
            if not api_key:
                errors.append(f"{config.api_key_env} is required for live AnythingLLM validation")
            else:
                preflight = anythingllm_preflight(config, api_key)
                if preflight.get("status") == "passed":
                    for case, target_root in expanded_cases(policy, target_roots):
                        cases.append(
                            anythingllm_case(
                                config=config,
                                policy=policy,
                                case=case,
                                target_root=target_root,
                                api_key=api_key,
                            )
                        )
    fixture_after = fixture_state(target_roots)
    report = build_report(
        policy=policy,
        cases=cases,
        fixture_before=fixture_before,
        fixture_after=fixture_after,
        anythingllm_preflight_result=preflight,
        errors=errors,
    )
    validation_errors = validate_unsupported_scope_refusal_quality_report(report, policy)
    if validation_errors:
        report["status"] = Phase190Status.FAILED.value
        report["errors"] = list(report.get("errors") or []) + validation_errors
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
