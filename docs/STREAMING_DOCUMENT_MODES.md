# Streaming Document Modes

Streaming document modes are for files that should not be loaded into memory as one string. They are separate from the normal documenter orchestrator on purpose: the normal path reviews bounded text chunks with the documenter role, while this path indexes and reduces byte ranges directly.

The streaming runner does not call vLLM for `context_presence`.

## Current Mode

`context_presence` is the first implemented mode.

It answers one narrow question: does a literal query appear in a document, and where?

Output claims are labeled:

- `source_verified`: at least one match cites exact source ranges.
- `insufficient_evidence`: no reviewed range contained the query, or the run stopped before full coverage.

Each match includes:

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

Bound work explicitly:

```bash
python scripts/run_streaming_documenter.py \
  --target-root /path/to/project \
  --doc huge.md \
  --query "required phrase" \
  --chunk-bytes 65536 \
  --read-block-bytes 8192 \
  --max-bytes 104857600 \
  --max-chunks 1000
```

## Artifacts

The runner writes:

- `streaming-manifest-*.json`: file size, byte range, document type, sampled headings, and `full_content_read: false`.
- `streaming-state-*.json`: resumable byte and line offsets, completed chunks, matches, and coverage.
- `streaming-context-presence-*.json`: final report with mode definition, matches, quality label, coverage totals, reviewed ranges, skipped ranges, and artifact paths.

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

`context_presence` is deterministic and source-backed, but it is not semantic search. It finds literal query bytes case-insensitively. Future modes can add token counts, coverage reports, outlines, structured fact extraction, classification, and lossy summarization without changing this mode's contract.
