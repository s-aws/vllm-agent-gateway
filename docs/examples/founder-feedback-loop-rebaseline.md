# Founder Feedback Loop Rebaseline Examples

Run the offline Phase 227 catalog gate:

```bash
python3 scripts/validate_founder_feedback_loop_rebaseline.py
```

Run the live feedback loop after the model, gateway, controller, and AnythingLLM are running:

```bash
python3 scripts/validate_founder_feedback_loop_live.py \
  --cases-path runtime/founder_feedback_loop_phase227_cases.json \
  --output-path runtime-state/founder-feedback-loop/phase227/phase227-founder-feedback-loop-live.json \
  --timeout-seconds 900
```

Validate the live report:

```bash
python3 scripts/validate_founder_feedback_loop_rebaseline.py --require-live-report
```

Inspect the decision coverage:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/founder-feedback-loop/phase227/phase227-founder-feedback-loop-rebaseline-report.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
PY
```
