from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.anythingllm_session_recovery import build_report_from_cases
from vllm_agent_gateway.acceptance.gateway_anythingllm_health_drift import build_gateway_anythingllm_health_drift_report
from vllm_agent_gateway.acceptance.post_restart_runtime_readiness import (
    PostRestartRuntimeReadinessConfig,
    READY_NEXT_ACTION,
    build_post_restart_runtime_readiness_report,
    run_post_restart_runtime_readiness,
    validate_post_restart_runtime_readiness_report,
)
from vllm_agent_gateway.acceptance.v1 import HEALTH_TARGETS


REPO_ROOT = Path(__file__).resolve().parents[2]


def check(
    check_id: str,
    category: str,
    *,
    status: str = "passed",
    details: dict[str, Any] | None = None,
    message: str = "ok",
    next_action: str = "",
) -> dict[str, Any]:
    return {
        "id": check_id,
        "category": category,
        "status": status,
        "message": message,
        "details": details or {},
        "next_action": next_action,
    }


def passing_doctor_report() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for target in HEALTH_TARGETS:
        checks.append(
            check(
                f"port.{target['name']}",
                "port_health",
                details={**target, "url": f"http://127.0.0.1:{target['port']}{target['path']}", "http_status": 200},
            )
        )
    checks.extend(
        [
            check("gateway.llm_gateway", "gateway_config", details={"target_base_url": "http://127.0.0.1:8000"}),
            check(
                "gateway.workflow_router_gateway",
                "gateway_config",
                details={"target_base_url": "http://127.0.0.1:8000", "controller_routing": "workflow_router"},
            ),
            check("role.reviewer/code", "role_proxy", details={"http_status": 200}),
            check("controller.health", "controller", details={"http_status": 200}),
            check("controller.allowed_roots", "controller", details={"missing_roots": []}),
            check("anythingllm.api_key", "anythingllm", details={"api_key_available": True}),
            check("anythingllm.ping", "anythingllm", details={"http_status": 200}),
            check("anythingllm.workspace", "anythingllm", details={"http_status": 200, "workspace_found": True}),
            check(
                "anythingllm.target_url",
                "anythingllm",
                details={"GenericOpenAiBasePath": "http://127.0.0.1:8500/v1", "expected": "http://127.0.0.1:8500/v1"},
            ),
        ]
    )
    return {
        "schema_version": 1,
        "kind": "first_time_user_doctor_report",
        "status": "passed",
        "checks": checks,
        "summary": {
            "check_count": len(checks),
            "status_counts": {"passed": len(checks), "failed": 0, "warning": 0, "skipped": 0},
            "failed_check_ids": [],
            "warning_check_ids": [],
        },
        "errors": [],
    }


def passing_session_report() -> dict[str, Any]:
    return build_report_from_cases(
        cases=[
            {
                "case_id": "DIRECT-HI",
                "surface": "direct_controller",
                "status": "passed",
                "http_status": 200,
                "text_sample": "general_chat_no_target Selected workflow: none include an allowed target_root path",
                "finding_count": 0,
                "findings": [],
            },
            {
                "case_id": "ANYTHINGLLM-HI",
                "surface": "anythingllm",
                "status": "passed",
                "http_status": 200,
                "text_sample": "general_chat_no_target Selected workflow: none include an allowed target_root path",
                "finding_count": 0,
                "findings": [],
            },
        ],
        anythingllm_preflight_result={"status": "passed", "workspace_found": True},
    )


def write_json(path: Path, report: dict[str, Any]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def policy() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "post_restart_runtime_readiness_policy",
        "phase": 163,
        "priority_backlog_id": "P0-BB-027",
        "required_decision": "ready_after_restart",
        "required_source_reports": [
            "first_time_user_doctor_report",
            "gateway_anythingllm_health_drift_report",
            "anythingllm_session_recovery_report",
        ],
        "required_surfaces": [
            *[f"port.{target['name']}" for target in HEALTH_TARGETS],
            "anythingllm.api_key",
            "anythingllm.workspace",
            "anythingllm.target_url",
            "session.direct_controller",
            "session.anythingllm",
        ],
        "allowed_warning_check_ids": ["fixtures.coinbase-frozen-git"],
        "acceptance_marker": "POST RESTART RUNTIME READINESS PASS",
    }


def report_paths(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    return (
        tmp_path / "policy.json",
        tmp_path / "doctor.json",
        tmp_path / "health.json",
        tmp_path / "session.json",
    )


def build_reports(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], Path, Path, Path, Path]:
    policy_path, doctor_path, health_path, session_path = report_paths(tmp_path)
    current_policy = policy()
    doctor = passing_doctor_report()
    write_json(policy_path, current_policy)
    write_json(doctor_path, doctor)
    health = build_gateway_anythingllm_health_drift_report(doctor_report=doctor, doctor_report_path=doctor_path)
    write_json(health_path, health)
    session = passing_session_report()
    write_json(session_path, session)
    return current_policy, doctor, health, session, policy_path, doctor_path, health_path, session_path


def replace_check_and_refresh_summary(report: dict[str, Any], check_id: str, replacement: dict[str, Any]) -> None:
    checks = report["checks"]
    for index, item in enumerate(checks):
        if item["id"] == check_id:
            checks[index] = replacement
            break
    else:
        raise AssertionError(f"missing check {check_id}")
    failed_ids = sorted(item["id"] for item in checks if item["status"] == "failed")
    warning_ids = sorted(item["id"] for item in checks if item["status"] == "warning")
    report["summary"]["failed_check_ids"] = failed_ids
    report["summary"]["warning_check_ids"] = warning_ids
    report["summary"]["status_counts"] = {
        "passed": sum(1 for item in checks if item["status"] == "passed"),
        "failed": len(failed_ids),
        "warning": len(warning_ids),
        "skipped": sum(1 for item in checks if item["status"] == "skipped"),
    }
    report["status"] = "failed" if failed_ids else "passed"


def test_post_restart_runtime_readiness_passes_clean_sources(tmp_path: Path) -> None:
    current_policy, doctor, health, session, policy_path, doctor_path, health_path, session_path = build_reports(tmp_path)

    report = build_post_restart_runtime_readiness_report(
        policy=current_policy,
        doctor_report=doctor,
        health_drift_report=health,
        session_recovery_report=session,
        policy_path=policy_path,
        doctor_report_path=doctor_path,
        health_drift_report_path=health_path,
        session_recovery_report_path=session_path,
    )

    assert report["status"] == "passed"
    assert report["decision"] == "ready_after_restart"
    assert report["summary"]["missing_required_surface_count"] == 0
    assert report["summary"]["next_action"] == READY_NEXT_ACTION
    assert report["summary"]["diagnostic_action_count"] == 0
    assert report["summary"]["blocking_diagnostic_action_count"] == 0
    assert report["diagnostic_actions"] == []


def test_post_restart_runtime_readiness_surfaces_api_key_bridge_recovery_action(tmp_path: Path) -> None:
    current_policy, doctor, _health, session, policy_path, doctor_path, health_path, session_path = build_reports(tmp_path)
    replace_check_and_refresh_summary(
        doctor,
        "anythingllm.api_key",
        check(
            "anythingllm.api_key",
            "anythingllm",
            status="failed",
            message="ANYTHINGLLM_API_KEY is missing.",
            details={
                "api_key_env": "ANYTHINGLLM_API_KEY",
                "api_key_available": False,
                "powershell_wsl_env_example": (
                    "$key=$env:ANYTHINGLLM_API_KEY; wsl.exe --cd /mnt/c/agentic_agents -- "
                    "env \"ANYTHINGLLM_API_KEY=$key\" python3 scripts/validate_post_restart_runtime_readiness.py"
                ),
            },
            next_action="Inject the Windows AnythingLLM API key into WSL with the command shown in details.",
        ),
    )
    write_json(doctor_path, doctor)
    health = build_gateway_anythingllm_health_drift_report(doctor_report=doctor, doctor_report_path=doctor_path)
    write_json(health_path, health)

    report = build_post_restart_runtime_readiness_report(
        policy=current_policy,
        doctor_report=doctor,
        health_drift_report=health,
        session_recovery_report=session,
        policy_path=policy_path,
        doctor_report_path=doctor_path,
        health_drift_report_path=health_path,
        session_recovery_report_path=session_path,
    )

    assert report["status"] == "failed"
    assert report["summary"]["diagnostic_action_count"] >= 1
    assert report["summary"]["blocking_diagnostic_action_count"] >= 1
    matching = [item for item in report["diagnostic_actions"] if item["check_id"] == "anythingllm.api_key"]
    assert matching
    assert any("wsl.exe --cd" in item.get("powershell_wsl_env_example", "") for item in matching)
    assert "anythingllm.api_key" in report["missing_required_surfaces"]


def test_post_restart_runtime_readiness_fails_missing_port_surface(tmp_path: Path) -> None:
    current_policy, doctor, health, session, policy_path, doctor_path, health_path, session_path = build_reports(tmp_path)
    doctor["checks"] = [item for item in doctor["checks"] if item["id"] != "port.implementer_default"]
    write_json(doctor_path, doctor)
    health = build_gateway_anythingllm_health_drift_report(doctor_report=doctor, doctor_report_path=doctor_path)

    report = build_post_restart_runtime_readiness_report(
        policy=current_policy,
        doctor_report=doctor,
        health_drift_report=health,
        session_recovery_report=session,
        policy_path=policy_path,
        doctor_report_path=doctor_path,
        health_drift_report_path=health_path,
        session_recovery_report_path=session_path,
    )

    assert report["status"] == "failed"
    assert "port.implementer_default" in report["missing_required_surfaces"]


def test_post_restart_runtime_readiness_fails_skipped_live_anythingllm_session(tmp_path: Path) -> None:
    current_policy, doctor, health, _session, policy_path, doctor_path, health_path, session_path = build_reports(tmp_path)
    session = build_report_from_cases(
        cases=[
            {
                "case_id": "DIRECT-HI",
                "surface": "direct_controller",
                "status": "passed",
                "http_status": 200,
                "text_sample": "general_chat_no_target Selected workflow: none include an allowed target_root path",
                "finding_count": 0,
                "findings": [],
            }
        ]
    )
    write_json(session_path, session)

    report = build_post_restart_runtime_readiness_report(
        policy=current_policy,
        doctor_report=doctor,
        health_drift_report=health,
        session_recovery_report=session,
        policy_path=policy_path,
        doctor_report_path=doctor_path,
        health_drift_report_path=health_path,
        session_recovery_report_path=session_path,
    )

    assert report["status"] == "failed"
    assert "session.anythingllm" in report["missing_required_surfaces"]
    assert any("live AnythingLLM case" in error for error in report["errors"])


def test_post_restart_runtime_readiness_rejects_hidden_summary_change(tmp_path: Path) -> None:
    current_policy, doctor, health, session, policy_path, doctor_path, health_path, session_path = build_reports(tmp_path)
    report = build_post_restart_runtime_readiness_report(
        policy=current_policy,
        doctor_report=doctor,
        health_drift_report=health,
        session_recovery_report=session,
        policy_path=policy_path,
        doctor_report_path=doctor_path,
        health_drift_report_path=health_path,
        session_recovery_report_path=session_path,
    )
    tampered = copy.deepcopy(report)
    tampered["summary"]["validation_error_count"] = 99

    errors = validate_post_restart_runtime_readiness_report(
        tampered,
        policy=current_policy,
        doctor_report=doctor,
        health_drift_report=health,
        session_recovery_report=session,
        policy_path=policy_path,
        doctor_report_path=doctor_path,
        health_drift_report_path=health_path,
        session_recovery_report_path=session_path,
    )

    assert any("report.summary must match rebuilt" in error for error in errors)


def test_post_restart_runtime_readiness_runner_uses_existing_source_runners(tmp_path: Path) -> None:
    policy_path, doctor_path, health_path, session_path = report_paths(tmp_path)
    write_json(policy_path, policy())

    def health_runner(config: Any) -> dict[str, Any]:
        doctor = passing_doctor_report()
        write_json(config.doctor_output_path, doctor)
        report = build_gateway_anythingllm_health_drift_report(
            doctor_report=doctor,
            doctor_report_path=config.doctor_output_path,
        )
        write_json(config.output_path, report)
        report["report_path"] = str(config.output_path.resolve())
        write_json(config.output_path, report)
        return report

    def session_runner(config: Any) -> dict[str, Any]:
        report = passing_session_report()
        write_json(config.output_path, report)
        return report

    report = run_post_restart_runtime_readiness(
        PostRestartRuntimeReadinessConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "readiness.json",
            health_drift_output_path=health_path,
            doctor_output_path=doctor_path,
            session_recovery_output_path=session_path,
            policy_path=policy_path,
        ),
        health_drift_runner=health_runner,
        session_recovery_runner=session_runner,
    )

    assert report["status"] == "passed"
    assert report["source_artifacts"][0]["path"] == str(doctor_path.resolve())
