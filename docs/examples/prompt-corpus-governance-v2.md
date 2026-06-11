# Prompt Corpus Governance V2 Examples

Run Phase 179 after Phase 178 has generated a passing blind-baseline delta report.

## Build The Report

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_prompt_corpus_governance_v2.py \
  --output-path runtime-state/phase179/phase179-prompt-corpus-governance-v2-report.json \
  --markdown-output-path runtime-state/phase179/phase179-prompt-corpus-governance-v2-report.md
```

Expected marker:

```text
PHASE179 PROMPT CORPUS GOVERNANCE V2 PASS
```

## Inspect Role Counts

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase179/phase179-prompt-corpus-governance-v2-report.json").read_text())
print(json.dumps(report["role_counts"], indent=2, sort_keys=True))
print(json.dumps(report["summary"], indent=2, sort_keys=True))
PY
```

Current passing summary shape:

```json
{
  "blocked_candidate_count": 1,
  "catalog_case_count": 34,
  "holdout_count": 6,
  "promotion_candidate_count": 6,
  "regression_count": 34,
  "target_count": 6,
  "validation_error_count": 0
}
```

## Review Promotion Candidates

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase179/phase179-prompt-corpus-governance-v2-report.json").read_text())
for group in report["promotion_candidate_groups"]:
    print(group["candidate_id"], group["decision_status"], group["case_ids"])
PY
```

`blocked_pending_founder_approval` is expected for the current repaired prompt set. Do not change it to `approved_for_promotion` or `promoted` without explicit founder approval and a separate stable-corpus update phase.
