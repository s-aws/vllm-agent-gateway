"""EIG-2 actor and scope breadth validation."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.eig1_connector_breadth import (
    actor_context,
    approval_for_case,
    clean_runtime_root,
    copy_runtime_root,
    install_runtime_connectors,
    object_list,
    read_json_object,
    string_list,
    validation_error,
)
from vllm_agent_gateway.connectors.catalog import ConnectorCatalogError, validate_connector_admission_manifest, write_json
from vllm_agent_gateway.connectors.identity import ConnectorIdentityError, validate_actor_context
from vllm_agent_gateway.connectors.mediator import ConnectorMediationError, mediate_connector_operation


SCHEMA_VERSION = 1
DEFAULT_POLICY_PATH = Path("runtime") / "eig2_actor_scope_breadth_policy.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "eig2-actor-scope-breadth"


class EIG2ActorScopeScenario(str, Enum):
    READ_SUCCESS = "read_success"
    MISSING_READ_SCOPE = "missing_read_scope"
    WRITE_DRY_RUN_SUCCESS = "write_dry_run_success"
    MISSING_WRITE_SCOPE = "missing_write_scope"
    BUSINESS_READ_SUCCESS = "business_read_success"
    BUSINESS_MISSING_READ_SCOPE = "business_missing_read_scope"
    CROSS_CONNECTOR_SCOPE_DENIAL = "cross_connector_scope_denial"


class EIG2ActorContextScenario(str, Enum):
    MALFORMED_ACTOR_CONTEXT = "malformed_actor_context"
    EXPIRED_ACTOR_CONTEXT = "expired_actor_context"
    ANONYMOUS_ACTOR_CONTEXT = "anonymous_actor_context"
    MISSING_ACTOR_CONTEXT = "missing_actor_context"


REQUIRED_ACTOR_SCOPE_SCENARIOS = {item.value for item in EIG2ActorScopeScenario}
REQUIRED_ACTOR_CONTEXT_SCENARIOS = {item.value for item in EIG2ActorContextScenario}


@dataclass(frozen=True)
class EIG2ActorScopeBreadthConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"eig2-actor-scope-breadth-{utc_timestamp()}.json"


def resolve_path(config_root: Path, raw_path: Path | str) -> Path:
    path = raw_path if isinstance(raw_path, Path) else Path(raw_path)
    return path if path.is_absolute() else config_root / path


def positive_case_by_id(fixture_pack: dict[str, Any], case_id: str) -> dict[str, Any]:
    for case in object_list(fixture_pack.get("positive_invocation_cases")):
        if case.get("id") == case_id:
            return case
    raise RuntimeError(f"Missing EIG-1 positive invocation case: {case_id}")


def connector_entries_from_fixture_pack(fixture_pack: dict[str, Any]) -> list[dict[str, Any]]:
    entries = object_list(fixture_pack.get("connector_manifests"))
    if not entries:
        raise RuntimeError("EIG-1 fixture pack must contain connector_manifests")
    return entries


def validate_policy_shape(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != "eig2_actor_scope_breadth_policy":
        errors.append(validation_error("policy.kind", "kind must be eig2_actor_scope_breadth_policy"))
    boundary = policy.get("scope_boundary")
    if not isinstance(boundary, dict):
        errors.append(validation_error("policy.scope_boundary", "scope_boundary must be an object"))
    else:
        if boundary.get("execution") != "local_stub_only":
            errors.append(validation_error("policy.scope_boundary.execution", "execution must be local_stub_only"))
        for key in (
            "real_oauth_provider_allowed",
            "shared_privileged_service_account_allowed",
            "external_network_allowed",
            "raw_mcp_allowed",
            "direct_model_tool_access_allowed",
            "runtime_registry_mutation_allowed",
            "target_repository_mutation_allowed",
        ):
            if boundary.get(key) is not False:
                errors.append(validation_error(f"policy.scope_boundary.{key}", f"{key} must be false"))
    assignments = object_list(policy.get("operation_scope_assignments"))
    assignment_keys = {
        (item.get("connector_id"), item.get("operation_id"))
        for item in assignments
        if isinstance(item.get("connector_id"), str) and isinstance(item.get("operation_id"), str)
    }
    required_assignments = {
        ("work_tracking_stub", "lookup_work_item"),
        ("work_tracking_stub", "dry_run_update_work_item"),
        ("business_record_stub", "lookup_business_record"),
        ("business_record_stub", "query_business_records"),
    }
    missing_assignments = sorted(f"{connector_id}.{operation_id}" for connector_id, operation_id in required_assignments - assignment_keys)
    if missing_assignments:
        errors.append(validation_error("policy.operation_scope_assignments", f"missing assignments: {', '.join(missing_assignments)}"))
    case_scenarios = {case.get("scenario") for case in object_list(policy.get("actor_scope_cases")) if isinstance(case.get("scenario"), str)}
    missing_case_scenarios = sorted(REQUIRED_ACTOR_SCOPE_SCENARIOS - case_scenarios)
    if missing_case_scenarios:
        errors.append(validation_error("policy.actor_scope_cases.scenarios", f"missing actor/scope scenarios: {', '.join(missing_case_scenarios)}"))
    context_scenarios = {
        case.get("scenario") for case in object_list(policy.get("actor_context_negative_cases")) if isinstance(case.get("scenario"), str)
    }
    missing_context_scenarios = sorted(REQUIRED_ACTOR_CONTEXT_SCENARIOS - context_scenarios)
    if missing_context_scenarios:
        errors.append(validation_error("policy.actor_context_negative_cases.scenarios", f"missing actor context scenarios: {', '.join(missing_context_scenarios)}"))
    if not object_list(policy.get("deferred_items")):
        errors.append(validation_error("policy.deferred_items", "at least one deferred item is required"))
    return errors


def scoped_connector_entries(fixture_entries: list[dict[str, Any]], assignments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries = copy.deepcopy(fixture_entries)
    assignment_by_operation = {
        (assignment.get("connector_id"), assignment.get("operation_id")): string_list(assignment.get("required_scopes"))
        for assignment in assignments
    }
    for entry in entries:
        manifest = entry.get("manifest")
        if not isinstance(manifest, dict):
            continue
        connector = manifest.get("connector")
        if not isinstance(connector, dict):
            continue
        connector_id = connector.get("id")
        operations = connector.get("operations")
        if not isinstance(operations, list):
            continue
        for operation in operations:
            if not isinstance(operation, dict):
                continue
            key = (connector_id, operation.get("id"))
            if key in assignment_by_operation:
                operation["required_scopes"] = assignment_by_operation[key]
    return entries


def validate_scoped_manifests(config_root: Path, entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    reports: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for entry in entries:
        manifest = entry.get("manifest")
        connector_id = "<missing>"
        if isinstance(manifest, dict) and isinstance(manifest.get("connector"), dict):
            connector_id = str(manifest["connector"].get("id") or "<missing>")
        try:
            validation = validate_connector_admission_manifest(manifest, config_root) if isinstance(manifest, dict) else None
            connector = validation["connector"] if validation else {}
            operations = [
                {
                    "operation_id": operation["id"],
                    "operation_class": operation["operation_class"],
                    "required_scopes": operation.get("required_scopes", []),
                }
                for operation in connector.get("operations", [])
                if isinstance(operation, dict)
            ]
            reports.append({"connector_id": connector_id, "status": "passed", "operations": operations})
        except ConnectorCatalogError as exc:
            errors.append(validation_error(exc.code, str(exc), item_id=connector_id))
            reports.append({"connector_id": connector_id, "status": "failed", "error_code": exc.code})
    return reports, errors


def actor_context_for_case(case: dict[str, Any]) -> dict[str, Any] | None:
    scenario = str(case.get("scenario") or "")
    scopes = string_list(case.get("granted_scopes"))
    if scenario == EIG2ActorContextScenario.MISSING_ACTOR_CONTEXT.value:
        return None
    actor_id = "eig2-actor"
    issued_at = "2026-01-01T00:00:00Z"
    expires_at = "2999-01-01T00:00:00Z"
    if scenario == EIG2ActorContextScenario.ANONYMOUS_ACTOR_CONTEXT.value:
        actor_id = "anonymous"
    if scenario == EIG2ActorContextScenario.EXPIRED_ACTOR_CONTEXT.value:
        issued_at = "2019-01-01T00:00:00Z"
        expires_at = "2020-01-01T00:00:00Z"
    context = actor_context(scopes=scopes, actor_id=actor_id, request_id=str(case.get("id") or "eig2-case"))
    context["issued_at_utc"] = issued_at
    context["expires_at_utc"] = expires_at
    if scenario == EIG2ActorContextScenario.MALFORMED_ACTOR_CONTEXT.value:
        context["granted_scopes"] = "work:read"
    return context


def invocation_case_from_policy_case(fixture_pack: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    source_case_id = case.get("source_case_id")
    if not isinstance(source_case_id, str) or not source_case_id.strip():
        raise RuntimeError(f"case {case.get('id')} missing source_case_id")
    source_case = positive_case_by_id(fixture_pack, source_case_id)
    invocation_case = {
        **source_case,
        "id": str(case.get("id") or source_case_id),
        "granted_scopes": string_list(case.get("granted_scopes")),
        "approval_required": case.get("approval_required") is True,
    }
    return invocation_case


def invoke_policy_case(runtime_root: Path, fixture_pack: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    invocation_case = invocation_case_from_policy_case(fixture_pack, case)
    raw_actor_context = actor_context_for_case(case)
    validated_actor = validate_actor_context(raw_actor_context)
    approval = approval_for_case(invocation_case, validated_actor) if invocation_case.get("approval_required") is True else None
    return mediate_connector_operation(
        config_root=runtime_root,
        connector_id=invocation_case["connector_id"],
        operation_id=invocation_case["operation_id"],
        arguments=invocation_case["arguments"],
        dry_run=invocation_case.get("dry_run") is True,
        actor_context=validated_actor,
        approval=approval,
    )


def audit_summary(audit: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision": audit.get("decision"),
        "authorization_status": audit.get("authorization_status"),
        "approval_state": audit.get("approval_state"),
        "required_scopes": audit.get("required_scopes", []),
        "granted_scopes": audit.get("granted_scopes", []),
        "missing_scopes": audit.get("missing_scopes", []),
        "argument_keys": audit.get("input", {}).get("argument_keys", []),
        "raw_auth_subject_stored": audit.get("raw_auth_subject_stored"),
        "raw_arguments_stored": audit.get("raw_arguments_stored"),
        "input_raw_arguments_stored": audit.get("input", {}).get("raw_arguments_stored"),
        "controller_owned_path": audit.get("controller_owned_path"),
        "raw_mcp_used": audit.get("raw_mcp_used"),
        "direct_model_tool_access_used": audit.get("direct_model_tool_access_used"),
        "external_network_called": audit.get("external_network_called"),
        "runtime_registry_changed": audit.get("runtime_registry_changed"),
        "target_repository_changed": audit.get("target_repository_changed"),
    }


def evaluate_policy_cases(
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
            expected_status = case.get("expected_status")
            expected_error = case.get("expected_error_code")
            expected_required_scopes = string_list(case.get("expected_required_scopes"))
            expected_missing_scopes = string_list(case.get("expected_missing_scopes"))
            case_errors: list[dict[str, str]] = []
            actual_status = "allowed"
            actual_error = None
            actual_missing_scopes: list[str] = []
            actual_required_scopes: list[str] = []
            recovery_present = False
            report_item: dict[str, Any] = {
                "case_id": case_id,
                "scenario": case.get("scenario"),
                "archetype": case.get("archetype"),
                "status": "failed",
                "expected_status": expected_status,
            }
            try:
                result = invoke_policy_case(runtime_root, fixture_pack, case)
                authorization = result["authorization"]
                audit = result["audit"]
                actual_required_scopes = string_list(authorization.get("required_scopes"))
                actual_missing_scopes = string_list(authorization.get("missing_scopes"))
                report_item.update(
                    {
                        "actual_status": actual_status,
                        "connector_id": result["connector_id"],
                        "operation_id": result["operation_id"],
                        "operation_class": result["operation_class"],
                        "audit": audit_summary(audit),
                    }
                )
                for key in (
                    "controller_owned_path",
                    "raw_mcp_used",
                    "direct_model_tool_access_used",
                    "external_network_called",
                    "runtime_registry_changed",
                    "target_repository_changed",
                ):
                    expected = False if key != "controller_owned_path" else True
                    if audit.get(key) is not expected:
                        case_errors.append(validation_error(f"case.audit.{key}", f"audit {key} must be {expected}", item_id=case_id))
                if audit.get("raw_auth_subject_stored") is not False or audit.get("raw_arguments_stored") is not False:
                    case_errors.append(validation_error("case.audit.raw_storage", "audit must not store raw auth subject or raw arguments", item_id=case_id))
                if audit.get("input", {}).get("raw_arguments_stored") is not False:
                    case_errors.append(validation_error("case.audit.input.raw_arguments", "audit input must not store raw arguments", item_id=case_id))
            except ConnectorIdentityError as exc:
                actual_status = "denied"
                actual_error = exc.code
                report_item.update({"actual_status": actual_status, "actual_error_code": actual_error, "recovery_present": False})
            except ConnectorMediationError as exc:
                actual_status = "denied"
                actual_error = exc.code
                authorization = exc.details.get("authorization") if isinstance(exc.details.get("authorization"), dict) else {}
                recovery = exc.details.get("recovery") if isinstance(exc.details.get("recovery"), dict) else None
                actual_required_scopes = string_list(authorization.get("required_scopes"))
                actual_missing_scopes = string_list(authorization.get("missing_scopes"))
                recovery_present = recovery is not None and bool(string_list(recovery.get("missing_scopes")))
                report_item.update(
                    {
                        "actual_status": actual_status,
                        "actual_error_code": actual_error,
                        "required_scopes": actual_required_scopes,
                        "missing_scopes": actual_missing_scopes,
                        "recovery_present": recovery_present,
                    }
                )
            if actual_status != expected_status:
                case_errors.append(validation_error("case.expected_status", f"expected {expected_status}, got {actual_status}", item_id=case_id))
            if expected_error and actual_error != expected_error:
                case_errors.append(validation_error("case.expected_error_code", f"expected {expected_error}, got {actual_error}", item_id=case_id))
            if actual_required_scopes != expected_required_scopes:
                case_errors.append(
                    validation_error(
                        "case.required_scopes",
                        f"expected required scopes {expected_required_scopes}, got {actual_required_scopes}",
                        item_id=case_id,
                    )
                )
            if actual_missing_scopes != expected_missing_scopes:
                case_errors.append(
                    validation_error(
                        "case.missing_scopes",
                        f"expected missing scopes {expected_missing_scopes}, got {actual_missing_scopes}",
                        item_id=case_id,
                    )
                )
            if case.get("recovery_required") is True and recovery_present is not True:
                case_errors.append(validation_error("case.recovery", "scope denials require recovery guidance", item_id=case_id))
            report_item["status"] = "failed" if case_errors else "passed"
            reports.append(report_item)
            errors.extend(case_errors)
    finally:
        clean_runtime_root(runtime_root)
    return reports, errors


def report_contains_raw_fixture_values(report: dict[str, Any]) -> bool:
    serialized = json.dumps(report, ensure_ascii=True, sort_keys=True)
    raw_values = [
        "WORK-SYN-1042",
        "DOC-SYN-1",
        "BR-SYN-001",
        "synthetic runbook",
        "Synthetic dry-run update.",
        "local-subject:eig2-actor",
    ]
    return any(value in serialized for value in raw_values)


def run_eig2_actor_scope_breadth_validation(config: EIG2ActorScopeBreadthConfig) -> dict[str, Any]:
    config_root = config.config_root
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path) if config.output_path else default_report_path(config_root)
    policy = read_json_object(policy_path)
    policy_errors = validate_policy_shape(policy)
    fixture_pack_path = resolve_path(config_root, str(policy.get("fixture_pack") or ""))
    fixture_pack = read_json_object(fixture_pack_path)
    fixture_entries = connector_entries_from_fixture_pack(fixture_pack)
    assignments = object_list(policy.get("operation_scope_assignments"))
    entries = scoped_connector_entries(fixture_entries, assignments)
    manifest_reports, manifest_errors = validate_scoped_manifests(config_root, entries)
    actor_scope_reports, actor_scope_errors = evaluate_policy_cases(
        config_root=config_root,
        fixture_pack=fixture_pack,
        entries=entries,
        cases=object_list(policy.get("actor_scope_cases")),
    )
    actor_context_reports, actor_context_errors = evaluate_policy_cases(
        config_root=config_root,
        fixture_pack=fixture_pack,
        entries=entries,
        cases=object_list(policy.get("actor_context_negative_cases")),
    )
    validation_errors = policy_errors + manifest_errors + actor_scope_errors + actor_context_errors
    status = "failed" if validation_errors else "passed"
    passed_actor_scope_scenarios = {
        report.get("scenario") for report in actor_scope_reports if report.get("status") == "passed" and isinstance(report.get("scenario"), str)
    }
    passed_context_scenarios = {
        report.get("scenario") for report in actor_context_reports if report.get("status") == "passed" and isinstance(report.get("scenario"), str)
    }
    report: dict[str, Any] = {
        "kind": "eig2_actor_scope_breadth_report",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "policy_path": str(policy_path),
        "fixture_pack": str(fixture_pack_path),
        "summary": {
            "manifest_count": len(manifest_reports),
            "operation_scope_assignment_count": len(assignments),
            "actor_scope_case_count": len(actor_scope_reports),
            "actor_context_negative_case_count": len(actor_context_reports),
            "passed_actor_scope_scenarios": sorted(str(item) for item in passed_actor_scope_scenarios),
            "passed_actor_context_scenarios": sorted(str(item) for item in passed_context_scenarios),
            "read_without_write_allowed": "read_success" in passed_actor_scope_scenarios,
            "write_without_read_allowed": "write_dry_run_success" in passed_actor_scope_scenarios,
            "cross_connector_scope_denied": "cross_connector_scope_denial" in passed_actor_scope_scenarios,
            "scope_denials_have_recovery": all(
                item.get("recovery_present") is True
                for item in actor_scope_reports
                if item.get("actual_error_code") == "connector_scope_denied"
            ),
            "runtime_registry_changed": False,
            "target_repository_changed": False,
            "external_network_called": False,
            "real_oauth_provider_used": False,
            "shared_privileged_service_account_used": False,
            "raw_mcp_used": False,
            "direct_model_tool_access_used": False,
            "validation_error_count": len(validation_errors),
            "phase294_ready": status == "passed",
        },
        "manifest_reports": manifest_reports,
        "actor_scope_reports": actor_scope_reports,
        "actor_context_negative_reports": actor_context_reports,
        "validation_errors": validation_errors,
        "created_at": utc_timestamp(),
    }
    report["summary"]["raw_fixture_values_retained_in_report"] = report_contains_raw_fixture_values(report)
    if report["summary"]["raw_fixture_values_retained_in_report"]:
        report["status"] = "failed"
        report["summary"]["phase294_ready"] = False
        report["validation_errors"].append(validation_error("report.raw_fixture_values", "report must not retain raw fixture values"))
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
