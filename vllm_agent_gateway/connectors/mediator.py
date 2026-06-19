"""Controller-owned connector operation mediation."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.connectors.catalog import (
    ConnectorCatalogError,
    ConnectorAuthType,
    ConnectorMediation,
    ConnectorOperationClass,
    ConnectorProtocol,
    runtime_connectors_by_id,
    string_list,
)
from vllm_agent_gateway.connectors.identity import replay_safe_argument_summary


class ConnectorMediationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "connector_mediation_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.status = status
        self.details = details or {}


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConnectorMediationError(f"{label} must be a JSON object.", code="invalid_connector_invocation")
    return value


def load_enabled_connector(config_root: Path, connector_id: str) -> dict[str, Any]:
    try:
        connectors = runtime_connectors_by_id(config_root)
    except ConnectorCatalogError as exc:
        raise ConnectorMediationError(str(exc), code=exc.code, status=exc.status) from exc
    connector = connectors.get(connector_id)
    if connector is None:
        raise ConnectorMediationError(f"Unknown connector: {connector_id}", code="unknown_connector", status=HTTPStatus.NOT_FOUND)
    if connector.get("enabled") is not True:
        raise ConnectorMediationError(f"Connector is not enabled: {connector_id}", code="connector_not_enabled", status=HTTPStatus.FORBIDDEN)
    return connector


def connector_operation(connector: dict[str, Any], operation_id: str) -> dict[str, Any]:
    operations = connector.get("operations")
    if not isinstance(operations, list):
        raise ConnectorMediationError("Connector operations must be a list.", code="invalid_connector_catalog")
    matches = [item for item in operations if isinstance(item, dict) and item.get("id") == operation_id]
    if not matches:
        raise ConnectorMediationError(f"Unknown connector operation: {operation_id}", code="unknown_connector_operation", status=HTTPStatus.NOT_FOUND)
    if len(matches) > 1:
        raise ConnectorMediationError(f"Duplicate connector operation: {operation_id}", code="duplicate_connector_operation_id")
    return matches[0]


def validate_connector_runtime_policy(connector: dict[str, Any]) -> None:
    if connector.get("mediation") != ConnectorMediation.CONTROLLER_OWNED.value:
        raise ConnectorMediationError("Connector mediation must be controller_owned.", code="unsafe_connector_mediation")
    if connector.get("protocol") != ConnectorProtocol.LOCAL_STUB.value:
        raise ConnectorMediationError(
            "Only local_stub connectors can be invoked in the current mediation phase.",
            code="connector_protocol_not_executable",
            status=HTTPStatus.FORBIDDEN,
        )
    safety = require_object(connector.get("safety"), "connector.safety")
    if safety.get("raw_mcp_allowed") is True:
        raise ConnectorMediationError("Raw MCP connector access is not allowed.", code="raw_mcp_bypass_not_allowed", status=HTTPStatus.FORBIDDEN)
    if safety.get("direct_model_tool_access") is True:
        raise ConnectorMediationError(
            "Direct model-to-connector tool access is not allowed.",
            code="direct_model_tool_bypass_not_allowed",
            status=HTTPStatus.FORBIDDEN,
        )


def validate_arguments(operation: dict[str, Any], arguments: dict[str, Any]) -> None:
    schema = require_object(operation.get("input_schema"), "connector.operation.input_schema")
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise ConnectorMediationError("connector.operation.input_schema.properties must be an object.", code="invalid_connector_schema")
    required = schema.get("required", [])
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        raise ConnectorMediationError("connector.operation.input_schema.required must be a list of strings.", code="invalid_connector_schema")
    missing = sorted(item for item in required if item not in arguments)
    if missing:
        raise ConnectorMediationError(
            f"Connector operation arguments are missing required field(s): {', '.join(missing)}",
            code="missing_connector_argument",
            status=HTTPStatus.BAD_REQUEST,
        )
    unsupported = sorted(set(arguments) - set(properties))
    if unsupported:
        raise ConnectorMediationError(
            f"Connector operation received unsupported argument(s): {', '.join(unsupported)}",
            code="unsupported_connector_argument",
            status=HTTPStatus.BAD_REQUEST,
        )
    for name, value in arguments.items():
        raw_schema = properties.get(name)
        if not isinstance(raw_schema, dict):
            raise ConnectorMediationError(f"connector.operation.input_schema.properties.{name} must be an object.", code="invalid_connector_schema")
        expected_type = raw_schema.get("type")
        if expected_type == "string" and not isinstance(value, str):
            raise ConnectorMediationError(f"Connector argument {name} must be a string.", code="invalid_connector_argument")
        if expected_type == "boolean" and not isinstance(value, bool):
            raise ConnectorMediationError(f"Connector argument {name} must be a boolean.", code="invalid_connector_argument")
        if expected_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            raise ConnectorMediationError(f"Connector argument {name} must be an integer.", code="invalid_connector_argument")
        if expected_type == "array" and not isinstance(value, list):
            raise ConnectorMediationError(f"Connector argument {name} must be an array.", code="invalid_connector_argument")
        if expected_type == "object" and not isinstance(value, dict):
            raise ConnectorMediationError(f"Connector argument {name} must be an object.", code="invalid_connector_argument")


def validate_approval(approval: Any, *, connector_id: str, operation_id: str) -> dict[str, Any]:
    if not isinstance(approval, dict):
        raise ConnectorMediationError(
            "connector write operations require approval.",
            code="missing_connector_invocation_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    if approval.get("status") != "approved_for_connector_invocation":
        raise ConnectorMediationError(
            "connector.invoke requires approval.status=approved_for_connector_invocation for write operations.",
            code="missing_connector_invocation_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    scope = approval.get("scope")
    scopes = set(scope) if isinstance(scope, list) else {scope} if isinstance(scope, str) else set()
    if "connector_invocation" not in scopes:
        raise ConnectorMediationError(
            "connector.invoke requires approval.scope=connector_invocation for write operations.",
            code="invalid_connector_invocation_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    if approval.get("connector_id") != connector_id or approval.get("operation_id") != operation_id:
        raise ConnectorMediationError(
            "connector invocation approval must match connector_id and operation_id.",
            code="stale_connector_invocation_approval",
            status=HTTPStatus.FORBIDDEN,
        )
    approval_refs = string_list(approval.get("approval_refs"), "approval.approval_refs")
    return {
        "status": "approved_for_connector_invocation",
        "scope": sorted(scopes),
        "connector_id": connector_id,
        "operation_id": operation_id,
        "approval_refs": approval_refs,
    }


def connector_required_scopes(auth: dict[str, Any]) -> list[str]:
    try:
        return string_list(auth.get("required_scopes", []), "connector.auth.required_scopes", allow_empty=True)
    except ConnectorCatalogError as exc:
        raise ConnectorMediationError(str(exc), code=exc.code, status=exc.status) from exc


def authorize_actor_for_connector(auth: dict[str, Any], actor_context: dict[str, Any]) -> dict[str, Any]:
    auth_type = auth.get("type")
    required_scopes = connector_required_scopes(auth)
    granted_scopes = actor_context.get("granted_scopes", [])
    if not isinstance(granted_scopes, list) or not all(isinstance(item, str) for item in granted_scopes):
        raise ConnectorMediationError(
            "actor_context.granted_scopes must be validated before connector mediation.",
            code="invalid_connector_actor_context",
            status=HTTPStatus.FORBIDDEN,
        )
    missing_scopes = sorted(set(required_scopes) - set(granted_scopes))
    decision = {
        "auth_type": auth_type,
        "required_scopes": required_scopes,
        "granted_scopes": sorted(set(granted_scopes)),
        "missing_scopes": missing_scopes,
        "scope_match": not missing_scopes,
        "authorization_status": "allowed",
    }
    if auth_type == ConnectorAuthType.OAUTH_USER_SCOPE.value and missing_scopes:
        decision["authorization_status"] = "denied"
        raise ConnectorMediationError(
            f"Actor is missing required connector scope(s): {', '.join(missing_scopes)}",
            code="connector_scope_denied",
            status=HTTPStatus.FORBIDDEN,
            details={
                "authorization": decision,
                "recovery": {
                    "required_action": "Retry with actor_context.granted_scopes containing the connector required scopes.",
                    "missing_scopes": missing_scopes,
                },
            },
        )
    return decision


def approval_state(operation_class: Any, approval_record: dict[str, Any] | None) -> str:
    if operation_class == ConnectorOperationClass.WRITE.value:
        return "approved" if approval_record is not None else "missing"
    return "not_required"


def output_summary(result_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "result_keys": sorted(result_payload),
        "status": result_payload.get("status") if isinstance(result_payload.get("status"), str) else None,
        "raw_output_summary_only": True,
    }


def audit_record(
    *,
    actor_context: dict[str, Any],
    connector_id: str,
    operation_id: str,
    operation_class: Any,
    arguments: dict[str, Any],
    authorization: dict[str, Any],
    approval_record: dict[str, Any] | None,
    decision: str,
    result_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "kind": "connector_invocation_audit",
        "schema_version": 1,
        "actor_id": actor_context["actor_id"],
        "auth_subject_hash": actor_context["auth_subject_hash"],
        "session_id": actor_context["session_id"],
        "request_id": actor_context["request_id"],
        "connector_id": connector_id,
        "operation_id": operation_id,
        "operation_class": operation_class,
        "required_scopes": authorization["required_scopes"],
        "granted_scopes": authorization["granted_scopes"],
        "missing_scopes": authorization["missing_scopes"],
        "authorization_status": authorization["authorization_status"],
        "approval_state": approval_state(operation_class, approval_record),
        "decision": decision,
        "input": replay_safe_argument_summary(arguments),
        "output": output_summary(result_payload) if result_payload is not None else None,
        "raw_auth_subject_stored": False,
        "raw_arguments_stored": False,
    }


def mediate_connector_operation(
    *,
    config_root: Path,
    connector_id: str,
    operation_id: str,
    arguments: dict[str, Any],
    dry_run: bool,
    actor_context: dict[str, Any],
    approval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    connector = load_enabled_connector(config_root, connector_id)
    validate_connector_runtime_policy(connector)
    operation = connector_operation(connector, operation_id)
    validate_arguments(operation, arguments)
    operation_class = operation.get("operation_class")
    auth = require_object(connector.get("auth"), "connector.auth")
    authorization = authorize_actor_for_connector(auth, actor_context)
    if auth.get("type") == ConnectorAuthType.SERVICE_READ_ONLY.value and operation_class == ConnectorOperationClass.WRITE.value:
        raise ConnectorMediationError("service_read_only connectors cannot expose write operations.", code="unsafe_connector_auth")
    approval_record = None
    if operation_class == ConnectorOperationClass.WRITE.value:
        try:
            approval_record = validate_approval(approval, connector_id=connector_id, operation_id=operation_id)
        except ConnectorMediationError as exc:
            exc.details = {**exc.details, "authorization": authorization}
            raise
        if dry_run is not True:
            raise ConnectorMediationError(
                "Write connector operations are dry-run only in the current mediation phase.",
                code="connector_write_execution_not_supported",
                status=HTTPStatus.FORBIDDEN,
                details={"authorization": authorization},
            )
    if operation_class == ConnectorOperationClass.DRY_RUN.value and dry_run is not True:
        raise ConnectorMediationError(
            "dry_run connector operations require dry_run=true.",
            code="connector_dry_run_required",
            details={"authorization": authorization},
        )

    result_payload = operation.get("stub_response")
    if not isinstance(result_payload, dict):
        result_payload = {
            "status": "stubbed",
            "connector_id": connector_id,
            "operation_id": operation_id,
        }
    audit = audit_record(
        actor_context=actor_context,
        connector_id=connector_id,
        operation_id=operation_id,
        operation_class=operation_class,
        arguments=arguments,
        authorization=authorization,
        approval_record=approval_record,
        decision="allowed",
        result_payload=result_payload,
    )
    return {
        "kind": "connector_invocation_result",
        "schema_version": 1,
        "connector_id": connector_id,
        "operation_id": operation_id,
        "operation_class": operation_class,
        "dry_run": dry_run,
        "protocol": connector.get("protocol"),
        "mediation": connector.get("mediation"),
        "auth_type": auth.get("type"),
        "actor_context": actor_context,
        "authorization": authorization,
        "approval": approval_record,
        "result": result_payload,
        "audit": {
            **audit,
            "controller_owned_path": True,
            "raw_mcp_used": False,
            "direct_model_tool_access_used": False,
            "external_network_called": False,
            "runtime_registry_changed": False,
            "target_repository_changed": False,
        },
    }
