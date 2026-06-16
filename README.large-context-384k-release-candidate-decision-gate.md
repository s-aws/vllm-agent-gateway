# Large-Context 384k Release-Candidate Decision Gate

This Phase 265 gate aggregates the accepted 384k-token project proof chain into a deterministic release-candidate decision:

- `ship`
- `hold`
- `repair_required`

It does not add a new runtime path and does not approve raw 384k prompt stuffing or post-384k expansion.

## What It Checks

- Phases 258 through 264 are marked complete in the roadmap.
- Phase 264 clean-clone replay proof is present at the explicit report path.
- The Phase 264 report proves the 384k target, all required strategies, gateway and AnythingLLM response counts, JSON/default parity, target settings, fixture safety, clean clone source state, and `phase265_ready=true`.
- Required docs preserve the current 384k boundary and known limitations.
- Runtime health is available on localhost model, gateway, controller, workflow-router gateway, role ports, and AnythingLLM API.

## Decision Rules

- `ship`: all required proof and live health checks pass.
- `hold`: only runtime health is unavailable while all static proof is valid.
- `repair_required`: any missing, stale, failed, unsafe, wrong-scope, documentation, answer-quality, fixture, index, or provenance gap exists.

## Command

Run this from the active project workspace after Phase 264 has been replayed from a clean remote clone. Pass the clean-clone Phase 264 report path explicitly:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_large_context_384k_release_candidate_decision_gate.py \
  --phase264-report-path /tmp/agentic_agents_phase264_remote_clone/runtime-state/phase264/phase264-large-context-384k-clean-clone-replay-report.json \
  --health-timeout-seconds 10
```

Do not rely on `runtime-state/phase264/` in the active workspace unless that report was freshly produced by the accepted clean-clone replay. Local `runtime-state/` is intentionally ignored and may contain stale failed reports.

## Pass Marker

```text
PHASE265 LARGE CONTEXT 384K RELEASE CANDIDATE DECISION GATE PASS
```

## Boundary

This gate decides whether the current 384k-token project usability target can move to stable handoff refresh. It is not an M15 gate. Work above 384k tokens remains paused until the 384k path has a ship-ready handoff and the founder explicitly approves post-384k scope.
