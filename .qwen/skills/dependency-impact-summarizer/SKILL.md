---
name: dependency-impact-summarizer
description: Summarize dependency impact for a potential behavior change from bounded evidence. Use for L2 read-only prompts asking impacted files, callers/usages, related tests, risk level, validation commands, and gaps.
---

# Dependency Impact Summarizer

Use this skill when the user asks what would be impacted if a behavior changed.

## Workflow

1. Anchor the impact summary on the selected behavior or entry point.
2. Group impacted files by direct source, caller/usage, tests, config, and docs.
3. Identify risk level from evidence breadth and coupling.
4. Explain what each validation command covers.
5. State gaps that require more context before implementation.

## Output

Return:

- impacted files
- callers/usages
- related tests
- risk level
- validation commands
- gaps
- source mutation: false

Do not design implementation packets or imply approval to edit.
