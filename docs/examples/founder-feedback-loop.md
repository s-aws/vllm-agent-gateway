# Founder Feedback Loop Examples

## Full Live Gate

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_founder_feedback_loop_live.py \
  --output-path runtime-state/founder-feedback-loop/phase125-founder-feedback-loop-live.json \
  --timeout-seconds 900
```

The validator seeds real workflow-router runs, records natural feedback through gateway and AnythingLLM, reads the generated `workflow_feedback.record` artifacts, and computes governed follow-up decisions.

## Review The Report

Open:

```text
runtime-state/founder-feedback-loop/phase125-founder-feedback-loop-live.json
```

Review each case in this order:

1. `status`
2. `surface`
3. `target_run_id`
4. `feedback_run_id`
5. `feedback_record.classifications`
6. `decision.kind`
7. `decision.decision_status`
8. `decision.gap_class`
9. `decision.validation_result`
10. `mutation_proof`

## Decision Meanings

```text
baseline_prompt_candidate -> candidate for baseline-corpus governance
holdout_prompt_candidate  -> candidate for holdout prompt bank governance
repair_followup           -> candidate for eval-repair, safety, drift, or formatter follow-up
rejected_finding          -> useful-only or non-actionable feedback; no repair work created
```

Phase 125 records candidates only. Promotion into the baseline corpus, holdout bank, or repair backlog remains a separate gated action.
