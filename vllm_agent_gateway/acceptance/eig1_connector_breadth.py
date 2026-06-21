"""EIG-1 connector archetype breadth validation."""

from __future__ import annotations

import copy
import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.connectors.catalog import (
    CONNECTOR_CATALOG_PATH,
    ConnectorCatalogError,
    ConnectorMediation,
    ConnectorOperationClass,
    ConnectorProtocol,
    validate_connector_admission_manifest,
    write_json,
)
from vllm_agent_gateway.connectors.identity import validate_actor_context
from vllm_agent_gateway.connectors.mediator import ConnectorMediationError, mediate_connector_operation


SCHEMA_VERSION = 1
DEFAULT_FIXTURE_PATH = Path("runtime") / "eig1_connector_breadth_fixtures.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "eig1-connector-breadth"


class EIG1ConnectorArchetype(str, Enum):
    WORK_TRACKING = "work_tracking"
    KNOWLEDGE_LOOKUP = "knowledge_lookup"
    BUSINESS_RECORD = "business_record"


class EIG1NegativeScenario(str, Enum):
    UNKNOWN_CONNECTOR = "unknown_connector"
    DISABLED_CONNECTOR = "disabled_connector"
    UNKNOWN_OPERATION = "unknown_operation"
    UNSUPPORTED_ARGUMENT = "unsupported_argument"
    MISSING_REQUIRED_ARGUMENT = "missing_required_argument"
    WRITE_WITHOUT_APPROVAL = "write_without_approval"
    WRITE_NON_DRY_RUN = "write_non_dry_run"
    NON_LOCAL_STUB_RUNTIME = "non_local_stub_runtime"
    RAW_MCP_ALLOWED_MANIFEST = "raw_mcp_allowed_manifest"
    DIRECT_MODEL_TOOL_ACCESS_MANIFEST = "direct_model_tool_access_manifest"


REQUIRED_ARCHETYPES = {item.value for item in EIG1ConnectorArchetype}
REQUIRED_NEGATIVE_SCENARIOS = {item.value for item in EIG1NegativeScenario}


@dataclass(frozen=True)
class EIG1ConnectorBreadthConfig:
    config_root: Path
    fixture_path: Path = DEFAULT_FIXTURE_PATH
    output_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"eig1-connector-breadth-{utc_timestamp()}.json"


def resolve_path(config_root: Path, raw_path: Path | str) -> Path:
    path = raw_path if isinstance(raw_path, Path) else Path(raw_path)
    return path if path.is_absolute() else config_root / path


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object at {path}")
    return value


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def object_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def validation_error(error_id: str, message: str, *, item_id: str | None = None) -> dict[str, str]:
    error = {"id": error_id, "message": message}
    if item_id:
        error["item_id"] = item_id
    return error


def connector_id_from_manifest_entry(entry: dict[str, Any]) -> str:
    manifest = entry.get("manifest")
    if not isinstance(manifest, dict):
        return "<missing>"
    connector = manifest.get("connector")
    if not isinstance(connector, dict):
        return "<missing>"
    connector_id = connector.get("id")
    return connector_id if isinstance(connector_id, str) else "<missing>"


def validate_fixture_pack_shape(pack: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if pack.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("pack.schema_version", "schema_version must be 1"))
    if pack.get("kind") != "eig1_connector_breadth_fixtures":
        errors.append(validation_error("pack.kind", "kind must be eig1_connector_breadth_fixtures"))
    boundary = pack.get("scope_boundary")
    if not isinstance(boundary, dict):
        errors.append(validation_error("pack.scope_boundary", "scope_boundary must be an object"))
    else:
        if boundary.get("execution") != "local_stub_only":
            errors.append(validation_error("pack.scope_boundary.execution", "execution must be local_stub_only"))
        if boundary.get("mediation") != ConnectorMediation.CONTROLLER_OWNED.value:
            errors.append(validation_error("pack.scope_boundary.mediation", "mediation must be controller_owned"))
        for key in (
            "external_network_allowed",
            "raw_mcp_allowed",
            "direct_model_tool_access_allowed",
            "runtime_registry_mutation_allowed",
            "target_repository_mutation_allowed",
        ):
            if boundary.get(key) is not False:
                errors.append(validation_error(f"pack.scope_boundary.{key}", f"{key} must be false"))
    manifest_entries = object_list(pack.get("connector_manifests"))
    archetypes = {entry.get("archetype") for entry in manifest_entries if isinstance(entry.get("archetype"), str)}
    missing_archetypes = sorted(REQUIRED_ARCHETYPES - archetypes)
    if missing_archetypes:
        errors.append(validation_error("pack.connector_manifests.archetypes", f"missing archetypes: {', '.join(missing_archetypes)}"))
    if len(manifest_entries) < 3:
        errors.append(validation_error("pack.connector_manifests.count", "at least three connector manifests are required"))
    positive_cases = object_list(pack.get("positive_invocation_cases"))
    if len(positive_cases) < 5:
        errors.append(validation_error("pack.positive_invocation_cases.count", "at least five positive invocation cases are required"))
    negative_controls = object_list(pack.get("negative_controls"))
    scenarios = {item.get("scenario") for item in negative_controls if isinstance(item.get("scenario"), str)}
    missing_scenarios = sorted(REQUIRED_NEGATIVE_SCENARIOS - scenarios)
    if missing_scenarios:
        errors.append(validation_error("pack.negative_controls.scenarios", f"missing negative scenarios: {', '.join(missing_scenarios)}"))
    holdouts = object_list(pack.get("holdout_cases"))
    holdout_archetypes = {item.get("archetype") for item in holdouts if isinstance(item.get("archetype"), str)}
    missing_holdouts = sorted(REQUIRED_ARCHETYPES - holdout_archetypes)
    if missing_holdouts:
        errors.append(validation_error("pack.holdout_cases.archetypes", f"missing holdouts for: {', '.join(missing_holdouts)}"))
    if not object_list(pack.get("deferred_items")):
        errors.append(validation_error("pack.deferred_items", "at least one deferred item is required"))
    return errors


def validate_manifest_entries(
    *,
    config_root: Path,
    manifest_entries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    reports: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    connector_ids: list[str] = []
    read_operation_count = 0
    write_operation_count = 0
    for entry in manifest_entries:
        archetype = entry.get("archetype")
        connector_id = connector_id_from_manifest_entry(entry)
        item_errors: list[dict[str, str]] = []
        if archetype not in REQUIRED_ARCHETYPES:
            item_errors.append(validation_error("manifest.archetype", "manifest archetype is not supported", item_id=connector_id))
        manifest = entry.get("manifest")
        if not isinstance(manifest, dict):
            item_errors.append(validation_error("manifest.shape", "manifest must be a JSON object", item_id=connector_id))
            errors.extend(item_errors)
            reports.append({"connector_id": connector_id, "archetype": archetype, "status": "failed", "errors": item_errors})
            continue
        try:
            validation = validate_connector_admission_manifest(manifest, config_root)
            connector = validation["connector"]
            connector_ids.append(connector["id"])
            operation_classes = [operation["operation_class"] for operation in connector["operations"]]
            read_operation_count += operation_classes.count(ConnectorOperationClass.READ.value)
            write_operation_count += operation_classes.count(ConnectorOperationClass.WRITE.value)
            fixture_count = sum(len(operation["eval_fixtures"]) for operation in connector["operations"])
            for operation in connector["operations"]:
                if not operation["eval_fixtures"]:
                    item_errors.append(validation_error("manifest.operation.eval_fixtures", "operation requires eval fixtures", item_id=connector["id"]))
                if operation["operation_class"] == ConnectorOperationClass.WRITE.value and operation["approval_required"] is not True:
                    item_errors.append(validation_error("manifest.operation.write_approval", "write operation must require approval", item_id=connector["id"]))
            status = "failed" if item_errors else "passed"
            reports.append(
                {
                    "connector_id": connector["id"],
                    "archetype": archetype,
                    "status": status,
                    "protocol": connector["protocol"],
                    "auth_type": connector["auth"]["type"],
                    "operation_count": len(connector["operations"]),
                    "operation_classes": sorted(set(operation_classes)),
                    "eval_fixture_count": fixture_count,
                }
            )
        except ConnectorCatalogError as exc:
            item_errors.append(validation_error(exc.code, str(exc), item_id=connector_id))
            reports.append({"connector_id": connector_id, "archetype": archetype, "status": "failed", "errors": item_errors})
        errors.extend(item_errors)
    duplicate_ids = sorted({connector_id for connector_id in connector_ids if connector_ids.count(connector_id) > 1})
    if duplicate_ids:
        errors.append(validation_error("manifest.connector_id.duplicate", f"duplicate connector ids: {', '.join(duplicate_ids)}"))
    if read_operation_count < 3:
        errors.append(validation_error("manifest.read_operation_count", "at least one read operation per archetype is required"))
    if write_operation_count < 1:
        errors.append(validation_error("manifest.write_operation_count", "at least one write-class dry-run operation is required"))
    return reports, errors


def actor_context(*, scopes: list[str], actor_id: str = "eig1-tester", request_id: str = "request-eig1") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "actor_id": actor_id,
        "auth_subject": f"local-subject:{actor_id}",
        "session_id": "session-eig1",
        "request_id": request_id,
        "granted_scopes": scopes,
        "issued_at_utc": "2026-01-01T00:00:00Z",
        "expires_at_utc": "2999-01-01T00:00:00Z",
    }


def approval_for_case(case: dict[str, Any], validated_actor: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "approved_for_connector_invocation",
        "scope": "connector_invocation",
        "connector_id": case["connector_id"],
        "operation_id": case["operation_id"],
        "actor_id": validated_actor["actor_id"],
        "session_id": validated_actor["session_id"],
        "request_id": validated_actor["request_id"],
        "granted_scopes": validated_actor["granted_scopes"],
        "approval_refs": [f"{case['id']}-approval"],
    }


def copy_runtime_root(config_root: Path) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="eig1-connector-breadth-"))
    shutil.copytree(config_root / "runtime", temp_dir / "runtime")
    return temp_dir


def install_runtime_connectors(runtime_root: Path, manifest_entries: list[dict[str, Any]], *, enabled: bool = True) -> None:
    connectors = []
    for entry in manifest_entries:
        manifest = entry["manifest"]
        connector = copy.deepcopy(manifest["connector"])
        connector["enabled"] = enabled
        connectors.append(connector)
    write_json(runtime_root / CONNECTOR_CATALOG_PATH, {"schema_version": SCHEMA_VERSION, "connectors": connectors})


def clean_runtime_root(runtime_root: Path) -> None:
    shutil.rmtree(runtime_root, ignore_errors=True)


def invoke_case(runtime_root: Path, case: dict[str, Any]) -> dict[str, Any]:
    validated_actor = validate_actor_context(actor_context(scopes=string_list(case.get("granted_scopes")), request_id=case["id"]))
    approval = approval_for_case(case, validated_actor) if case.get("approval_required") is True else None
    return mediate_connector_operation(
        config_root=runtime_root,
        connector_id=case["connector_id"],
        operation_id=case["operation_id"],
        arguments=case["arguments"],
        dry_run=case.get("dry_run") is True,
        actor_context=validated_actor,
        approval=approval,
    )


def validate_positive_cases(
    *,
    config_root: Path,
    manifest_entries: list[dict[str, Any]],
    cases: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    runtime_root = copy_runtime_root(config_root)
    reports: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    try:
        install_runtime_connectors(runtime_root, manifest_entries, enabled=True)
        for case in cases:
            case_id = str(case.get("id") or "unknown")
            try:
                result = invoke_case(runtime_root, case)
                audit = result["audit"]
                expected_class = case.get("expected_operation_class")
                case_errors = []
                if result["operation_class"] != expected_class:
                    case_errors.append(validation_error("positive_case.operation_class", "operation class did not match expectation", item_id=case_id))
                for key, expected in (
                    ("controller_owned_path", True),
                    ("raw_mcp_used", False),
                    ("direct_model_tool_access_used", False),
                    ("external_network_called", False),
                    ("runtime_registry_changed", False),
                    ("target_repository_changed", False),
                    ("raw_arguments_stored", False),
                ):
                    source = audit if key in audit else audit.get("input", {})
                    if source.get(key) is not expected:
                        case_errors.append(validation_error(f"positive_case.audit.{key}", f"audit {key} must be {expected}", item_id=case_id))
                status = "failed" if case_errors else "passed"
                reports.append(
                    {
                        "case_id": case_id,
                        "archetype": case.get("archetype"),
                        "connector_id": result["connector_id"],
                        "operation_id": result["operation_id"],
                        "operation_class": result["operation_class"],
                        "status": status,
                        "audit": {
                            "decision": audit["decision"],
                            "authorization_status": audit["authorization_status"],
                            "approval_state": audit["approval_state"],
                            "argument_keys": audit["input"]["argument_keys"],
                            "raw_arguments_stored": audit["input"]["raw_arguments_stored"],
                            "raw_auth_subject_stored": audit["raw_auth_subject_stored"],
                            "external_network_called": audit["external_network_called"],
                            "runtime_registry_changed": audit["runtime_registry_changed"],
                            "target_repository_changed": audit["target_repository_changed"],
                        },
                    }
                )
                errors.extend(case_errors)
            except (ConnectorMediationError, ConnectorCatalogError, KeyError, TypeError) as exc:
                errors.append(validation_error("positive_case.failed", f"{type(exc).__name__}: {exc}", item_id=case_id))
                reports.append({"case_id": case_id, "archetype": case.get("archetype"), "status": "failed"})
    finally:
        clean_runtime_root(runtime_root)
    return reports, errors


def expected_control_error(
    *,
    config_root: Path,
    manifest_entries: list[dict[str, Any]],
    scenario: str,
) -> str:
    runtime_root = copy_runtime_root(config_root)
    try:
        install_runtime_connectors(runtime_root, manifest_entries, enabled=True)
        base_case = {
            "id": f"negative-{scenario}",
            "connector_id": "work_tracking_stub",
            "operation_id": "lookup_work_item",
            "arguments": {"work_item_id": "WORK-SYN-1042"},
            "dry_run": True,
            "granted_scopes": ["work:read", "work:write"],
        }
        if scenario == EIG1NegativeScenario.UNKNOWN_CONNECTOR.value:
            base_case["connector_id"] = "missing_connector_stub"
        elif scenario == EIG1NegativeScenario.DISABLED_CONNECTOR.value:
            install_runtime_connectors(runtime_root, manifest_entries, enabled=False)
        elif scenario == EIG1NegativeScenario.UNKNOWN_OPERATION.value:
            base_case["operation_id"] = "missing_operation"
        elif scenario == EIG1NegativeScenario.UNSUPPORTED_ARGUMENT.value:
            base_case["arguments"] = {"work_item_id": "WORK-SYN-1042", "extra": "not-supported"}
        elif scenario == EIG1NegativeScenario.MISSING_REQUIRED_ARGUMENT.value:
            base_case["arguments"] = {"include_history": True}
        elif scenario == EIG1NegativeScenario.WRITE_WITHOUT_APPROVAL.value:
            base_case.update(
                {
                    "operation_id": "dry_run_update_work_item",
                    "arguments": {
                        "work_item_id": "WORK-SYN-1042",
                        "new_status": "review_ready",
                        "comment": "Synthetic dry-run update.",
                    },
                    "approval_required": False,
                }
            )
        elif scenario == EIG1NegativeScenario.WRITE_NON_DRY_RUN.value:
            base_case.update(
                {
                    "operation_id": "dry_run_update_work_item",
                    "arguments": {
                        "work_item_id": "WORK-SYN-1042",
                        "new_status": "review_ready",
                        "comment": "Synthetic dry-run update.",
                    },
                    "approval_required": True,
                    "dry_run": False,
                }
            )
        elif scenario == EIG1NegativeScenario.NON_LOCAL_STUB_RUNTIME.value:
            mutated_entries = copy.deepcopy(manifest_entries)
            mutated_entries[1]["manifest"]["connector"]["protocol"] = ConnectorProtocol.HTTPS_JSON.value
            install_runtime_connectors(runtime_root, mutated_entries, enabled=True)
            base_case.update(
                {
                    "connector_id": "knowledge_lookup_stub",
                    "operation_id": "search_documents",
                    "arguments": {"query": "synthetic runbook"},
                    "granted_scopes": [],
                }
            )
        else:
            raise AssertionError(f"scenario must be handled by manifest validation: {scenario}")
        invoke_case(runtime_root, base_case)
    except ConnectorMediationError as exc:
        return exc.code
    finally:
        clean_runtime_root(runtime_root)
    return "no_error"


def manifest_control_error(
    *,
    config_root: Path,
    manifest_entries: list[dict[str, Any]],
    scenario: str,
) -> str:
    mutated_manifest = copy.deepcopy(manifest_entries[0]["manifest"])
    safety = mutated_manifest["connector"]["safety"]
    if scenario == EIG1NegativeScenario.RAW_MCP_ALLOWED_MANIFEST.value:
        safety["raw_mcp_allowed"] = True
    elif scenario == EIG1NegativeScenario.DIRECT_MODEL_TOOL_ACCESS_MANIFEST.value:
        safety["direct_model_tool_access"] = True
    else:
        raise AssertionError(f"unsupported manifest control scenario: {scenario}")
    try:
        validate_connector_admission_manifest(mutated_manifest, config_root)
    except ConnectorCatalogError as exc:
        return exc.code
    return "no_error"


def validate_negative_controls(
    *,
    config_root: Path,
    manifest_entries: list[dict[str, Any]],
    controls: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    reports: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for control in controls:
        control_id = str(control.get("id") or "unknown")
        scenario = control.get("scenario")
        expected_error = control.get("expected_error_code")
        if scenario in {
            EIG1NegativeScenario.RAW_MCP_ALLOWED_MANIFEST.value,
            EIG1NegativeScenario.DIRECT_MODEL_TOOL_ACCESS_MANIFEST.value,
        }:
            actual_error = manifest_control_error(config_root=config_root, manifest_entries=manifest_entries, scenario=str(scenario))
        else:
            actual_error = expected_control_error(config_root=config_root, manifest_entries=manifest_entries, scenario=str(scenario))
        status = "passed" if actual_error == expected_error else "failed"
        if status != "passed":
            errors.append(
                validation_error(
                    "negative_control.error_code",
                    f"expected {expected_error}, got {actual_error}",
                    item_id=control_id,
                )
            )
        reports.append(
            {
                "control_id": control_id,
                "scenario": scenario,
                "status": status,
                "expected_error_code": expected_error,
                "actual_error_code": actual_error,
            }
        )
    return reports, errors


def report_contains_raw_fixture_arguments(report: dict[str, Any]) -> bool:
    serialized = json.dumps(report, ensure_ascii=True, sort_keys=True)
    raw_values = [
        "WORK-SYN-1042",
        "DOC-SYN-1",
        "BR-SYN-001",
        "synthetic runbook",
        "Synthetic dry-run update.",
    ]
    return any(value in serialized for value in raw_values)


def run_eig1_connector_breadth_validation(config: EIG1ConnectorBreadthConfig) -> dict[str, Any]:
    config_root = config.config_root
    fixture_path = resolve_path(config_root, config.fixture_path)
    output_path = resolve_path(config_root, config.output_path) if config.output_path else default_report_path(config_root)
    pack = read_json_object(fixture_path)
    shape_errors = validate_fixture_pack_shape(pack)
    manifest_entries = object_list(pack.get("connector_manifests"))
    positive_cases = object_list(pack.get("positive_invocation_cases"))
    negative_controls = object_list(pack.get("negative_controls"))
    manifest_reports, manifest_errors = validate_manifest_entries(config_root=config_root, manifest_entries=manifest_entries)
    positive_reports, positive_errors = validate_positive_cases(
        config_root=config_root,
        manifest_entries=manifest_entries,
        cases=positive_cases,
    )
    negative_reports, negative_errors = validate_negative_controls(
        config_root=config_root,
        manifest_entries=manifest_entries,
        controls=negative_controls,
    )
    validation_errors = shape_errors + manifest_errors + positive_errors + negative_errors
    status = "failed" if validation_errors else "passed"
    archetypes = {entry.get("archetype") for entry in manifest_entries if isinstance(entry.get("archetype"), str)}
    read_operation_count = sum(
        1
        for report in manifest_reports
        for operation_class in report.get("operation_classes", [])
        if operation_class == ConnectorOperationClass.READ.value
    )
    write_operation_count = sum(
        1
        for report in manifest_reports
        for operation_class in report.get("operation_classes", [])
        if operation_class == ConnectorOperationClass.WRITE.value
    )
    report: dict[str, Any] = {
        "kind": "eig1_connector_breadth_report",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "fixture_path": str(fixture_path),
        "summary": {
            "connector_manifest_count": len(manifest_entries),
            "archetype_count": len(archetypes),
            "read_archetype_count": sum(
                1 for report_item in manifest_reports if ConnectorOperationClass.READ.value in report_item.get("operation_classes", [])
            ),
            "write_connector_count": sum(
                1 for report_item in manifest_reports if ConnectorOperationClass.WRITE.value in report_item.get("operation_classes", [])
            ),
            "read_operation_class_covered": read_operation_count >= 3,
            "write_operation_class_covered": write_operation_count >= 1,
            "positive_invocation_count": len(positive_reports),
            "negative_control_count": len(negative_reports),
            "holdout_count": len(object_list(pack.get("holdout_cases"))),
            "deferred_item_count": len(object_list(pack.get("deferred_items"))),
            "validation_error_count": len(validation_errors),
            "runtime_registry_changed": False,
            "target_repository_changed": False,
            "external_network_called": False,
            "raw_mcp_used": False,
            "direct_model_tool_access_used": False,
            "phase290_ready": status == "passed",
        },
        "manifest_reports": manifest_reports,
        "positive_invocation_reports": positive_reports,
        "negative_control_reports": negative_reports,
        "validation_errors": validation_errors,
        "created_at": utc_timestamp(),
    }
    report["summary"]["raw_fixture_arguments_retained_in_report"] = report_contains_raw_fixture_arguments(report)
    if report["summary"]["raw_fixture_arguments_retained_in_report"]:
        report["status"] = "failed"
        report["summary"]["phase290_ready"] = False
        report["validation_errors"].append(
            validation_error("report.raw_fixture_arguments", "report must not retain raw fixture argument values")
        )
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
