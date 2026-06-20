# EIG Baseline Candidate Live Replay

Phase 308 runs the Phase 307 EIG baseline candidates through live runtime proof without promoting them into `runtime/baseline_corpus.json`.

Use this after Phase 307 candidate intake passes. It composes the existing EIG connector runtime chat validator and EIG privacy runtime chat validator, then records whether the seven candidate cases pass through both required surfaces: workflow-router gateway and AnythingLLM.

## What This Proves

- Phase 307 candidate intake still passes.
- Baseline corpus governance still passes.
- The three EIG connector runtime candidates pass through the workflow-router gateway.
- The three EIG connector runtime candidates pass through AnythingLLM.
- The four EIG privacy runtime candidates pass through workflow-router gateway and AnythingLLM.
- Stable corpus promotion remains disabled.
- Founder approval is not recorded by this phase.

## Validation

Run from Bash or PowerShell after vLLM, the gateway/proxies, controller, and AnythingLLM are healthy.

```bash
python3 scripts/validate_eig_baseline_candidate_live_replay.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --anythingllm-api-base-url http://192.168.0.208:3001 \
  --timeout-seconds 240
```

Expected marker:

```text
EIG BASELINE CANDIDATE LIVE REPLAY PASS
```

The report writes to:

```text
runtime-state/eig-baseline-candidate-live-replay/phase308-validation.json
```

If Bash receives `404` from `http://127.0.0.1:3001/api/ping`, use the reachable AnythingLLM API address from the host network, such as `http://192.168.0.208:3001` or `http://100.100.12.45:3001`.

Examples: [docs/examples/eig-baseline-candidate-live-replay.md](docs/examples/eig-baseline-candidate-live-replay.md).
