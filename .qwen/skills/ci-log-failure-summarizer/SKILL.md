---
name: ci-log-failure-summarizer
description: Summarize a pasted CI, GitHub Actions, pipeline, or build log into first failing command, likely cause, next local command, and read-only evidence.
---

# ci-log-failure-summarizer

Use this skill only when registry metadata selects it for `code_investigation.plan`.

Required behavior:

- Keep the workflow read-only.
- Identify the first failing command from the pasted CI log before interpreting symptoms.
- Report the primary observed error exactly enough to distinguish assertion, import, compiler, or generic CI failures.
- Recommend the next local command only from the log, related tests, or bounded verification evidence.
- Return gaps instead of guessing when the command, error, or local command is not present.
- Do not propose source edits or implementation packets.

Output contract:

- Support the `ci_failure_summary` artifact.
- Include `first_failing_command`, `primary_error`, `likely_cause`, `next_local_command`, `mutation_policy`, and `gaps`.
- Preserve `mutation_policy=read_only_no_source_mutation`.

Stop conditions:

- Stop if the request asks to fix, edit, apply, or mutate files.
- Stop if the pasted content is not a CI/build/pipeline log.
