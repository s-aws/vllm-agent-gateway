from __future__ import annotations

from vllm_agent_gateway.acceptance.release_candidate_large_context_strategy_replay import (
    build_report,
    validate_policy,
    validate_report,
)


def policy() -> dict:
    return {
        "schema_version": 1,
        "kind": "release_candidate_large_context_strategy_replay_policy",
        "phase": 241,
        "priority_backlog_id": "P0-M14-241",
        "milestone_ids": ["M6", "M8", "M16", "M14"],
        "required_decision": "release_candidate_large_context_strategy_ready",
        "required_anythingllm": {
            "api_base_url": "http://127.0.0.1:3001",
            "workflow_router_base_url": "http://127.0.0.1:8500/v1",
            "workspace": "my-workspace",
            "model": "Qwen3-Coder-30B-A3B-Instruct",
            "provider": "generic-openai",
        },
        "required_surfaces": ["gateway", "anythingllm"],
        "required_strategy_ids": ["retrieval", "artifact_paging", "summarization", "refusal", "chunked_investigation"],
        "required_bootstrap_reports": ["large_corpus_context_budget_inventory", "context_index_prototype"],
        "required_live_reports": ["large_context_usability_live_closeout", "chunked_investigation_executor_implementation"],
        "minimums": {
            "phase221_response_count": 4,
            "phase223_response_count": 2,
            "anythingllm_response_count": 3,
            "small_repo_regression_count": 2,
            "large_corpus_estimated_tokens": 100,
        },
        "safety_requirements": {
            "raw_1m_prompt_support_proven": False,
            "raw_prompt_stuffing_allowed": False,
            "source_text_retention": "metadata_only",
            "store_source_text": False,
            "store_rejected_content": False,
            "generated_corpus_unchanged_after_live_replay": True,
            "artifact_only_answers_allowed": False,
        },
        "blind_baseline_summary": {
            "ideal_answer_shape": ["answer first"],
            "must_have_facts": ["large context is retrieval first"],
            "hard_failures": ["raw 1M claim"],
        },
        "acceptance_marker": "RELEASE CANDIDATE LARGE CONTEXT STRATEGY REPLAY PASS",
    }


def phase214_report() -> dict:
    return {
        "status": "passed",
        "report_path": "phase214.json",
        "summary": {
            "estimated_token_count": 1286080,
            "raw_1m_prompt_support_proven": False,
        },
        "generated_fixture": {"root": "/tmp/generated-large-corpus"},
    }


def phase217_report() -> dict:
    return {
        "status": "passed",
        "report_path": "phase217.json",
        "summary": {
            "source_text_retention": "metadata_only",
            "store_source_text": False,
            "store_rejected_content": False,
        },
    }


def phase221_report() -> dict:
    return {
        "status": "passed",
        "report_path": "phase221.json",
        "summary": {
            "response_count": 4,
            "failed_response_count": 0,
            "raw_prompt_stuffing_allowed": False,
        },
        "responses": [
            {"surface": "gateway", "selected_context_strategy": "retrieval", "run_id": "workflow-router-a"},
            {"surface": "gateway", "selected_context_strategy": "artifact_paging", "run_id": "workflow-router-b"},
            {"surface": "anythingllm", "selected_context_strategy": "summarization", "run_id": "workflow-router-c"},
            {"surface": "anythingllm", "selected_context_strategy": "refusal", "run_id": "workflow-router-d"},
        ],
        "small_repo_regression_results": [{"status": "passed"}, {"status": "passed"}],
    }


def phase223_report() -> dict:
    return {
        "status": "passed",
        "report_path": "phase223.json",
        "summary": {
            "response_count": 2,
            "failed_response_count": 0,
            "raw_prompt_stuffing_allowed": False,
        },
        "responses": [
            {"surface": "gateway", "selected_context_strategy": "chunked_investigation", "run_id": "workflow-router-e"},
            {"surface": "anythingllm", "selected_context_strategy": "chunked_investigation", "run_id": "workflow-router-f"},
        ],
        "small_repo_regression_results": [],
    }


def passing_report() -> dict:
    snapshot = {"path": "/tmp/generated-large-corpus", "exists": True, "file_count": 2, "files": {"a.py": {"sha256": "x", "size": 1}}}
    return build_report(
        policy=policy(),
        target_settings={"status": "passed"},
        bootstrap_reports={"phase214": phase214_report(), "phase217": phase217_report()},
        live_reports={"phase221": phase221_report(), "phase223": phase223_report()},
        corpus_before=snapshot,
        corpus_after=snapshot,
        errors=[],
    )


def test_phase241_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase241_report_passes() -> None:
    report = passing_report()
    assert report["status"] == "passed"
    assert report["decision"] == "release_candidate_large_context_strategy_ready"
    assert validate_report(report, policy()) == []


def test_phase241_rejects_missing_strategy() -> None:
    report = passing_report()
    report["summary"]["strategy_ids"].remove("chunked_investigation")
    report["decision"] = "release_candidate_large_context_strategy_blocked"
    errors = validate_report(report, policy())
    assert any("strategy_ids" in error for error in errors)


def test_phase241_rejects_raw_1m_claim() -> None:
    report = passing_report()
    report["summary"]["raw_1m_prompt_support_proven"] = True
    report["decision"] = "release_candidate_large_context_strategy_blocked"
    errors = validate_report(report, policy())
    assert any("raw_1m_prompt_support_proven" in error for error in errors)


def test_phase241_rejects_generated_corpus_mutation() -> None:
    report = passing_report()
    report["corpus_unchanged"] = False
    report["summary"]["corpus_unchanged"] = False
    report["decision"] = "release_candidate_large_context_strategy_blocked"
    errors = validate_report(report, policy())
    assert any("corpus_unchanged" in error for error in errors)
