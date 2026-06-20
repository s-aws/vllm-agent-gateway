# Context Ceiling Benchmark Examples

Run the non-live policy check:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_context_ceiling_benchmark.py \
  --no-live \
  --output-path runtime-state/context-ceiling-benchmark/phase318-shape-validation.json
```

Run the live benchmark against the local vLLM endpoint:

```bash
python3 scripts/validate_context_ceiling_benchmark.py \
  --output-path runtime-state/context-ceiling-benchmark/phase318-validation.json
```

Inspect the summary:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/context-ceiling-benchmark/phase318-validation.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
PY
```

Important fields:

```text
result_count=4
max_prompt_tokens=<measured prompt size>
max_latency_seconds=<measured latency>
minimum_answer_score=<lowest score>
raw_500k_prompt_support_proven=false
stable_corpus_mutated=false
```

Phase 318 measured result:

```text
ctx-32k: timeout at 180.046 seconds, prompt_tokens=30407
ctx-64k: passed, score=100, latency=178.405 seconds, prompt_tokens=62012
ctx-128k: passed, score=100, latency=1.976 seconds, prompt_tokens=125013
ctx-256k: passed, score=100, latency=169.699 seconds, prompt_tokens=249354
```

If a context class fails, inspect `results[].failure_class`, `results[].error_sample`, and `results[].missing_fragments`. A failure is useful M7 evidence; it should be recorded as the measured ceiling rather than treated as support for raw long-context prompting.
