# M5 Generalization Closeout Examples

Use these commands from Bash/WSL.

## Run Closeout

```bash
python3 scripts/validate_m5_generalization_closeout.py
```

## Focused Regression

```bash
python3 -m pytest tests/regression/test_m5_generalization_closeout.py -q
```

## Report Review

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase213/phase213-m5-generalization-closeout-report.json").read_text())
print(report["status"], report["decision"], report["summary"])
for item in report["source_reports"]:
    print(item["id"], item["status"], item["path"])
PY
```
