# V1 Beta Release Closeout Examples

Run the closeout gate:

```bash
python3 scripts/validate_v1_beta_release_closeout.py
```

Inspect the closeout summary:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase199/phase199-v1-beta-release-closeout-report.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
PY
```

Inspect source proof:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase199/phase199-v1-beta-release-closeout-report.json").read_text())
for source_id, ref in sorted(report["source_refs"].items()):
    print(source_id, ref["phase"], ref["status"], ref["sha256"])
PY
```

Inspect fixture status:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase199/phase199-v1-beta-release-closeout-report.json").read_text())
for item in report["fixtures"]:
    print(item["root"], "clean=", item.get("clean"))
PY
```

If the report returns `decision=blocked`, repair the listed validation errors before approving Phase 200.
