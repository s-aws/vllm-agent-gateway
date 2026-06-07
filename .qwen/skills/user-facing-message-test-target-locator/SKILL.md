---
name: user-facing-message-test-target-locator
description: Check whether an error or log message appears user-facing and identify bounded related tests and verification commands without editing files.
---

# user-facing-message-test-target-locator

Use this skill only when registry metadata selects it for `code_investigation.plan`.

Required behavior:

- Keep the workflow read-only.
- Locate the message source before assessing whether it is user-facing.
- Return `unknown` when bounded evidence finds an exception or log source but not the UI/rendering path.
- Recommend test targets only from related-test discovery and bounded verification evidence.
- Do not print secrets or unrelated surrounding runtime values.

Output contract:

- Support the `message_source_lookup` artifact with `user_facing_assessment`.
- Include message source, user-facing status, reason, test targets, verification commands, mutation policy, and gaps.
- Preserve `mutation_policy=read_only_no_source_mutation`.

Stop conditions:

- Stop if the request asks to change the message or add tests.
- Stop if the request does not ask about a user-facing message or test target.
