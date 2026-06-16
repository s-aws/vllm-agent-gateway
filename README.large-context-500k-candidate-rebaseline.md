# Large-Context 500k Candidate Rebaseline

This gate activates a 500k-token project usability candidate after the 384k product path has been completed.

It does not promote 500k to stable. The current 384k stable baseline remains 384k-token project usability until the 500k candidate passes its own fixture, stale-index, live gateway, AnythingLLM, clean-clone, decision, and handoff proof.

## What This Proves

- 384k remains the stable large-context baseline.
- 500k-token project usability is now an approved candidate target.
- Raw 500k-token prompts are not supported or claimed.
- The next 500k phases are constrained to the existing indexing, retrieval, chunking, summarization, artifact paging, evidence selection, and model-context-aware routing path.
- The 500k candidate work must not alter protected frozen fixtures or generated stable proof artifacts.

## Command

```bash
python3 scripts/validate_large_context_500k_candidate_rebaseline.py
```

Expected marker:

```text
PHASE270 LARGE CONTEXT 500K CANDIDATE REBASELINE PASS
```

## Scope Boundary

This phase is static. It does not call vLLM, the workflow-router gateway, the controller, or AnythingLLM.

Live proof starts only after fixture/index readiness and stale-index rejection are proven for the 500k candidate. Raw 500k prompt serving remains unsupported unless a separate proof gate validates model config, vLLM settings, hardware memory, latency, and blind-baseline answer quality.
