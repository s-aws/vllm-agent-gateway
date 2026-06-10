# Local Model Regression Watchlist

Phase 139 defines the compact watchlist for local-model behaviors most likely to regress founder testing.

The watchlist is intentionally small and tied to the Phase 137 founder prompt pack. Every current founder prompt case must be covered by at least one watch item.

## What It Contains

Each watch item records:

- prompt family
- covered founder prompt case IDs
- risk
- expected symptoms
- existing validation gates
- repair owner
- repair boundary
- severity

## Command

```bash
python3 scripts/validate_local_model_regression_watchlist.py \
  --require-artifacts \
  --output-path runtime-state/local-model-regression-watchlist/phase139/phase139-local-model-regression-watchlist-report.json
```

Expected current result:

```text
LOCAL MODEL REGRESSION WATCHLIST PASS
```

## Artifacts

- Watchlist: `runtime/local_model_regression_watchlist.json`
- Report: `runtime-state/local-model-regression-watchlist/phase139/phase139-local-model-regression-watchlist-report.json`

Use the report when a later gate fails. The failure should map back to one watch item before new phases or repairs are proposed.
