---
name: implementation-packet-designer
description: Convert approved execution-plan design_packet steps into bounded implementation packet candidates for the existing implementation.workflow. Use after execution-plan-writer only when specific plan steps have user or controller approval and the agent must prepare packet candidates without applying edits, invoking tools, running tests, inventing patch text, widening file scope, or bypassing draft/apply policy.
---

# Implementation Packet Designer

Use this skill after `execution-plan-writer` when specific `design_packet` steps have been approved by the user or controller.

This skill covers the packet-design part of problem-solving Step 5: develop an action plan. It does not execute Step 6. It does not edit files, apply patches, invoke tools, run tests, or approve apply mode.

## Inputs

Use only:

- execution plan from `execution-plan-writer`
- impact map from `impact-map-builder`
- approved step IDs and approval references from the user or controller
- target files, source references, acceptance criteria, and verification strategy already present in the plan
- exact operation text only when it is already approved and evidence-backed

If approval is missing or ambiguous, stop. Do not treat conversation momentum as approval.

## Workflow

1. Refuse to proceed if any prior `stop.required` is true.
2. Confirm `plan_mode` is `implementation_prep`.
3. Confirm every selected step has `action: "design_packet"`.
4. Confirm every selected step is explicitly approved by ID.
5. Reject selected steps that are still blocked by context gathering, impact mapping, user decisions, or stop conditions.
6. Build one packet candidate per approved step unless a step clearly needs to be split by target file or operation kind.
7. Keep `target_files` exactly inside the approved step scope.
8. Choose allowed operations only from the implementation workflow: `append_text`, `replace_text`, `create_file`.
9. Include a concrete `operation` only when all operation fields are already known and approved.
10. Put incomplete or unsafe packets in `blocked_packets`, not in executable candidates.
11. Route to `verification-planner` when packet candidates exist but verification commands are missing or incomplete.

## Implementation Workflow Compatibility

The existing implementation workflow accepts explicit packet files shaped like:

```json
{
  "schema_version": 1,
  "packets": [
    {
      "id": "IMP-0001",
      "target_files": ["README.md"],
      "allowed_operations": ["replace_text"],
      "operation": {
        "kind": "replace_text",
        "path": "README.md",
        "old": "old text",
        "new": "new text"
      },
      "source_refs": [
        {
          "path": "README.md",
          "line_range": [1, 3]
        }
      ],
      "acceptance_criteria": ["README is updated."],
      "max_context_tokens": 4000,
      "notes": "short note"
    }
  ]
}
```

Concrete operation requirements:

- `append_text`: requires `path` and `content`.
- `replace_text`: requires `path`, non-empty exact `old`, and exact `new`.
- `create_file`: requires `path` and `content`.

If any required operation field is missing, set `operation` to `null` and put the item in `blocked_packets`.

## Output

Return exactly one JSON object:

```json
{
  "packet_set_id": "IMPSET-0001",
  "source_plan_id": "EP-0001 or null",
  "approval": {
    "status": "approved|missing|partial|rejected",
    "approved_step_ids": [],
    "approval_refs": []
  },
  "workflow_compatibility": {
    "target_workflow": "implementation.workflow",
    "schema_version": 1,
    "supported_operations": ["append_text", "replace_text", "create_file"],
    "default_mode": "draft",
    "apply_mode_allowed_by_this_skill": false,
    "notes": []
  },
  "packet_candidates": [
    {
      "id": "IMP-0001",
      "source_step_id": "STEP-0001",
      "task": "one concrete task",
      "target_files": [],
      "allowed_operations": ["append_text|replace_text|create_file"],
      "operation_intent": {
        "kind": "append_text|replace_text|create_file|unspecified",
        "path": "repo-relative path or null",
        "description": "what the operation should accomplish",
        "requires_exact_old_text": false,
        "requires_content": false
      },
      "operation": {
        "kind": "append_text|replace_text|create_file",
        "path": "repo-relative path",
        "old": "replace_text only",
        "new": "replace_text only",
        "content": "append_text or create_file only"
      },
      "source_refs": [
        {
          "path": "repo-relative path",
          "line_range": [1, 1]
        }
      ],
      "acceptance_criteria": [],
      "verification_requirements": [],
      "max_context_tokens": 4000,
      "notes": ""
    }
  ],
  "blocked_packets": [
    {
      "source_step_id": "STEP-0001 or null",
      "reason": "missing_approval|blocked_step|unsupported_operation|missing_target_files|missing_exact_text|missing_acceptance_criteria|unsafe_scope|prior_stop",
      "needed_resolution": "specific approval, exact text, bounded context, or plan revision needed"
    }
  ],
  "packet_file_preview": {
    "schema_version": 1,
    "packets": [],
    "verification_commands": []
  },
  "next_step": {
    "suggested_skill": "verification-planner|execution-plan-writer|none",
    "reason": "short explanation"
  },
  "stop": {
    "required": false,
    "reason": "string or null",
    "open_questions": []
  }
}
```

Use `packet_candidates` for executable packet candidates only. Use `blocked_packets` for approved work that cannot yet become a workflow packet. Use empty arrays for missing collections. Use `null` for missing scalar values.

## Packet Rules

- Assign packet set ID `IMPSET-0001`.
- Assign packet IDs sequentially as `IMP-0001`, `IMP-0002`, and so on.
- Keep every path repo-relative.
- Keep `operation.path` inside `target_files`.
- Keep `target_files` limited to files listed by the approved execution-plan step.
- Keep `source_refs` as objects with at least a `path`; include `line_range` only when known.
- Keep `max_context_tokens` at or below 4000 unless the approved plan explicitly provides a lower value.
- Put workflow packet previews only in `packet_file_preview.packets` when every packet candidate has a concrete `operation`.
- Include verification commands only when already controller-approved and pytest-style; otherwise leave `verification_commands` empty and route to `verification-planner`.

## Routing

- Route to `verification-planner` when packet candidates exist and verification needs selection or confirmation.
- Route to `execution-plan-writer` when the plan must be revised before packets can be designed.
- Route to `none` when approval is missing, rejected, partial, or a prior stop blocks packet design.

## Must Not

- Do not edit files.
- Do not apply patches.
- Do not invoke tools.
- Do not run tests.
- Do not approve writes or apply mode.
- Do not invent exact patch text.
- Do not invent `old`, `new`, or `content` fields.
- Do not include files outside approved step target files.
- Do not include unsupported operations.
- Do not convert `gather_context`, `map_impact`, `ask_user`, `plan_verification`, or `stop` steps into packets.
- Do not make packet design a second implementation mechanism.

## Examples

Input context:

```json
{
  "execution_plan": {
    "plan_id": "EP-0001",
    "plan_mode": "implementation_prep",
    "steps": [
      {
        "id": "STEP-0001",
        "action": "design_packet",
        "description": "Update README install sentence.",
        "target_files": ["README.md"],
        "source_refs": ["README.md:3"],
        "acceptance_criteria": ["README mentions Docker or Podman."],
        "blocked_by": []
      }
    ]
  },
  "approved_step_ids": ["STEP-0001"],
  "approval_refs": ["user:approved STEP-0001"],
  "operation_details": [
    {
      "source_step_id": "STEP-0001",
      "kind": "replace_text",
      "path": "README.md",
      "old": "Install with Docker.",
      "new": "Install with Docker or Podman."
    }
  ]
}
```

Output:

```json
{
  "packet_set_id": "IMPSET-0001",
  "source_plan_id": "EP-0001",
  "approval": {
    "status": "approved",
    "approved_step_ids": ["STEP-0001"],
    "approval_refs": ["user:approved STEP-0001"]
  },
  "workflow_compatibility": {
    "target_workflow": "implementation.workflow",
    "schema_version": 1,
    "supported_operations": ["append_text", "replace_text", "create_file"],
    "default_mode": "draft",
    "apply_mode_allowed_by_this_skill": false,
    "notes": ["The implementation workflow defaults to draft mode unless apply mode is explicitly requested outside this skill."]
  },
  "packet_candidates": [
    {
      "id": "IMP-0001",
      "source_step_id": "STEP-0001",
      "task": "Update README install sentence.",
      "target_files": ["README.md"],
      "allowed_operations": ["replace_text"],
      "operation_intent": {
        "kind": "replace_text",
        "path": "README.md",
        "description": "Replace the approved installation sentence.",
        "requires_exact_old_text": false,
        "requires_content": false
      },
      "operation": {
        "kind": "replace_text",
        "path": "README.md",
        "old": "Install with Docker.",
        "new": "Install with Docker or Podman."
      },
      "source_refs": [
        {
          "path": "README.md",
          "line_range": [3, 3]
        }
      ],
      "acceptance_criteria": ["README mentions Docker or Podman."],
      "verification_requirements": [],
      "max_context_tokens": 4000,
      "notes": ""
    }
  ],
  "blocked_packets": [],
  "packet_file_preview": {
    "schema_version": 1,
    "packets": [
      {
        "id": "IMP-0001",
        "target_files": ["README.md"],
        "allowed_operations": ["replace_text"],
        "operation": {
          "kind": "replace_text",
          "path": "README.md",
          "old": "Install with Docker.",
          "new": "Install with Docker or Podman."
        },
        "source_refs": [
          {
            "path": "README.md",
            "line_range": [3, 3]
          }
        ],
        "acceptance_criteria": ["README mentions Docker or Podman."],
        "max_context_tokens": 4000,
        "notes": ""
      }
    ],
    "verification_commands": []
  },
  "next_step": {
    "suggested_skill": "verification-planner",
    "reason": "A packet candidate exists and verification selection still needs confirmation."
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
  "execution_plan": {
    "plan_id": "EP-0001",
    "plan_mode": "implementation_prep",
    "steps": [
      {
        "id": "STEP-0001",
        "action": "design_packet",
        "description": "Update README.",
        "target_files": ["README.md"],
        "acceptance_criteria": ["README is updated."],
        "blocked_by": []
      }
    ]
  },
  "approved_step_ids": [],
  "approval_refs": []
}
```

Output:

```json
{
  "packet_set_id": "IMPSET-0001",
  "source_plan_id": "EP-0001",
  "approval": {
    "status": "missing",
    "approved_step_ids": [],
    "approval_refs": []
  },
  "workflow_compatibility": {
    "target_workflow": "implementation.workflow",
    "schema_version": 1,
    "supported_operations": ["append_text", "replace_text", "create_file"],
    "default_mode": "draft",
    "apply_mode_allowed_by_this_skill": false,
    "notes": []
  },
  "packet_candidates": [],
  "blocked_packets": [
    {
      "source_step_id": "STEP-0001",
      "reason": "missing_approval",
      "needed_resolution": "User or controller must approve STEP-0001 before packet design."
    }
  ],
  "packet_file_preview": {
    "schema_version": 1,
    "packets": [],
    "verification_commands": []
  },
  "next_step": {
    "suggested_skill": "none",
    "reason": "Packet design is blocked until an approved step ID is provided."
  },
  "stop": {
    "required": true,
    "reason": "No execution-plan step is approved for packet design.",
    "open_questions": ["Which design_packet step ID is approved for packet candidate creation?"]
  }
}
```
