# AnythingLLM Session Recovery

Phase 140 validates that basic greetings through the workflow-router path do not trigger repository workflows.

This covers the founder-facing case where typing `hi` in AnythingLLM should return a bounded helpful response instead of timing out or trying to run code investigation.

## What It Checks

- direct workflow-router chat handles `hi`
- stale prior repository history is ignored when the latest message is `hi`
- live AnythingLLM workspace chat handles `hi`
- live AnythingLLM same-session follow-up handles `hello there`
- greeting responses include `general_chat_no_target`
- greeting responses show `Selected workflow: none`
- greeting responses do not include repository workflow markers or artifact sections

## Command

```bash
python3 scripts/validate_anythingllm_session_recovery.py \
  --anythingllm-api-base-url http://127.0.0.1:3001 \
  --workspace my-workspace \
  --timeout-seconds 120 \
  --output-path runtime-state/anythingllm-session-recovery/phase140/phase140-anythingllm-session-recovery-report.json
```

Expected result:

```text
ANYTHINGLLM SESSION RECOVERY PASS
```

## Artifact

- `runtime-state/anythingllm-session-recovery/phase140/phase140-anythingllm-session-recovery-report.json`

`runtime-state` is local-only and should not be committed.
