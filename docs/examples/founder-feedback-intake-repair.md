# Founder Feedback Intake And Repair Examples

Run the Phase 198 intake gate after Phase 197 has completed:

```bash
python3 scripts/validate_founder_feedback_intake_repair.py
```

Review the summary:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase198/phase198-founder-feedback-intake-repair-report.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
PY
```

Review decisions:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase198/phase198-founder-feedback-intake-repair-report.json").read_text())
for item in report["decision_records"]:
    print(item["case_id"], item["decision"], item["owner_path"], item["required_rerun_gate"])
PY
```

Optional founder notes use this shape:

```json
{
  "kind": "founder_feedback_notes",
  "phase": 198,
  "notes": [
    {
      "case_id": "P01",
      "prompt": "exact Phase 197 prompt",
      "target_run_id": "workflow-router-...",
      "classification": "advisory",
      "severity": "medium",
      "actual_response_excerpt": "short excerpt",
      "expected_behavior": "what should have happened",
      "fixture_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
      "created_at": "2026-06-11T00:00:00Z"
    }
  ]
}
```

Unlinked notes are written to `rejected_records` with rejection reasons. They do not become implementation work.
