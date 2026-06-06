---
name: safe-test-command-selector
description: Select safe pytest validation commands from bounded evidence. Use for prompts asking for the smallest relevant test command, medium command, broad command, command rationale, covered risks, and remaining gaps.
---

# Safe Test Command Selector

Use this skill when the user asks what test command should be run for a behavior, failure, file, or planned change.

## Workflow

1. Use only known test paths, test names, package layout, and evidence-backed risk.
2. Prefer `python -m pytest` commands.
3. Start with the smallest command that covers the named behavior.
4. Add medium and broad commands only when evidence supports them.
5. Explain what each command covers and what it does not cover.
6. Reject shell pipelines, destructive commands, broad arbitrary scripts, and commands outside the repo test policy.

## Output

Return:

- smallest command
- medium command when useful
- broad command when useful
- rationale
- covered risks
- gaps

Do not run commands.
