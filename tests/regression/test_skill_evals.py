from __future__ import annotations

import json
from pathlib import Path

from vllm_agent_gateway.skills.evals import build_skill_eval_report, run_skill_eval_catalog


REPO_ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def make_eval_root(tmp_path: Path, *, case_overrides: dict[str, object] | None = None) -> Path:
    root = tmp_path / "skill-eval-root"
    write_json(
        root / "runtime" / "workflows.json",
        {
            "schema_version": 1,
            "workflows": [
                {
                    "id": "code_investigation.plan",
                    "controller_actions": [
                        {
                            "tool_id": "git_grep",
                            "action": "bounded_lookup",
                            "result_artifacts": ["investigation_plan"],
                        }
                    ],
                }
            ],
        },
    )
    write_json(root / "runtime" / "tools.json", {"schema_version": 1, "tools": []})
    case = {
        "id": "example_eval",
        "prompt_family": "example",
        "natural_prompt": "In <repo>, investigate example behavior. Read only.",
        "expected_workflow": "code_investigation.plan",
        "expected_artifacts": ["investigation_plan"],
        "mutation_policy": "no_repository_mutation",
        "live_suite": "skill_registry_contract",
    }
    if case_overrides:
        case.update(case_overrides)
    write_json(
        root / "runtime" / "skill_evals.json",
        {
            "schema_version": 1,
            "kind": "skill_eval_fixture_registry",
            "fixtures": [
                {
                    "id": "clear_request",
                    "description": "Clear request.",
                    "expected_behavior": "produce_ready_or_next_step",
                }
            ],
            "cases": [case],
        },
    )
    write_json(
        root / "runtime" / "skills.json",
        {
            "schema_version": 1,
            "kind": "skill_registry",
            "policy": {
                "body_load_policy": "metadata_selected_only",
                "creation_rule": "Create skills only after an eval failure.",
            },
            "skills": [],
        },
    )
    return root


def test_skill_eval_runner_validates_project_catalog_and_writes_report(tmp_path: Path) -> None:
    report_path = tmp_path / "skill-eval-report.json"
    manifest = json.loads((REPO_ROOT / "runtime" / "skill_evals.json").read_text(encoding="utf-8"))

    report = run_skill_eval_catalog(REPO_ROOT, output_path=report_path)

    assert report["status"] == "passed"
    assert report["summary"]["case_count"] == len(manifest["cases"])
    assert report["summary"]["failed_count"] == 0
    assert report_path.exists()
    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    assert persisted["status"] == "passed"
    assert persisted["report_path"] == str(report_path.resolve())


def test_skill_eval_runner_rejects_unknown_live_suite(tmp_path: Path) -> None:
    root = make_eval_root(tmp_path, case_overrides={"live_suite": "unknown_live_suite"})

    report = build_skill_eval_report(root)

    assert report["status"] == "failed"
    assert report["checks"][0]["status"] == "failed"
    assert "unsupported live_suite" in report["checks"][0]["errors"][0]


def test_skill_eval_runner_rejects_unknown_expected_artifact(tmp_path: Path) -> None:
    root = make_eval_root(tmp_path, case_overrides={"expected_artifacts": ["missing_artifact"]})

    report = build_skill_eval_report(root)

    assert report["status"] == "failed"
    assert report["checks"][0]["status"] == "failed"
    assert "unknown expected_artifacts" in report["checks"][0]["errors"][0]


def test_skill_eval_runner_maps_l1_and_l2_cases_to_live_suite_commands(tmp_path: Path) -> None:
    report = run_skill_eval_catalog(
        REPO_ROOT,
        output_path=tmp_path / "live-map-report.json",
        case_ids=[
            "l1_read_only_context",
            "l1_explain_code",
            "l1_coverage_gap_summary",
            "l1_local_change_summary",
            "l2_multi_file_behavior",
            "l2_test_selection",
            "l2_runtime_error_diagnosis",
            "l2_request_flow_map",
            "l2_code_path_comparison",
            "l2_change_surface_summary",
            "d1_config_default_test",
            "d1_message_assertion_test",
            "d1_test_assertion_update",
        ],
        live_target="gateway",
        execute_live=False,
    )

    assert report["status"] == "passed"
    mappings = {check["case_id"]: check["live_mapping"] for check in report["checks"]}
    assert mappings["l1_read_only_context"]["case_id"] == "L1-001"
    assert mappings["l1_explain_code"]["case_id"] == "L1-002"
    assert mappings["l1_coverage_gap_summary"]["case_id"] == "L1-017"
    assert mappings["l1_local_change_summary"]["case_id"] == "L1-021"
    assert mappings["l2_multi_file_behavior"]["case_id"] == "L2-002"
    assert mappings["l2_test_selection"]["case_id"] == "L2-005"
    assert mappings["l2_runtime_error_diagnosis"]["case_id"] == "L2-006"
    assert mappings["l2_request_flow_map"]["case_id"] == "L2-007"
    assert mappings["l2_code_path_comparison"]["case_id"] == "L2-008"
    assert mappings["l2_change_surface_summary"]["case_id"] == "L2-009"
    assert mappings["d1_config_default_test"]["case_id"] == "D1-004"
    assert mappings["d1_message_assertion_test"]["case_id"] == "D1-005"
    assert mappings["d1_test_assertion_update"]["case_id"] == "D1-006"
    commands = report["live_suite_runs"]
    assert len(commands) == 2
    assert all(command["status"] == "planned" for command in commands)
    assert all("--skip-anythingllm" in command["command"] for command in commands)


def test_skill_eval_runner_reports_requested_missing_case(tmp_path: Path) -> None:
    root = make_eval_root(tmp_path)

    report = build_skill_eval_report(root, case_ids=["missing_case"])

    assert report["status"] == "failed"
    assert "Requested skill eval case id(s) not found: missing_case" in report["errors"]
