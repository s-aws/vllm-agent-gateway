# Chunked Investigation Executor Implementation Examples

Run the offline preflight:

```bash
python3 scripts/validate_chunked_investigation_executor_implementation.py
```

Run the live closeout from Bash after the model and gateway stack are running:

```bash
python3 scripts/validate_chunked_investigation_executor_implementation.py --live --timeout-seconds 900
```

Inspect the live report:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase223/phase223-chunked-investigation-executor-implementation-report.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
for response in report["responses"]:
    print(response["surface"], response["run_id"], response["status"], response["chunked_evidence_count"])
for regression in report["small_repo_regression_results"]:
    print(regression["surface"], regression["target_root"], regression["status"], regression["selected_context_strategy"])
PY
```

Expected live closeout:

- `failed_response_count` is `0`
- `failed_small_repo_regression_count` is `0`
- `phase224_ready` is `true`
- gateway and AnythingLLM both return `large_context.chunked_investigation`
- small-repo prompts do not invoke the chunked executor
- visible chunked evidence prefers distinct source paths
- verification-stage evidence prefers test, doc, case, or config refs when available
- chat output includes `Scope and limits`, `Evidence table`, `Flow narrative`, and `Not proven by selected evidence`
- each evidence row includes stage, path, lines, source hash, chunk hash, and freshness

Example answer shape:

```text
Answer:
Chunked investigation result: Scope and limits: this is a bounded retrieval trace, not an exhaustive whole-corpus analysis...
Evidence table: risk gate / entry point: [stage: flow_entry_points | path: ... | lines: ... | source_hash: ... | chunk_hash: ... | freshness: fresh] ...
Flow narrative: Entry point: the selected evidence path indicates this stage through [...]
Not proven by selected evidence: The selected refs do not prove every intermediate call edge...
```
