# Large-Context 500k Candidate Rebaseline Examples

Run the static candidate gate:

```bash
python3 scripts/validate_large_context_500k_candidate_rebaseline.py
```

Inspect the target values in the generated report:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase270/phase270-large-context-500k-candidate-rebaseline-report.json").read_text())
print(report["summary"]["stable_estimated_project_tokens"])
print(report["summary"]["candidate_estimated_project_tokens"])
print(report["summary"]["phase270_ready"])
PY
```

Expected values:

```text
384000
500000
True
```

This gate is intentionally static. It proves the 500k candidate is approved and bounded; it does not prove live 500k behavior or raw 500k-token prompting.
