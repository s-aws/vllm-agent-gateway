# Prompt Tightening Recommendation Examples

## Run The Gate

```bash
python3 scripts/validate_prompt_tightening_recommendations.py \
  --require-artifacts \
  --output-path runtime-state/prompt-tightening-recommendations/phase128/prompt-tightening-recommendations-report.json
```

Expected output:

```text
PROMPT TIGHTENING RECOMMENDATIONS PASS
```

## Inspect Candidates

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/prompt-tightening-recommendations/phase128/prompt-tightening-recommendations-report.json").read_text())
for candidate in report["candidates"]:
    print(candidate["candidate_id"])
    print("status:", candidate["decision"]["status"])
    print("trigger:", ", ".join(candidate["trigger_reasons"]))
    print("suggestion:", candidate["suggestion_text"])
PY
```

## Expected Phase 128 Summary

```json
{
  "applied_prompt_catalog_change_count": 0,
  "candidate_count": 1,
  "decision_status_counts": {
    "accepted": 0,
    "pending_review": 1,
    "rejected": 0
  },
  "error_count": 0,
  "suggestion_class_counts": {
    "output_contract": 1
  },
  "trigger_reason_counts": {
    "low_confidence_pass": 1
  }
}
```

## Accepting A Candidate Later

Do not add rerun proof before approval.

After a founder approves a candidate, the decision record must include:

- `decision.status=accepted`
- decision rationale
- approval metadata
- target rerun proof
- holdout rerun proof
- gateway and AnythingLLM route coverage

Phase 128 validates that structure, but it does not perform the approved prompt rewrite.
