---
name: pasted-failure-summarizer
description: Summarize pasted test or command failure output into a bounded diagnosis. Use for read-only prompts asking what failed, likely cause, affected files, and next inspection steps without applying fixes.
---

# Pasted Failure Summarizer

Use this skill when the user pastes test output, traceback output, command output, or assertion text.

## Workflow

1. Extract failed test names, files, assertion messages, and stack locations.
2. Separate observed failure facts from likely cause.
3. Use repository evidence only when supplied by the workflow.
4. Recommend the next bounded inspection step.
5. Suggest verification commands only when they directly relate to the failure.

## Output

Return:

- failed tests or commands
- primary error
- likely cause
- affected files when known
- next bounded inspection step
- verification command when evidence-backed

Do not edit files, run commands, or promise a fix.
