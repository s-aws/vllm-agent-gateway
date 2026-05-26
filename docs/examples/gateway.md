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

Use Claude Code against a role prompt proxy. Anthropic-compatible clients usually want the base URL without `/v1`:

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8205
claude -p --bare --tools "Read,Grep,Glob" \
  --model Qwen/Qwen3-Coder-30B-A3B-Instruct \
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
8000 vLLM upstream
```
