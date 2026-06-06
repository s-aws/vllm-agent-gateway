---
name: execution-plan-writer
description: Write a deterministic execution plan artifact from scoped problem details, entrypoint findings, bounded context plans, and impact evidence before implementation packets or repository mutation. Use when enough evidence exists to plan next actions, or when the agent must stop because evidence, approval, containment, or scope is insufficient.
---

# Execution Plan Writer

Use this skill after `context-plan-builder` and any available bounded context or impact evidence.

This skill covers problem-solving Step 5: develop an action plan. It does not execute the plan, edit files, invoke tools, create patches, approve writes, or mark work complete.

## Inputs

Use only:

- request classification from `request-triage`
- problem, goal, scope, assumptions, approvals, and stop conditions from `scope-and-assumptions`
- entrypoint candidates and selected entrypoint from `entrypoint-finder`
- bounded context requests and completed context results from `context-plan-builder`
- impact evidence, if available
- user approvals already provided

If impact evidence is missing, the plan may include an `impact_map` or `gather_context` step, but it must not jump to edit steps.

## Workflow

1. Refuse to proceed if any prior `stop.required` is true.
2. Confirm the objective and desired future state.
3. Confirm available evidence and identify missing evidence.
4. Decide whether the plan is investigation-only, implementation-prep, or ready-for-packet-design.
5. Create ordered steps with one action per step.
6. Attach target files only when they are named by the user or supported by bounded context.
7. Attach source references only when available.
8. Define acceptance criteria for every step.
9. Require approval before implementation packet design, write, apply, broad traversal, or unsafe commands.
10. Route to the next skill or stop.

## Plan Modes

Use exactly one `plan_mode`:

- `investigation_only`: more bounded context or impact mapping is needed.
- `implementation_prep`: evidence is enough to design implementation packets after approval.
- `blocked`: scope, containment, approval, or evidence is insufficient.

Do not use an implementation-ready mode unless affected files, evidence, and acceptance criteria are specific.

If `request_type` is `investigation`, or the objective says read-only, "do not edit", "investigate", or "plan before refactor", use `investigation_only` unless the user explicitly asks for implementation preparation after the investigation result. A read-only plan must not route directly to implementation packet design.

If any step action is `gather_context`, `map_impact`, `ask_user`, or `stop`, do not route to `implementation-packet-designer`. Packet design is premature while required context, impact mapping, user decisions, or stop conditions remain.

## Step Actions

Use only these action values:

- `gather_context`: request bounded context through controller or approved tools.
- `map_impact`: summarize affected behavior paths, files, symbols, tests, risks, and unknowns.
- `ask_user`: request a blocking decision or missing information.
- `design_packet`: prepare implementation packet candidates after approval.
- `plan_verification`: define verification strategy after target files and behavior are known.
- `stop`: halt because safe progress is blocked.

Do not use `edit`, `apply`, `run_command`, or `run_tests` as execution-plan actions. Those belong to later workflows.

## Output

Return exactly one JSON object:

```json
{
  "plan_id": "EP-0001",
  "plan_mode": "investigation_only|implementation_prep|blocked",
  "objective": "one sentence",
  "basis": {
    "request_type": "investigation|implementation|refactor|test_fix|documentation|workflow|unknown",
    "entrypoint": {
      "path": "repo-relative path or null",
      "symbol": "name or null",
      "confidence": "medium|high|null"
    },
    "source_refs": [],
    "assumptions": [],
    "unknowns": []
  },
  "preconditions": [],
  "steps": [
    {
      "id": "STEP-0001",
      "action": "gather_context|map_impact|ask_user|design_packet|plan_verification|stop",
      "description": "one concrete action",
      "owner": "controller|agent|user",
      "target_files": [],
      "source_refs": [],
      "acceptance_criteria": [],
      "blocked_by": [],
      "approval_required_before": []
    }
  ],
  "approval_required": true,
  "verification_strategy": [
    {
      "type": "test_discovery|pytest|manual_check|not_ready",
      "description": "what should be verified later",
      "associated_files": []
    }
  ],
  "containment": {
    "required": true,
    "actions": []
  },
  "next_step": {
    "suggested_skill": "impact-map-builder|implementation-packet-designer|verification-planner|none",
    "reason": "short explanation"
  },
  "stop": {
    "required": false,
    "reason": "string or null",
    "open_questions": []
  }
}
```

Use empty arrays for missing collections. Use `null` for unknown entrypoint values.

## Step Rules

- Assign step IDs sequentially as `STEP-0001`, `STEP-0002`, and so on.
- Keep each step independently executable and reviewable.
- Include acceptance criteria for every non-`stop` step.
- Use `owner: "user"` only for decisions or missing information.
- Use `owner: "controller"` for bounded workflow/tool execution.
- Use `owner: "agent"` for reasoning over bounded artifacts.
- Put unresolved dependencies in `blocked_by`.
- Put write, apply, broad traversal, and packet design approval needs in `approval_required_before`.

## Routing

- Route to `impact-map-builder` when context is planned or gathered but impact evidence is missing.
- Route to `implementation-packet-designer` only when the plan has enough specific evidence, the user is no longer asking for read-only investigation only, no `gather_context`, `map_impact`, `ask_user`, or `stop` steps remain, and approval is required or already available.
- Route to `verification-planner` only when target files and intended behavior are specific enough to plan verification.
- Route to `none` when the plan is blocked or when the next step requires user input.

## Must Not

- Do not edit files.
- Do not invoke tools.
- Do not run tests.
- Do not create exact patch text.
- Do not approve writes, apply mode, broad traversal, or unsafe commands.
- Do not invent target files.
- Do not claim source evidence without source references.
- Do not mark the problem solved.
- Do not skip impact mapping when affected behavior paths are unknown.
- Do not route a read-only investigation directly to implementation packet design.
- Do not route to implementation packet design while the plan still contains required context-gathering, impact-mapping, user-question, or stop steps.
- Do not create a second implementation mechanism beside the implementation workflow.

## Examples

Input context:

```json
{
  "request_type": "refactor",
  "problem": {
    "statement": "Run status handling may be split across more than one controller-service path."
  },
  "goal": {
    "future_state": "Run status handling has one explicit code path per behavior."
  },
  "entrypoint": {
    "path": "vllm_agent_gateway/controller_service/server.py",
    "symbol": null,
    "confidence": "medium"
  },
  "context_plan": {
    "context_requests": [
      {
        "id": "CTX-0001",
        "purpose": "file_structure",
        "suggested_tool": "structure_index",
        "query": "vllm_agent_gateway/controller_service/server.py"
      }
    ]
  }
}
```

Output:

```json
{
  "plan_id": "EP-0001",
  "plan_mode": "investigation_only",
  "objective": "Determine whether controller-service run status handling has duplicate behavior paths before proposing a refactor.",
  "basis": {
    "request_type": "refactor",
    "entrypoint": {
      "path": "vllm_agent_gateway/controller_service/server.py",
      "symbol": null,
      "confidence": "medium"
    },
    "source_refs": [],
    "assumptions": ["The requested refactor should preserve behavior unless the user says otherwise."],
    "unknowns": ["Exact status-handling functions.", "Related tests.", "Duplicate or parallel paths."]
  },
  "preconditions": ["Use read-only context gathering before any implementation packet design."],
  "steps": [
    {
      "id": "STEP-0001",
      "action": "gather_context",
      "description": "Execute the bounded context plan for controller-service file structure and related tests.",
      "owner": "controller",
      "target_files": ["vllm_agent_gateway/controller_service/server.py"],
      "source_refs": [],
      "acceptance_criteria": ["Context results identify relevant functions or report insufficient evidence."],
      "blocked_by": [],
      "approval_required_before": []
    },
    {
      "id": "STEP-0002",
      "action": "map_impact",
      "description": "Map affected behavior paths, symbols, tests, risks, and unknowns from bounded context results.",
      "owner": "agent",
      "target_files": [],
      "source_refs": [],
      "acceptance_criteria": ["Impact map lists affected paths or explicitly records uncertainty."],
      "blocked_by": ["STEP-0001"],
      "approval_required_before": []
    }
  ],
  "approval_required": true,
  "verification_strategy": [
    {
      "type": "not_ready",
      "description": "Verification planning waits until affected files and intended changes are known.",
      "associated_files": []
    }
  ],
  "containment": {
    "required": true,
    "actions": ["Keep work read-only until impact is mapped and the user approves implementation packet design."]
  },
  "next_step": {
    "suggested_skill": "impact-map-builder",
    "reason": "Impact evidence is missing, so implementation packet design would be premature."
  },
  "stop": {
    "required": false,
    "reason": null,
    "open_questions": []
  }
}
```

Input context:

```json
{
  "request_type": "unknown",
  "stop": {
    "required": true,
    "reason": "The problem target is unspecified."
  }
}
```

Output:

```json
{
  "plan_id": "EP-0001",
  "plan_mode": "blocked",
  "objective": "unknown",
  "basis": {
    "request_type": "unknown",
    "entrypoint": {
      "path": null,
      "symbol": null,
      "confidence": null
    },
    "source_refs": [],
    "assumptions": [],
    "unknowns": ["Problem target.", "Expected outcome."]
  },
  "preconditions": [],
  "steps": [
    {
      "id": "STEP-0001",
      "action": "ask_user",
      "description": "Ask the user to identify the problem target and expected outcome.",
      "owner": "user",
      "target_files": [],
      "source_refs": [],
      "acceptance_criteria": ["User provides a specific problem target and desired result."],
      "blocked_by": [],
      "approval_required_before": []
    }
  ],
  "approval_required": true,
  "verification_strategy": [
    {
      "type": "not_ready",
      "description": "Verification cannot be planned until the problem is specified.",
      "associated_files": []
    }
  ],
  "containment": {
    "required": true,
    "actions": ["Do not gather context, design packets, or edit files until the problem target is specified."]
  },
  "next_step": {
    "suggested_skill": "none",
    "reason": "The plan is blocked pending user clarification."
  },
  "stop": {
    "required": true,
    "reason": "The problem target is unspecified.",
    "open_questions": ["What behavior, file, command, workflow, or test should be planned around?"]
  }
}
```
