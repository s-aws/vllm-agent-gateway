# V1 Release-Candidate Decision Gate

Phase 244 makes the release-candidate decision explicit and auditable.

The gate can return three decisions:

- `ship`: all required proof exists and live runtime health passes.
- `hold`: proof is otherwise valid, but live runtime health is not ready.
- `repair_required`: required phase, report, documentation, or proof artifacts are missing or invalid.

This is intentionally not a "green-only" validator. A `hold` decision can be a passing gate result when it correctly identifies runtime health as the blocker.

## What It Checks

- Phase 232-243 roadmap statuses are complete.
- Required machine-readable reports exist for Phase 242 and Phase 243.
- Required docs are linked and include current known-limit markers.
- Localhost model, gateway, controller, role proxy, workflow-router gateway, and AnythingLLM API health probes are checked.
- The final decision gives the next action for ship, hold, or repair-required outcomes.

## Validation

Run the live decision gate:

```bash
python3 scripts/validate_v1_release_candidate_decision_gate.py
```

Run without live port probes for static policy/report validation:

```bash
python3 scripts/validate_v1_release_candidate_decision_gate.py --skip-live-health
```

Examples: [docs/examples/v1-release-candidate-decision-gate.md](docs/examples/v1-release-candidate-decision-gate.md)
