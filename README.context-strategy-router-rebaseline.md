# Context Strategy Router Rebaseline

Phase 319 rebaselines the existing context strategy router after the Phase 318 raw-context benchmark.

This is not a second router and it does not claim raw 500k prompt support. It proves the controller still chooses deterministic strategies for small, medium, huge, ambiguous, unsupported, missing-index, stale-index, sensitive/secret, artifact-paging, chunked, and summarization requests.

## What It Checks

- Small requests stay on `direct_context`.
- Medium specific lookups use retrieval with budget evidence.
- Huge raw-context requests are refused as raw prompt stuffing and redirected to safer strategies.
- Ambiguous or unsupported large-context requests block instead of fabricating an answer.
- Missing and stale indexes fail closed.
- Sensitive or secret-seeking prompts refuse raw value retrieval.
- Repeated inputs produce the same route decision.
- Phase 318 remains a measurement boundary with `raw_500k_prompt_support_proven=false`.

## Validation

```bash
python3 scripts/validate_context_strategy_router_rebaseline.py
python3 -m pytest tests/regression/test_context_strategy_router_rebaseline.py -q
```

For static shape checks without a local Phase 318 report:

```bash
python3 scripts/validate_context_strategy_router_rebaseline.py --no-require-artifacts
```

## Artifacts

- Policy: `runtime/context_strategy_router_rebaseline_policy.json`
- Validator: `scripts/validate_context_strategy_router_rebaseline.py`
- Report: `runtime-state/phase319/phase319-context-strategy-router-rebaseline-report.json`
- Markdown report: `runtime-state/phase319/phase319-context-strategy-router-rebaseline-report.md`

Examples: [docs/examples/context-strategy-router-rebaseline.md](docs/examples/context-strategy-router-rebaseline.md)
