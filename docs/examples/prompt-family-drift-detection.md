# Prompt Family Drift Detection Examples

Build the Phase 191 report:

```bash
python3 scripts/validate_prompt_family_drift_detection.py
```

Write to explicit paths:

```bash
python3 scripts/validate_prompt_family_drift_detection.py \
  --output-path runtime-state/phase191/phase191-prompt-family-drift-detection-report.json \
  --markdown-output-path runtime-state/phase191/phase191-prompt-family-drift-detection-report.md
```

Inspect the decision counts:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase191/phase191-prompt-family-drift-detection-report.json").read_text())
print(report["status"])
print(report["summary"]["decision_counts_by_source"])
print(report["summary"]["next_action"])
PY
```

Find catalog prompts that need repair before field testing:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase191/phase191-prompt-family-drift-detection-report.json").read_text())
for record in report["records"]:
    if record["source"] == "catalog" and record["decision"] in {"partial_drift", "out_of_coverage"}:
        print(record["prompt_id"], record["decision"], record["recommended_next_action"])
PY
```
