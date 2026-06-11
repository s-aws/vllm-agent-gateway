# Skill Registry Readiness Review Examples

Build the Phase 193 report:

```bash
python3 scripts/validate_skill_registry_readiness_review.py
```

Write to explicit paths:

```bash
python3 scripts/validate_skill_registry_readiness_review.py \
  --output-path runtime-state/phase193/phase193-skill-registry-readiness-review-report.json \
  --markdown-output-path runtime-state/phase193/phase193-skill-registry-readiness-review-report.md \
  --scale-report-path runtime-state/phase193/phase193-skill-scale-source.json \
  --coverage-report-path runtime-state/phase193/phase193-prompt-skill-coverage-source.json
```

Inspect readiness decisions:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase193/phase193-skill-registry-readiness-review-report.json").read_text())
print(report["status"])
print(report["summary"]["decision_counts"])
print(report["summary"]["next_action"])
PY
```

List non-keep decisions:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase193/phase193-skill-registry-readiness-review-report.json").read_text())
for skill in report["skill_decisions"]:
    if skill["decision"] != "keep":
        print(skill["skill_id"], skill["decision"], skill["recommended_next_action"])
PY
```

Confirm implemented coverage and planned coverage are separate:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase193/phase193-skill-registry-readiness-review-report.json").read_text())
for skill in report["skill_decisions"]:
    planned = skill["planned_coverage_entry_ids"]
    evidence = skill["readiness_evidence"]
    if planned or not evidence["body_present"]:
        print(skill["skill_id"], "implemented=", skill["coverage_entry_ids"], "planned=", planned)
PY
```
