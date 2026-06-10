# Baseline Corpus Promotion Rules Examples

Validate the current promotion policy:

```bash
python3 scripts/validate_baseline_corpus_promotion_rules.py \
  --require-artifacts \
  --output-path runtime-state/baseline-corpus-promotion-rules/phase142/phase142-baseline-corpus-promotion-rules-report.json
```

Inspect candidate state:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/baseline-corpus-promotion-rules/phase142/phase142-baseline-corpus-promotion-rules-report.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
for candidate in report["candidates"]:
    print(candidate["candidate_id"], candidate["decision_status"], candidate["missing_evidence"])
PY
```

Current expected result:

```text
founder-pack-phase137 blocked_pending_evidence [...]
```

Do not edit `runtime/baseline_corpus.json` from this phase. A later approved corpus-update phase must perform stable-corpus mutation after the promotion rules report shows an approved candidate.
