# vLLM Agent Gateway

`vllm-agent-gateway` is a small local runtime for putting stricter controls between agent clients and a vLLM-hosted model.

It provides:

- role-specific prompt proxy ports
- tiny role/subrole prompt files
- a budget gateway that counts input tokens and clamps output tokens
- fail-closed rejection for oversized requests
- a tool catalog used by controllers/runners to authorize deterministic actions
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

## Documenter Orchestrator Demo

The first controller example is intentionally narrow: it reviews a seed documentation file with the `documenter/default` role. It can optionally expand to exact tracked follow-up files reported by the documenter, but the controller owns that decision.

```text
controller -> documenter role proxy -> LLM gateway -> vLLM
```

The controller owns repo discovery, file reading, chunking, packet construction, sequencing, validation, and report writing. The documenter role receives one bounded packet and returns one structured JSON delta.

Chunks overlap by default with `--chunk-overlap-lines 8`. This gives the documenter local continuity without making it stateful.

Dry-run packet generation:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --doc README.md --dry-run
```

Run the full workflow against the local documenter role endpoint:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --doc README.md --mode full
```

`full` mode automatically writes a document manifest JSON artifact beside the report. By default the manifest uses tracked files only. For first-run/bootstrap repositories where useful docs may not be tracked yet, scan the target tree:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --doc README.md \
  --mode full \
  --document-scope all
```

The all-files scan skips common generated directories such as `.git`, `.venv`, `node_modules`, build outputs, caches, and `.agentic_reports`.

Quick one-chunk smoke run. `--max-chunks` is applied per reviewed file:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --doc README.md --mode review --max-chunks 1
```

Adjust chunk sizing:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --doc README.md \
  --chunk-token-limit 1200 \
  --chunk-overlap-lines 12
```

Review a different project while using this repo for gateway configuration:

```bash
python /path/to/vllm-agent-gateway/scripts/run_documenter_orchestrator.py \
  --config-root /path/to/vllm-agent-gateway \
  --target-root /path/to/project \
  --doc README.md
```

Bounded follow-up expansion:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --doc README.md \
  --mode full \
  --include-followups \
  --followup-depth 1 \
  --max-followup-files 5
```

Follow-up expansion is fail-closed. The documenter can only return exact file paths visible in the packet, and the controller only queues paths that are tracked by git, use an allowed text/config/code suffix, have not already been seen, and fit within the configured depth/count limits. Accepted and skipped follow-ups are recorded in the JSON report.

The E2E documenter roadmap is tracked in `docs/DOCUMENTER_E2E_ROADMAP.md`. Use it as the control document before adding new documenter workflow behavior.

Modes:

```text
review      write chunk-review JSON only
summarize   summarize an existing JSON report with --report
full        review chunks and write the final Markdown summary
```

Reports are written under `.agentic_reports/` in the config repo by default, which is ignored by git. Full mode writes a JSON report, a document manifest JSON artifact, and a Markdown summary. The target project is read only unless you explicitly point `--output-dir` at it.

## Tool Policy

`runtime/tools.json` is the tool catalog. `runtime/roles.json` assigns tool IDs to each role with `tool_ids`.

In this version, tool IDs authorize deterministic controller behavior. They are not synthetic model tools yet. For example, the documenter orchestrator requires `git_ls_files` and `read_file` before it can discover tracked docs and read selected documents. First-run all-file discovery also requires `scan_files`.

Controller reports include `tool_policy.controller_tool_dependencies` so runs can be audited against the role's assigned `tool_ids`.

Future synthetic tools will need a real execution loop:

```text
tool schema -> model tool call -> local execution -> tool result -> final model answer
```

Prompt text alone is not tool execution.

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
runtime/tools.json         controller/tool mediator catalog
agent_prompt_proxy.py      OpenAI/Anthropic-compatible role prompt proxy
llm_gateway.py             token budget and forwarding gateway
scripts/                   controller and smoke-test helpers
start-agent-prompt-proxies.sh
stop-agent-prompt-proxies.sh
VLLM_AGENT_HOST.md         setup and operating notes
```
