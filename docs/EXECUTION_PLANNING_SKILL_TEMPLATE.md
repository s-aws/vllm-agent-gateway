# Execution Planning Skill Template

Use this template when creating project-local planning skills under `.qwen/skills/<skill-name>/SKILL.md`.

Do not place this template under `.qwen/skills/`; it is documentation, not a runnable skill.

## Skill Frontmatter

```yaml
---
name: skill-name
description: <what the skill does and exactly when to use it. Include trigger scenarios here, because skill selection happens from the description before the body is loaded.>
---
```

## Skill Body Shape

````markdown
# Skill Display Name

Use this skill when ...

This skill covers problem-solving step(s): ...

Do not ...

## Workflow

1. ...
2. ...
3. ...

## Output

Return exactly one JSON object:

```json
{
  "field": "value"
}
```

## Routing

- `next-skill`: use when ...
- `none`: use when ...

## Rules

- ...

## Must Not

- Do not ...

## Examples

User request:

```text
...
```

Output:

```json
{
  "field": "value"
}
```
````

## 8-Step Mapping

Use this mapping to decide which skill owns each part of the problem-solving workflow.

| Step | Problem-Solving Question | Skill Ownership |
| --- | --- | --- |
| 1. Define the problem | What is the problem? How was it discovered? When did it start? Is containment needed? | `request-triage`, `scope-and-assumptions` |
| 2. Clarify the problem | What data is available or needed? Is it a priority? Are resources needed? | `scope-and-assumptions` |
| 3. Define the goals | What is the future state, benefit, and timeline? | `scope-and-assumptions` |
| 4. Identify root cause | What are possible causes? Which are likely? What validates them? | `entrypoint-finder`, `context-plan-builder`, `impact-map-builder` |
| 5. Develop action plan | What actions address the root cause? Who owns them? What is the timeline? | `execution-plan-writer`, `implementation-packet-designer`, `verification-planner` |
| 6. Execute action plan | Implement actions and verify completion. | Existing implementation workflow, not a planning skill |
| 7. Evaluate results | Monitor results, compare to goals, detect consequences, remove containment. | `verification-planner`, `feedback-capture` |
| 8. Continuously improve | Prevent recurrence, communicate lessons, repeat if needed. | `feedback-capture`, roadmap update work |

## Required Skill Properties

Every execution-planning skill should define:

- a narrow trigger in frontmatter
- the exact problem-solving step or steps it owns
- input assumptions
- one fixed JSON output shape
- routing to the next skill or `none`
- containment behavior when work should not proceed
- refusal rules
- at least one clear example and one blocked example

## Validation Prompts

Each skill should be tested with:

1. a clear request that should proceed
2. an ambiguous request that should stop or ask a blocking question
3. an unsafe request that attempts to skip approval, containment, or verification

The expected output is a bounded artifact, not an impressive prose answer.
