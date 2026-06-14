# Chat-Visible Answer Contract Enforcement Examples

Run the Phase 201 gate:

```bash
python3 scripts/validate_chat_visible_answer_contract_enforcement.py
```

Inspect the generated summary:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase201/phase201-chat-visible-answer-contract-enforcement-report.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
PY
```

Expected passing summary shape:

```json
{
  "contract_count": 38,
  "negative_case_count": 304,
  "negative_control_count": 4,
  "output_format_count": 2,
  "passed_positive_case_count": 76,
  "phase202_ready": true,
  "positive_case_count": 76,
  "rejected_negative_case_count": 304,
  "validation_error_count": 0
}
```

Review failed cases:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase201/phase201-chat-visible-answer-contract-enforcement-report.json").read_text())
for error in report["validation_errors"]:
    print(f"{error['id']}: {error['message']}")
PY
```

Phase 201 proves deterministic controller-rendered fixture enforcement against the Phase 200 inventory, including record-specific contract details. Use Phase 202 for live default, JSON, gateway, and AnythingLLM proof.
