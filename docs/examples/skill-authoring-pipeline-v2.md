# Skill Authoring Pipeline V2 Examples

Build the Phase 194 report:

```bash
python3 scripts/validate_skill_authoring_pipeline_v2.py
```

Write to explicit paths:

```bash
python3 scripts/validate_skill_authoring_pipeline_v2.py \
  --candidate-root tests/fixtures/skill_authoring_pipeline_v2/phase194-readme-locator \
  --output-path runtime-state/phase194/phase194-skill-authoring-pipeline-v2-report.json \
  --markdown-output-path runtime-state/phase194/phase194-skill-authoring-pipeline-v2-report.md \
  --batch-report-path runtime-state/phase194/phase194-skill-authoring-pipeline-v2-batch-report.json
```

Inspect the candidate decision:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase194/phase194-skill-authoring-pipeline-v2-report.json").read_text())
print(report["status"])
print(report["gate_scope"])
print(report["packet_status"])
print(report["proof_status"])
print(report["promotion_eligible"])
print(report["candidate"]["skill_id"])
print(report["summary"]["promotion_decision"])
print(report["summary"]["next_action"])
PY
```

Phase 194 passing output means the draft packet is admitted for review. It does not mean the skill is proved or promotion eligible.

Author a new candidate packet:

1. Start from a real prompt gap, not a speculative skill idea.
2. Create one draft skill body, one batch manifest, one planned prompt-coverage entry, one eval skeleton, docs stubs, and a fail-closed regression skeleton under a candidate root.
3. Add at least two target prompts and two holdout prompts.
4. Define objective acceptance criteria with concrete evidence artifacts.
5. Define the blind-baseline-first plan before collecting local-model output.
6. Define live validation across localhost `8000`, gateway `8300`, controller `8400`, workflow-router `8500`, documenter `8205`, AnythingLLM, and both frozen Coinbase fixture roots.
7. Run this validator. Only later lifecycle phases may install or promote the skill.

List missing gates or validation errors:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase194/phase194-skill-authoring-pipeline-v2-report.json").read_text())
for gate in report["gate_results"]:
    if gate["status"] == "missing":
        print("missing gate:", gate["id"])
for error in report["validation_errors"]:
    print(error["id"], error["message"])
PY
```
