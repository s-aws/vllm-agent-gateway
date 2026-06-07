---
name: runtime-reproduction-checklist-writer
description: Convert a pasted runtime stack trace into a minimal reproduction checklist using bounded source, traceback, and verification evidence.
---

# runtime-reproduction-checklist-writer

Use this skill only when registry metadata selects it for `code_investigation.plan`.

Required behavior:

- Keep the workflow read-only.
- Start from the observed exception and nearest project-code traceback frame.
- Produce a minimal reproduction checklist before suggesting any implementation work.
- Use related tests or bounded verification commands only when they are present in evidence.
- Return gaps when the stack trace lacks a project frame or reproducible command.

Output contract:

- Support the `reproduction_checklist` artifact.
- Include `observed_error`, `traceback_frame`, `minimal_reproduction_checklist`, `related_tests`, `next_local_command`, `mutation_policy`, and `gaps`.
- Preserve `mutation_policy=read_only_no_source_mutation`.

Stop conditions:

- Stop if the request asks to fix, edit, apply, or mutate files.
- Stop if the request does not include a runtime error, stack trace, traceback, or exception.
