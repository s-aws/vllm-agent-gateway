---
name: module-summarizer
description: Summarize a module or file from bounded AST and snippet evidence. Use for read-only prompts asking for responsibilities, definitions, related tests, source refs, and gaps for one file.
---

# Module Summarizer

Use after `code_investigation.plan` has selected a file or module.

## Workflow

1. Identify the target file path.
2. Use module docstring, AST definitions, snippets, and test references only.
3. Summarize responsibilities separately from definitions.
4. List major classes/functions and related tests.
5. Mark partial evidence when the file is unreadable, truncated, or outside budget.

## Output

Return:

- target module
- concise summary
- responsibilities
- definitions
- related tests
- source refs and gaps

Do not propose implementation changes from a module summary.
