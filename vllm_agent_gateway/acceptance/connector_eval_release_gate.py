"""Connector eval and release gate validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vllm_agent_gateway.connectors.catalog import utc_now, write_json


POLICY_PATH = Path("runtime") / "connector_eval_release_gate_policy.json"
SCHEMA_VERSION = 1


class ConnectorEvalReleaseGateError(RuntimeError):
    pass


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConnectorEvalReleaseGateError(f"Missing {label}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConnectorEvalReleaseGateError(f"Invalid {label} JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ConnectorEvalReleaseGateError(f"{label} must be a JSON object.")
    return value


def string_items(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def object_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def sample_connector_release_packet() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "connector_release_packet",
        "connector_id": "ticketing_stub",
        "connector_enabled_requested": True,
        "natural_workflow_exposed": False,
        "connector_validation": {
            "status": "passed",
            "connector_id": "ticketing_stub",
            "operation_ids": ["lookup_ticket"],
        },
        "operation_evals": [
            {
                "operation_id": "lookup_ticket",
                "prompt_cases": ["ticketing_stub.lookup_ticket.target", "ticketing_stub.lookup_ticket.format_json"],
                "holdouts": ["ticketing_stub.lookup_ticket.holdout"],
                "blind_baseline": {
                    "status": "passed",
                    "collected_before_local_output": True,
                    "must_have_count": 3,
                },
                "negative_controls": [
                    {"id": "raw_mcp_bypass", "status": "passed"},
                    {"id": "direct_model_tool_bypass", "status": "passed"},
                    {"id": "unknown_connector_or_operation", "status": "passed"},
                ],
                "local_stack_results": [
                    {"surface": "controller", "status": "passed"},
                ],
                "findings": [],
            }
        ],
        "release_decision": {
            "decision": "ship",
            "blockers": [],
            "advisories": [],
            "approval_refs": ["phase283-sample"],
        },
    }


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append({"code": "unsupported_schema_version", "message": "policy schema_version must be 1"})
    if policy.get("kind") != "connector_eval_release_gate_policy":
        errors.append({"code": "invalid_policy_kind", "message": "policy kind must be connector_eval_release_gate_policy"})
    if not string_items(policy.get("required_negative_controls")):
        errors.append({"code": "missing_required_negative_controls", "message": "policy requires negative controls"})
    if not string_items(policy.get("allowed_release_decisions")):
        errors.append({"code": "missing_release_decisions", "message": "policy requires release decisions"})
    return errors


def failed(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def validate_operation_eval(
    operation_eval: dict[str, Any],
    *,
    policy: dict[str, Any],
    natural_workflow_exposed: bool,
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    operation_id = operation_eval.get("operation_id")
    if not isinstance(operation_id, str) or not operation_id:
        errors.append(failed("missing_operation_id", "operation eval requires operation_id"))
        operation_id = "<missing>"
    prompt_cases = string_items(operation_eval.get("prompt_cases"))
    holdouts = string_items(operation_eval.get("holdouts"))
    if len(prompt_cases) < int(policy.get("minimum_prompt_cases_per_operation", 2)):
        errors.append(failed("missing_prompt_coverage", f"{operation_id} requires more prompt cases"))
    if len(holdouts) < int(policy.get("minimum_holdouts_per_operation", 1)):
        errors.append(failed("missing_holdout_coverage", f"{operation_id} requires holdout coverage"))
    blind_baseline = operation_eval.get("blind_baseline")
    if not isinstance(blind_baseline, dict) or blind_baseline.get("status") != "passed":
        errors.append(failed("missing_blind_baseline", f"{operation_id} requires a passing blind baseline"))
    elif blind_baseline.get("collected_before_local_output") is not True:
        errors.append(failed("late_blind_baseline", f"{operation_id} blind baseline must be collected before local output"))
    negative_controls = object_items(operation_eval.get("negative_controls"))
    passed_controls = {item.get("id") for item in negative_controls if item.get("status") == "passed"}
    missing_controls = sorted(set(string_items(policy.get("required_negative_controls"))) - {str(item) for item in passed_controls})
    if missing_controls:
        errors.append(failed("missing_negative_controls", f"{operation_id} missing negative controls: {', '.join(missing_controls)}"))
    local_stack_results = object_items(operation_eval.get("local_stack_results"))
    passed_surfaces = {item.get("surface") for item in local_stack_results if item.get("status") == "passed"}
    required_controller_surface = policy.get("required_controller_surface", "controller")
    if required_controller_surface not in passed_surfaces:
        errors.append(failed("missing_controller_surface", f"{operation_id} requires controller surface proof"))
    if natural_workflow_exposed:
        missing_surfaces = sorted(set(string_items(policy.get("natural_workflow_required_surfaces"))) - {str(item) for item in passed_surfaces})
        if missing_surfaces:
            errors.append(failed("missing_natural_workflow_surfaces", f"{operation_id} missing surfaces: {', '.join(missing_surfaces)}"))
    blocking_findings = [
        item
        for item in object_items(operation_eval.get("findings"))
        if item.get("severity") in {"critical", "high"} and item.get("status") != "rejected"
    ]
    if blocking_findings:
        errors.append(failed("blocking_connector_eval_finding", f"{operation_id} has unresolved critical/high findings"))
    return errors


def validate_release_packet(packet: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    errors = validate_policy(policy)
    if packet.get("schema_version") != SCHEMA_VERSION:
        errors.append(failed("unsupported_schema_version", "packet schema_version must be 1"))
    if packet.get("kind") != "connector_release_packet":
        errors.append(failed("invalid_packet_kind", "packet kind must be connector_release_packet"))
    connector_id = packet.get("connector_id")
    if not isinstance(connector_id, str) or not connector_id:
        errors.append(failed("missing_connector_id", "packet requires connector_id"))
        connector_id = "<missing>"
    connector_validation = packet.get("connector_validation")
    if not isinstance(connector_validation, dict) or connector_validation.get("status") != "passed":
        errors.append(failed("missing_connector_validation", "connector release requires passing connector validation"))
        operation_ids: list[str] = []
    else:
        if connector_validation.get("connector_id") != connector_id:
            errors.append(failed("connector_validation_mismatch", "connector validation connector_id must match packet connector_id"))
        operation_ids = string_items(connector_validation.get("operation_ids"))
        if not operation_ids:
            errors.append(failed("missing_connector_operations", "connector validation must include operation_ids"))
    operation_evals = object_items(packet.get("operation_evals"))
    evals_by_operation = {item.get("operation_id"): item for item in operation_evals if isinstance(item.get("operation_id"), str)}
    for operation_id in operation_ids:
        operation_eval = evals_by_operation.get(operation_id)
        if operation_eval is None:
            errors.append(failed("missing_operation_eval", f"missing eval for operation {operation_id}"))
            continue
        errors.extend(
            validate_operation_eval(
                operation_eval,
                policy=policy,
                natural_workflow_exposed=packet.get("natural_workflow_exposed") is True,
            )
        )
    release_decision = packet.get("release_decision")
    if not isinstance(release_decision, dict):
        errors.append(failed("missing_release_decision", "packet requires release_decision"))
        decision = None
        blockers = []
    else:
        decision = release_decision.get("decision")
        blockers = object_items(release_decision.get("blockers"))
        if decision not in set(string_items(policy.get("allowed_release_decisions"))):
            errors.append(failed("invalid_release_decision", "release decision is not allowed"))
    if policy.get("ship_requires_zero_blockers") is True and decision == "ship" and blockers:
        errors.append(failed("ship_with_blockers", "ship decision cannot include blockers"))
    if policy.get("enabled_requires_ship") is True and packet.get("connector_enabled_requested") is True and decision != "ship":
        errors.append(failed("enabled_without_ship_decision", "connector enablement requires ship decision"))
    status = "failed" if errors else "passed"
    return {
        "kind": "connector_eval_release_gate_report",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "summary": {
            "validation_status": status,
            "connector_id": connector_id,
            "operation_count": len(operation_ids),
            "operation_eval_count": len(operation_evals),
            "connector_enabled_requested": packet.get("connector_enabled_requested") is True,
            "natural_workflow_exposed": packet.get("natural_workflow_exposed") is True,
            "release_decision": decision,
            "error_count": len(errors),
            "phase284_ready": status == "passed",
        },
        "errors": errors,
        "created_at": utc_now(),
    }


def run_connector_eval_release_gate(
    *,
    config_root: Path,
    packet_path: Path | None = None,
    output_path: Path,
) -> dict[str, Any]:
    policy = read_json_object(config_root / POLICY_PATH, "connector eval release gate policy")
    packet = read_json_object(packet_path, "connector release packet") if packet_path is not None else sample_connector_release_packet()
    report = validate_release_packet(packet, policy)
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    if report["status"] != "passed":
        raise ConnectorEvalReleaseGateError(f"connector eval release gate failed with {len(report['errors'])} error(s)")
    return report
