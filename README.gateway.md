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
8500 workflow-router gateway
8400 controller service
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
WORKFLOW_ROUTER_GATEWAY_ENABLED=1
WORKFLOW_ROUTER_GATEWAY_PORT=8500
WORKFLOW_ROUTER_GATEWAY_BASE_URL=http://127.0.0.1:8500
WORKFLOW_ROUTER_CONTROLLER_URL=http://$CONTROLLER_CONNECT_HOST:$CONTROLLER_PORT/v1/controller/workflow-router/chat/completions
TARGET_BASE_URL=$GATEWAY_BASE_URL
HOST_ADDRESS=0.0.0.0
CONTROLLER_BIND_HOST=127.0.0.1
CONTROLLER_PORT=8400
CONTROLLER_CONNECT_HOST=<normalized CONTROLLER_BIND_HOST>
GATEWAY_CONTROLLER_ROUTING=explicit_envelope
GATEWAY_CONTROLLER_HARNESS_URL=http://$CONTROLLER_CONNECT_HOST:$CONTROLLER_PORT/v1/controller/harness/chat/completions
CONTROLLER_OUTPUT_ROOT=<private runtime state>/controller-artifacts
CONTROLLER_ALLOWED_TARGET_ROOTS=<repo root>
```

The gateway counts input tokens with vLLM `/tokenize` when possible, rejects inputs above the target budget, and clamps requested output tokens based on remaining context.

## Controller-Aware Routing

Use the normal OpenAI-compatible gateway base URL for ordinary model chat and explicit `agentic_controller_request` envelopes:

```text
http://127.0.0.1:8300/v1
```

Use the workflow-router gateway base URL for natural-language workflow requests that should be routed by `workflow_router.plan` without a JSON envelope:

```text
http://127.0.0.1:8500/v1
```

If a client is configured with `http://127.0.0.1:8300` and appends `/chat/completions` without `/v1`, the gateway accepts that alias and forwards it to the upstream `/v1/chat/completions` route.

Normal chat should continue to flow through the gateway to the model. Explicit workflow requests that contain exactly one `agentic_controller_request` envelope should route from the gateway to the controller harness endpoint instead of being forwarded to the model as plain text.

The `8500` workflow-router gateway is intentionally separate. Its `/v1/chat/completions` route forwards normal chat payloads to `/v1/controller/workflow-router/chat/completions`; ordinary model chat should not use this port.

For message-content envelopes, the active request is only the latest chat message. Older controller-envelope messages in AnythingLLM history must not route a later normal chat prompt to the controller. If the latest message contains one envelope it routes; if it contains none it forwards as normal model chat. Top-level plus active-message ambiguity and multiple envelopes inside the active message are still rejected.

The full startup script enables this route with `GATEWAY_CONTROLLER_ROUTING=explicit_envelope`. A standalone gateway defaults to `off`, which rejects controller envelopes instead of forwarding them to the model. See [docs/GATEWAY_CONTROLLER_ROUTING_PLAN.md](docs/GATEWAY_CONTROLLER_ROUTING_PLAN.md).

The explicit-envelope route has been live-validated from Bash through direct gateway calls and through the AnythingLLM workspace API against both frozen validation repos in `dry_run` mode. The natural workflow-router route has been live-validated from Bash and AnythingLLM through `http://127.0.0.1:8500/v1` against both frozen validation repos. `8400` is the controller service endpoint, not an OpenAI-compatible client base URL.

## Client Notes

Anthropic-compatible clients such as Claude Code usually want the base URL without `/v1`.

OpenAI-compatible clients usually want `/v1`.

Claude Code was tested with `--bare` because it reduces fixed request overhead substantially.

## Setup Details

For the verified vLLM launch command, gateway behavior, and Claude Code notes, see [VLLM_AGENT_HOST.md](VLLM_AGENT_HOST.md).

Examples: [docs/examples/gateway.md](docs/examples/gateway.md).

Controller service details: [README.controller-service.md](README.controller-service.md).
