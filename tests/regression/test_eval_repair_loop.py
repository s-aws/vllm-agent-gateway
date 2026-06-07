from __future__ import annotations

import json
from pathlib import Path

from vllm_agent_gateway.acceptance.eval_repair_loop import (
    EvalRepairLoopConfig,
    run_eval_repair_loop,
    validate_eval_repair_report,
)


def write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def taxonomy_report(findings: list[dict[str, object]], *, status: str = "passed") -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "failure_taxonomy_report",
        "status": status,
        "input_reports": [{"label": "unit", "path": "unit-input.json", "kind": "founder_field_prompt_evaluation"}],
        "summary": {"finding_count": len(findings), "highest_severity": "high"},
        "findings": findings,
        "errors": [],
    }


def valid_recursive_report() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "recursive_blind_testing_report",
        "status": "passed",
        "policy_id": "bounded-recursive-blind-testing-v1",
        "scenario_id": "anythingllm_output_review",
        "rounds": [
            {
                "round_id": "round-1",
                "evaluator_context": {"fork_context": False, "agent_id": "blind-agent-1"},
                "input_refs": ["runtime-state/founder-field-tests/failed.json"],
                "blind_findings": [],
                "accepted_findings": [],
                "rejected_findings": [],
            }
        ],
        "score_summary": {
            "total_score": 91,
            "category_scores": {
                "route_workflow_skill_tool_correctness": 91,
                "evidence_grounding_and_artifact_quality": 91,
                "semantic_correctness": 91,
                "output_contract_and_chat_visible_markers": 91,
                "verification_command_relevance": 91,
                "safety_approval_and_mutation_boundary": 91,
                "diagnosability": 91,
            },
        },
        "convergence": {
            "status": "converged",
            "summary": "No unresolved high findings remain.",
            "evidence_refs": ["python scripts/validate_recursive_blind_testing.py"],
        },
    }


def run_report(
    tmp_path: Path,
    *,
    taxonomy: Path | None = None,
    recursive: Path | None = None,
    target: str = "P01",
    holdout: str = "P02",
) -> dict[str, object]:
    return run_eval_repair_loop(
        EvalRepairLoopConfig(
            config_root=tmp_path,
            failure_taxonomy_report_paths=(taxonomy,) if taxonomy else (),
            recursive_report_paths=(recursive,) if recursive else (),
            target_prompt_case_id=target,
            holdout_prompt_case_id=holdout,
            output_path=tmp_path / "eval-repair-loop.json",
            markdown_output_path=tmp_path / "eval-repair-loop.md",
        )
    )


def test_eval_repair_loop_maps_all_phase104_repair_categories(tmp_path: Path) -> None:
    taxonomy = write_json(
        tmp_path / "taxonomy.json",
        taxonomy_report(
            [
                {
                    "report_label": "unit",
                    "report_path": "unit-input.json",
                    "source": "cases[P01].output_contract",
                    "category": "routing_miss",
                    "severity": "high",
                    "message": "expected_workflow did not match selected_workflow",
                    "evidence": {"expected_workflow": "code_investigation.plan"},
                },
                {
                    "report_label": "unit",
                    "report_path": "unit-input.json",
                    "source": "cases[P02].semantic_quality",
                    "category": "semantic_miss",
                    "severity": "medium",
                    "message": "selected skill metadata omitted source refs",
                    "evidence": {"case_id": "P02"},
                },
                {
                    "report_label": "unit",
                    "report_path": "unit-input.json",
                    "source": "cases[P03].tool_candidates",
                    "category": "evidence_miss",
                    "severity": "medium",
                    "message": "required tool candidate was rejected by the tool allowlist",
                    "evidence": {"case_id": "P03"},
                },
                {
                    "report_label": "unit",
                    "report_path": "unit-input.json",
                    "source": "cases[P04].prompt_risk",
                    "category": "prompt_ambiguity",
                    "severity": "low",
                    "message": "prompt_risk: missing target file",
                    "evidence": {"case_id": "P04"},
                },
                {
                    "report_label": "unit",
                    "report_path": "unit-input.json",
                    "source": "cases[P05].model_quality",
                    "category": "model_quality",
                    "severity": "medium",
                    "message": "model output was malformed json schema",
                    "evidence": {"case_id": "P05"},
                },
                {
                    "report_label": "unit",
                    "report_path": "unit-input.json",
                    "source": "anythingllm_preflight",
                    "category": "anythingllm_config_error",
                    "severity": "high",
                    "message": "AnythingLLM workspace or API key is not configured",
                    "evidence": {"case_id": "P06"},
                },
                {
                    "report_label": "unit",
                    "report_path": "unit-input.json",
                    "source": "cases[P07].unsupported",
                    "category": "unknown",
                    "severity": "medium",
                    "message": "unsupported broad refactor scope must be deferred",
                    "evidence": {"case_id": "P07"},
                },
            ]
        ),
    )

    report = run_report(tmp_path, taxonomy=taxonomy)

    assert report["status"] == "passed"
    assert {
        "route_rule",
        "skill_metadata",
        "tool_availability",
        "prompt_ambiguity",
        "model_quality",
        "docs_setup_issue",
        "unsupported_scope",
    } == {item["failure_category"] for item in report["recommendations"]}  # type: ignore[index]
    for item in report["recommendations"]:  # type: ignore[index]
        assert item["evidence_refs"]
        assert item["target_file_or_artifact"]
        assert item["validation_command"]
        assert item["advisory_only"] is True
        assert item["fixture_mutation_guard"] is True
    assert (tmp_path / "eval-repair-loop.md").read_text(encoding="utf-8").startswith("# Eval Repair Loop Report")


def test_eval_repair_loop_blocks_fixture_mutation(tmp_path: Path) -> None:
    taxonomy = write_json(
        tmp_path / "taxonomy.json",
        taxonomy_report(
            [
                {
                    "report_label": "unit",
                    "report_path": "unit-input.json",
                    "source": "fixture_state",
                    "category": "fixture_mutation",
                    "severity": "critical",
                    "message": "Fixture state changed between before and after snapshots.",
                    "evidence": {},
                }
            ]
        ),
    )

    report = run_report(tmp_path, taxonomy=taxonomy)

    assert report["status"] == "failed"
    assert any("protected fixture mutation" in error for error in report["validation_errors"])  # type: ignore[index]


def test_eval_repair_loop_validator_requires_evidence_and_validation_command(tmp_path: Path) -> None:
    taxonomy = write_json(
        tmp_path / "taxonomy.json",
        taxonomy_report(
            [
                {
                    "report_label": "unit",
                    "report_path": "unit-input.json",
                    "source": "cases[P01].output_contract",
                    "category": "routing_miss",
                    "severity": "high",
                    "message": "expected_workflow did not match selected_workflow",
                    "evidence": {"case_id": "P01"},
                }
            ]
        ),
    )
    report = run_report(tmp_path, taxonomy=taxonomy)
    report["recommendations"][0]["evidence_refs"] = []  # type: ignore[index]
    report["recommendations"][0]["validation_command"] = ""  # type: ignore[index]

    errors = validate_eval_repair_report(report)

    assert any("evidence_refs must be non-empty" in item for item in errors)
    assert any("validation_command must be non-empty" in item for item in errors)


def test_eval_repair_loop_targets_chat_contract_for_output_contract_miss(tmp_path: Path) -> None:
    taxonomy = write_json(
        tmp_path / "taxonomy.json",
        taxonomy_report(
            [
                {
                    "report_label": "unit",
                    "report_path": "unit-input.json",
                    "source": "cases[P02].output_contract",
                    "category": "output_contract_miss",
                    "severity": "medium",
                    "message": "Response missed baseline chat markers: Inputs:, Outputs:",
                    "evidence": {"case_id": "P02", "expected_workflow": "code_investigation.plan"},
                }
            ]
        ),
    )

    report = run_report(tmp_path, taxonomy=taxonomy)
    recommendation = report["recommendations"][0]  # type: ignore[index]

    assert report["status"] == "passed"
    assert recommendation["target_surface"] == "chat_contract"
    assert "vllm_agent_gateway/controller_service/server.py" in recommendation["target_file_or_artifact"]
    assert "vllm_agent_gateway/controllers/code_investigation/plan.py" in recommendation["target_file_or_artifact"]
    assert "test_chat_response_contract.py" in recommendation["validation_command"]
    assert "FormatA/JSON chat contract" in recommendation["minimal_repair_recommendation"]


def test_eval_repair_loop_does_not_treat_setup_json_refs_as_model_quality(tmp_path: Path) -> None:
    recursive = valid_recursive_report()
    recursive["rounds"][0]["accepted_findings"] = [  # type: ignore[index]
        {
            "id": "F001",
            "category": "setup_issue",
            "severity": "medium",
            "summary": "Line-ending warning needed clearer setup docs.",
            "evidence_refs": ["runtime-state/first-time-user-doctor/setup.json"],
            "owner": "docs",
            "action": "Document the warning.",
            "validation_refs": ["python scripts/check_docs_index.py"],
        }
    ]
    recursive_path = write_json(tmp_path / "recursive.json", recursive)

    report = run_report(tmp_path, recursive=recursive_path)
    recommendation = report["recommendations"][0]  # type: ignore[index]

    assert report["status"] == "passed"
    assert recommendation["failure_category"] == "docs_setup_issue"
    assert recommendation["target_surface"] == "docs_setup"
    assert recommendation["validation_command"] == "python scripts/run_productized_setup.py validate"


def test_eval_repair_loop_model_quality_command_matches_cli_shape(tmp_path: Path) -> None:
    taxonomy = write_json(
        tmp_path / "taxonomy.json",
        taxonomy_report(
            [
                {
                    "report_label": "unit",
                    "report_path": "unit-input.json",
                    "source": "classified_failures[0]",
                    "category": "model_quality",
                    "severity": "medium",
                    "message": "model output was malformed and not valid json",
                    "evidence": {"case_id": "P05"},
                }
            ]
        ),
    )

    report = run_report(tmp_path, taxonomy=taxonomy)
    command = report["recommendations"][0]["validation_command"]  # type: ignore[index]

    assert report["status"] == "passed"
    assert command.startswith("python scripts/generate_model_capability_profile.py")
    assert "--portability-report-path runtime-state/model-portability/phase100-current-skip-live.json" in command


def test_eval_repair_loop_blocks_cycle_count_above_two(tmp_path: Path) -> None:
    recursive = valid_recursive_report()
    recursive["rounds"][0]["accepted_findings"] = [  # type: ignore[index]
        {
            "id": "F001",
            "category": "routing_miss",
            "severity": "high",
            "summary": "Wrong workflow selected.",
            "evidence_refs": ["route-decision.json"],
            "owner": "router",
            "action": "Repair narrow route rule.",
            "validation_refs": ["python scripts/validate_founder_field_prompt_matrix.py"],
            "repair_cycle_count": 3,
        }
    ]
    recursive_path = write_json(tmp_path / "recursive.json", recursive)

    report = run_report(tmp_path, recursive=recursive_path)

    assert report["status"] == "failed"
    assert any("repair_cycle_count exceeds 2" in error for error in report["validation_errors"])  # type: ignore[index]


def test_eval_repair_loop_requires_holdout_for_current_phase_tightening(tmp_path: Path) -> None:
    recursive = valid_recursive_report()
    recursive["rounds"][0]["accepted_findings"] = [  # type: ignore[index]
        {
            "id": "F001",
            "category": "output_contract_miss",
            "severity": "medium",
            "summary": "Current output contract fix needs rerun proof.",
            "evidence_refs": ["visible-response.json"],
            "owner": "chat_contract",
            "action": "Tighten current chat output renderer.",
            "validation_refs": ["python -m pytest tests/regression/test_chat_response_contract.py -q"],
            "current_phase_tightening": True,
            "target_prompt_case_id": "P01",
        }
    ]
    recursive_path = write_json(tmp_path / "recursive.json", recursive)

    report = run_report(tmp_path, recursive=recursive_path, holdout="")

    assert report["status"] == "failed"
    assert any("holdout_prompt_case_id is required" in error for error in report["validation_errors"])  # type: ignore[index]


def test_eval_repair_loop_requires_target_and_holdout_pass_for_current_phase_tightening(tmp_path: Path) -> None:
    recursive = valid_recursive_report()
    recursive["rounds"][0]["accepted_findings"] = [  # type: ignore[index]
        {
            "id": "F001",
            "category": "output_contract_miss",
            "severity": "medium",
            "summary": "Current output contract fix needs rerun proof.",
            "evidence_refs": ["visible-response.json"],
            "owner": "chat_contract",
            "action": "Tighten current chat output renderer.",
            "validation_refs": ["python -m pytest tests/regression/test_chat_response_contract.py -q"],
            "current_phase_tightening": True,
            "target_prompt_case_id": "P01",
            "holdout_prompt_case_id": "P02",
        }
    ]
    recursive_path = write_json(tmp_path / "recursive.json", recursive)

    report = run_report(tmp_path, recursive=recursive_path, target="P01", holdout="P02")

    assert report["status"] == "failed"
    assert any("target_result_status must be passed" in error for error in report["validation_errors"])  # type: ignore[index]
    assert any("holdout_result_status must be passed" in error for error in report["validation_errors"])  # type: ignore[index]


def test_eval_repair_loop_allows_current_phase_tightening_after_target_and_holdout_pass(tmp_path: Path) -> None:
    recursive = valid_recursive_report()
    recursive["rounds"][0]["accepted_findings"] = [  # type: ignore[index]
        {
            "id": "F001",
            "category": "output_contract_miss",
            "severity": "medium",
            "summary": "Current output contract fix has rerun proof.",
            "evidence_refs": ["visible-response.json"],
            "owner": "chat_contract",
            "action": "Tighten current chat output renderer.",
            "validation_refs": ["python -m pytest tests/regression/test_chat_response_contract.py -q"],
            "current_phase_tightening": True,
            "target_prompt_case_id": "P01",
            "holdout_prompt_case_id": "P02",
            "target_result_status": "passed",
            "holdout_result_status": "passed",
        }
    ]
    recursive_path = write_json(tmp_path / "recursive.json", recursive)

    report = run_report(tmp_path, recursive=recursive_path, target="P01", holdout="P02")

    assert report["status"] == "passed"
    recommendation = report["recommendations"][0]  # type: ignore[index]
    assert recommendation["target_result_status"] == "passed"
    assert recommendation["holdout_result_status"] == "passed"


def test_eval_repair_loop_blocks_holdout_regression(tmp_path: Path) -> None:
    recursive = valid_recursive_report()
    recursive["rounds"][0]["accepted_findings"] = [  # type: ignore[index]
        {
            "id": "F001",
            "category": "output_contract_miss",
            "severity": "medium",
            "summary": "Current output contract fix needs rerun proof.",
            "evidence_refs": ["visible-response.json"],
            "owner": "chat_contract",
            "action": "Tighten current chat output renderer.",
            "validation_refs": ["python -m pytest tests/regression/test_chat_response_contract.py -q"],
            "current_phase_tightening": True,
            "target_prompt_case_id": "P01",
            "holdout_prompt_case_id": "P02",
            "holdout_result_status": "regressed",
        }
    ]
    recursive_path = write_json(tmp_path / "recursive.json", recursive)

    report = run_report(tmp_path, recursive=recursive_path, target="P01", holdout="P02")

    assert report["status"] == "failed"
    assert any("holdout_result_status must be passed" in error for error in report["validation_errors"])  # type: ignore[index]


def test_eval_repair_loop_blocks_unresolved_high_recursive_findings(tmp_path: Path) -> None:
    recursive = valid_recursive_report()
    recursive["rounds"][0]["blind_findings"] = [  # type: ignore[index]
        {
            "id": "F999",
            "category": "routing_miss",
            "severity": "high",
            "summary": "Wrong workflow selected.",
            "evidence_refs": ["route-decision.json"],
        }
    ]
    recursive_path = write_json(tmp_path / "recursive.json", recursive)

    report = run_report(tmp_path, recursive=recursive_path)

    assert report["status"] == "failed"
    assert any("unresolved critical/high" in error for error in report["validation_errors"])  # type: ignore[index]


def test_eval_repair_loop_blocks_structured_recursive_fixture_mutation_evidence(tmp_path: Path) -> None:
    recursive = valid_recursive_report()
    recursive["rounds"][0]["blind_findings"] = [  # type: ignore[index]
        {
            "id": "F999",
            "category": "unsafe_behavior",
            "severity": "medium",
            "summary": "Fixture guard detected source mutation.",
            "evidence_refs": ["mutation-proof.json"],
            "evidence": {"source_changed": True},
        }
    ]
    recursive_path = write_json(tmp_path / "recursive.json", recursive)

    report = run_report(tmp_path, recursive=recursive_path)

    assert report["status"] == "failed"
    assert any("protected fixture mutation" in error for error in report["validation_errors"])  # type: ignore[index]


def test_eval_repair_loop_blocks_structured_advisory_holdout_regression(tmp_path: Path) -> None:
    recursive = valid_recursive_report()
    recursive["rounds"][0]["accepted_findings"] = [  # type: ignore[index]
        {
            "id": "F001",
            "category": "overfitting_risk",
            "severity": "medium",
            "summary": "Target improved, but structured evidence says holdout failed.",
            "evidence_refs": ["holdout-proof.json"],
            "evidence": {"holdout_result_status": "regressed"},
            "owner": "prompt_catalog",
            "action": "Keep recommendation advisory.",
            "validation_refs": ["python scripts/validate_founder_field_prompt_matrix.py"],
        }
    ]
    recursive_path = write_json(tmp_path / "recursive.json", recursive)

    report = run_report(tmp_path, recursive=recursive_path)

    assert report["status"] == "failed"
    assert any("holdout regression" in error for error in report["validation_errors"])  # type: ignore[index]


def test_eval_repair_loop_blocks_low_recursive_score(tmp_path: Path) -> None:
    recursive = valid_recursive_report()
    recursive["score_summary"]["total_score"] = 84  # type: ignore[index]
    recursive_path = write_json(tmp_path / "recursive.json", recursive)

    report = run_report(tmp_path, recursive=recursive_path)

    assert report["status"] == "failed"
    assert any("total_score is below 85" in error for error in report["validation_errors"])  # type: ignore[index]


def test_eval_repair_loop_blocks_round_exhaustion(tmp_path: Path) -> None:
    recursive = valid_recursive_report()
    recursive["convergence"]["status"] = "round_limit_exhausted"  # type: ignore[index]
    recursive_path = write_json(tmp_path / "recursive.json", recursive)

    report = run_report(tmp_path, recursive=recursive_path)

    assert report["status"] == "failed"
    assert any("round_limit_exhausted" in error for error in report["validation_errors"])  # type: ignore[index]
