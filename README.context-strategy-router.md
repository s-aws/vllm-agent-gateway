# Context Strategy Router

Phase 220 adds deterministic context-strategy selection to the existing workflow-router path.

The router now records whether a request uses `direct_context`, `retrieval`, `chunked_investigation`, `summarization`, `artifact_paging`, or `refusal`. The selected strategy, execution path, rationale, rejected strategies, routing inputs, source freshness, and safe alternatives are exposed in artifacts and chat-visible summary metadata.

## What It Does

- Selects a context strategy before large-context execution.
- Preserves small-repo behavior with `direct_context`.
- Routes supported large-corpus evidence, summary, paging, and raw-context-limit questions through the existing retrieval-backed answer path.
- Fails closed for ambiguous, unindexed, stale, and mutation-risk large-context requests.
- Keeps answer-first chat and Phase 219 paged evidence continuity.
- Uses a shared enum source for strategy IDs.

## Boundaries

- No new chat endpoint.
- No raw 1M-token support claim.
- No chunked-investigation executor yet; the router selects and blocks that strategy until an executor is approved.
- No protected fixture mutation.
- No advanced refactor reactivation.

## Validation

```bash
python3 scripts/validate_context_strategy_router.py
python3 -m pytest tests/regression/test_context_strategy_router.py -q
```

## Artifacts

- Policy: `runtime/context_strategy_router_policy.json`
- Validator: `scripts/validate_context_strategy_router.py`
- Report: `runtime-state/phase220/phase220-context-strategy-router-report.json`
- Markdown report: `runtime-state/phase220/phase220-context-strategy-router-report.md`

Examples: [docs/examples/context-strategy-router.md](docs/examples/context-strategy-router.md)
