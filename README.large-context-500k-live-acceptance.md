# Large-Context 500k Live Acceptance

This gate proves the 500k-token project usability candidate through the live workflow-router gateway and AnythingLLM path after fixture/index readiness and stale-index rejection are proven.

It uses the existing Phase 261 live acceptance path for the live gateway, AnythingLLM, strategy coverage, JSON/default parity, blind-baseline comparison, target settings, and fixture fingerprint checks. Phase 273 does not add a second live harness; it requires Phase 272 first, then delegates live execution to Phase 261 and records the result as 500k candidate proof.

## What This Proves

- Phase 272 passed and the 500k candidate is ready for live validation.
- The existing Phase 261 live acceptance path still passes.
- Gateway and AnythingLLM each produce the expected live responses.
- Required strategies are covered: retrieval, artifact paging, summarization, refusal, and chunked investigation.
- JSON/default output parity passes.
- Critical and high blind-baseline findings are zero.
- The answer path remains governed by retrieval, chunking, summarization, artifact paging, evidence selection, and model-context-aware routing.

## Command

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_large_context_500k_live_acceptance.py \
  --live \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --anythingllm-workflow-router-base-url http://127.0.0.1:8500/v1 \
  --timeout-seconds 1200
```

For Windows AnythingLLM pointed at a WSL network URL, pass the effective printed workflow-router URL:

```bash
python3 scripts/validate_large_context_500k_live_acceptance.py \
  --live \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --anythingllm-workflow-router-base-url http://PRINTED_WSL_WORKFLOW_ROUTER_HOST:8500/v1 \
  --timeout-seconds 1200
```

Expected marker:

```text
PHASE273 LARGE CONTEXT 500K LIVE ACCEPTANCE PASS
```

## Scope Boundary

This gate does not promote 500k to stable. It proves live candidate behavior only. Phase 274 must close or classify any answer-quality repair findings, and Phase 276 must make the ship, hold, or repair-required decision.

Raw 500k prompt serving remains unsupported unless a separate proof gate validates model config, vLLM settings, hardware memory, latency, and blind-baseline answer quality.
