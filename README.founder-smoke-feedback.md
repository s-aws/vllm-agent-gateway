# Founder Smoke Feedback Classification

Phase 135 classifies Phase 134 founder smoke results into governed next actions.

If the smoke suite passes, this report records that no feedback action is needed. If a smoke case fails, the classifier maps it to one of the governed follow-up types.

## Decision Types

- baseline candidate
- holdout candidate
- repair follow-up
- rejected finding
- skill/tool gap

## Command

From Bash/WSL:

```bash
python3 scripts/classify_founder_smoke_feedback.py \
  --require-artifacts \
  --smoke-report-path runtime-state/founder-field-tests/phase134-founder-smoke.json \
  --output-path runtime-state/founder-smoke-feedback/phase135/phase135-founder-smoke-feedback.json
```

Expected current marker:

```text
FOUNDER SMOKE FEEDBACK PASS
```

## Current Result

The current Phase 135 report has:

- `smoke_case_count=4`
- `failed_smoke_case_count=0`
- `classification_count=0`
- `actionable_feedback_count=0`

## Failure Handling

Failed smoke cases are classified from structured evidence:

- HTTP failure: repair follow-up, `harness_error`
- missing chat contract markers: repair follow-up, `deterministic_formatter`
- missing semantic markers or forbidden content: repair follow-up, `model_capability`
- failed case with no actionable evidence: rejected finding
