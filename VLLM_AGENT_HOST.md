# vLLM Agent Host Notes

The current verified endpoint is:

```text
http://127.0.0.1:8000/v1
```

The served model name is:

```text
Qwen/Qwen3-Coder-30B-A3B-Instruct
```

Start vLLM with the equivalent local Docker command for your host. Host-specific launchers, if used, belong in `private_agentic_agents`.

```bash
docker run -d --name vllm-qwen3-coder --gpus all --ipc=host -p 8000:8000 \
  -v /path/to/models:/models \
  nvcr.io/nvidia/vllm:26.01-py3 \
  vllm serve /models/Qwen3-Coder-30B-A3B-Instruct \
    --served-model-name Qwen/Qwen3-Coder-30B-A3B-Instruct \
    --host 0.0.0.0 \
    --port 8000 \
    --gpu-memory-utilization 0.95 \
    --max-model-len 65536 \
    --max-num-seqs 4 \
    --enable-prefix-caching \
    --enable-auto-tool-choice \
    --tool-call-parser qwen3_coder \
    --generation-config vllm \
    --override-generation-config.temperature 0.0 \
    --override-generation-config.top_p 1.0 \
    --override-generation-config.repetition_penalty 1.0
```

Important server settings:

- `--generation-config vllm` prevents the model's Hugging Face generation defaults from applying.
- `--override-generation-config.temperature 0.0` makes clients deterministic when they omit temperature.
- `--override-generation-config.top_p 1.0` avoids extra nucleus sampling.
- `--override-generation-config.repetition_penalty 1.0` avoids server-side output distortion for code.
- `--enable-auto-tool-choice --tool-call-parser qwen3_coder` keeps OpenAI-style tool calls working.
- Do not use `--reasoning-parser qwen3` with this Qwen3-Coder setup unless tool calls are retested. It caused raw `<tool_call>` output to fail OpenAI tool-call validation.
- `--max-model-len 65536` exposes a 65k token context window.
- `--max-num-seqs 4` keeps concurrency below the measured full-context KV capacity.

Verified smoke tests after the restart:

- Chat Completions obeyed a hard system instruction with no explicit temperature in the request.
- Responses API obeyed the same hard system instruction with no explicit temperature in the request.
- Chat Completions returned a valid OpenAI `tool_calls` object for a required `delegate_task` function.

Client settings to prefer:

- Base URL: `http://127.0.0.1:8000/v1`
- API key: any non-empty dummy value if the client requires one.
- Model: `Qwen/Qwen3-Coder-30B-A3B-Instruct`
- Temperature: `0` or omitted, since the server now defaults to `0`.
- Max output tokens: do not set tiny limits. Use at least `4096` for coding agents and `8192` or higher for large edits/reviews.
- Context/task budget: cap delegated sub-agent work well below server context and require the delegator to split work before dispatch. For Claude Code subagents, use `--bare` and a minimal tool set so Claude Code's native system/tool overhead does not consume the whole gateway budget.

The vLLM server can improve instruction adherence only up to the transport and decoding layer. Reliable delegation still requires the client/orchestrator to enforce bounded task packets, explicit acceptance criteria, verification commands, and result schemas.

Private local roadmap and notes live outside the public repo under sibling directory `private_agentic_agents`.

## LLM Gateway

The Linux startup script runs a strict budget gateway between the role prompt proxies and vLLM:

```text
client -> role prompt proxy -> llm_gateway.py:8300 -> vLLM:8000
```

The gateway does not summarize, trim, or chunk automatically. Version 1 fails closed:

- counts input tokens with vLLM's `/tokenize` endpoint when possible
- enforces `TARGET_INPUT_LIMIT`
- computes remaining safe output from `MODEL_LIMIT - input_tokens - SAFETY_BUFFER`
- clamps the request's output token field to the lower of client request, available output, and `DEFAULT_MAX_OUTPUT`
- rejects over-budget token requests with HTTP `422` and a structured JSON error
- forwards only the budgeted request to vLLM

Default gateway budget:

```text
MODEL_LIMIT=65536
TARGET_INPUT_LIMIT=24000
SAFETY_BUFFER=1000
DEFAULT_MAX_OUTPUT=4000
MIN_AVAILABLE_OUTPUT=512
```

Gateway routing defaults:

```text
VLLM_BASE_URL=http://127.0.0.1:8000
GATEWAY_BIND_HOST=127.0.0.1
GATEWAY_PORT=8300
GATEWAY_CONNECT_HOST=<normalized GATEWAY_BIND_HOST>
GATEWAY_BASE_URL=http://$GATEWAY_CONNECT_HOST:8300
TARGET_BASE_URL=$GATEWAY_BASE_URL
```

`VLLM_BASE_URL` is the upstream vLLM server and may be local or remote. `GATEWAY_BIND_HOST` is only the gateway listener address. The startup script derives `GATEWAY_CONNECT_HOST` from `GATEWAY_BIND_HOST`, normalizing wildcard binds such as `0.0.0.0` to `127.0.0.1` for local proxy-to-gateway calls. Override `GATEWAY_CONNECT_HOST`, `GATEWAY_BASE_URL`, or `TARGET_BASE_URL` only when the prompt proxy must reach the gateway through a different hostname.

Override these for a Linux launch by prefixing the start command:

```bash
TARGET_INPUT_LIMIT=18000 DEFAULT_MAX_OUTPUT=3000 bash start-agent-prompt-proxies.sh
```

Gateway diagnostics:

```text
http://127.0.0.1:8300/__gateway/health
```

Gateway budget logs are content-free. They record route, byte count, token count, token-count source, and forward/reject decision, but not prompt text. By default, logs and PID files are written under `private_agentic_agents/runtime-state`.

Claude Code may send more than 35k tokens for a tiny prompt inside a repo because its own system prompt, tools, project context, and agent configuration are part of the request. Use Claude Code's `--bare` mode for gateway-managed subagents, and specify the smallest useful tool set:

```bash
ANTHROPIC_BASE_URL=http://127.0.0.1:8205 \
claude -p --bare --tools "Read,Grep,Glob" --model Qwen/Qwen3-Coder-30B-A3B-Instruct \
  "What is your role name?"
```

In a repo smoke test, this reduced a Claude Code role request from about `37830` input tokens to about `1310` input tokens.

For agents that need write or test capability, add only the required tools instead of using Claude Code's full default tool surface:

```bash
claude -p --bare --tools "Read,Grep,Glob,Edit,Bash" --model Qwen/Qwen3-Coder-30B-A3B-Instruct "..."
```

`--tools` names Claude Code built-in tools. It does not create new tools. For example, `--tools "git_ls_files"` is only a model-visible word and can lead to invented tool use. Use a real built-in tool plus a permission restriction:

```bash
ANTHROPIC_BASE_URL=http://127.0.0.1:8205 \
ANTHROPIC_API_KEY=dummy \
claude --bare -p \
  --tools Bash \
  --allowedTools 'Bash(git ls-files*)' \
  --model Qwen/Qwen3-Coder-30B-A3B-Instruct \
  'Provide a list of the first 20 tracked markdown files and provide the exact tool used. Do not invent files.'
```

Verified result shape:

```text
Tool used: git ls-files "*.md"
```

Gateway budget logs include content-free tool schema diagnostics:

```text
tool_count=0 tool_names=-
tool_count=1 tool_names=Bash
```

In testing, `claude --bare -p --tools git_ls_files ...` produced `tool_count=0` and the model emitted raw tool-call-shaped JSON. That means `git_ls_files` was not an executable Claude Code tool schema in the request. The restricted Bash pattern produced `tool_count=1 tool_names=Bash` and returned real `git ls-files` output.

## Controller Demo

`scripts/run_documenter_orchestrator.py` is the first controller example. It is deliberately smaller than a general orchestrator:

- loads `runtime/roles.json` and `runtime/tools.json`
- checks the `documenter/default` role has the required controller tools
- discovers tracked documentation files with `git ls-files`
- reads one selected doc file
- chunks it deterministically
- overlaps chunks by line count for local continuity
- sends one bounded packet at a time to the documenter role endpoint
- validates the returned JSON delta
- writes a local ignored report under `.agentic_reports/`

Dry run without calling the model:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --doc README.md --dry-run
```

Run the full workflow against the local role endpoint:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --doc README.md --mode full
```

Quick one-chunk smoke run:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --doc README.md --mode review --max-chunks 1
```

Default chunk overlap is `--chunk-overlap-lines 8`.

Summarize an existing JSON report:

```bash
python scripts/run_documenter_orchestrator.py --mode summarize --report .agentic_reports/example.json
```

Run against another target repo while keeping this repo as the config root:

```bash
python /path/to/vllm-agent-gateway/scripts/run_documenter_orchestrator.py \
  --config-root /path/to/vllm-agent-gateway \
  --target-root /path/to/project \
  --doc README.md
```

The controller is stateful. The documenter role is packet-bound and should not choose files, maintain repo-wide manifests, or decide the next chunk. In `full` mode, the controller aggregates chunk deltas and sends only that aggregate back for the final Markdown summary. By default, reports are written under `.agentic_reports/` in the config root, not the target repo.

## Role Prompt Proxies

Use these OpenAI-compatible proxy base URLs when a client should receive a tiny role-specific system instruction before the gateway and vLLM see the request. The startup script prints this list from `runtime/roles.json`.

```text
http://127.0.0.1:8101/v1  reviewer/code        roles/reviewer/code.md
http://127.0.0.1:8102/v1  tester/code          roles/tester/code.md
http://127.0.0.1:8201/v1  architect/default    roles/architect/default.md
http://127.0.0.1:8202/v1  dispatcher/default   roles/dispatcher/default.md
http://127.0.0.1:8203/v1  implementer/default  roles/implementer/default.md
http://127.0.0.1:8204/v1  researcher/default   roles/researcher/default.md
http://127.0.0.1:8205/v1  documenter/default   roles/documenter/default.md
```

Role endpoints are loaded from `runtime/roles.json`. Edit the canonical `roles/<role>/<subrole>.md` files for active behavior. Add or remove role ports in the manifest, not in the startup script.

Ubuntu 24.04/Linux is the canonical runtime.

From the public repo:

```bash
bash start-agent-prompt-proxies.sh
```

Stop the proxies:

```bash
bash stop-agent-prompt-proxies.sh
```

Local Linux clients can use `http://127.0.0.1:<port>/v1`. Network clients should use the host IP endpoint list printed by the start script.

Anthropic-compatible clients such as Claude Code usually want the base URL without `/v1` because they append `/v1/messages` themselves:

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8102
claude --model Qwen/Qwen3-Coder-30B-A3B-Instruct
```

OpenAI-compatible clients usually want `/v1` in the base URL:

```text
http://127.0.0.1:8102/v1
```

Check the host IP for network clients with:

```bash
hostname -I
```

The proxy injects `boot-strap-agents.md` plus the matching role markdown file on every request, so edits take effect without restarting. It injects into `/v1/chat/completions`, `/v1/responses`, `/v1/completions`, and `/v1/messages`; other routes pass through to vLLM. For Anthropic `/v1/messages`, the proxy appends the injected instructions after the client-provided `system` prompt and also appends them to the last user message. This is deliberate: Claude Code sends strong identity text, and `system`-only injection was not reliable enough.

The proxy handles Claude Code's `HEAD /` health probe locally. Anthropic `/v1/messages/count_tokens` requests are role-injected and forwarded to the gateway so the count reflects the same injected request shape that will be sent for generation.

Debug request logging is disabled by default. To temporarily write `/v1/messages` proxy diagnostics to `private_agentic_agents/runtime-state/agent-prompt-proxy.debug.jsonl`, start the proxy with:

```bash
AGENT_PROMPT_PROXY_DEBUG=1 bash start-agent-prompt-proxies.sh
```

Proxy diagnostics:

```text
http://127.0.0.1:8202/__proxy/health
http://127.0.0.1:8202/__proxy/prompt
```
