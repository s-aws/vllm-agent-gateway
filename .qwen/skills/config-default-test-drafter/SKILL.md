---
name: config-default-test-drafter
description: Draft a small unit-test proposal for an explicit configuration default value. Use when the user asks to draft or dry-run a test proving a named config symbol or key defaults to an exact expected value, with no repository mutation.
---

# Config Default Test Drafter

Use this skill only for draft-only test proposals with exact config evidence.

Required inputs:

- target repository
- repo-relative config source file
- exact config symbol or key
- exact expected default value
- draft-only or no-mutation intent

Procedure:

1. Confirm the request is write-adjacent and must use `execution_planning.plan`.
2. Require `approval_boundary=packet_design_required` and `mutation_policy=draft_artifacts_only`.
3. Verify the source file contains the exact symbol assignment before proposing a test.
4. Select an existing pytest file from bounded evidence or the user's explicit test path.
5. Emit a `small_unit_test_proposal` with subkind `config_default_test`.
6. Include exact packet operations, safety checks, blockers, and a bounded pytest command.

Stop if:

- the expected value is missing or ambiguous
- the config source file is missing
- the source evidence does not contain the expected default assignment
- no bounded pytest target can be selected
- the user asks to apply or mutate the repository
