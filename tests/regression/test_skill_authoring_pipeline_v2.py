import json
import shutil
from pathlib import Path

from vllm_agent_gateway.acceptance.skill_authoring_pipeline_v2 import (
    SkillAuthoringPipelineV2Config,
    build_skill_authoring_pipeline_v2_report,
    run_skill_authoring_pipeline_v2,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "skill_authoring_pipeline_v2" / "phase194-readme-locator"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_phase193_stub(path: Path) -> None:
    write_json(
        path,
        {
            "schema_version": 1,
            "kind": "skill_registry_readiness_review_report",
            "status": "passed",
            "summary": {
                "decision_counts": {"keep": 54},
                "validation_error_count": 0,
            },
        },
    )


def temp_project_root(tmp_path: Path) -> tuple[Path, Path, Path]:
    project_root = tmp_path / "project"
    shutil.copytree(REPO_ROOT / "runtime", project_root / "runtime")
    shutil.copyfile(REPO_ROOT / "README.skill-registry.md", project_root / "README.skill-registry.md")
    shutil.copyfile(REPO_ROOT / "README.skill-authoring-pipeline-v2.md", project_root / "README.skill-authoring-pipeline-v2.md")
    candidate_root = project_root / "candidate"
    shutil.copytree(FIXTURE_ROOT, candidate_root)
    batch_path = candidate_root / "skill-batch.json"
    batch = read_json(batch_path)
    batch["skills"][0]["path"] = "candidate/draft-skills/phase194-readme-locator/SKILL.md"
    write_json(batch_path, batch)
    phase193_path = project_root / "runtime-state" / "phase193.json"
    phase193_path.parent.mkdir(parents=True, exist_ok=True)
    write_phase193_stub(phase193_path)
    return project_root, candidate_root, phase193_path


def config_for(project_root: Path, candidate_root: Path, phase193_path: Path, tmp_path: Path) -> SkillAuthoringPipelineV2Config:
    return SkillAuthoringPipelineV2Config(
        config_root=project_root,
        candidate_root=candidate_root,
        output_path=tmp_path / "report.json",
        markdown_output_path=tmp_path / "report.md",
        batch_report_path=tmp_path / "batch-report.json",
        phase193_report_path=phase193_path,
    )


def test_project_skill_authoring_pipeline_v2_passes_current_candidate(tmp_path: Path) -> None:
    report = run_skill_authoring_pipeline_v2(
        SkillAuthoringPipelineV2Config(
            config_root=REPO_ROOT,
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
            batch_report_path=tmp_path / "batch-report.json",
            phase193_report_path=tmp_path / "phase193-report.json",
        )
    )

    assert report["status"] == "passed"
    assert report["gate_scope"] == "draft_packet_admission_only"
    assert report["packet_status"] == "admitted"
    assert report["proof_status"] == "not_run"
    assert report["promotion_eligible"] is False
    assert report["candidate"]["skill_id"] == "phase194-readme-locator"
    assert report["summary"]["promotion_decision"] == "draft_packet_admitted_not_promoted"
    assert report["summary"]["gate_count"] == 9
    assert report["summary"]["holdout_prompt_count"] == 2
    assert report["runtime_registry_mutation_check"]["status"] == "passed"
    assert report["candidate_absence_check"]["skill_id_absent"] is True


def test_skill_authoring_pipeline_v2_policy_rejects_manual_prompt_injection() -> None:
    policy = read_json(REPO_ROOT / "runtime" / "skill_authoring_pipeline_v2_policy.json")
    policy["candidate_contract"]["manual_prompt_injection_allowed"] = True

    errors = validate_policy(policy)

    assert any(error["id"] == "candidate_contract.manual_prompt_injection_allowed" for error in errors)


def test_skill_authoring_pipeline_v2_policy_rejects_promotion_eligible_packet_admission() -> None:
    policy = read_json(REPO_ROOT / "runtime" / "skill_authoring_pipeline_v2_policy.json")
    policy["candidate_contract"]["promotion_eligible_on_packet_admission"] = True

    errors = validate_policy(policy)

    assert any(error["id"] == "candidate_contract.promotion_eligible_on_packet_admission" for error in errors)


def test_skill_authoring_pipeline_v2_policy_rejects_removed_required_gate() -> None:
    policy = read_json(REPO_ROOT / "runtime" / "skill_authoring_pipeline_v2_policy.json")
    policy["candidate_contract"]["required_eval_gate_ids"].remove("blind_baseline_first")

    errors = validate_policy(policy)

    assert any(error["id"] == "candidate_contract.required_eval_gate_ids" for error in errors)


def test_skill_authoring_pipeline_v2_policy_rejects_removed_anythingllm_target() -> None:
    policy = read_json(REPO_ROOT / "runtime" / "skill_authoring_pipeline_v2_policy.json")
    policy["live_validation_requirements"]["required_targets"].remove("anythingllm")

    errors = validate_policy(policy)

    assert any(error["id"] == "live_validation_requirements.required_targets" for error in errors)


def test_skill_authoring_pipeline_v2_rejects_missing_blind_baseline_first(tmp_path: Path) -> None:
    project_root, candidate_root, phase193_path = temp_project_root(tmp_path)
    plan_path = candidate_root / "authoring-pipeline-plan.json"
    plan = read_json(plan_path)
    plan["blind_baseline_plan"]["contextless_agent_first"] = False
    write_json(plan_path, plan)

    report = build_skill_authoring_pipeline_v2_report(config_for(project_root, candidate_root, phase193_path, tmp_path))

    assert report["status"] == "failed"
    assert any(
        error["id"] == "candidate.authoring_pipeline_plan.blind_baseline_plan.contextless_agent_first"
        for error in report["validation_errors"]
    )


def test_skill_authoring_pipeline_v2_rejects_premature_implemented_coverage(tmp_path: Path) -> None:
    project_root, candidate_root, phase193_path = temp_project_root(tmp_path)
    coverage_path = candidate_root / "prompt-coverage-entry.json"
    coverage = read_json(coverage_path)
    coverage["status"] = "implemented"
    write_json(coverage_path, coverage)

    report = build_skill_authoring_pipeline_v2_report(config_for(project_root, candidate_root, phase193_path, tmp_path))

    assert report["status"] == "failed"
    assert any(error["id"] == "candidate.prompt_coverage_entry.status" for error in report["validation_errors"])


def test_skill_authoring_pipeline_v2_rejects_fail_open_regression_skeleton(tmp_path: Path) -> None:
    project_root, candidate_root, phase193_path = temp_project_root(tmp_path)
    skeleton_path = candidate_root / "test-skeletons" / "test_phase194_readme_locator_authoring_gate.py"
    skeleton_path.write_text(skeleton_path.read_text(encoding="utf-8").replace("pytest.fail(", "pass  # "), encoding="utf-8")

    report = build_skill_authoring_pipeline_v2_report(config_for(project_root, candidate_root, phase193_path, tmp_path))

    assert report["status"] == "failed"
    assert any(error["id"] == "candidate.regression_test_skeleton.fail_closed" for error in report["validation_errors"])


def test_skill_authoring_pipeline_v2_rejects_unreachable_fail_closed_skeleton(tmp_path: Path) -> None:
    project_root, candidate_root, phase193_path = temp_project_root(tmp_path)
    skeleton_path = candidate_root / "test-skeletons" / "test_phase194_readme_locator_authoring_gate.py"
    skeleton_text = skeleton_path.read_text(encoding="utf-8").replace(
        'pytest.fail("routing gate is not installed yet")',
        'if False:\n        pytest.fail("routing gate is not installed yet")',
        1,
    )
    skeleton_path.write_text(skeleton_text, encoding="utf-8")

    report = build_skill_authoring_pipeline_v2_report(config_for(project_root, candidate_root, phase193_path, tmp_path))

    assert report["status"] == "failed"
    assert any(error["id"] == "candidate.regression_test_skeleton.fail_closed" for error in report["validation_errors"])


def test_skill_authoring_pipeline_v2_rejects_incomplete_live_fixture_plan(tmp_path: Path) -> None:
    project_root, candidate_root, phase193_path = temp_project_root(tmp_path)
    plan_path = candidate_root / "authoring-pipeline-plan.json"
    plan = read_json(plan_path)
    plan["live_validation_plan"]["target_roots"] = ["/mnt/c/coinbase_testing_repo_frozen_tmp"]
    plan["live_validation_plan"]["required_targets"] = ["localhost_8000", "gateway_8300"]
    write_json(plan_path, plan)

    report = build_skill_authoring_pipeline_v2_report(config_for(project_root, candidate_root, phase193_path, tmp_path))

    assert report["status"] == "failed"
    error_ids = {error["id"] for error in report["validation_errors"]}
    assert "candidate.authoring_pipeline_plan.live_validation_plan.target_roots" in error_ids
    assert "candidate.authoring_pipeline_plan.live_validation_plan.required_targets" in error_ids


def test_skill_authoring_pipeline_v2_rejects_bogus_live_commands(tmp_path: Path) -> None:
    project_root, candidate_root, phase193_path = temp_project_root(tmp_path)
    plan_path = candidate_root / "authoring-pipeline-plan.json"
    plan = read_json(plan_path)
    plan["live_validation_plan"]["commands"] = ["python3 scripts/not_a_real_validation.py"]
    write_json(plan_path, plan)

    report = build_skill_authoring_pipeline_v2_report(config_for(project_root, candidate_root, phase193_path, tmp_path))

    assert report["status"] == "failed"
    assert any(error["id"] == "candidate.authoring_pipeline_plan.live_validation_plan.commands" for error in report["validation_errors"])


def test_skill_authoring_pipeline_v2_rejects_script_names_only_in_command_comments(tmp_path: Path) -> None:
    project_root, candidate_root, phase193_path = temp_project_root(tmp_path)
    plan_path = candidate_root / "authoring-pipeline-plan.json"
    plan = read_json(plan_path)
    plan["live_validation_plan"]["commands"] = [
        "python3 scripts/not_real.py # scripts/validate_skill_authoring_pipeline_v2.py",
        "python3 scripts/not_real_either.py # scripts/validate_skill_authoring_factory_live.py",
    ]
    write_json(plan_path, plan)

    report = build_skill_authoring_pipeline_v2_report(config_for(project_root, candidate_root, phase193_path, tmp_path))

    assert report["status"] == "failed"
    assert any(error["id"] == "candidate.authoring_pipeline_plan.live_validation_plan.commands" for error in report["validation_errors"])


def test_skill_authoring_pipeline_v2_rejects_candidate_plan_mutation_flags(tmp_path: Path) -> None:
    project_root, candidate_root, phase193_path = temp_project_root(tmp_path)
    plan_path = candidate_root / "authoring-pipeline-plan.json"
    plan = read_json(plan_path)
    plan["manual_prompt_injection_allowed"] = True
    plan["runtime_registry_mutation_allowed"] = True
    write_json(plan_path, plan)

    report = build_skill_authoring_pipeline_v2_report(config_for(project_root, candidate_root, phase193_path, tmp_path))

    assert report["status"] == "failed"
    error_ids = {error["id"] for error in report["validation_errors"]}
    assert "candidate.authoring_pipeline_plan.manual_prompt_injection_allowed" in error_ids
    assert "candidate.authoring_pipeline_plan.runtime_registry_mutation_allowed" in error_ids


def test_skill_authoring_pipeline_v2_rejects_prompt_holdout_overlap(tmp_path: Path) -> None:
    project_root, candidate_root, phase193_path = temp_project_root(tmp_path)
    plan_path = candidate_root / "authoring-pipeline-plan.json"
    plan = read_json(plan_path)
    plan["holdout_prompts"][0]["prompt"] = plan["prompt_examples"][0]["prompt"]
    write_json(plan_path, plan)

    report = build_skill_authoring_pipeline_v2_report(config_for(project_root, candidate_root, phase193_path, tmp_path))

    assert report["status"] == "failed"
    assert any(error["id"] == "candidate.authoring_pipeline_plan.prompt_holdout_overlap" for error in report["validation_errors"])


def test_skill_authoring_pipeline_v2_rejects_candidate_already_in_runtime_registry(tmp_path: Path) -> None:
    project_root, candidate_root, phase193_path = temp_project_root(tmp_path)
    skills_path = project_root / "runtime" / "skills.json"
    skills = read_json(skills_path)
    batch = read_json(candidate_root / "skill-batch.json")
    skills["skills"].append(batch["skills"][0])
    write_json(skills_path, skills)

    report = build_skill_authoring_pipeline_v2_report(config_for(project_root, candidate_root, phase193_path, tmp_path))

    assert report["status"] == "failed"
    assert any(error["id"] == "candidate.runtime_registry.skill_id" for error in report["validation_errors"])


def test_skill_authoring_pipeline_v2_rejects_weak_phase193_report_shape(tmp_path: Path) -> None:
    project_root, candidate_root, phase193_path = temp_project_root(tmp_path)
    phase193_path.write_text(json.dumps({"status": "passed", "summary": {"decision_counts": {"keep": 1}}}), encoding="utf-8")

    report = build_skill_authoring_pipeline_v2_report(config_for(project_root, candidate_root, phase193_path, tmp_path))

    assert report["status"] == "failed"
    error_ids = {error["id"] for error in report["validation_errors"]}
    assert "phase193.schema_version" in error_ids
    assert "phase193.kind" in error_ids
