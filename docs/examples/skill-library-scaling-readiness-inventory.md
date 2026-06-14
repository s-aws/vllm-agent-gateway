# Skill Library Scaling Readiness Inventory Examples

Run the Phase 229 inventory gate:

```bash
python3 scripts/validate_skill_library_scaling_readiness_inventory.py
```

Inspect the recommended Phase 230 candidate:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/skill-library-scaling/phase229/phase229-skill-library-scaling-readiness-inventory-report.json").read_text())
print(report["summary"]["phase230_recommended_candidate_id"])
print(json.dumps(report["candidate_records"], indent=2, sort_keys=True))
PY
```
