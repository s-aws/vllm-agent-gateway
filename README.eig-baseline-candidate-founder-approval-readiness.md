# EIG Baseline Candidate Founder Approval Readiness

Phase 317 aggregates the Phase 312-316 EIG baseline-candidate proof chain and verifies that founder approval is the only remaining blocker.

This gate does not promote candidates, does not record approval, does not mutate `runtime/baseline_corpus.json`, and does not merge PR #1. It exists so a contextless reviewer can see whether the current EIG candidates are ready for a founder decision without confusing that state with release or corpus promotion.

## What This Proves

- Two EIG baseline candidates still exist and cover seven source cases.
- `blind_baseline` evidence is recorded.
- `local_model_comparison` evidence is recorded.
- `route_proof` and `no_mutation_proof` evidence are recorded.
- `holdout` evidence is recorded.
- The stable baseline corpus hash is unchanged.
- Founder approval is not recorded.
- Stable corpus promotion remains blocked.

## Validation

Run:

```bash
python3 scripts/validate_eig_baseline_candidate_founder_approval_readiness.py
```

Expected marker:

```text
EIG BASELINE CANDIDATE FOUNDER APPROVAL READINESS PASS
```

Expected summary:

```text
candidate_count=2
blocked_candidate_count=2
recorded_evidence=["blind_baseline","holdout","local_model_comparison","no_mutation_proof","route_proof"]
missing_evidence=["founder_approval"]
ready_for_founder_decision=true
founder_approval_recorded=false
promotion_allowed=false
stable_corpus_mutated=false
```

Examples: [docs/examples/eig-baseline-candidate-founder-approval-readiness.md](docs/examples/eig-baseline-candidate-founder-approval-readiness.md).
