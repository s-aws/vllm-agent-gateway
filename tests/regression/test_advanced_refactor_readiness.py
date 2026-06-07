from __future__ import annotations

import json
import shutil
from pathlib import Path

from vllm_agent_gateway.acceptance.advanced_refactor_readiness import (
    AdvancedRefactorReadinessConfig,
    advanced_refactor_gate_decision,
    run_advanced_refactor_readiness,
)
from vllm_agent_gateway.controller_service.server import ControllerServiceConfig, handle_workflow_router_chat_completion


REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN_ROOTS = (
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
)


def write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def implementation_prep_report(surface: str, *, source_changed: bool = False) -> dict[str, object]:
    summary = {
        "direct_enabled": surface == "direct",
        "gateway_enabled": surface == "gateway",
        "anythingllm_enabled": surface == "anythingllm",
        "failed_check_ids": [],
        "case_count": 2,
        "check_count": 3,
    }
    target_roots = [FROZEN_ROOTS[0]] if surface == "direct" else list(FROZEN_ROOTS)
    checks = [{"id": "catalog.contract", "status": "passed", "details": {"errors": []}}]
    for index, target_root in enumerate(target_roots, start=1):
        checks.append(
            {
                "id": f"{surface}.IPREP-{index:03d}",
                "status": "passed",
                "details": {
                    "target_root": target_root,
                    "route_status": "ready",
                    "selected_workflow": "execution_planning.plan",
                    "proposal_status": "ready",
                    "proposal_operation_targets": [{"kind": "replace_text", "path": "README.md"}],
                    "downstream_repo_mutated": False,
                    "summary_source_changed": source_changed,
                    "fixture_state_unchanged": True,
                    "downstream_verification_command_count": 1,
                    "proposal_verification_commands": ["python -m pytest tests/unit/test_example.py"],
                },
            }
        )
    return {
        "schema_version": 1,
        "kind": "implementation_prep_expansion_report",
        "status": "passed",
        "summary": summary,
        "checks": checks,
    }


def approval_continuation_report(surface: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "approval_continuation_robustness_report",
        "status": "passed",
        "summary": {
            "direct_enabled": surface == "direct",
            "gateway_enabled": surface == "gateway",
            "anythingllm_enabled": surface == "anythingllm",
            "failed_count": 0,
            "target_roots": list(FROZEN_ROOTS),
            "check_count": 2,
        },
        "checks": [
            {"id": "catalog", "status": "passed", "details": {"errors": []}},
            {
                "id": f"{surface}.approval_continuation",
                "status": "passed",
                "details": {
                    "wrong_run_error": "approval_not_pending",
                    "duplicate_error": "approval_already_consumed",
                    "denial_error": "approval_denied",
                    "target_mismatch_error": "approval_scope_changed",
                    "scope_change_error": "approval_scope_changed",
                    "fixture_state_unchanged": True,
                },
            },
        ],
    }


def disposable_apply_report(surface: str, *, source_tree_changed: bool = False, rollback_failed: bool = False) -> dict[str, object]:
    checks: list[dict[str, object]] = [{"id": "catalog.contract", "status": "passed", "details": {"errors": []}}]
    for case_id in ("DAE-001", "DAE-002"):
        checks.append(
            {
                "id": f"{surface}.{case_id}",
                "status": "passed",
                "details": {
                    "case_id": case_id,
                    "source_tree_changed": source_tree_changed,
                    "copy_tree_restored": not rollback_failed,
                    "fixture_state_unchanged": True,
                    "changed_file_count": 1,
                },
            }
        )
    checks.append(
        {
            "id": f"{surface}.DAE-003",
            "status": "passed",
            "details": {
                "case_id": "DAE-003",
                "fixture_state_unchanged": True,
                "blocked": {"error_code": "unsupported_disposable_operation_kind"},
            },
        }
    )
    if surface in {"gateway", "anythingllm"}:
        for target_root in FROZEN_ROOTS:
            checks.append(
                {
                    "id": f"protected_source_apply_refusal.{Path(target_root).name}",
                    "status": "passed",
                    "details": {
                        "fixture_state_unchanged": True,
                        "http_status": 403,
                        "target_root": target_root,
                    },
                }
            )
    return {
        "schema_version": 1,
        "kind": "disposable_apply_expansion_report",
        "status": "passed",
        "summary": {
            "direct_enabled": surface == "direct",
            "gateway_enabled": surface == "gateway",
            "anythingllm_enabled": surface == "anythingllm",
            "failed_check_ids": [],
            "case_count": 3,
            "check_count": len(checks),
            "live_case_count": 2,
            "port_health_enabled": surface != "direct",
        },
        "checks": checks,
    }


def multi_repo_report() -> dict[str, object]:
    cases: list[dict[str, object]] = []
    for target_root, category in (
        (FROZEN_ROOTS[0], "real-world-python-non-git"),
        (FROZEN_ROOTS[1], "real-world-python-git"),
    ):
        for client in ("gateway", "anythingllm"):
            cases.append(
                {
                    "case_id": f"{category}-{client}",
                    "category": category,
                    "client": client,
                    "target_root": target_root,
                    "status": "passed",
                    "source_unchanged": True,
                    "git_status_unchanged": True,
                    "layout_status": "supported",
                    "selected_context_sources": ["ast_index", "text_search"],
                    "context_gaps": [],
                }
            )
    for category in ("synthetic-python-service", "synthetic-node-cli", "synthetic-go-http-service"):
        for client in ("gateway", "anythingllm"):
            cases.append(
                {
                    "case_id": f"{category}-{client}",
                    "category": category,
                    "client": client,
                    "target_root": f"/tmp/{category}",
                    "status": "passed",
                    "source_unchanged": True,
                    "git_status_unchanged": True,
                    "layout_status": "supported",
                    "selected_context_sources": ["text_search"],
                    "context_gaps": [],
                }
            )
    return {
        "schema_version": 1,
        "kind": "multi_repo_fixture_live_report",
        "status": "passed",
        "summary": {
            "case_count": 5,
            "fixture_count": 5,
            "client_case_count": len(cases),
            "clients": ["gateway", "anythingllm"],
            "categories": [
                "real-world-python-git",
                "real-world-python-non-git",
                "synthetic-python-service",
                "synthetic-node-cli",
                "synthetic-go-http-service",
            ],
            "error_count": 0,
        },
        "cases": cases,
        "port_health": [
            {"label": "localhost-model", "status": "passed", "url": "http://127.0.0.1:8000/v1/models"},
            {"label": "llm-gateway", "status": "passed", "url": "http://127.0.0.1:8300/v1/models"},
            {"label": "controller", "status": "passed", "url": "http://127.0.0.1:8400/health"},
            {"label": "workflow-router-gateway", "status": "passed", "url": "http://127.0.0.1:8500/v1/models"},
        ],
    }


def deferred_plan(target_root: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "task_decomposition",
        "workflow": "task.decompose",
        "status": "blocked",
        "prompt_family": "advanced_refactor_deferred",
        "deferred_to_phase": 105,
        "mutation_policy": "unsupported_deferred_until_phase_105",
        "target_repository_changed": False,
        "runtime_registry_changed": False,
        "target_root": target_root,
        "selected_workflow_ids": [],
        "selected_skill_ids": [],
        "selected_tool_ids": [],
        "approval_gates": [],
        "work_packages": [{"id": "DEFER1", "workflow_id": None}],
        "verification_strategy": {"status": "blocked_deferred_scope"},
    }


def task_decomposition_report() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "task_decomposition_live_validation",
        "status": "passed",
        "runtime_changed_files": [],
        "target_changed_files": {},
        "target_roots": list(FROZEN_ROOTS),
        "checks": {
            "direct": [
                {"target_root": FROZEN_ROOTS[0], "deferred_run_id": "deferred-a"},
                {"target_root": FROZEN_ROOTS[1], "deferred_run_id": "deferred-b"},
            ],
            "gateway": [
                {"target_root": FROZEN_ROOTS[0], "format_a_run_id": "wr-a", "json_run_id": "wr-b"},
                {"target_root": FROZEN_ROOTS[1], "format_a_run_id": "wr-c", "json_run_id": "wr-d"},
            ],
            "anythingllm": [
                {"target_root": FROZEN_ROOTS[0], "format_a_run_id": "wr-e", "json_run_id": "wr-f"},
                {"target_root": FROZEN_ROOTS[1], "format_a_run_id": "wr-g", "json_run_id": "wr-h"},
            ],
            "ports": [
                {"label": label, "status": "passed", "url": f"http://127.0.0.1/{label}"}
                for label in (
                    "localhost-model",
                    "llm-gateway",
                    "controller",
                    "workflow-router-gateway",
                    "reviewer-code",
                    "tester-code",
                    "architect-default",
                    "dispatcher-default",
                    "implementer-default",
                    "researcher-default",
                    "documenter-default",
                )
            ],
        },
    }


def eval_repair_loop_report() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "eval_repair_loop_report",
        "status": "passed",
        "summary": {
            "fixture_mutation_guard": True,
            "max_repair_cycles_per_issue": 2,
            "recommendation_count": 1,
            "advisory_recommendation_count": 1,
            "current_phase_tightening_count": 0,
        },
        "blocking_errors": [],
        "validation_errors": [],
    }


def model_policy_and_profile(root: Path) -> Path:
    profile = write_json(
        root / "runtime-state" / "model-capability-profiles" / "phase100-current-profile.json",
        {
            "schema_version": 1,
            "kind": "model_capability_profile",
            "status": "warning",
            "task_policy": {
                "read_only_l1": {"status": "approved"},
                "draft_only_l1": {"status": "approved"},
                "approval_gated_l1": {"status": "conditional"},
                "l2_read_only": {"status": "approved"},
                "apply_prep": {"status": "conditional"},
                "real_apply": {"status": "not_approved"},
            },
        },
    )
    return write_json(
        root / "runtime" / "model_capability_routing.json",
        {
            "schema_version": 1,
            "kind": "model_capability_routing_policy",
            "enforcement_mode": "fail_closed",
            "default_profile_id": "unit-profile",
            "profiles": [{"profile_id": "unit-profile", "profile_path": str(profile.relative_to(root))}],
            "task_class_rules": {
                "read_only_l1": {"task_policy_key": "read_only_l1", "allowed_task_policy_statuses": ["approved"]},
                "draft_only_l1": {"task_policy_key": "draft_only_l1", "allowed_task_policy_statuses": ["approved"]},
                "approval_gated_l1": {
                    "task_policy_key": "approval_gated_l1",
                    "allowed_task_policy_statuses": ["conditional"],
                },
                "l2_read_only": {"task_policy_key": "l2_read_only", "allowed_task_policy_statuses": ["approved"]},
                "apply_prep": {"task_policy_key": "apply_prep", "allowed_task_policy_statuses": ["conditional"]},
                "real_apply": {"task_policy_key": "real_apply", "allowed_task_policy_statuses": []},
            },
        },
    )


def write_prerequisite_reports(root: Path, *, omit_anythingllm: bool = False, source_changed: bool = False) -> dict[str, tuple[Path, ...] | Path]:
    reports: dict[str, tuple[Path, ...] | Path] = {}
    surfaces = ("direct", "gateway") if omit_anythingllm else ("direct", "gateway", "anythingllm")
    reports["implementation_prep_reports"] = tuple(
        write_json(
            root / "runtime-state" / "implementation-prep-expansion" / f"phase96-implementation-prep-{surface}.json",
            implementation_prep_report(surface, source_changed=source_changed),
        )
        for surface in surfaces
    )
    reports["approval_continuation_reports"] = tuple(
        write_json(
            root / "runtime-state" / "approval-continuation-robustness" / f"phase97-approval-{surface}.json",
            approval_continuation_report(surface),
        )
        for surface in surfaces
    )
    reports["disposable_apply_reports"] = tuple(
        write_json(
            root / "runtime-state" / "disposable-apply-expansion" / f"phase98-{surface}.json",
            disposable_apply_report(surface, source_tree_changed=source_changed),
        )
        for surface in surfaces
    )
    reports["multi_repo_report"] = write_json(root / "runtime-state" / "multi-repo-fixtures" / "phase101.json", multi_repo_report())
    reports["task_decomposition_report"] = write_json(
        root / "runtime-state" / "task-decomposition" / "phase102-live.json",
        task_decomposition_report(),
    )
    reports["eval_repair_loop_report"] = write_json(
        root / "runtime-state" / "eval-repair-loop" / "phase104.json",
        eval_repair_loop_report(),
    )
    reports["model_policy_path"] = model_policy_and_profile(root)
    reports["advanced_refactor_deferred_plan_paths"] = (
        write_json(root / "deferred-a.json", deferred_plan(FROZEN_ROOTS[0])),
        write_json(root / "deferred-b.json", deferred_plan(FROZEN_ROOTS[1])),
    )
    return reports


def readiness_config(root: Path, reports: dict[str, tuple[Path, ...] | Path]) -> AdvancedRefactorReadinessConfig:
    return AdvancedRefactorReadinessConfig(
        config_root=root,
        output_path=root / "runtime-state" / "advanced-refactor-readiness" / "phase105-readiness.json",
        markdown_output_path=root / "runtime-state" / "advanced-refactor-readiness" / "phase105-readiness.md",
        implementation_prep_reports=reports["implementation_prep_reports"],  # type: ignore[arg-type]
        approval_continuation_reports=reports["approval_continuation_reports"],  # type: ignore[arg-type]
        disposable_apply_reports=reports["disposable_apply_reports"],  # type: ignore[arg-type]
        multi_repo_report=reports["multi_repo_report"],  # type: ignore[arg-type]
        task_decomposition_report=reports["task_decomposition_report"],  # type: ignore[arg-type]
        eval_repair_loop_report=reports["eval_repair_loop_report"],  # type: ignore[arg-type]
        model_policy_path=reports["model_policy_path"],  # type: ignore[arg-type]
        advanced_refactor_deferred_plan_paths=reports["advanced_refactor_deferred_plan_paths"],  # type: ignore[arg-type]
        target_roots=FROZEN_ROOTS,
    )


def copy_runtime_config(root: Path) -> None:
    shutil.copytree(REPO_ROOT / "runtime", root / "runtime")
    shutil.copytree(REPO_ROOT / ".qwen", root / ".qwen")
    profile_src = REPO_ROOT / "runtime-state" / "model-capability-profiles" / "phase100-current-profile.json"
    profile_dst = root / "runtime-state" / "model-capability-profiles" / "phase100-current-profile.json"
    profile_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(profile_src, profile_dst)


def make_target_repo(root: Path) -> Path:
    target = root / "target"
    write_json(target / "runtime-placeholder.json", {"ok": True})
    (target / "core").mkdir(parents=True, exist_ok=True)
    (target / "tests" / "unit").mkdir(parents=True, exist_ok=True)
    (target / "core" / "stealth_order_manager.py").write_text(
        "class StealthOrderManager:\n"
        "    def find_stealth_order_by_placed_order_id(self, placed_order_id):\n"
        "        return self._placed_order_index.get(placed_order_id)\n",
        encoding="utf-8",
    )
    (target / "tests" / "unit" / "test_order_id_and_followup_rules.py").write_text(
        "def test_placed_order_lookup():\n    assert True\n",
        encoding="utf-8",
    )
    return target


def test_advanced_refactor_readiness_admits_pilots_only_when_all_prerequisites_pass(tmp_path: Path) -> None:
    reports = write_prerequisite_reports(tmp_path)
    report = run_advanced_refactor_readiness(readiness_config(tmp_path, reports))

    assert report["status"] == "passed"
    assert report["readiness_status"] == "pilot_ready"
    assert report["pilot_prompt_set"]["status"] == "admitted"  # type: ignore[index]
    assert report["pilot_prompt_set"]["policy"] == "approval_gated_disposable_copy_only"  # type: ignore[index]
    assert report["stable_promotion"]["enabled"] is False  # type: ignore[index]
    assert report["runtime_behavior"]["broad_refactor_runtime_enabled"] is False  # type: ignore[index]


def test_advanced_refactor_readiness_blocks_when_anythingllm_evidence_is_missing(tmp_path: Path) -> None:
    reports = write_prerequisite_reports(tmp_path, omit_anythingllm=True)
    report = run_advanced_refactor_readiness(readiness_config(tmp_path, reports))

    assert report["status"] == "passed"
    assert report["readiness_status"] == "blocked"
    assert report["pilot_prompt_set"]["status"] == "blocked"  # type: ignore[index]
    failed = {item["id"] for item in report["prerequisites"] if item["status"] != "passed"}  # type: ignore[index]
    assert "implementation_prep_proven" in failed
    assert "approval_continuation_proven" in failed
    assert "disposable_apply_proven" in failed


def test_advanced_refactor_readiness_blocks_source_mutation_and_rollback_failures(tmp_path: Path) -> None:
    reports = write_prerequisite_reports(tmp_path, source_changed=True)
    report = run_advanced_refactor_readiness(readiness_config(tmp_path, reports))

    assert report["readiness_status"] == "blocked"
    failed = {item["id"] for item in report["prerequisites"] if item["status"] != "passed"}  # type: ignore[index]
    assert "implementation_prep_proven" in failed
    assert "disposable_apply_proven" in failed
    assert "rollback_proven" in failed


def test_advanced_refactor_gate_decision_is_fail_closed_without_report(tmp_path: Path) -> None:
    decision = advanced_refactor_gate_decision(tmp_path)

    assert decision["status"] == "blocked"
    assert decision["reason"] == "advanced_refactor_readiness_report_missing_or_unreadable"


def test_advanced_refactor_gate_decision_blocks_truncated_pilot_ready_report(tmp_path: Path) -> None:
    report_path = write_json(
        tmp_path / "runtime-state" / "advanced-refactor-readiness" / "phase105-readiness.json",
        {
            "schema_version": 1,
            "kind": "advanced_refactor_readiness_report",
            "status": "passed",
            "readiness_status": "pilot_ready",
            "prerequisites": [
                {
                    "id": "implementation_prep_proven",
                    "status": "passed",
                    "required_evidence": ["one proof is not enough"],
                    "evidence_refs": ["unit.json"],
                }
            ],
            "pilot_prompt_set": {
                "status": "admitted",
                "policy": "approval_gated_disposable_copy_only",
                "admitted_prompts": [
                    {
                        "id": "P105-PILOT-UNIT",
                        "approval_gate": {"required": True},
                        "mutation_policy": "approval_gated_disposable_copy_only",
                        "source_apply_enabled": False,
                        "stable_channel_eligible": False,
                    }
                ],
            },
            "stable_promotion": {"enabled": False, "status": "blocked_requires_later_explicit_promotion"},
            "runtime_behavior": {"router_behavior_changed": False, "broad_refactor_runtime_enabled": False},
        },
    )

    decision = advanced_refactor_gate_decision(tmp_path, report_path)

    assert decision["status"] == "blocked"
    assert decision["reason"] == "advanced_refactor_readiness_report_invalid"
    assert any("prerequisites missing required Phase 105 IDs" in item for item in decision["validation_errors"])


def test_workflow_router_blocks_natural_advanced_refactor_without_readiness_report(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    copy_runtime_config(config_root)
    target = make_target_repo(tmp_path)
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(target,),
        port=0,
    )

    body = handle_workflow_router_chat_completion(
        {
            "model": "agentic-workflow-router",
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"In {target}, refactor the placed_order_id stealth lookup so there is only one code path. "
                        "Start from the logic beginning point."
                    ),
                }
            ],
        },
        config,
    )

    compact = body["agentic_controller_response"]
    assert compact["summary"]["route_status"] == "blocked"
    assert compact["summary"]["selected_workflow"] == "refactor.single_path"
    assert compact["summary"]["next_action"] == "none"
    assert compact["summary"]["approval_state_status"] == "not_created"
    assert compact["summary"]["approval_type"] == "none"
    assert compact["summary"]["target_repo_read"] is False
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["blockers"][0]["reason"] == "advanced_refactor_readiness_not_met"
    assert decision["approval_required_before"] == []
    assert "approval_state" not in compact["artifacts"]
    assert "downstream_result" not in compact["artifacts"]


def test_workflow_router_blocks_broad_prompt_even_after_ready_report(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    copy_runtime_config(config_root)
    reports = write_prerequisite_reports(config_root)
    report = run_advanced_refactor_readiness(readiness_config(config_root, reports))
    assert report["readiness_status"] == "pilot_ready"
    target = make_target_repo(tmp_path)
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(target,),
        port=0,
    )

    body = handle_workflow_router_chat_completion(
        {
            "model": "agentic-workflow-router",
            "messages": [
                {
                    "role": "user",
                    "content": f"In {target}, refactor the whole subsystem so all functions use only one code path.",
                }
            ],
        },
        config,
    )

    compact = body["agentic_controller_response"]
    assert compact["summary"]["route_status"] == "blocked"
    assert compact["summary"]["next_action"] == "none"
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert decision["blockers"][0]["reason"] == "advanced_refactor_pilot_scope_not_admitted"
    assert decision["blockers"][0]["pilot_scope_reason"] == "advanced_refactor_pilot_scope_too_broad"
    assert "approval_state" not in compact["artifacts"]
    assert "downstream_result" not in compact["artifacts"]


def test_workflow_router_allows_approval_gate_after_ready_report(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    copy_runtime_config(config_root)
    reports = write_prerequisite_reports(config_root)
    report = run_advanced_refactor_readiness(readiness_config(config_root, reports))
    assert report["readiness_status"] == "pilot_ready"
    target = make_target_repo(tmp_path)
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(target,),
        port=0,
    )

    body = handle_workflow_router_chat_completion(
        {
            "model": "agentic-workflow-router",
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"In {target}, refactor the placed_order_id stealth lookup so there is only one code path. "
                        "Start from the logic beginning point."
                    ),
                }
            ],
        },
        config,
    )

    compact = body["agentic_controller_response"]
    assert compact["summary"]["route_status"] == "ready"
    assert compact["summary"]["selected_workflow"] == "refactor.single_path"
    assert compact["summary"]["next_action"] == "request_approval"
    assert compact["summary"]["approval_type"] == "packet_design"
    assert compact["summary"]["target_repo_read"] is True
