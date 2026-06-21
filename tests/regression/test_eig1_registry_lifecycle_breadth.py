from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.eig1_registry_lifecycle_breadth import (
    DEFAULT_POLICY_PATH,
    EIG1RegistryLifecycleBreadthConfig,
    run_eig1_registry_lifecycle_breadth,
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
    return run_eig1_registry_lifecycle_breadth(
        EIG1RegistryLifecycleBreadthConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            output_path=tmp_path / "report.json",
        )
    )


def error_ids(report: dict[str, object]) -> set[str]:
    errors = report["validation_errors"]
    assert isinstance(errors, list)
    return {str(item["id"]) for item in errors if isinstance(item, dict)}


def scenario(report: dict[str, object], connector_id: str, scenario_id: str) -> dict[str, object]:
    scenarios = report["scenario_reports"]
    assert isinstance(scenarios, list)
    for item in scenarios:
        assert isinstance(item, dict)
        if item.get("connector_id") == connector_id and item.get("scenario") == scenario_id:
            return item
    raise AssertionError(f"missing scenario {connector_id}.{scenario_id}")


def test_eig1_registry_lifecycle_breadth_passes(tmp_path: Path) -> None:
    report = run_eig1_registry_lifecycle_breadth(
        EIG1RegistryLifecycleBreadthConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "report.json",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["connector_count"] == 3
    assert report["summary"]["connector_ids"] == [
        "business_record_stub",
        "knowledge_lookup_stub",
        "work_tracking_stub",
    ]
    assert report["summary"]["scenario_count"] == 18
    assert report["summary"]["scenario_count_per_connector"] == {
        "business_record_stub": 6,
        "knowledge_lookup_stub": 6,
        "work_tracking_stub": 6,
    }
    assert report["summary"]["uses_disposable_runtime_copy"] is True
    assert report["summary"]["real_runtime_registry_changed"] is False
    assert report["summary"]["tools_workflows_roles_changed"] is False
    assert report["summary"]["target_repository_changed"] is False
    assert report["summary"]["future_gap_documented"] is True
    assert report["summary"]["phase296_ready"] is True
    for connector_id in report["summary"]["connector_ids"]:
        assert scenario(report, connector_id, "draft_registration")["changed_runtime_files"] == ["runtime/connectors.json"]
        assert scenario(report, connector_id, "enabled_registration")["release_gate_passed"] is True
        assert scenario(report, connector_id, "disabled_invocation_denial")["error_code"] == "connector_not_enabled"
        assert scenario(report, connector_id, "duplicate_registration_rejection")["changed_runtime_files"] == []
        assert scenario(report, connector_id, "stale_validation_rejection")["error_code"] == "connector_release_gate_stale_validation"
        assert scenario(report, connector_id, "release_gate_mismatch_rejection")["error_code"] == "connector_release_gate_mismatch"


def test_eig1_registry_lifecycle_rejects_missing_required_scenario(tmp_path: Path) -> None:
    policy = policy_pack()
    mutated = copy.deepcopy(policy)
    scenarios = mutated["required_scenarios"]
    assert isinstance(scenarios, list)
    mutated["required_scenarios"] = [item for item in scenarios if item != "stale_validation_rejection"]

    report = run_with_policy(tmp_path, mutated)

    assert report["status"] == "failed"
    assert "policy.required_scenarios" in error_ids(report)


def test_eig1_registry_lifecycle_rejects_missing_future_gap(tmp_path: Path) -> None:
    policy = policy_pack()
    mutated = copy.deepcopy(policy)
    mutated["documented_future_gap"] = {}

    report = run_with_policy(tmp_path, mutated)

    assert report["status"] == "failed"
    assert "policy.documented_future_gap" in error_ids(report)


def test_eig1_registry_lifecycle_rejects_real_runtime_mutation_policy(tmp_path: Path) -> None:
    policy = policy_pack()
    mutated = copy.deepcopy(policy)
    boundary = mutated["scope_boundary"]
    assert isinstance(boundary, dict)
    boundary["real_runtime_registry_mutation_allowed"] = True

    report = run_with_policy(tmp_path, mutated)

    assert report["status"] == "failed"
    assert "policy.scope_boundary.real_runtime_registry_mutation_allowed" in error_ids(report)
