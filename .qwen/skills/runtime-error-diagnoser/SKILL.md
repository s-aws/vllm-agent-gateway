---
name: runtime-error-diagnoser
description: Diagnose a runtime error, exception, or stack trace from bounded read-only evidence, including observed error, likely cause, evidence files, next inspection steps, risks, gaps, and verification commands.
---

# Runtime Error Diagnoser

Use this skill for read-only prompts that include a runtime error, exception, or stack trace and ask for diagnosis.

## Workflow

1. Treat the repository as read-only.
2. Extract the exception type, message, and nearest project-code frame from the request.
3. Use bounded investigation evidence to connect the error to source files, tests, and likely runtime behavior.
4. State likely cause as a hypothesis unless evidence directly proves it.
5. Return next inspection steps before any fix plan.

## Output Rules

- Return `runtime_error_diagnosis`.
- Include observed error, likely cause, evidence files, next inspection steps, risks, gaps, verification commands, and source refs.
- Always include `mutation_policy: read_only_no_source_mutation`.
- Do not propose implementation packets or edit operations.
