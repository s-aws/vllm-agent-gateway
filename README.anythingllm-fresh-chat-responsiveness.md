# AnythingLLM Fresh Chat Responsiveness

Phase 237 proves the first tester path for AnythingLLM is responsive, including the user-facing `hi` case.

The gate checks the configured AnythingLLM target, direct workflow-router gateway chat, AnythingLLM workspace chat, browser-visible `/stream-chat` proof, and protected fixture state.

## What It Checks

- AnythingLLM system settings use the workflow-router gateway with `Qwen3-Coder-30B-A3B-Instruct`.
- Bash-side validation can use `http://127.0.0.1:8500/v1` while Windows AnythingLLM can use the WSL network URL printed by `start-agent-prompt-proxies.sh`.
- Direct workflow-router gateway handles `hi`.
- AnythingLLM API handles `hi` in a fresh session.
- Direct workflow-router gateway handles the representative read-only code explanation prompt.
- AnythingLLM API handles the same code explanation prompt in a fresh session.
- AnythingLLM Desktop UI shows a browser-visible response for the governed `UI167-GENCHAT-001` `hi` case.
- Protected frozen fixtures remain unchanged.

## Commands

Run the UI `hi` proof first:

```bash
python3 scripts/validate_anythingllm_ui_e2e.py \
  --case-id UI167-GENCHAT-001 \
  --output-path runtime-state/anythingllm-ui/phase237/phase237-ui-hi.json \
  --timeout-seconds 240
```

Then run the aggregate gate:

```bash
python3 scripts/validate_anythingllm_fresh_chat_responsiveness.py \
  --ui-report-path runtime-state/anythingllm-ui/phase237/phase237-ui-hi.json \
  --output-path runtime-state/anythingllm-fresh-chat-responsiveness/phase237/phase237-anythingllm-fresh-chat-responsiveness-report.json \
  --timeout-seconds 180
```

When AnythingLLM uses a network API base because Windows `127.0.0.1:3001` reaches the wrong process, and its Generic OpenAI target is the WSL network workflow-router URL because Windows `127.0.0.1` forwarding hangs before body bytes, keep the internal Bash gateway URL unchanged and pass both split-address values:

```bash
python3 scripts/validate_anythingllm_fresh_chat_responsiveness.py \
  --anythingllm-api-base-url http://192.168.0.208:3001 \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --anythingllm-workflow-router-base-url http://100.100.12.45:8500/v1 \
  --ui-report-path runtime-state/anythingllm-ui/phase237/phase237-ui-hi.json \
  --output-path runtime-state/anythingllm-fresh-chat-responsiveness/phase237/phase237-anythingllm-fresh-chat-responsiveness-report.json \
  --timeout-seconds 180
```

Expected result:

```text
ANYTHINGLLM FRESH CHAT RESPONSIVENESS PASS
```

## Failure Meaning

- Target settings fail: AnythingLLM is not pointed at the expected workflow-router gateway URL for the current client surface.
- API base settings fail: pass the working AnythingLLM API base with `--anythingllm-api-base-url`; the report keeps the policy default as `target_settings.required.policy_api_base_url` for audit.
- Gateway cases fail: the controller/gateway path is not returning chat-visible content.
- AnythingLLM API cases fail: AnythingLLM cannot reach or render the workflow-router response through its workspace API.
- UI proof fails: the browser-visible `/stream-chat` path is not usable even if the API path works.
- Fixture state changes: stop and inspect the protected fixture before rerunning.

Examples: [docs/examples/anythingllm-fresh-chat-responsiveness.md](docs/examples/anythingllm-fresh-chat-responsiveness.md).
