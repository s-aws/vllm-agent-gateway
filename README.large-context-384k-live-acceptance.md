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
python3 scripts/validate_large_context_384k_live_acceptance.py --live
```

For Windows AnythingLLM pointed at a WSL network URL, keep Bash validators on the internal router URL and pass the effective AnythingLLM target URL:

```bash
python3 scripts/validate_large_context_384k_live_acceptance.py \
  --live \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --anythingllm-workflow-router-base-url http://100.100.12.45:8500/v1
```

## Pass Marker

```text
PHASE261 LARGE CONTEXT 384K LIVE ACCEPTANCE PASS
```

## Boundary

This gate does not approve post-384k expansion. Work above 384k tokens remains paused until the 384k product target has a ship-ready proof chain and a future milestone expansion is explicitly approved.
