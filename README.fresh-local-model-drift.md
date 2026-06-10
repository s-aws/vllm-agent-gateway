# Fresh Local-Model Drift Gate

Phase 127 adds a bounded Priority 0 drift gate for the current localhost model.

Use this gate when stable chat-quality proof may be stale because the local model, gateway, controller, AnythingLLM configuration, or prompt-routing behavior changed.

## What It Proves

The gate reruns a small stable subset from the governed baseline corpus:

- Phase 116 code-quality/self-review prompts
- Phase 117 defect-diagnosis prompts
- Phase 118 engineering-judgment prompts
- Phase 119 delivery/mentorship prompts

Each family runs two prompt cases: one against `/mnt/c/coinbase_testing_repo_frozen_tmp` and one against `/mnt/c/coinbase_testing_repo_frozen_tmp.github`.

Each case must pass through both:

- workflow-router gateway
- AnythingLLM API

The gate fails if a family is missing, a selected case is not traceable to the governed baseline corpus, a frozen target root is missing, one route is skipped, a fresh artifact is stale, a comparison regresses below the prior accepted minimum score, or mutation proof is non-empty.

## Primary Command

Run from Bash/WSL with `ANYTHINGLLM_API_KEY` available:

```bash
python3 scripts/validate_fresh_local_model_drift.py \
  --output-path runtime-state/fresh-local-model-drift/phase127/fresh-local-model-drift-report.json \
  --timeout-seconds 300 \
  --command-timeout-seconds 1800
```

The report is written under `runtime-state/fresh-local-model-drift/phase127/`.

`runtime-state/` is local-only and should not be committed.

## Inputs

- `runtime/fresh_local_model_drift_cases.json`: Phase 127 drift-case catalog.
- `runtime/baseline_corpus.json`: governed stable corpus from Phase 120.
- `runtime/phase116_*`, `runtime/phase117_*`, `runtime/phase118_*`, `runtime/phase119_*`: prompt cases and blind baselines.

## Output

The consolidated report includes:

- selected case IDs
- target roots
- route coverage
- subprocess commands and return codes
- fresh local-eval artifact path and hash
- fresh comparison artifact path and hash
- current source hashes
- prior accepted minimum route score
- fresh minimum route score
- drift severity
- next action

Status is `passed` only when all selected families pass and `summary.drift_status` is `no_drift_detected`.

## Failure Review

Start with:

```bash
python3 -m json.tool runtime-state/fresh-local-model-drift/phase127/fresh-local-model-drift-report.json
```

Review `errors`, then inspect the failed family comparison artifact listed in `fresh_comparison_path`.

Do not fix drift with prompt wording alone unless the fresh report proves the issue is only a prompt-contract miss. Routing, context, formatter, skill/tool, and model-capability gaps must be classified before repair.
