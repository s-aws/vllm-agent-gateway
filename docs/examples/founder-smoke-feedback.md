# Founder Smoke Feedback Examples

## Classify The Current Smoke Result

```bash
python3 scripts/classify_founder_smoke_feedback.py \
  --require-artifacts \
  --smoke-report-path runtime-state/founder-field-tests/phase134-founder-smoke.json \
  --output-path runtime-state/founder-smoke-feedback/phase135/phase135-founder-smoke-feedback.json
```

Expected output:

```text
FOUNDER SMOKE FEEDBACK {"actionable_feedback_count": 0, "classification_count": 0, "failed_smoke_case_count": 0, "smoke_case_count": 4}
FOUNDER SMOKE FEEDBACK PASS
```

## Inspect Classifications

```bash
python3 -c 'import json; from pathlib import Path; report=json.loads(Path("runtime-state/founder-smoke-feedback/phase135/phase135-founder-smoke-feedback.json").read_text()); print(json.dumps(report["summary"], indent=2, sort_keys=True))'
```

Current classifications are empty because the Phase 134 smoke suite passed.
