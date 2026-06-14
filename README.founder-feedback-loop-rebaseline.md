# Founder Feedback Loop Rebaseline

Phase 227 revalidates founder feedback classification after the large-context strategy matrix closeout.

Use this when current chat behavior needs feedback classification into deterministic outcomes:

- `baseline_prompt_candidate`
- `holdout_prompt_candidate`
- `repair_followup`
- `rejected_finding`
- `advisory_finding`
- `deferred_finding`

The rebaseline uses the existing `workflow_feedback.record` governance path. It does not add a second feedback database, issue tracker, or workflow status system.

## Validation

Offline catalog check:

```bash
python3 scripts/validate_founder_feedback_loop_rebaseline.py
```

Live gateway and AnythingLLM feedback run:

```bash
python3 scripts/validate_founder_feedback_loop_live.py \
  --cases-path runtime/founder_feedback_loop_phase227_cases.json \
  --output-path runtime-state/founder-feedback-loop/phase227/phase227-founder-feedback-loop-live.json \
  --timeout-seconds 900
```

Live report gate:

```bash
python3 scripts/validate_founder_feedback_loop_rebaseline.py --require-live-report
```

Examples: [docs/examples/founder-feedback-loop-rebaseline.md](docs/examples/founder-feedback-loop-rebaseline.md)
