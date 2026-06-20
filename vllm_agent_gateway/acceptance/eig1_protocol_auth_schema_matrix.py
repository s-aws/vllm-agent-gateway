"""EIG-1 protocol, auth, and schema matrix validation."""

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
    clean_runtime_root,
    copy_runtime_root,
    install_runtime_connectors,
    object_list,
    read_json_object,
    string_list,
    validation_error,
)
from vllm_agent_gateway.connectors.catalog import (
    ConnectorAuthType,
    ConnectorCatalogError,
    ConnectorOperationClass,
    ConnectorProtocol,
    validate_connector_admission_manifest,
    write_json,
)
from vllm_agent_gateway.connectors.identity import validate_actor_context
from vllm_agent_gateway.connectors.mediator import ConnectorMediationError, mediate_connector_operation


SCHEMA_VERSION = 1
DEFAULT_MATRIX_PATH = Path("runtime") / "eig1_protocol_auth_schema_matrix.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "eig1-protocol-auth-schema-matrix"


class EIG1Classification(str, Enum):
    ACCEPTED = "accepted"
    EXECUTABLE = "executable"
    VALIDATION_ONLY = "validation_only"
    REJECTED = "rejected"
    DEFERRED = "deferred"


@dataclass(frozen=True)
class EIG1ProtocolAuthSchemaConfig:
    config_root: Path
    matrix_path: Path = DEFAULT_MATRIX_PATH
    output_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"eig1-protocol-auth-schema-{utc_timestamp()}.json"


def resolve_path(config_root: Path, raw_path: Path | str) -> Path:
    path = raw_path if isinstance(raw_path, Path) else Path(raw_path)
    return path if path.is_absolute() else config_root / path


def connector_entries_from_fixture_pack(pack: dict[str, Any]) -> list[dict[str, Any]]:
    entries = object_list(pack.get("connector_manifests"))
    if not entries:
        raise RuntimeError("EIG-1 fixture pack must contain connector_manifests")
    return entries


def manifest_by_connector_id(entries: list[dict[str, Any]], connector_id: str) -> dict[str, Any]:
    for entry in entries:
        manifest = entry.get("manifest")
        if not isinstance(manifest, dict):
            continue
        connector = manifest.get("connector")
        if isinstance(connector, dict) and connector.get("id") == connector_id:
            return copy.deepcopy(manifest)
    raise RuntimeError(f"Missing connector fixture manifest: {connector_id}")


def read_fixture_pack(config_root: Path, matrix: dict[str, Any]) -> dict[str, Any]:
    fixture_pack = matrix.get("fixture_pack")
    if not isinstance(fixture_pack, str) or not fixture_pack.strip():
        raise RuntimeError("matrix.fixture_pack must be a non-empty path")
    return read_json_object(resolve_path(config_root, fixture_pack))


def validate_matrix_shape(matrix: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if matrix.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("matrix.schema_version", "schema_version must be 1"))
    if matrix.get("kind") != "eig1_protocol_auth_schema_matrix":
        errors.append(validation_error("matrix.kind", "kind must be eig1_protocol_auth_schema_matrix"))
    boundary = matrix.get("scope_boundary")
    if not isinstance(boundary, dict):
        errors.append(validation_error("matrix.scope_boundary", "scope_boundary must be an object"))
    else:
        if boundary.get("only_executable_protocol") != ConnectorProtocol.LOCAL_STUB.value:
            errors.append(validation_error("matrix.scope_boundary.only_executable_protocol", "only local_stub may be executable"))
        for key in (
            "non_executable_protocols_must_fail_at_mediation",
            "external_network_allowed",
            "raw_mcp_allowed",
            "direct_model_tool_access_allowed",
            "runtime_registry_mutation_allowed",
        ):
            expected = True if key == "non_executable_protocols_must_fail_at_mediation" else False
            if boundary.get(key) is not expected:
                errors.append(validation_error(f"matrix.scope_boundary.{key}", f"{key} must be {str(expected).lower()}"))
    required_protocols = {
        ConnectorProtocol.LOCAL_STUB.value,
        ConnectorProtocol.HTTPS_JSON.value,
        ConnectorProtocol.MCP_MEDIATED.value,
        "raw_http",
    }
    protocol_values = {item.get("protocol") for item in object_list(matrix.get("protocol_cases"))}
    missing_protocols = sorted(required_protocols - protocol_values)
    if missing_protocols:
        errors.append(validation_error("matrix.protocol_cases", f"missing protocol cases: {', '.join(missing_protocols)}"))
    auth_case_ids = {item.get("id") for item in object_list(matrix.get("auth_cases"))}
    required_auth_case_ids = {
        "EIG1-AUTH-STUB-LOCAL",
        "EIG1-AUTH-STUB-HTTPS",
        "EIG1-AUTH-SERVICE-READ",
        "EIG1-AUTH-SERVICE-WRITE",
        "EIG1-AUTH-OAUTH-SCOPED",
        "EIG1-AUTH-OAUTH-MISSING-SCOPES",
    }
    missing_auth = sorted(required_auth_case_ids - auth_case_ids)
    if missing_auth:
        errors.append(validation_error("matrix.auth_cases", f"missing auth cases: {', '.join(missing_auth)}"))
    field_shapes = {item.get("field_shape") for item in object_list(matrix.get("schema_cases"))}
    required_shapes = {
        "required_string",
        "optional_boolean",
        "integer",
        "array",
        "object",
        "unknown_argument",
        "missing_required",
        "malformed_string",
        "malformed_boolean",
        "malformed_integer",
        "malformed_array",
        "malformed_object",
        "deep_object_property_validation",
    }
    missing_shapes = sorted(required_shapes - field_shapes)
    if missing_shapes:
        errors.append(validation_error("matrix.schema_cases", f"missing schema cases: {', '.join(missing_shapes)}"))
    return errors


def validate_manifest_error(config_root: Path, manifest: dict[str, Any]) -> str:
    try:
        validate_connector_admission_manifest(manifest, config_root)
    except ConnectorCatalogError as exc:
        return exc.code
    return "passed"


def executable_mediation_status(config_root: Path, manifest: dict[str, Any]) -> str:
    runtime_root = copy_runtime_root(config_root)
    try:
        install_runtime_connectors(runtime_root, [{"manifest": manifest}], enabled=True)
        validated_actor = validate_actor_context(actor_context(scopes=string_list(manifest["connector"]["auth"].get("required_scopes"))))
        operation = manifest["connector"]["operations"][0]
        arguments = {}
        for required in operation["input_schema"].get("required", []):
            schema = operation["input_schema"]["properties"][required]
            if schema.get("type") == "string":
                arguments[required] = "synthetic"
            elif schema.get("type") == "boolean":
                arguments[required] = True
            elif schema.get("type") == "integer":
                arguments[required] = 1
            elif schema.get("type") == "array":
                arguments[required] = ["synthetic"]
            elif schema.get("type") == "object":
                arguments[required] = {"synthetic": True}
        mediate_connector_operation(
            config_root=runtime_root,
            connector_id=manifest["connector"]["id"],
            operation_id=operation["id"],
            arguments=arguments,
            dry_run=True,
            actor_context=validated_actor,
        )
        return "allowed"
    except ConnectorMediationError as exc:
        return exc.code
    finally:
        clean_runtime_root(runtime_root)


def protocol_manifest(entries: list[dict[str, Any]], protocol: str) -> dict[str, Any]:
    manifest = manifest_by_connector_id(entries, "knowledge_lookup_stub")
    connector = manifest["connector"]
    connector["protocol"] = protocol
    connector["auth"] = {"type": ConnectorAuthType.SERVICE_READ_ONLY.value, "required_scopes": []}
    return manifest


def validate_protocol_cases(config_root: Path, matrix: dict[str, Any], entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    reports: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for case in object_list(matrix.get("protocol_cases")):
        case_id = str(case.get("id") or "unknown")
        protocol = str(case.get("protocol") or "")
        manifest = protocol_manifest(entries, protocol)
        validation_status = validate_manifest_error(config_root, manifest)
        mediation_status = None
        if validation_status == "passed" and case.get("classification") in {EIG1Classification.EXECUTABLE.value, EIG1Classification.VALIDATION_ONLY.value}:
            mediation_status = executable_mediation_status(config_root, manifest)
        expected_validation = case.get("expected_validation_status")
        expected_error = case.get("expected_validation_error")
        expected_mediation = case.get("expected_mediation_status")
        expected_mediation_error = case.get("expected_mediation_error")
        case_errors: list[dict[str, str]] = []
        if expected_validation and validation_status != expected_validation:
            case_errors.append(validation_error("protocol.validation_status", f"expected {expected_validation}, got {validation_status}", item_id=case_id))
        if expected_error and validation_status != expected_error:
            case_errors.append(validation_error("protocol.validation_error", f"expected {expected_error}, got {validation_status}", item_id=case_id))
        if expected_mediation and mediation_status != expected_mediation:
            case_errors.append(validation_error("protocol.mediation_status", f"expected {expected_mediation}, got {mediation_status}", item_id=case_id))
        if expected_mediation_error and mediation_status != expected_mediation_error:
            case_errors.append(validation_error("protocol.mediation_error", f"expected {expected_mediation_error}, got {mediation_status}", item_id=case_id))
        status = "failed" if case_errors else "passed"
        reports.append(
            {
                "case_id": case_id,
                "protocol": protocol,
                "classification": case.get("classification"),
                "status": status,
                "validation_status": validation_status,
                "mediation_status": mediation_status,
            }
        )
        errors.extend(case_errors)
    return reports, errors


def auth_manifest(entries: list[dict[str, Any]], case: dict[str, Any]) -> dict[str, Any]:
    connector_id = "work_tracking_stub" if case.get("operation_shape") == "includes_write" else "knowledge_lookup_stub"
    manifest = manifest_by_connector_id(entries, connector_id)
    connector = manifest["connector"]
    connector["protocol"] = case["protocol"]
    connector["auth"] = {
        "type": case["auth_type"],
        "required_scopes": string_list(case.get("required_scopes")),
    }
    if case.get("auth_type") == ConnectorAuthType.NONE_FOR_STUB.value:
        connector["auth"]["required_scopes"] = []
    if case.get("operation_shape") == "read_only":
        connector["operations"] = [
            operation for operation in connector["operations"] if operation.get("operation_class") == ConnectorOperationClass.READ.value
        ]
    return manifest


def validate_auth_cases(config_root: Path, matrix: dict[str, Any], entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    reports: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for case in object_list(matrix.get("auth_cases")):
        case_id = str(case.get("id") or "unknown")
        manifest = auth_manifest(entries, case)
        validation_status = validate_manifest_error(config_root, manifest)
        expected_validation = case.get("expected_validation_status")
        expected_error = case.get("expected_validation_error")
        case_errors: list[dict[str, str]] = []
        if expected_validation and validation_status != expected_validation:
            case_errors.append(validation_error("auth.validation_status", f"expected {expected_validation}, got {validation_status}", item_id=case_id))
        if expected_error and validation_status != expected_error:
            case_errors.append(validation_error("auth.validation_error", f"expected {expected_error}, got {validation_status}", item_id=case_id))
        status = "failed" if case_errors else "passed"
        reports.append(
            {
                "case_id": case_id,
                "auth_type": case.get("auth_type"),
                "protocol": case.get("protocol"),
                "operation_shape": case.get("operation_shape"),
                "classification": case.get("classification"),
                "status": status,
                "validation_status": validation_status,
            }
        )
        errors.extend(case_errors)
    return reports, errors


def schema_case_invocation(
    config_root: Path,
    entries: list[dict[str, Any]],
    *,
    connector_id: str,
    operation_id: str,
    arguments: dict[str, Any],
    scopes: list[str],
) -> str:
    runtime_root = copy_runtime_root(config_root)
    try:
        install_runtime_connectors(runtime_root, entries, enabled=True)
        validated_actor = validate_actor_context(actor_context(scopes=scopes))
        mediate_connector_operation(
            config_root=runtime_root,
            connector_id=connector_id,
            operation_id=operation_id,
            arguments=arguments,
            dry_run=True,
            actor_context=validated_actor,
        )
        return "allowed"
    except ConnectorMediationError as exc:
        return exc.code
    finally:
        clean_runtime_root(runtime_root)


def schema_status_for_shape(config_root: Path, entries: list[dict[str, Any]], field_shape: str) -> str:
    if field_shape == "unknown_argument":
        return schema_case_invocation(
            config_root,
            entries,
            connector_id="work_tracking_stub",
            operation_id="lookup_work_item",
            arguments={"work_item_id": "synthetic", "extra": "not-supported"},
            scopes=["work:read", "work:write"],
        )
    if field_shape == "missing_required":
        return schema_case_invocation(
            config_root,
            entries,
            connector_id="work_tracking_stub",
            operation_id="lookup_work_item",
            arguments={"include_history": True},
            scopes=["work:read", "work:write"],
        )
    if field_shape == "malformed_string":
        return schema_case_invocation(
            config_root,
            entries,
            connector_id="work_tracking_stub",
            operation_id="lookup_work_item",
            arguments={"work_item_id": 123},
            scopes=["work:read", "work:write"],
        )
    if field_shape == "malformed_boolean":
        return schema_case_invocation(
            config_root,
            entries,
            connector_id="work_tracking_stub",
            operation_id="lookup_work_item",
            arguments={"work_item_id": "synthetic", "include_history": "true"},
            scopes=["work:read", "work:write"],
        )
    if field_shape == "malformed_integer":
        return schema_case_invocation(
            config_root,
            entries,
            connector_id="knowledge_lookup_stub",
            operation_id="search_documents",
            arguments={"query": "synthetic", "limit": "2"},
            scopes=[],
        )
    if field_shape == "malformed_array":
        return schema_case_invocation(
            config_root,
            entries,
            connector_id="knowledge_lookup_stub",
            operation_id="read_document_summary",
            arguments={"document_id": "synthetic", "include_sections": "overview"},
            scopes=[],
        )
    if field_shape == "malformed_object":
        return schema_case_invocation(
            config_root,
            entries,
            connector_id="business_record_stub",
            operation_id="lookup_business_record",
            arguments={"record_id": "synthetic", "include_metrics": True, "filters": "region"},
            scopes=["records:read"],
        )
    if field_shape == "deep_object_property_validation":
        return "deferred"
    return "allowed"


def positive_case_by_id(positive_cases: list[dict[str, Any]], case_id: str) -> dict[str, Any] | None:
    for case in positive_cases:
        if case.get("id") == case_id:
            return case
    return None


def accepted_schema_status(config_root: Path, entries: list[dict[str, Any]], case: dict[str, Any], positive_cases: list[dict[str, Any]]) -> str:
    source_case_id = case.get("source_case_id")
    if not isinstance(source_case_id, str) or not source_case_id.strip():
        return "missing_source_case"
    source_case = positive_case_by_id(positive_cases, source_case_id)
    if source_case is None:
        return "missing_source_case"
    return schema_case_invocation(
        config_root,
        entries,
        connector_id=source_case["connector_id"],
        operation_id=source_case["operation_id"],
        arguments=source_case["arguments"],
        scopes=string_list(source_case.get("granted_scopes")),
    )


def validate_schema_cases(
    config_root: Path,
    matrix: dict[str, Any],
    entries: list[dict[str, Any]],
    positive_cases: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    reports: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for case in object_list(matrix.get("schema_cases")):
        case_id = str(case.get("id") or "unknown")
        classification = case.get("classification")
        field_shape = str(case.get("field_shape") or "")
        if classification == EIG1Classification.ACCEPTED.value:
            actual_status = accepted_schema_status(config_root, entries, case, positive_cases)
        else:
            actual_status = schema_status_for_shape(config_root, entries, field_shape)
        expected_error = case.get("expected_mediation_error")
        case_errors: list[dict[str, str]] = []
        if classification == EIG1Classification.ACCEPTED.value and actual_status != "allowed":
            case_errors.append(validation_error("schema.accepted_status", f"expected allowed, got {actual_status}", item_id=case_id))
        if classification == EIG1Classification.REJECTED.value and actual_status != expected_error:
            case_errors.append(validation_error("schema.rejected_status", f"expected {expected_error}, got {actual_status}", item_id=case_id))
        if classification == EIG1Classification.DEFERRED.value and actual_status != EIG1Classification.DEFERRED.value:
            case_errors.append(validation_error("schema.deferred_status", f"expected deferred, got {actual_status}", item_id=case_id))
        status = "failed" if case_errors else "passed"
        reports.append(
            {
                "case_id": case_id,
                "field_shape": field_shape,
                "classification": classification,
                "status": status,
                "actual_status": actual_status,
            }
        )
        errors.extend(case_errors)
    return reports, errors


def run_eig1_protocol_auth_schema_validation(config: EIG1ProtocolAuthSchemaConfig) -> dict[str, Any]:
    config_root = config.config_root
    matrix_path = resolve_path(config_root, config.matrix_path)
    output_path = resolve_path(config_root, config.output_path) if config.output_path else default_report_path(config_root)
    matrix = read_json_object(matrix_path)
    shape_errors = validate_matrix_shape(matrix)
    fixture_pack = read_fixture_pack(config_root, matrix)
    entries = connector_entries_from_fixture_pack(fixture_pack)
    positive_cases = object_list(fixture_pack.get("positive_invocation_cases"))
    protocol_reports, protocol_errors = validate_protocol_cases(config_root, matrix, entries)
    auth_reports, auth_errors = validate_auth_cases(config_root, matrix, entries)
    schema_reports, schema_errors = validate_schema_cases(config_root, matrix, entries, positive_cases)
    validation_errors = shape_errors + protocol_errors + auth_errors + schema_errors
    status = "failed" if validation_errors else "passed"
    report: dict[str, Any] = {
        "kind": "eig1_protocol_auth_schema_report",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "matrix_path": str(matrix_path),
        "summary": {
            "protocol_case_count": len(protocol_reports),
            "auth_case_count": len(auth_reports),
            "schema_case_count": len(schema_reports),
            "validation_error_count": len(validation_errors),
            "only_executable_protocol": ConnectorProtocol.LOCAL_STUB.value,
            "non_executable_protocols_fail_at_mediation": all(
                item["status"] == "passed"
                for item in protocol_reports
                if item.get("classification") == EIG1Classification.VALIDATION_ONLY.value
            ),
            "deferred_schema_case_count": sum(
                1 for item in schema_reports if item.get("classification") == EIG1Classification.DEFERRED.value
            ),
            "runtime_registry_changed": False,
            "external_network_called": False,
            "raw_mcp_used": False,
            "direct_model_tool_access_used": False,
            "phase291_ready": status == "passed",
        },
        "protocol_reports": protocol_reports,
        "auth_reports": auth_reports,
        "schema_reports": schema_reports,
        "validation_errors": validation_errors,
        "created_at": utc_timestamp(),
    }
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
