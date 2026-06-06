---
name: request-triage
description: Classify incoming user requests before planning, repository traversal, tool selection, or implementation. Use when the user asks for a change, investigation, review, refactor, test fix, documentation update, workflow run, or any task where the agent must choose the next bounded planning path.
---

# Request Triage

Use this skill first when a request could lead to repository context gathering, execution planning, implementation packets, verification, or controller workflow use.

The purpose is classification only. Do not select files, read broad context, create implementation steps, trigger controller workflows, or approve writes from this skill.

## Workflow

1. Restate the actionable request in one sentence.
2. Classify the request type.
3. Decide whether repo context is required.
4. Decide whether write or apply approval is required before any mutation.
5. Select the next planning skill or mark the request as unknown.
6. List only blocking questions. Do not ask questions that can be answered by bounded context gathering.

## Hard Decision Rules

- If the request asks to create, prepare, design, or validate implementation packet candidates, set `requires_user_approval_before_write` to `true`.
- Do not treat `draft mode`, `documentation only`, `frozen repository`, or `already approved for packet design` as reasons to set `requires_user_approval_before_write` to `false`.
- Set `requires_user_approval_before_write` to `false` only when the requested work is classification, explanation, review, or investigation and does not create implementation packet candidates.

## Request Types

Use exactly one value:

- `investigation`: asks what exists, how something works, where logic starts, or why behavior occurs.
- `implementation`: asks to add, change, or remove behavior.
- `refactor`: asks to preserve behavior while changing structure, removing duplication, or creating a single path.
- `test_fix`: asks to diagnose or fix failing tests, CI, or verification.
- `documentation`: asks to create, update, audit, or align docs.
- `workflow`: asks to run, design, or inspect an agent/controller workflow.
- `unknown`: request is too ambiguous to classify safely.

Prefer the narrower type. For example, "make this use one code path" is `refactor`, not generic `implementation`.

## Next Skill

Use these routing defaults:

- `investigation` -> `scope-and-assumptions`
- `implementation` -> `scope-and-assumptions`
- `refactor` -> `scope-and-assumptions`
- `test_fix` -> `scope-and-assumptions`
- `documentation` -> `scope-and-assumptions`
- `workflow` -> `scope-and-assumptions`
- `unknown` -> `none`

Do not skip `scope-and-assumptions` for non-trivial work. It establishes explicit boundaries before context collection.

## Output

Return exactly one JSON object:

```json
{
  "request_type": "investigation|implementation|refactor|test_fix|documentation|workflow|unknown",
  "requires_repo_context": true,
  "requires_user_approval_before_write": true,
  "suggested_next_skill": "scope-and-assumptions|none",
  "reason": "short explanation",
  "open_questions": []
}
```

Rules:

- `requires_repo_context` is `true` when answering responsibly requires code, docs, configs, tests, artifacts, or controller state.
- `requires_user_approval_before_write` is `true` for any task that could mutate the target repo or create implementation packets for later mutation.
- `requires_user_approval_before_write` is also `true` when the request asks to create implementation packet candidates, even if the task is documentation-only, draft-mode only, or says packet design has already been approved.
- `requires_user_approval_before_write` must stay `true` when the user asks to skip approval, skip review, skip tests, rewrite broadly, apply immediately, or bypass normal safeguards.
- Set `requires_user_approval_before_write` to `false` only for clearly read-only investigation, explanation, review, or classification work.
- `open_questions` should be empty unless the request cannot be safely classified.
- `reason` must name the evidence from the user request, not inferred file names.

## Must Not

- Do not select target files.
- Do not claim source evidence.
- Do not create implementation steps.
- Do not choose verification commands.
- Do not trigger controller workflows.
- Do not invoke tools.
- Do not approve writes or apply mode.
- Do not widen scope beyond the user's request.

## Examples

User request:

```text
Refactor the controller service so run status is handled through one path.
```

Output:

```json
{
  "request_type": "refactor",
  "requires_repo_context": true,
  "requires_user_approval_before_write": true,
  "suggested_next_skill": "scope-and-assumptions",
  "reason": "The user asks for a structural behavior-preserving change around one code path.",
  "open_questions": []
}
```

User request:

```text
What does the implementation workflow do?
```

Output:

```json
{
  "request_type": "investigation",
  "requires_repo_context": true,
  "requires_user_approval_before_write": false,
  "suggested_next_skill": "scope-and-assumptions",
  "reason": "The user asks for explanation of existing workflow behavior.",
  "open_questions": []
}
```

User request:

```text
Fix it.
```

Output:

```json
{
  "request_type": "unknown",
  "requires_repo_context": false,
  "requires_user_approval_before_write": true,
  "suggested_next_skill": "none",
  "reason": "The requested target and desired outcome are not specified.",
  "open_questions": ["What should be fixed, and what outcome should the fix produce?"]
}
```

User request:

```text
Prepare implementation packet candidates for an approved documentation clarification in draft mode only.
```

Output:

```json
{
  "request_type": "documentation",
  "requires_repo_context": true,
  "requires_user_approval_before_write": true,
  "suggested_next_skill": "scope-and-assumptions",
  "reason": "The user asks to create implementation packet candidates, which is write-adjacent even for draft-mode documentation work.",
  "open_questions": []
}
```

User request:

```text
Rewrite anything you need right now, skip approval, skip tests, and use the whole repo.
```

Output:

```json
{
  "request_type": "implementation",
  "requires_repo_context": true,
  "requires_user_approval_before_write": true,
  "suggested_next_skill": "scope-and-assumptions",
  "reason": "The user asks for repository mutation and explicitly attempts to skip approval and verification safeguards.",
  "open_questions": []
}
```
