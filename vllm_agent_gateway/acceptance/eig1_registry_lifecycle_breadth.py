"""EIG-1 registry lifecycle breadth validation."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.eig1_connector_breadth import (
    actor_context,
    clean_runtime_root,
    copy_runtime_root,
    object_list,
    read_json_object,
    validation_error,
)
from vllm_agent_gateway.acceptance.eig1_connector_release_gate_breadth import operation_eval
from vllm_agent_gateway.acceptance.connector_eval_release_gate import read_json_object as read_policy_json
from vllm_agent_gateway.acceptance.connector_eval_release_gate import validate_release_packet
from vllm_agent_gateway.connectors.identity import validate_actor_context
from vllm_agent_gateway.connectors.mediator import ConnectorMediationError, mediate_connector_operation
from vllm_agent_gateway.controllers.connector_catalog.register import (
    ConnectorCatalogRegistrationError,
    ConnectorCatalogRegistrationRequest,
    invoke_connector_catalog_registration,
    runtime_hashes,
)
from vllm_agent_gateway.connectors.catalog import write_json


SCHEMA_VERSION = 1
DEFAULT_POLICY_PATH = Path("runtime") / "eig1_registry_lifecycle_breadth_policy.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "eig1-registry-lifecycle-breadth"


@dataclass(frozen=True)
class EIG1RegistryLifecycleBreadthConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"eig1-registry-lifecycle-breadth-{utc_timestamp()}.json"


def resolve_path(config_root: Path, raw_path: Path | str) -> Path:
    path = raw_path if isinstance(raw_path, Path) else Path(raw_path)
    return path if path.is_absolute() else config_root / path


def validate_policy_shape(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != "eig1_registry_lifecycle_breadth_policy":
        errors.append(validation_error("policy.kind", "kind must be eig1_registry_lifecycle_breadth_policy"))
    required = {
        "draft_registration",
        "enabled_registration",
        "disabled_invocation_denial",
        "duplicate_registration_rejection",
        "stale_validation_rejection",
        "release_gate_mismatch_rejection",
    }
    scenarios = set(item for item in policy.get("required_scenarios", []) if isinstance(item, str))
    missing = sorted(required - scenarios)
    if missing:
        errors.append(validation_error("policy.required_scenarios", f"missing lifecycle scenarios: {', '.join(missing)}"))
    boundary = policy.get("scope_boundary")
    if not isinstance(boundary, dict):
        errors.append(validation_error("policy.scope_boundary", "scope_boundary must be an object"))
    else:
        if boundary.get("uses_disposable_runtime_copy") is not True:
            errors.append(validation_error("policy.scope_boundary.uses_disposable_runtime_copy", "disposable runtime copy is required"))
        for key in (
            "real_runtime_registry_mutation_allowed",
            "tools_workflows_roles_mutation_allowed",
            "target_repository_mutation_allowed",
            "external_service_mutation_allowed",
        ):
            if boundary.get(key) is not False:
                errors.append(validation_error(f"policy.scope_boundary.{key}", f"{key} must be false"))
    gap = policy.get("documented_future_gap")
    if not isinstance(gap, dict) or gap.get("status") != "deferred_future_milestone_candidate":
        errors.append(validation_error("policy.documented_future_gap", "update/deprecation gap must be explicitly deferred"))
    return errors


def fixture_pack(config_root: Path, policy: dict[str, Any]) -> dict[str, Any]:
    raw_path = policy.get("fixture_pack")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise RuntimeError("policy.fixture_pack must be a non-empty path")
    return read_json_object(resolve_path(config_root, raw_path))


def release_gate_policy(config_root: Path, policy: dict[str, Any]) -> dict[str, Any]:
    raw_path = policy.get("release_gate_policy")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise RuntimeError("policy.release_gate_policy must be a non-empty path")
    return read_policy_json(resolve_path(config_root, raw_path), "connector eval release gate policy")


def registration_approval(*, enabled: bool) -> dict[str, Any]:
    scope = ["connector_catalog_registration"]
    if enabled:
        scope.append("connector_enablement")
    return {
        "status": "approved_for_connector_catalog_registration",
        "scope": scope,
        "runtime_connector_append": True,
        "enabled": enabled,
        "approval_refs": [f"eig1-phase292-enabled-{str(enabled).lower()}"],
    }


def release_packet(manifest: dict[str, Any], release_policy: dict[str, Any]) -> dict[str, Any]:
    connector = manifest["connector"]
    connector_id = connector["id"]
    operation_ids = [operation["id"] for operation in connector["operations"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "connector_release_packet",
        "connector_id": connector_id,
        "connector_enabled_requested": True,
        "natural_workflow_exposed": False,
        "connector_validation": {
            "status": "passed",
            "connector_id": connector_id,
            "operation_ids": operation_ids,
        },
        "operation_evals": [operation_eval(connector_id, operation, release_policy) for operation in connector["operations"]],
        "release_decision": {
            "decision": "ship",
            "blockers": [],
            "advisories": [],
            "approval_refs": [f"phase292-{connector_id}"],
        },
    }


def write_release_gate_report(output_root: Path, manifest: dict[str, Any], release_policy: dict[str, Any], *, connector_id_override: str | None = None, stale: bool = False) -> Path:
    packet = release_packet(manifest, release_policy)
    if connector_id_override:
        packet["connector_id"] = connector_id_override
        packet["connector_validation"]["connector_id"] = connector_id_override
    report = validate_release_packet(packet, release_policy)
    if stale:
        report["summary"]["operation_ids"] = ["stale_operation"]
    report_path = output_root / "release-gates" / f"{packet['connector_id']}-{utc_timestamp()}.json"
    write_json(report_path, report)
    return report_path


def invoke_registration(
    *,
    runtime_root: Path,
    output_root: Path,
    manifest: dict[str, Any],
    enabled: bool,
    release_gate_report_path: Path | None = None,
) -> tuple[str, dict[str, Any] | str]:
    try:
        result = invoke_connector_catalog_registration(
            ConnectorCatalogRegistrationRequest(
                config_root=runtime_root,
                output_root=output_root,
                connector_manifest=manifest,
                release_gate_report_path=str(release_gate_report_path) if release_gate_report_path else None,
                approval=registration_approval(enabled=enabled),
            )
        )
        report = result.report if isinstance(result.report, dict) else {}
        return "completed", {
            "summary": report.get("summary") if isinstance(report.get("summary"), dict) else {},
            "artifacts": result.artifact_paths,
        }
    except ConnectorCatalogRegistrationError as exc:
        return "failed", exc.code


def changed_files(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(key for key, value in after.items() if before.get(key) != value)


def sample_value_for_schema(property_schema: dict[str, Any]) -> Any:
    expected_type = property_schema.get("type")
    if expected_type == "string":
        return "synthetic"
    if expected_type == "boolean":
        return True
    if expected_type == "integer":
        return 1
    if expected_type == "array":
        return ["synthetic"]
    if expected_type == "object":
        return {"synthetic": True}
    return "synthetic"


def sample_arguments_for_operation(operation: dict[str, Any]) -> dict[str, Any]:
    schema = operation.get("input_schema") if isinstance(operation.get("input_schema"), dict) else {}
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    required = [item for item in schema.get("required", []) if isinstance(item, str)]
    return {
        name: sample_value_for_schema(properties.get(name, {}))
        for name in required
    }


def lifecycle_scenarios(
    *,
    config_root: Path,
    manifest: dict[str, Any],
    release_policy: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    reports: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    connector_id = manifest.get("connector", {}).get("id", "<missing>") if isinstance(manifest.get("connector"), dict) else "<missing>"

    def add_report(report: dict[str, Any], expected_status: str, expected_code: str | None = None) -> None:
        report["connector_id"] = connector_id
        status_ok = report.get("status") == expected_status
        code_ok = expected_code is None or report.get("error_code") == expected_code
        scenario = str(report.get("scenario"))
        changed = report.get("changed_runtime_files")
        if scenario in {"draft_registration", "enabled_registration"}:
            if changed != ["runtime/connectors.json"]:
                errors.append(
                    validation_error(
                        "scenario.hash_delta",
                        "successful registration must change only runtime/connectors.json",
                        item_id=scenario,
                    )
                )
            if report.get("rollback_instructions_present") is not True:
                errors.append(validation_error("scenario.rollback", "successful registration must provide rollback instructions", item_id=scenario))
        elif isinstance(changed, list) and changed:
            errors.append(validation_error("scenario.hash_delta", "rejection scenario must not mutate runtime files", item_id=scenario))
        if not status_ok or not code_ok:
            errors.append(
                validation_error(
                    "scenario.result",
                    f"expected status={expected_status} code={expected_code}, got status={report.get('status')} code={report.get('error_code')}",
                    item_id=scenario,
                )
            )
        reports.append(report)

    runtime_root = copy_runtime_root(config_root)
    try:
        output_root = runtime_root / "controller-output"
        before = runtime_hashes(runtime_root)
        status, payload = invoke_registration(runtime_root=runtime_root, output_root=output_root, manifest=manifest, enabled=False)
        after = runtime_hashes(runtime_root)
        summary = payload["summary"] if isinstance(payload, dict) else {}
        add_report(
            {
                "scenario": "draft_registration",
                "status": status,
                "error_code": None if isinstance(payload, dict) else payload,
                "enabled": summary.get("enabled"),
                "changed_runtime_files": changed_files(before, after),
                "rollback_instructions_present": isinstance(payload, dict) and "rollback_instructions" in payload.get("artifacts", {}),
                "target_repository_changed": summary.get("target_repository_changed"),
            },
            "completed",
        )
        connector = manifest["connector"]
        auth = connector.get("auth") if isinstance(connector.get("auth"), dict) else {}
        operation = connector["operations"][0]
        validated_actor = validate_actor_context(actor_context(scopes=[item for item in auth.get("required_scopes", []) if isinstance(item, str)]))
        try:
            mediate_connector_operation(
                config_root=runtime_root,
                connector_id=connector["id"],
                operation_id=operation["id"],
                arguments=sample_arguments_for_operation(operation),
                dry_run=True,
                actor_context=validated_actor,
            )
            denial_code = "no_error"
        except ConnectorMediationError as exc:
            denial_code = exc.code
        add_report(
            {
                "scenario": "disabled_invocation_denial",
                "status": "failed" if denial_code != "no_error" else "completed",
                "error_code": denial_code,
                "changed_runtime_files": [],
            },
            "failed",
            "connector_not_enabled",
        )
        before_duplicate = runtime_hashes(runtime_root)
        duplicate_status, duplicate_payload = invoke_registration(runtime_root=runtime_root, output_root=output_root, manifest=manifest, enabled=False)
        after_duplicate = runtime_hashes(runtime_root)
        add_report(
            {
                "scenario": "duplicate_registration_rejection",
                "status": duplicate_status,
                "error_code": duplicate_payload if isinstance(duplicate_payload, str) else None,
                "changed_runtime_files": changed_files(before_duplicate, after_duplicate),
            },
            "failed",
            "connector_already_registered",
        )
    finally:
        clean_runtime_root(runtime_root)

    runtime_root = copy_runtime_root(config_root)
    try:
        output_root = runtime_root / "controller-output"
        release_report = write_release_gate_report(output_root, manifest, release_policy)
        before = runtime_hashes(runtime_root)
        status, payload = invoke_registration(
            runtime_root=runtime_root,
            output_root=output_root,
            manifest=manifest,
            enabled=True,
            release_gate_report_path=release_report,
        )
        after = runtime_hashes(runtime_root)
        summary = payload["summary"] if isinstance(payload, dict) else {}
        add_report(
            {
                "scenario": "enabled_registration",
                "status": status,
                "error_code": None if isinstance(payload, dict) else payload,
                "enabled": summary.get("enabled"),
                "release_gate_passed": summary.get("release_gate_passed"),
                "changed_runtime_files": changed_files(before, after),
                "rollback_instructions_present": isinstance(payload, dict) and "rollback_instructions" in payload.get("artifacts", {}),
            },
            "completed",
        )
    finally:
        clean_runtime_root(runtime_root)

    runtime_root = copy_runtime_root(config_root)
    try:
        output_root = runtime_root / "controller-output"
        stale_report = write_release_gate_report(output_root, manifest, release_policy, stale=True)
        before = runtime_hashes(runtime_root)
        status, payload = invoke_registration(
            runtime_root=runtime_root,
            output_root=output_root,
            manifest=manifest,
            enabled=True,
            release_gate_report_path=stale_report,
        )
        after = runtime_hashes(runtime_root)
        add_report(
            {
                "scenario": "stale_validation_rejection",
                "status": status,
                "error_code": payload if isinstance(payload, str) else None,
                "changed_runtime_files": changed_files(before, after),
            },
            "failed",
            "connector_release_gate_stale_validation",
        )
    finally:
        clean_runtime_root(runtime_root)

    runtime_root = copy_runtime_root(config_root)
    try:
        output_root = runtime_root / "controller-output"
        mismatch_report = write_release_gate_report(output_root, manifest, release_policy, connector_id_override="other_connector_stub")
        before = runtime_hashes(runtime_root)
        status, payload = invoke_registration(
            runtime_root=runtime_root,
            output_root=output_root,
            manifest=manifest,
            enabled=True,
            release_gate_report_path=mismatch_report,
        )
        after = runtime_hashes(runtime_root)
        add_report(
            {
                "scenario": "release_gate_mismatch_rejection",
                "status": status,
                "error_code": payload if isinstance(payload, str) else None,
                "changed_runtime_files": changed_files(before, after),
            },
            "failed",
            "connector_release_gate_mismatch",
        )
    finally:
        clean_runtime_root(runtime_root)

    return reports, errors


def validate_connector_fixture_count(entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    connector_ids = [
        entry.get("manifest", {}).get("connector", {}).get("id")
        for entry in entries
        if isinstance(entry.get("manifest"), dict) and isinstance(entry.get("manifest", {}).get("connector"), dict)
    ]
    connector_ids = [item for item in connector_ids if isinstance(item, str)]
    errors: list[dict[str, str]] = []
    if len(connector_ids) < 3:
        errors.append(validation_error("fixture.connector_count", "registry lifecycle breadth requires at least three connector fixtures"))
    missing = sorted({"work_tracking_stub", "knowledge_lookup_stub", "business_record_stub"} - set(connector_ids))
    if missing:
        errors.append(validation_error("fixture.connector_ids", f"missing connector fixtures: {', '.join(missing)}"))
    return errors


def run_eig1_registry_lifecycle_breadth(config: EIG1RegistryLifecycleBreadthConfig) -> dict[str, Any]:
    config_root = config.config_root
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path) if config.output_path else default_report_path(config_root)
    policy = read_json_object(policy_path)
    policy_errors = validate_policy_shape(policy)
    pack = fixture_pack(config_root, policy)
    release_policy = release_gate_policy(config_root, policy)
    entries = object_list(pack.get("connector_manifests"))
    fixture_errors = validate_connector_fixture_count(entries)
    scenario_reports: list[dict[str, Any]] = []
    scenario_errors: list[dict[str, str]] = []
    for entry in entries:
        if not isinstance(entry.get("manifest"), dict):
            continue
        reports, errors = lifecycle_scenarios(
            config_root=config_root,
            manifest=copy.deepcopy(entry["manifest"]),
            release_policy=release_policy,
        )
        scenario_reports.extend(reports)
        scenario_errors.extend(errors)
    connector_ids = sorted(
        {
            item.get("connector_id")
            for item in scenario_reports
            if isinstance(item.get("connector_id"), str)
        }
    )
    validation_errors = policy_errors + fixture_errors + scenario_errors
    status = "failed" if validation_errors else "passed"
    report: dict[str, Any] = {
        "kind": "eig1_registry_lifecycle_breadth_report",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "policy_path": str(policy_path),
        "summary": {
            "connector_count": len(connector_ids),
            "connector_ids": connector_ids,
            "scenario_count": len(scenario_reports),
            "scenario_count_per_connector": {
                connector_id: sum(1 for item in scenario_reports if item.get("connector_id") == connector_id)
                for connector_id in connector_ids
            },
            "validation_error_count": len(validation_errors),
            "uses_disposable_runtime_copy": True,
            "real_runtime_registry_changed": False,
            "tools_workflows_roles_changed": False,
            "target_repository_changed": False,
            "future_gap_documented": isinstance(policy.get("documented_future_gap"), dict),
            "phase296_ready": status == "passed",
        },
        "scenario_reports": scenario_reports,
        "validation_errors": validation_errors,
        "documented_future_gap": policy.get("documented_future_gap"),
        "created_at": utc_timestamp(),
    }
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
