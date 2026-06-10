# Founder Feedback Loop

Founder feedback loop governance turns natural tester feedback into reviewable Priority 0 follow-up decisions.

It builds on `workflow_feedback.record`. It does not replace that workflow and does not mutate stable baseline corpora automatically.

## What It Produces

The Phase 125 gate classifies feedback records into one of four governed decisions:

- `baseline_prompt_candidate`: feedback should become a candidate stable baseline prompt.
- `holdout_prompt_candidate`: feedback should become a candidate holdout prompt so repairs do not overfit.
- `repair_followup`: feedback indicates a miss that needs eval-repair or another gated repair path.
- `rejected_finding`: feedback is useful-only or not actionable as a defect, so no repair work is created.

Each decision records:

- source prompt case ID
- target run ID
- feedback run ID
- feedback classification
- gap class
- accepted or rejected decision status
- validation result or required follow-up gate
- `controller_artifacts_only` mutation policy

## Validation

Run the live gate from Bash:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_founder_feedback_loop_live.py \
  --output-path runtime-state/founder-feedback-loop/phase125-founder-feedback-loop-live.json \
  --timeout-seconds 900
```

This requires:

- localhost model on `8000`
- controller/gateway/proxy ports running
- AnythingLLM available at `http://127.0.0.1:3001`
- `ANYTHINGLLM_API_KEY` in the Bash environment
- both frozen Coinbase fixtures present

Expected clean result:

```text
FOUNDER FEEDBACK LOOP REPORT PASSED
```

The report is local-only under `runtime-state/founder-feedback-loop/`.

## Safety

- Uses existing natural `workflow_feedback.record` routing.
- Writes only controller artifacts and local validation reports.
- Does not edit target repositories.
- Does not automatically add prompt cases to the stable baseline or holdout corpus.
- Accepted candidate decisions must still pass their downstream gates before promotion.
