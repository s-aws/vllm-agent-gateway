# Baseline Corpus Governance

Baseline corpus governance is the Priority 0 quality gate for blind-baseline chat evaluations.

It prevents chat-quality proof from becoming scattered reports by keeping one governed corpus at `runtime/baseline_corpus.json`. Each entry connects:

- prompt cases
- contextless blind baselines
- local gateway and AnythingLLM response captures
- blind-baseline comparison results
- holdout status
- repair status
- no-mutation proof
- source hashes for stale-result detection

The corpus does not replace live evaluation. It records whether the latest stable proof is complete, internally consistent, and still tied to the prompt/baseline inputs that produced it.

## When To Use

Run this gate when:

- closing a Priority 0 chat-quality phase
- changing prompt cases or blind baselines
- rerunning local evals or comparisons
- deciding whether a prompt family is still stable enough to build on
- preparing a release or founder-testing summary

## Validation

Validate the governed corpus and require local proof artifacts when they are available:

```bash
python scripts/validate_baseline_corpus.py --require-artifacts --output-path runtime-state/baseline-corpus/baseline-corpus-report.json
```

For clean clones that do not have local `runtime-state/` proof artifacts, omit `--require-artifacts`. The validator still checks the committed corpus shape, prompt cases, blind baselines, source ordering, hashes for committed sources, summary status, repair status, and holdout counts.

```bash
python scripts/validate_baseline_corpus.py
```

## Fail-Closed Conditions

The validator fails if a stable entry has:

- missing prompt cases or blind baselines
- blind baseline collected after local output
- missing local eval or comparison summary
- missing gateway or AnythingLLM route
- missing Coinbase frozen fixture coverage
- unresolved critical or high finding
- recommended repairs without accepted repair and holdout rerun status
- changed runtime or target fixture mutation proof
- stale committed prompt-case or blind-baseline hash

## Current Scope

The governed corpus covers stable Priority 0 entries from Phase 116 through Phase 119 plus the Phase 242 release-candidate promotion:

- `P0-BB-001`: code quality and self-review
- `P0-BB-002`: testing and defect diagnosis
- `P0-BB-003`: tradeoffs, debt, and engineering judgment
- `P0-BB-004`: delivery and mentorship
- `P0-M14-242`: promoted release-candidate chat-quality coverage from Phases 239-241

Phase 242 promoted cases declare required prompt categories, gateway and AnythingLLM target surfaces, expected answer markers, forbidden behaviors, evidence expectations, and source proof reports. AnythingLLM answer usefulness is covered by `README.anythingllm-answer-usefulness.md`.
