---
name: configuration-effect-summarizer
description: Explain the runtime effect of a configuration key or environment variable from bounded read-only evidence.
---

# Configuration Effect Summarizer

Use this skill for prompts asking what a config value, setting, or environment variable does at runtime.

## Workflow

1. Keep the target repository read-only.
2. Use configuration references found by `code_investigation.plan`.
3. Distinguish environment reads, derived aliases, client construction, and runtime consumers.
4. Return `configuration_effect_summary` with references, runtime effects, source refs, and gaps.
5. Do not expose secret values; report environment visibility only.

## Output Rules

- Use `status: ready` when config references or likely runtime effects were found.
- Use `status: unknown` when bounded evidence does not prove usage.
- Always include `mutation_policy: read_only_no_source_mutation`.
