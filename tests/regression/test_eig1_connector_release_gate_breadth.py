from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.eig1_connector_release_gate_breadth import (
    DEFAULT_POLICY_PATH,
    EIG1ConnectorReleaseGateBreadthConfig,
    run_eig1_connector_release_gate_breadth,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def policy_pack() -> dict[str, object]:
    return json.loads((REPO_ROOT / DEFAULT_POLICY_PATH).read_text(encoding="utf-8"))


def run_with_policy(tmp_path: Path, policy: dict[str, object]) -> dict[str, object]:
    policy_path = write_json(tmp_path / "policy.json", policy)
    return run_eig1_connector_release_gate_breadth(
        EIG1ConnectorReleaseGateBreadthConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            output_path=tmp_path / "report.json",
        )
    )


def error_ids(report: dict[str, object]) -> set[str]:
    errors = report["validation_errors"]
    assert isinstance(errors, list)
    return {str(item["id"]) for item in errors if isinstance(item, dict)}


def failure_report(report: dict[str, object], failure_id: str) -> dict[str, object]:
    failures = report["failure_class_reports"]
    assert isinstance(failures, list)
    for item in failures:
        assert isinstance(item, dict)
        if item.get("failure_id") == failure_id:
            return item
    raise AssertionError(f"missing failure {failure_id}")


def test_eig1_connector_release_gate_breadth_passes(tmp_path: Path) -> None:
    report = run_eig1_connector_release_gate_breadth(
        EIG1ConnectorReleaseGateBreadthConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "report.json",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["ship_packet_count"] == 3
    assert report["summary"]["failure_class_count"] == 6
    assert report["summary"]["runtime_registry_changed"] is False
    assert report["summary"]["target_repository_changed"] is False
    assert report["summary"]["real_external_connector_execution"] is False
    assert report["summary"]["phase292_ready"] is True
    assert failure_report(report, "late_blind_baseline")["actual_error_codes"] == ["late_blind_baseline"]
    assert all(item["natural_workflow_exposed"] is False for item in report["ship_packet_reports"])


def test_eig1_connector_release_gate_breadth_rejects_missing_failure_class(tmp_path: Path) -> None:
    policy = policy_pack()
    mutated = copy.deepcopy(policy)
    failures = mutated["required_failure_classes"]
    assert isinstance(failures, list)
    mutated["required_failure_classes"] = [
        item for item in failures if not (isinstance(item, dict) and item.get("id") == "missing_holdout")
    ]

    report = run_with_policy(tmp_path, mutated)

    assert report["status"] == "failed"
    assert "policy.required_failure_classes" in error_ids(report)


def test_eig1_connector_release_gate_breadth_rejects_wrong_expected_error(tmp_path: Path) -> None:
    policy = policy_pack()
    mutated = copy.deepcopy(policy)
    failures = mutated["required_failure_classes"]
    assert isinstance(failures, list)
    for item in failures:
        if isinstance(item, dict) and item.get("id") == "enablement_without_ship":
            item["expected_error_code"] = "missing_connector_validation"

    report = run_with_policy(tmp_path, mutated)

    assert report["status"] == "failed"
    assert "failure_class.expected_error" in error_ids(report)


def test_eig1_connector_release_gate_breadth_rejects_natural_workflow_exposure(tmp_path: Path) -> None:
    policy = policy_pack()
    mutated = copy.deepcopy(policy)
    mutated["natural_workflow_exposed"] = True

    report = run_with_policy(tmp_path, mutated)

    assert report["status"] == "failed"
    assert "policy.natural_workflow_exposed" in error_ids(report)
