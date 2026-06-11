# Founder Trial Execution Round

Phase 197 runs the Phase 195 founder trial pack through AnythingLLM and records prompt-level evidence for review.

Use this after Phase 196 recommends `release_for_broader_founder_beta`.

## What It Runs

- Smoke cases: `P01`, `P02`, `P03`, `P22`
- Expanded read-only cases: `P04`, `P05`, `P06`, `P08`, `P09`, `P10`, `P13`, `P17`, `P19`, `P21`
- AnythingLLM API: `http://127.0.0.1:3001`
- AnythingLLM provider target: `http://127.0.0.1:8500/v1`
- Workspace: `my-workspace`
- Frozen fixture roots:
  - `/mnt/c/coinbase_testing_repo_frozen_tmp`
  - `/mnt/c/coinbase_testing_repo_frozen_tmp.github`

## Run Live

If the API key is only present in Windows, bridge it into WSL:

```powershell
$key=$env:ANYTHINGLLM_API_KEY
wsl.exe --cd /mnt/c/agentic_agents -- env "ANYTHINGLLM_API_KEY=$key" `
  python3 scripts/validate_founder_trial_execution_round.py --run-live --timeout-seconds 900
```

Expected marker:

```text
PHASE197 FOUNDER TRIAL EXECUTION ROUND PASS
```

Outputs:

- `runtime-state/phase197/phase197-founder-trial-execution-run.json`
- `runtime-state/phase197/phase197-founder-trial-execution-run.md`
- `runtime-state/phase197/phase197-founder-trial-execution-run/responses/*.txt`
- `runtime-state/phase197/phase197-founder-trial-execution-round-report.json`
- `runtime-state/phase197/phase197-founder-trial-execution-round-report.md`

## Interpreting Results

`status` describes evidence validity. `quality_status` describes answer quality.

- `passed`: every trial prompt met the governed output and semantic markers.
- `advisory`: evidence is valid, but prompt risks or improvement suggestions remain.
- `failed`: evidence is valid, but one or more prompt answers missed the governed target.

Phase 198 should consume advisories and blockers from this report.

Examples: [docs/examples/founder-trial-execution-round.md](docs/examples/founder-trial-execution-round.md).
