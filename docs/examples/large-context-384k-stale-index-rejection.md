# Large-Context 384k Stale-Index Rejection Examples

Run the stale-index rejection gate:

```bash
python3 scripts/validate_large_context_384k_stale_index_rejection.py
```

Inspect case results:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase260/phase260-large-context-384k-stale-index-rejection-report.json").read_text())
print(report["summary"]["case_count"])
print(report["summary"]["passed_case_count"])
for case in report["case_results"]:
    print(case["case_id"], case["surface"], case["passed"])
PY
```

Important retrieval-answer case:

```text
P260-STALENESS-005
```

That case proves retrieval blocks when all candidate evidence is rejected by freshness or policy checks.
