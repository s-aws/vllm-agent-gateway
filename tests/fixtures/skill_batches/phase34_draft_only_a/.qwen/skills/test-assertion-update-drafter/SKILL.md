---
name: test-assertion-update-drafter
description: Draft a small test assertion update from exact old assertion text to exact new assertion text. Use when the user asks to draft or dry-run a bounded test assertion change, with no repository mutation or production-code edits.
---

# Test Assertion Update Drafter

Use this skill only for draft-only updates to existing test assertions.

Required inputs:

- target repository
- repo-relative pytest file
- exact old assertion text
- exact new assertion text
- draft-only or no-mutation intent

Procedure:

1. Confirm the request is write-adjacent and must use `execution_planning.plan`.
2. Require `approval_boundary=packet_design_required` and `mutation_policy=draft_artifacts_only`.
3. Verify the old assertion appears exactly once in the target pytest file.
4. Verify the new assertion is not already present.
5. Emit a `small_unit_test_proposal` with subkind `test_assertion_update`.
6. Include exact `replace_text` packet operations, safety checks, blockers, and a bounded pytest command.

Stop if:

- the old assertion is missing, duplicated, or not exact
- the new assertion is already present
- the target file is not a pytest file
- the request implies production-code changes
- the user asks to apply or mutate the repository
