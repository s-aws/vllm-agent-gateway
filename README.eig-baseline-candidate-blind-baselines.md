# EIG Baseline Candidate Blind Baselines

Phase 312 records the contextless blind-baseline expectations for the seven EIG baseline-candidate prompt cases.

This is promotion evidence only. It does not run the local model, does not approve promotion, and does not mutate `runtime/baseline_corpus.json`.

## What This Proves

- A bounded contextless subagent reviewed the seven EIG candidate prompts before local-model comparison.
- The blind agent did not see local-model output.
- Every EIG connector and privacy runtime candidate has an expected answer shape, required content, prohibited content, evidence expectations, hard failures, and scoring notes.
- The recorded promotion evidence type is `blind_baseline`.
- Promotion remains blocked on local-model comparison, holdout, route proof, no-mutation proof, and founder approval.

## Validation

Run:

```bash
python3 scripts/validate_eig_baseline_candidate_blind_baselines.py
```

Expected marker:

```text
EIG BASELINE CANDIDATE BLIND BASELINES PASS
```

The report writes to:

```text
runtime-state/eig-baseline-candidate-blind-baselines/phase312-validation.json
```

Expected summary:

```text
case_count=7
contextless_agent_first=true
local_model_output_seen=false
recorded_evidence=["blind_baseline"]
promotion_allowed=false
remaining_missing_evidence=["founder_approval","holdout","local_model_comparison","no_mutation_proof","route_proof"]
```

Examples: [docs/examples/eig-baseline-candidate-blind-baselines.md](docs/examples/eig-baseline-candidate-blind-baselines.md).
