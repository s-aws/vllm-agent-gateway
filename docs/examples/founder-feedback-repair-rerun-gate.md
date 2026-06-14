# Founder Feedback Repair Rerun Gate Examples

Validate the current Phase 228 gate:

```bash
python3 scripts/validate_founder_feedback_repair_rerun_gate.py
```

Run a policy-only preflight:

```bash
python3 scripts/validate_founder_feedback_repair_rerun_gate.py --allow-missing-live-artifacts
```

Inspect the report:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/founder-feedback-loop/phase228/phase228-founder-feedback-repair-rerun-gate-report.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
PY
```
