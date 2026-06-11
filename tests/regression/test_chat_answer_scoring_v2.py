import json
from pathlib import Path

from vllm_agent_gateway.acceptance.chat_answer_scoring_v2 import (
    ChatAnswerScoringV2Config,
    build_chat_answer_scoring_v2_report,
    run_chat_answer_scoring_v2,
    validate_chat_answer_scoring_v2_report,
    validate_policy,
    validate_sources,
)


def write_json(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_text(path: Path, value: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


def sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def synthetic_case(case_id: str, answer_path: Path, *, evidence_status: str = "passed", evidence_score: int = 20) -> dict:
    return {
        "case_id": case_id,
        "family": "family_a",
        "role": "target",
        "route_surface": "anythingllm_via_workflow_router_gateway",
        "run_id": f"workflow-router-{case_id}",
        "baseline_before_local": True,
        "score": 95 if evidence_status == "passed" else 91,
        "score_breakdown": {
            "answer_completeness": 30,
            "evidence": evidence_score,
            "output_contract": 15,
            "routing": 20,
            "safety_boundary": 15,
        },
        "dimensions": {
            "routing": {"status": "passed", "score": 20},
            "evidence": {"status": evidence_status, "score": evidence_score},
            "correctness": {"status": "passed"},
            "completeness": {"status": "passed", "score": 30},
            "format": {"status": "passed"},
            "user_visible_usefulness": {"status": "passed", "score": 95},
        },
        "gap_classes": ["none"] if evidence_status == "passed" else ["evidence_detail_advisory"],
        "prompt_risk": "" if evidence_status == "passed" else "Prompt may need tighter source wording.",
        "local_answer_path": str(answer_path),
        "local_answer_sha256": sha256_file(answer_path) if answer_path.is_file() else "",
    }


def synthetic_policy(expected_delta_count: int = 2) -> dict:
    return {
        "schema_version": 1,
        "kind": "chat_answer_scoring_v2_policy",
        "phase": 192,
        "priority_backlog_id": "P0-BB-056",
        "acceptance_marker": "PHASE192 CHAT ANSWER SCORING V2 PASS",
        "source_blind_baseline_delta_report_path": "delta.json",
        "source_founder_round2_report_path": "round2.json",
        "source_drift_detection_report_path": "drift.json",
        "source_kinds": {
            "blind_baseline_delta_report": "blind_baseline_delta_report",
            "founder_round2_report": "founder_field_round2_report",
            "drift_detection_report": "prompt_family_drift_detection_report",
        },
        "expected_delta_count": expected_delta_count,
        "expected_drift_active_catalog_blocking_drift_count": 0,
        "expected_required_surface": "anythingllm_via_workflow_router_gateway",
        "minimum_case_score": 85,
        "minimum_report_score": 85,
        "classification_contract": {
            "required_dimensions": [
                "routing",
                "evidence_relevance",
                "correctness",
                "answer_completeness",
                "source_refs",
                "format_adherence",
                "safety_boundaries",
                "user_visible_usefulness",
            ],
            "blocking_dimensions": [
                "routing",
                "correctness",
                "answer_completeness",
                "source_refs",
                "format_adherence",
                "safety_boundaries",
                "user_visible_usefulness",
            ],
            "allowed_repair_targets": [
                "none",
                "router",
                "evidence_relevance",
                "correctness",
                "answer_completeness",
                "source_refs",
                "format_contract",
                "safety_boundary",
                "user_visible_usefulness",
                "prompt_wording",
                "prompt_governance",
            ],
            "allowed_classifications": ["pass", "advisory", "fail"],
            "score_weights": {
                "routing": 15,
                "evidence_relevance": 15,
                "correctness": 15,
                "answer_completeness": 15,
                "source_refs": 10,
                "format_adherence": 10,
                "safety_boundaries": 10,
                "user_visible_usefulness": 10,
            },
        },
        "scoring_examples": [
            {
                "case_id": "PASS",
                "expected_classification": "pass",
                "expected_repair_targets": ["none"],
                "response_text": "Answer:\nselected_workflow: code_investigation.plan\nSource refs:\n- core/example.py:10\nEvidence:\n- direct\nSource mutation: false\n",
                "source_case": {
                    **synthetic_case("PASS", Path("unused")),
                    "local_answer_path": "",
                    "local_answer_sha256": "",
                },
            },
            {
                "case_id": "ADVISORY",
                "expected_classification": "advisory",
                "expected_repair_targets": ["evidence_relevance", "prompt_wording"],
                "response_text": "Answer:\nselected_workflow: code_investigation.plan\nSource refs:\n- core/example.py:10\nEvidence:\n- supporting\nSource mutation: false\n",
                "source_case": {
                    **synthetic_case("ADVISORY", Path("unused"), evidence_status="advisory", evidence_score=14),
                    "local_answer_path": "",
                    "local_answer_sha256": "",
                },
            },
            {
                "case_id": "FAIL",
                "expected_classification": "fail",
                "expected_repair_targets": ["router", "evidence_relevance", "source_refs", "format_contract"],
                "response_text": "Looks fine.",
                "source_case": {
                    **synthetic_case("FAIL", Path("unused")),
                    "route_surface": "direct_controller",
                    "dimensions": {
                        "routing": {"status": "failed", "score": 0},
                        "evidence": {"status": "failed", "score": 0},
                        "correctness": {"status": "passed"},
                        "completeness": {"status": "passed", "score": 30},
                        "format": {"status": "failed"},
                        "user_visible_usefulness": {"status": "passed", "score": 90},
                    },
                    "local_answer_path": "",
                    "local_answer_sha256": "",
                },
            },
        ],
    }


def synthetic_sources(tmp_path: Path) -> tuple[dict, dict[str, dict], dict[str, Path]]:
    pass_answer = write_text(
        tmp_path / "answers" / "pass.txt",
        "Answer:\nselected_workflow: code_investigation.plan\nSource refs:\n- core/example.py:10\nEvidence:\n- direct\nRelated tests:\n- tests/test_example.py\nRecommended commands:\n- python -m pytest tests/test_example.py -v\nSource mutation: false\n",
    )
    advisory_answer = write_text(
        tmp_path / "answers" / "advisory.txt",
        "Answer:\nselected_workflow: code_investigation.plan\nSource refs:\n- core/example.py:10\nEvidence:\n- supporting\nRecommended commands:\n- python -m pytest tests/test_example.py -v\nSource mutation: false\n",
    )
    policy = synthetic_policy()
    delta = {
        "kind": "blind_baseline_delta_report",
        "status": "passed",
        "deltas": [
            synthetic_case("P01", pass_answer),
            synthetic_case("P02", advisory_answer, evidence_status="advisory", evidence_score=14),
        ],
    }
    round2 = {"kind": "founder_field_round2_report", "status": "passed", "summary": {"case_count": 2}}
    drift = {
        "kind": "prompt_family_drift_detection_report",
        "status": "passed",
        "summary": {"active_catalog_blocking_drift_count": 0},
    }
    sources = {
        "blind_baseline_delta_report": delta,
        "founder_round2_report": round2,
        "drift_detection_report": drift,
    }
    paths = {
        "policy": write_json(tmp_path / "policy.json", policy),
        "blind_baseline_delta_report": write_json(tmp_path / "delta.json", delta),
        "founder_round2_report": write_json(tmp_path / "round2.json", round2),
        "drift_detection_report": write_json(tmp_path / "drift.json", drift),
    }
    return policy, sources, paths


def test_chat_answer_scoring_v2_policy_and_sources_pass(tmp_path: Path) -> None:
    policy, sources, paths = synthetic_sources(tmp_path)

    assert validate_policy(policy) == []
    assert validate_sources(policy, sources, {key: value for key, value in paths.items() if key != "policy"}) == []


def test_chat_answer_scoring_v2_report_scores_pass_and_advisory_cases(tmp_path: Path) -> None:
    policy, sources, paths = synthetic_sources(tmp_path)

    report = build_chat_answer_scoring_v2_report(
        config_root=tmp_path,
        policy=policy,
        sources=sources,
        paths={key: value for key, value in paths.items() if key != "policy"},
        policy_path=paths["policy"],
    )

    assert report["status"] == "passed"
    assert report["summary"]["classification_counts"] == {"advisory": 1, "pass": 1}
    assert report["summary"]["repair_target_counts"] == {"evidence_relevance": 1, "none": 1, "prompt_wording": 1}
    assert report["summary"]["example_count"] == 3
    assert "pass with advisory cases" in report["summary"]["pass_with_advisories_explanation"]
    assert "evidence_relevance" in report["summary"]["next_action"]
    assert all(case["scored_case_id"].startswith(case["case_id"]) for case in report["scored_cases"])


def test_chat_answer_scoring_v2_rejects_active_prompt_drift(tmp_path: Path) -> None:
    policy, sources, paths = synthetic_sources(tmp_path)
    sources["drift_detection_report"]["summary"]["active_catalog_blocking_drift_count"] = 1

    report = build_chat_answer_scoring_v2_report(
        config_root=tmp_path,
        policy=policy,
        sources=sources,
        paths={key: value for key, value in paths.items() if key != "policy"},
        policy_path=paths["policy"],
    )

    assert report["status"] == "failed"
    assert any(error["id"] == "drift.active_catalog_blocking_drift_count" for error in report["validation_errors"])


def test_chat_answer_scoring_v2_rejects_missing_source_refs(tmp_path: Path) -> None:
    policy, sources, paths = synthetic_sources(tmp_path)
    path = Path(sources["blind_baseline_delta_report"]["deltas"][0]["local_answer_path"])
    path.write_text("Answer:\nEvidence:\nNo file refs here.\nSource mutation: false\n", encoding="utf-8")
    sources["blind_baseline_delta_report"]["deltas"][0]["local_answer_sha256"] = sha256_file(path)

    report = build_chat_answer_scoring_v2_report(
        config_root=tmp_path,
        policy=policy,
        sources=sources,
        paths={key: value for key, value in paths.items() if key != "policy"},
        policy_path=paths["policy"],
    )

    p01 = next(case for case in report["scored_cases"] if case["case_id"] == "P01")
    assert report["status"] == "failed"
    assert p01["dimensions"]["source_refs"]["status"] == "failed"
    assert "source_refs" in p01["repair_targets"]


def test_chat_answer_scoring_v2_rejects_late_or_missing_blind_baseline_order(tmp_path: Path) -> None:
    policy, sources, paths = synthetic_sources(tmp_path)
    sources["blind_baseline_delta_report"]["deltas"][0]["baseline_before_local"] = False

    report = build_chat_answer_scoring_v2_report(
        config_root=tmp_path,
        policy=policy,
        sources=sources,
        paths={key: value for key, value in paths.items() if key != "policy"},
        policy_path=paths["policy"],
    )

    assert report["status"] == "failed"
    assert any(error["id"] == "cases.P01.baseline_before_local" for error in report["validation_errors"])


def test_chat_answer_scoring_v2_rejects_stale_report(tmp_path: Path) -> None:
    policy, sources, paths = synthetic_sources(tmp_path)
    report = build_chat_answer_scoring_v2_report(
        config_root=tmp_path,
        policy=policy,
        sources=sources,
        paths={key: value for key, value in paths.items() if key != "policy"},
        policy_path=paths["policy"],
    )
    report["summary"]["classification_counts"] = {"pass": 999}

    errors = validate_chat_answer_scoring_v2_report(
        report,
        config_root=tmp_path,
        policy=policy,
        sources=sources,
        paths={key: value for key, value in paths.items() if key != "policy"},
        policy_path=paths["policy"],
    )

    assert errors == ["report must match rebuilt chat-answer scoring V2 report"]


def test_run_chat_answer_scoring_v2_writes_json_and_markdown(tmp_path: Path) -> None:
    synthetic_sources(tmp_path)

    report = run_chat_answer_scoring_v2(
        ChatAnswerScoringV2Config(
            config_root=tmp_path,
            policy_path=Path("policy.json"),
            output_path=Path("out/report.json"),
            markdown_output_path=Path("out/report.md"),
        )
    )
    persisted = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "out" / "report.md").read_text(encoding="utf-8")

    assert report["status"] == "passed"
    assert persisted["report_path"] == str((tmp_path / "out" / "report.json").resolve())
    assert markdown.startswith("# Chat Answer Scoring V2")
    assert "## Repair Targets" in markdown
    assert "P01|family_a|target|workflow-router-P01" in markdown
