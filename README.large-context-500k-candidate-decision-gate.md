# Large-Context 500k Candidate Decision Gate

This gate aggregates the Phase 270 through Phase 275 proof chain into a deterministic `ship`, `hold`, or `repair_required` decision for the 500k-token project usability candidate.

It does not prove raw 500k prompt serving. The decision only applies to governed project usability through indexing, retrieval, chunking, summarization, artifact paging, evidence selection, and model-context-aware routing.

## Command

Use the Phase 275 clean-clone report path from the clone replay:

```bash
python3 scripts/validate_large_context_500k_candidate_decision_gate.py \
  --phase275-report-path /tmp/agentic_agents_phase275_remote_clone/runtime-state/phase275/phase275-large-context-500k-clean-clone-replay-report.json
```

Expected marker:

```text
PHASE276 LARGE CONTEXT 500K CANDIDATE DECISION GATE PASS
```

## Decision Rules

- `ship`: Phase 270 through Phase 275 are complete, the Phase 275 clean-clone replay passed, live runtime health is green, no blockers remain, and raw 500k prompt serving is still out of scope.
- `hold`: the only blockers are runtime health probes.
- `repair_required`: required proof is missing, failed, stale, or contradicts the 500k candidate boundary.

`ship` means Phase 277 may refresh the stable handoff. Phase 276 does not promote 500k to stable by itself and does not update stable release metadata.
