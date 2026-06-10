# Founder Feedback Triage Dashboard

The founder feedback triage dashboard is a read-only report that consolidates feedback records, smoke feedback classifications, closure state, roadmap references, and next actions.

It does not create new feedback records. It summarizes existing governed inputs:

- Phase 125 founder feedback loop report
- Phase 135 founder smoke feedback classification
- Phase 131 stable release blocker closure report

## When To Use

Run this dashboard when:

- preparing founder-review or release-candidate status
- checking whether accepted feedback still blocks release
- reviewing whether a smoke-suite miss created actionable work
- handing a contextless agent the current feedback state

## Contract

The dashboard fails if:

- a feedback decision lacks a `target_run_id`
- a feedback decision lacks a `feedback_run_id`
- a feedback record run ID does not match the governed decision
- accepted feedback has no closure record
- a closure record does not resolve the release blocker
- a closure required gate does not match the decision required gate
- smoke feedback classifications disagree with the smoke summary
- report summaries are edited instead of rebuilt from source artifacts

## Validation

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_founder_feedback_triage_dashboard.py \
  --require-artifacts \
  --output-path runtime-state/founder-feedback-triage-dashboard/phase145/phase145-founder-feedback-triage-dashboard.json
```

Expected clean result:

```text
FOUNDER FEEDBACK TRIAGE PASS
```

The report is written under `runtime-state/founder-feedback-triage-dashboard/` and is local-only.
