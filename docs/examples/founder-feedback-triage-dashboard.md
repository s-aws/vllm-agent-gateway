# Founder Feedback Triage Dashboard Examples

## Build The Dashboard

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_founder_feedback_triage_dashboard.py \
  --require-artifacts \
  --output-path runtime-state/founder-feedback-triage-dashboard/phase145/phase145-founder-feedback-triage-dashboard.json
```

## Review The Result

Open:

```text
runtime-state/founder-feedback-triage-dashboard/phase145/phase145-founder-feedback-triage-dashboard.json
```

Review these fields:

1. `summary.unresolved_feedback_count`
2. `summary.open_next_action_count`
3. `feedback_records[*].target_run_id`
4. `feedback_records[*].feedback_run_id`
5. `feedback_records[*].decision_kind`
6. `feedback_records[*].closure_status`
7. `feedback_records[*].roadmap_refs`
8. `next_actions`

A clean current release-candidate state should have zero unresolved feedback records and zero open next actions.
