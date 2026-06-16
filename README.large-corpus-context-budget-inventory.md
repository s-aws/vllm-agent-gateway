# Large-Corpus Context Budget Inventory

Phase 214 creates a reproducible large local corpus fixture and records the current context-budget facts before retrieval or indexing work starts.

This phase does not implement retrieval, durable indexing, context routing, artifact paging, or raw 384k-token or larger prompting. It establishes the measured facts required for those later phases.

## What It Checks

- A deterministic local corpus fixture can be generated without external access.
- The corpus exceeds the current model and gateway prompt budget by estimated token count.
- The inventory records file count, directory count, bytes, estimated tokens, language mix, extension mix, binary paths, ignored paths, role split, and largest files.
- Current model and gateway assumptions are parsed from `VLLM_AGENT_HOST.md` and `start-agent-prompt-proxies.sh`.
- Local runtime probes are recorded when available, including `/v1/models` and gateway/controller health endpoints.
- Blind-baseline prompt categories exist for navigation, evidence lookup, summarization, and limitations.
- The report explicitly states that raw long-context prompt support is not proven.

## Inputs

- `runtime/large_corpus_context_budget_inventory_policy.json`
- `VLLM_AGENT_HOST.md`
- `start-agent-prompt-proxies.sh`

## Outputs

- `runtime-state/phase214/generated-large-corpus/`
- `runtime-state/phase214/phase214-large-corpus-context-budget-inventory-report.json`
- `runtime-state/phase214/phase214-large-corpus-context-budget-inventory-report.md`

## Validation

```bash
python3 scripts/validate_large_corpus_context_budget_inventory.py
python3 -m pytest tests/regression/test_large_corpus_context_budget_inventory.py -q
```

## Boundary

The generated corpus is not production source and must not be treated as a protected fixture. Phase 216 must define corpus/index safety governance before any durable index feeds chat-visible answers.
