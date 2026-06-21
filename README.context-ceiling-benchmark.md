# Context Ceiling Benchmark

Phase 318 measures the current local model's raw context behavior at 32K, 64K, 128K, and 256K prompt classes.

This is a benchmark gate, not a support claim. It does not change the stable large-context product path, which remains governed 500k-token project usability through indexing, retrieval, chunking, summarization, artifact paging, evidence selection, and routing. It does not claim raw 500k prompt support.

## What This Proves

- The expected local model is present on `localhost:8000`.
- `/tokenize` is available for prompt-size measurement.
- The model reports the required `max_model_len`.
- Four raw context classes can be attempted with measured prompt tokens.
- Each live result records latency, answer score, failure class, memory snapshots, and selected metrics.
- `runtime/baseline_corpus.json` remains unchanged.
- Raw 500k prompt support remains unproven.

## Validation

Shape-only validation:

```bash
python3 scripts/validate_context_ceiling_benchmark.py --no-live
```

Live validation:

```bash
python3 scripts/validate_context_ceiling_benchmark.py \
  --output-path runtime-state/context-ceiling-benchmark/phase318-validation.json
```

Expected marker for a fully measured live run:

```text
CONTEXT CEILING BENCHMARK PASS
```

The pass marker means every context class was measured and classified. Individual classes can still report `timeout`, `context_length_rejected`, `answer_quality_below_threshold`, or another failure class; those outcomes are M7 evidence, not a raw long-context support claim.

Examples: [docs/examples/context-ceiling-benchmark.md](docs/examples/context-ceiling-benchmark.md).
