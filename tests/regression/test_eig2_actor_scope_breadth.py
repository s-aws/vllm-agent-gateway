from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.eig2_actor_scope_breadth import (
    DEFAULT_POLICY_PATH,
    EIG2ActorScopeBreadthConfig,
    run_eig2_actor_scope_breadth_validation,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def policy_pack() -> dict[str, object]:
    return json.loads((REPO_ROOT / DEFAULT_POLICY_PATH).read_text(encoding="utf-8"))


def run_with_policy(tmp_path: Path, policy: dict[str, object]) -> dict[str, object]:
    policy_path = write_json(tmp_path / "eig2-policy.json", policy)
    return run_eig2_actor_scope_breadth_validation(
        EIG2ActorScopeBreadthConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            output_path=tmp_path / "report.json",
        )
    )


def error_ids(report: dict[str, object]) -> set[str]:
    errors = report["validation_errors"]
    assert isinstance(errors, list)
    return {str(item["id"]) for item in errors if isinstance(item, dict)}


def report_by_case(report: dict[str, object], section: str, case_id: str) -> dict[str, object]:
    values = report[section]
    assert isinstance(values, list)
    for value in values:
        assert isinstance(value, dict)
        if value.get("case_id") == case_id:
            return value
    raise AssertionError(f"missing case {case_id}")


def test_eig2_actor_scope_breadth_passes(tmp_path: Path) -> None:
    report = run_eig2_actor_scope_breadth_validation(
        EIG2ActorScopeBreadthConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "report.json",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["operation_scope_assignment_count"] == 4
    assert report["summary"]["actor_scope_case_count"] == 7
    assert report["summary"]["actor_context_negative_case_count"] == 4
    assert report["summary"]["read_without_write_allowed"] is True
    assert report["summary"]["write_without_read_allowed"] is True
    assert report["summary"]["cross_connector_scope_denied"] is True
    assert report["summary"]["scope_denials_have_recovery"] is True
    assert report["summary"]["runtime_registry_changed"] is False
    assert report["summary"]["target_repository_changed"] is False
    assert report["summary"]["real_oauth_provider_used"] is False
    assert report["summary"]["shared_privileged_service_account_used"] is False
    assert report["summary"]["raw_fixture_values_retained_in_report"] is False
    assert report["summary"]["phase294_ready"] is True

    read_case = report_by_case(report, "actor_scope_reports", "EIG2-WORK-READ-ALLOW")
    assert read_case["actual_status"] == "allowed"
    assert read_case["audit"]["required_scopes"] == ["work:read"]
    assert read_case["audit"]["granted_scopes"] == ["work:read"]

    write_case = report_by_case(report, "actor_scope_reports", "EIG2-WORK-WRITE-ALLOW")
    assert write_case["actual_status"] == "allowed"
    assert write_case["audit"]["required_scopes"] == ["work:write"]
    assert write_case["audit"]["granted_scopes"] == ["work:write"]

    denied_case = report_by_case(report, "actor_scope_reports", "EIG2-CROSS-CONNECTOR-DENY")
    assert denied_case["actual_error_code"] == "connector_scope_denied"
    assert denied_case["missing_scopes"] == ["work:read"]
    assert denied_case["recovery_present"] is True


def test_eig2_actor_scope_rejects_missing_scope_scenario(tmp_path: Path) -> None:
    policy = policy_pack()
    mutated = copy.deepcopy(policy)
    cases = mutated["actor_scope_cases"]
    assert isinstance(cases, list)
    mutated["actor_scope_cases"] = [
        item for item in cases if not (isinstance(item, dict) and item.get("scenario") == "missing_write_scope")
    ]

    report = run_with_policy(tmp_path, mutated)

    assert report["status"] == "failed"
    assert "policy.actor_scope_cases.scenarios" in error_ids(report)


def test_eig2_actor_scope_rejects_missing_operation_scope_assignment(tmp_path: Path) -> None:
    policy = policy_pack()
    mutated = copy.deepcopy(policy)
    assignments = mutated["operation_scope_assignments"]
    assert isinstance(assignments, list)
    mutated["operation_scope_assignments"] = [
        item
        for item in assignments
        if not (
            isinstance(item, dict)
            and item.get("connector_id") == "work_tracking_stub"
            and item.get("operation_id") == "lookup_work_item"
        )
    ]

    report = run_with_policy(tmp_path, mutated)

    assert report["status"] == "failed"
    assert "policy.operation_scope_assignments" in error_ids(report)


def test_eig2_actor_scope_rejects_undeclared_operation_scope(tmp_path: Path) -> None:
    policy = policy_pack()
    mutated = copy.deepcopy(policy)
    assignments = mutated["operation_scope_assignments"]
    assert isinstance(assignments, list)
    for item in assignments:
        if isinstance(item, dict) and item.get("connector_id") == "work_tracking_stub" and item.get("operation_id") == "lookup_work_item":
            item["required_scopes"] = ["admin:all"]

    report = run_with_policy(tmp_path, mutated)

    assert report["status"] == "failed"
    assert "invalid_connector_operation_scope" in error_ids(report)


def test_eig2_actor_scope_rejects_wrong_least_privilege_expectation(tmp_path: Path) -> None:
    policy = policy_pack()
    mutated = copy.deepcopy(policy)
    cases = mutated["actor_scope_cases"]
    assert isinstance(cases, list)
    for item in cases:
        if isinstance(item, dict) and item.get("id") == "EIG2-WORK-READ-ALLOW":
            item["expected_required_scopes"] = ["work:read", "work:write"]

    report = run_with_policy(tmp_path, mutated)

    assert report["status"] == "failed"
    assert "case.required_scopes" in error_ids(report)
