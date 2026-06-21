from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.eig2_approval_replay_breadth import (
    DEFAULT_POLICY_PATH,
    EIG2ApprovalReplayBreadthConfig,
    run_eig2_approval_replay_breadth_validation,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def policy_pack() -> dict[str, object]:
    return json.loads((REPO_ROOT / DEFAULT_POLICY_PATH).read_text(encoding="utf-8"))


def run_with_policy(tmp_path: Path, policy: dict[str, object]) -> dict[str, object]:
    policy_path = write_json(tmp_path / "eig2-approval-policy.json", policy)
    return run_eig2_approval_replay_breadth_validation(
        EIG2ApprovalReplayBreadthConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            output_path=tmp_path / "report.json",
        )
    )


def error_ids(report: dict[str, object]) -> set[str]:
    errors = report["validation_errors"]
    assert isinstance(errors, list)
    return {str(item["id"]) for item in errors if isinstance(item, dict)}


def report_by_case(report: dict[str, object], case_id: str) -> dict[str, object]:
    values = report["approval_replay_reports"]
    assert isinstance(values, list)
    for value in values:
        assert isinstance(value, dict)
        if value.get("case_id") == case_id:
            return value
    raise AssertionError(f"missing case {case_id}")


def test_eig2_approval_replay_breadth_passes(tmp_path: Path) -> None:
    report = run_eig2_approval_replay_breadth_validation(
        EIG2ApprovalReplayBreadthConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "report.json",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["approval_replay_case_count"] == 9
    assert report["summary"]["all_required_scenarios_passed"] is True
    assert report["summary"]["audit_validation_passed"] is True
    assert report["summary"]["wrong_actor_denied"] is True
    assert report["summary"]["wrong_session_denied"] is True
    assert report["summary"]["wrong_request_denied"] is True
    assert report["summary"]["wrong_connector_denied"] is True
    assert report["summary"]["wrong_operation_denied"] is True
    assert report["summary"]["scope_change_denied"] is True
    assert report["summary"]["non_dry_run_write_denied"] is True
    assert report["summary"]["runtime_registry_changed"] is False
    assert report["summary"]["target_repository_changed"] is False
    assert report["summary"]["raw_values_retained_in_report"] is False
    assert report["summary"]["phase295_ready"] is True

    allowed = report_by_case(report, "EIG2-APPROVAL-ALLOW")
    assert allowed["actual_report_status"] == "completed"
    assert allowed["audit"]["approval_state"] == "approved"
    assert allowed["audit"]["granted_scopes"] == ["work:write"]

    scope_change = report_by_case(report, "EIG2-APPROVAL-SCOPE-CHANGE")
    assert scope_change["actual_error_code"] == "stale_connector_invocation_approval"
    assert scope_change["audit"]["decision"] == "denied"
    assert scope_change["audit_validation_status"] == "passed"

    non_dry_run = report_by_case(report, "EIG2-APPROVAL-NON-DRY-RUN")
    assert non_dry_run["actual_error_code"] == "connector_write_execution_not_supported"
    assert non_dry_run["audit"]["authorization_status"] == "allowed"


def test_eig2_approval_replay_rejects_missing_required_scenario(tmp_path: Path) -> None:
    policy = policy_pack()
    mutated = copy.deepcopy(policy)
    cases = mutated["approval_replay_cases"]
    assert isinstance(cases, list)
    mutated["approval_replay_cases"] = [
        item for item in cases if not (isinstance(item, dict) and item.get("scenario") == "scope_change")
    ]

    report = run_with_policy(tmp_path, mutated)

    assert report["status"] == "failed"
    assert "policy.approval_replay_cases.scenarios" in error_ids(report)


def test_eig2_approval_replay_rejects_wrong_expected_error(tmp_path: Path) -> None:
    policy = policy_pack()
    mutated = copy.deepcopy(policy)
    cases = mutated["approval_replay_cases"]
    assert isinstance(cases, list)
    for item in cases:
        if isinstance(item, dict) and item.get("id") == "EIG2-APPROVAL-WRONG-ACTOR":
            item["expected_error_code"] = "allowed"

    report = run_with_policy(tmp_path, mutated)

    assert report["status"] == "failed"
    assert "case.expected_error_code" in error_ids(report)


def test_eig2_approval_replay_rejects_wrong_success_expectation(tmp_path: Path) -> None:
    policy = policy_pack()
    mutated = copy.deepcopy(policy)
    cases = mutated["approval_replay_cases"]
    assert isinstance(cases, list)
    for item in cases:
        if isinstance(item, dict) and item.get("id") == "EIG2-APPROVAL-ALLOW":
            item["expected_report_status"] = "failed"

    report = run_with_policy(tmp_path, mutated)

    assert report["status"] == "failed"
    assert "case.expected_report_status" in error_ids(report)
