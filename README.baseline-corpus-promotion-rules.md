# Baseline Corpus Promotion Rules

Phase 142 defines how founder smoke or prompt-pack cases can become stable Priority 0 baseline corpus entries.

This feature is a promotion gate, not a corpus mutator. It validates readiness and blocks unsafe promotion. Updating `runtime/baseline_corpus.json` still requires a separate approved phase.

## Required Promotion Evidence

A candidate can be approved only when all of these are present and hash-bound:

- `blind_baseline`: contextless blind baseline collected before local-model output.
- `local_model_comparison`: passed comparison with score `>=85`, zero critical findings, and zero high findings.
- `holdout`: holdout proof with at least one holdout case and passing status.
- `route_proof`: gateway and AnythingLLM route proof covering both frozen Coinbase fixtures.
- `no_mutation_proof`: no runtime or target source mutation.
- `founder_approval`: explicit founder approval scoped to baseline-corpus promotion.

## Current Candidate

The current governed candidate is `founder-pack-phase137`. It remains `blocked_pending_evidence` because the Phase 137 founder prompt pack has smoke/regression proof but not full stable-corpus promotion evidence.

That blocked state is intentional and passing. The validator fails only when a candidate claims approval or promotion without the required proof.

## Run

```bash
python3 scripts/validate_baseline_corpus_promotion_rules.py \
  --require-artifacts \
  --output-path runtime-state/baseline-corpus-promotion-rules/phase142/phase142-baseline-corpus-promotion-rules-report.json
```

Expected current pass shape:

```json
{
  "status": "passed",
  "summary": {
    "candidate_count": 1,
    "approved_candidate_count": 0,
    "blocked_candidate_count": 1,
    "error_count": 0
  }
}
```
