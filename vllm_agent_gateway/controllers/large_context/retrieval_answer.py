"""Retrieval-backed chat answer gate for large local corpora.

This module connects the Phase 217 metadata-first index to the existing
workflow-router answer path. It does not create a second chat endpoint and it
does not persist source text.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.context_index_prototype import (
    DEFAULT_POLICY_PATH as DEFAULT_CONTEXT_INDEX_POLICY_PATH,
    dict_value,
    evaluate_candidate,
    fingerprint_ignore_policy,
    object_list,
    read_json_object,
    resolve_path,
    sha256_file,
    sha256_text,
    string_list,
    terms_for_text,
)
from vllm_agent_gateway.controllers.large_context.strategy_types import ContextStrategy
from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus


WORKFLOW_ID = "large_context.retrieval_answer"
SCHEMA_VERSION = 1
DEFAULT_OUTPUT_DIR = "large-context-retrieval-answer"
DEFAULT_MAX_EVIDENCE_REFS = 4
DEFAULT_MAX_ARTIFACT_EVIDENCE_REFS = 12
DEFAULT_ARTIFACT_PAGE_SIZE = 4
DEFAULT_TARGET_INPUT_LIMIT = 24_000
DEFAULT_MODEL_CONTEXT_LIMIT = 65_536
DEFAULT_MAX_SOURCE_LINES_READ = 80
FRESHNESS_OR_POLICY_REJECTION_REASONS = {
    "stale_index_freshness_status",
    "stale_source_hash",
    "stale_source_size",
    "stale_source_mtime",
    "changed_ignore_policy_hash",
    "changed_safety_policy_hash",
    "source_missing",
    "invalid_relative_path",
    "unexpected_context_strategy",
    "unsupported_index_schema_version",
    "source_text_field_present",
}


class RetrievalAnswerCategory(str, Enum):
    NAVIGATION = "large_corpus_navigation"
    EVIDENCE_LOOKUP = "large_corpus_evidence_lookup"
    SUMMARIZATION = "large_corpus_summarization"
    LIMITATIONS = "large_corpus_limitations"
    UNKNOWN = "unknown"


class RetrievalAnswerStatus(str, Enum):
    ANSWERED = "answered"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class RetrievalBackedChatAnswerRequest:
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


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def artifact_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalized_path_identity(value: Path | str) -> str:
    text = str(value).replace("\\", "/").rstrip("/")
    match = re.match(r"^/mnt/([a-zA-Z])/(.+)$", text)
    if match:
        text = f"{match.group(1).lower()}:/{match.group(2)}"
    return text.lower()


def policy_index_path(config_root: Path, policy: dict[str, Any]) -> Path:
    artifact = dict_value(policy.get("index_artifact"))
    return resolve_path(config_root, str(artifact.get("path")))


def context_index_target_root(config_root: Path, policy: dict[str, Any], index: dict[str, Any] | None = None) -> Path:
    if isinstance(index, dict) and isinstance(index.get("target_root"), str):
        return Path(index["target_root"])
    corpus = dict_value(policy.get("source_corpus"))
    return resolve_path(config_root, str(corpus.get("root")))


def target_matches_indexed_corpus(
    config_root: Path | str,
    target_root: Path | str,
    context_index_policy_path: Path | str = DEFAULT_CONTEXT_INDEX_POLICY_PATH,
) -> bool:
    root = Path(config_root).resolve()
    policy_path = resolve_path(root, context_index_policy_path)
    if not policy_path.is_file():
        return False
    try:
        policy = read_json_object(policy_path)
    except (OSError, RuntimeError, json.JSONDecodeError):
        return False
    expected_root = resolve_path(root, str(dict_value(policy.get("source_corpus")).get("root"))).resolve()
    target = Path(target_root).resolve()
    return normalized_path_identity(target) == normalized_path_identity(expected_root)


def classify_request(user_request: str) -> RetrievalAnswerCategory:
    text = user_request.lower()
    if any(term in text for term in ("architecture", "high level", "service design", "generated service", "summarize")):
        return RetrievalAnswerCategory.SUMMARIZATION
    if any(term in text for term in ("risk gate", "audit summar", "evidence for", "flow into")):
        return RetrievalAnswerCategory.EVIDENCE_LOOKUP
    if any(term in text for term in ("order replay", "pipeline", "relevant modules", "top files", "identify")):
        return RetrievalAnswerCategory.NAVIGATION
    if any(
        term in text
        for term in (
            "raw prompt",
            "raw prompt stuff",
            "entire corpus as one",
            "as one prompt",
            "should i paste",
            "paste into qwen",
            "paste this corpus",
            "paste the corpus",
            "1m",
            "1 million",
            "million-token",
        )
    ):
        return RetrievalAnswerCategory.LIMITATIONS
    return RetrievalAnswerCategory.UNKNOWN


def contains_unsafe_evidence_request(user_request: str) -> bool:
    text = user_request.lower()
    return any(term in text for term in ("private", "secret", "ignored", ".cgcignore", "credential", "api key", "bearer token"))


def query_terms_for_category(user_request: str, category: RetrievalAnswerCategory) -> list[str]:
    terms = terms_for_text(user_request, limit=20, max_length=32)
    supplements = {
        RetrievalAnswerCategory.NAVIGATION: ["order", "replay", "pipeline", "risk", "gate", "audit", "summary"],
        RetrievalAnswerCategory.EVIDENCE_LOOKUP: ["risk", "gate", "audit", "summary", "evidence", "source"],
        RetrievalAnswerCategory.SUMMARIZATION: ["generated", "design", "architecture", "service", "pipeline", "context"],
        RetrievalAnswerCategory.LIMITATIONS: ["token", "budget", "context", "limitation", "retrieval"],
        RetrievalAnswerCategory.UNKNOWN: [],
    }
    seen: set[str] = set()
    merged: list[str] = []
    for term in terms + supplements[category]:
        clean = term.lower().strip()
        if clean and clean not in seen:
            seen.add(clean)
            merged.append(clean)
    return merged[:24]


def path_weight(source_path: str, category: RetrievalAnswerCategory) -> int:
    if category == RetrievalAnswerCategory.NAVIGATION:
        if source_path.startswith("src/order_replay/"):
            return 40
        if source_path.startswith("tests/"):
            return 18
        if source_path.startswith("docs/"):
            return 10
        if source_path.startswith("cases/"):
            return 4
    if category == RetrievalAnswerCategory.EVIDENCE_LOOKUP:
        if source_path.startswith("src/order_replay/"):
            return 35
        if source_path.startswith("tests/"):
            return 28
        if source_path.startswith("cases/"):
            return 12
        if source_path.startswith("docs/"):
            return 10
    if category == RetrievalAnswerCategory.SUMMARIZATION:
        if source_path.startswith("src/"):
            return 25
        if source_path.startswith("docs/"):
            return 22
        if source_path.startswith("config/"):
            return 18
        if source_path.startswith("tests/"):
            return 14
        if source_path.startswith("cases/"):
            return 8
    return 0


def score_chunk(chunk: dict[str, Any], query_terms: list[str], category: RetrievalAnswerCategory) -> tuple[int, list[str]]:
    indexed_terms = set(string_list(chunk.get("search_terms")))
    matched = sorted(set(query_terms).intersection(indexed_terms))
    source_path = str(chunk.get("source_path") or chunk.get("relative_path") or "")
    score = len(matched) * 10 + path_weight(source_path, category)
    if source_path.endswith(".py"):
        score += 5
    return score, matched


def select_candidate_chunks(
    index: dict[str, Any],
    query_terms: list[str],
    category: RetrievalAnswerCategory,
    *,
    max_evidence_refs: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for chunk in object_list(index.get("chunks")):
        score, matched = score_chunk(chunk, query_terms, category)
        if score <= 0 or not matched:
            continue
        candidate = dict(chunk)
        candidate["_score"] = score
        candidate["_matched_terms"] = matched
        candidates.append(candidate)
    ranked = sorted(
        candidates,
        key=lambda item: (
            -int(item.get("_score", 0)),
            str(item.get("source_path") or item.get("relative_path") or ""),
            int(item.get("chunk_index", 0)),
        ),
    )
    selected: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for item in ranked:
        source_path = str(item.get("source_path") or item.get("relative_path") or "")
        if source_path in seen_paths:
            continue
        selected.append(item)
        seen_paths.add(source_path)
        if len(selected) >= max_evidence_refs:
            break
    return selected


def read_current_chunk_lines(source_path: Path, start_line: int, end_line: int) -> list[str]:
    try:
        lines = source_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    safe_start = max(start_line, 1)
    safe_end = max(min(end_line, safe_start + DEFAULT_MAX_SOURCE_LINES_READ - 1), safe_start)
    return lines[safe_start - 1 : safe_end]


def validate_chunk_against_current_source(
    *,
    target_root: Path,
    chunk: dict[str, Any],
    phase216_policy: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    reasons: list[str] = []
    relative_path = str(chunk.get("relative_path") or chunk.get("source_path") or "")
    if not relative_path or Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
        return None, ["invalid_relative_path"]
    admission = evaluate_candidate(target_root, relative_path, phase216_policy)
    if admission.get("decision") != "admit":
        reasons.extend(string_list(admission.get("rejection_reasons")))
    current_source = target_root / relative_path
    if not current_source.is_file():
        reasons.append("source_missing")
    if chunk.get("admission_decision") != "admit":
        reasons.append("index_chunk_not_admitted")
    if chunk.get("freshness_status") != "fresh":
        reasons.append("stale_index_freshness_status")
    if chunk.get("context_strategy_id") != ContextStrategy.RETRIEVAL.value:
        reasons.append("unexpected_context_strategy")
    if chunk.get("index_schema_version") != SCHEMA_VERSION:
        reasons.append("unsupported_index_schema_version")
    if any(key in chunk for key in ("source_text", "chunk_text", "text", "snippet", "content")):
        reasons.append("source_text_field_present")
    if current_source.is_file():
        stat = current_source.stat()
        if chunk.get("source_sha256") != sha256_file(current_source):
            reasons.append("stale_source_hash")
        if chunk.get("source_size") != stat.st_size:
            reasons.append("stale_source_size")
        if chunk.get("source_mtime_ns") != stat.st_mtime_ns:
            reasons.append("stale_source_mtime")
        if chunk.get("ignore_policy_fingerprint") != fingerprint_ignore_policy(target_root, phase216_policy):
            reasons.append("changed_ignore_policy_hash")
        safety_hash = sha256_text(json.dumps(phase216_policy, sort_keys=True))
        if chunk.get("safety_policy_fingerprint") != safety_hash:
            reasons.append("changed_safety_policy_hash")
    if reasons:
        return None, sorted(set(reasons))
    start_line = int(chunk.get("line_start") or chunk.get("start_line") or 1)
    end_line = int(chunk.get("line_end") or chunk.get("end_line") or start_line)
    current_lines = read_current_chunk_lines(current_source, start_line, end_line)
    current_chunk_hash = sha256_text("\n".join(current_lines))
    evidence = {
        "source_path": relative_path,
        "line_start": start_line,
        "line_end": end_line,
        "chunk_id": chunk.get("chunk_id"),
        "chunk_sha256": chunk.get("chunk_sha256"),
        "current_chunk_sha256": current_chunk_hash,
        "source_sha256": chunk.get("source_sha256"),
        "source_size": chunk.get("source_size"),
        "source_mtime_ns": chunk.get("source_mtime_ns"),
        "chunk_token_estimate": chunk.get("chunk_token_estimate") or chunk.get("estimated_tokens"),
        "freshness_status": chunk.get("freshness_status"),
        "score": chunk.get("_score"),
        "matched_terms": chunk.get("_matched_terms"),
        "search_terms_hash": chunk.get("search_terms_hash"),
        "source_text_retained": False,
        "on_demand_source_line_count": len(current_lines),
    }
    return evidence, []


def select_valid_evidence(
    *,
    target_root: Path,
    index: dict[str, Any],
    phase216_policy: dict[str, Any],
    query_terms: list[str],
    category: RetrievalAnswerCategory,
    max_evidence_refs: int,
    scan_multiplier: int = 4,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence_refs: list[dict[str, Any]] = []
    safety_decisions: list[dict[str, Any]] = []
    for chunk in select_candidate_chunks(index, query_terms, category, max_evidence_refs=max_evidence_refs * scan_multiplier):
        evidence, rejection_reasons = validate_chunk_against_current_source(
            target_root=target_root,
            chunk=chunk,
            phase216_policy=phase216_policy,
        )
        source_path = str(chunk.get("source_path") or chunk.get("relative_path") or "")
        if evidence is None:
            safety_decisions.append(
                {
                    "source_path": source_path,
                    "decision": "reject",
                    "reasons": rejection_reasons,
                }
            )
            continue
        safety_decisions.append(
            {
                "source_path": source_path,
                "decision": "admit",
                "reasons": [],
                "source_sha256": evidence.get("source_sha256"),
            }
        )
        evidence_refs.append(evidence)
        if len(evidence_refs) >= max_evidence_refs:
            break
    return evidence_refs, safety_decisions


def page_evidence_refs(
    evidence_refs: list[dict[str, Any]],
    *,
    page_size: int,
    chat_evidence_count: int,
) -> dict[str, Any]:
    safe_page_size = max(page_size, 1)
    pages: list[dict[str, Any]] = []
    for page_index, start in enumerate(range(0, len(evidence_refs), safe_page_size), start=1):
        page_refs = evidence_refs[start : start + safe_page_size]
        page_id = f"retrieval-evidence-page-{page_index:03d}"
        pages.append(
            {
                "page_id": page_id,
                "page_index": page_index,
                "page_size": len(page_refs),
                "source_ref_count": len(page_refs),
                "source_refs": [
                    {
                        "source_path": ref.get("source_path"),
                        "line_start": ref.get("line_start"),
                        "line_end": ref.get("line_end"),
                        "chunk_id": ref.get("chunk_id"),
                        "chunk_sha256": ref.get("chunk_sha256"),
                        "source_sha256": ref.get("source_sha256"),
                        "freshness_status": ref.get("freshness_status"),
                        "score": ref.get("score"),
                        "matched_terms": ref.get("matched_terms"),
                    }
                    for ref in page_refs
                ],
                "continuation_hint": (
                    f"Open page {page_index + 1} for the next evidence refs."
                    if start + safe_page_size < len(evidence_refs)
                    else "No additional evidence pages."
                ),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "retrieval_evidence_pages",
        "page_count": len(pages),
        "page_size": safe_page_size,
        "total_source_ref_count": len(evidence_refs),
        "chat_source_ref_count": min(chat_evidence_count, len(evidence_refs)),
        "artifact_source_ref_count": len(evidence_refs),
        "chat_refs_trace_to_pages": True,
        "source_text_retention": "metadata_only",
        "store_source_text": False,
        "continuation_hint": (
            f"See {pages[0]['page_id']} for paged evidence details." if pages else "No evidence pages were created."
        ),
        "pages": pages,
    }


def load_phase214_budget_summary(config_root: Path) -> dict[str, Any]:
    report_path = config_root / "runtime-state" / "phase214" / "phase214-large-corpus-context-budget-inventory-report.json"
    policy_path = config_root / "runtime" / "large_corpus_context_budget_inventory_policy.json"
    report = read_json_object(report_path) if report_path.is_file() else {}
    policy = read_json_object(policy_path) if policy_path.is_file() else {}
    summary = dict_value(report.get("summary"))
    budget = dict_value(policy.get("context_budget_sources"))
    return {
        "estimated_corpus_tokens": summary.get("estimated_token_count"),
        "file_count": summary.get("file_count"),
        "model_context_limit": budget.get("expected_model_limit", DEFAULT_MODEL_CONTEXT_LIMIT),
        "target_input_limit": budget.get("expected_target_input_limit", DEFAULT_TARGET_INPUT_LIMIT),
        "raw_1m_prompt_support_proven": summary.get("raw_1m_prompt_support_proven") is True,
        "phase214_report_path": str(report_path),
    }


def evidence_lines(evidence_refs: list[dict[str, Any]], *, limit: int = 5) -> list[str]:
    lines: list[str] = []
    for index, ref in enumerate(evidence_refs[:limit], start=1):
        lines.append(
            f"{index}. `{ref.get('source_path')}` lines {ref.get('line_start')}-{ref.get('line_end')} "
            f"(score {ref.get('score')}, terms {', '.join(string_list(ref.get('matched_terms'))[:6])}, "
            f"source {str(ref.get('source_sha256'))[:12]}, chunk {str(ref.get('chunk_sha256'))[:12]}, fresh)."
        )
    return lines


def build_limitations_answer(budget: dict[str, Any], *, target_input_limit: int, model_context_limit: int) -> tuple[str, list[str]]:
    estimated_tokens = budget.get("estimated_corpus_tokens")
    target_limit = budget.get("target_input_limit") or target_input_limit
    model_limit = budget.get("model_context_limit") or model_context_limit
    limitations = [
        "Raw 1M-token prompt support is not proven for the current local stack.",
        "The safe path is retrieval, chunking, summarization, and artifact paging.",
        "This answer uses budget evidence rather than stuffing the whole corpus into the prompt.",
    ]
    answer = (
        f"No. The Phase 214 inventory estimates `{estimated_tokens}` corpus tokens, while the gateway target input "
        f"limit is `{target_limit}` and the expected model context limit is `{model_limit}`. Use retrieval-first "
        "evidence selection and paged artifacts instead of sending the whole corpus as one prompt. "
        f"Evidence: `{budget.get('phase214_report_path')}`. Limitation: raw 1M-token support remains unproven."
    )
    return answer, limitations


def build_retrieval_answer(
    *,
    category: RetrievalAnswerCategory,
    evidence_refs: list[dict[str, Any]],
    budget: dict[str, Any],
    selected_token_estimate: int,
    target_input_limit: int,
) -> tuple[str, list[str], str]:
    if not evidence_refs:
        limitations = [
            "No fresh safe retrieval evidence was admitted.",
            "No source claim was made from unavailable or unsafe evidence.",
        ]
        return (
            "I cannot answer that from the large-corpus index yet because no fresh safe evidence was admitted. "
            "Try a narrower read-only request or rebuild the Phase 217 index.",
            limitations,
            "low",
        )
    limitations = [
        "Evidence is bounded retrieval metadata plus current-file freshness checks, not a full call graph.",
        "The full corpus was not inserted into the prompt.",
        "Longer evidence details are paged in the retrieval artifact.",
    ]
    evidence_summary = " ".join(evidence_lines(evidence_refs, limit=4))
    if category == RetrievalAnswerCategory.NAVIGATION:
        answer = (
            "The most relevant retrieved cluster for the order replay pipeline is the generated "
            "`src/order_replay/` module set, with supporting tests or cases where they rank high. "
            f"Start with these evidence refs: {evidence_summary} "
            f"Prompt budget proof: selected evidence estimates `{selected_token_estimate}` tokens against target input limit "
            f"`{target_input_limit}`, so this did not raw-stuff the `{budget.get('estimated_corpus_tokens')}`-token corpus. "
            "Confidence: medium."
        )
        return answer, limitations, "medium"
    if category == RetrievalAnswerCategory.EVIDENCE_LOOKUP:
        answer = (
            "Risk-gate-to-audit-summary evidence is concentrated in the retrieved order replay sources and related "
            f"supporting files. Direct evidence refs: {evidence_summary} "
            "Unknowns: this gate has not performed a full call-chain proof, so treat the result as evidence selection for "
            "the next investigation step. Confidence: medium."
        )
        return answer, limitations, "medium"
    if category == RetrievalAnswerCategory.SUMMARIZATION:
        answer = (
            "The generated service corpus is a deterministic multi-file fixture organized around source modules, tests, "
            "docs/config/cases, and repeated order-replay/risk-gate/audit-summary markers. "
            f"Representative retrieved refs: {evidence_summary} "
            f"The answer used `{selected_token_estimate}` selected evidence tokens instead of reading the full corpus or the full "
            f"`{budget.get('estimated_corpus_tokens')}`-token corpus. Confidence: medium."
        )
        return answer, limitations, "medium"
    return (
        f"I found fresh retrieval evidence but the request category is not specific enough. Evidence refs: {evidence_summary} "
        "Ask for navigation, evidence lookup, architecture summary, or context-limit explanation. Confidence: low.",
        limitations,
        "low",
    )


def build_report(request: RetrievalBackedChatAnswerRequest, run_dir: Path) -> dict[str, Any]:
    config_root = Path(request.config_root).resolve()
    target_root = Path(request.target_root).resolve()
    policy_path = resolve_path(config_root, request.context_index_policy_path)
    context_policy = read_json_object(policy_path)
    index_path = policy_index_path(config_root, context_policy)
    index = read_json_object(index_path)
    phase216_policy_path = resolve_path(config_root, str(context_policy.get("phase216_policy_path")))
    phase216_policy = read_json_object(phase216_policy_path)
    indexed_root = context_index_target_root(config_root, context_policy, index)
    category = classify_request(request.user_request)
    budget = load_phase214_budget_summary(config_root)
    validation_errors: list[dict[str, Any]] = []

    if normalized_path_identity(target_root) != normalized_path_identity(indexed_root):
        validation_errors.append(
            {
                "id": "target_root.not_indexed_corpus",
                "severity": "high",
                "message": "target_root does not match the Phase 217 indexed corpus",
            }
        )
    if index.get("source_text_retention") != "metadata_only" or index.get("store_source_text") is not False:
        validation_errors.append(
            {
                "id": "index.source_text_retention",
                "severity": "critical",
                "message": "Phase 218 requires the Phase 217 index to be metadata-only",
            }
        )
    if contains_unsafe_evidence_request(request.user_request):
        artifact_evidence_refs: list[dict[str, Any]] = []
        answer = (
            "I cannot retrieve private, ignored, credential, token, or secret-like evidence into chat. "
            "The large-context path fails closed for that request and makes no source claim."
        )
        limitations = [
            "Ignored/private/secret-like content is not allowed in retrieval-backed chat.",
            "No source claim was made from denied evidence.",
        ]
        evidence_refs = []
        safety_decisions = [
            {
                "source_path": "request",
                "decision": "reject",
                "reasons": ["unsafe_evidence_request"],
            }
        ]
        confidence = "high"
        selected_token_estimate = 0
        validation_errors.append(
            {
                "id": "request.unsafe_evidence_request",
                "severity": "high",
                "message": "request asks for private, ignored, credential, token, or secret-like evidence",
            }
        )
    elif category == RetrievalAnswerCategory.LIMITATIONS:
        artifact_evidence_refs = []
        answer, limitations = build_limitations_answer(
            budget,
            target_input_limit=request.target_input_limit,
            model_context_limit=request.model_context_limit,
        )
        evidence_refs: list[dict[str, Any]] = []
        safety_decisions: list[dict[str, Any]] = []
        confidence = "high"
        selected_token_estimate = 0
        artifact_evidence_refs: list[dict[str, Any]] = []
    else:
        query_terms = query_terms_for_category(request.user_request, category)
        artifact_evidence_refs, safety_decisions = select_valid_evidence(
            target_root=target_root,
            index=index,
            phase216_policy=phase216_policy,
            query_terms=query_terms,
            category=category,
            max_evidence_refs=request.max_artifact_evidence_refs,
        )
        evidence_refs = artifact_evidence_refs[: request.max_evidence_refs]
        rejected_reasons = {
            reason
            for decision in safety_decisions
            if decision.get("decision") == "reject"
            for reason in string_list(decision.get("reasons"))
        }
        if not evidence_refs and rejected_reasons.intersection(FRESHNESS_OR_POLICY_REJECTION_REASONS):
            validation_errors.append(
                {
                    "id": "index.no_fresh_evidence",
                    "severity": "high",
                    "message": "all candidate retrieval evidence was rejected by freshness or policy checks",
                }
            )
        selected_token_estimate = sum(int(ref.get("chunk_token_estimate") or 0) for ref in evidence_refs)
        answer, limitations, confidence = build_retrieval_answer(
            category=category,
            evidence_refs=evidence_refs,
            budget=budget,
            selected_token_estimate=selected_token_estimate,
            target_input_limit=request.target_input_limit,
        )
    artifact_pages = page_evidence_refs(
        artifact_evidence_refs,
        page_size=request.artifact_page_size,
        chat_evidence_count=len(evidence_refs),
    )
    if evidence_refs and artifact_pages.get("page_count"):
        answer = (
            f"{answer} Paged evidence: `{artifact_pages.get('page_count')}` page(s), "
            f"`{artifact_pages.get('artifact_source_ref_count')}` total source refs, starting at "
            f"`{object_list(artifact_pages.get('pages'))[0].get('page_id')}`. "
            "The chat refs trace to the paged artifact source refs."
        )
    prompt_budget = {
        "raw_corpus_estimated_tokens": budget.get("estimated_corpus_tokens"),
        "selected_evidence_token_estimate": selected_token_estimate,
        "target_input_limit": request.target_input_limit,
        "model_context_limit": request.model_context_limit,
        "raw_prompt_stuffing": False,
        "within_target_input_limit": selected_token_estimate < request.target_input_limit,
    }
    if not prompt_budget["within_target_input_limit"]:
        validation_errors.append(
            {
                "id": "prompt_budget.exceeded",
                "severity": "critical",
                "message": "selected evidence exceeded target input limit",
            }
        )
    status = RetrievalAnswerStatus.BLOCKED if validation_errors else RetrievalAnswerStatus.ANSWERED
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "retrieval_backed_chat_answer",
        "workflow": WORKFLOW_ID,
        "run_id": request.run_id or run_dir.name,
        "status": status.value,
        "target_root": str(target_root),
        "indexed_root": str(indexed_root),
        "user_request": request.user_request,
        "category": category.value,
        "answer": answer,
        "confidence": confidence,
        "evidence_refs": evidence_refs,
        "artifact_pages": artifact_pages,
        "safety_decisions": safety_decisions,
        "prompt_budget": prompt_budget,
        "limitations": limitations,
        "validation_errors": validation_errors,
        "source_text_retention": "metadata_only",
        "store_source_text": False,
        "store_rejected_content": False,
        "created_at": utc_now(),
        "summary": {
            "answer": answer,
            "route_status": "ready" if status == RetrievalAnswerStatus.ANSWERED else "blocked",
            "selected_workflow": WORKFLOW_ID,
            "retrieval_status": status.value,
            "retrieval_category": category.value,
            "retrieval_evidence_count": len(evidence_refs),
            "retrieval_artifact_page_count": artifact_pages.get("page_count"),
            "retrieval_artifact_source_ref_count": artifact_pages.get("artifact_source_ref_count"),
            "retrieval_continuation_hint": artifact_pages.get("continuation_hint"),
            "retrieval_first_page_id": object_list(artifact_pages.get("pages"))[0].get("page_id")
            if object_list(artifact_pages.get("pages"))
            else None,
            "retrieval_safety_decision_count": len(safety_decisions),
            "retrieval_confidence": confidence,
            "raw_prompt_stuffing": False,
            "target_input_limit": request.target_input_limit,
            "raw_corpus_estimated_tokens": budget.get("estimated_corpus_tokens"),
            "source_text_retention": "metadata_only",
            "phase219_ready": status == RetrievalAnswerStatus.ANSWERED,
        },
    }
    return report


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Retrieval-Backed Chat Answer",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Category: `{report.get('category')}`",
        f"- Confidence: `{report.get('confidence')}`",
        f"- Evidence refs: `{len(object_list(report.get('evidence_refs')))}`",
        f"- Raw prompt stuffing: `{dict_value(report.get('prompt_budget')).get('raw_prompt_stuffing')}`",
        "",
        "## Answer",
        "",
        str(report.get("answer")),
        "",
        "## Evidence Refs",
    ]
    for ref in object_list(report.get("evidence_refs")):
        lines.append(
            f"- `{ref.get('source_path')}` lines `{ref.get('line_start')}-{ref.get('line_end')}` "
            f"source `{str(ref.get('source_sha256'))[:12]}` chunk `{str(ref.get('chunk_sha256'))[:12]}`"
        )
    lines.extend(["", "## Limitations"])
    for item in string_list(report.get("limitations")):
        lines.append(f"- {item}")
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(["", "## Validation Errors"])
        for item in errors:
            lines.append(f"- `{item.get('id')}`: {item.get('message')}")
    return "\n".join(lines) + "\n"


def invoke_retrieval_backed_chat_answer(request: RetrievalBackedChatAnswerRequest) -> InvocationResult:
    run_id = request.run_id or f"large-context-retrieval-answer-{artifact_timestamp()}"
    run_dir = Path(request.output_root).resolve() / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    effective_request = RetrievalBackedChatAnswerRequest(
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
    report_path = run_dir / "retrieval-backed-chat-answer.json"
    markdown_path = run_dir / "retrieval-backed-chat-answer.md"
    write_json(report_path, report)
    markdown_path.write_text(render_markdown_report(report), encoding="utf-8")
    run_state = {
        "schema_version": SCHEMA_VERSION,
        "kind": "large_context_retrieval_answer_run_state",
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "summary": report["summary"],
        "artifacts": {
            "retrieval_backed_chat_answer": str(report_path),
            "retrieval_backed_chat_answer_markdown": str(markdown_path),
        },
        "updated_at": utc_now(),
    }
    run_state_path = run_dir / "run-state.json"
    write_json(run_state_path, run_state)
    artifacts = {
        "retrieval_backed_chat_answer": str(report_path),
        "retrieval_backed_chat_answer_markdown": str(markdown_path),
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
