# Large-Context 384k Objective Rebaseline Examples

Run the static objective gate:

```bash
python3 scripts/validate_large_context_384k_objective_rebaseline.py
```

Inspect the target threshold in the generated report:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase251/phase251-large-context-384k-objective-rebaseline-report.json").read_text())
print(report["summary"]["target_estimated_project_tokens"])
print(report["summary"]["phase251_ready"])
PY
```

Expected target:

```text
384000
```

This gate is intentionally static. It does not call vLLM or AnythingLLM and does not prove raw 384k-token prompting.
