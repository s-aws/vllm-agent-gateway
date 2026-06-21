# AnythingLLM Fresh Chat Responsiveness Examples

Use this after the model, controller, gateway/proxies, and AnythingLLM are running.

From Bash/WSL, make the AnythingLLM API key available:

```bash
export ANYTHINGLLM_API_KEY="${ANYTHINGLLM_API_KEY:?set AnythingLLM API key first}"
```

Run the browser-visible `hi` proof:

```bash
python3 scripts/validate_anythingllm_ui_e2e.py \
  --case-id UI167-GENCHAT-001 \
  --output-path runtime-state/anythingllm-ui/phase237/phase237-ui-hi.json \
  --timeout-seconds 240
```

Run the aggregate Phase 237 proof:

```bash
python3 scripts/validate_anythingllm_fresh_chat_responsiveness.py \
  --ui-report-path runtime-state/anythingllm-ui/phase237/phase237-ui-hi.json \
  --output-path runtime-state/anythingllm-fresh-chat-responsiveness/phase237/phase237-anythingllm-fresh-chat-responsiveness-report.json \
  --timeout-seconds 180
```

If the AnythingLLM API is reachable through a network address instead of Windows `127.0.0.1:3001`, and AnythingLLM is using the WSL network workflow-router URL instead of Windows `127.0.0.1`, pass both split-address values:

```bash
python3 scripts/validate_anythingllm_fresh_chat_responsiveness.py \
  --anythingllm-api-base-url http://192.168.0.208:3001 \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --anythingllm-workflow-router-base-url http://100.100.12.45:8500/v1 \
  --ui-report-path runtime-state/anythingllm-ui/phase237/phase237-ui-hi.json \
  --output-path runtime-state/anythingllm-fresh-chat-responsiveness/phase237/phase237-anythingllm-fresh-chat-responsiveness-report.json \
  --timeout-seconds 180
```

Inspect the result:

```bash
python3 -m json.tool runtime-state/anythingllm-fresh-chat-responsiveness/phase237/phase237-anythingllm-fresh-chat-responsiveness-report.json | less
```

Important fields:

- `target_settings.actual.GenericOpenAiBasePath` equivalent is recorded as `target_settings.actual.generic_openai_base_path`.
- `target_settings.required.policy_api_base_url` records the policy default while `target_settings.required.api_base_url` records the API base selected for the current live run.
- `cases[].surface` distinguishes direct `workflow_router_gateway` from `anythingllm_api`.
- `cases[].parsed_run_id` proves the response came through the workflow-router path.
- `ui_report.case_summaries[].stream_chat_seen` proves the browser-visible `/stream-chat` path was exercised.
- `fixture_unchanged` must be `true`.
