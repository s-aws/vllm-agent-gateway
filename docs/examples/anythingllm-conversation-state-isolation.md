# AnythingLLM Conversation State Isolation Examples

Run the full Phase 152 gate:

```bash
export ANYTHINGLLM_API_KEY="${ANYTHINGLLM_API_KEY:?set AnythingLLM API key first}"

python3 scripts/validate_anythingllm_conversation_state_isolation.py \
  --model-base-url http://127.0.0.1:8000/v1 \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --anythingllm-api-base-url http://127.0.0.1:3001 \
  --workspace my-workspace \
  --output-path runtime-state/anythingllm-conversation-state-isolation/phase152/phase152-anythingllm-conversation-state-isolation-report.json \
  --markdown-output-path runtime-state/anythingllm-conversation-state-isolation/phase152/phase152-anythingllm-conversation-state-isolation-report.md
```

Run a focused single-fixture probe:

```bash
python3 scripts/validate_anythingllm_conversation_state_isolation.py \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --output-path runtime-state/anythingllm-conversation-state-isolation/manual/phase152-github-only.json \
  --markdown-output-path runtime-state/anythingllm-conversation-state-isolation/manual/phase152-github-only.md
```

The full report should cover:

```json
{
  "surfaces": [
    "anythingllm_same_session",
    "direct_controller_history",
    "gateway_history_payload"
  ],
  "case_ids": ["ISO-001", "ISO-002", "ISO-003", "ISO-004"],
  "target_roots": [
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github"
  ]
}
```

The gate intentionally reuses an AnythingLLM `sessionId` for each case:

1. Seed the session with stale content.
2. Send the current prompt in the same session.
3. Send the same current prompt in a fresh session.
4. Compare route signatures and output-format behavior.

The current prompt must win every time.
