from __future__ import annotations

import json
from pathlib import Path

from vllm_agent_gateway.acceptance.no_manual_skill_injection_explainability import (
    DEFAULT_POLICY_PATH,
    NoManualSkillInjectionExplainabilityConfig,
    default_report_path,
    phase204_case_from_prompt,
    prompt_contract_errors,
    read_json_object,
    validate_report,
    validate_no_manual_skill_injection_explainability,
    validate_text_against_phase204_case,
)
from vllm_agent_gateway.controllers.workflow_router.plan import WorkflowRouterPlanRequest, route_request
from vllm_agent_gateway.prompt_catalogs import load_prompt_catalog, prompt_cases_from_catalog


REPO_ROOT = Path(__file__).resolve().parents[2]
MATRIX_REPORT_PATH = REPO_ROOT / "runtime-state" / "phase203" / "phase203-workflow-skill-tool-selection-matrix-report.json"


def load_policy() -> dict:
    return read_json_object(REPO_ROOT / DEFAULT_POLICY_PATH)


def load_matrix() -> dict:
    return json.loads(MATRIX_REPORT_PATH.read_text(encoding="utf-8"))


def test_phase204_offline_policy_and_prompt_contract_pass(tmp_path: Path) -> None:
    report = validate_no_manual_skill_injection_explainability(
        NoManualSkillInjectionExplainabilityConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase204-offline.json",
        )
    )

    assert report["status"] == "preflight_passed"
    assert report["mode"] == "offline"
    assert report["phase_closeout_eligible"] is False
    assert report["summary"]["case_count"] == 33
    assert report["summary"]["matrix_row_coverage_count"] >= 25
    assert report["summary"]["prompt_contract_error_count"] == 0
    assert report["summary"]["phase205_holdout_replay_still_required"] is True


def test_phase204_default_preflight_path_does_not_overlap_live_closeout_path() -> None:
    preflight_path = default_report_path(REPO_ROOT, live=False)
    live_path = default_report_path(REPO_ROOT, live=True)

    assert preflight_path != live_path
    assert "preflight" in preflight_path.name
    assert "preflight" not in live_path.name


def test_phase204_rejects_prompt_that_names_skill_id(tmp_path: Path) -> None:
    policy = load_policy()
    catalog = load_prompt_catalog(REPO_ROOT, Path(policy["source_prompt_catalog_path"]))
    catalog["cases"][0]["prompt"] += " Use entrypoint-finder."
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    policy = dict(policy)
    policy["source_prompt_catalog_path"] = str(catalog_path)
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    report = validate_no_manual_skill_injection_explainability(
        NoManualSkillInjectionExplainabilityConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            output_path=tmp_path / "phase204-skill-id-failure.json",
        )
    )

    assert report["status"] == "failed"
    assert any("explicitly names skill id" in error for error in report["prompt_contract_errors"])


def test_phase204_rejects_prompt_that_names_internal_workflow(tmp_path: Path) -> None:
    policy = load_policy()
    catalog = load_prompt_catalog(REPO_ROOT, Path(policy["source_prompt_catalog_path"]))
    catalog["cases"][0]["prompt"] += " Route with code_investigation.plan."
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    policy = dict(policy)
    policy["source_prompt_catalog_path"] = str(catalog_path)
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    report = validate_no_manual_skill_injection_explainability(
        NoManualSkillInjectionExplainabilityConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            output_path=tmp_path / "phase204-internal-workflow-failure.json",
        )
    )

    assert report["status"] == "failed"
    assert any("forbidden internal marker" in error for error in report["prompt_contract_errors"])


def test_phase204_rejects_response_missing_selected_skill() -> None:
    policy = load_policy()
    matrix = load_matrix()
    catalog = load_prompt_catalog(REPO_ROOT, Path(policy["source_prompt_catalog_path"]))
    case = prompt_cases_from_catalog(catalog)[0]
    matrix_record = next(item for item in matrix["matrix_records"] if item["route_rule"] == case.expected_rule)
    phase_case = phase204_case_from_prompt(case, matrix_record)
    text = "\n".join(
        [
            "Result:",
            "- Selected workflow: code_investigation.plan",
            "- Selected skills: context-plan-builder",
            "- Selected tools: git_grep, read_file, structure_index",
            "Skill Selection:",
            "- Why: matched the prompt family.",
            "- Route rules: l1_find_behavior_start_terms",
            "- Confidence: medium",
            "- Coverage entries: L1-001",
            "- Skills: context-plan-builder",
            "- Tools: git_grep, read_file, structure_index",
            "- Rejected candidates: workflows 2, skills 4, tools 3",
            "- Grounded in: route_decision.selected_skills, route_decision.selected_tools, route_decision.selection_audit, registry_snapshot.skills",
        ]
    )
    route_decision = {
        "status": "ready",
        "selected_workflow": "code_investigation.plan",
        "selected_skills": ["context-plan-builder"],
        "selected_tools": ["git_grep", "read_file", "structure_index"],
        "selection_audit": {
            "selected": {"route_rules": ["l1_find_behavior_start_terms"]},
            "workflow_candidates": {"rejected_count": 2},
            "skill_candidates": {"rejected_count": 4},
            "tool_candidates": {"rejected_count": 3},
            "selection_policy": {
                "metadata_only": True,
                "manual_skill_injection_required": False,
                "low_confidence_fails_closed": True,
                "minimum_confidence": "medium",
            },
        },
        "evidence": [{"source": "workflow_registry"}, {"source": "skill_registry"}],
    }
    registry_snapshot = {"skills": {"entrypoint-finder": {}}, "tools": {"git_grep": {}}}

    errors = validate_text_against_phase204_case(
        policy=policy,
        case=phase_case,
        text=text,
        route_decision=route_decision,
        registry_snapshot=registry_snapshot,
    )

    assert any("missing expected selected skill entrypoint-finder" in error for error in errors)


def test_phase204_rejects_missing_rejected_candidate_visibility() -> None:
    policy = load_policy()
    matrix = load_matrix()
    catalog = load_prompt_catalog(REPO_ROOT, Path(policy["source_prompt_catalog_path"]))
    case = prompt_cases_from_catalog(catalog)[0]
    matrix_record = next(item for item in matrix["matrix_records"] if item["route_rule"] == case.expected_rule)
    phase_case = phase204_case_from_prompt(case, matrix_record)
    text = "\n".join(
        [
            "Result:",
            "- Selected workflow: code_investigation.plan",
            "- Selected skills: entrypoint-finder, context-plan-builder",
            "- Selected tools: git_grep, read_file, structure_index",
            "Skill Selection:",
            "- Why: matched the prompt family.",
            "- Route rules: l1_find_behavior_start_terms",
            "- Confidence: medium",
            "- Coverage entries: L1-001",
            "- Skills: entrypoint-finder, context-plan-builder",
            "- Tools: git_grep, read_file, structure_index",
            "- Rejected candidates: workflows 0, skills 0, tools 0",
            "- Grounded in: route_decision.selected_skills, route_decision.selected_tools, route_decision.selection_audit, registry_snapshot.skills",
        ]
    )
    route_decision = {
        "status": "ready",
        "selected_workflow": "code_investigation.plan",
        "selected_skills": ["entrypoint-finder", "context-plan-builder"],
        "selected_tools": ["git_grep", "read_file", "structure_index"],
        "selection_audit": {
            "selected": {"route_rules": ["l1_find_behavior_start_terms"]},
            "workflow_candidates": {"rejected_count": 0},
            "skill_candidates": {"rejected_count": 0},
            "tool_candidates": {"rejected_count": 0},
            "selection_policy": {
                "metadata_only": True,
                "manual_skill_injection_required": False,
                "low_confidence_fails_closed": True,
                "minimum_confidence": "medium",
            },
        },
        "evidence": [{"source": "workflow_registry"}, {"source": "skill_registry"}],
    }
    registry_snapshot = {"skills": {"entrypoint-finder": {}}, "tools": {"git_grep": {}}}

    errors = validate_text_against_phase204_case(
        policy=policy,
        case=phase_case,
        text=text,
        route_decision=route_decision,
        registry_snapshot=registry_snapshot,
    )

    assert any("workflow_rejected_count below minimum" in error for error in errors)
    assert any("skill_rejected_count below minimum" in error for error in errors)
    assert any("tool_rejected_count below minimum" in error for error in errors)


def test_phase204_prompt_contract_requires_matrix_coverage_floor(tmp_path: Path) -> None:
    policy = load_policy()
    catalog = load_prompt_catalog(REPO_ROOT, Path(policy["source_prompt_catalog_path"]))
    cases = prompt_cases_from_catalog(catalog)[:1]

    errors = prompt_contract_errors(policy=policy, cases=cases, matrix_report=load_matrix())

    assert any("matrix row coverage" in error for error in errors)


def test_phase204_allows_partial_case_filter_for_debug_smoke(tmp_path: Path) -> None:
    report = validate_no_manual_skill_injection_explainability(
        NoManualSkillInjectionExplainabilityConfig(
            config_root=REPO_ROOT,
            case_ids=("P01",),
            allow_partial=True,
            output_path=tmp_path / "phase204-partial.json",
        )
    )

    assert report["status"] == "preflight_passed"
    assert report["partial_case_filter"] is True
    assert report["summary"]["case_count"] == 1


def founder_case(case_id: str) -> dict:
    catalog = load_prompt_catalog(REPO_ROOT, Path(load_policy()["source_prompt_catalog_path"]))
    return next(item for item in catalog["cases"] if item["case_id"] == case_id)


def route_founder_case(case_id: str) -> dict:
    case = founder_case(case_id)
    return route_request(
        WorkflowRouterPlanRequest(
            config_root=REPO_ROOT,
            target_root=case["target_root"],
            user_request=case["prompt"],
        ),
        {"max_model_calls": 3, "max_selected_skills": 5, "max_selected_tools": 5},
    )


def test_phase204_router_promotes_coverage_skill_for_behavior_exists_prompt() -> None:
    decision = route_founder_case("P04")

    assert "behavior-existence-checker" in decision["selected_skills"]
    assert decision["selection_audit"]["selected"]["coverage_entry_ids"] == ["L1-006"]


def test_phase204_router_promotes_coverage_tool_for_request_flow_prompt() -> None:
    decision = route_founder_case("P19")

    assert "request-flow-mapper" in decision["selected_skills"]
    assert {"git_grep", "read_file", "structure_index"} <= set(decision["selected_tools"])
    assert "codegraph_context" not in decision["selected_tools"]
    assert decision["selection_audit"]["selected"]["coverage_entry_ids"] == ["L2-007"]


def test_phase204_router_promotes_execution_planning_coverage_skill() -> None:
    decision = route_founder_case("P23")

    assert "implementation-packet-designer" in decision["selected_skills"]
    assert decision["selection_audit"]["selected"]["coverage_entry_ids"] == ["L1-010"]


def test_phase204_live_report_requires_every_case_on_every_surface() -> None:
    policy = load_policy()
    case_ids = policy["case_ids"]
    results = [
        {"case_id": case_id, "surface": "gateway", "status": "passed"}
        for case_id in case_ids
    ]
    results.append({"case_id": case_ids[0], "surface": "anythingllm", "status": "passed"})
    report = {
        "schema_version": 1,
        "kind": "no_manual_skill_injection_explainability_report",
        "phase": 204,
        "priority_backlog_id": "P0-M3-204",
        "status": "passed",
        "mode": "live",
        "partial_case_filter": False,
        "summary": {
            "case_count": len(case_ids),
            "case_ids": case_ids,
            "matrix_row_coverage_count": 25,
            "policy_error_count": 0,
            "prompt_contract_error_count": 0,
            "surfaces": ["anythingllm", "gateway"],
        },
        "results": results,
    }

    errors = validate_report(report, policy)

    assert any("missing required case/surface pair" in error for error in errors)
    assert any("response_count" in error for error in errors)
