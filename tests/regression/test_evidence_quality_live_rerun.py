from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.evidence_quality_live_rerun import (
    DEFAULT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_PREFLIGHT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_PREFLIGHT_OUTPUT_PATH,
    EvidenceQualityLiveRerunConfig,
    case_requirements_by_id,
    default_markdown_output_path,
    default_output_path,
    phase206_cases,
    phase207_cases_by_audit_id,
    prompt_for_root,
    read_json_object,
    validate_evidence_quality_live_rerun,
    validate_live_response,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "evidence_quality_live_rerun_policy.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_phase208_default_report_paths_keep_live_proof_separate_from_preflight() -> None:
    assert default_output_path(live=True) == DEFAULT_OUTPUT_PATH
    assert default_output_path(live=False) == DEFAULT_PREFLIGHT_OUTPUT_PATH
    assert default_markdown_output_path(live=True) == DEFAULT_MARKDOWN_OUTPUT_PATH
    assert default_markdown_output_path(live=False) == DEFAULT_PREFLIGHT_MARKDOWN_OUTPUT_PATH
    assert DEFAULT_OUTPUT_PATH != DEFAULT_PREFLIGHT_OUTPUT_PATH
    assert DEFAULT_MARKDOWN_OUTPUT_PATH != DEFAULT_PREFLIGHT_MARKDOWN_OUTPUT_PATH


def test_phase208_policy_preflight_passes(tmp_path: Path) -> None:
    report = validate_evidence_quality_live_rerun(
        EvidenceQualityLiveRerunConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase208-report.json",
            markdown_output_path=tmp_path / "phase208-report.md",
            live=False,
        )
    )

    assert report["status"] == "preflight_passed"
    assert report["summary"]["audit_case_count"] == 4
    assert report["summary"]["holdout_case_count"] == 4
    assert report["summary"]["live_case_count"] == 8
    assert report["summary"]["target_root_count"] == 2
    assert report["summary"]["surface_count"] == 2
    assert report["summary"]["response_count"] == 0


def test_phase208_prompt_mirroring_covers_non_git_fixture() -> None:
    policy = read_json_object(POLICY_PATH)
    case = phase206_cases(REPO_ROOT, policy)[0]

    prompt = prompt_for_root(case, "/mnt/c/coinbase_testing_repo_frozen_tmp")

    assert "/mnt/c/coinbase_testing_repo_frozen_tmp.github" not in prompt
    assert "/mnt/c/coinbase_testing_repo_frozen_tmp" in prompt


def test_phase208_live_response_requires_visible_phase207_source_ref(tmp_path: Path) -> None:
    policy = read_json_object(POLICY_PATH)
    audit_case = phase206_cases(REPO_ROOT, policy)[0]
    requirement = case_requirements_by_id(policy)["P206-EV-001"]
    phase207_by_id = phase207_cases_by_audit_id(REPO_ROOT, policy)
    route_decision_path = tmp_path / "route-decision.json"
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
        investigation_plan_path,
        {
            "kind": "code_investigation_plan",
            "status": "ready",
            "source_refs": [{"path": "core/stealth_order_manager.py", "line": 4169}],
        },
    )
    run_record = {
        "run_id": "phase208-test",
        "status": "completed",
        "summary": {
            "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
            "selected_workflow": "code_investigation.plan",
            "downstream_status": "completed",
            "source_changed": False,
        },
        "failure_count": 0,
        "artifacts": {
            "route_decision": str(route_decision_path),
            "downstream_investigation_plan": str(investigation_plan_path),
        },
    }
    text = "\n".join(
        [
            "Answer:",
            "- Beginning point: core/stealth_order_manager.py",
            "- Related tests: tests/unit/test_order_id_and_followup_rules.py",
            "- Recommended commands: python -m pytest tests/unit/test_order_id_and_followup_rules.py",
            "- Source refs: core/stealth_order_manager.py",
            "- Source mutation: false",
            "Skill Selection:",
            "- Confidence: medium",
            "Context Sources:",
            "Artifacts:",
        ]
    )

    result = validate_live_response(
        policy=policy,
        audit_case=audit_case,
        baseline_case=audit_case,
        requirement=requirement,
        phase207_by_id=phase207_by_id,
        surface="gateway",
        target_root="/mnt/c/coinbase_testing_repo_frozen_tmp.github",
        text=text,
        run_record=run_record,
        run_id="phase208-test",
    )

    assert result["status"] == "failed"
    assert any("Phase 207 source proof" in error for error in result["errors"])


def test_phase208_live_response_passes_with_visible_phase207_source_ref(tmp_path: Path) -> None:
    policy = read_json_object(POLICY_PATH)
    audit_case = phase206_cases(REPO_ROOT, policy)[0]
    requirement = case_requirements_by_id(policy)["P206-EV-001"]
    phase207_by_id = phase207_cases_by_audit_id(REPO_ROOT, policy)
    route_decision_path = tmp_path / "route-decision.json"
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
        investigation_plan_path,
        {
            "kind": "code_investigation_plan",
            "status": "ready",
            "source_refs": [{"path": "core/stealth_order_manager.py", "line": 4169}],
        },
    )
    run_record = {
        "run_id": "phase208-test",
        "status": "completed",
        "summary": {
            "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
            "selected_workflow": "code_investigation.plan",
            "downstream_status": "completed",
            "source_changed": False,
        },
        "failure_count": 0,
        "artifacts": {
            "route_decision": str(route_decision_path),
            "downstream_investigation_plan": str(investigation_plan_path),
        },
    }
    text = "\n".join(
        [
            "Answer:",
            "- Beginning point: core/stealth_order_manager.py:4169",
            "- Related tests: tests/unit/test_order_id_and_followup_rules.py:8",
            "- Recommended commands: python -m pytest tests/unit/test_order_id_and_followup_rules.py",
            "- Source refs: core/stealth_order_manager.py:4169",
            "- Source mutation: false",
            "Skill Selection:",
            "- Confidence: medium",
            "Context Sources:",
            "Artifacts:",
        ]
    )

    result = validate_live_response(
        policy=policy,
        audit_case=audit_case,
        baseline_case=audit_case,
        requirement=requirement,
        phase207_by_id=phase207_by_id,
        surface="gateway",
        target_root="/mnt/c/coinbase_testing_repo_frozen_tmp.github",
        text=text,
        run_record=run_record,
        run_id="phase208-test",
    )

    assert result["status"] == "passed"
    assert "core/stealth_order_manager.py:4169" in result["visible_source_ref_hits"]
    assert result["target_root_proofs"]
    assert result["source_hash_revalidated_count"] >= 1
    assert result["baseline_comparison"]["score"] >= 80
