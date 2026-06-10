# Model Swap Smoke Probe

Phase 154 detects whether `localhost:8000` is still serving the expected current model and decides whether full chat-quality drift testing is required before release decisions.

Use this after restarting vLLM, changing model containers, changing model aliases, or recovering the gateway stack.

## What It Checks

- Live `http://127.0.0.1:8000/v1/models` metadata.
- One direct `/chat/completions` generation smoke against the reported model id.
- Harness health for the model, LLM gateway, workflow-router gateway, and controller.
- Current-model compatibility artifacts through the existing Phase 150 matrix.
- Expected model ids from `runtime/current_model_compatibility_matrix_policy.json`.

The probe does not mutate model profiles, change routing, enable automatic model selection, or approve a swapped model.

## Decisions

- `current_model_ready`: expected and actual model ids match; no model-swap-specific drift gate is required.
- `model_swap_requires_drift`: localhost model ids changed; run fresh local-model drift and model portability before release decisions.
- `fix_model_backend`: localhost `8000` metadata is unavailable.
- `fix_harness`: gateway/controller/proxy health failed.
- `fix_model_generation`: metadata is reachable but direct generation failed.
- `refresh_current_model_evidence`: compatibility artifacts are not passing.

## Run

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_model_swap_smoke_probe.py \
  --output-path runtime-state/model-swap-smoke-probe/phase154/phase154-model-swap-smoke-probe-report.json \
  --markdown-output-path runtime-state/model-swap-smoke-probe/phase154/phase154-model-swap-smoke-probe-report.md
```

Expected marker:

```text
MODEL SWAP SMOKE PROBE PASS
```

If the decision is `model_swap_requires_drift`, the probe can still pass. That means the detector worked, not that the new model is release-ready.

Examples: [docs/examples/model-swap-smoke-probe.md](docs/examples/model-swap-smoke-probe.md).
