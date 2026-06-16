# Large-Context 500k Stale-Index Rejection

This gate proves stale, missing, ignored, private, or unsafe derived index state fails closed for the 500k-token project usability candidate before live gateway and AnythingLLM validation.

It uses the existing Phase 260 stale-index rejection path for the actual stale-source, changed-policy, missing-source, and unsafe-evidence cases. Phase 272 does not create a second stale-index implementation; it requires Phase 271 500k fixture/index readiness first, then delegates fail-closed case execution to Phase 260.

## What This Proves

- Phase 271 passed and the 500k fixture/index is ready.
- The existing Phase 260 stale-index rejection path still passes.
- Stale source hashes are blocked.
- Changed ignore and safety policy hashes are blocked.
- Missing indexed sources are blocked.
- Unsafe private, ignored, credential, token, or secret-like evidence requests are blocked.
- The 500k candidate cannot proceed to live acceptance until stale-index rejection is proven.

## Command

```bash
python3 scripts/validate_large_context_500k_stale_index_rejection.py
```

Expected marker:

```text
PHASE272 LARGE CONTEXT 500K STALE INDEX REJECTION PASS
```

## Scope Boundary

This phase does not call vLLM, the workflow-router gateway, the controller, or AnythingLLM.

Live 500k proof starts in Phase 273. Raw 500k prompt serving remains unsupported unless a separate proof gate validates model config, vLLM settings, hardware memory, latency, and blind-baseline answer quality.
