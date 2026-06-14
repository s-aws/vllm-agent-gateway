# Release-Candidate Baseline Corpus Promotion Examples

## Validate The Promoted Corpus

```bash
python scripts/validate_baseline_corpus.py --require-artifacts --output-path runtime-state/baseline-corpus/phase242-baseline-corpus-report.json
```

Expected summary:

```text
BASELINE CORPUS GOVERNANCE {"entry_count": 5, "error_count": 0, "stable_entry_count": 5}
BASELINE CORPUS GOVERNANCE PASS
```

## Validate Promotion Rules After Corpus Hash Change

```bash
python scripts/validate_baseline_corpus_promotion_rules.py --require-artifacts --output-path runtime-state/baseline-corpus-promotion-rules/phase242-rules-report.json
```

Expected summary:

```text
BASELINE CORPUS PROMOTION RULES {"approved_candidate_count": 0, "blocked_candidate_count": 1, "candidate_count": 1, "error_count": 0, "promoted_candidate_count": 0, "rejected_candidate_count": 0}
BASELINE CORPUS PROMOTION RULES PASS
```

## Inspect Promoted Categories

```bash
python - <<'PY'
import json
from collections import Counter

cases = json.load(open("runtime/phase242_release_candidate_prompt_cases.json", encoding="utf-8"))["cases"]
print("case_count", len(cases))
print("holdout_count", sum(1 for case in cases if case["holdout"]))
print(Counter(case["category"] for case in cases))
PY
```

Expected high-level result:

- `case_count` is `20`
- `holdout_count` is `8`
- categories include greeting, small-repo read-only, non-Coinbase generalization, feedback, unsupported-boundary, and all large-context strategy families

## Focused Regression

```bash
python -m pytest tests/regression/test_baseline_corpus.py tests/regression/test_baseline_corpus_promotion_rules.py -q
```
