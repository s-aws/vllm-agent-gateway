from __future__ import annotations

import json
from pathlib import Path

import pytest

from vllm_agent_gateway.run_inspector import (
    InspectorOutputFormat,
    RunInspectorConfig,
    RunObservabilityConfig,
    format_run_observability,
    format_run_inspection,
    inspect_run,
    observe_runs,
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")


def controller_record(
    root: Path,
    *,
    run_id: str,
    workflow: str,
    updated_at: str,
    route_decision_path: Path | None = None,
) -> None:
    artifacts = {"request": str(root / workflow / run_id / "request.json")}
    if route_decision_path is not None:
        artifacts["route_decision"] = str(route_decision_path)
    write_json(
        root / "controller-runs" / f"{run_id}.json",
        {
            "schema_version": 1,
            "kind": "controller_run_record",
            "updated_at": updated_at,
            "run_id": run_id,
            "workflow": workflow,
            "status": "completed",
            "summary": {
                "target_root": "/mnt/c/example",
                "route_status": "ready",
                "selected_workflow": "code_investigation.plan",
                "model_router_status": "available",
                "confidence": "medium",
                "downstream_workflow": "code_investigation.plan",
                "downstream_run_id": "code-investigation-20260606T000010000000Z",
                "downstream_status": "completed",
                "source_changed": False,
                "disposable_copy_changed": False,
            },
            "artifacts": artifacts,
            "warnings": [],
            "failures": [],
            "resume_key": {"run_state": str(root / workflow / run_id / "run-state.json")},
        },
    )


def test_run_inspector_selects_latest_workflow_run_and_loads_route_decision(tmp_path: Path) -> None:
    output_root = tmp_path / "controller-artifacts"
    route_path = output_root / "workflow-router" / "workflow-router-20260606T000010000000Z" / "route-decision.json"
    write_json(
        route_path,
        {
            "kind": "workflow_router_decision",
            "run_id": "workflow-router-20260606T000010000000Z",
            "status": "ready",
            "selected_workflow": "code_investigation.plan",
            "selected_skills": ["request-triage", "code-explanation-summarizer"],
            "selected_tools": ["structure_index", "read_file"],
            "evidence": [{"source": "router_rule", "rule": "l1_explain_code_terms"}],
            "downstream": {
                "workflow": "code_investigation.plan",
                "run_id": "code-investigation-20260606T000010000000Z",
                "status": "completed",
                "artifacts": {"code_explanation": "code-explanation.json"},
            },
        },
    )
    controller_record(
        output_root,
        run_id="workflow-router-20260606T000001000000Z",
        workflow="workflow_router.plan",
        updated_at="2026-06-06T00:00:01Z",
    )
    controller_record(
        output_root,
        run_id="workflow-router-20260606T000010000000Z",
        workflow="workflow_router.plan",
        updated_at="2026-06-06T00:00:10Z",
        route_decision_path=route_path,
    )
    controller_record(
        output_root,
        run_id="workflow-feedback-20260606T000020000000Z",
        workflow="workflow_feedback.record",
        updated_at="2026-06-06T00:00:20Z",
    )

    report_path = tmp_path / "inspection.json"
    report = inspect_run(
        RunInspectorConfig(
            config_root=tmp_path,
            controller_output_root=output_root,
            workflow="workflow_router.plan",
            output_path=report_path,
            output_format=InspectorOutputFormat.JSON,
        )
    )

    assert report["run_id"] == "workflow-router-20260606T000010000000Z"
    assert report["route"]["rules"] == ["l1_explain_code_terms"]
    assert report["selected_skills"] == ["request-triage", "code-explanation-summarizer"]
    assert report["selected_tools"] == ["structure_index", "read_file"]
    assert report["downstream"]["artifact_keys"] == ["code_explanation"]
    assert report["semantic_status"] == "completed_no_failures"
    assert report["mutation_proof"] == {
        "disposable_copy_changed": False,
        "source_changed": False,
        "target_root": "/mnt/c/example",
    }
    written = json.loads(report_path.read_text(encoding="utf-8"))
    assert written["kind"] == "controller_run_inspection"
    assert written["report_path"] == str(report_path.resolve())


def test_run_inspector_text_output_is_chat_reviewable(tmp_path: Path) -> None:
    output_root = tmp_path / "controller-artifacts"
    controller_record(
        output_root,
        run_id="workflow-router-20260606T000010000000Z",
        workflow="workflow_router.plan",
        updated_at="2026-06-06T00:00:10Z",
    )

    report = inspect_run(
        RunInspectorConfig(
            config_root=tmp_path,
            controller_output_root=output_root,
            run_id="workflow-router-20260606T000010000000Z",
        )
    )
    text = format_run_inspection(report)

    assert "Latest Run Inspection" in text
    assert "workflow-router-20260606T000010000000Z" in text
    assert "Semantic status: completed_no_failures" in text
    assert "Mutation proof:" in text


def test_run_inspector_missing_run_reports_clear_error(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="was not found"):
        inspect_run(
            RunInspectorConfig(
                config_root=tmp_path,
                controller_output_root=tmp_path / "controller-artifacts",
                run_id="workflow-router-missing",
            )
        )


def test_run_observability_reports_recent_workflow_router_runs(tmp_path: Path) -> None:
    output_root = tmp_path / "controller-artifacts"
    first_route = output_root / "workflow-router" / "workflow-router-20260606T000010000000Z" / "route-decision.json"
    second_route = output_root / "workflow-router" / "workflow-router-20260606T000020000000Z" / "route-decision.json"
    first_approval = output_root / "workflow-router" / "workflow-router-20260606T000010000000Z" / "approval-state.json"
    second_approval = output_root / "workflow-router" / "workflow-router-20260606T000020000000Z" / "approval-state.json"
    write_json(
        first_route,
        {
            "kind": "workflow_router_decision",
            "created_at": "2026-06-06T00:00:01Z",
            "run_id": "workflow-router-20260606T000010000000Z",
            "status": "ready",
            "selected_workflow": "refactor.single_path",
            "selected_skills": ["request-triage", "entrypoint-finder"],
            "selected_tools": ["structure_index", "read_file"],
            "evidence": [{"source": "router_rule", "rule": "single_path_refactor_terms"}],
            "next_action": "request_approval",
            "downstream": {"workflow": "refactor.single_path", "status": "completed", "artifacts": {"refactor_plan": "x"}},
        },
    )
    write_json(first_approval, {"status": "waiting_for_approval", "approval_type": "packet_design"})
    write_json(
        second_route,
        {
            "kind": "workflow_router_decision",
            "created_at": "2026-06-06T00:00:10Z",
            "run_id": "workflow-router-20260606T000020000000Z",
            "status": "ready",
            "selected_workflow": "execution_planning.plan",
            "selected_skills": ["request-triage", "execution-plan-writer"],
            "selected_tools": ["structure_index", "git_grep", "read_file"],
            "evidence": [{"source": "router_rule", "rule": "l1_small_text_edit_terms"}],
            "next_action": "none",
            "downstream": {"workflow": "execution_planning.plan", "status": "completed", "artifacts": {"report": "x"}},
        },
    )
    write_json(second_approval, {"status": "finished", "approval_type": "packet_design"})
    controller_record(
        output_root,
        run_id="workflow-router-20260606T000010000000Z",
        workflow="workflow_router.plan",
        updated_at="2026-06-06T00:00:04Z",
        route_decision_path=first_route,
    )
    first_record = output_root / "controller-runs" / "workflow-router-20260606T000010000000Z.json"
    first = json.loads(first_record.read_text(encoding="utf-8"))
    first["summary"]["selected_workflow"] = "refactor.single_path"
    first["summary"]["next_action"] = "request_approval"
    first["summary"]["approval_state_status"] = "waiting_for_approval"
    first["summary"]["approval_type"] = "packet_design"
    first["artifacts"]["approval_state"] = str(first_approval)
    write_json(first_record, first)
    controller_record(
        output_root,
        run_id="workflow-router-20260606T000020000000Z",
        workflow="workflow_router.plan",
        updated_at="2026-06-06T00:00:14Z",
        route_decision_path=second_route,
    )
    second_record = output_root / "controller-runs" / "workflow-router-20260606T000020000000Z.json"
    second = json.loads(second_record.read_text(encoding="utf-8"))
    second["summary"]["selected_workflow"] = "execution_planning.plan"
    second["summary"]["next_action"] = "none"
    second["summary"]["approval_state_status"] = "finished"
    second["summary"]["approval_type"] = "packet_design"
    second["artifacts"]["approval_state"] = str(second_approval)
    write_json(second_record, second)

    report_path = tmp_path / "observability.json"
    report = observe_runs(
        RunObservabilityConfig(
            config_root=tmp_path,
            controller_output_root=output_root,
            workflow="workflow_router.plan",
            limit=5,
            output_path=report_path,
            output_format=InspectorOutputFormat.JSON,
        )
    )

    assert report["kind"] == "controller_run_observability_report"
    assert report["metrics"]["run_count"] == 2
    assert report["metrics"]["by_approval_status"] == {"finished": 1, "waiting_for_approval": 1}
    assert report["metrics"]["by_selected_workflow"] == {"execution_planning.plan": 1, "refactor.single_path": 1}
    assert report["metrics"]["duration_seconds"]["max"] == 4.0
    assert report["runs"][0]["run_id"] == "workflow-router-20260606T000020000000Z"
    assert report["runs"][0]["model_router_status"] == "available"
    assert report["runs"][0]["approval_status"] == "finished"
    assert report["runs"][1]["approval_status"] == "waiting_for_approval"
    written = json.loads(report_path.read_text(encoding="utf-8"))
    assert written["report_path"] == str(report_path.resolve())


def test_run_observability_text_output_is_chat_reviewable(tmp_path: Path) -> None:
    output_root = tmp_path / "controller-artifacts"
    controller_record(
        output_root,
        run_id="workflow-router-20260606T000010000000Z",
        workflow="workflow_router.plan",
        updated_at="2026-06-06T00:00:10Z",
    )

    report = observe_runs(
        RunObservabilityConfig(
            config_root=tmp_path,
            controller_output_root=output_root,
            workflow="workflow_router.plan",
            limit=1,
        )
    )
    text = format_run_observability(report)

    assert "Run Observability Report" in text
    assert "Run count: 1" in text
    assert "Recent runs:" in text
    assert "model=available" in text
    assert "workflow-router-20260606T000010000000Z" in text


def test_run_observability_filters_by_supported_dimensions(tmp_path: Path) -> None:
    output_root = tmp_path / "controller-artifacts"
    route_path = output_root / "workflow-router" / "workflow-router-20260606T000010000000Z" / "route-decision.json"
    write_json(
        route_path,
        {
            "kind": "workflow_router_decision",
            "created_at": "2026-06-06T00:00:01Z",
            "run_id": "workflow-router-20260606T000010000000Z",
            "status": "blocked",
            "selected_workflow": "code_context.lookup",
            "selected_skills": ["documentation-lookup"],
            "selected_tools": ["read_file"],
            "evidence": [{"source": "router_rule", "rule": "l1_documentation_lookup_terms"}],
            "next_action": "none",
            "downstream": {"workflow": "code_context.lookup", "status": "blocked", "artifacts": {}},
        },
    )
    controller_record(
        output_root,
        run_id="workflow-router-20260606T000010000000Z",
        workflow="workflow_router.plan",
        updated_at="2026-06-06T00:00:04Z",
        route_decision_path=route_path,
    )
    record_path = output_root / "controller-runs" / "workflow-router-20260606T000010000000Z.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["summary"].update(
        {
            "target_root": "/mnt/c/fixture-a",
            "route_status": "blocked",
            "selected_workflow": "code_context.lookup",
            "model_router_status": "accepted",
            "downstream_workflow": "code_context.lookup",
            "downstream_status": "blocked",
        }
    )
    record["failures"] = [{"category": "prompt_miss", "message": "expected marker was absent"}]
    write_json(record_path, record)

    report = observe_runs(
        RunObservabilityConfig(
            config_root=tmp_path,
            controller_output_root=output_root,
            workflow="workflow_router.plan",
            limit=5,
            prompt_family="l1_documentation_lookup_terms",
            skill="documentation-lookup",
            model_status="accepted",
            target_root="/mnt/c/fixture-a",
            route_status="blocked",
            semantic_status="completed_with_failures",
            failure_category="prompt_miss",
        )
    )

    assert report["metrics"]["run_count"] == 1
    assert report["filters"]["failure_category"] == "prompt_miss"
    assert report["runs"][0]["failure_categories"] == ["prompt_miss"]


def test_run_observability_rejects_non_positive_limit(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="limit must be positive"):
        observe_runs(
            RunObservabilityConfig(
                config_root=tmp_path,
                controller_output_root=tmp_path / "controller-artifacts",
                limit=0,
            )
        )
