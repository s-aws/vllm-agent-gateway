# EIG Baseline Candidate Privacy Repair

Phase 314 repairs the EIG-3 PII authorization privacy answer that blocked Phase 313 local-model comparison.

The repair is deterministic and controller-owned. It does not call external services, does not reveal raw sensitive values, does not start a repository workflow, and does not mutate `runtime/baseline_corpus.json`.

## What Changed

The EIG-3 privacy no-target response now preserves case-specific policy facts from the prompt:

- fixture identifier
- sensitive-data classification
- `raw_value_shown: false`
- hallucinated-authorization rejection when the prompt involves claimed approval or authorization
- memory lifecycle rejection markers when the prompt involves stale, cross-session, wrong-session, or raw-sensitive memory
- no repository workflow boundary

## Proof

The repaired live replay passed across workflow-router gateway and AnythingLLM:

```text
candidate_count=2
live_result_count=14
covered_surface_count=2
missing_surface_count=0
stable_corpus_mutated=false
stable_corpus_promotion_allowed=false
validation_error_count=0
```

The repaired local comparison then passed against the Phase 312 blind baselines:

```text
comparison_decision=passed
response_count=14
passed_response_count=14
failed_response_count=0
minimum_score=95
hard_failure_count=0
recorded_evidence=["blind_baseline","local_model_comparison"]
remaining_missing_evidence=["founder_approval","holdout","no_mutation_proof","route_proof"]
```

Promotion remains blocked until the remaining evidence items and founder approval are present.

Examples: [docs/examples/eig-baseline-candidate-privacy-repair.md](docs/examples/eig-baseline-candidate-privacy-repair.md).
