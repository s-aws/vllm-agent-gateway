# EIG Baseline Candidate Promotion Readiness

Phase 311 validates whether the EIG baseline candidates are ready for stable baseline corpus promotion.

This gate is intentionally fail-closed. It does not mutate `runtime/baseline_corpus.json`, does not approve promotion, and does not replace founder approval. It creates a durable decision artifact that shows the current candidates are still blocked until every required promotion evidence type is recorded.

## What This Proves

- The Phase 307 EIG candidate intake policy is current.
- The Phase 308 live-replay policy is current.
- The stable baseline corpus is current and unchanged.
- PR #1 still contains the Phase 307/308 evidence markers and the stable-corpus promotion approval boundary.
- Both EIG candidate groups remain outside the stable corpus.
- Promotion remains blocked because committed promotion evidence refs and founder approval are not present.

## Current Decision

The expected current decision is:

```text
candidate_count=2
blocked_candidate_count=2
approved_candidate_count=0
promoted_candidate_count=0
promotion_allowed=false
stable_corpus_mutated=false
stable_corpus_mutation_allowed=false
founder_approval_recorded=false
```

The expected missing evidence set is:

```text
blind_baseline
local_model_comparison
holdout
route_proof
no_mutation_proof
founder_approval
```

Phase 308 live replay is useful evidence, but it is not enough by itself to promote these candidates into the stable corpus because the promotion system requires committed per-candidate evidence refs and explicit founder approval.

## Validation

Run:

```bash
python3 scripts/validate_eig_baseline_candidate_promotion_readiness.py
```

Expected marker:

```text
EIG BASELINE CANDIDATE PROMOTION READINESS PASS
```

The report writes to:

```text
runtime-state/eig-baseline-candidate-promotion-readiness/phase311-validation.json
```

Examples: [docs/examples/eig-baseline-candidate-promotion-readiness.md](docs/examples/eig-baseline-candidate-promotion-readiness.md).
