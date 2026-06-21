# EIG Baseline Candidate Intake

Phase 307 records the EIG runtime prompt packs as stable-baseline candidates without mutating `runtime/baseline_corpus.json`.

Use this gate before live replay or promotion work. It prevents a common release mistake: treating closeout-proven EIG prompts as stable Priority 0 corpus entries before they have blind baselines, local-model comparison, holdouts, route proof, no-mutation proof, and founder approval.

## What This Proves

- The Phase 295 connector runtime chat pack contributes three candidate cases.
- The Phase 302 privacy runtime chat pack contributes four candidate cases.
- The current stable baseline corpus still has its original five entries and has not been mutated by this intake phase.
- The two proposed EIG entry IDs are not already present in the stable corpus.
- Each candidate remains blocked pending live replay and required promotion evidence.
- Stable corpus promotion still requires a separate phase.

## Not Included

- No stable corpus mutation.
- No live gateway or AnythingLLM replay.
- No founder approval recording.
- No real external connector execution.
- No real sensitive-data ingestion.

## Validation

Run:

```bash
python3 scripts/validate_eig_baseline_candidate_intake.py
```

Expected marker:

```text
EIG BASELINE CANDIDATE INTAKE PASS
```

The report writes to:

```text
runtime-state/eig-baseline-candidate-intake/phase307-validation.json
```

Examples: [docs/examples/eig-baseline-candidate-intake.md](docs/examples/eig-baseline-candidate-intake.md).
