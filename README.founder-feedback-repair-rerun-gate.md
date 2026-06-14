# Founder Feedback Repair Rerun Gate

Phase 228 defines the proof required before an accepted founder feedback repair can be marked fixed.

The gate requires:

- blind-baseline-first comparison
- target prompt rerun
- holdout prompt rerun
- gateway and AnythingLLM surfaces
- frozen fixture mutation checks
- gap-class comparison
- rejected-explanation capture
- artifact traceability

Manual success without rerun proof is explicitly blocked.

## Validation

```bash
python3 scripts/validate_founder_feedback_repair_rerun_gate.py
```

For policy-only preflight without live artifacts:

```bash
python3 scripts/validate_founder_feedback_repair_rerun_gate.py --allow-missing-live-artifacts
```

Examples: [docs/examples/founder-feedback-repair-rerun-gate.md](docs/examples/founder-feedback-repair-rerun-gate.md)
