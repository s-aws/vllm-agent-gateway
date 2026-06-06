---
name: coverage-gap-summarizer
description: Identify test coverage gaps for a requested behavior from bounded read-only evidence, including covered tests, uncovered source areas, verification commands, and evidence gaps.
---

# Coverage Gap Summarizer

Use this skill for read-only prompts asking which tests cover a behavior and what coverage gaps remain.

## Workflow

1. Treat the repository as read-only.
2. Use bounded investigation evidence, related-test evidence, and verification commands from `code_investigation.plan`.
3. Return `coverage_gap_summary` with covered tests, likely uncovered source files or behavior areas, recommended verification commands, evidence gaps, and source refs.
4. Do not claim full coverage unless direct tests and source refs prove it.
5. If evidence is shallow, say which gap remains instead of inventing missing tests.

## Output Rules

- Use `status: ready` when at least one source or test reference was found.
- Use `status: unknown` when no bounded coverage evidence was found.
- Always include `mutation_policy: read_only_no_source_mutation`.
