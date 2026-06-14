# Chunked Investigation Executor Implementation

Phase 223 implements the read-only `large_context.chunked_investigation` executor.

Use this when a large-corpus prompt asks for a multi-step cross-file flow that is too broad for direct context and too structured for a single retrieval answer. The executor only runs when the existing context strategy router selects `chunked_investigation`.

## What It Does

- Stays inside `workflow_router.execute_read_only`.
- Reuses the metadata-first context index, retrieval evidence validation, and artifact paging contracts.
- Decomposes the prompt into bounded stages.
- Produces stage records, evidence refs, a claim map, paged evidence metadata, and an answer-first chat summary.
- Prefers distinct source refs across stages when fresh alternatives exist.
- Prefers test, doc, case, or config support for the verification stage when available.
- Renders the chat answer as a bounded flow narrative with scope limits, evidence metadata, and explicit unverified edges.
- Keeps source text retention metadata-only.
- Blocks stale, unsafe, mutation-risk, over-budget, or unindexed cases.

## Artifacts

- `chunked-investigation-report.json`
- `chunked-investigation-report.md`
- `chunked-investigation-plan.json`
- `chunk-stage-records.json`
- `chunk-evidence-refs.json`
- `chunk-page-manifest.json`
- `chunk-final-answer.json`

## Validation

Offline preflight:

```bash
python3 scripts/validate_chunked_investigation_executor_implementation.py
```

Live closeout through gateway and AnythingLLM:

```bash
python3 scripts/validate_chunked_investigation_executor_implementation.py --live --timeout-seconds 900
```

Focused regression:

```bash
python3 -m pytest tests/regression/test_chunked_investigation_executor.py tests/regression/test_chunked_investigation_executor_implementation.py -q
```

The focused gate also checks that visible stage refs do not unnecessarily duplicate the same source path and that verification-stage evidence can cite non-source support.

The answer-quality gate checks that chat output includes:

- `Scope and limits`
- `Evidence table`
- `Flow narrative`
- `Not proven by selected evidence`
- stage citations with path, lines, source hash, chunk hash, and freshness

Examples: [docs/examples/chunked-investigation-executor-implementation.md](docs/examples/chunked-investigation-executor-implementation.md)
