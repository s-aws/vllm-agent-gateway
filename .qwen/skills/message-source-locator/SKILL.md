---
name: message-source-locator
description: Locate the source of an error, exception, log, logger, or printed message from bounded exact-text evidence. Use for read-only prompts asking where a message comes from.
---

# Message Source Locator

Use after `code_investigation.plan` has searched for a requested error, exception, log, or printed message.

## Workflow

1. Preserve the requested message text exactly.
2. Classify each source line as raised exception, log call, print output, or generic message reference.
3. Prefer source files over tests and documentation for the primary answer.
4. Return file, line, role, and source refs.
5. If no exact source line is found, say unknown and list the evidence gap.

## Output

Return:

- target message
- source files and line refs
- source role
- evidence text
- gaps

Do not diagnose or fix the error unless a separate approved workflow asks for that.
