# Streaming Document Modes

Streaming modes handle files that should not be loaded into memory as one string. They are explicit reductions, not hidden fallback behavior.

Use streaming for:

- oversized single-document inputs
- literal source-presence checks
- deterministic reductions
- source-validated model-assisted reductions
- lossy summarization only when explicitly requested

## Implemented Modes

Deterministic modes:

- `context_presence`: finds literal query occurrences and cites source ranges.
- `token_count`: estimates tokens by file, chunk, section, and optional query match.
- `coverage`: reports reviewed, skipped, summarized, and failed ranges.
- `outline`: extracts heading and section structure.

Model-assisted modes:

- `extract_facts`: source-validated facts and documentation gaps.
- `classify`: source-validated labels and risks.
- `summarize`: explicit lossy summaries with caveats and separate source-backed support records.

## Output Labels

- `source_verified`: cites exact source ranges and passes validation.
- `summary_derived`: lossy orientation from source-referenced summaries; not evidence by itself.
- `insufficient_evidence`: missing, weak, invalid, or incomplete support.

## Artifacts

- `streaming-manifest-*.json`
- `streaming-state-*.json`
- `streaming-context-presence-*.json`
- `streaming-token-count-*.json`
- `streaming-coverage-*.json`
- `streaming-outline-*.json`
- `streaming-extract-facts-*.json`
- `streaming-classify-*.json`
- `streaming-summarize-*.json`

## References

- Full mode details: [docs/STREAMING_DOCUMENT_MODES.md](docs/STREAMING_DOCUMENT_MODES.md)
- Examples: [docs/examples/streaming.md](docs/examples/streaming.md)
