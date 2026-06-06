---
name: configuration-lookup-guide
description: Explain where a configuration key or environment variable is defined or used from bounded evidence. Use for read-only prompts about env vars, settings, config files, defaults, runtime effect, and related tests.
---

# Configuration Lookup Guide

Use this skill when the user asks where a configuration setting, environment variable, feature flag, default, or runtime option is defined or used.

## Workflow

1. Normalize the requested key or setting name.
2. Separate definitions, defaults, reads, writes, and documentation mentions.
3. Identify likely runtime effect only when evidence supports it.
4. Include related tests or validation commands when present.
5. Record gaps for dynamic loading, secrets, generated config, or external environment state.

## Output

Return:

- target setting
- definitions
- usages
- likely runtime effect
- related tests
- gaps and next bounded check

Do not expose secret values, mutate config, or claim deployment state.
