# EIG Baseline Candidate Route And Mutation Proof

Phase 315 validates the route and no-mutation evidence for repaired EIG baseline candidates.

This gate does not run promotion and does not edit `runtime/baseline_corpus.json`. It inspects the repaired live replay and its child reports to prove that the candidate responses used the expected routes and did not mutate source, connector registry, privacy source content, or stable corpus state.

## What This Proves

- Connector candidates used `connector.invoke` through the controller-owned mediation path.
- Privacy candidates used no repository workflow and returned `eig3_privacy_policy_no_target`.
- Gateway and AnythingLLM surfaces are both present.
- Connector source registry remained unchanged.
- Privacy reports did not retain raw source content.
- Stable baseline corpus was not mutated or promoted.
- The gate records `route_proof` and `no_mutation_proof` evidence.

## Validation

Run:

```bash
python3 scripts/validate_eig_baseline_candidate_route_mutation_proof.py \
  --live-replay-report-path runtime-state/eig-baseline-candidate-live-replay/phase314-after-pii-repair-live.json
```

Expected marker:

```text
EIG BASELINE CANDIDATE ROUTE MUTATION PROOF PASS
```

Expected summary:

```text
connector_result_count=6
privacy_result_count=8
route_proof_recorded=true
no_mutation_proof_recorded=true
recorded_evidence=["route_proof","no_mutation_proof"]
remaining_missing_evidence=["founder_approval","holdout"]
validation_error_count=0
```

Examples: [docs/examples/eig-baseline-candidate-route-mutation-proof.md](docs/examples/eig-baseline-candidate-route-mutation-proof.md).
