# Release-Candidate Ship Handoff

Phase 247 records the current ship-ready release-candidate state in committed metadata and validates that the tester-facing docs point at that state.

This gate exists because Phase 246 produced a `ship` decision from a release clone, but several durable docs and stable-channel metadata still referenced older proof floors. Phase 247 is the handoff packet that makes the ship decision contextless.

## Current Decision

- Decision: `ship`
- Decision source branch: `codex/m14-release-clone-proof`
- Decision source commit: `bb0c6b0`
- Decision source clone: `/tmp/agentic_agents_phase243_remote_clone`
- Runtime restoration gateway run: `workflow-router-20260614T225336875601Z`
- Runtime restoration AnythingLLM run: `workflow-router-20260614T225345166828Z`
- Final regression floor: `1594 passed, 4 skipped, 23 deselected`

The committed compact proof is:

```text
runtime/release_proofs/v1-1-release-candidate-stable-proof.json
```

Generated reports remain local-only under `runtime-state/`.

## What It Validates

- Stable release-channel readiness points at the Phase 246 ship proof.
- The committed compact proof records the ship decision, source branch, source commit, clone path, Phase 244 decision summary, Phase 245 run IDs, and full regression result.
- Tester-facing docs include current handoff markers and do not hide the old Phase 244 `hold` state.
- Known limitations remain visible: this is not a production deployment, raw 1M-token prompt serving is not claimed, and advanced broad refactor orchestration is not released.
- AnythingLLM must point at `http://127.0.0.1:8500/v1` for natural workflow routing.

## Validation

Run from Bash/WSL:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_release_candidate_ship_handoff.py
```

Expected marker:

```text
PHASE247 RELEASE CANDIDATE SHIP HANDOFF PASS
```

Examples: [docs/examples/release-candidate-ship-handoff.md](docs/examples/release-candidate-ship-handoff.md)

## Boundaries

This handoff does not expand the supported product scope. It packages the current release-candidate proof so a founder or external tester can start from durable state.

Advanced broad refactor orchestration is not released. Raw 1M-token prompt serving is not claimed. This is a local founder-testing release, not a production deployment.
