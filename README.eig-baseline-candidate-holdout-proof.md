# EIG Baseline Candidate Holdout Proof

Phase 316 validates paraphrased EIG baseline-candidate holdouts before any stable corpus promotion decision.

The holdout prompts were produced by a bounded contextless subagent before local output review, then adapted only enough to preserve the current deterministic router trigger contract. This phase does not promote candidates, does not record founder approval, and does not mutate `runtime/baseline_corpus.json`.

## What This Proves

- Three connector holdouts route through local-stub `connector.invoke`.
- Four synthetic privacy holdouts route through safe no-target privacy handling.
- Workflow-router gateway and AnythingLLM both pass.
- Connector registry and stable baseline corpus remain unchanged.
- The `holdout` promotion evidence item is recorded.
- Founder approval remains the only missing promotion evidence item.

## Validation

Run:

```bash
python3 scripts/validate_eig_baseline_candidate_holdout_proof.py \
  --anythingllm-api-base-url http://192.168.0.208:3001
```

Expected marker:

```text
EIG BASELINE CANDIDATE HOLDOUT PROOF PASS
```

Expected summary:

```text
holdout_case_count=7
result_count=14
passed_result_count=14
failed_result_count=0
recorded_evidence=["holdout"]
remaining_missing_evidence=["founder_approval"]
stable_corpus_mutated=false
connector_registry_mutated=false
```

Examples: [docs/examples/eig-baseline-candidate-holdout-proof.md](docs/examples/eig-baseline-candidate-holdout-proof.md).
