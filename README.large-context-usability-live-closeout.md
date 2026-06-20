# Large-Context Usability Live Closeout

Phase 221 closes the first large-context usability proof for M6 and M8.

It runs blind-baseline-scored large-corpus prompts through the real workflow-router gateway and AnythingLLM paths. The gate proves the current stack can answer useful questions over the generated 1M+ token corpus without raw prompt stuffing, while preserving chat-visible strategy metadata, source hash proof, index freshness, paged artifacts, and small-repo non-regression.

## What It Validates

- Large-corpus evidence lookup routes to `retrieval`.
- Long evidence reports route to `artifact_paging`.
- Bounded architecture summaries route to `summarization`.
- Raw-context capacity questions route to a safe `refusal` answer that explains the context limit.
- Gateway and AnythingLLM responses start with useful chat-visible answers.
- Responses include `selected_context_strategy`, `context_strategy_rationale`, run IDs, source refs, and no raw prompt stuffing.
- Retrieved evidence refs revalidate against current source hashes and fresh index metadata.
- Small Coinbase fixture prompts remain `direct_context` and do not invoke large-context retrieval.

## Boundaries

- No raw 1M-token support claim.
- No new chat endpoint.
- No source text retained in the index or paged artifacts.
- No protected fixture mutation.
- No advanced refactor reactivation.

## Validation

Offline preflight:

```bash
python3 scripts/validate_large_context_usability_live_closeout.py
```

Live closeout:

```bash
python3 scripts/validate_large_context_usability_live_closeout.py --live --timeout-seconds 900
```

If `127.0.0.1:3001` is not the AnythingLLM API, pass the reachable AnythingLLM API network URL:

```bash
python3 scripts/validate_large_context_usability_live_closeout.py \
  --live \
  --anythingllm-api-base-url http://192.168.0.208:3001 \
  --timeout-seconds 900
```

Focused regression:

```bash
python3 -m pytest tests/regression/test_large_context_usability_live_closeout.py tests/regression/test_context_strategy_router.py -q
```

## Artifacts

- Policy: `runtime/large_context_usability_live_closeout_policy.json`
- Validator: `scripts/validate_large_context_usability_live_closeout.py`
- Report: `runtime-state/phase221/phase221-large-context-usability-live-closeout-report.json`
- Markdown report: `runtime-state/phase221/phase221-large-context-usability-live-closeout-report.md`

Examples: [docs/examples/large-context-usability-live-closeout.md](docs/examples/large-context-usability-live-closeout.md)
