from __future__ import annotations

import json
from pathlib import Path

import pytest

from vllm_agent_gateway.run_inspector import (
    InspectorOutputFormat,
    RunInspectorConfig,
    format_run_inspection,
    inspect_run,
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
