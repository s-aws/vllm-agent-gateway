from __future__ import annotations

from pathlib import Path

from vllm_agent_gateway.acceptance.eval_repair_execution_gate import (
    CommandResult,
    EvalRepairExecutionGateConfig,
    ExecutionStatus,
    run_closed_loop_eval_repair_gate,
    validate_closed_loop_report,
)


def passing_runner(command: list[str], cwd: Path, timeout_seconds: int) -> CommandResult:
    return CommandResult(
        status=ExecutionStatus.PASSED,
        command=command,
        returncode=0,
        stdout="command passed\nrun_id: workflow-router-unit",
        stderr="",
    )


def failing_target_runner(command: list[str], cwd: Path, timeout_seconds: int) -> CommandResult:
    if "L1-001" in command:
        return CommandResult(
            status=ExecutionStatus.FAILED,
            command=command,
            returncode=1,
            stdout="missing markers: Beginning point:, Related tests:, Recommended commands:",
            stderr="",
        )
    return passing_runner(command, cwd, timeout_seconds)


def config(tmp_path: Path, *, execute_live: bool = True, include_port_health: bool = True) -> EvalRepairExecutionGateConfig:
    return EvalRepairExecutionGateConfig(
        config_root=tmp_path,
        output_path=tmp_path / "phase111-closed-loop.json",
        target_roots=("/mnt/c/example_coinbase", "/mnt/c/example_coinbase.git"),
        execute_live=execute_live,
        include_port_health=include_port_health,
    )


def test_closed_loop_eval_repair_gate_passes_with_target_holdout_and_port_health(tmp_path: Path) -> None:
    report = run_closed_loop_eval_repair_gate(config(tmp_path), command_runner=passing_runner)

    assert report["status"] == "passed"
    assert report["before_failure_capture"]["status"] == "failed_controlled_negative"  # type: ignore[index]
    assert report["failure_taxonomy"]["status"] == "passed"  # type: ignore[index]
    assert report["advisory_eval_repair"]["status"] == "passed"  # type: ignore[index]
    assert report["execution"]["target_result_status"] == "passed"  # type: ignore[index]
    assert report["execution"]["holdout_result_status"] == "passed"  # type: ignore[index]
    assert report["execution"]["port_health_status"] == "passed"  # type: ignore[index]
    assert report["deterministic_adjudication"]["status"] == "accepted"  # type: ignore[index]
    assert report["protected_fixture_mutation"] is False
    assert validate_closed_loop_report(report) == []
    final_recommendation = report["final_eval_repair_report"]["recommendations"][0]  # type: ignore[index]
    assert final_recommendation["current_phase_tightening"] is True
    assert "validate_workflow_router_l1_suite.py" in final_recommendation["target_rerun_command"]
    assert final_recommendation["target_prompt_case_id"] == "L1-001"
    assert final_recommendation["holdout_prompt_case_id"] == "L1-002"
    assert (tmp_path / "phase111-closed-loop.md").read_text(encoding="utf-8").startswith(
        "# Closed-Loop Eval Repair Execution Report"
    )


def test_closed_loop_eval_repair_gate_fails_when_target_does_not_pass(tmp_path: Path) -> None:
    report = run_closed_loop_eval_repair_gate(config(tmp_path), command_runner=failing_target_runner)

    assert report["status"] == "failed"
    assert report["execution"]["target_result_status"] == "failed"  # type: ignore[index]
    assert report["execution"]["holdout_result_status"] == "passed"  # type: ignore[index]
    assert any("target_result_status must be passed" in error for error in report["validation_errors"])  # type: ignore[index]
    assert report["deterministic_adjudication"]["status"] == "partial"  # type: ignore[index]


def test_closed_loop_eval_repair_gate_requires_live_execution_for_pass(tmp_path: Path) -> None:
    report = run_closed_loop_eval_repair_gate(config(tmp_path, execute_live=False), command_runner=passing_runner)

    assert report["status"] == "failed"
    assert report["execution"]["target_result_status"] == "not_run_required"  # type: ignore[index]
    assert report["execution"]["holdout_result_status"] == "not_run_required"  # type: ignore[index]
    assert any("target_result_status must be passed" in error for error in report["validation_errors"])  # type: ignore[index]
