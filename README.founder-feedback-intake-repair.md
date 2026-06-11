# Founder Feedback Intake And Repair Proposal

Phase 198 converts founder trial advisories, blockers, and optional founder feedback into deterministic repair decisions before V1 beta closeout.

Use this after `README.founder-trial-execution-round.md` has produced a valid Phase 197 report. This gate does not silently rewrite prompts or implement repairs. It decides whether each advisory or blocker is accepted, rejected, deferred, or blocking so Phase 199 can make a mechanical closeout decision.

## What It Validates

- Phase 197 report exists, passed, and has no validation errors.
- Phase 197 field report source reference exists and still matches its recorded hash.
- Every Phase 197 advisory or blocker has exactly one decision record.
- Response artifact paths and hashes are freshly verified.
- Founder notes, when present, are linked to the exact Phase 197 case, run ID, fixture root, and prompt.
- Unlinked or vague founder notes are rejected with reasons instead of becoming work.
- Every accepted record has an owner path, decision rationale, closure status, and rerun gate.
- Phase 199 is blocked when blockers or invalid proof remain.

## Outputs

- `runtime-state/phase198/phase198-founder-feedback-intake-repair-report.json`
- `runtime-state/phase198/phase198-founder-feedback-intake-repair-report.md`

The JSON report contains:

- `source_refs`: Phase 197 report, Phase 197 field report, and optional founder notes.
- `decision_records`: accepted advisory, blocker, or founder-note decisions.
- `rejected_records`: rejected founder notes with explicit reasons.
- `summary`: counts by source classification, owner, rerun gate, decision, blocker status, and Phase 199 readiness.

## Command

```bash
python3 scripts/validate_founder_feedback_intake_repair.py
```

The command passes only when the intake report can be deterministically rebuilt from its source artifacts.

## Phase 199 Boundary

Phase 199 must not proceed if the Phase 198 report is missing, failed, stale, has validation errors, has uncovered Phase 197 advisories or blockers, has invalid response artifact hashes, or contains a blocking record that remains open.
