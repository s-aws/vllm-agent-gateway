# Workflow/Skill/Tool Selection Matrix Examples

Run the Phase 203 matrix refresh:

```bash
python3 scripts/validate_workflow_skill_tool_selection_matrix.py
```

Inspect the summary:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase203/phase203-workflow-skill-tool-selection-matrix-report.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
PY
```

List entries that still need Phase 204 explainability proof:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase203/phase203-workflow-skill-tool-selection-matrix-report.json").read_text())
for gap in report["gap_records"]:
    print(gap["entry_id"], gap["phase204_action"])
PY
```
