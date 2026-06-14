# M5 Generalization Closeout

Phase 213 decides whether the M5 multi-repo generalization cycle is closed or must repeat.

The closeout gate reviews the Phase 209 fixture pack, the Phase 211 repaired live proof, and the Phase 212 live rerun across Staterail and Coinbase holdouts.

## Decision

The passing decision is `close_m5_move_to_m6`.

Phase 214 is now approved. It starts M6/M7 large-corpus and context-budget work as the next Priority 0 direction.

## Inputs

- `runtime/m5_generalization_closeout_policy.json`
- `runtime-state/phase209/phase209-multi-repo-fixture-baseline-pack-report.json`
- `runtime-state/phase210/phase210-multi-repo-baseline-comparison-report.json`
- `runtime-state/phase212/phase212-multi-repo-live-generalization-rerun-report.json`

## Outputs

- `runtime-state/phase213/phase213-m5-generalization-closeout-report.json`
- `runtime-state/phase213/phase213-m5-generalization-closeout-report.md`

## Validation

```bash
python3 scripts/validate_m5_generalization_closeout.py
python3 -m pytest tests/regression/test_m5_generalization_closeout.py -q
```

## Known Limits

M5 proves read-only chat quality and routing across the selected fixtures. It does not prove large-context usability, advanced broad refactor orchestration, or mutation workflows on protected fixtures.
