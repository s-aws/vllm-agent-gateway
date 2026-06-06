---
name: message-assertion-test-drafter
description: Draft a small unit-test proposal for an exact error or log message assertion. Use when the user asks to draft or dry-run a test asserting a specific emitted message, exception message, or log text, with no repository mutation.
---

# Message Assertion Test Drafter

Use this skill only for draft-only message assertion test proposals.

Required inputs:

- target repository
- repo-relative message source file
- exact message text or bounded message template
- expected emitter, exception, or behavior
- draft-only or no-mutation intent

Procedure:

1. Confirm the request is write-adjacent and must use `execution_planning.plan`.
2. Require `approval_boundary=packet_design_required` and `mutation_policy=draft_artifacts_only`.
3. Verify bounded source evidence contains the message template or exact message anchor.
4. Select an existing pytest file from bounded evidence or the user's explicit test path.
5. Emit a `small_unit_test_proposal` with subkind `message_assertion_test`.
6. Include exact packet operations, safety checks, blockers, and a bounded pytest command.

Stop if:

- the exact message is missing
- the message source cannot be found
- the assertion would require behavior design instead of testing existing behavior
- no bounded pytest target can be selected
- the user asks to apply or mutate the repository
