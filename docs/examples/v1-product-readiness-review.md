# V1 Product Readiness Review Examples

Run from Bash/WSL.

## Generate The Review

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_v1_product_readiness_review.py \
  --output-path runtime-state/v1-product-readiness-review/phase155/phase155-v1-product-readiness-review-report.json \
  --markdown-output-path runtime-state/v1-product-readiness-review/phase155/phase155-v1-product-readiness-review-report.md
```

Expected markers:

- `V1 PRODUCT READINESS REVIEW REPORT ...`
- `V1 PRODUCT READINESS REVIEW SUMMARY ...`
- `V1 PRODUCT READINESS REVIEW PASS`

## Inspect The Decision

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/v1-product-readiness-review/phase155/phase155-v1-product-readiness-review-report.json").read_text())
print(report["recommendation"])
print(report["summary"]["release_blocker_count"])
print(report["summary"]["model_swap_decision"])
print(report["supported_workflows"])
print(report["unsupported_workflows"])
PY
```

## Inspect Blockers

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/v1-product-readiness-review/phase155/phase155-v1-product-readiness-review-report.json").read_text())
for blocker in report["release_blockers"]:
    print(blocker["id"], blocker["source"], blocker["message"])
PY
```

No blockers should print for a passing review.

## Interpretation

`go_for_founder_testing` means V1 founder testing can continue within the documented local scope. It does not mean production deployment, broad advanced refactor orchestration, every repository/language, every coding task, unsupported output formats, or automatic model selection are released.
