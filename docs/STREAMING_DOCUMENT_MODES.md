# Streaming Document Modes

Streaming document modes are for files that should not be loaded into memory as one string. They are separate from the normal documenter orchestrator on purpose: the normal path reviews bounded text chunks with the documenter role, while this path indexes and reduces byte ranges directly.

The deterministic streaming modes do not call vLLM.

## Current Modes

Implemented deterministic modes:

- `context_presence`: finds literal query occurrences and cites exact byte/line ranges.
- `token_count`: estimates tokens by reviewed file range, chunk, heading-derived section, and optional query match.
- `coverage`: reports reviewed, skipped, summarized, and failed ranges without doing another semantic reduction.
- `outline`: extracts markdown, AsciiDoc, and basic reStructuredText headings into a source-backed outline.

Output claims are labeled:

- `source_verified`: at least one match cites exact source ranges.
- `insufficient_evidence`: no reviewed range supports the requested mode result, or the run stopped before enough coverage.

Source-backed mode records include:

- `doc_id`
- `chunk_id`
- `byte_range`
- `line_range`
- `preview`
- `quality_label`

## Command

```bash
python scripts/run_streaming_documenter.py \
  --target-root /path/to/project \
  --doc README.md \
  --mode context_presence \
  --query "runtime ports"
```

Token count:

```bash
python scripts/run_streaming_documenter.py \
  --target-root /path/to/project \
  --doc README.md \
  --mode token_count \
  --query "runtime ports"
```

Coverage:

```bash
python scripts/run_streaming_documenter.py \
  --target-root /path/to/project \
  --doc README.md \
  --mode coverage
```

Outline:

```bash
python scripts/run_streaming_documenter.py \
  --target-root /path/to/project \
  --doc README.md \
  --mode outline
```

Bound work explicitly:

```bash
python scripts/run_streaming_documenter.py \
  --target-root /path/to/project \
  --doc huge.md \
  --query "required phrase" \
  --chunk-bytes 65536 \
  --read-block-bytes 8192 \
  --max-bytes 104857600 \
  --max-chunks 1000 \
  --max-query-matches 1000 \
  --max-outline-entries 2000
```

## Artifacts

The runner writes:

- `streaming-manifest-*.json`: file size, byte range, document type, sampled headings, and `full_content_read: false`.
- `streaming-state-*.json`: resumable byte and line offsets, completed chunks, matches, and coverage.
- `streaming-context-presence-*.json`: final report with mode definition, matches, quality label, coverage totals, reviewed ranges, skipped ranges, and artifact paths.
- `streaming-token-count-*.json`: token estimates with file, chunk, section, and optional query-match source refs.
- `streaming-coverage-*.json`: coverage-only report with reviewed, skipped, summarized, and failed ranges.
- `streaming-outline-*.json`: heading index and heading-derived section ranges.

The state schema is versioned with `schema_version: 1`.

## Resume

Pause deliberately:

```bash
python scripts/run_streaming_documenter.py \
  --target-root /path/to/project \
  --doc huge.md \
  --query "required phrase" \
  --stop-after-chunks 10
```

Resume from the state artifact:

```bash
python scripts/run_streaming_documenter.py \
  --target-root /path/to/project \
  --doc huge.md \
  --query "required phrase" \
  --resume .agentic_reports/streaming-state-<target>-<doc>-<run-id>.json
```

Resume refuses incompatible arguments by default. Use `--resume-allow-arg-changes` only when the mismatch is intentional.

## Limits

This phase does not implement recursive summarization. Summarization is a later lossy mode and must report caveats separately from source-verified evidence.

`context_presence` is deterministic and source-backed, but it is not semantic search. It finds literal query bytes case-insensitively.

`token_count` is an estimate, not tokenizer-exact accounting. Its default method is documented in the report as `utf8_character_count_div_4_rounded_up`.

`outline` is line-oriented. It carries partial lines across byte chunks so headings split by chunk boundaries can still be detected, but it is not a full Markdown parser.

Structured fact extraction, classification, and lossy summarization are later modes. Summarization remains explicit and non-default.
