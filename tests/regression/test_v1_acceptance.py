from __future__ import annotations

import json
from pathlib import Path

from vllm_agent_gateway.acceptance.v1 import (
    V1AcceptanceConfig,
    acceptance_failure_guidance,
    execute_suite_commands,
    founder_field_summary_from_suites,
    require_feedback_record_context,
    run_id_from_text,
    skill_library_health_from_suites,
    suite_commands,
)
import vllm_agent_gateway.acceptance.v1 as v1_acceptance
from vllm_agent_gateway.acceptance.profiles import ReleaseGateProfile


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_v1_acceptance_suite_commands_cover_required_representative_cases() -> None:
    commands = suite_commands(
        V1AcceptanceConfig(
            config_root=REPO_ROOT,
            target_roots=("/mnt/c/coinbase_testing_repo_frozen_tmp", "/mnt/c/coinbase_testing_repo_frozen_tmp.github"),
            python_executable="python3",
        )
    )

    by_id = {item["id"]: item["command"] for item in commands}

    assert set(by_id) == {
        "representative_l1",
        "representative_l2",
        "task_decomposition",
        "controlled_apply",
        "inline_format_a",
        "external_tester_onboarding",
        "founder_field_prompts",
        "skill_library_release_gate",
    }
    assert "L1-002" in by_id["representative_l1"]
    assert "L1-010" in by_id["representative_l1"]
    assert "L2-005" in by_id["representative_l2"]
    assert "validate_task_decomposition_live.py" in " ".join(by_id["task_decomposition"])
    assert "validate_controlled_small_change_apply_live.py" in " ".join(by_id["controlled_apply"])
    assert "validate_workflow_router_inline_answers.py" in " ".join(by_id["inline_format_a"])
    assert "validate_external_tester_onboarding.py" in " ".join(by_id["external_tester_onboarding"])
    assert "--live-anythingllm" in by_id["external_tester_onboarding"]
    assert "--include-feedback" in by_id["external_tester_onboarding"]
    assert "ONB-001" in by_id["external_tester_onboarding"]
    assert "run_founder_field_prompt_eval.py" in " ".join(by_id["founder_field_prompts"])
    assert "validate_skill_release_gate.py" in " ".join(by_id["skill_library_release_gate"])
    assert "--profile" in by_id["skill_library_release_gate"]
    assert "release-candidate" in by_id["skill_library_release_gate"]
    assert "--anythingllm" not in by_id["skill_library_release_gate"]
    assert by_id["representative_l1"].count("--target-root") == 2
    assert by_id["task_decomposition"].count("--target-root") == 2
    assert by_id["controlled_apply"].count("--target-root") == 2
    assert by_id["skill_library_release_gate"].count("--target-root") == 2


def test_v1_1_acceptance_suite_commands_cover_consolidated_release_gate() -> None:
    commands = suite_commands(
        V1AcceptanceConfig(
            config_root=REPO_ROOT,
            target_roots=("/mnt/c/coinbase_testing_repo_frozen_tmp", "/mnt/c/coinbase_testing_repo_frozen_tmp.github"),
            python_executable="python3",
            profile=ReleaseGateProfile.V1_1_RELEASE_CANDIDATE,
        )
    )

    by_id = {item["id"]: item["command"] for item in commands}

    assert set(by_id) == {
        "first_time_user_doctor",
        "docs_index",
        "release_channels",
        "representative_l1",
        "representative_l2",
        "task_decomposition",
        "controlled_apply",
        "inline_format_a",
        "external_tester_onboarding",
        "founder_field_prompts",
        "skill_library_release_gate",
        "security_policy",
        "run_observability",
    }
    assert "run_first_time_user_doctor.py" in " ".join(by_id["first_time_user_doctor"])
    assert "check_docs_index.py" in " ".join(by_id["docs_index"])
    assert "validate_release_channels.py" in " ".join(by_id["release_channels"])
    assert "validate_security_policy.py" in " ".join(by_id["security_policy"])
    assert "report_run_observability.py" in " ".join(by_id["run_observability"])
    assert "--format" in by_id["run_observability"]
    assert "json" in by_id["run_observability"]
    assert "--profile" in by_id["skill_library_release_gate"]
    assert "v1.1-release-candidate" in by_id["skill_library_release_gate"]
    assert by_id["first_time_user_doctor"].count("--target-root") == 2
    assert by_id["skill_library_release_gate"].count("--target-root") == 2


def test_v1_acceptance_suite_command_results_include_duration(monkeypatch) -> None:
    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(v1_acceptance.subprocess, "run", lambda *_args, **_kwargs: Result())

    results = execute_suite_commands(
        V1AcceptanceConfig(
            config_root=REPO_ROOT,
            target_roots=("/mnt/c/coinbase_testing_repo_frozen_tmp",),
            command_timeout_seconds=1,
            python_executable="python3",
        )
    )

    assert results
    assert all(item["duration_seconds"] >= 0 for item in results)


def test_v1_acceptance_run_id_from_text_extracts_workflow_router_id() -> None:
    assert (
        run_id_from_text("workflow_router.plan completed\nrun_id: workflow-router-20260605T020043450668Z")
        == "workflow-router-20260605T020043450668Z"
    )
    assert run_id_from_text("missing") == "unknown"


def test_v1_acceptance_failure_guidance_maps_common_failures() -> None:
    guidance = acceptance_failure_guidance(
        [
            "RuntimeError: ANYTHINGLLM_API_KEY is required",
            "RuntimeError: health check failed: []",
            "TimeoutError: timed out waiting for body bytes",
        ]
    )

    assert "Set ANYTHINGLLM_API_KEY" in guidance[0]
    assert any("Restart the harness" in item for item in guidance)
    assert any("Run live validators from Bash" in item for item in guidance)


def test_v1_acceptance_summarizes_founder_and_skill_release_reports(tmp_path: Path) -> None:
    founder_report = tmp_path / "founder.json"
    skill_report = tmp_path / "skill.json"
    founder_report.write_text(
        json.dumps(
            {
                "status": "passed",
                "summary": {"passed": 34, "failed": 0},
                "cases": [{"case_id": "P01"}, {"case_id": "P02"}],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )
    skill_report.write_text(
        json.dumps(
            {
                "status": "passed",
                "profile": "release-candidate",
                "catalog_summary": {"skill_count": 50, "eval_case_count": 49, "route_key_count": 50},
                "profile_contract": {"profile": "release-candidate", "includes_anythingllm": True},
                "prompt_catalog_summary": {"field_prompt_count": 34, "prompt_matrix_case_count": 50},
                "generated_reports": {"batch_d_live_report": "batch-d.json"},
                "commands": [{"label": "phase63_batch_d_live_guard", "status": "passed"}],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )
    suite_runs = [
        {"id": "founder_field_prompts", "stdout_tail": f"FOUNDER FIELD REPORT {founder_report}\n"},
        {"id": "skill_library_release_gate", "stdout_tail": f"SKILL RELEASE GATE REPORT {skill_report}\n"},
    ]

    founder_summary = founder_field_summary_from_suites(suite_runs)
    skill_summary = skill_library_health_from_suites(suite_runs)

    assert founder_summary["status"] == "passed"
    assert founder_summary["prompt_count"] == 2
    assert skill_summary["profile"] == "release-candidate"
    assert skill_summary["profile_contract"]["includes_anythingllm"] is True
    assert skill_summary["catalog_summary"]["skill_count"] == 50
    assert skill_summary["prompt_catalog_summary"]["field_prompt_count"] == 34
    assert skill_summary["batch_d_live_report"] == "batch-d.json"
    assert skill_summary["live_suite_statuses"]["phase63_batch_d_live_guard"] == "passed"


def test_v1_acceptance_feedback_context_accepts_no_gap_useful_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target_root = "/mnt/c/coinbase_testing_repo_frozen_tmp.github"
    record_path = tmp_path / "feedback-record.json"
    record_path.write_text(
        json.dumps(
            {
                "classifications": ["useful"],
                "feedback": {"useful": ["inline answer was chat visible"], "missing": []},
                "feedback_context": {
                    "selected_workflow": "code_investigation.plan",
                    "selected_skills": ["code-explanation-summarizer"],
                    "target_root": target_root,
                    "downstream_artifact_keys": ["code_explanation"],
                    "route_rules": ["l1_explain_code_terms"],
                    "semantic_status": "ok",
                },
                "next_action": {"kind": "keep_current_route", "mutation_policy": "controller_artifacts_only"},
            }
        ),
        encoding="utf-8",
    )

    def fake_json_request(*_args, **_kwargs):
        return 200, {"artifacts": {"feedback_record": str(record_path)}}

    monkeypatch.setattr(v1_acceptance, "json_request", fake_json_request)

    context = require_feedback_record_context(
        V1AcceptanceConfig(config_root=REPO_ROOT, timeout_seconds=1),
        "workflow-feedback-20260606T000000000000Z",
        "gateway",
        target_root,
    )

    assert context["classifications"] == ["useful"]
    assert context["next_action"]["kind"] == "keep_current_route"


def test_v1_acceptance_feedback_context_rejects_synthetic_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target_root = "/mnt/c/coinbase_testing_repo_frozen_tmp.github"
    record_path = tmp_path / "feedback-record.json"
    record_path.write_text(
        json.dumps(
            {
                "classifications": ["useful", "missing"],
                "feedback": {"useful": ["inline answer was chat visible"], "missing": ["none for V1 acceptance"]},
                "feedback_context": {
                    "selected_workflow": "code_investigation.plan",
                    "selected_skills": ["code-explanation-summarizer"],
                    "target_root": target_root,
                    "downstream_artifact_keys": ["code_explanation"],
                },
                "next_action": {"kind": "prompt_or_artifact_gap_review", "mutation_policy": "controller_artifacts_only"},
            }
        ),
        encoding="utf-8",
    )

    def fake_json_request(*_args, **_kwargs):
        return 200, {"artifacts": {"feedback_record": str(record_path)}}

    monkeypatch.setattr(v1_acceptance, "json_request", fake_json_request)

    try:
        require_feedback_record_context(
            V1AcceptanceConfig(config_root=REPO_ROOT, timeout_seconds=1),
            "workflow-feedback-20260606T000000000000Z",
            "gateway",
            target_root,
        )
    except RuntimeError as exc:
        assert "useful-only" in str(exc)
    else:
        raise AssertionError("synthetic missing feedback should fail V1 acceptance")
