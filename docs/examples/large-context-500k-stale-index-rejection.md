# Large-Context 500k Stale-Index Rejection Examples

Run the full Phase 272 gate:

```bash
python3 scripts/validate_large_context_500k_stale_index_rejection.py
```

Inspect the generated report:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase272/phase272-large-context-500k-stale-index-rejection-report.json").read_text())
print(report["summary"]["candidate_estimated_project_tokens"])
print(report["summary"]["phase260_case_count"])
print(report["summary"]["phase260_passed_case_count"])
print(report["summary"]["phase273_ready"])
PY
```

Expected values:

```text
500000
6
6
True
```

This gate is intentionally non-live. It proves that the stale-index and unsafe-evidence controls remain fail-closed before the 500k candidate is tested through gateway and AnythingLLM.
