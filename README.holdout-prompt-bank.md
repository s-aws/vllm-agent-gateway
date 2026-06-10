# Holdout Prompt Bank

The holdout prompt bank is the Priority 0 gate that proves stable prompt-family repairs do not overfit one target prompt.

The governed bank lives at `runtime/holdout_prompt_bank.json`. It indexes the holdout case IDs for each stable baseline-corpus entry and points to the prompt cases, blind baselines, local eval captures, and comparison reports that prove those holdouts still pass.

The report also records proof hashes and target coverage. If a holdout pair does not include both frozen Coinbase fixtures, the bank must name the missing frozen target roots and justify the coverage choice.

## When To Use

Run this gate when:

- closing a Priority 0 chat-quality phase
- accepting a repair from a blind-baseline miss
- changing prompt cases, blind baselines, or comparison logic
- rerunning local evals for a stable prompt family
- preparing a stable chat-quality release summary

## Validation

Validate against local runtime proof artifacts:

```bash
python scripts/validate_holdout_prompt_bank.py --require-artifacts --output-path runtime-state/holdout-prompt-bank/holdout-prompt-bank-report.json
```

For clean clones without `runtime-state/`, omit `--require-artifacts`. The validator still checks committed prompt cases, blind baselines, bank shape, corpus alignment, source hashes for committed inputs, and holdout IDs.

```bash
python scripts/validate_holdout_prompt_bank.py
```

## Fail-Closed Conditions

The gate fails if:

- a stable corpus entry is missing from the bank
- holdout IDs do not match prompt cases marked `holdout=true`
- a holdout has no blind baseline
- gateway or AnythingLLM local eval capture is missing
- a holdout route comparison did not pass
- a holdout route score is below `85`
- unresolved findings remain
- route captures lack run IDs or selected workflows
- source or target mutation proof is dirty
- a proof hash is stale
- missing frozen Coinbase holdout coverage is not explicitly justified
