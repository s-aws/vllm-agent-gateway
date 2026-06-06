---
name: documentation-locator
description: Find documentation for a requested behavior from bounded read-only evidence, including doc files, source refs, and documentation gaps.
---

# Documentation Locator

Use this skill for prompts asking where behavior is documented or whether docs exist for a behavior.

## Workflow

1. Keep the target repository read-only.
2. Prefer Markdown, README, agent, and docs files found by bounded investigation evidence.
3. Return `documentation_lookup` with documentation files, matching snippets, source refs, and gaps.
4. Separate documentation evidence from source-code evidence.
5. If no documentation is found, return an explicit gap and do not infer that docs are absent globally.

## Output Rules

- Use `status: ready` when documentation evidence is found.
- Use `status: unknown` when bounded evidence finds no documentation.
- Always include `mutation_policy: read_only_no_source_mutation`.
