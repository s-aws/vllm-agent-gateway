from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.skill_tool_selection_explainability_e2e import (
    DEFAULT_POLICY_PATH,
    SkillToolSelectionExplainabilityE2EConfig,
    run_skill_tool_selection_explainability_e2e,
    validate_policy,
    validate_text_against_route,
)
from vllm_agent_gateway.acceptance.current_model_compatibility_matrix import read_json_object


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def route_decision() -> dict[str, Any]:
    return {
        "kind": "workflow_route_decision",
        "schema_version": 1,
        "status": "ready",
        "selected_workflow": "code_investigation.plan",
        "confidence": "medium",
        "selected_skills": ["related-test-discovery"],
        "selected_tools": ["git_grep", "read_file"],
        "evidence": [
            {"source": "workflow_registry", "selected_workflow": "code_investigation.plan"},
            {
                "source": "skill_registry",
                "selected_skills": ["related-test-discovery"],
                "capability_route_keys": {"related-test-discovery": "test.related_discovery"},
            },
        ],
        "selection_audit": {
            "selection_policy": {
                "metadata_only": True,
                "manual_skill_injection_required": False,
                "low_confidence_fails_closed": True,
                "minimum_confidence": "medium",
            },
            "selected": {
                "workflow_id": "code_investigation.plan",
                "confidence": "medium",
                "confidence_reasons": ["prompt_skill_coverage_match"],
                "route_rules": ["l1_find_related_tests_terms"],
                "coverage_entry_ids": ["L1-003"],
            },
            "workflow_candidates": {
                "rejected": [{"workflow_id": "code_context.lookup"}],
                "rejected_count": 1,
            },
            "skill_candidates": {
                "rejected": [{"skill_id": "code-explanation-summarizer"}],
                "rejected_count": 1,
            },
            "tool_candidates": {
                "rejected": [{"tool_id": "structure_index"}],
                "rejected_count": 1,
            },
        },
    }


def registry_snapshot() -> dict[str, Any]:
    return {
        "skills": {
            "related-test-discovery": {
                "description": "Find related tests.",
                "capability_contract": {"route_key": "test.related_discovery"},
            }
        },
        "tools": {
            "git_grep": {"description": "Search files."},
            "read_file": {"description": "Read a selected file."},
        },
    }


def case() -> dict[str, Any]:
    return {
        "case_id": "SEL-001",
        "expected_selected_workflow": "code_investigation.plan",
        "expected_selected_skills": ["related-test-discovery"],
        "expected_selected_tools": ["git_grep", "read_file"],
        "expected_route_rules": ["l1_find_related_tests_terms"],
    }


def valid_text() -> str:
    return "\n".join(
        [
            "I completed workflow_router.plan.",
            "workflow_router.plan completed",
            "run_id: workflow-router-test",
            "",
            "Result:",
            "- Workflow: workflow_router.plan",
            "- Status: completed",
            "- Selected workflow: code_investigation.plan",
            "- Selected skills: related-test-discovery",
            "- Selected tools: git_grep; read_file",
            "- Next action: none",
            "",
            "Skill Selection:",
            "- Why: Selected code_investigation.plan because router rule(s) matched: l1_find_related_tests_terms.",
            "- Route rules: l1_find_related_tests_terms",
            "- Confidence: medium (prompt_skill_coverage_match)",
            "- Coverage entries: L1-003",
            "- Skills: related-test-discovery (test.related_discovery)",
            "- Tools: git_grep; read_file",
            "- Rejected candidates: workflows 1; skills 1; tools 1",
            "- Grounded in: route_decision.evidence; route_decision.selected_skills; route_decision.selected_tools; route_decision.selection_audit; registry_snapshot.skills",
            "",
            "Artifacts:",
            "- route_decision: /tmp/route-decision.json",
        ]
    )


def test_skill_tool_selection_explainability_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_skill_tool_selection_explainability_policy_rejects_missing_anythingllm_surface() -> None:
    mutated = copy.deepcopy(policy())
    mutated["required_surfaces"] = ["gateway"]

    errors = validate_policy(mutated)

    assert "policy.required_surfaces must be gateway and anythingllm" in errors


def test_validate_text_against_route_passes_for_visible_selection_evidence() -> None:
    errors = validate_text_against_route(
        policy=policy(),
        case=case(),
        target_root="/mnt/c/coinbase_testing_repo_frozen_tmp",
        surface="gateway",
        text=valid_text(),
        route_decision=route_decision(),
        registry_snapshot=registry_snapshot(),
    )

    assert errors == []


def test_validate_text_against_route_rejects_missing_rejected_counts() -> None:
    text = valid_text().replace("- Rejected candidates: workflows 1; skills 1; tools 1", "- Rejected candidates: none")

    errors = validate_text_against_route(
        policy=policy(),
        case=case(),
        target_root="/mnt/c/coinbase_testing_repo_frozen_tmp",
        surface="gateway",
        text=text,
        route_decision=route_decision(),
        registry_snapshot=registry_snapshot(),
    )

    assert any("missing rejected candidate fragment workflows 1" in error for error in errors)
    assert any("missing rejected candidate fragment skills 1" in error for error in errors)
    assert any("missing rejected candidate fragment tools 1" in error for error in errors)


def test_validate_text_against_route_rejects_raw_internal_json() -> None:
    text = valid_text() + '\n"selection_audit": {"workflow_candidates": []}\n'

    errors = validate_text_against_route(
        policy=policy(),
        case=case(),
        target_root="/mnt/c/coinbase_testing_repo_frozen_tmp",
        surface="gateway",
        text=text,
        route_decision=route_decision(),
        registry_snapshot=registry_snapshot(),
    )

    assert any('exposed raw internal marker "selection_audit"' in error for error in errors)


def test_validate_text_against_route_rejects_selected_skill_missing_from_registry_snapshot() -> None:
    snapshot = registry_snapshot()
    snapshot["skills"] = {}

    errors = validate_text_against_route(
        policy=policy(),
        case=case(),
        target_root="/mnt/c/coinbase_testing_repo_frozen_tmp",
        surface="gateway",
        text=valid_text(),
        route_decision=route_decision(),
        registry_snapshot=snapshot,
    )

    assert any("registry_snapshot.skills missing selected skill related-test-discovery" in error for error in errors)


def test_validate_text_against_route_rejects_selected_tool_missing_from_registry_snapshot() -> None:
    snapshot = registry_snapshot()
    snapshot["tools"] = {"read_file": snapshot["tools"]["read_file"]}

    errors = validate_text_against_route(
        policy=policy(),
        case=case(),
        target_root="/mnt/c/coinbase_testing_repo_frozen_tmp",
        surface="gateway",
        text=valid_text(),
        route_decision=route_decision(),
        registry_snapshot=snapshot,
    )

    assert any("registry_snapshot.tools missing selected tool git_grep" in error for error in errors)


def test_phase151_report_fails_when_required_live_surfaces_are_skipped(tmp_path: Path) -> None:
    report = run_skill_tool_selection_explainability_e2e(
        SkillToolSelectionExplainabilityE2EConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase151-report.json",
            markdown_output_path=tmp_path / "phase151-report.md",
            target_roots=("/mnt/c/coinbase_testing_repo_frozen_tmp",),
            include_gateway=False,
            include_anythingllm=False,
        )
    )

    assert report["status"] == "failed"
    assert "gateway validation is required by policy" in report["errors"]
    assert "AnythingLLM validation is required by policy" in report["errors"]
    assert (tmp_path / "phase151-report.md").exists()
