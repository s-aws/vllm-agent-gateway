from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.gateway_anythingllm_health_drift import (
    HealthDriftKind,
    build_gateway_anythingllm_health_drift_report,
    validate_gateway_anythingllm_health_drift_report,
)
from vllm_agent_gateway.acceptance.v1 import HEALTH_TARGETS


def check(
    check_id: str,
    category: str,
    *,
    status: str = "passed",
    message: str = "ok",
    details: dict[str, Any] | None = None,
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
            check(
                "gateway.llm_gateway",
                "gateway_config",
                details={
                    "url": "http://127.0.0.1:8300/__gateway/health",
                    "http_status": 200,
                    "target_base_url": "http://127.0.0.1:8000",
                    "controller_routing": "explicit_envelope",
                    "controller_harness_url": "http://127.0.0.1:8400/v1/controller/harness/chat/completions",
                },
            ),
            check(
                "gateway.workflow_router_gateway",
                "gateway_config",
                details={
                    "url": "http://127.0.0.1:8500/__gateway/health",
                    "http_status": 200,
                    "target_base_url": "http://127.0.0.1:8000",
                    "controller_routing": "workflow_router",
                    "controller_harness_url": "http://127.0.0.1:8400/v1/controller/workflow-router/chat/completions",
                },
            ),
            check(
                "role.reviewer/code",
                "role_proxy",
                details={
                    "url": "http://127.0.0.1:8101/__proxy/health",
                    "http_status": 200,
                    "body": {"role_key": "reviewer", "subrole": "code"},
                },
            ),
            check(
                "controller.health",
                "controller",
                details={"url": "http://127.0.0.1:8400/health", "http_status": 200},
            ),
            check(
                "controller.allowed_roots",
                "controller",
                details={"allowed_target_roots": ["/mnt/c/agentic_agents"], "missing_roots": []},
            ),
            check("anythingllm.api_key", "anythingllm", details={"api_key_available": True}),
            check(
                "anythingllm.ping",
                "anythingllm",
                details={"url": "http://127.0.0.1:3001/api/ping", "http_status": 200},
            ),
            check(
                "anythingllm.workspace",
                "anythingllm",
                details={"url": "http://127.0.0.1:3001/api/v1/workspaces", "http_status": 200, "workspace_found": True},
            ),
            check(
                "anythingllm.target_url",
                "anythingllm",
                details={
                    "url": "http://127.0.0.1:3001/api/v1/system",
                    "http_status": 200,
                    "GenericOpenAiBasePath": "http://127.0.0.1:8500/v1",
                    "expected": "http://127.0.0.1:8500/v1",
                },
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
            "category_counts": {},
            "failed_check_ids": [],
            "warning_check_ids": [],
        },
        "errors": [],
    }


def replace_check(report: dict[str, Any], check_id: str, replacement: dict[str, Any]) -> None:
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


def report_for(doctor_report: dict[str, Any]) -> dict[str, Any]:
    return build_gateway_anythingllm_health_drift_report(
        doctor_report=doctor_report,
        doctor_report_path=Path("runtime-state/first-time-user-doctor/test.json"),
    )


def finding_kinds(report: dict[str, Any]) -> set[str]:
    return {str(item["kind"]) for item in report["findings"]}


def test_gateway_anythingllm_health_drift_passes_clean_doctor_report() -> None:
    doctor = passing_doctor_report()
    report = report_for(doctor)

    assert report["status"] == "passed"
    assert report["summary"]["finding_count"] == 0
    assert report["missing_required_categories"] == []
    assert report["missing_port_check_ids"] == []


def test_gateway_anythingllm_health_drift_ignores_fixture_line_ending_warning() -> None:
    doctor = passing_doctor_report()
    doctor["checks"].append(
        check(
            "fixtures.coinbase-frozen-git",
            "fixtures",
            status="warning",
            message="Fixture has watched hashes and only line-ending git noise from Bash.",
            next_action="Line-ending-only dirtiness is not blocking.",
        )
    )
    doctor["summary"]["check_count"] = len(doctor["checks"])
    doctor["summary"]["warning_check_ids"] = ["fixtures.coinbase-frozen-git"]
    doctor["summary"]["status_counts"] = {
        "passed": len(doctor["checks"]) - 1,
        "failed": 0,
        "warning": 1,
        "skipped": 0,
    }

    report = report_for(doctor)

    assert report["status"] == "passed"
    assert report["summary"]["finding_count"] == 0
    assert report["summary"]["warning_check_count"] == 1


def test_gateway_anythingllm_health_drift_classifies_unreachable_port() -> None:
    doctor = passing_doctor_report()
    replace_check(
        doctor,
        "port.model",
        check(
            "port.model",
            "port_health",
            status="failed",
            message="model health check failed: connection refused",
            details={"url": "http://127.0.0.1:8000/v1/models", "diagnostic_kind": "unreachable_port", "stage": "open"},
        ),
    )

    report = report_for(doctor)

    assert report["status"] == "failed"
    assert finding_kinds(report) == {HealthDriftKind.UNREACHABLE_PORT.value}


def test_gateway_anythingllm_health_drift_classifies_headers_without_body_timeout() -> None:
    doctor = passing_doctor_report()
    replace_check(
        doctor,
        "port.llm_gateway",
        check(
            "port.llm_gateway",
            "port_health",
            status="failed",
            message="headers received with HTTP 200, but response body timed out",
            details={
                "url": "http://127.0.0.1:8300/v1/models",
                "diagnostic_kind": "headers_without_body_timeout",
                "stage": "body_read",
                "http_status": 200,
            },
        ),
    )

    report = report_for(doctor)

    assert report["status"] == "failed"
    assert finding_kinds(report) == {HealthDriftKind.HEADERS_WITHOUT_BODY_TIMEOUT.value}


def test_gateway_anythingllm_health_drift_classifies_wrong_gateway_backend() -> None:
    doctor = passing_doctor_report()
    replace_check(
        doctor,
        "gateway.workflow_router_gateway",
        check(
            "gateway.workflow_router_gateway",
            "gateway_config",
            status="failed",
            message="workflow router gateway configuration does not match expected routing.",
            details={
                "url": "http://127.0.0.1:8500/__gateway/health",
                "http_status": 200,
                "target_base_url": "http://127.0.0.1:8400",
                "controller_routing": "explicit_envelope",
                "controller_harness_url": "http://127.0.0.1:8400/v1/controller/harness/chat/completions",
            },
        ),
    )

    report = report_for(doctor)

    assert report["status"] == "failed"
    assert finding_kinds(report) == {HealthDriftKind.WRONG_BACKEND_TARGET.value}


def test_gateway_anythingllm_health_drift_classifies_auth_failure() -> None:
    doctor = passing_doctor_report()
    replace_check(
        doctor,
        "anythingllm.workspace",
        check(
            "anythingllm.workspace",
            "anythingllm",
            status="failed",
            message="AnythingLLM workspace lookup returned HTTP 401.",
            details={"url": "http://127.0.0.1:3001/api/v1/workspaces", "http_status": 401},
            next_action="Check ANYTHINGLLM_API_KEY.",
        ),
    )

    report = report_for(doctor)

    assert report["status"] == "failed"
    assert finding_kinds(report) == {HealthDriftKind.AUTH_FAILURE.value}


def test_gateway_anythingllm_health_drift_does_not_call_missing_workspace_auth_failure() -> None:
    doctor = passing_doctor_report()
    replace_check(
        doctor,
        "anythingllm.workspace",
        check(
            "anythingllm.workspace",
            "anythingllm",
            status="failed",
            message="AnythingLLM workspace 'my-workspace' was not found.",
            details={"url": "http://127.0.0.1:3001/api/v1/workspaces", "http_status": 200, "workspace_found": False},
        ),
    )

    report = report_for(doctor)

    assert report["status"] == "failed"
    assert finding_kinds(report) == {HealthDriftKind.UNEXPECTED_RESPONSE.value}


def test_gateway_anythingllm_health_drift_classifies_anythingllm_wrong_target() -> None:
    doctor = passing_doctor_report()
    replace_check(
        doctor,
        "anythingllm.target_url",
        check(
            "anythingllm.target_url",
            "anythingllm",
            status="failed",
            message="AnythingLLM does not point at the workflow-router gateway.",
            details={
                "url": "http://127.0.0.1:3001/api/v1/system",
                "http_status": 200,
                "GenericOpenAiBasePath": "http://127.0.0.1:8300/v1",
                "expected": "http://127.0.0.1:8500/v1",
            },
        ),
    )

    report = report_for(doctor)

    assert report["status"] == "failed"
    assert finding_kinds(report) == {HealthDriftKind.WRONG_BACKEND_TARGET.value}


def test_gateway_anythingllm_health_drift_classifies_role_metadata_drift() -> None:
    doctor = passing_doctor_report()
    replace_check(
        doctor,
        "role.reviewer/code",
        check(
            "role.reviewer/code",
            "role_proxy",
            status="failed",
            message="reviewer/code proxy does not match runtime role metadata.",
            details={
                "url": "http://127.0.0.1:8101/__proxy/health",
                "http_status": 200,
                "body": {"role_key": "tester", "subrole": "code"},
            },
        ),
    )

    report = report_for(doctor)

    assert report["status"] == "failed"
    assert finding_kinds(report) == {HealthDriftKind.UNEXPECTED_RESPONSE.value}


def test_gateway_anythingllm_health_drift_rejects_hidden_summary_change() -> None:
    doctor = passing_doctor_report()
    report = report_for(doctor)
    tampered = copy.deepcopy(report)
    tampered["summary"]["check_count"] = 999

    errors = validate_gateway_anythingllm_health_drift_report(
        tampered,
        doctor_report=doctor,
        doctor_report_path=Path("runtime-state/first-time-user-doctor/test.json"),
    )

    assert any("report.summary must match rebuilt gateway/AnythingLLM health drift report" in error for error in errors)
