"""EIG-2 approval replay breadth validation."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.connector_user_scope_audit import validate_connector_invocation_audit_report
from vllm_agent_gateway.acceptance.eig1_connector_breadth import (
    actor_context,
    clean_runtime_root,
    copy_runtime_root,
    install_runtime_connectors,
    object_list,
    read_json_object,
    string_list,
    validation_error,
)
from vllm_agent_gateway.acceptance.eig2_actor_scope_breadth import (
    connector_entries_from_fixture_pack,
    resolve_path,
    scoped_connector_entries,
)
from vllm_agent_gateway.connectors.catalog import write_json
from vllm_agent_gateway.controllers.connector_catalog.invoke import ConnectorInvocationRequest, invoke_connector_invocation


SCHEMA_VERSION = 1
DEFAULT_POLICY_PATH = Path("runtime") / "eig2_approval_replay_breadth_policy.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "eig2-approval-replay-breadth"


class EIG2ApprovalReplayScenario(str, Enum):
    APPROVED_DRY_RUN_SUCCESS = "approved_dry_run_success"
    WRONG_ACTOR = "wrong_actor"
    WRONG_SESSION = "wrong_session"
    WRONG_REQUEST = "wrong_request"
    WRONG_CONNECTOR = "wrong_connector"
    WRONG_OPERATION = "wrong_operation"
    STALE_APPROVAL_SCOPE_STATE = "stale_approval_scope_state"
    SCOPE_CHANGE = "scope_change"
    NON_DRY_RUN_WRITE = "non_dry_run_write"


REQUIRED_APPROVAL_SCENARIOS = {item.value for item in EIG2ApprovalReplayScenario}


@dataclass(frozen=True)
class EIG2ApprovalReplayBreadthConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"eig2-approval-replay-breadth-{utc_timestamp()}.json"


def positive_case_by_id(fixture_pack: dict[str, Any], case_id: str) -> dict[str, Any]:
    for case in object_list(fixture_pack.get("positive_invocation_cases")):
        if case.get("id") == case_id:
            return case
    raise RuntimeError(f"Missing EIG-1 positive invocation case: {case_id}")


def validate_policy_shape(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != "eig2_approval_replay_breadth_policy":
        errors.append(validation_error("policy.kind", "kind must be eig2_approval_replay_breadth_policy"))
    boundary = policy.get("scope_boundary")
    if not isinstance(boundary, dict):
        errors.append(validation_error("policy.scope_boundary", "scope_boundary must be an object"))
    else:
        if boundary.get("execution") != "local_stub_only":
            errors.append(validation_error("policy.scope_boundary.execution", "execution must be local_stub_only"))
        for key in (
            "real_oauth_provider_allowed",
            "external_network_allowed",
            "raw_mcp_allowed",
            "direct_model_tool_access_allowed",
            "runtime_registry_mutation_allowed",
            "target_repository_mutation_allowed",
            "external_audit_sink_allowed",
        ):
            if boundary.get(key) is not False:
                errors.append(validation_error(f"policy.scope_boundary.{key}", f"{key} must be false"))
    scenarios = {case.get("scenario") for case in object_list(policy.get("approval_replay_cases")) if isinstance(case.get("scenario"), str)}
    missing_scenarios = sorted(REQUIRED_APPROVAL_SCENARIOS - scenarios)
    if missing_scenarios:
        errors.append(validation_error("policy.approval_replay_cases.scenarios", f"missing approval replay scenarios: {', '.join(missing_scenarios)}"))
    if not object_list(policy.get("deferred_items")):
        errors.append(validation_error("policy.deferred_items", "at least one deferred item is required"))
    return errors


def base_actor_context(case: dict[str, Any]) -> dict[str, Any]:
    return actor_context(
        scopes=string_list(case.get("actor_granted_scopes")),
        actor_id="eig2-approval-actor",
        request_id=str(case.get("id") or "eig2-approval-case"),
    )


def approval_for_replay_case(
    *,
    case: dict[str, Any],
    source_case: dict[str, Any],
    raw_actor_context: dict[str, Any],
) -> dict[str, Any]:
    approval = {
        "status": "approved_for_connector_invocation",
        "scope": "connector_invocation",
        "connector_id": source_case["connector_id"],
        "operation_id": source_case["operation_id"],
        "actor_id": raw_actor_context["actor_id"],
        "session_id": raw_actor_context["session_id"],
        "request_id": raw_actor_context["request_id"],
        "granted_scopes": sorted(set(string_list(raw_actor_context.get("granted_scopes")))),
        "approval_refs": [f"{case['id']}-approval"],
    }
    mutation = case.get("approval_mutation")
    if mutation == "wrong_actor":
        approval["actor_id"] = "eig2-other-actor"
    elif mutation == "wrong_session":
        approval["session_id"] = "eig2-other-session"
    elif mutation == "wrong_request":
        approval["request_id"] = "eig2-other-request"
    elif mutation == "wrong_connector":
        approval["connector_id"] = "business_record_stub"
    elif mutation == "wrong_operation":
        approval["operation_id"] = "lookup_work_item"
    elif mutation == "missing_scope_state":
        approval.pop("granted_scopes", None)
    elif mutation == "scope_change":
        approval["granted_scopes"] = string_list(case.get("approval_granted_scopes"))
    return approval


def invoke_replay_case(
    *,
    runtime_root: Path,
    output_root: Path,
    fixture_pack: dict[str, Any],
    case: dict[str, Any],
) -> dict[str, Any]:
    source_case_id = case.get("source_case_id")
    if not isinstance(source_case_id, str) or not source_case_id.strip():
        raise RuntimeError(f"case {case.get('id')} missing source_case_id")
    source_case = positive_case_by_id(fixture_pack, source_case_id)
    raw_actor_context = base_actor_context(case)
    approval = approval_for_replay_case(case=case, source_case=source_case, raw_actor_context=raw_actor_context)
    request = ConnectorInvocationRequest(
        config_root=runtime_root,
        output_root=output_root,
        connector_id=source_case["connector_id"],
        operation_id=source_case["operation_id"],
        arguments=source_case["arguments"],
        dry_run=case.get("dry_run") is True,
        actor_context=raw_actor_context,
        approval=approval,
    )
    return invoke_connector_invocation(request).report or {}


def compact_audit(audit: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision": audit.get("decision"),
        "denial_code": audit.get("denial_code"),
        "actor_id": audit.get("actor_id"),
        "session_id": audit.get("session_id"),
        "request_id": audit.get("request_id"),
        "connector_id": audit.get("connector_id"),
        "operation_id": audit.get("operation_id"),
        "required_scopes": audit.get("required_scopes", []),
        "granted_scopes": audit.get("granted_scopes", []),
        "missing_scopes": audit.get("missing_scopes", []),
        "authorization_status": audit.get("authorization_status"),
        "approval_state": audit.get("approval_state"),
        "argument_keys": audit.get("input", {}).get("argument_keys", []),
        "raw_auth_subject_stored": audit.get("raw_auth_subject_stored"),
        "raw_arguments_stored": audit.get("raw_arguments_stored"),
        "input_raw_arguments_stored": audit.get("input", {}).get("raw_arguments_stored"),
    }


def validate_replay_cases(
    *,
    config_root: Path,
    fixture_pack: dict[str, Any],
    entries: list[dict[str, Any]],
    cases: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    runtime_root = copy_runtime_root(config_root)
    reports: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    try:
        install_runtime_connectors(runtime_root, entries, enabled=True)
        for case in cases:
            case_id = str(case.get("id") or "unknown")
            expected_status = case.get("expected_report_status")
            expected_error = case.get("expected_error_code")
            case_errors: list[dict[str, str]] = []
            report = invoke_replay_case(
                runtime_root=runtime_root,
                output_root=runtime_root / "runtime-state" / "eig2-approval-replay-case-output",
                fixture_pack=fixture_pack,
                case=case,
            )
            status = report.get("status")
            failures = report.get("errors") if isinstance(report.get("errors"), list) else []
            actual_error = failures[0].get("code") if failures and isinstance(failures[0], dict) else None
            audit = report.get("audit") if isinstance(report.get("audit"), dict) else {}
            audit_validation = validate_connector_invocation_audit_report(report)
            if status != expected_status:
                case_errors.append(validation_error("case.expected_report_status", f"expected {expected_status}, got {status}", item_id=case_id))
            if expected_error and actual_error != expected_error:
                case_errors.append(validation_error("case.expected_error_code", f"expected {expected_error}, got {actual_error}", item_id=case_id))
            if audit_validation.get("status") != "passed":
                case_errors.append(
                    validation_error(
                        "case.audit_validation",
                        "; ".join(str(item) for item in audit_validation.get("errors", [])),
                        item_id=case_id,
                    )
                )
            if audit.get("raw_auth_subject_stored") is not False or audit.get("raw_arguments_stored") is not False:
                case_errors.append(validation_error("case.audit.raw_storage", "audit must not store raw auth subject or raw arguments", item_id=case_id))
            if audit.get("input", {}).get("raw_arguments_stored") is not False:
                case_errors.append(validation_error("case.audit.input.raw_arguments", "audit input must not store raw arguments", item_id=case_id))
            reports.append(
                {
                    "case_id": case_id,
                    "scenario": case.get("scenario"),
                    "status": "failed" if case_errors else "passed",
                    "expected_report_status": expected_status,
                    "actual_report_status": status,
                    "expected_error_code": expected_error,
                    "actual_error_code": actual_error,
                    "audit_validation_status": audit_validation.get("status"),
                    "audit": compact_audit(audit),
                    "artifact_keys": sorted(report.get("artifacts", {})) if isinstance(report.get("artifacts"), dict) else [],
                }
            )
            errors.extend(case_errors)
    finally:
        clean_runtime_root(runtime_root)
    return reports, errors


def report_contains_raw_values(report: dict[str, Any]) -> bool:
    serialized = json.dumps(report, ensure_ascii=True, sort_keys=True)
    raw_values = [
        "WORK-SYN-1042",
        "Synthetic dry-run update.",
        "local-subject:eig2-approval-actor",
    ]
    return any(value in serialized for value in raw_values)


def run_eig2_approval_replay_breadth_validation(config: EIG2ApprovalReplayBreadthConfig) -> dict[str, Any]:
    config_root = config.config_root
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path) if config.output_path else default_report_path(config_root)
    policy = read_json_object(policy_path)
    policy_errors = validate_policy_shape(policy)

    actor_scope_policy_path = resolve_path(config_root, str(policy.get("actor_scope_policy") or ""))
    actor_scope_policy = read_json_object(actor_scope_policy_path)
    fixture_pack_path = resolve_path(config_root, str(actor_scope_policy.get("fixture_pack") or ""))
    fixture_pack = read_json_object(fixture_pack_path)
    entries = scoped_connector_entries(
        connector_entries_from_fixture_pack(fixture_pack),
        object_list(actor_scope_policy.get("operation_scope_assignments")),
    )
    replay_reports, replay_errors = validate_replay_cases(
        config_root=config_root,
        fixture_pack=fixture_pack,
        entries=entries,
        cases=object_list(policy.get("approval_replay_cases")),
    )
    validation_errors = policy_errors + replay_errors
    status = "failed" if validation_errors else "passed"
    passed_scenarios = {report.get("scenario") for report in replay_reports if report.get("status") == "passed" and isinstance(report.get("scenario"), str)}
    report: dict[str, Any] = {
        "kind": "eig2_approval_replay_breadth_report",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "policy_path": str(policy_path),
        "actor_scope_policy_path": str(actor_scope_policy_path),
        "fixture_pack": str(fixture_pack_path),
        "summary": {
            "approval_replay_case_count": len(replay_reports),
            "passed_scenarios": sorted(str(item) for item in passed_scenarios),
            "all_required_scenarios_passed": REQUIRED_APPROVAL_SCENARIOS <= passed_scenarios,
            "audit_validation_passed": all(report.get("audit_validation_status") == "passed" for report in replay_reports),
            "wrong_actor_denied": "wrong_actor" in passed_scenarios,
            "wrong_session_denied": "wrong_session" in passed_scenarios,
            "wrong_request_denied": "wrong_request" in passed_scenarios,
            "wrong_connector_denied": "wrong_connector" in passed_scenarios,
            "wrong_operation_denied": "wrong_operation" in passed_scenarios,
            "scope_change_denied": "scope_change" in passed_scenarios,
            "non_dry_run_write_denied": "non_dry_run_write" in passed_scenarios,
            "runtime_registry_changed": False,
            "target_repository_changed": False,
            "external_network_called": False,
            "external_audit_sink_used": False,
            "raw_mcp_used": False,
            "direct_model_tool_access_used": False,
            "validation_error_count": len(validation_errors),
            "phase295_ready": status == "passed",
        },
        "approval_replay_reports": replay_reports,
        "validation_errors": validation_errors,
        "created_at": utc_timestamp(),
    }
    report["summary"]["raw_values_retained_in_report"] = report_contains_raw_values(report)
    if report["summary"]["raw_values_retained_in_report"]:
        report["status"] = "failed"
        report["summary"]["phase295_ready"] = False
        report["validation_errors"].append(validation_error("report.raw_values", "report must not retain raw fixture values"))
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
