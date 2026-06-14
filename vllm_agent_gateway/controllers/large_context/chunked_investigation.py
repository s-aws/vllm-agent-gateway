"""Read-only chunked investigation executor for large local corpora.

This module orchestrates multi-step large-corpus investigation without adding a
second retrieval implementation. Evidence admission, freshness checks, and
artifact paging stay delegated to the retrieval-backed large-context helpers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.context_index_prototype import dict_value, object_list, resolve_path, string_list
from vllm_agent_gateway.controllers.large_context.retrieval_answer import (
    DEFAULT_ARTIFACT_PAGE_SIZE,
    DEFAULT_CONTEXT_INDEX_POLICY_PATH,
    DEFAULT_MAX_ARTIFACT_EVIDENCE_REFS,
    DEFAULT_MAX_EVIDENCE_REFS,
    DEFAULT_MODEL_CONTEXT_LIMIT,
    DEFAULT_TARGET_INPUT_LIMIT,
    RetrievalAnswerCategory,
    artifact_timestamp,
    classify_request,
    contains_unsafe_evidence_request,
    context_index_target_root,
    load_phase214_budget_summary,
    normalized_path_identity,
    page_evidence_refs,
    policy_index_path,
    query_terms_for_category,
    read_json_object,
    select_valid_evidence,
    write_json,
    utc_now,
)
from vllm_agent_gateway.controllers.large_context.strategy_types import ContextStrategy
from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus


WORKFLOW_ID = "large_context.chunked_investigation"
SCHEMA_VERSION = 1
CONTRACT_VERSION = "phase222.1"
DEFAULT_OUTPUT_DIR = "large-context-chunked-investigation"
STAGE_NARRATIVE_LABELS = {
    "flow_entry_points": "Entry point",
    "decision_to_summary_flow": "Decision/output path",
    "verification_surfaces": "Verification surface",
}
STAGE_ROLES = {
    "flow_entry_points": "risk gate / entry point",
    "decision_to_summary_flow": "decision or output stage",
    "verification_surfaces": "verification / audit summary stage",
}
NOT_PROVEN_BY_SELECTED_EVIDENCE = [
    "The selected refs do not prove every intermediate call edge.",
    "The selected refs do not prove this is the only path through the corpus.",
    "The selected refs do not prove runtime behavior beyond the static evidence metadata.",
]


@dataclass(frozen=True)
class ChunkedInvestigationRequest:
    config_root: Path | str
    target_root: Path | str
    output_root: Path | str
    user_request: str
    run_id: str | None = None
    context_index_policy_path: Path | str = DEFAULT_CONTEXT_INDEX_POLICY_PATH
    max_evidence_refs: int = DEFAULT_MAX_EVIDENCE_REFS
    max_artifact_evidence_refs: int = DEFAULT_MAX_ARTIFACT_EVIDENCE_REFS
    artifact_page_size: int = DEFAULT_ARTIFACT_PAGE_SIZE
    target_input_limit: int = DEFAULT_TARGET_INPUT_LIMIT
    model_context_limit: int = DEFAULT_MODEL_CONTEXT_LIMIT


def unique_terms(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for group in groups:
        for raw in group:
            term = str(raw).lower().strip()
            if term and term not in seen:
                seen.add(term)
                merged.append(term)
    return merged[:24]


def source_type_for_path(source_path: str) -> str:
    normalized = source_path.replace("\\", "/").lower()
    if normalized.startswith("tests/") or "/tests/" in normalized:
        return "test"
    if normalized.startswith("docs/") or normalized.endswith(".md"):
        return "doc"
    if normalized.startswith("config/") or "/config/" in normalized:
        return "config"
    if normalized.startswith("cases/") or normalized.endswith(".json"):
        return "case"
    return "source"


def evidence_key(ref: dict[str, Any]) -> tuple[str, str, int, int]:
    return (
        str(ref.get("source_path") or ""),
        str(ref.get("chunk_id") or ""),
        int(ref.get("line_start") or 0),
        int(ref.get("line_end") or 0),
    )


def build_stage_plan(user_request: str) -> list[dict[str, Any]]:
    category = classify_request(user_request)
    if category in {RetrievalAnswerCategory.UNKNOWN, RetrievalAnswerCategory.LIMITATIONS}:
        category = RetrievalAnswerCategory.NAVIGATION
    base_terms = query_terms_for_category(user_request, category)
    return [
        {
            "stage_id": "flow_entry_points",
            "stage_query": "Identify the likely entry-point source files and modules for the requested large-corpus flow.",
            "query_terms": unique_terms(base_terms, ["entry", "start", "order", "replay", "pipeline", "module", "source"]),
            "retrieval_category": RetrievalAnswerCategory.NAVIGATION.value,
            "preferred_source_types": ["source"],
            "dependencies": [],
            "stop_condition": "Stop if no fresh source evidence can be admitted for the entry-point stage.",
        },
        {
            "stage_id": "decision_to_summary_flow",
            "stage_query": "Find bounded evidence for how the main decision or processing stage connects to the final summary/output stage.",
            "query_terms": unique_terms(base_terms, ["risk", "gate", "audit", "summary", "flow", "decision", "output"]),
            "retrieval_category": RetrievalAnswerCategory.NAVIGATION.value,
            "preferred_source_types": ["source"],
            "dependencies": ["flow_entry_points"],
            "stop_condition": "Stop if no fresh source evidence can be admitted for the middle/output stage.",
        },
        {
            "stage_id": "verification_surfaces",
            "stage_query": "Find tests, cases, docs, or configuration that validate or describe the requested flow.",
            "query_terms": unique_terms(base_terms, ["test", "case", "scenario", "docs", "architecture", "validation", "config"]),
            "retrieval_category": RetrievalAnswerCategory.SUMMARIZATION.value,
            "preferred_source_types": ["test", "doc", "case", "config"],
            "dependencies": ["flow_entry_points", "decision_to_summary_flow"],
            "stop_condition": "Continue with limitations if no verification surface evidence is available.",
        },
    ]


def enrich_evidence_refs(
    refs: list[dict[str, Any]],
    *,
    stage_id: str,
    claim_id: str,
    query_terms: list[str],
    start_rank: int,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for offset, ref in enumerate(refs, start=start_rank):
        source_path = str(ref.get("source_path") or "")
        enriched_ref = {
            "evidence_ref_id": f"{stage_id}-evidence-{offset:03d}",
            "retrieval_stage_id": stage_id,
            "claim_ids": [claim_id],
            "source_path": source_path,
            "line_start": ref.get("line_start"),
            "line_end": ref.get("line_end"),
            "chunk_id": ref.get("chunk_id"),
            "source_sha256": ref.get("source_sha256"),
            "chunk_sha256": ref.get("chunk_sha256"),
            "freshness_status": ref.get("freshness_status"),
            "source_type": source_type_for_path(source_path),
            "retrieval_rank": offset,
            "retrieval_score": ref.get("score"),
            "query_terms": query_terms,
            "chunk_token_estimate": ref.get("chunk_token_estimate"),
            "matched_terms": string_list(ref.get("matched_terms")),
            "source_text_retained": False,
        }
        enriched.append(enriched_ref)
    return enriched


def choose_stage_refs(
    raw_refs: list[dict[str, Any]],
    *,
    stage: dict[str, Any],
    seen_global_evidence: set[tuple[str, str, int, int]],
    limit: int,
) -> list[dict[str, Any]]:
    preferred_types = set(string_list(stage.get("preferred_source_types")))
    selected: list[dict[str, Any]] = []
    seen_stage_evidence: set[tuple[str, str, int, int]] = set()

    def add_from(pool: list[dict[str, Any]], *, require_unseen: bool, require_preferred: bool) -> None:
        for ref in pool:
            if len(selected) >= limit:
                return
            key = evidence_key(ref)
            if key in seen_stage_evidence:
                continue
            source_type = source_type_for_path(str(ref.get("source_path") or ""))
            if require_unseen and key in seen_global_evidence:
                continue
            if require_preferred and preferred_types and source_type not in preferred_types:
                continue
            seen_stage_evidence.add(key)
            selected.append(ref)

    add_from(raw_refs, require_unseen=True, require_preferred=True)
    add_from(raw_refs, require_unseen=True, require_preferred=False)
    add_from(raw_refs, require_unseen=False, require_preferred=True)
    add_from(raw_refs, require_unseen=False, require_preferred=False)
    for ref in selected:
        seen_global_evidence.add(evidence_key(ref))
    return selected


def stage_finding(stage_id: str, refs: list[dict[str, Any]]) -> tuple[str, str, list[str]]:
    if not refs:
        return (
            f"{stage_id}: no fresh admissible evidence was found.",
            "low",
            ["No source claim was made for this stage because evidence was unavailable or rejected."],
        )
    source_summary = ", ".join(
        f"{ref.get('source_path')}:{ref.get('line_start')}-{ref.get('line_end')}" for ref in refs[:3]
    )
    return (
        f"{stage_id}: found fresh metadata-backed evidence in {source_summary}.",
        "medium",
        [
            "This is bounded retrieval evidence, not exhaustive whole-corpus proof.",
            "The full corpus was not inserted into the prompt.",
        ],
    )


def answer_ref(ref: dict[str, Any]) -> str:
    return f"`{ref.get('source_path')}` lines {ref.get('line_start')}-{ref.get('line_end')}"


def short_hash(value: object) -> str:
    raw = str(value or "")
    return raw[:12] if raw else "unknown"


def evidence_citation(ref: dict[str, Any]) -> str:
    return (
        f"[stage: {ref.get('retrieval_stage_id')} | path: {ref.get('source_path')} | "
        f"lines: {ref.get('line_start')}-{ref.get('line_end')} | "
        f"source_hash: {short_hash(ref.get('source_sha256'))} | "
        f"chunk_hash: {short_hash(ref.get('chunk_sha256'))} | freshness: {ref.get('freshness_status')}]"
    )


def build_evidence_table(evidence_refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ref in evidence_refs:
        stage_id = str(ref.get("retrieval_stage_id") or "")
        rows.append(
            {
                "stage_id": stage_id,
                "stage_role": STAGE_ROLES.get(stage_id, stage_id.replace("_", " ")),
                "source_path": ref.get("source_path"),
                "line_span": f"{ref.get('line_start')}-{ref.get('line_end')}",
                "source_sha256": ref.get("source_sha256"),
                "chunk_sha256": ref.get("chunk_sha256"),
                "freshness_status": ref.get("freshness_status"),
                "confidence": "medium",
                "caveat": "Metadata-backed evidence only; source text is not retained in this artifact.",
            }
        )
    return rows


def render_evidence_table(evidence_refs: list[dict[str, Any]]) -> str:
    if not evidence_refs:
        return "Evidence table: no fresh evidence refs were selected. "
    rows = []
    for ref in evidence_refs:
        stage_id = str(ref.get("retrieval_stage_id") or "")
        role = STAGE_ROLES.get(stage_id, stage_id.replace("_", " "))
        rows.append(f"{role}: {evidence_citation(ref)}")
    return f"Evidence table: {' '.join(rows)} "


def refs_for_step(step: dict[str, Any], refs_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [refs_by_id[ref_id] for ref_id in string_list(step.get("evidence_ref_ids")) if ref_id in refs_by_id]


def build_flow_narrative(steps: list[dict[str, Any]], evidence_refs: list[dict[str, Any]]) -> list[str]:
    refs_by_id = {str(ref.get("evidence_ref_id")): ref for ref in evidence_refs if ref.get("evidence_ref_id")}
    narrative: list[str] = []
    for step in steps:
        stage_id = str(step.get("stage_id") or "")
        label = STAGE_NARRATIVE_LABELS.get(stage_id, stage_id.replace("_", " ").title())
        stage_refs = refs_for_step(step, refs_by_id)
        if stage_refs:
            refs = "; ".join(evidence_citation(ref) for ref in stage_refs[:2])
            narrative.append(
                f"{label}: the selected evidence path indicates this stage through {refs}."
            )
        else:
            narrative.append(
                f"{label}: no fresh admissible evidence was selected, so this stage remains unresolved."
            )
    if narrative:
        narrative.append(
            "Scope note: this is a bounded cross-file trace from selected fresh evidence, not exhaustive whole-corpus proof."
        )
    return narrative


def build_final_answer(
    *,
    steps: list[dict[str, Any]],
    evidence_refs: list[dict[str, Any]],
    flow_narrative: list[str],
    selected_token_estimate: int,
    budget: dict[str, Any],
    target_input_limit: int,
    artifact_pages: dict[str, Any],
) -> str:
    completed = [step for step in steps if step.get("stage_status") == "answered"]
    unresolved = [step for step in steps if step.get("stage_status") != "answered"]
    top_refs = ", ".join(
        f"`{ref.get('source_path')}` lines {ref.get('line_start')}-{ref.get('line_end')}" for ref in evidence_refs[:4]
    )
    page_count = artifact_pages.get("page_count")
    source_ref_count = artifact_pages.get("artifact_source_ref_count")
    answer = (
        "Chunked investigation result: Scope and limits: this is a bounded retrieval trace, not an exhaustive "
        "whole-corpus analysis. Citations identify selected chunks by path, lines, hashes, freshness, and stage. "
        f"I decomposed the large-corpus request into `{len(steps)}` bounded stages and completed `{len(completed)}` "
        "of them with fresh source-hash evidence. "
    )
    if top_refs:
        answer += f"Key refs: {top_refs}. "
    answer += render_evidence_table(evidence_refs)
    if flow_narrative:
        answer += f"Flow narrative: {' '.join(flow_narrative)} "
    answer += f"Not proven by selected evidence: {' '.join(NOT_PROVEN_BY_SELECTED_EVIDENCE)} "
    if unresolved:
        answer += f"Unresolved stages: `{', '.join(str(step.get('stage_id')) for step in unresolved)}`. "
    answer += (
        f"Prompt budget proof: selected evidence estimates `{selected_token_estimate}` tokens against target input limit "
        f"`{target_input_limit}`, so this did not raw-stuff the `{budget.get('estimated_corpus_tokens')}`-token corpus. "
        f"Paged evidence: `{page_count}` page(s), `{source_ref_count}` total source refs. Confidence: medium."
    )
    return answer


def validation_error(error_id: str, severity: str, message: str) -> dict[str, str]:
    return {"id": error_id, "severity": severity, "message": message}


def build_report(request: ChunkedInvestigationRequest, run_dir: Path) -> dict[str, Any]:
    config_root = Path(request.config_root).resolve()
    target_root = Path(request.target_root).resolve()
    policy_path = resolve_path(config_root, request.context_index_policy_path)
    context_policy = read_json_object(policy_path)
    index_path = policy_index_path(config_root, context_policy)
    index = read_json_object(index_path)
    phase216_policy_path = resolve_path(config_root, str(context_policy.get("phase216_policy_path")))
    phase216_policy = read_json_object(phase216_policy_path)
    indexed_root = context_index_target_root(config_root, context_policy, index)
    budget = load_phase214_budget_summary(config_root)
    stage_plan = build_stage_plan(request.user_request)
    validation_errors: list[dict[str, str]] = []
    safety_decisions: list[dict[str, Any]] = []

    if normalized_path_identity(target_root) != normalized_path_identity(indexed_root):
        validation_errors.append(
            validation_error("target_root.not_indexed_corpus", "high", "target_root does not match the context index")
        )
    if dict_value(index).get("source_text_retention") != "metadata_only" or index.get("store_source_text") is not False:
        validation_errors.append(
            validation_error("index.source_text_retention", "critical", "context index must remain metadata-only")
        )
    if contains_unsafe_evidence_request(request.user_request):
        validation_errors.append(
            validation_error("request.unsafe_evidence_request", "high", "request asks for private or secret-like evidence")
        )

    steps: list[dict[str, Any]] = []
    retrievals: list[dict[str, Any]] = []
    evidence_refs: list[dict[str, Any]] = []
    seen_global_evidence: set[tuple[str, str, int, int]] = set()
    selected_token_estimate = 0
    refs_per_stage = max(1, request.max_evidence_refs // len(stage_plan))

    if not validation_errors:
        for stage in stage_plan:
            stage_id = str(stage["stage_id"])
            claim_id = f"claim-{len(steps) + 1:03d}"
            raw_refs, stage_safety = select_valid_evidence(
                target_root=target_root,
                index=index,
                phase216_policy=phase216_policy,
                query_terms=string_list(stage.get("query_terms")),
                category=RetrievalAnswerCategory(str(stage.get("retrieval_category") or RetrievalAnswerCategory.NAVIGATION.value)),
                max_evidence_refs=(
                    256
                    if set(string_list(stage.get("preferred_source_types"))) - {"source"}
                    else max(request.max_artifact_evidence_refs, request.max_evidence_refs * 12)
                ),
            )
            safety_decisions.extend(
                {
                    **decision,
                    "retrieval_stage_id": stage_id,
                }
                for decision in stage_safety
            )
            unique_stage_refs = choose_stage_refs(
                raw_refs,
                stage=stage,
                seen_global_evidence=seen_global_evidence,
                limit=refs_per_stage,
            )
            enriched_refs = enrich_evidence_refs(
                unique_stage_refs,
                stage_id=stage_id,
                claim_id=claim_id,
                query_terms=string_list(stage.get("query_terms")),
                start_rank=len(evidence_refs) + 1,
            )
            evidence_refs.extend(enriched_refs)
            selected_token_estimate += sum(int(ref.get("chunk_token_estimate") or 0) for ref in enriched_refs)
            finding, confidence, limitations = stage_finding(stage_id, enriched_refs)
            stage_status = "answered" if enriched_refs else "unresolved"
            steps.append(
                {
                    "stage_id": stage_id,
                    "stage_query": stage.get("stage_query"),
                    "stage_status": stage_status,
                    "selected_token_estimate": sum(int(ref.get("chunk_token_estimate") or 0) for ref in enriched_refs),
                    "evidence_ref_ids": [str(ref.get("evidence_ref_id")) for ref in enriched_refs],
                    "missing_evidence": [] if enriched_refs else [stage.get("stop_condition")],
                    "confidence": confidence,
                    "finding": finding,
                    "claim_id": claim_id,
                    "limitations": limitations,
                    "dependencies": stage.get("dependencies"),
                }
            )
            retrievals.append(
                {
                    "retrieval_stage_id": stage_id,
                    "query_terms": stage.get("query_terms"),
                    "admitted_evidence_ref_count": len(enriched_refs),
                    "rejected_decision_count": len([item for item in stage_safety if item.get("decision") == "reject"]),
                }
            )

    if selected_token_estimate >= request.target_input_limit:
        validation_errors.append(
            validation_error("prompt_budget.exceeded", "critical", "selected evidence exceeded target input limit")
        )
    if not evidence_refs and not validation_errors:
        validation_errors.append(
            validation_error("evidence.none_admitted", "high", "no fresh evidence was admitted for chunked investigation")
        )

    artifact_pages = page_evidence_refs(
        evidence_refs,
        page_size=request.artifact_page_size,
        chat_evidence_count=min(request.max_evidence_refs, len(evidence_refs)),
    )
    status = "blocked" if validation_errors else "answered"
    completed_steps = [step for step in steps if step.get("stage_status") == "answered"]
    unresolved_steps = [step for step in steps if step.get("stage_status") != "answered"]
    claim_map = [
        {
            "claim_id": step.get("claim_id"),
            "claim": step.get("finding"),
            "retrieval_stage_id": step.get("stage_id"),
            "evidence_ref_ids": step.get("evidence_ref_ids"),
            "confidence": step.get("confidence"),
        }
        for step in steps
    ]
    limitations = [
        "Chunked investigation uses bounded metadata-backed retrieval, not exhaustive whole-corpus proof.",
        "The full corpus was not inserted into the prompt.",
        "Artifacts retain source metadata and hashes, not source text bodies.",
    ]
    flow_narrative = [] if validation_errors else build_flow_narrative(steps, evidence_refs)
    if validation_errors:
        answer = (
            "I cannot complete the chunked investigation from the current large-context evidence. "
            "See validation errors and unresolved stages for the blocked proof."
        )
    else:
        answer = build_final_answer(
            steps=steps,
            evidence_refs=evidence_refs,
            flow_narrative=flow_narrative,
            selected_token_estimate=selected_token_estimate,
            budget=budget,
            target_input_limit=request.target_input_limit,
            artifact_pages=artifact_pages,
        )
    final_answer = {
        "answer": answer,
        "answer_first": True,
        "flow_narrative": flow_narrative,
        "evidence_table": build_evidence_table(evidence_refs),
        "not_proven_by_selected_evidence": NOT_PROVEN_BY_SELECTED_EVIDENCE,
        "completed_stage_summary": [
            {
                "stage_id": step.get("stage_id"),
                "finding": step.get("finding"),
                "evidence_ref_ids": step.get("evidence_ref_ids"),
                "confidence": step.get("confidence"),
            }
            for step in completed_steps
        ],
        "unresolved_steps": [
            {
                "stage_id": step.get("stage_id"),
                "missing_evidence": step.get("missing_evidence"),
                "limitations": step.get("limitations"),
            }
            for step in unresolved_steps
        ],
        "claim_map": claim_map,
        "confidence": "medium" if completed_steps and not validation_errors else "low",
        "limitations": limitations,
        "artifact_refs": {
            "page_manifest": "chunk-page-manifest.json",
            "report": "chunked-investigation-report.json",
        },
        "raw_prompt_stuffing": False,
    }
    plan = {
        "schema_version": SCHEMA_VERSION,
        "kind": "chunked_investigation_plan",
        "run_id": request.run_id or run_dir.name,
        "target_root": str(target_root),
        "user_request": request.user_request,
        "strategy_id": ContextStrategy.CHUNKED_INVESTIGATION.value,
        "stage_count": len(stage_plan),
        "stage_plan": stage_plan,
        "stage_dependencies": {str(stage["stage_id"]): stage.get("dependencies", []) for stage in stage_plan},
        "budget": {
            "target_input_limit": request.target_input_limit,
            "model_context_limit": request.model_context_limit,
            "selected_evidence_token_estimate": selected_token_estimate,
        },
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "chunked_investigation_report",
        "workflow": WORKFLOW_ID,
        "run_id": request.run_id or run_dir.name,
        "request_id": request.run_id or run_dir.name,
        "strategy": ContextStrategy.CHUNKED_INVESTIGATION.value,
        "executor_contract_version": CONTRACT_VERSION,
        "target_root": str(target_root),
        "indexed_root": str(indexed_root),
        "input_summary": {
            "user_request": request.user_request,
            "prompt_class": "large_cross_file_flow",
            "context_index_policy_path": str(policy_path),
        },
        "corpus_snapshot": {
            "index_path": str(index_path),
            "indexed_file_count": index.get("indexed_file_count"),
            "chunk_count": index.get("chunk_count"),
            "estimated_indexed_token_count": index.get("estimated_indexed_token_count"),
            "source_text_retention": "metadata_only",
            "store_source_text": False,
        },
        "plan": plan,
        "steps": steps,
        "retrievals": retrievals,
        "evidence": evidence_refs,
        "claim_map": claim_map,
        "final_answer": final_answer,
        "limits": {
            "raw_prompt_stuffing": False,
            "target_input_limit": request.target_input_limit,
            "model_context_limit": request.model_context_limit,
            "raw_corpus_estimated_tokens": budget.get("estimated_corpus_tokens"),
            "selected_evidence_token_estimate": selected_token_estimate,
            "within_target_input_limit": selected_token_estimate < request.target_input_limit,
            "source_text_retention": "metadata_only",
        },
        "safety": {
            "source_text_retention": "metadata_only",
            "store_source_text": False,
            "store_rejected_content": False,
            "safety_decisions": safety_decisions,
        },
        "validation": {
            "validation_errors": validation_errors,
            "phase222_contract_satisfied": not validation_errors,
            "artifact_only_answer": False,
            "claim_map_required": True,
        },
        "artifact_pages": artifact_pages,
        "status": status,
        "created_at": utc_now(),
        "summary": {
            "answer": answer,
            "route_status": "ready" if status == "answered" else "blocked",
            "selected_workflow": WORKFLOW_ID,
            "chunked_status": status,
            "chunked_stage_count": len(steps),
            "chunked_completed_stage_count": len(completed_steps),
            "chunked_evidence_count": len(evidence_refs),
            "chunked_claim_count": len(claim_map),
            "chunked_artifact_page_count": artifact_pages.get("page_count"),
            "chunked_artifact_source_ref_count": artifact_pages.get("artifact_source_ref_count"),
            "chunked_first_page_id": object_list(artifact_pages.get("pages"))[0].get("page_id")
            if object_list(artifact_pages.get("pages"))
            else None,
            "raw_prompt_stuffing": False,
            "source_text_retention": "metadata_only",
            "phase222_contract_satisfied": not validation_errors,
        },
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    final_answer = dict_value(report.get("final_answer"))
    lines = [
        "# Chunked Investigation",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Strategy: `{report.get('strategy')}`",
        f"- Stages: `{dict_value(report.get('summary')).get('chunked_stage_count')}`",
        f"- Evidence refs: `{dict_value(report.get('summary')).get('chunked_evidence_count')}`",
        f"- Raw prompt stuffing: `{dict_value(report.get('limits')).get('raw_prompt_stuffing')}`",
        "",
        "## Answer",
        "",
        str(final_answer.get("answer") or ""),
        "",
        "## Stages",
    ]
    for step in object_list(report.get("steps")):
        lines.append(f"- `{step.get('stage_id')}`: `{step.get('stage_status')}` - {step.get('finding')}")
    lines.extend(["", "## Evidence Refs"])
    for ref in object_list(report.get("evidence")):
        lines.append(
            f"- `{ref.get('evidence_ref_id')}` `{ref.get('source_path')}` lines "
            f"`{ref.get('line_start')}-{ref.get('line_end')}` source `{str(ref.get('source_sha256'))[:12]}` "
            f"chunk `{str(ref.get('chunk_sha256'))[:12]}`"
        )
    errors = object_list(dict_value(report.get("validation")).get("validation_errors"))
    if errors:
        lines.extend(["", "## Validation Errors"])
        for item in errors:
            lines.append(f"- `{item.get('id')}`: {item.get('message')}")
    return "\n".join(lines) + "\n"


def invoke_chunked_investigation(request: ChunkedInvestigationRequest) -> InvocationResult:
    run_id = request.run_id or f"large-context-chunked-investigation-{artifact_timestamp()}"
    run_dir = Path(request.output_root).resolve() / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    effective_request = ChunkedInvestigationRequest(
        config_root=request.config_root,
        target_root=request.target_root,
        output_root=request.output_root,
        user_request=request.user_request,
        run_id=run_id,
        context_index_policy_path=request.context_index_policy_path,
        max_evidence_refs=request.max_evidence_refs,
        max_artifact_evidence_refs=request.max_artifact_evidence_refs,
        artifact_page_size=request.artifact_page_size,
        target_input_limit=request.target_input_limit,
        model_context_limit=request.model_context_limit,
    )
    report = build_report(effective_request, run_dir)
    report_path = run_dir / "chunked-investigation-report.json"
    markdown_path = run_dir / "chunked-investigation-report.md"
    page_manifest_path = run_dir / "chunk-page-manifest.json"
    plan_path = run_dir / "chunked-investigation-plan.json"
    stage_records_path = run_dir / "chunk-stage-records.json"
    evidence_refs_path = run_dir / "chunk-evidence-refs.json"
    final_answer_path = run_dir / "chunk-final-answer.json"
    write_json(report_path, report)
    markdown_path.write_text(render_markdown_report(report), encoding="utf-8")
    write_json(page_manifest_path, dict_value(report.get("artifact_pages")))
    write_json(plan_path, dict_value(report.get("plan")))
    write_json(stage_records_path, {"schema_version": SCHEMA_VERSION, "kind": "chunk_stage_records", "steps": report.get("steps", [])})
    write_json(evidence_refs_path, {"schema_version": SCHEMA_VERSION, "kind": "chunk_evidence_refs", "evidence": report.get("evidence", [])})
    write_json(final_answer_path, dict_value(report.get("final_answer")))
    run_state = {
        "schema_version": SCHEMA_VERSION,
        "kind": "large_context_chunked_investigation_run_state",
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "summary": report["summary"],
        "artifacts": {
            "chunked_investigation_report": str(report_path),
            "chunked_investigation_markdown": str(markdown_path),
            "chunked_investigation_plan": str(plan_path),
            "chunk_stage_records": str(stage_records_path),
            "chunk_evidence_refs": str(evidence_refs_path),
            "chunk_page_manifest": str(page_manifest_path),
            "chunk_final_answer": str(final_answer_path),
        },
        "updated_at": utc_now(),
    }
    run_state_path = run_dir / "run-state.json"
    write_json(run_state_path, run_state)
    artifacts = {
        **run_state["artifacts"],
        "run_state": str(run_state_path),
    }
    return InvocationResult(
        workflow=WORKFLOW_ID,
        status=WorkflowStatus.COMPLETED,
        artifact_paths=artifacts,
        summary_text=f"{WORKFLOW_ID} completed: {report['status']}",
        failures=[],
        resume_key={"schema_version": SCHEMA_VERSION, "run_state": str(run_state_path)},
        report=report,
        run_id=run_id,
    )
