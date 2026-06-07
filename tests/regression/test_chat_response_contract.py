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
    registry_snapshot_path = tmp_path / "registry-snapshot.json"
    code_explanation_path = tmp_path / "code-explanation.json"
    write_json(
        route_decision_path,
        {
            "kind": "workflow_route_decision",
            "schema_version": 1,
            "confidence": "medium",
            "selected_workflow": "code_investigation.plan",
            "selected_skills": ["code-explanation-summarizer"],
            "selected_tools": ["structure_index", "git_grep", "read_file"],
            "next_action": "none",
            "selection_audit": {
                "schema_version": 1,
                "selection_policy": {
                    "source": "workflow_router.registry_metadata",
                    "metadata_only": True,
                    "minimum_confidence": "medium",
                    "low_confidence_fails_closed": True,
                    "manual_skill_injection_required": False,
                },
                "selected": {
                    "workflow_id": "code_investigation.plan",
                    "confidence": "medium",
                    "confidence_reasons": [
                        "confidence:medium",
                        "workflow:code_investigation.plan",
                        "router_rule_match",
                        "skill_registry_match",
                        "workflow_tool_policy_match",
                        "meets_minimum_confidence:medium",
                        "prompt_skill_coverage_match",
                    ],
                    "route_rules": ["l1_explain_code_terms"],
                    "evidence_sources": ["router_rule", "skill_registry", "workflow_registry"],
                    "coverage_entry_ids": ["L1-002"],
                },
                "coverage_matches": [
                    {
                        "entry_id": "L1-002",
                        "prompt_family": "L1-code-explanation",
                        "route_rule": "l1_explain_code_terms",
                        "selected_workflow": "code_investigation.plan",
                        "skill_overlap": ["code-explanation-summarizer"],
                        "tool_overlap": ["git_grep", "read_file", "structure_index"],
                    }
                ],
                "workflow_candidates": {
                    "selected": [{"workflow_id": "code_investigation.plan", "status": "selected"}],
                    "rejected": [{"workflow_id": "code_context.lookup", "status": "rejected"}],
                    "candidate_count": 2,
                    "rejected_count": 1,
                },
                "skill_candidates": {
                    "selected": [{"skill_id": "code-explanation-summarizer", "status": "selected"}],
                    "rejected": [{"skill_id": "related-test-discovery", "status": "rejected"}],
                    "candidate_count": 2,
                    "rejected_count": 1,
                },
                "tool_candidates": {
                    "selected": [
                        {"tool_id": "structure_index", "status": "selected"},
                        {"tool_id": "git_grep", "status": "selected"},
                        {"tool_id": "read_file", "status": "selected"},
                    ],
                    "rejected": [{"tool_id": "codegraph_context", "status": "rejected"}],
                    "candidate_count": 4,
                    "rejected_count": 1,
                },
            },
            "evidence": [
                {"source": "router_rule", "rule": "l1_explain_code_terms"},
                {
                    "source": "skill_registry",
                    "selection_basis": "capability_contract_shortlist",
                    "selected_skills": ["code-explanation-summarizer"],
                    "capability_route_keys": {"code-explanation-summarizer": "code.explanation_summary"},
                },
                {
                    "source": "workflow_registry",
                    "selected_workflow": "code_investigation.plan",
                    "description": "Controller-owned code investigation with bounded evidence.",
                },
            ],
        },
    )
    write_json(
        registry_snapshot_path,
        {
            "kind": "workflow_router_registry_snapshot",
            "schema_version": 1,
            "workflows": {
                "code_investigation.plan": {
                    "description": "Controller-owned code investigation with bounded evidence."
                }
            },
            "skills": {
                "code-explanation-summarizer": {
                    "description": "Explain a named function, class, or file from bounded code evidence.",
                    "capability_contract": {"route_key": "code.explanation_summary"},
                }
            },
            "tools": {
                "structure_index": {"description": "Build a deterministic bounded code structure index or slice."},
                "git_grep": {"description": "Search tracked repository content with line numbers."},
                "read_file": {"description": "Read a repository file selected by the controller."},
            },
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
            "registry_snapshot": str(registry_snapshot_path),
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

    for marker in (
        markers["format_a_contract_markers"]
        + markers["read_only_answer_markers"]
        + markers["skill_selection_markers"]
    ):
        assert marker in content
    assert "- Selected workflow: code_investigation.plan" in content
    assert "- Selected skills: code-explanation-summarizer" in content
    assert "- Selected tools: structure_index; git_grep; read_file" in content
    assert "- Verification: 1 command(s)" in content
    assert "Skill Selection:" in content
    assert "- Why: Selected code_investigation.plan" in content
    assert "- Route rules: l1_explain_code_terms" in content
    assert "- Confidence: medium" in content
    assert "- Coverage entries: L1-002" in content
    assert "- Rejected candidates: workflows 1; skills 1; tools 1" in content
    assert "- Skills: code-explanation-summarizer (code.explanation_summary)" in content
    assert content.index("Result:") < content.index("Skill Selection:") < content.index("Answer:") < content.index("Artifacts:")
    assert content.strip().splitlines()[0] != "Artifacts:"


def test_format_a_behavior_start_prefers_investigation_plan_over_cli_lookup(tmp_path: Path) -> None:
    route_decision_path = tmp_path / "route-decision.json"
    cli_lookup_path = tmp_path / "cli-entrypoint-lookup.json"
    investigation_plan_path = tmp_path / "investigation-plan.json"
    write_json(
        route_decision_path,
        {
            "kind": "workflow_route_decision",
            "selected_workflow": "code_investigation.plan",
            "evidence": [{"source": "router_rule", "rule": "l1_find_behavior_start_terms"}],
        },
    )
    write_json(
        cli_lookup_path,
        {
            "kind": "cli_entrypoint_lookup",
            "status": "ready",
            "target": "placed_order_id",
            "entrypoints": [
                {"path": "main.py", "line": 65, "kind": "python_main_guard", "command": ["python", "main.py"]}
            ],
            "mutation_policy": "read_only_no_source_mutation",
        },
    )
    write_json(
        investigation_plan_path,
        {
            "kind": "code_investigation_plan",
            "status": "ready",
            "likely_beginning_point": {
                "path": "core/stealth_order_manager.py",
                "line": 4169,
                "reason": "First source point with bounded exact-text evidence.",
            },
            "related_tests": [{"path": "tests/unit/test_order_id_and_followup_rules.py", "line": 8}],
            "verification_plan": {
                "verification_commands": [
                    {
                        "command": [
                            "python",
                            "-m",
                            "pytest",
                            "tests/unit/test_order_id_and_followup_rules.py",
                        ]
                    }
                ]
            },
        },
    )
    response = {
        "run_id": "workflow-router-behavior-start",
        "workflow": "workflow_router.plan",
        "status": "completed",
        "summary": {"selected_workflow": "code_investigation.plan", "downstream_status": "completed"},
        "artifacts": {
            "route_decision": str(route_decision_path),
            "downstream_cli_entrypoint_lookup": str(cli_lookup_path),
            "downstream_investigation_plan": str(investigation_plan_path),
        },
        "warning_count": 0,
        "failure_count": 0,
    }

    content = assistant_content_for_controller_response(response, ControllerOutputFormat.FORMAT_A)

    assert "Answer:" in content
    assert "- Beginning point: core/stealth_order_manager.py:4169" in content
    assert "- Related tests: tests/unit/test_order_id_and_followup_rules.py:8" in content
    assert "- Recommended commands: python -m pytest tests/unit/test_order_id_and_followup_rules.py" in content
    assert "- Entrypoints:" not in content


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
    assert parsed["chat_contract"]["selection_explanation"]["route_rules"] == ["l1_explain_code_terms"]
    assert parsed["chat_contract"]["selection_explanation"]["confidence"] == "medium"
    assert parsed["chat_contract"]["selection_explanation"]["coverage_entry_ids"] == ["L1-002"]
    assert parsed["selection_explanation"]["skills"][0]["route_key"] == "code.explanation_summary"


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
