import json
from pathlib import Path

from vllm_agent_gateway.acceptance.blind_baseline_delta_report import (
    BlindBaselineDeltaReportConfig,
    build_blind_baseline_delta_report,
    run_blind_baseline_delta_report,
    validate_blind_baseline_delta_report,
    validate_policy,
)


def write_json(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def case_evidence(case_id: str, response_path: Path, *, score: int = 100, status: str = "passed") -> dict:
    return {
        "case_id": case_id,
        "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
        "expected_workflow": "code_investigation.plan",
        "expected_skill_id": "example-skill",
        "status": status,
        "score": score,
        "score_breakdown": {
            "routing": 20 if status == "passed" else 0,
            "answer_completeness": 30 if score >= 85 else 10,
            "evidence": 20 if score >= 85 else 5,
            "safety_boundary": 15,
            "output_contract": 15 if status == "passed" else 0,
        },
        "quality_classification": "pass" if score >= 85 and status == "passed" else "blocker",
        "output_contract_status": "passed" if status == "passed" else "failed",
        "semantic_quality_status": "passed" if status == "passed" else "failed",
        "route_surface": "anythingllm_via_workflow_router_gateway",
        "run_id": f"workflow-router-test-{case_id}",
        "response_artifact_path": str(response_path),
        "response_artifact_sha256": sha256_file(response_path),
        "blind_baseline_comparison": {
            "ideal_answer_shape": "A useful answer.",
            "must_have_facts": ["fact"],
            "must_have_markers": ["Answer:"],
            "evidence_expectations": ["source refs"],
            "safety_boundaries": ["read only"],
            "output_expectations": ["chat-visible answer"],
        },
        "initial_difference": "No difference.",
        "prompt_risk": "",
        "suggested_prompt_if_missed": "",
    }


def synthetic_sources(tmp_path: Path) -> tuple[dict, dict, dict, dict, dict[str, Path]]:
    c1_response = tmp_path / "responses" / "C1.txt"
    c2_response = tmp_path / "responses" / "C2.txt"
    c1_response.parent.mkdir(parents=True, exist_ok=True)
    c1_response.write_text("selected_workflow: code_investigation.plan\nAnswer:\nEvidence:\n", encoding="utf-8")
    c2_response.write_text("selected_workflow: code_investigation.plan\nAnswer:\nEvidence:\n", encoding="utf-8")
    policy = {
        "schema_version": 1,
        "kind": "blind_baseline_delta_report_policy",
        "phase": 178,
        "priority_backlog_id": "P0-BB-042",
        "source_round2_report_path": "round2.json",
        "source_field_report_path": "field.json",
        "source_blind_baseline_path": "baseline.json",
        "required_route_surface": "anythingllm_via_workflow_router_gateway",
        "minimum_score": 85,
        "required_dimensions": [
            "routing",
            "evidence",
            "correctness",
            "completeness",
            "format",
            "user_visible_usefulness",
        ],
        "required_case_ids": ["C1", "C2"],
        "case_groups": [
            {
                "family": "synthetic_family",
                "target_case_ids": ["C1"],
                "holdout_case_ids": ["C2"],
            }
        ],
        "acceptance_marker": "PHASE178 BLIND BASELINE DELTA REPORT PASS",
    }
    round2 = {
        "kind": "founder_field_round2_report",
        "status": "passed",
        "case_evidence": [case_evidence("C1", c1_response), case_evidence("C2", c2_response)],
    }
    field = {
        "kind": "founder_field_prompt_evaluation",
        "status": "passed",
        "created_at": "20260610T010000000000Z",
        "fixture_state_before": {"state": "same"},
        "fixture_state_after": {"state": "same"},
        "cases": [{"case_id": "C1"}, {"case_id": "C2"}],
    }
    baseline = {
        "kind": "founder_field_round2_blind_baselines",
        "local_model_output_seen_by_blind_agent": False,
        "generated_at": "20260610T000000000000Z",
        "cases": [{"case_id": "C1"}, {"case_id": "C2"}],
    }
    paths = {
        "policy": write_json(tmp_path / "policy.json", policy),
        "round2": write_json(tmp_path / "round2.json", round2),
        "field": write_json(tmp_path / "field.json", field),
        "baseline": write_json(tmp_path / "baseline.json", baseline),
    }
    return policy, round2, field, baseline, paths


def test_blind_baseline_delta_policy_passes_synthetic_contract(tmp_path: Path) -> None:
    policy, _, _, _, _ = synthetic_sources(tmp_path)

    assert validate_policy(policy) == []


def test_blind_baseline_delta_report_passes_synthetic_sources(tmp_path: Path) -> None:
    policy, round2, field, baseline, paths = synthetic_sources(tmp_path)

    report = build_blind_baseline_delta_report(
        config_root=tmp_path,
        policy=policy,
        round2_report=round2,
        field_report=field,
        baseline_package=baseline,
        policy_path=paths["policy"],
        round2_report_path=paths["round2"],
        field_report_path=paths["field"],
        baseline_path=paths["baseline"],
    )

    assert report["status"] == "passed"
    assert report["summary"]["delta_count"] == 2
    assert report["summary"]["blocking_gap_count"] == 0
    assert report["deltas"][0]["baseline_before_local"] is True
    assert report["deltas"][0]["gap_classes"] == ["none"]


def test_blind_baseline_delta_report_rejects_late_blind_baseline(tmp_path: Path) -> None:
    policy, round2, field, baseline, _ = synthetic_sources(tmp_path)
    baseline["generated_at"] = "20260610T020000000000Z"

    report = build_blind_baseline_delta_report(
        config_root=tmp_path,
        policy=policy,
        round2_report=round2,
        field_report=field,
        baseline_package=baseline,
    )

    assert report["status"] == "failed"
    assert any(error["id"] == "baseline.generated_at" for error in report["validation_errors"])


def test_blind_baseline_delta_report_records_blocking_gap_candidate(tmp_path: Path) -> None:
    policy, round2, field, baseline, _ = synthetic_sources(tmp_path)
    response_path = Path(round2["case_evidence"][0]["response_artifact_path"])
    round2["case_evidence"][0] = case_evidence("C1", response_path, score=50, status="failed")

    report = build_blind_baseline_delta_report(
        config_root=tmp_path,
        policy=policy,
        round2_report=round2,
        field_report=field,
        baseline_package=baseline,
    )

    assert report["status"] == "failed"
    assert report["summary"]["blocking_gap_count"] == 1
    assert report["backlog_candidates"][0]["case_id"] == "C1"
    assert "routing_miss" in report["backlog_candidates"][0]["gap_classes"]


def test_run_blind_baseline_delta_report_writes_json_and_markdown(tmp_path: Path) -> None:
    _, _, _, _, _ = synthetic_sources(tmp_path)

    report = run_blind_baseline_delta_report(
        BlindBaselineDeltaReportConfig(
            config_root=tmp_path,
            policy_path=Path("policy.json"),
            output_path=Path("out/report.json"),
            markdown_output_path=Path("out/report.md"),
        )
    )
    persisted = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))

    assert report["status"] == "passed"
    assert persisted["report_path"] == str((tmp_path / "out" / "report.json").resolve())
    assert (tmp_path / "out" / "report.md").read_text(encoding="utf-8").startswith("# Blind-Baseline Delta Report")
    assert (
        validate_blind_baseline_delta_report(
            persisted,
            config_root=tmp_path,
            policy=json.loads((tmp_path / "policy.json").read_text(encoding="utf-8")),
            round2_report=json.loads((tmp_path / "round2.json").read_text(encoding="utf-8")),
            field_report=json.loads((tmp_path / "field.json").read_text(encoding="utf-8")),
            baseline_package=json.loads((tmp_path / "baseline.json").read_text(encoding="utf-8")),
            policy_path=tmp_path / "policy.json",
            round2_report_path=tmp_path / "round2.json",
            field_report_path=tmp_path / "field.json",
            baseline_path=tmp_path / "baseline.json",
        )
        == []
    )
