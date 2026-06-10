# Model Swap Smoke Probe Examples

Run from Bash/WSL after starting vLLM and the gateway/proxy stack.

## Smoke Current Localhost Model

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_model_swap_smoke_probe.py \
  --output-path runtime-state/model-swap-smoke-probe/phase154/phase154-model-swap-smoke-probe-report.json \
  --markdown-output-path runtime-state/model-swap-smoke-probe/phase154/phase154-model-swap-smoke-probe-report.md
```

Expected markers:

- `MODEL SWAP SMOKE PROBE REPORT ...`
- `MODEL SWAP SMOKE PROBE SUMMARY ...`
- `MODEL SWAP SMOKE PROBE PASS`

## Inspect The Decision

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/model-swap-smoke-probe/phase154/phase154-model-swap-smoke-probe-report.json").read_text())
print(report["summary"]["decision"])
print(report["decision"]["expected_model_ids"])
print(report["decision"]["actual_model_ids"])
print(report["decision"]["next_gate"])
PY
```

## Interpret Results

- `current_model_ready`: continue release work; this probe found no model swap.
- `model_swap_requires_drift`: run fresh local-model drift and model portability before judging chat quality.
- `fix_model_backend`: fix `localhost:8000` before model-quality evaluation.
- `fix_harness`: restart or repair gateway/controller/proxies before model-quality evaluation.
- `fix_model_generation`: fix direct generation from `localhost:8000` before model-quality evaluation.
- `refresh_current_model_evidence`: refresh current-model compatibility artifacts before release decisions.

## Follow-Up Gates For A Swap

```bash
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_fresh_local_model_drift.py \
  --output-path runtime-state/fresh-local-model-drift/phase127/model-swap-rerun-report.json

python3 scripts/validate_model_portability.py \
  --candidate-id localhost-8000-model-swap-candidate \
  --candidate-model-base-url http://127.0.0.1:8000/v1 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --output-path runtime-state/model-portability/phase154/model-swap-portability.json
```

Do not treat a swapped model as supported until those follow-up gates pass.
