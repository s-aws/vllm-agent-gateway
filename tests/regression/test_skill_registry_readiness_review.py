import json
from pathlib import Path

from vllm_agent_gateway.acceptance.skill_registry_readiness_review import (
    SkillRegistryReadinessConfig,
    build_skill_registry_readiness_report,
    run_skill_registry_readiness_review,
    validate_policy,
    validate_skill_registry_readiness_report,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def synthetic_policy(skill_count: int = 1, implemented_count: int = 1, planned_count: int = 1) -> dict:
    return {
        "schema_version": 1,
        "kind": "skill_registry_readiness_review_policy",
        "phase": 193,
        "priority_backlog_id": "P0-BB-057",
        "acceptance_marker": "PHASE193 SKILL REGISTRY READINESS REVIEW PASS",
        "required_source_paths": {
            "skill_registry": "runtime/skills.json",
            "skill_evals": "runtime/skill_evals.json",
            "prompt_skill_coverage": "runtime/prompt_skill_coverage.json",
            "workflows": "runtime/workflows.json",
            "tools": "runtime/tools.json",
        },
        "expected_counts": {
            "skill_count": skill_count,
            "eval_case_count": skill_count,
            "route_key_count": skill_count,
            "deprecated_skill_count": 0,
            "do_not_admit_count": 0,
            "prompt_coverage_entry_count": implemented_count + planned_count,
            "implemented_prompt_coverage_count": implemented_count,
            "planned_prompt_coverage_count": planned_count,
        },
        "decision_contract": {
            "allowed_decisions": ["keep", "split", "merge", "retire", "defer"],
            "required_report_fields": [
                "skill_id",
                "decision",
                "route_key",
                "route_namespace",
                "workflows",
                "safety_level",
                "mutation_policy",
                "eval_status",
                "coverage_entry_ids",
                "planned_coverage_entry_ids",
                "eval_case_ids",
                "readiness_evidence",
                "reasoning_summary",
                "recommended_next_action",
            ],
            "split_triggers": ["too_many_workflows", "too_many_task_types", "mixed_mutation_boundary"],
            "merge_triggers": ["semantic_intent_overlap", "duplicate_route_key", "duplicate_trigger_boundary"],
            "retire_triggers": ["deprecated", "missing_body", "unreferenced_invalid_eval"],
        },
        "scaling_requirements": {
            "metadata_only_selection": True,
            "no_body_reads_during_selection": True,
            "route_key_unique": True,
            "semantic_overlap_rejected": True,
            "batch_admission_required": True,
            "live_proof_required_before_validated": True,
        },
    }


def synthetic_skill(skill_id: str = "skill-a", workflows: list[str] | None = None) -> dict:
    workflows = workflows or ["code_investigation.plan"]
    return {
        "id": skill_id,
        "route_namespace": "code",
        "workflows": workflows,
        "safety_level": "read_only_planning",
        "triggers": ["find behavior start"],
        "eval_status": "validated",
        "capability_contract": {
            "route_key": f"code.{skill_id}",
            "task_types": ["task_a"],
            "input_artifacts": ["natural_user_request"],
            "output_artifacts": ["answer_a"],
            "approval_boundary": "none",
            "mutation_policy": "no_repository_mutation",
            "eval_case_ids": [f"{skill_id}_case"],
        },
        "problem_solving_steps": [1, 2],
    }


def synthetic_scale_report(skill_count: int) -> dict:
    return {
        "kind": "skill_scale_report",
        "status": "passed",
        "summary": {
            "skill_count": skill_count,
            "eval_case_count": skill_count,
            "route_key_count": skill_count,
            "deprecated_skill_count": 0,
            "do_not_admit_count": 0,
        },
    }


def synthetic_coverage_report(entry_count: int, implemented_count: int) -> dict:
    return {
        "kind": "prompt_skill_coverage_report",
        "status": "passed",
        "summary": {
            "entry_count": entry_count,
            "implemented_count": implemented_count,
        },
    }


def synthetic_sources(skill: dict | None = None, *, planned_count: int = 1) -> tuple[dict, dict, dict, dict]:
    skill = skill or synthetic_skill()
    implemented_entry = {
        "id": "L1-A",
        "status": "implemented",
        "prompt_family": "L1-a",
        "skill_ids": [skill["id"]],
    }
    planned_entries = [
        {
            "id": f"FX-{index}",
            "status": "planned",
            "prompt_family": f"fixture-{index}",
            "selected_workflow": "code_investigation.plan",
        }
        for index in range(planned_count)
    ]
    coverage_manifest = {"kind": "prompt_skill_coverage_registry", "entries": [implemented_entry, *planned_entries]}
    scale_report = synthetic_scale_report(1)
    coverage_report = synthetic_coverage_report(1 + planned_count, 1)
    return {skill["id"]: skill}, coverage_manifest, scale_report, coverage_report


def test_project_skill_registry_readiness_review_passes_current_artifacts(tmp_path: Path) -> None:
    report = run_skill_registry_readiness_review(
        SkillRegistryReadinessConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
            scale_report_path=tmp_path / "scale.json",
            coverage_report_path=tmp_path / "coverage.json",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["decision_counts"] == {"keep": 54}
    assert report["summary"]["planned_or_deferred_coverage_count"] == 2
    assert report["summary"]["semantic_conflict_count"] == 0


def test_skill_registry_readiness_policy_rejects_disabled_scaling_requirement() -> None:
    policy = synthetic_policy()
    policy["scaling_requirements"]["metadata_only_selection"] = False

    errors = validate_policy(policy)

    assert any(error["id"] == "scaling_requirements.metadata_only_selection" for error in errors)


def test_skill_registry_readiness_rejects_expected_count_drift(tmp_path: Path) -> None:
    policy = synthetic_policy(skill_count=99)
    skills, coverage_manifest, scale_report, coverage_report = synthetic_sources()

    report = build_skill_registry_readiness_report(
        config_root=tmp_path,
        policy=policy,
        skills=skills,
        coverage_manifest=coverage_manifest,
        skill_scale_report=scale_report,
        prompt_coverage_report=coverage_report,
    )

    assert report["status"] == "failed"
    assert any(error["id"] == "expected_counts.skill_count" for error in report["validation_errors"])


def test_skill_registry_readiness_rejects_oversized_skill_with_split_decision(tmp_path: Path) -> None:
    policy = synthetic_policy()
    skill = synthetic_skill(workflows=["w1", "w2", "w3", "w4", "w5", "w6"])
    skills, coverage_manifest, scale_report, coverage_report = synthetic_sources(skill)

    report = build_skill_registry_readiness_report(
        config_root=tmp_path,
        policy=policy,
        skills=skills,
        coverage_manifest=coverage_manifest,
        skill_scale_report=scale_report,
        prompt_coverage_report=coverage_report,
    )

    assert report["status"] == "failed"
    assert report["summary"]["decision_counts"]["split"] == 1
    assert any(error["id"] == "skills.blocking_decisions" for error in report["validation_errors"])


def test_skill_registry_readiness_rejects_duplicate_route_key_with_merge_decision(tmp_path: Path) -> None:
    first = synthetic_skill("skill-a")
    second = synthetic_skill("skill-b")
    second["capability_contract"]["route_key"] = first["capability_contract"]["route_key"]
    skills = {"skill-a": first, "skill-b": second}
    coverage_manifest = {"kind": "prompt_skill_coverage_registry", "entries": []}
    policy = synthetic_policy(skill_count=2, implemented_count=0, planned_count=0)
    scale_report = synthetic_scale_report(2)
    scale_report["summary"]["do_not_admit_count"] = 0
    coverage_report = synthetic_coverage_report(0, 0)

    report = build_skill_registry_readiness_report(
        config_root=tmp_path,
        policy=policy,
        skills=skills,
        coverage_manifest=coverage_manifest,
        skill_scale_report=scale_report,
        prompt_coverage_report=coverage_report,
    )

    assert report["status"] == "failed"
    assert report["summary"]["decision_counts"]["merge"] == 2
    assert any(error["id"].endswith(".route_key") for error in report["validation_errors"])


def test_skill_registry_readiness_rejects_duplicate_trigger_boundary_with_merge_decision(tmp_path: Path) -> None:
    first = synthetic_skill("skill-a")
    second = synthetic_skill("skill-b")
    second["triggers"] = list(first["triggers"])
    skills = {"skill-a": first, "skill-b": second}
    policy = synthetic_policy(skill_count=2, implemented_count=0, planned_count=0)

    report = build_skill_registry_readiness_report(
        config_root=tmp_path,
        policy=policy,
        skills=skills,
        coverage_manifest={"kind": "prompt_skill_coverage_registry", "entries": []},
        skill_scale_report=synthetic_scale_report(2),
        prompt_coverage_report=synthetic_coverage_report(0, 0),
    )

    assert report["status"] == "failed"
    assert report["summary"]["decision_counts"]["merge"] == 2
    assert all(record["readiness_evidence"]["duplicate_trigger_boundary"] for record in report["skill_decisions"])


def test_skill_registry_readiness_retires_missing_body(tmp_path: Path) -> None:
    skill = synthetic_skill()
    skill["body_present"] = False
    policy = synthetic_policy()
    skills, coverage_manifest, scale_report, coverage_report = synthetic_sources(skill)

    report = build_skill_registry_readiness_report(
        config_root=tmp_path,
        policy=policy,
        skills=skills,
        coverage_manifest=coverage_manifest,
        skill_scale_report=scale_report,
        prompt_coverage_report=coverage_report,
    )

    assert report["status"] == "failed"
    assert report["summary"]["decision_counts"]["retire"] == 1


def test_skill_registry_readiness_defers_planned_only_coverage(tmp_path: Path) -> None:
    skill = synthetic_skill()
    policy = synthetic_policy(implemented_count=0, planned_count=1)
    coverage_manifest = {
        "kind": "prompt_skill_coverage_registry",
        "entries": [
            {
                "id": "FX-A",
                "status": "planned",
                "prompt_family": "fixture-a",
                "skill_ids": [skill["id"]],
            }
        ],
    }

    report = build_skill_registry_readiness_report(
        config_root=tmp_path,
        policy=policy,
        skills={skill["id"]: skill},
        coverage_manifest=coverage_manifest,
        skill_scale_report=synthetic_scale_report(1),
        prompt_coverage_report=synthetic_coverage_report(1, 0),
    )

    record = report["skill_decisions"][0]
    assert report["status"] == "passed"
    assert record["decision"] == "defer"
    assert record["coverage_entry_ids"] == []
    assert record["planned_coverage_entry_ids"] == ["FX-A"]


def test_skill_registry_readiness_report_rejects_hidden_summary_edit(tmp_path: Path) -> None:
    policy = synthetic_policy()
    skills, coverage_manifest, scale_report, coverage_report = synthetic_sources()
    report = build_skill_registry_readiness_report(
        config_root=tmp_path,
        policy=policy,
        skills=skills,
        coverage_manifest=coverage_manifest,
        skill_scale_report=scale_report,
        prompt_coverage_report=coverage_report,
    )
    report["summary"]["decision_counts"] = {"keep": 999}

    errors = validate_skill_registry_readiness_report(
        report,
        config_root=tmp_path,
        policy=policy,
        skills=skills,
        coverage_manifest=coverage_manifest,
        skill_scale_report=scale_report,
        prompt_coverage_report=coverage_report,
    )

    assert errors == ["report must match rebuilt skill registry readiness review report"]


def test_run_skill_registry_readiness_review_writes_json_and_markdown(tmp_path: Path) -> None:
    report = run_skill_registry_readiness_review(
        SkillRegistryReadinessConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
            scale_report_path=tmp_path / "scale.json",
            coverage_report_path=tmp_path / "coverage.json",
        )
    )
    persisted = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "report.md").read_text(encoding="utf-8")

    assert report["status"] == "passed"
    assert persisted["report_path"] == str((tmp_path / "report.json").resolve())
    assert markdown.startswith("# Skill Registry Readiness Review")
    assert "## Skill Decisions" in markdown
