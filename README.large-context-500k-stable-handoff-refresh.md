# Large-Context 500k Stable Handoff Refresh

Phase 277 refreshes the stable tester handoff after the Phase 276 decision gate returned `ship` for governed 500k-token project usability.

This is a stable handoff for large project usability through governed context strategy: indexing, retrieval, chunking, summarization, artifact paging, evidence selection, stale-index rejection, clean-clone replay, live gateway proof, and AnythingLLM proof. It is not a raw context-window claim.

## What It Validates

- Phase 270 through Phase 276 are complete.
- The supplied Phase 276 report is `decision=ship` with zero blockers.
- Stable release metadata contains Phase 277 refresh fields.
- The committed stable proof contains the 500k project-usability metadata.
- The 384k-token project usability baseline remains preserved as lineage.
- Docs explain that raw 500k prompt serving is not claimed.
- Docs retain the limits that raw 1M-token prompt serving and advanced broad refactor orchestration are not released.

## Run It

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_large_context_500k_stable_handoff_refresh.py \
  --phase276-report-path runtime-state/phase276/phase276-large-context-500k-candidate-decision-gate-report.json
```

If the Phase 276 report came from the live clean-clone replay chain, pass its explicit path:

```bash
python3 scripts/validate_large_context_500k_stable_handoff_refresh.py \
  --phase276-report-path /mnt/c/agentic_agents/runtime-state/phase276/phase276-large-context-500k-candidate-decision-gate-report.json
```

Expected marker:

```text
PHASE277 LARGE CONTEXT 500K STABLE HANDOFF REFRESH PASS
```

## Boundary

Stable now covers 500k-token project usability through governed context strategy. The 384k-token project usability baseline remains preserved. Raw 500k prompt serving is not claimed. Raw 1M-token prompt serving is not claimed. Advanced broad refactor orchestration remains deferred.

Examples: [docs/examples/large-context-500k-stable-handoff-refresh.md](docs/examples/large-context-500k-stable-handoff-refresh.md).
