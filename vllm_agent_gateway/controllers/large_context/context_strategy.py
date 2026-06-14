"""Deterministic context strategy selection for workflow-router decisions."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.context_index_prototype import (
    dict_value,
    object_list,
    read_json_object,
    resolve_path,
    sha256_file,
)
from vllm_agent_gateway.controllers.large_context.retrieval_answer import (
    DEFAULT_CONTEXT_INDEX_POLICY_PATH,
    RetrievalAnswerCategory,
    classify_request,
    contains_unsafe_evidence_request,
    load_phase214_budget_summary,
    target_matches_indexed_corpus,
)
from vllm_agent_gateway.controllers.large_context.strategy_types import (
    ContextStrategy,
    ContextStrategyExecutionPath,
    ContextStrategyStatus,
)


SCHEMA_VERSION = 1
DEFAULT_STRATEGY_POLICY_PATH = Path("runtime") / "retrieval_first_context_strategy_design_policy.json"


LARGE_CONTEXT_TERMS = {
    "large corpus",
    "large-corpus",
    "whole corpus",
    "entire corpus",
    "1m token",
    "1 million token",
    "million-token",
    "context budget",
    "context-budget",
    "raw prompt",
    "as one prompt",
    "without reading every file",
    "every file",
    "order replay pipeline",
    "risk gate",
    "audit summar",
    "architecture summary",
    "generated service architecture",
    "representative evidence",
}
RAW_PROMPT_STUFFING_TERMS = {
    "raw prompt",
    "raw-stuff",
    "raw stuff",
    "stuff the whole corpus",
    "stuff the entire corpus",
    "as one prompt",
    "paste into qwen",
    "paste this corpus",
    "paste the corpus",
    "entire corpus as one",
    "whole corpus as one",
    "send the whole corpus",
    "send the entire corpus",
    "1m prompt",
    "1 million token prompt",
    "million-token prompt",
}
RAW_PROMPT_CAPACITY_TERMS = {
    "can the current local model take",
    "can the local model take",
    "can we raw prompt",
    "should i paste",
    "is it safe to paste",
    "paste into qwen",
    "paste this corpus",
    "paste the corpus",
    "take this entire corpus as one",
    "take the entire corpus as one",
    "as one prompt",
    "as one raw prompt",
    "directly into the local model",
}
MUTATION_RISK_TERMS = {
    "apply",
    "change",
    "commit",
    "edit",
    "fix",
    "implement",
    "mutate",
    "refactor",
    "rewrite",
}
ARTIFACT_PAGING_TERMS = {
    "all evidence",
    "all relevant",
    "evidence report",
    "long report",
    "many source",
    "many evidence",
    "paged",
    "pages",
    "top files",
    "top modules",
}
CHUNKED_INVESTIGATION_TERMS = {
    "call chain",
    "dependency chain",
    "end to end",
    "end-to-end",
    "multi-step traversal",
    "multiple bounded",
    "across the whole corpus",
    "cross-file flow",
}


def lower_request(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def contains_any(text: str, terms: set[str]) -> list[str]:
    return sorted(term for term in terms if term in text)


def contains_any_word(text: str, terms: set[str]) -> list[str]:
    return sorted(term for term in terms if re.search(rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z0-9_])", text))


def is_raw_prompt_capacity_request(text: str, category: RetrievalAnswerCategory, matched_raw_terms: list[str]) -> bool:
    if category == RetrievalAnswerCategory.LIMITATIONS:
        return True
    if not matched_raw_terms:
        return False
    return bool(contains_any(text, RAW_PROMPT_CAPACITY_TERMS))


def route_has_rule(route_evidence: list[dict[str, Any]], rule: str) -> bool:
    return any(isinstance(item, dict) and item.get("rule") == rule for item in route_evidence)


def strategy_policy_summary(config_root: Path, policy_path: Path | str = DEFAULT_STRATEGY_POLICY_PATH) -> dict[str, Any]:
    path = Path(policy_path)
    if not path.is_absolute():
        path = config_root / path
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "path": str(path),
            "status": "missing_or_malformed",
            "required_strategy_ids": [],
        }
    required = policy.get("required_strategy_ids")
    return {
        "path": str(path),
        "status": "loaded" if isinstance(required, list) else "malformed",
        "required_strategy_ids": [str(item) for item in required] if isinstance(required, list) else [],
    }


def context_index_policy_path_from_request_context(request_context: dict[str, Any] | None) -> Path | str:
    if isinstance(request_context, dict) and isinstance(request_context.get("context_index_policy_path"), str):
        return request_context["context_index_policy_path"]
    return DEFAULT_CONTEXT_INDEX_POLICY_PATH


def index_freshness_status(config_root: Path, target_root: Path, context_index_policy_path: Path | str) -> dict[str, Any]:
    try:
        policy_path = resolve_path(config_root, str(context_index_policy_path))
        policy = read_json_object(policy_path)
        index_path = resolve_path(config_root, str(dict_value(policy.get("index_artifact")).get("path")))
        index = read_json_object(index_path)
    except (OSError, RuntimeError, json.JSONDecodeError):
        return {"status": "missing_or_malformed", "stale_source_count": 0, "checked_source_count": 0}
    stale_count = 0
    checked_count = 0
    stale_examples: list[str] = []
    for chunk in object_list(index.get("chunks")):
        relative_path = str(chunk.get("relative_path") or chunk.get("source_path") or "")
        if not relative_path or Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
            stale_count += 1
            if len(stale_examples) < 5:
                stale_examples.append(relative_path or "<missing>")
            continue
        source_path = target_root / relative_path
        checked_count += 1
        if not source_path.is_file():
            stale_count += 1
            if len(stale_examples) < 5:
                stale_examples.append(relative_path)
            continue
        stat = source_path.stat()
        if (
            chunk.get("freshness_status") != "fresh"
            or chunk.get("source_sha256") != sha256_file(source_path)
            or chunk.get("source_size") != stat.st_size
            or chunk.get("source_mtime_ns") != stat.st_mtime_ns
        ):
            stale_count += 1
            if len(stale_examples) < 5:
                stale_examples.append(relative_path)
    return {
        "status": "fresh" if stale_count == 0 else "stale",
        "stale_source_count": stale_count,
        "checked_source_count": checked_count,
        "stale_examples": stale_examples,
    }


def has_large_context_intent(text: str, route_evidence: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    compact = lower_request(text)
    matched = contains_any(compact, LARGE_CONTEXT_TERMS)
    if route_has_rule(route_evidence, "large_context_read_only_terms"):
        return True, matched
    return bool(matched), matched


def decision_record(
    *,
    selected_strategy: ContextStrategy,
    status: ContextStrategyStatus,
    execution_path: ContextStrategyExecutionPath,
    reason: str,
    rationale: list[str],
    matched_terms: list[str],
    policy_summary: dict[str, Any],
    budget: dict[str, Any],
    indexed_corpus_match: bool,
    source_freshness: dict[str, Any],
    prompt_class: str,
    blockers: list[dict[str, str]] | None = None,
    safe_alternatives: list[str] | None = None,
) -> dict[str, Any]:
    selected_value = selected_strategy.value
    policy_strategy_ids = [
        str(item)
        for item in policy_summary.get("required_strategy_ids", [])
        if isinstance(item, str) and item
    ] or [item.value for item in ContextStrategy]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "context_strategy_decision",
        "status": status.value,
        "selected_strategy": selected_value,
        "execution_path": execution_path.value,
        "reason": reason,
        "rationale": rationale,
        "matched_terms": matched_terms,
        "prompt_class": prompt_class,
        "indexed_corpus_match": indexed_corpus_match,
        "policy_status": policy_summary.get("status"),
        "policy_path": policy_summary.get("path"),
        "policy_strategy_ids": policy_strategy_ids,
        "estimated_corpus_tokens": budget.get("estimated_corpus_tokens"),
        "target_input_limit": budget.get("target_input_limit"),
        "model_context_limit": budget.get("model_context_limit"),
        "raw_1m_prompt_support_proven": budget.get("raw_1m_prompt_support_proven") is True,
        "source_freshness_status": source_freshness.get("status"),
        "stale_source_count": source_freshness.get("stale_source_count", 0),
        "checked_source_count": source_freshness.get("checked_source_count", 0),
        "stale_examples": source_freshness.get("stale_examples", []),
        "routing_inputs_used": [
            "prompt_intent",
            "target_root",
            "estimated_corpus_tokens",
            "file_count",
            "requested_specificity",
            "output_format",
            "mutation_intent",
            "allowed_root_status",
            "ignore_policy_status",
            "index_safety_status",
            "source_freshness_status",
            "context_budget",
            "ambiguity_level",
        ],
        "rejected_strategies": [
            {
                "strategy": strategy_id,
                "reason": "not_selected_by_phase220_deterministic_precedence",
            }
            for strategy_id in policy_strategy_ids
            if strategy_id != selected_value
        ],
        "blockers": blockers or [],
        "safe_alternatives": safe_alternatives
        or [
            "Use retrieval-first evidence selection.",
            "Use chunked investigation for multi-step flow questions.",
            "Use summarization with explicit sampling limits for overview questions.",
        ],
    }


def select_context_strategy(
    *,
    config_root: Path | str,
    target_root: Path | str,
    user_request: str,
    route_evidence: list[dict[str, Any]],
    selected_workflow: str | None,
    request_context: dict[str, Any] | None = None,
    strategy_policy_path: Path | str = DEFAULT_STRATEGY_POLICY_PATH,
) -> dict[str, Any]:
    root = Path(config_root).resolve()
    target = Path(target_root).resolve()
    policy_summary = strategy_policy_summary(root, strategy_policy_path)
    budget = load_phase214_budget_summary(root)
    compact = lower_request(user_request)
    large_context_intent, large_terms = has_large_context_intent(user_request, route_evidence)
    matched_raw_terms = contains_any(compact, RAW_PROMPT_STUFFING_TERMS)
    matched_mutation_terms = contains_any_word(compact, MUTATION_RISK_TERMS)
    context_index_policy_path = context_index_policy_path_from_request_context(request_context)
    indexed_corpus_match = target_matches_indexed_corpus(root, target, context_index_policy_path)
    source_freshness = (
        index_freshness_status(root, target, context_index_policy_path)
        if indexed_corpus_match
        else {"status": "not_applicable", "stale_source_count": 0, "checked_source_count": 0}
    )
    category = classify_request(user_request)

    if not large_context_intent:
        return decision_record(
            selected_strategy=ContextStrategy.DIRECT_CONTEXT,
            status=ContextStrategyStatus.SELECTED,
            execution_path=ContextStrategyExecutionPath.EXISTING_READ_ONLY_WORKFLOW,
            reason="bounded_non_large_context_request",
            rationale=[
                "No large-corpus route rule or large-context term was detected.",
                "Existing small-repo workflow behavior should remain unchanged.",
            ],
            matched_terms=[],
            policy_summary=policy_summary,
            budget=budget,
            indexed_corpus_match=indexed_corpus_match,
            source_freshness=source_freshness,
            prompt_class="small_or_bounded_request",
        )

    if matched_mutation_terms:
        return decision_record(
            selected_strategy=ContextStrategy.REFUSAL,
            status=ContextStrategyStatus.BLOCKED,
            execution_path=ContextStrategyExecutionPath.NONE,
            reason="large_context_mutation_risk",
            rationale=[
                "Large-context strategy routing is read-only in this phase.",
                "Mutation requires an approved implementation path and must not run through retrieval-backed chat.",
            ],
            matched_terms=large_terms + matched_mutation_terms,
            policy_summary=policy_summary,
            budget=budget,
            indexed_corpus_match=indexed_corpus_match,
            source_freshness=source_freshness,
            prompt_class="large_context_mutation_risk",
            blockers=[
                {
                    "reason": "large_context_mutation_risk",
                    "message": "Large-context mutation is not supported by the read-only context strategy router.",
                }
            ],
        )

    if not indexed_corpus_match:
        return decision_record(
            selected_strategy=ContextStrategy.REFUSAL,
            status=ContextStrategyStatus.BLOCKED,
            execution_path=ContextStrategyExecutionPath.NONE,
            reason="target_not_indexed_corpus",
            rationale=[
                "The request has large-context intent.",
                "The target root does not match the Phase 217 indexed corpus or supplied context index policy.",
            ],
            matched_terms=large_terms,
            policy_summary=policy_summary,
            budget=budget,
            indexed_corpus_match=indexed_corpus_match,
            source_freshness=source_freshness,
            prompt_class="unindexed_large_context_target",
            blockers=[
                {
                    "reason": "target_not_indexed_corpus",
                    "message": "Large-context routing requires an approved fresh context index for the target root.",
                }
            ],
        )

    if source_freshness.get("status") != "fresh" and category != RetrievalAnswerCategory.LIMITATIONS:
        return decision_record(
            selected_strategy=ContextStrategy.REFUSAL,
            status=ContextStrategyStatus.BLOCKED,
            execution_path=ContextStrategyExecutionPath.NONE,
            reason="stale_index_or_source_hash",
            rationale=[
                "The target root matches the context index, but at least one source freshness check failed.",
                "Large-context retrieval must not answer from stale chunks.",
            ],
            matched_terms=large_terms,
            policy_summary=policy_summary,
            budget=budget,
            indexed_corpus_match=indexed_corpus_match,
            source_freshness=source_freshness,
            prompt_class="stale_index_or_source_hash",
            blockers=[
                {
                    "reason": "stale_index_or_source_hash",
                    "message": "Refresh the large-context index before answering from this target root.",
                }
            ],
        )

    if is_raw_prompt_capacity_request(compact, category, matched_raw_terms):
        return decision_record(
            selected_strategy=ContextStrategy.REFUSAL,
            status=ContextStrategyStatus.SELECTED,
            execution_path=ContextStrategyExecutionPath.LARGE_CONTEXT_RETRIEVAL_ANSWER,
            reason="raw_1m_prompt_support_unproven",
            rationale=[
                "Raw 1M-token prompt support is not proven.",
                "The safe answer should explain the budget limit and point to retrieval, chunking, summarization, or paging.",
            ],
            matched_terms=large_terms + matched_raw_terms,
            policy_summary=policy_summary,
            budget=budget,
            indexed_corpus_match=indexed_corpus_match,
            source_freshness=source_freshness,
            prompt_class="raw_context_limit_request",
        )

    if contains_unsafe_evidence_request(user_request):
        return decision_record(
            selected_strategy=ContextStrategy.REFUSAL,
            status=ContextStrategyStatus.SELECTED,
            execution_path=ContextStrategyExecutionPath.LARGE_CONTEXT_RETRIEVAL_ANSWER,
            reason="unsafe_evidence_request",
            rationale=[
                "The request asks for ignored, private, credential, token, or secret-like evidence.",
                "The retrieval-backed answer path can fail closed without source refs or sensitive value leakage.",
            ],
            matched_terms=large_terms,
            policy_summary=policy_summary,
            budget=budget,
            indexed_corpus_match=indexed_corpus_match,
            source_freshness=source_freshness,
            prompt_class="unsafe_large_context_request",
        )

    artifact_terms = contains_any(compact, ARTIFACT_PAGING_TERMS)
    if artifact_terms:
        return decision_record(
            selected_strategy=ContextStrategy.ARTIFACT_PAGING,
            status=ContextStrategyStatus.SELECTED,
            execution_path=ContextStrategyExecutionPath.LARGE_CONTEXT_RETRIEVAL_ANSWER,
            reason="long_evidence_requires_paged_artifacts",
            rationale=[
                "The prompt asks for many source refs or a long evidence report.",
                "Chat should stay answer-first while detailed evidence is paged to artifacts.",
            ],
            matched_terms=large_terms + artifact_terms,
            policy_summary=policy_summary,
            budget=budget,
            indexed_corpus_match=indexed_corpus_match,
            source_freshness=source_freshness,
            prompt_class="long_evidence_report",
        )

    chunked_terms = contains_any(compact, CHUNKED_INVESTIGATION_TERMS)
    if chunked_terms:
        return decision_record(
            selected_strategy=ContextStrategy.CHUNKED_INVESTIGATION,
            status=ContextStrategyStatus.SELECTED,
            execution_path=ContextStrategyExecutionPath.LARGE_CONTEXT_CHUNKED_INVESTIGATION,
            reason="chunked_investigation_executor_available",
            rationale=[
                "The prompt asks for multi-step traversal over a corpus.",
                "The Phase 223 executor can decompose the request into bounded retrieval stages.",
            ],
            matched_terms=large_terms + chunked_terms,
            policy_summary=policy_summary,
            budget=budget,
            indexed_corpus_match=indexed_corpus_match,
            source_freshness=source_freshness,
            prompt_class="large_cross_file_flow",
        )

    if category == RetrievalAnswerCategory.SUMMARIZATION:
        return decision_record(
            selected_strategy=ContextStrategy.SUMMARIZATION,
            status=ContextStrategyStatus.SELECTED,
            execution_path=ContextStrategyExecutionPath.LARGE_CONTEXT_RETRIEVAL_ANSWER,
            reason="large_architecture_summary",
            rationale=[
                "The prompt asks for architecture or corpus overview.",
                "Representative retrieval evidence is acceptable only with explicit limitations.",
            ],
            matched_terms=large_terms,
            policy_summary=policy_summary,
            budget=budget,
            indexed_corpus_match=indexed_corpus_match,
            source_freshness=source_freshness,
            prompt_class="large_architecture_summary",
        )

    if category == RetrievalAnswerCategory.UNKNOWN:
        return decision_record(
            selected_strategy=ContextStrategy.REFUSAL,
            status=ContextStrategyStatus.BLOCKED,
            execution_path=ContextStrategyExecutionPath.NONE,
            reason="ambiguous_large_context_request",
            rationale=[
                "The prompt has large-context intent but does not name a bounded lookup, summary, report, or limitation question.",
                "The controller needs a subsystem, symbol, file family, or output shape before reading the corpus.",
            ],
            matched_terms=large_terms,
            policy_summary=policy_summary,
            budget=budget,
            indexed_corpus_match=indexed_corpus_match,
            source_freshness=source_freshness,
            prompt_class="ambiguous_large_context_request",
            blockers=[
                {
                    "reason": "ambiguous_large_context_request",
                    "message": "Specify the subsystem, symbol, file family, or output shape needed for bounded large-context retrieval.",
                }
            ],
        )

    return decision_record(
        selected_strategy=ContextStrategy.RETRIEVAL,
        status=ContextStrategyStatus.SELECTED,
        execution_path=ContextStrategyExecutionPath.LARGE_CONTEXT_RETRIEVAL_ANSWER,
        reason="large_specific_evidence_lookup",
        rationale=[
            "The prompt asks for specific source evidence from a corpus that exceeds the direct context budget.",
            "The approved retrieval-backed answer path can retrieve bounded evidence with source refs and hash proof.",
        ],
        matched_terms=large_terms,
        policy_summary=policy_summary,
        budget=budget,
        indexed_corpus_match=indexed_corpus_match,
        source_freshness=source_freshness,
        prompt_class="large_specific_evidence_lookup",
    )


def context_strategy_blockers(decision: dict[str, Any]) -> list[dict[str, str]]:
    if decision.get("status") != ContextStrategyStatus.BLOCKED.value:
        return []
    blockers = decision.get("blockers")
    if isinstance(blockers, list):
        return [item for item in blockers if isinstance(item, dict)]
    return [
        {
            "reason": str(decision.get("reason") or "context_strategy_blocked"),
            "message": "The selected context strategy is blocked.",
        }
    ]
