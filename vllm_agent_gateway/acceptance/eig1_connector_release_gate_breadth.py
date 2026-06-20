"""EIG-1 connector release-gate breadth validation."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.connector_eval_release_gate import read_json_object as read_policy_json
from vllm_agent_gateway.acceptance.connector_eval_release_gate import validate_release_packet
from vllm_agent_gateway.acceptance.eig1_connector_breadth import object_list, read_json_object, validation_error
from vllm_agent_gateway.connectors.catalog import write_json


SCHEMA_VERSION = 1
DEFAULT_POLICY_PATH = Path("runtime") / "eig1_connector_release_gate_breadth_policy.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "eig1-connector-release-gate-breadth"


@dataclass(frozen=True)
class EIG1ConnectorReleaseGateBreadthConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"eig1-connector-release-gate-breadth-{utc_timestamp()}.json"


def resolve_path(config_root: Path, raw_path: Path | str) -> Path:
    path = raw_path if isinstance(raw_path, Path) else Path(raw_path)
    return path if path.is_absolute() else config_root / path


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def error_codes(report: dict[str, Any]) -> set[str]:
    return {str(item.get("code")) for item in object_list(report.get("errors"))}


def validate_policy_shape(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != "eig1_connector_release_gate_breadth_policy":
        errors.append(validation_error("policy.kind", "kind must be eig1_connector_release_gate_breadth_policy"))
    if policy.get("natural_workflow_exposed") is not False:
        errors.append(validation_error("policy.natural_workflow_exposed", "Phase 291 breadth fixtures must not be exposed to natural workflows"))
    boundary = policy.get("scope_boundary")
    if not isinstance(boundary, dict):
        errors.append(validation_error("policy.scope_boundary", "scope_boundary must be an object"))
    else:
        for key in (
            "real_external_connector_execution",
            "runtime_registry_mutation_allowed",
            "target_repository_mutation_allowed",
            "natural_language_exposure_required",
        ):
            if boundary.get(key) is not False:
                errors.append(validation_error(f"policy.scope_boundary.{key}", f"{key} must be false"))
    failure_ids = {item.get("id") for item in object_list(policy.get("required_failure_classes"))}
    required_failures = {
        "missing_validation",
        "late_blind_baseline",
        "missing_holdout",
        "missing_negative_control",
        "unresolved_high_finding",
        "enablement_without_ship",
    }
    missing = sorted(required_failures - failure_ids)
    if missing:
        errors.append(validation_error("policy.required_failure_classes", f"missing failure classes: {', '.join(missing)}"))
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


def operation_eval(connector_id: str, operation: dict[str, Any], release_policy: dict[str, Any]) -> dict[str, Any]:
    operation_id = operation["id"]
    required_negative_controls = string_list(release_policy.get("required_negative_controls"))
    return {
        "operation_id": operation_id,
        "prompt_cases": [
            f"connector_eval.{connector_id}.{operation_id}.target",
            f"connector_eval.{connector_id}.{operation_id}.format_json",
        ],
        "holdouts": [
            f"connector_eval.{connector_id}.{operation_id}.holdout",
        ],
        "blind_baseline": {
            "status": "passed",
            "collected_before_local_output": True,
            "must_have_count": 3,
        },
        "negative_controls": [{"id": control_id, "status": "passed"} for control_id in required_negative_controls],
        "local_stack_results": [
            {"surface": "controller", "status": "passed"},
        ],
        "findings": [],
    }


def release_packet_for_connector(entry: dict[str, Any], release_policy: dict[str, Any]) -> dict[str, Any]:
    manifest = entry["manifest"]
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
            "approval_refs": [f"phase291-{connector_id}"],
        },
    }


def mutate_failure_packet(packet: dict[str, Any], failure_id: str) -> dict[str, Any]:
    mutated = copy.deepcopy(packet)
    first_eval = mutated["operation_evals"][0]
    if failure_id == "missing_validation":
        mutated["connector_validation"]["status"] = "failed"
    elif failure_id == "late_blind_baseline":
        first_eval["blind_baseline"]["collected_before_local_output"] = False
    elif failure_id == "missing_holdout":
        first_eval["holdouts"] = []
    elif failure_id == "missing_negative_control":
        first_eval["negative_controls"] = first_eval["negative_controls"][:1]
    elif failure_id == "unresolved_high_finding":
        first_eval["findings"] = [{"severity": "high", "status": "accepted"}]
    elif failure_id == "enablement_without_ship":
        mutated["release_decision"]["decision"] = "hold"
    else:
        raise RuntimeError(f"unsupported failure class: {failure_id}")
    return mutated


def validate_ship_packets(
    *,
    entries: list[dict[str, Any]],
    release_policy: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, Any]]]:
    packet_summaries: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    packets: list[dict[str, Any]] = []
    for entry in entries:
        connector_id = entry["manifest"]["connector"]["id"]
        packet = release_packet_for_connector(entry, release_policy)
        packets.append(packet)
        report = validate_release_packet(packet, release_policy)
        operation_count = len(packet["connector_validation"]["operation_ids"])
        eval_count = len(packet["operation_evals"])
        status = "passed" if report["status"] == "passed" and operation_count == eval_count else "failed"
        if status != "passed":
            errors.append(validation_error("ship_packet.validation", "ship packet did not pass release gate", item_id=connector_id))
        packet_summaries.append(
            {
                "connector_id": connector_id,
                "status": status,
                "operation_count": operation_count,
                "operation_eval_count": eval_count,
                "natural_workflow_exposed": packet["natural_workflow_exposed"],
                "release_decision": packet["release_decision"]["decision"],
                "error_codes": sorted(error_codes(report)),
            }
        )
    return packet_summaries, errors, packets


def validate_failure_classes(
    *,
    base_packet: dict[str, Any],
    release_policy: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    reports: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for failure in object_list(policy.get("required_failure_classes")):
        failure_id = str(failure.get("id") or "unknown")
        expected_error = str(failure.get("expected_error_code") or "")
        mutated = mutate_failure_packet(base_packet, failure_id)
        report = validate_release_packet(mutated, release_policy)
        codes = error_codes(report)
        status = "passed" if report["status"] == "failed" and expected_error in codes else "failed"
        if status != "passed":
            errors.append(
                validation_error(
                    "failure_class.expected_error",
                    f"expected {expected_error}, got {', '.join(sorted(codes)) or 'no_error'}",
                    item_id=failure_id,
                )
            )
        reports.append(
            {
                "failure_id": failure_id,
                "status": status,
                "expected_error_code": expected_error,
                "actual_error_codes": sorted(codes),
            }
        )
    return reports, errors


def run_eig1_connector_release_gate_breadth(config: EIG1ConnectorReleaseGateBreadthConfig) -> dict[str, Any]:
    config_root = config.config_root
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path) if config.output_path else default_report_path(config_root)
    policy = read_json_object(policy_path)
    policy_errors = validate_policy_shape(policy)
    pack = fixture_pack(config_root, policy)
    release_policy = release_gate_policy(config_root, policy)
    entries = object_list(pack.get("connector_manifests"))
    ship_reports, ship_errors, packets = validate_ship_packets(entries=entries, release_policy=release_policy)
    failure_reports, failure_errors = validate_failure_classes(base_packet=packets[0], release_policy=release_policy, policy=policy) if packets else ([], [])
    validation_errors = policy_errors + ship_errors + failure_errors
    expected_connector_count = int(policy.get("expected_connector_count", 0))
    if len(ship_reports) != expected_connector_count:
        validation_errors.append(
            validation_error("ship_packet.connector_count", f"expected {expected_connector_count}, got {len(ship_reports)}")
        )
    status = "failed" if validation_errors else "passed"
    report: dict[str, Any] = {
        "kind": "eig1_connector_release_gate_breadth_report",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "policy_path": str(policy_path),
        "summary": {
            "ship_packet_count": len(ship_reports),
            "failure_class_count": len(failure_reports),
            "validation_error_count": len(validation_errors),
            "natural_workflow_exposed": False,
            "runtime_registry_changed": False,
            "target_repository_changed": False,
            "real_external_connector_execution": False,
            "phase292_ready": status == "passed",
        },
        "ship_packet_reports": ship_reports,
        "failure_class_reports": failure_reports,
        "validation_errors": validation_errors,
        "created_at": utc_timestamp(),
    }
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
