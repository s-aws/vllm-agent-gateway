# Gateway

The gateway path is:

```text
client -> role prompt proxy -> gateway server -> vLLM
```

The gateway is responsible for transport and budget enforcement. Workflow control belongs in controllers such as the documenter orchestrator, streaming runner, structure indexer, and implementation workflow.

## Runtime Pieces

- `vllm_agent_gateway/gateway/prompt_proxy.py`: role-specific OpenAI/Anthropic-compatible prompt proxy.
- `vllm_agent_gateway/gateway/server.py`: token budget and forwarding gateway.
- `runtime/roles.json`: role IDs, ports, prompt files, expected role names, budgets, and client policy.
- `runtime/tools.json`: controller/tool mediator tool catalog.
- `roles/<role>/<subrole>.md`: small role prompt files.

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

The gateway counts input tokens with vLLM `/tokenize` when possible, rejects inputs above the target budget, and clamps requested output tokens based on remaining context.

## Client Notes

Anthropic-compatible clients such as Claude Code usually want the base URL without `/v1`.

OpenAI-compatible clients usually want `/v1`.

Claude Code was tested with `--bare` because it reduces fixed request overhead substantially.

## Setup Details

For the verified vLLM launch command, gateway behavior, and Claude Code notes, see [VLLM_AGENT_HOST.md](VLLM_AGENT_HOST.md).

Examples: [docs/examples/gateway.md](docs/examples/gateway.md).
