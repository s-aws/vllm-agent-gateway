"""Validation for connector user-scoped invocation audit artifacts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_AUDIT_FIELDS = {
    "kind",
    "schema_version",
    "actor_id",
    "auth_subject_hash",
    "session_id",
    "request_id",
    "connector_id",
    "operation_id",
    "required_scopes",
    "granted_scopes",
    "missing_scopes",
    "authorization_status",
    "approval_state",
    "decision",
    "input",
    "raw_auth_subject_stored",
    "raw_arguments_stored",
}


class ConnectorUserScopeAuditError(RuntimeError):
    pass


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConnectorUserScopeAuditError(f"Expected JSON object: {path}")
    return value


def validate_string_list(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"{label} must be a list of strings")


def validate_connector_invocation_audit_report(report: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if report.get("kind") != "connector_invocation_report":
        errors.append("report.kind must be connector_invocation_report")
    if report.get("schema_version") != 1:
        errors.append("report.schema_version must be 1")
    status = report.get("status")
    if status not in {"completed", "failed"}:
        errors.append("report.status must be completed or failed")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errors.append("report.summary must be an object")
        summary = {}
    audit = report.get("audit")
    if not isinstance(audit, dict):
        errors.append("report.audit must be an object")
        audit = {}
    missing_fields = sorted(REQUIRED_AUDIT_FIELDS - set(audit))
    if missing_fields:
        errors.append(f"report.audit missing fields: {', '.join(missing_fields)}")
    if audit.get("kind") != "connector_invocation_audit":
        errors.append("audit.kind must be connector_invocation_audit")
    if audit.get("schema_version") != 1:
        errors.append("audit.schema_version must be 1")
    if audit.get("raw_auth_subject_stored") is not False:
        errors.append("audit.raw_auth_subject_stored must be false")
    if audit.get("raw_arguments_stored") is not False:
        errors.append("audit.raw_arguments_stored must be false")
    validate_string_list(audit.get("required_scopes"), "audit.required_scopes", errors)
    validate_string_list(audit.get("granted_scopes"), "audit.granted_scopes", errors)
    validate_string_list(audit.get("missing_scopes"), "audit.missing_scopes", errors)
    input_summary = audit.get("input")
    if not isinstance(input_summary, dict):
        errors.append("audit.input must be an object")
        input_summary = {}
    if input_summary.get("raw_arguments_stored") is not False:
        errors.append("audit.input.raw_arguments_stored must be false")
    if not isinstance(input_summary.get("argument_hash"), str) or not HEX_SHA256_RE.fullmatch(input_summary["argument_hash"]):
        errors.append("audit.input.argument_hash must be a sha256 hex string")
    validate_string_list(input_summary.get("argument_keys"), "audit.input.argument_keys", errors)
    decision = audit.get("decision")
    if decision == "allowed":
        if status != "completed":
            errors.append("allowed audit decision requires completed report status")
        if audit.get("authorization_status") != "allowed":
            errors.append("allowed audit decision requires authorization_status=allowed")
    elif decision == "denied":
        if status != "failed":
            errors.append("denied audit decision requires failed report status")
        if not isinstance(audit.get("denial_code"), str) or not audit["denial_code"]:
            errors.append("denied audit decision requires denial_code")
    else:
        errors.append("audit.decision must be allowed or denied")
    actor_bound = summary.get("actor_bound")
    if actor_bound is True and not audit.get("actor_id"):
        errors.append("actor_bound summary requires audit.actor_id")
    if actor_bound is False and audit.get("actor_id") is not None:
        errors.append("unbound actor summary must not include audit.actor_id")
    return {
        "kind": "connector_user_scope_audit_validation_report",
        "schema_version": 1,
        "status": "passed" if not errors else "failed",
        "summary": {
            "audit_status": "passed" if not errors else "failed",
            "error_count": len(errors),
            "connector_id": audit.get("connector_id"),
            "operation_id": audit.get("operation_id"),
            "decision": audit.get("decision"),
            "authorization_status": audit.get("authorization_status"),
            "raw_auth_subject_stored": audit.get("raw_auth_subject_stored"),
            "raw_arguments_stored": audit.get("raw_arguments_stored"),
        },
        "errors": errors,
    }


def validate_connector_invocation_audit_path(path: Path) -> dict[str, Any]:
    report = read_json_object(path)
    validation = validate_connector_invocation_audit_report(report)
    if validation["status"] != "passed":
        raise ConnectorUserScopeAuditError(f"connector invocation audit validation failed with {len(validation['errors'])} error(s)")
    return validation
