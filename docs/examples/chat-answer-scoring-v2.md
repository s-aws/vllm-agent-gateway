# Chat Answer Scoring V2 Examples

Build the Phase 192 report:

```bash
python3 scripts/validate_chat_answer_scoring_v2.py
```

Write to explicit paths:

```bash
python3 scripts/validate_chat_answer_scoring_v2.py \
  --output-path runtime-state/phase192/phase192-chat-answer-scoring-v2-report.json \
  --markdown-output-path runtime-state/phase192/phase192-chat-answer-scoring-v2-report.md
```

Inspect summary and repair targets:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase192/phase192-chat-answer-scoring-v2-report.json").read_text())
print(report["status"])
print(report["summary"]["classification_counts"])
print(report["summary"]["repair_target_counts"])
print(report["summary"]["next_action"])
PY
```

List advisory or failed cases:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase192/phase192-chat-answer-scoring-v2-report.json").read_text())
for case in report["scored_cases"]:
    if case["classification"] != "pass":
        print(case["scored_case_id"], case["classification"], case["repair_targets"], case["recommended_next_action"])
PY
```
