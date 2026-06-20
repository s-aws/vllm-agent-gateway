# Context Strategy Router Clone Replay

Phase 320 proves the Phase 319 context strategy router rebaseline can run from a clone without relying on ignored `runtime-state/phase214` artifacts.

The validator bootstraps a disposable large-context fixture and metadata-only context index, derives a Phase 319 policy pointed at that fixture, and runs the existing Phase 319 gate with live Phase 318 artifacts disabled. This is a clone-safety replay, not a replacement for the live context ceiling benchmark.

## What It Checks

- The disposable fixture and context index can be generated from committed source.
- Phase 319 passes against the bootstrapped fixture.
- Source text and the synthetic secret sentinel are not stored in index or report output.
- The replay does not require persistent runtime-state from the active workspace.
- Raw 500k prompt support remains unclaimed.

## Validation

```bash
python3 scripts/validate_context_strategy_router_clone_replay.py
python3 -m pytest tests/regression/test_context_strategy_router_clone_replay.py -q
```

## Artifacts

- Policy: `runtime/context_strategy_router_clone_replay_policy.json`
- Validator: `scripts/validate_context_strategy_router_clone_replay.py`
- Report: `runtime-state/phase320/phase320-context-strategy-router-clone-replay-report.json`
- Markdown report: `runtime-state/phase320/phase320-context-strategy-router-clone-replay-report.md`

Examples: [docs/examples/context-strategy-router-clone-replay.md](docs/examples/context-strategy-router-clone-replay.md)
