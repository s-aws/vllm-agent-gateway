# Large-Context 384k Objective Rebaseline

This gate keeps the current large-context goal centered on 384k-token project usability.

It does not create a new large-context implementation. It validates that durable project instructions, milestones, roadmap state, and active large-context acceptance thresholds agree on the current release target:

- 384k-token project usability through indexing, retrieval, chunking, summarization, artifact paging, evidence selection, and model-context-aware routing
- no raw 384k prompt-stuffing claim
- no requirement or approval to solve post-384k project usability before the current product is usable

Existing proof artifacts that exceed 384k tokens can remain useful surplus evidence. They must not raise the current release target or start post-384k work unless the 384k product target has a ship-ready proof chain and a future milestone expansion is explicitly approved.

## Command

```bash
python3 scripts/validate_large_context_384k_objective_rebaseline.py
```

## Pass Marker

```text
PHASE251 LARGE CONTEXT 384K OBJECTIVE REBASELINE PASS
```

## Scope Boundary

Post-384k project usability is paused until the 384k product target has a ship-ready proof chain and a future milestone expansion is explicitly approved. Raw 384k-token or larger prompts are not supported unless a dedicated proof gate validates the model configuration, vLLM settings, hardware memory, latency, and blind-baseline answer quality.
