# Local Model Regression Watchlist Examples

Validate the current watchlist:

```bash
python3 scripts/validate_local_model_regression_watchlist.py \
  --require-artifacts \
  --output-path runtime-state/local-model-regression-watchlist/phase139/phase139-local-model-regression-watchlist-report.json
```

Inspect prompt-case coverage:

```bash
python3 -c 'import json; from pathlib import Path; report=json.loads(Path("runtime-state/local-model-regression-watchlist/phase139/phase139-local-model-regression-watchlist-report.json").read_text()); print(json.dumps(report["case_coverage"], indent=2, sort_keys=True))'
```

Inspect repair ownership:

```bash
python3 -c 'import json; from pathlib import Path; report=json.loads(Path("runtime-state/local-model-regression-watchlist/phase139/phase139-local-model-regression-watchlist-report.json").read_text()); print(json.dumps(report["repair_owner_counts"], indent=2, sort_keys=True))'
```
