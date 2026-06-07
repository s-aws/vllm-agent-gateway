# Context Retrieval Upgrade Examples

## Direct Validator

```bash
python3 scripts/validate_context_retrieval_upgrade.py
```

Expected result:

```text
CONTEXT RETRIEVAL UPGRADE PASS
```

## Live Gateway Validator

Start the Bash-hosted stack first:

```bash
CONTROLLER_ALLOWED_TARGET_ROOTS="/mnt/c/agentic_agents:/mnt/c/coinbase_testing_repo_frozen_tmp:/mnt/c/coinbase_testing_repo_frozen_tmp.github" \
  ./start-agent-prompt-proxies.sh
```

Then run:

```bash
python3 scripts/validate_context_retrieval_upgrade.py \
  --live-gateway \
  --port-health \
  --output-path runtime-state/context-retrieval-upgrade/phase95-context-retrieval-gateway.json
```

This validates localhost `8000`, ordinary gateway `8300`, workflow-router gateway `8500`, controller `8400`, role ports, both frozen Coinbase fixtures, and a generated non-Coinbase fixture.

## AnythingLLM Validator

AnythingLLM should point at:

```text
http://127.0.0.1:8500/v1
```

Run:

```bash
python3 scripts/validate_context_retrieval_upgrade.py \
  --skip-direct \
  --live-anythingllm \
  --output-path runtime-state/context-retrieval-upgrade/phase95-context-retrieval-anythingllm.json
```

If Bash can see `ANYTHINGLLM_API_KEY` as a shell variable but Python cannot, export or bridge it before running the validator.

## Manual Prompt

Paste this into AnythingLLM:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find where the placed_order_id stealth lookup begins. Read only. Return the entrypoint, evidence files, related tests, and confidence.
```

Expected chat-visible markers:

- `Context Sources:`
- `ast_index`
- `text_search`
- `test_lookup`
- `route_decision.context_source_audit`
