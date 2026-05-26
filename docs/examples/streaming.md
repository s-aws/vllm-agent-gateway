# Streaming Examples

Context presence:

```bash
python scripts/run_streaming_documenter.py --target-root . --doc README.md \
  --mode context_presence \
  --query "runtime ports"
```

Deterministic modes:

```bash
python scripts/run_streaming_documenter.py --target-root . --doc README.md --mode token_count
python scripts/run_streaming_documenter.py --target-root . --doc README.md --mode coverage
python scripts/run_streaming_documenter.py --target-root . --doc README.md --mode outline
```

Model-assisted facts:

```bash
python scripts/run_streaming_documenter.py --target-root . --doc README.md \
  --mode extract_facts \
  --role-base-url http://127.0.0.1:8205/v1
```

Model-assisted classification:

```bash
python scripts/run_streaming_documenter.py --target-root . --doc README.md \
  --mode classify \
  --role-base-url http://127.0.0.1:8205/v1 \
  --classification-label installation \
  --classification-label runtime
```

Explicit lossy summarization:

```bash
python scripts/run_streaming_documenter.py --target-root . --doc README.md \
  --mode summarize \
  --role-base-url http://127.0.0.1:8205/v1 \
  --max-summaries 8 \
  --max-summary-depth 3
```

Bound a large run:

```bash
python scripts/run_streaming_documenter.py --target-root /path/to/project --doc huge.md \
  --mode context_presence \
  --query "required phrase" \
  --chunk-bytes 65536 \
  --read-block-bytes 8192 \
  --max-bytes 104857600 \
  --max-chunks 1000 \
  --max-model-records 1000 \
  --max-summaries 8 \
  --max-summary-depth 3
```

Resume from streaming state:

```bash
python scripts/run_streaming_documenter.py --target-root /path/to/project --doc huge.md \
  --mode context_presence \
  --query "required phrase" \
  --resume .agentic_reports/streaming-state-<target>-<doc>-<run-id>.json
```
