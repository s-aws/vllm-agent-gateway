# Large-Context 384k Live Acceptance

This gate proves the current 384k-token project target against the live local stack.

It is a composition gate, not a new runtime implementation. It requires:

- Phase 258 contract proof
- Phase 259 fixture/index readiness proof
- Phase 260 stale-index rejection proof
- Phase 221 plus Phase 223 live gateway and AnythingLLM proof
- blind-baseline comparison artifacts
- gateway JSON/default parity
- split-url AnythingLLM target settings proof
- pre/post fingerprints for the generated corpus and both Coinbase fixtures

It keeps the active product target at 384k-token project usability through governed retrieval, chunking, summarization, artifact paging, evidence selection, and model-context-aware routing.

## Command

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_large_context_384k_live_acceptance.py \
  --live \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --anythingllm-workflow-router-base-url http://127.0.0.1:8500/v1 \
  --timeout-seconds 1200
```

For Windows AnythingLLM pointed at a WSL network URL, the workflow-router gateway must be bound for network clients before the printed WSL URL is usable:

```bash
WORKFLOW_ROUTER_GATEWAY_BIND_HOST=0.0.0.0 \
GATEWAY_BIND_HOST=0.0.0.0 \
CONTROLLER_BIND_HOST=0.0.0.0 \
bash start-agent-prompt-proxies.sh
```

If the startup output says the network workflow-router target is unavailable while `WORKFLOW_ROUTER_GATEWAY_BIND_HOST=127.0.0.1`, restart with the bind-host setting above. Then keep Bash validators on the internal router URL and pass the effective AnythingLLM target URL printed by `start-agent-prompt-proxies.sh`:

```bash
python3 scripts/validate_large_context_384k_live_acceptance.py \
  --live \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --anythingllm-workflow-router-base-url http://PRINTED_WSL_WORKFLOW_ROUTER_HOST:8500/v1 \
  --timeout-seconds 1200
```

## Pass Marker

```text
PHASE261 LARGE CONTEXT 384K LIVE ACCEPTANCE PASS
```

Expected summary fields include:

- `response_count=18`
- `gateway_response_count=9`
- `anythingllm_response_count=9`
- `failed_small_repo_regression_count=0`
- `json_default_parity_status=passed`
- `critical_or_high_finding_count=0`
- strategy IDs: `retrieval`, `artifact_paging`, `summarization`, `refusal`, and `chunked_investigation`

## Proof Artifacts

Primary local artifacts are written under `runtime-state/phase261/`:

```text
phase261-large-context-384k-live-acceptance-report.json
phase261-phase221-large-context-usability-live-closeout-report.json
phase261-phase223-chunked-investigation-executor-implementation-report.json
phase261-blind-baseline-artifacts.json
phase261-blind-baseline-comparisons.json
```

## Boundary

This gate does not approve post-384k expansion. Work above 384k tokens remains paused until the 384k product target has a ship-ready proof chain and a future milestone expansion is explicitly approved.
