from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vllm_agent_gateway.controller_service.server import (
    ControllerOutputFormat,
    assistant_content_for_controller_response,
)


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "chat_response_contract" / "format_a_required_markers.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def required_markers() -> dict[str, list[str]]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def response_with_code_explanation(tmp_path: Path) -> dict[str, Any]:
    route_decision_path = tmp_path / "route-decision.json"
    code_explanation_path = tmp_path / "code-explanation.json"
    write_json(
        route_decision_path,
        {
            "kind": "workflow_route_decision",
            "schema_version": 1,
            "selected_workflow": "code_investigation.plan",
            "selected_skills": ["code-explanation-summarizer"],
            "selected_tools": ["structure_index", "git_grep", "read_file"],
            "next_action": "none",
        },
    )
    write_json(
        code_explanation_path,
        {
            "kind": "code_explanation",
            "status": "ready",
            "target": {
                "path": "core/stealth_order_manager.py",
                "symbol": "find_stealth_order_by_placed_order_id",
            },
            "summary": "Looks up a stealth order by placed order id.",
            "key_inputs": [{"name": "placed_order_id", "role": "lookup key"}],
            "outputs": [{"description": "matching stealth order or None"}],
            "side_effects": [{"kind": "read", "target": "_placed_order_index"}],
            "related_tests": [{"path": "tests/unit/test_order_id_and_followup_rules.py", "line": 42}],
            "source_refs": [{"path": "core/stealth_order_manager.py", "line": 120}],
        },
    )
    return {
        "run_id": "workflow-router-test",
        "workflow": "workflow_router.plan",
        "status": "completed",
        "summary": {
            "route_status": "ready",
            "selected_workflow": "code_investigation.plan",
            "next_action": "none",
            "verification_command_count": 1,
        },
        "artifacts": {
            "route_decision": str(route_decision_path),
            "downstream_code_explanation": str(code_explanation_path),
        },
        "warning_count": 0,
        "warnings": [],
        "failure_count": 0,
        "failures": [],
        "run_lookup": "/v1/controller/runs/workflow-router-test",
    }


def test_format_a_contract_renders_result_answer_before_artifacts(tmp_path: Path) -> None:
    markers = required_markers()
    content = assistant_content_for_controller_response(
        response_with_code_explanation(tmp_path),
        ControllerOutputFormat.FORMAT_A,
    )

    for marker in markers["format_a_contract_markers"] + markers["read_only_answer_markers"]:
        assert marker in content
    assert "- Selected workflow: code_investigation.plan" in content
    assert "- Selected skills: code-explanation-summarizer" in content
    assert "- Selected tools: structure_index; git_grep; read_file" in content
    assert "- Verification: 1 command(s)" in content
    assert content.index("Result:") < content.index("Answer:") < content.index("Artifacts:")
    assert content.strip().splitlines()[0] != "Artifacts:"


def test_json_output_includes_same_chat_contract(tmp_path: Path) -> None:
    rendered = assistant_content_for_controller_response(
        response_with_code_explanation(tmp_path),
        ControllerOutputFormat.JSON,
    )
    parsed = json.loads(rendered)

    assert parsed["output_format"] == "json"
    assert parsed["chat_contract"]["workflow"] == "workflow_router.plan"
    assert parsed["chat_contract"]["selected_workflow"] == "code_investigation.plan"
    assert parsed["chat_contract"]["selected_skills"] == ["code-explanation-summarizer"]
    assert parsed["chat_contract"]["selected_tools"] == ["structure_index", "git_grep", "read_file"]
    assert parsed["chat_contract"]["verification_command_count"] == 1


def test_format_a_skill_lifecycle_audit_is_not_artifact_only(tmp_path: Path) -> None:
    markers = required_markers()
    audit_path = tmp_path / "skill-lifecycle-audit.json"
    write_json(
        audit_path,
        {
            "kind": "skill_lifecycle_audit",
            "status": "ready",
            "summary": {
                "skill_count": 46,
                "status_counts": {"validated": 46},
                "queue_counts": {"no_action": 46},
                "blocker_count": 0,
                "orphan_eval_case_count": 0,
                "runtime_registry_changed": False,
                "target_repository_changed": False,
            },
            "action_queue": [],
        },
    )
    response = {
        "run_id": "skill-lifecycle-test",
        "workflow": "skill_lifecycle.audit",
        "status": "completed",
        "summary": {"audit_status": "passed", "next_action": "none"},
        "artifacts": {"skill_lifecycle_audit": str(audit_path)},
        "warning_count": 0,
        "failure_count": 0,
    }

    content = assistant_content_for_controller_response(response, ControllerOutputFormat.FORMAT_A)

    for marker in markers["format_a_contract_markers"] + markers["skill_lifecycle_markers"]:
        assert marker in content
    assert "- Selected workflow: skill_lifecycle.audit" in content
    assert "- Selected skills: none" in content
    assert "- Selected tools: none" in content
    assert content.index("Result:") < content.index("Lifecycle Audit:") < content.index("Artifacts:")


def test_format_a_long_sections_are_bounded_with_omitted_markers() -> None:
    markers = required_markers()
    response = {
        "run_id": "bounded-response-test",
        "workflow": "workflow_router.plan",
        "status": "completed",
        "summary": {f"summary_field_{index:02d}": index for index in range(40)},
        "artifacts": {f"artifact_{index:02d}": f"/tmp/artifact-{index}.json" for index in range(40)},
        "warning_count": 0,
        "failure_count": 0,
    }

    content = assistant_content_for_controller_response(response, ControllerOutputFormat.FORMAT_A)

    for marker in markers["truncation_markers"]:
        assert marker in content
    assert "omitted 16 summary field(s)" in content
    assert "omitted 30 artifact(s)" in content
