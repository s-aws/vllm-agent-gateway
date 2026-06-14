# Chat-Visible Answer Contract Inventory Examples

Run the Phase 200 inventory gate:

```bash
python3 scripts/validate_chat_visible_answer_contract_inventory.py
```

Inspect the summary:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase200/phase200-chat-visible-answer-contract-inventory-report.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
PY
```

List workflow counts:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase200/phase200-chat-visible-answer-contract-inventory-report.json").read_text())
for workflow, count in sorted(report["summary"]["workflow_counts"].items()):
    print(workflow, count)
PY
```

Review one contract:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase200/phase200-chat-visible-answer-contract-inventory-report.json").read_text())
record = report["contract_records"][0]
print(record["entry_id"])
print(record["selected_workflow"])
print(record["required_sections"])
print(record["output_format_behavior"])
PY
```

Use the inventory as input to Phase 201. Do not treat it as proof that the live model currently satisfies every contract.
