# Retrieval-First Context Strategy Design

Phase 215 defines the strategy contract for large-corpus questions before any retrieval, indexing, artifact paging, or router behavior is implemented.

The design is intentionally conservative. It does not claim raw 1M-token prompting and it does not approve indexing. It records how later phases must choose between direct context, retrieval, chunked investigation, summarization, artifact paging, and refusal.

## Strategy Labels

- `direct_context`: selected evidence fits inside the current gateway target input budget.
- `retrieval`: a specific large-corpus evidence lookup needs approved safe index or retrieval support.
- `chunked_investigation`: a flow or dependency question needs multiple bounded evidence steps.
- `summarization`: a broad overview can use representative source selection with explicit limitations.
- `artifact_paging`: detailed evidence must be paged to artifacts while chat remains useful.
- `refusal`: the request is unsafe, unsupported, unapproved, stale, ambiguous, or asks for raw prompt stuffing.

## Required Inputs

The design requires deterministic routing inputs for prompt intent, target root, corpus size, file count, requested specificity, output format, mutation intent, allowed-root status, ignore policy status, index safety status, source freshness, context budget, and ambiguity level.

## Failure Behavior

The policy fails closed for raw 1M prompt-stuffing requests, missing or unapproved target roots, ignored/private/secret-like content, stale indexes, missing evidence, ambiguous large-context requests, and large-corpus mutation/apply attempts.

## Phase Boundary

Phase 215 only validates the strategy contract. Later phases must still implement and prove:

- Phase 216: corpus and index safety governance.
- Phase 217: local context index prototype.
- Phase 218: retrieval-backed chat answers.
- Phase 219: artifact paging and long-answer usability.
- Phase 220: deterministic context strategy routing.
- Phase 221: live large-context closeout through gateway and AnythingLLM.

## Inputs

- `runtime/retrieval_first_context_strategy_design_policy.json`
- `runtime-state/phase214/phase214-large-corpus-context-budget-inventory-report.json`

## Outputs

- `runtime-state/phase215/phase215-retrieval-first-context-strategy-design-report.json`
- `runtime-state/phase215/phase215-retrieval-first-context-strategy-design-report.md`

## Validation

```bash
python3 scripts/validate_retrieval_first_context_strategy_design.py
python3 -m pytest tests/regression/test_retrieval_first_context_strategy_design.py -q
```
