# Artifact Paging And Long Answer Usability

Phase 219 keeps large-context answers useful when evidence is too long for one chat response.

The chat response remains answer-first. Longer evidence details are written to deterministic artifact pages with source refs, line spans, source hashes, chunk hashes, freshness, and continuation hints.

## What It Does

- Keeps the `Answer:` summary as the first visible chat content.
- Adds paged evidence metadata to the retrieval-backed answer artifact.
- Preserves source continuity from chat refs to artifact pages and from artifact pages back to source refs.
- Exposes page count, total artifact refs, first page ID, and continuation hint in both default and JSON output.
- Keeps source text out of durable index and paged artifacts.
- Preserves fail-closed behavior for ignored, private, secret-like, stale, unavailable, and unapproved evidence.

## Boundaries

- No new large-context chat endpoint.
- No raw 1M-token prompt support claim.
- No copied source text in page artifacts.
- No protected fixture mutation.
- Full context strategy routing is still Phase 220.

## Validation

```bash
python3 scripts/validate_artifact_paging_long_answer_usability.py
python3 -m pytest tests/regression/test_artifact_paging_long_answer_usability.py -q
```

## Artifacts

- Policy: `runtime/artifact_paging_long_answer_usability_policy.json`
- Validator: `scripts/validate_artifact_paging_long_answer_usability.py`
- Report: `runtime-state/phase219/phase219-artifact-paging-long-answer-usability-report.json`
- Markdown report: `runtime-state/phase219/phase219-artifact-paging-long-answer-usability-report.md`

Examples: [docs/examples/artifact-paging-long-answer-usability.md](docs/examples/artifact-paging-long-answer-usability.md)
