# V1 Product Readiness Reassessment Examples

Generate the Phase 196 reassessment:

```powershell
$key=$env:ANYTHINGLLM_API_KEY
wsl.exe --cd /mnt/c/agentic_agents -- env "ANYTHINGLLM_API_KEY=$key" `
  python3 scripts/validate_v1_product_readiness_reassessment_live.py --timeout-seconds 900
```

```bash
python3 scripts/validate_v1_product_readiness_reassessment.py
```

Write explicit report paths:

```bash
python3 scripts/validate_v1_product_readiness_reassessment.py \
  --output-path runtime-state/phase196/phase196-v1-product-readiness-reassessment-report.json \
  --markdown-output-path runtime-state/phase196/phase196-v1-product-readiness-reassessment-report.md
```

Inspect the decision:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase196/phase196-v1-product-readiness-reassessment-report.json").read_text())
print(report["status"])
print(report["recommendation"])
print(report["summary"])
PY
```

Inspect blockers and advisories:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase196/phase196-v1-product-readiness-reassessment-report.json").read_text())
for blocker in report["release_blockers"]:
    print("BLOCKER", blocker["id"], blocker["message"])
for advisory in report["advisories"]:
    print("ADVISORY", advisory["id"], advisory["statement"])
PY
```

The report should not be treated as approval for advanced broad refactor work. That remains outside V1 founder beta scope.
