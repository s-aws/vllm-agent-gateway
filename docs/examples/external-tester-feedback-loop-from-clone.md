# External Tester Feedback Loop From Clone Examples

Run this from the release-candidate clone path, not from the active workspace:

```bash
cd /tmp/agentic_agents_phase243_remote_clone
bash ./stop-agent-prompt-proxies.sh || true
bash ./start-agent-prompt-proxies.sh
```

Run the two external-tester feedback cases:

```bash
python3 scripts/validate_founder_feedback_loop_live.py \
  --cases-path runtime/external_tester_feedback_loop_from_clone_cases.json \
  --required-decision-kind rejected_finding \
  --required-decision-kind repair_followup \
  --output-path runtime-state/external-tester-feedback-loop-from-clone/phase243/phase243-external-tester-feedback-loop-live.json \
  --timeout-seconds 900
```

Then validate the trace contract:

```bash
python3 scripts/validate_external_tester_feedback_loop_from_clone.py
```

The final report should show `phase244_ready=true` only when both feedback cases pass, the clone source is clean, runtime-state artifacts are ignored, and accepted repair feedback remains open behind rerun requirements.
