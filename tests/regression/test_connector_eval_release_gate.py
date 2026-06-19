from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from vllm_agent_gateway.acceptance.connector_eval_release_gate import (
    ConnectorEvalReleaseGateError,
    read_json_object,
    run_connector_eval_release_gate,
    sample_connector_release_packet,
    validate_release_packet,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY = read_json_object(REPO_ROOT / "runtime" / "connector_eval_release_gate_policy.json", "policy")


def error_codes(report: dict[str, object]) -> set[str]:
    errors = report.get("errors")
    assert isinstance(errors, list)
    return {item["code"] for item in errors if isinstance(item, dict)}


def test_connector_eval_release_gate_accepts_sample_packet(tmp_path: Path) -> None:
    report = run_connector_eval_release_gate(
        config_root=REPO_ROOT,
        output_path=tmp_path / "phase283-report.json",
    )

    assert report["status"] == "passed"
    assert report["summary"]["connector_id"] == "ticketing_stub"
    assert report["summary"]["operation_count"] == 1
    assert report["summary"]["connector_enabled_requested"] is True
    assert report["summary"]["release_decision"] == "ship"
    assert report["summary"]["phase284_ready"] is True


def test_connector_eval_release_gate_rejects_missing_connector_validation() -> None:
    packet = sample_connector_release_packet()
    packet["connector_validation"]["status"] = "failed"
    report = validate_release_packet(packet, POLICY)

    assert report["status"] == "failed"
    assert "missing_connector_validation" in error_codes(report)


def test_connector_eval_release_gate_rejects_late_blind_baseline() -> None:
    packet = sample_connector_release_packet()
    packet["operation_evals"][0]["blind_baseline"]["collected_before_local_output"] = False
    report = validate_release_packet(packet, POLICY)

    assert report["status"] == "failed"
    assert "late_blind_baseline" in error_codes(report)


def test_connector_eval_release_gate_rejects_missing_negative_control() -> None:
    packet = sample_connector_release_packet()
    packet["operation_evals"][0]["negative_controls"] = [
        {"id": "raw_mcp_bypass", "status": "passed"},
    ]
    report = validate_release_packet(packet, POLICY)

    assert report["status"] == "failed"
    assert "missing_negative_controls" in error_codes(report)


def test_connector_eval_release_gate_rejects_natural_workflow_without_gateway_and_anythingllm() -> None:
    packet = sample_connector_release_packet()
    packet["natural_workflow_exposed"] = True
    report = validate_release_packet(packet, POLICY)

    assert report["status"] == "failed"
    assert "missing_natural_workflow_surfaces" in error_codes(report)


def test_connector_eval_release_gate_accepts_natural_workflow_with_required_surfaces() -> None:
    packet = sample_connector_release_packet()
    packet["natural_workflow_exposed"] = True
    packet["operation_evals"][0]["local_stack_results"].extend(
        [
            {"surface": "workflow_router_gateway", "status": "passed"},
            {"surface": "anythingllm", "status": "passed"},
        ]
    )
    report = validate_release_packet(packet, POLICY)

    assert report["status"] == "passed"


def test_connector_eval_release_gate_rejects_enablement_without_ship() -> None:
    packet = sample_connector_release_packet()
    packet["release_decision"]["decision"] = "hold"
    report = validate_release_packet(packet, POLICY)

    assert report["status"] == "failed"
    assert "enabled_without_ship_decision" in error_codes(report)


def test_connector_eval_release_gate_rejects_unresolved_high_finding() -> None:
    packet = sample_connector_release_packet()
    packet["operation_evals"][0]["findings"] = [{"severity": "high", "status": "accepted"}]
    report = validate_release_packet(packet, POLICY)

    assert report["status"] == "failed"
    assert "blocking_connector_eval_finding" in error_codes(report)


def test_connector_eval_release_gate_cli_fails_for_bad_packet(tmp_path: Path) -> None:
    packet = copy.deepcopy(sample_connector_release_packet())
    packet["connector_enabled_requested"] = True
    packet["release_decision"]["decision"] = "repair_required"
    packet_path = tmp_path / "bad-packet.json"
    packet_path.write_text(json.dumps(packet, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ConnectorEvalReleaseGateError):
        run_connector_eval_release_gate(
            config_root=REPO_ROOT,
            packet_path=packet_path,
            output_path=tmp_path / "report.json",
        )
