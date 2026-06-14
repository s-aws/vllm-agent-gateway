# Release-Candidate Baseline Corpus Promotion

Phase 242 promotes the passing release-candidate chat-quality coverage into the governed Priority 0 baseline corpus at `runtime/baseline_corpus.json`.

This is not a new live harness. It turns the existing Phase 239, Phase 240, and Phase 241 proof chain into stable baseline records so future repairs cannot silently regress:

- greeting and vague chat handling
- Coinbase small-repo read-only answers
- non-Coinbase Python-service and Staterail generalization
- feedback capture
- unsupported source-mutation refusal
- large-context retrieval, artifact paging, summarization, refusal, and chunked investigation

## What Changed

Phase 242 adds:

- `runtime/phase242_release_candidate_prompt_cases.json`
- `runtime/phase242_release_candidate_blind_baselines.json`
- one stable entry in `runtime/baseline_corpus.json`
- generated local proof summaries under `runtime-state/phase242/`
- stricter baseline corpus validation for promoted entries that declare required prompt categories, target surfaces, and promotion evidence

Each promoted logical case requires both `gateway` and `anythingllm` response proof.

## Validation

Run the governed corpus gate with local proof artifacts:

```bash
python scripts/validate_baseline_corpus.py --require-artifacts --output-path runtime-state/baseline-corpus/phase242-baseline-corpus-report.json
```

Run the older Phase 142 promotion-rule gate after the corpus hash changes:

```bash
python scripts/validate_baseline_corpus_promotion_rules.py --require-artifacts --output-path runtime-state/baseline-corpus-promotion-rules/phase242-rules-report.json
```

Run focused regression:

```bash
python -m pytest tests/regression/test_baseline_corpus.py tests/regression/test_baseline_corpus_promotion_rules.py -q
```

Because this changes the governed release-candidate baseline, phase closeout requires the full Bash regression gate.

## Failure Conditions

The corpus must fail if a promoted entry:

- omits any required release-candidate category
- drops either gateway or AnythingLLM target surface
- has empty expected markers, forbidden behaviors, or evidence expectations
- lacks promotion evidence for Phases 239, 240, and 241
- references stale or missing prompt, baseline, local-eval, comparison, or source proof hashes
- records unresolved critical or high findings
- records fixture/source mutation

## Scope Boundary

Phase 242 does not rerun live prompts. It promotes already-passing release-candidate proof into a durable regression surface. Fresh live drift remains covered by the existing live replay and drift gates.
