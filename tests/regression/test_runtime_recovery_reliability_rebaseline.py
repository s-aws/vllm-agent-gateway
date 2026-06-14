from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.runtime_recovery_reliability_rebaseline import (
    DEFAULT_POLICY_PATH,
    build_runtime_recovery_rebaseline_report,
    validate_policy,
    validate_runtime_recovery_rebaseline_report,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict[str, Any]:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def restart_evidence(*, managed_stack: str = "passed", vllm_model: str = "passed", status: str = "passed") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "runtime_recovery_restart_evidence",
        "phase": 231,
        "status": status,
        "components": [
            {
                "component": "managed_stack",
                "restart_mode": "repo_scripts",
                "status": managed_stack,
                "script": "stop-agent-prompt-proxies.sh && start-agent-prompt-proxies.sh",
            },
            {
                "component": "vllm_model",
                "restart_mode": "docker_restart",
                "status": vllm_model,
                "container": "vllm-qwen3",
            },
        ],
        "summary": {
            "component_count": 2,
            "failed_component_count": 0 if managed_stack == "passed" and vllm_model == "passed" else 1,
            "command_count": 2,
            "restarted_components": [
                item
                for item, component_status in (("managed_stack", managed_stack), ("vllm_model", vllm_model))
                if component_status == "passed"
            ],
        },
    }


def post_restart_report(*, status: str = "passed", decision: str = "ready_after_restart", missing_count: int = 0) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "post_restart_runtime_readiness_report",
        "phase": 163,
        "status": status,
        "decision": decision,
        "summary": {
            "decision": decision,
            "missing_required_surface_count": missing_count,
            "validation_error_count": 0 if status == "passed" else 1,
        },
    }


def small_repo_report(*, clients: tuple[str, ...] = ("gateway", "anythingllm"), case_id: str = "python-service-code-explanation") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "multi_repo_fixture_live_report",
        "status": "passed",
        "cases": [
            {
                "client": client,
                "case_id": case_id,
                "status": "passed",
                "selected_workflow": "code_investigation.plan",
                "source_unchanged": True,
            }
            for client in clients
        ],
        "summary": {
            "case_count": 1,
            "client_case_count": len(clients),
            "clients": list(clients),
            "error_count": 0,
        },
    }


def large_context_report(*, surfaces: tuple[str, ...] = ("gateway", "anythingllm"), case_id: str = "P221-LC-001") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "large_context_usability_live_closeout_report",
        "phase": 221,
        "status": "passed",
        "live": True,
        "responses": [
            {
                "surface": surface,
                "case_id": case_id,
                "status": "passed",
                "selected_context_strategy": "retrieval",
                "score": 100,
            }
            for surface in surfaces
        ],
        "summary": {
            "response_count": len(surfaces),
            "failed_response_count": 0,
            "surface_count": len(surfaces),
        },
    }


def build_report(
    *,
    current_policy: dict[str, Any] | None = None,
    restart: dict[str, Any] | None = None,
    post_restart: dict[str, Any] | None = None,
    small_repo: dict[str, Any] | None = None,
    large_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_runtime_recovery_rebaseline_report(
        policy=current_policy or policy(),
        restart_evidence=restart or restart_evidence(),
        post_restart_report=post_restart or post_restart_report(),
        small_repo_report=small_repo or small_repo_report(),
        large_context_report=large_context or large_context_report(),
    )


def test_phase231_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase231_report_passes_clean_sources() -> None:
    current_policy = policy()
    restart = restart_evidence()
    post_restart = post_restart_report()
    small_repo = small_repo_report()
    large_context = large_context_report()

    report = build_runtime_recovery_rebaseline_report(
        policy=current_policy,
        restart_evidence=restart,
        post_restart_report=post_restart,
        small_repo_report=small_repo,
        large_context_report=large_context,
    )

    assert report["status"] == "passed"
    assert report["decision"] == "ready_after_recovery"
    assert report["summary"]["missing_required_surface_count"] == 0
    assert report["summary"]["phase232_ready"] is True
    assert (
        validate_runtime_recovery_rebaseline_report(
            report,
            policy=current_policy,
            restart_evidence=restart,
            post_restart_report=post_restart,
            small_repo_report=small_repo,
            large_context_report=large_context,
        )
        == []
    )


def test_phase231_rejects_missing_managed_stack_restart() -> None:
    report = build_report(restart=restart_evidence(managed_stack="not_restarted", status="failed"))

    assert report["status"] == "failed"
    assert "restart.managed_stack" in report["missing_required_surfaces"]
    assert any(item["id"] == "restart.managed_stack" for item in report["validation_errors"])


def test_phase231_rejects_missing_vllm_restart() -> None:
    report = build_report(restart=restart_evidence(vllm_model="not_restarted", status="failed"))

    assert report["status"] == "failed"
    assert "restart.vllm_model" in report["missing_required_surfaces"]
    assert any(item["id"] == "restart.vllm_model" for item in report["validation_errors"])


def test_phase231_rejects_failed_post_restart_readiness() -> None:
    report = build_report(post_restart=post_restart_report(status="failed", decision="blocked_after_restart", missing_count=2))

    assert report["status"] == "failed"
    assert "post_restart.readiness" in report["missing_required_surfaces"]
    assert any(item["id"] == "post_restart.status" for item in report["validation_errors"])


def test_phase231_rejects_small_repo_without_anythingllm() -> None:
    report = build_report(small_repo=small_repo_report(clients=("gateway",)))

    assert report["status"] == "failed"
    assert "small_repo.anythingllm" in report["missing_required_surfaces"]
    assert any(item["id"] == "small_repo.clients" for item in report["validation_errors"])


def test_phase231_rejects_large_context_without_anythingllm() -> None:
    report = build_report(large_context=large_context_report(surfaces=("gateway",)))

    assert report["status"] == "failed"
    assert "large_context.anythingllm" in report["missing_required_surfaces"]
    assert any(item["id"] == "large_context.surfaces" for item in report["validation_errors"])


def test_phase231_rebuild_rejects_hidden_summary_edit() -> None:
    current_policy = policy()
    restart = restart_evidence()
    post_restart = post_restart_report()
    small_repo = small_repo_report()
    large_context = large_context_report()
    report = build_runtime_recovery_rebaseline_report(
        policy=current_policy,
        restart_evidence=restart,
        post_restart_report=post_restart,
        small_repo_report=small_repo,
        large_context_report=large_context,
    )
    edited = copy.deepcopy(report)
    edited["summary"]["source_report_count"] = 999

    errors = validate_runtime_recovery_rebaseline_report(
        edited,
        policy=current_policy,
        restart_evidence=restart,
        post_restart_report=post_restart,
        small_repo_report=small_repo,
        large_context_report=large_context,
    )

    assert errors == ["report must match rebuilt runtime recovery rebaseline report"]
