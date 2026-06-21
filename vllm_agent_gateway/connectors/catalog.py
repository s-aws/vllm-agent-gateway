"""Governed connector catalog admission helpers."""

from __future__ import annotations

import re
import json
from enum import Enum
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.tools.catalog import (
    artifact_timestamp,
    utc_now,
    write_json,
)


SCHEMA_VERSION = 1
CONNECTOR_CATALOG_PATH = Path("runtime") / "connectors.json"
WORKFLOW_CATALOG_PATH = Path("runtime") / "workflows.json"
CONNECTOR_ID_PATTERN = re.compile(r"[a-z][a-z0-9_]*")
OPERATION_ID_PATTERN = re.compile(r"[a-z][a-z0-9_]*")


class ConnectorProtocol(str, Enum):
    HTTPS_JSON = "https_json"
    MCP_MEDIATED = "mcp_mediated"
    LOCAL_STUB = "local_stub"


class ConnectorMediation(str, Enum):
    CONTROLLER_OWNED = "controller_owned"


class ConnectorAuthType(str, Enum):
    OAUTH_USER_SCOPE = "oauth_user_scope"
    SERVICE_READ_ONLY = "service_read_only"
    NONE_FOR_STUB = "none_for_stub"


class ConnectorOperationClass(str, Enum):
    READ = "read"
    WRITE = "write"
    DRY_RUN = "dry_run"


class ConnectorDataClassification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"


class ConnectorPiiPolicy(str, Enum):
    NOT_ALLOWED = "not_allowed"
    MASKED_REQUIRED = "masked_required"
    POLICY_REQUIRED = "policy_required"


class ConnectorCatalogError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "connector_catalog_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConnectorCatalogError(f"Missing {label}: {path}", code=f"missing_{label.replace(' ', '_')}") from exc
    except json.JSONDecodeError as exc:
        raise ConnectorCatalogError(f"Invalid {label} JSON: {exc}", code=f"invalid_{label.replace(' ', '_')}") from exc
    if not isinstance(value, dict):
        raise ConnectorCatalogError(f"{label} must contain a JSON object.", code=f"invalid_{label.replace(' ', '_')}")
    return value


def string_list(value: Any, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ConnectorCatalogError(f"{label} must be a list of non-empty strings.", code="invalid_connector_manifest")
    if not allow_empty and not value:
        raise ConnectorCatalogError(f"{label} must not be empty.", code="invalid_connector_manifest")
    return list(value)


def enum_values(enum_type: type[Enum]) -> set[str]:
    return {item.value for item in enum_type}


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConnectorCatalogError(f"{label} must be a JSON object.", code="invalid_connector_manifest")
    return value


def require_string(value: Any, label: str, *, min_length: int = 1) -> str:
    if not isinstance(value, str) or len(value.strip()) < min_length:
        raise ConnectorCatalogError(f"{label} must be a non-empty string.", code="invalid_connector_manifest")
    return value


def validate_json_schema_object(value: Any, label: str) -> dict[str, Any]:
    schema = require_object(value, label)
    if schema.get("type") != "object":
        raise ConnectorCatalogError(f"{label}.type must be object.", code="invalid_connector_schema")
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise ConnectorCatalogError(f"{label}.properties must be an object.", code="invalid_connector_schema")
    required = schema.get("required", [])
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        raise ConnectorCatalogError(f"{label}.required must be a list of strings.", code="invalid_connector_schema")
    return schema


def runtime_connectors_by_id(config_root: Path) -> dict[str, dict[str, Any]]:
    catalog = read_json_object(config_root / CONNECTOR_CATALOG_PATH, "connector catalog")
    if catalog.get("schema_version") != SCHEMA_VERSION:
        raise ConnectorCatalogError("runtime/connectors.json schema_version must be 1.", code="invalid_connector_catalog")
    connectors = catalog.get("connectors")
    if not isinstance(connectors, list):
        raise ConnectorCatalogError("runtime/connectors.json must contain a connectors list.", code="invalid_connector_catalog")
    values: dict[str, dict[str, Any]] = {}
    for item in connectors:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ConnectorCatalogError("Every runtime connector entry must contain an id.", code="invalid_connector_catalog")
        if item["id"] in values:
            raise ConnectorCatalogError(f"Duplicate runtime connector id: {item['id']}", code="duplicate_connector_id")
        values[item["id"]] = item
    return values


def workflows_by_id(config_root: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json_object(config_root / WORKFLOW_CATALOG_PATH, "workflow catalog")
    workflows = manifest.get("workflows")
    if not isinstance(workflows, list):
        raise ConnectorCatalogError("runtime/workflows.json must contain a workflows list.", code="invalid_workflow_catalog")
    return {item["id"]: item for item in workflows if isinstance(item, dict) and isinstance(item.get("id"), str)}


def validate_auth_policy(connector: dict[str, Any], protocol: str) -> dict[str, Any]:
    auth = require_object(connector.get("auth"), "connector.auth")
    auth_type = auth.get("type")
    if auth_type not in enum_values(ConnectorAuthType):
        raise ConnectorCatalogError(f"connector.auth.type is unsupported: {auth_type!r}", code="unsupported_connector_auth")
    raw_scopes = auth.get("required_scopes", [])
    scopes = string_list(raw_scopes, "connector.auth.required_scopes", allow_empty=True)
    if auth_type == ConnectorAuthType.OAUTH_USER_SCOPE.value and not scopes:
        raise ConnectorCatalogError("oauth_user_scope connectors must declare required scopes.", code="missing_connector_auth_scopes")
    if auth_type == ConnectorAuthType.NONE_FOR_STUB.value and protocol != ConnectorProtocol.LOCAL_STUB.value:
        raise ConnectorCatalogError("none_for_stub auth is allowed only for local_stub connectors.", code="unsafe_connector_auth")
    return {"type": auth_type, "required_scopes": scopes}


def validate_safety_policy(connector: dict[str, Any]) -> dict[str, Any]:
    safety = require_object(connector.get("safety"), "connector.safety")
    data_classification = safety.get("data_classification")
    pii_policy = safety.get("pii_policy")
    if data_classification not in enum_values(ConnectorDataClassification):
        raise ConnectorCatalogError(
            f"connector.safety.data_classification is unsupported: {data_classification!r}",
            code="unsupported_connector_data_classification",
        )
    if pii_policy not in enum_values(ConnectorPiiPolicy):
        raise ConnectorCatalogError(
            f"connector.safety.pii_policy is unsupported: {pii_policy!r}",
            code="unsupported_connector_pii_policy",
        )
    if data_classification == ConnectorDataClassification.SENSITIVE.value and pii_policy == ConnectorPiiPolicy.NOT_ALLOWED.value:
        raise ConnectorCatalogError("sensitive connectors must not use pii_policy=not_allowed.", code="unsafe_connector_pii_policy")
    if safety.get("raw_mcp_allowed") is True:
        raise ConnectorCatalogError("raw MCP access is not allowed.", code="raw_mcp_bypass_not_allowed")
    if safety.get("direct_model_tool_access") is True:
        raise ConnectorCatalogError("direct model-to-connector tool access is not allowed.", code="direct_model_tool_bypass_not_allowed")
    return {
        "data_classification": data_classification,
        "pii_policy": pii_policy,
        "external_network": bool(safety.get("external_network", False)),
    }


def validate_operation(
    raw_operation: Any,
    *,
    connector_auth_type: str,
    connector_required_scopes: list[str],
    workflows: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    operation = require_object(raw_operation, "connector.operations[]")
    required = {
        "id",
        "description",
        "operation_class",
        "approval_required",
        "input_schema",
        "output_schema",
        "allowed_workflows",
        "eval_fixtures",
    }
    missing = sorted(required - set(operation))
    if missing:
        raise ConnectorCatalogError(
            f"connector operation is missing field(s): {', '.join(missing)}",
            code="invalid_connector_operation",
        )
    operation_id = operation["id"]
    if not isinstance(operation_id, str) or not OPERATION_ID_PATTERN.fullmatch(operation_id):
        raise ConnectorCatalogError("connector operation id must be snake_case and start with a letter.", code="invalid_connector_operation_id")
    if not isinstance(operation["description"], str) or len(operation["description"].strip()) < 12:
        raise ConnectorCatalogError("connector operation description must be descriptive.", code="invalid_connector_operation")
    operation_class = operation["operation_class"]
    if operation_class not in enum_values(ConnectorOperationClass):
        raise ConnectorCatalogError(f"connector operation_class is unsupported: {operation_class!r}", code="unsupported_connector_operation_class")
    approval_required = operation["approval_required"]
    if not isinstance(approval_required, bool):
        raise ConnectorCatalogError("connector operation approval_required must be boolean.", code="invalid_connector_operation")
    if operation_class == ConnectorOperationClass.WRITE.value and approval_required is not True:
        raise ConnectorCatalogError("write connector operations must require approval.", code="unsafe_connector_write_operation")
    if connector_auth_type == ConnectorAuthType.SERVICE_READ_ONLY.value and operation_class == ConnectorOperationClass.WRITE.value:
        raise ConnectorCatalogError("service_read_only connectors cannot expose write operations.", code="unsafe_connector_auth")
    if "required_scopes" in operation:
        operation_required_scopes = string_list(operation["required_scopes"], "connector.operation.required_scopes")
        if connector_auth_type != ConnectorAuthType.OAUTH_USER_SCOPE.value:
            raise ConnectorCatalogError(
                "operation-level required_scopes are allowed only for oauth_user_scope connectors.",
                code="unsafe_connector_auth",
            )
        undeclared_scopes = sorted(set(operation_required_scopes) - set(connector_required_scopes))
        if undeclared_scopes:
            raise ConnectorCatalogError(
                f"connector operation required_scopes must be declared by connector.auth.required_scopes: {', '.join(undeclared_scopes)}",
                code="invalid_connector_operation_scope",
            )
    else:
        operation_required_scopes = connector_required_scopes
    validate_json_schema_object(operation["input_schema"], "connector.operation.input_schema")
    validate_json_schema_object(operation["output_schema"], "connector.operation.output_schema")
    allowed_workflows = string_list(operation["allowed_workflows"], "connector.operation.allowed_workflows")
    eval_fixtures = string_list(operation["eval_fixtures"], "connector.operation.eval_fixtures")
    for workflow_id in allowed_workflows:
        if workflow_id not in workflows:
            raise ConnectorCatalogError(f"Unknown workflow in connector operation allowed_workflows: {workflow_id}", code="unknown_workflow")
    return {
        "id": operation_id,
        "description": operation["description"],
        "operation_class": operation_class,
        "approval_required": approval_required,
        "required_scopes": operation_required_scopes,
        "input_schema": operation["input_schema"],
        "output_schema": operation["output_schema"],
        "allowed_workflows": allowed_workflows,
        "eval_fixtures": eval_fixtures,
    }


def validate_connector_shape(raw_connector: Any, config_root: Path) -> dict[str, Any]:
    connector = require_object(raw_connector, "connector")
    required = {
        "id",
        "owner",
        "description",
        "protocol",
        "mediation",
        "auth",
        "safety",
        "operations",
    }
    missing = sorted(required - set(connector))
    if missing:
        raise ConnectorCatalogError(f"connector is missing field(s): {', '.join(missing)}", code="invalid_connector_manifest")
    connector_id = connector["id"]
    if not isinstance(connector_id, str) or not CONNECTOR_ID_PATTERN.fullmatch(connector_id):
        raise ConnectorCatalogError("connector.id must be snake_case and start with a letter.", code="invalid_connector_id")
    if not isinstance(connector["owner"], str) or not connector["owner"].strip():
        raise ConnectorCatalogError("connector.owner must be a non-empty string.", code="invalid_connector_manifest")
    if not isinstance(connector["description"], str) or len(connector["description"].strip()) < 20:
        raise ConnectorCatalogError("connector.description must be descriptive.", code="invalid_connector_manifest")
    protocol = connector["protocol"]
    if protocol not in enum_values(ConnectorProtocol):
        raise ConnectorCatalogError(f"connector.protocol is unsupported: {protocol!r}", code="unsupported_connector_protocol")
    mediation = connector["mediation"]
    if mediation != ConnectorMediation.CONTROLLER_OWNED.value:
        raise ConnectorCatalogError("connector.mediation must be controller_owned.", code="unsafe_connector_mediation")
    auth = validate_auth_policy(connector, protocol)
    safety = validate_safety_policy(connector)
    raw_operations = connector.get("operations")
    if not isinstance(raw_operations, list) or not raw_operations:
        raise ConnectorCatalogError("connector.operations must be a non-empty list.", code="invalid_connector_manifest")
    workflows = workflows_by_id(config_root)
    operations = [
        validate_operation(
            item,
            connector_auth_type=auth["type"],
            connector_required_scopes=auth["required_scopes"],
            workflows=workflows,
        )
        for item in raw_operations
    ]
    operation_ids = [item["id"] for item in operations]
    duplicate_operation_ids = sorted({item for item in operation_ids if operation_ids.count(item) > 1})
    if duplicate_operation_ids:
        raise ConnectorCatalogError(
            f"Duplicate connector operation id(s): {', '.join(duplicate_operation_ids)}",
            code="duplicate_connector_operation_id",
        )
    return {
        "id": connector_id,
        "owner": connector["owner"],
        "description": connector["description"],
        "protocol": protocol,
        "mediation": mediation,
        "auth": auth,
        "safety": safety,
        "operations": operations,
    }


def validate_connector_admission_manifest(manifest: dict[str, Any], config_root: Path) -> dict[str, Any]:
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ConnectorCatalogError("connector admission schema_version must be 1.", code="unsupported_schema_version")
    if manifest.get("kind") != "connector_admission_manifest":
        raise ConnectorCatalogError("connector admission kind must be connector_admission_manifest.", code="invalid_connector_manifest")
    connector = validate_connector_shape(manifest.get("connector"), config_root)
    existing_connectors = runtime_connectors_by_id(config_root)
    connector_id = connector["id"]
    if connector_id in existing_connectors:
        raise ConnectorCatalogError(
            f"Connector already exists in runtime/connectors.json: {connector_id}",
            code="connector_already_registered",
        )
    operation_checks = [
        {
            "connector_id": connector_id,
            "operation_id": operation["id"],
            "operation_class": operation["operation_class"],
            "approval_required": operation["approval_required"],
            "workflow_count": len(operation["allowed_workflows"]),
            "eval_fixture_count": len(operation["eval_fixtures"]),
            "status": "passed",
        }
        for operation in connector["operations"]
    ]
    return {
        "status": "passed",
        "schema_version": SCHEMA_VERSION,
        "connector": connector,
        "connector_id": connector_id,
        "operation_checks": operation_checks,
        "runtime_behavior_changed": False,
        "runtime_registry_changed": False,
        "target_repository_changed": False,
        "next_action": "review_then_register_connector_catalog_entry",
    }


def runtime_connector_entry(connector: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": connector["id"],
        "owner": connector["owner"],
        "description": connector["description"],
        "protocol": connector["protocol"],
        "mediation": connector["mediation"],
        "auth": connector["auth"],
        "safety": connector["safety"],
        "operations": connector["operations"],
        "enabled": False,
    }


def build_connector_catalog_validation_report(
    config_root: Path,
    manifest: dict[str, Any],
    *,
    output_path: Path | None = None,
) -> dict[str, Any]:
    report = {
        "kind": "connector_catalog_validation_report",
        "schema_version": SCHEMA_VERSION,
        "status": "failed",
        "connector_id": None,
        "summary": {
            "validation_status": "failed",
            "runtime_registry_changed": False,
            "runtime_behavior_changed": False,
            "target_repository_changed": False,
        },
        "errors": [],
        "checks": [],
        "created_at": utc_now(),
    }
    try:
        validation = validate_connector_admission_manifest(manifest, config_root)
        report["status"] = "passed"
        report["connector_id"] = validation["connector_id"]
        report["summary"] = {
            "validation_status": "passed",
            "connector_id": validation["connector_id"],
            "operation_count": len(validation["operation_checks"]),
            "runtime_registry_changed": False,
            "runtime_behavior_changed": False,
            "target_repository_changed": False,
            "next_action": validation["next_action"],
        }
        report["checks"] = validation["operation_checks"]
        report["validation"] = validation
    except ConnectorCatalogError as exc:
        report["errors"].append({"code": exc.code, "message": str(exc)})
        report["summary"]["error_count"] = len(report["errors"])
    if output_path is not None:
        write_json(output_path, report)
        report["report_path"] = str(output_path.resolve())
        write_json(output_path, report)
    return report


__all__ = [
    "CONNECTOR_CATALOG_PATH",
    "SCHEMA_VERSION",
    "ConnectorCatalogError",
    "artifact_timestamp",
    "build_connector_catalog_validation_report",
    "read_json_object",
    "runtime_connector_entry",
    "runtime_connectors_by_id",
    "utc_now",
    "write_json",
]
