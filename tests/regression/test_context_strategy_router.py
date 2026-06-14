from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.context_index_prototype import read_json_object, write_json
from vllm_agent_gateway.acceptance.context_strategy_router import (
    DEFAULT_POLICY_PATH,
    ContextStrategyRouterConfig,
    run_context_strategy_router,
    validate_policy,
)
from vllm_agent_gateway.controllers.large_context.context_strategy import (
    select_context_strategy,
)
from vllm_agent_gateway.controllers.large_context.retrieval_answer import (
    RetrievalAnswerCategory,
    classify_request,
)
from vllm_agent_gateway.controllers.workflow_router.plan import (
    WorkflowRouterPlanRequest,
    invoke_workflow_router_plan,
    workflow_kind_for_request,
)
from vllm_agent_gateway.controllers.large_context.strategy_types import ContextStrategy
from tests.regression.test_retrieval_backed_chat_answer_gate import make_context_index_policy


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def test_phase220_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase220_policy_rejects_missing_strategy() -> None:
    mutated = copy.deepcopy(policy())
    mutated["required_strategy_ids"] = [item for item in mutated["required_strategy_ids"] if item != "artifact_paging"]

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.required_strategy_ids" for item in errors)


def test_context_strategy_selector_blocks_stale_index(tmp_path: Path) -> None:
    target_root, context_policy_path = make_context_index_policy(tmp_path)
    context_policy = read_json_object(context_policy_path)
    index_path = Path(context_policy["index_artifact"]["path"])
    index = read_json_object(index_path)
    chunks = index["chunks"]
    chunks[0]["source_sha256"] = "0" * 64
    stale_index_path = tmp_path / "stale-index.json"
    write_json(stale_index_path, index)
    stale_policy = dict(context_policy)
    stale_policy["index_artifact"] = {**stale_policy["index_artifact"], "path": str(stale_index_path)}
    stale_policy_path = tmp_path / "stale-policy.json"
    write_json(stale_policy_path, stale_policy)

    decision = select_context_strategy(
        config_root=REPO_ROOT,
        target_root=target_root,
        user_request="In the large corpus fixture, find evidence for how risk gate decisions flow into audit summaries.",
        route_evidence=[{"source": "router_rule", "rule": "large_context_read_only_terms"}],
        selected_workflow="code_investigation.plan",
        request_context={"context_index_policy_path": str(stale_policy_path)},
    )

    assert decision["selected_strategy"] == ContextStrategy.REFUSAL.value
    assert decision["status"] == "blocked"
    assert decision["reason"] == "stale_index_or_source_hash"
    assert decision["source_freshness_status"] == "stale"


def test_context_strategy_selector_selects_all_core_strategies(tmp_path: Path) -> None:
    target_root, context_policy_path = make_context_index_policy(tmp_path)
    route_evidence = [{"source": "router_rule", "rule": "large_context_read_only_terms"}]
    common = {
        "config_root": REPO_ROOT,
        "target_root": target_root,
        "route_evidence": route_evidence,
        "selected_workflow": "code_investigation.plan",
        "request_context": {"context_index_policy_path": str(context_policy_path)},
    }

    cases = {
        "retrieval": "In the large corpus fixture, find evidence for how risk gate decisions flow into audit summaries.",
        "summarization": "In the large corpus fixture, summarize the generated service architecture without reading every file.",
        "artifact_paging": "In the large corpus fixture, produce a long evidence report with all relevant top files for order replay.",
        "chunked_investigation": "In the large corpus fixture, trace the end-to-end cross-file flow across the whole corpus.",
        "refusal": "Can the current local model take this entire corpus as one raw prompt?",
    }

    results = {
        expected: select_context_strategy(user_request=prompt, **common)["selected_strategy"]
        for expected, prompt in cases.items()
    }
    direct = select_context_strategy(
        config_root=REPO_ROOT,
        target_root=REPO_ROOT,
        user_request="Explain README.md. Read only.",
        route_evidence=[],
        selected_workflow="code_investigation.plan",
        request_context={},
    )["selected_strategy"]

    assert direct == "direct_context"
    assert results == {key: key for key in cases}


def test_small_repo_retrieval_word_does_not_trigger_large_context(tmp_path: Path) -> None:
    target_root = tmp_path / "context-retrieval-fixture"
    target_root.mkdir()
    (target_root / "README.md").write_text("# Retrieval fixture\n\nThis file discusses retrieval helpers.\n", encoding="utf-8")

    result = invoke_workflow_router_plan(
        WorkflowRouterPlanRequest(
            config_root=REPO_ROOT,
            target_root=target_root,
            output_root=tmp_path / "out",
            user_request=f"In {target_root}, find where retrieval starts in this repo. Read only.",
            mode="plan_only",
            budgets={"max_model_calls": 0, "max_selected_skills": 5, "max_selected_tools": 5},
        )
    )

    summary = result.report["summary"]
    assert summary["route_status"] == "ready"
    assert summary["selected_context_strategy"] == "direct_context"
    assert summary["context_strategy_reason"] == "bounded_non_large_context_request"


def test_evidence_lookup_raw_stuffing_disclosure_keeps_retrieval_strategy(tmp_path: Path) -> None:
    target_root, context_policy_path = make_context_index_policy(tmp_path)

    decision = select_context_strategy(
        config_root=REPO_ROOT,
        target_root=target_root,
        user_request=(
            "In the large corpus fixture, find evidence for how risk gate decisions flow into audit summaries. "
            "Include source refs, limitations, and whether raw prompt stuffing was used."
        ),
        route_evidence=[{"source": "router_rule", "rule": "large_context_read_only_terms"}],
        selected_workflow="code_investigation.plan",
        request_context={"context_index_policy_path": str(context_policy_path)},
    )

    assert decision["selected_strategy"] == ContextStrategy.RETRIEVAL.value
    assert decision["status"] == "selected"
    assert decision["execution_path"] == "large_context.retrieval_answer"
    assert decision["reason"] == "large_specific_evidence_lookup"


def test_large_context_architecture_holdout_routes_to_summarization(tmp_path: Path) -> None:
    target_root, context_policy_path = make_context_index_policy(tmp_path)
    prompt = (
        f"In {target_root}, give a bounded architecture summary using representative evidence instead of every file."
    )
    workflow_id, status, evidence = workflow_kind_for_request(prompt)

    decision = select_context_strategy(
        config_root=REPO_ROOT,
        target_root=target_root,
        user_request=prompt,
        route_evidence=evidence,
        selected_workflow=workflow_id,
        request_context={"context_index_policy_path": str(context_policy_path)},
    )

    assert workflow_id == "code_investigation.plan"
    assert status == "ready"
    assert decision["selected_strategy"] == ContextStrategy.SUMMARIZATION.value
    assert decision["execution_path"] == "large_context.retrieval_answer"


def test_large_context_raw_prompt_paste_holdout_routes_to_limit_refusal(tmp_path: Path) -> None:
    target_root, context_policy_path = make_context_index_policy(tmp_path)
    prompt = (
        f"Should I paste {target_root} into Qwen as one prompt? "
        "Answer with limits, safer approach, and missing benchmark proof."
    )
    workflow_id, status, evidence = workflow_kind_for_request(prompt)

    decision = select_context_strategy(
        config_root=REPO_ROOT,
        target_root=target_root,
        user_request=prompt,
        route_evidence=evidence,
        selected_workflow=workflow_id,
        request_context={"context_index_policy_path": str(context_policy_path)},
    )

    assert workflow_id == "code_investigation.plan"
    assert status == "ready"
    assert decision["selected_strategy"] == ContextStrategy.REFUSAL.value
    assert decision["execution_path"] == "large_context.retrieval_answer"
    assert decision["reason"] == "raw_1m_prompt_support_unproven"
    assert classify_request(prompt) == RetrievalAnswerCategory.LIMITATIONS


def test_phase220_report_passes_without_phase219_precondition(tmp_path: Path) -> None:
    report = run_context_strategy_router(
        ContextStrategyRouterConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase220-report.json",
            markdown_output_path=tmp_path / "phase220-report.md",
            require_artifacts=False,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["all_strategies_covered"] is True
    assert report["summary"]["phase221_ready"] is True
    serialized = json.dumps(report, sort_keys=True)
    assert "PHASE216_DUMMY_SECRET_DO_NOT_EXPOSE" not in serialized
