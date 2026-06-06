---
name: failing-test-diagnosis
description: Diagnose a failing test from pasted output and bounded repository evidence. Use for L2 read-only prompts asking for root cause, smallest safe fix plan, verification, and source mutation proof without editing.
---

# Failing Test Diagnosis

Use this skill after a workflow has both pasted failure output and bounded source/test evidence.

## Workflow

1. Identify the failed test and assertion.
2. Locate the behavior or contract the test is checking.
3. Compare failure text against source and invariant evidence.
4. State a root-cause hypothesis with confidence.
5. Produce a smallest safe fix plan as prose only.
6. Provide verification commands from known tests.

## Output

Return:

- failed test
- root-cause hypothesis
- evidence
- smallest safe fix plan
- verification
- source mutation: false
- gaps

Do not create patch operations or mutate files.
