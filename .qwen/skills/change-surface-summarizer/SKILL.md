---
name: change-surface-summarizer
description: Identify the minimal safe change surface for a requested behavior change without implementation, including files needing review, related tests, risk level, gaps, verification commands, and approval stop conditions.
---

# Change Surface Summarizer

Use this skill for read-only prompts asking which files would need review before a safe change.

## Workflow

1. Treat the requested change as analysis-only unless approval has already been handled by another workflow.
2. Identify source, test, configuration, and documentation files in bounded evidence.
3. Separate files needing review from files that merely mention the behavior.
4. State risk level from evidence breadth, related tests, and missing transitions.
5. Stop before implementation packet generation.

## Output Rules

- Return `change_surface_summary`.
- Include files needing review, related tests, risk level, risks, gaps, verification commands, and source refs.
- Include `implementation_status: not_ready_without_approval`.
- Always include `mutation_policy: read_only_no_source_mutation`.
