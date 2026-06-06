---
name: scope-and-assumptions
description: Define the problem, clarify scope, capture assumptions, containment needs, priority, resource needs, goals, and stop conditions before context gathering or execution planning. Use after request-triage for any non-trivial investigation, implementation, refactor, test fix, documentation, or workflow task.
---

# Scope And Assumptions

Use this skill after `request-triage` classifies a non-trivial request.

This skill covers the first three problem-solving steps:

1. Define the problem.
2. Clarify the problem.
3. Define the goals.

Do not gather broad repository context, select files, create implementation steps, or invoke controller workflows from this skill. Its job is to prevent vague work from reaching the next process step.

## Workflow

1. Define the problem in one concrete sentence.
2. Capture how the problem was discovered, using only user-provided evidence or `unknown`.
3. Capture when it started or how long it has been happening, using `unknown` when not provided.
4. Decide whether containment is required before moving forward.
5. Clarify what data is already available and what data is still needed.
6. Decide whether resolving the problem is currently a top priority.
7. Identify whether additional resources, user decisions, or controller workflows are needed.
8. Define the desired future state, success criteria, and timeline.
9. Set explicit in-scope, out-of-scope, assumption, approval, and stop-condition records.

## Containment

Containment means preventing unclear, unsafe, or incomplete work from moving to the next step.

Examples:

- Ask a blocking question when the target behavior is unspecified.
- Refuse to plan writes before approval exists.
- Require a read-only investigation before implementation.
- Stop at low confidence instead of inventing files or root cause.

Containment does not mean mutating the repository.

## Output

Return exactly one JSON object:

```json
{
  "problem": {
    "statement": "one concrete sentence",
    "discovered_by": "user|artifact|test|workflow|unknown",
    "start_or_duration": "string or unknown",
    "current_impact": "string or unknown"
  },
  "clarification": {
    "available_data": [],
    "needed_data": [],
    "priority": "low|medium|high|unknown",
    "additional_resources_required": [],
    "containment": {
      "required": true,
      "status": "not_needed|proposed|blocked",
      "actions": []
    }
  },
  "goal": {
    "future_state": "one sentence",
    "benefit": "what fixing this accomplishes",
    "desired_timeline": "string or unknown",
    "success_criteria": []
  },
  "scope": {
    "in_scope": [],
    "out_of_scope": [],
    "assumptions": [],
    "approval_required_before": [],
    "stop_conditions": []
  },
  "next_step": {
    "suggested_skill": "entrypoint-finder|context-plan-builder|execution-plan-writer|none",
    "reason": "short explanation",
    "open_questions": []
  }
}
```

## Routing

Use `next_step.suggested_skill` this way:

- `entrypoint-finder`: use when the task needs code or workflow investigation and the logical beginning point is not yet known.
- `context-plan-builder`: use when the entry point is already known and the next decision is what bounded context to gather.
- `execution-plan-writer`: use only when the request is already fully scoped and enough evidence exists to write a plan without more context.
- `none`: use when blocking questions, missing approvals, or insufficient scope should stop progress.

## Rules

- Use `unknown` instead of inventing discovery, timeline, impact, priority, or resources.
- Keep `open_questions` limited to questions that block safe progress.
- Keep `assumptions` explicit and reviewable.
- Put target repo mutation in `approval_required_before` unless the user has already approved it.
- Put broad or unbounded traversal in `approval_required_before`.
- Treat implementation packet creation as write-adjacent because it can lead to mutation later.
- If containment is required and not satisfied, route to `none`.

## Must Not

- Do not select target files unless the user already named them.
- Do not claim source evidence.
- Do not identify root cause.
- Do not create action steps.
- Do not choose tests or verification commands.
- Do not invoke tools or controller workflows.
- Do not approve write, apply, broad traversal, or unsafe commands.
- Do not move to implementation planning when the problem statement or goal is unclear.

## Examples

User request:

```text
Refactor the controller service so run status is handled through one path.
```

Output:

```json
{
  "problem": {
    "statement": "Run status handling may be split across more than one controller-service path.",
    "discovered_by": "user",
    "start_or_duration": "unknown",
    "current_impact": "Potential duplicated behavior and harder maintenance."
  },
  "clarification": {
    "available_data": ["User identified the target area as controller service run status handling."],
    "needed_data": ["Current logic entry point.", "Known run status paths.", "Related tests."],
    "priority": "unknown",
    "additional_resources_required": [],
    "containment": {
      "required": true,
      "status": "proposed",
      "actions": ["Perform read-only entrypoint investigation before any refactor plan."]
    }
  },
  "goal": {
    "future_state": "Run status handling has one explicit code path per behavior.",
    "benefit": "Maintenance and verification become simpler.",
    "desired_timeline": "unknown",
    "success_criteria": ["Behavior-preserving refactor plan exists.", "No implementation occurs before approval."]
  },
  "scope": {
    "in_scope": ["Read-only investigation of controller service run status behavior."],
    "out_of_scope": ["Applying edits before approval.", "Changing unrelated controller behavior."],
    "assumptions": ["The request is behavior-preserving unless the user says otherwise."],
    "approval_required_before": ["write", "apply"],
    "stop_conditions": ["Unable to identify a likely entry point with bounded context."]
  },
  "next_step": {
    "suggested_skill": "entrypoint-finder",
    "reason": "The task is scoped enough to find the logic beginning point.",
    "open_questions": []
  }
}
```

User request:

```text
Fix it.
```

Output:

```json
{
  "problem": {
    "statement": "The target problem is not specified.",
    "discovered_by": "unknown",
    "start_or_duration": "unknown",
    "current_impact": "unknown"
  },
  "clarification": {
    "available_data": [],
    "needed_data": ["Problem target.", "Expected outcome."],
    "priority": "unknown",
    "additional_resources_required": ["user clarification"],
    "containment": {
      "required": true,
      "status": "blocked",
      "actions": ["Do not gather context or plan implementation until the target problem is specified."]
    }
  },
  "goal": {
    "future_state": "unknown",
    "benefit": "unknown",
    "desired_timeline": "unknown",
    "success_criteria": []
  },
  "scope": {
    "in_scope": [],
    "out_of_scope": ["Repository traversal.", "Implementation planning.", "File edits."],
    "assumptions": [],
    "approval_required_before": ["write", "apply", "broad traversal"],
    "stop_conditions": ["Problem target remains unspecified."]
  },
  "next_step": {
    "suggested_skill": "none",
    "reason": "The request is too ambiguous to safely clarify without user input.",
    "open_questions": ["What should be fixed, and what result should the fix produce?"]
  }
}
```
