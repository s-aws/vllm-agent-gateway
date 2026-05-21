# vLLM Agent Gateway

`vllm-agent-gateway` is a small local runtime for putting stricter controls between agent clients and a vLLM-hosted model.

It provides:

- role-specific prompt proxy ports
- tiny role/subrole prompt files
- a budget gateway that counts input tokens and clamps output tokens
- fail-closed rejection for oversized requests
- Linux-first startup and stop scripts
- a JSON role manifest for ports, prompts, budgets, and client policy

The current implementation is intentionally conservative. It does not silently summarize, trim, or rewrite agent context. Oversized requests are rejected so the caller has to delegate a smaller task or explicitly reduce context.

## Tested Setup

This repository is currently tested on:

- Ubuntu 24.04/Linux runtime
- NVIDIA RTX 6000 PRO 96 GB
- NVIDIA vLLM Docker container: `nvcr.io/nvidia/vllm:26.01-py3`
- Model: `Qwen/Qwen3-Coder-30B-A3B-Instruct`
- vLLM OpenAI-compatible server on `http://127.0.0.1:8000/v1`
- Python 3 and Bash
- Claude Code as one tested client, using `--bare` for lower request overhead

The scripts are Linux-first. Host-specific wrappers, private notes, logs, PID files, and local experiments should live outside this public repo, typically in a sibling `private_agentic_agents` directory.

## Architecture

```text
client -> role prompt proxy -> llm_gateway.py -> vLLM
```

Default ports:

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

Role endpoints are loaded from `runtime/roles.json`. Add or remove role ports in the manifest, not in the startup script.

## Start

Start vLLM separately, then run:

```bash
bash start-agent-prompt-proxies.sh
```

Stop the gateway and prompt proxy:

```bash
bash stop-agent-prompt-proxies.sh
```

The startup script prints local and network role endpoints generated from `runtime/roles.json`.

## Gateway Defaults

```text
MODEL_LIMIT=65536
TARGET_INPUT_LIMIT=24000
SAFETY_BUFFER=1000
DEFAULT_MAX_OUTPUT=4000
MIN_AVAILABLE_OUTPUT=512
```

Routing defaults:

```text
VLLM_BASE_URL=http://127.0.0.1:8000
GATEWAY_BIND_HOST=127.0.0.1
GATEWAY_PORT=8300
GATEWAY_CONNECT_HOST=<normalized GATEWAY_BIND_HOST>
GATEWAY_BASE_URL=http://$GATEWAY_CONNECT_HOST:8300
TARGET_BASE_URL=$GATEWAY_BASE_URL
HOST_ADDRESS=0.0.0.0
```

Example override:

```bash
TARGET_INPUT_LIMIT=18000 DEFAULT_MAX_OUTPUT=3000 bash start-agent-prompt-proxies.sh
```

## Client Notes

Anthropic-compatible clients such as Claude Code usually want the base URL without `/v1`:

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8205
claude -p --bare --tools "Read,Grep,Glob" --model Qwen/Qwen3-Coder-30B-A3B-Instruct "What is your role name?"
```

OpenAI-compatible clients usually want `/v1`:

```text
http://127.0.0.1:8205/v1
```

For details on the verified vLLM launch command, gateway behavior, and Claude Code tool restrictions, see `VLLM_AGENT_HOST.md`.

## Repository Layout

```text
roles/                    role and subrole prompt files
runtime/roles.json         active role manifest
agent_prompt_proxy.py      OpenAI/Anthropic-compatible role prompt proxy
llm_gateway.py             token budget and forwarding gateway
start-agent-prompt-proxies.sh
stop-agent-prompt-proxies.sh
VLLM_AGENT_HOST.md         setup and operating notes
```
