# Context Index Prototype

Phase 217 builds a deterministic metadata-first context index prototype over the Phase 214 large corpus.

The index is not retrieval-backed chat. It stores admitted chunk metadata only: source paths, hashes, line spans, token estimates, bounded normalized search terms, and term hashes. It does not store source text, snippets, excerpts, rejected content, or secret-like values.

## What It Checks

- Phase 216 safety governance passed and remains in force.
- The index is built only from the approved Phase 214 generated corpus.
- `.gitignore`, `.cgcignore`, policy deny patterns, binary filtering, generated-artifact filtering, private paths, secret-like detection, unapproved roots, stale source hashes, and metadata mutation controls are enforced.
- Every chunk carries source hash, chunk hash, line span, token estimate, ignore-policy fingerprint, safety-policy fingerprint, context strategy ID, and freshness metadata.
- Query smoke tests return only source refs, line spans, hashes, matched terms, freshness status, and scores.
- The durable index and reports do not contain source text or rejected-source content.

## Inputs

- `runtime/context_index_prototype_policy.json`
- `runtime/corpus_index_safety_governance_policy.json`
- `runtime-state/phase216/phase216-corpus-index-safety-governance-report.json`
- `runtime-state/phase214/generated-large-corpus/`

## Outputs

- `runtime-state/phase217/phase217-context-index.json`
- `runtime-state/phase217/phase217-context-index-summary.md`
- `runtime-state/phase217/phase217-context-index-prototype-report.json`
- `runtime-state/phase217/phase217-context-index-prototype-report.md`

## Validation

```bash
python3 scripts/validate_context_index_prototype.py
python3 -m pytest tests/regression/test_context_index_prototype.py -q
```

## Boundary

Phase 217 does not connect retrieval to chat, choose embeddings, implement vector search, implement artifact paging, or prove raw 1M-token context. Phase 218 is the first gate that may attempt retrieval-backed chat answers.
