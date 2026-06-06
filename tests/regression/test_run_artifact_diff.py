from __future__ import annotations

import json
from pathlib import Path

from vllm_agent_gateway.acceptance.run_artifact_diff import RunArtifactDiffConfig, run_artifact_diff


def write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def founder_report(tmp_path: Path, name: str, *, case_status: str = "passed", semantic_status: str = "passed") -> Path:
    return write_json(
        tmp_path / f"{name}.json",
        {
            "kind": "founder_field_prompt_evaluation",
            "status": "passed" if case_status == "passed" and semantic_status == "passed" else "failed",
            "created_at": "20260606T000000Z",
            "summary": {"passed": 1 if case_status == "passed" else 0, "failed": 0 if case_status == "passed" else 1},
            "fixture_state_before": {
                "/mnt/c/example": {"hashes": {"a.py": "left"}, "git_status": ""}
            },
            "fixture_state_after": {
                "/mnt/c/example": {"hashes": {"a.py": "left"}, "git_status": ""}
            },
            "cases": [
                {
                    "case_id": "P01",
                    "status": case_status,
                    "expected_workflow": "code_investigation.plan",
                    "expected_rule": "l1_find_behavior_start_terms",
                    "expected_skill_id": "entrypoint-finder",
                    "expected_artifact_key": "behavior_start",
                    "semantic_quality_status": semantic_status,
                    "output_contract_status": case_status,
                }
            ],
        },
    )


def v1_report(tmp_path: Path, name: str, founder_path: Path, *, suite_status: str = "passed") -> Path:
    return write_json(
        tmp_path / f"{name}.json",
        {
            "kind": "v1_acceptance_report",
            "status": "passed" if suite_status == "passed" else "failed",
            "profile": "release-candidate",
            "created_at": "20260606T000000Z",
            "target_roots": ["/mnt/c/example"],
            "suite_runs": [{"id": "founder_field_prompts", "status": suite_status, "returncode": 0}],
            "health": [{"name": "model", "status": "passed", "http_status": 200}],
            "json_output": [{}],
            "feedback": [{}],
            "errors": [],
            "fixture_state": {
                "/mnt/c/example": {"hashes": {"a.py": "left"}, "git_status": {"clean": True}}
            },
            "founder_field_summary": {
                "status": "passed",
                "report_path": str(founder_path),
                "summary": {"passed": 1, "failed": 0},
                "errors": [],
            },
            "skill_library_health": {
                "status": "passed",
                "catalog_summary": {"skill_count": 10, "eval_case_count": 9, "route_key_count": 10},
                "prompt_catalog_summary": {"prompt_matrix_failed": 0},
                "generated_reports": {"skill_scale_report": "skill-scale.json"},
            },
        },
    )


def test_run_artifact_diff_detects_semantic_and_suite_changes(tmp_path: Path) -> None:
    left_founder = founder_report(tmp_path, "left-founder")
    right_founder = founder_report(tmp_path, "right-founder", case_status="failed", semantic_status="failed")
    left_v1 = v1_report(tmp_path, "left-v1", left_founder)
    right_v1 = v1_report(tmp_path, "right-v1", right_founder, suite_status="failed")

    report = run_artifact_diff(
        RunArtifactDiffConfig(
            config_root=tmp_path,
            left_report_path=left_v1,
            right_report_path=right_v1,
            left_label="before",
            right_label="after",
            output_path=tmp_path / "diff.json",
        )
    )

    assert report["status"] == "passed"
    assert report["diff"]["status_changed"] is True
    assert report["diff"]["suite_status_changes"]["changed_count"] == 1
    assert report["diff"]["semantic_miss_changes"]["added"] == ["P01"]
    assert report["diff"]["case_status_changes"]["changed_count"] == 1
    assert any("New semantic misses" in item for item in report["recommendations"])


def test_run_artifact_diff_detects_fixture_state_changes(tmp_path: Path) -> None:
    left = write_json(
        tmp_path / "left.json",
        {
            "kind": "v1_acceptance_report",
            "status": "passed",
            "fixture_state": {"/mnt/c/example": {"hashes": {"a.py": "left"}, "git_status": {"clean": True}}},
        },
    )
    right = write_json(
        tmp_path / "right.json",
        {
            "kind": "v1_acceptance_report",
            "status": "passed",
            "fixture_state": {"/mnt/c/example": {"hashes": {"a.py": "right"}, "git_status": {"clean": True}}},
        },
    )

    report = run_artifact_diff(
        RunArtifactDiffConfig(
            config_root=tmp_path,
            left_report_path=left,
            right_report_path=right,
            output_path=tmp_path / "diff.json",
        )
    )

    assert report["diff"]["fixture_state_changes"]
    assert any("Fixture state changed" in item for item in report["recommendations"])


def test_run_artifact_diff_unwraps_model_portability_nested_acceptance(tmp_path: Path) -> None:
    founder = founder_report(tmp_path, "founder")
    acceptance = v1_report(tmp_path, "acceptance", founder)
    left = write_json(
        tmp_path / "left-portability.json",
        {
            "kind": "model_portability_report",
            "status": "passed",
            "candidate": {"candidate_id": "model-a", "candidate_model_base_url": "http://127.0.0.1:8000/v1"},
            "candidate_model_probe": {"model_ids": ["model-a"]},
            "acceptance_report_path": str(acceptance),
            "classification_summary": {"harness": 0, "classifier": 0, "prompt": 0, "model_quality": 0, "unknown": 0},
            "classified_failures": [],
        },
    )
    right = write_json(
        tmp_path / "right-portability.json",
        {
            "kind": "model_portability_report",
            "status": "passed",
            "candidate": {"candidate_id": "model-b", "candidate_model_base_url": "http://127.0.0.1:8000/v1"},
            "candidate_model_probe": {"model_ids": ["model-b"]},
            "acceptance_report_path": str(acceptance),
            "classification_summary": {"harness": 0, "classifier": 0, "prompt": 0, "model_quality": 0, "unknown": 0},
            "classified_failures": [],
        },
    )

    report = run_artifact_diff(
        RunArtifactDiffConfig(
            config_root=tmp_path,
            left_report_path=left,
            right_report_path=right,
            output_path=tmp_path / "diff.json",
        )
    )

    assert report["status"] == "passed"
    assert report["diff"]["candidate_changed"]["changed"] is True
    assert report["left"]["summary"]["nested_acceptance"]["suite_statuses"]["founder_field_prompts"] == "passed"
