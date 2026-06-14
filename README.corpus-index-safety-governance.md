# Corpus Index Safety Governance

Phase 216 defines and validates the safety boundary for any future durable corpus index.

This phase does not build an index, choose embeddings, connect retrieval to chat, implement artifact paging, or prove raw 1M-token context. It proves that future indexing must fail closed before ignored, private, secret-like, stale, unapproved, binary, generated, or escaped content can enter chat-visible answers or durable artifacts.

## What It Checks

- Only explicitly approved roots can be indexed.
- Deny rules override allow rules.
- `.gitignore`, `.cgcignore`, and policy deny patterns apply before candidate admission.
- Binary files, generated runtime artifacts, private paths, and ignored paths are rejected.
- Secret-like values are detected before admission and are not copied into reports.
- Source hashes, chunk hashes, ignore-policy fingerprints, safety-policy fingerprints, model IDs, context strategy IDs, and freshness markers are required metadata.
- Stale source hashes, changed ignore policy hashes, changed safety policy hashes, changed context strategy IDs, symlink escapes, path traversal, and unapproved roots fail closed.
- Rejected source text cannot appear in chat-visible output, validation reports, or durable artifacts.

## Inputs

- `runtime/corpus_index_safety_governance_policy.json`
- `runtime-state/phase215/phase215-retrieval-first-context-strategy-design-report.json`

## Outputs

- `runtime-state/phase216/corpus-safety-negative-controls/`
- `runtime-state/phase216/phase216-corpus-index-safety-governance-report.json`
- `runtime-state/phase216/phase216-corpus-index-safety-governance-report.md`

## Validation

```bash
python3 scripts/validate_corpus_index_safety_governance.py
python3 -m pytest tests/regression/test_corpus_index_safety_governance.py -q
```

## Boundary

Phase 217 can prototype a local context index only after this gate passes. Phase 218 can connect retrieval to chat only after the index prototype also passes.
