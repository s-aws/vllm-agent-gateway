# Gateway Examples

Start vLLM separately, then run:

```bash
bash start-agent-prompt-proxies.sh
```

Stop the gateway and prompt proxies:

```bash
bash stop-agent-prompt-proxies.sh
```

Override gateway budget defaults:

```bash
TARGET_INPUT_LIMIT=18000 DEFAULT_MAX_OUTPUT=3000 bash start-agent-prompt-proxies.sh
```

Enable or disable controller-envelope routing:

```bash
GATEWAY_CONTROLLER_ROUTING=explicit_envelope bash start-agent-prompt-proxies.sh
GATEWAY_CONTROLLER_ROUTING=off bash start-agent-prompt-proxies.sh
```

When the full stack is started normally, AnythingLLM can use:

```text
http://127.0.0.1:8300/v1
```

Clients configured as `http://127.0.0.1:8300` are also accepted when they call `/chat/completions`; the gateway aliases that path to `/v1/chat/completions`.

Ordinary chat goes to the model. A request containing exactly one `agentic_controller_request` routes to:

```text
http://127.0.0.1:8400/v1/controller/harness/chat/completions
```

Minimal routed-controller probe:

```bash
curl -s http://127.0.0.1:8300/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"agentic-controller","messages":[{"role":"user","content":"{\"agentic_controller_request\":{\"workflow\":\"execution_planning.plan\",\"schema_version\":1,\"target_root\":\"/mnt/c/coinbase_testing_repo_frozen_tmp\",\"user_request\":\"Create a read-only investigation plan for the frozen repo invariant file.\",\"mode\":\"investigation_only\",\"context\":{\"entrypoint_hints\":[{\"path\":\"docs/agents/INVARIANTS.md\",\"symbol\":null,\"reason\":\"Frozen validation entrypoint.\"}],\"allowed_context_tools\":[\"structure_index\",\"git_grep\",\"read_file\",\"manual\"]},\"budgets\":{\"max_context_requests\":3,\"max_files\":5,\"max_records\":25,\"max_model_calls\":8,\"max_output_tokens\":3600}}}"}]}'
```

Repeat the full routed validation against both frozen fixtures and AnythingLLM:

```bash
cd /mnt/c/agentic_agents
WSLENV=ANYTHINGLLM_API_KEY python3 scripts/validate_gateway_controller_route.py --timeout-seconds 900
```

Use `--skip-anythingllm` to validate only the direct gateway route.

Run the full live execution-planning matrix, including port smoke, direct gateway dry runs, AnythingLLM dry runs, and disposable-copy mutation probes:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="${ANYTHINGLLM_API_KEY:?set AnythingLLM API key first}"
PYTHONUNBUFFERED=1 python3 scripts/validate_live_execution_planning_matrix.py --mode dry_run --timeout-seconds 900
```

Use Claude Code against a role prompt proxy. Anthropic-compatible clients usually want the base URL without `/v1`:

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8205
claude -p --bare --tools "Read,Grep,Glob" \
  --model Qwen3-Coder-30B-A3B-Instruct \
  "What is your role name?"
```

OpenAI-compatible clients usually want `/v1`:

```text
http://127.0.0.1:8205/v1
```

Default local endpoints:

```text
8101 reviewer/code
8102 tester/code
8201 architect/default
8202 dispatcher/default
8203 implementer/default
8204 researcher/default
8205 documenter/default
8300 LLM gateway
8400 controller service
8000 vLLM upstream
```
