# vLLM Agent Gateway

`vllm-agent-gateway` is a Linux-first local runtime for putting stricter controls between agent clients and a vLLM-hosted model.

It provides:

- role-specific prompt proxy ports
- a token-budget gateway that rejects oversized requests and clamps output
- tiny role/subrole prompt files
- a role manifest for ports, prompts, budgets, and client policy
- controller-owned document review, streaming document modes, code structure indexes, and implementation workflow artifacts
- a tool catalog used by controllers and the tool mediator to authorize deterministic actions

The project is intentionally conservative. It does not silently summarize, trim, rewrite, or forward unbounded context. When a request is too large, the gateway or controller rejects it so the caller has to delegate a smaller task or explicitly choose a reduction mode.

## Quick Start

Tested setup:

- Ubuntu 24.04/Linux runtime
- NVIDIA RTX 6000 PRO 96 GB
- NVIDIA vLLM Docker container: `nvcr.io/nvidia/vllm:26.01-py3`
- Model: `Qwen/Qwen3-Coder-30B-A3B-Instruct`
- vLLM OpenAI-compatible server on `http://127.0.0.1:8000/v1`
- Python 3 and Bash
- Claude Code as one tested client, usually with `--bare`

Start vLLM separately, then start the gateway and role prompt proxies:

```bash
bash start-agent-prompt-proxies.sh
```

Stop them:

```bash
bash stop-agent-prompt-proxies.sh
```

Run regression tests:

```bash
pytest tests/regression/ -v
```

## Basic Usage

Run a one-chunk documenter dry run:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --doc README.md --dry-run --max-chunks 1
```

Run a source-presence check without vLLM:

```bash
python scripts/run_streaming_documenter.py --target-root . --doc README.md \
  --mode context_presence \
  --query "runtime ports"
```

Build a deterministic structure index:

```bash
python scripts/run_code_structure_index.py --target-root .
```

Create draft implementation artifacts from explicit packets:

```bash
python scripts/run_implementation_workflow.py --target-root . \
  --packet-file implementation-packets.json
```

## Documentation Map

Start with the ordered index: [docs/README.md](docs/README.md).

Feature docs:

- [README.gateway.md](README.gateway.md): gateway, role proxies, ports, setup, and client notes
- [README.documenter.md](README.documenter.md): documenter orchestrator, review plans, follow-ups, drafts, and state
- [README.streaming.md](README.streaming.md): streaming document modes for oversized files and explicit reductions
- [README.code-structure-indexes.md](README.code-structure-indexes.md): deterministic source/config/document structure indexes
- [README.implementation-workflow.md](README.implementation-workflow.md): implementation plans, draft/apply policy, verification, and resume
- [README.tool-policy.md](README.tool-policy.md): tool catalog, role tool assignment, and mediated tool execution

Examples live under [docs/examples/](docs/examples/).

## Repository Layout

```text
roles/                       role and subrole prompt files
runtime/roles.json            active role manifest
runtime/tools.json            controller/tool mediator catalog
vllm_agent_gateway/gateway/    prompt proxy and token budget gateway
vllm_agent_gateway/documenter/ documenter orchestrator and streaming modes
vllm_agent_gateway/structure_index/
                              deterministic code/document/config indexer
vllm_agent_gateway/implementation/
                              controlled implementation packet workflow
vllm_agent_gateway/tools/      mediated local tool execution
scripts/                      controller and smoke-test helpers
docs/                         ordered reference docs, roadmaps, and examples
```
