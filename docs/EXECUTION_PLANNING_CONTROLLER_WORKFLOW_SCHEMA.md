# Execution Planning Controller Workflow Schema

This document defines the implemented controller-owned `execution_planning.plan` workflow contract.

Status: implemented for the direct controller endpoint, controller harness adapter, explicit-envelope gateway route, and AnythingLLM routed dry-run path through `8300`.

The purpose is to keep the executable request contract explicit. The controller implementation is considered correct only if it accepts this envelope, writes these artifacts, preserves these safety rules, and passes the validation matrix in this document.

## Workflow Summary

`execution_planning.plan` turns an explicit planning request into bounded artifacts:

```text
explicit controller envelope
-> target-root and policy validation
-> deterministic skill chain
-> bounded context gathering
-> execution plan
-> optional draft packet preview
-> verification plan
-> feedback record
```

It must not run from ordinary natural language chat. It must not expose raw CodeGraphContext, shell, or repository-wide traversal to the model. It must not mutate the target repository.

## Controller Endpoint

Primary endpoint:

```text
POST /v1/controller/execution-planning/plans
```

Harness adapter path:

```text
POST /v1/controller/harness/chat/completions
```

The harness adapter must accept this workflow only inside an explicit `agentic_controller_request` envelope.

For message-content envelopes, the active envelope is the latest chat message containing exactly one `agentic_controller_request`. This supports repeated AnythingLLM testing in a workspace with prior controller-envelope history. Top-level plus message ambiguity and multiple envelopes inside the active message are still rejected.

## Request Schema

Required minimal request:

```json
{
  "workflow": "execution_planning.plan",
  "schema_version": 1,
  "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp",
  "user_request": "Prepare implementation packet candidates for an approved frozen-repo documentation clarification that client_order_id owns internal lookup paths, including StealthOrderManager placed-order index keys. Use draft mode only and do not mutate the frozen repository.",
  "mode": "implementation_prep",
  "approval": {
    "status": "approved_for_packet_design",
    "scope": "packet_design_only",
    "apply_allowed": false,
    "approval_refs": [
      "user:approved packet design only"
    ]
  },
  "context": {
    "entrypoint_hints": [
      {
        "path": "docs/agents/INVARIANTS.md",
        "symbol": null,
        "reason": "User-named documentation target."
      }
    ],
    "allowed_context_tools": [
      "structure_index",
      "git_grep",
      "read_file",
      "manual"
    ]
  },
  "packet_operations": [
    {
      "kind": "replace_text",
      "path": "docs/agents/INVARIANTS.md",
      "old": "- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, and DB\n  local rows.",
      "new": "- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, DB\n  local rows, and stealth manager placed-order index keys."
    }
  ],
  "budgets": {
    "max_context_requests": 5,
    "max_files": 10,
    "max_records": 50,
    "max_model_calls": 12,
    "max_output_tokens": 4600
  }
}
```

### Top-Level Fields

| Field | Required | Type | Rule |
| --- | --- | --- | --- |
| `workflow` | yes | string | Must be `execution_planning.plan`. |
| `schema_version` | yes | integer | Must be `1` for this draft. |
| `target_root` | yes | string | Must resolve under `CONTROLLER_ALLOWED_TARGET_ROOTS`. |
| `user_request` | yes | string | The exact user objective. Do not infer hidden objectives from chat history. |
| `mode` | yes | string | One of `investigation_only`, `implementation_prep`, or `dry_run`. |
| `skill_chain` | no | string array | If omitted, use the default nine-skill chain. Unsupported names fail before model calls. |
| `approval` | no | object | Required for implementation packet candidate creation. |
| `context` | no | object | Bounded hints and pre-supplied context. |
| `packet_operations` | mode-dependent | object array | Required for `implementation_prep` and `dry_run` in this controller version. Each operation must target a path under `target_root`; `replace_text.old` must exist before model calls. |
| `budgets` | no | object | Controller-enforced limits. Unsupported budget fields fail before model calls. |
| `output` | no | object | Compact response and artifact naming options. |
| `feedback` | no | object | Optional tester feedback to pass to `feedback-capture`. |

## Modes

`investigation_only`:

- Runs through planning only.
- May produce `request-triage`, `scope-and-assumptions`, `entrypoint-finder`, `context-plan`, `impact-map`, `execution-plan`, and `feedback-record`.
- Must not produce implementation packet candidates.
- Must not invoke `implementation.workflow`.

`implementation_prep`:

- Requires `approval.status: "approved_for_packet_design"`.
- Produces implementation packet candidates and a verification plan.
- May produce a packet file preview.
- Must not apply changes.

`dry_run`:

- Same as `implementation_prep`, plus the controller passes the model-produced packet preview to `implementation.workflow` in `draft` mode.
- Must verify selected target files are unchanged before returning success.
- Must record non-mutation proof in the response and artifacts.

## Default Skill Chain

When `skill_chain` is omitted, the controller uses:

```json
[
  "request-triage",
  "scope-and-assumptions",
  "entrypoint-finder",
  "context-plan-builder",
  "impact-map-builder",
  "execution-plan-writer",
  "implementation-packet-designer",
  "verification-planner",
  "feedback-capture"
]
```

Skill text is loaded by name from the project-local allowlisted skill root:

```text
.qwen/skills/<skill-name>/SKILL.md
```

The model receives one skill and one bounded input at a time. The controller validates required top-level keys after every model call. If a skill response is malformed JSON or misses required keys, the controller retries that skill once with a stricter prompt and counts the retry against `max_model_calls`; a second invalid response stops the workflow.

## Approval Object

```json
{
  "status": "none|approved_for_packet_design",
  "scope": "read_only|packet_design_only",
  "apply_allowed": false,
  "approval_refs": []
}
```

Rules:

- `apply_allowed` must be `false` in this workflow version.
- Packet candidate creation requires `approved_for_packet_design`.
- Apply mode is unsupported and must fail with `apply_mode_not_supported`.
- Feedback is not approval.
- The model may not convert a vague approval into broader scope.

## Packet Operations

`implementation_prep` and `dry_run` require explicit packet operations in this controller version:

```json
[
  {
    "kind": "replace_text",
    "path": "docs/agents/INVARIANTS.md",
    "old": "exact existing text",
    "new": "exact proposed text"
  }
]
```

Supported operation kinds:

- `replace_text`
- `append_text`
- `create_file`

Rules:

- Operation paths must stay under `target_root`.
- `replace_text.old` and `replace_text.new` must be strings.
- `replace_text.old` must be found in the target file before model calls begin.
- The controller passes operation details to the planning skills as bounded input; the model may package or explain the operation, but it does not get to invent a broader mutation path.
- `dry_run` passes the produced packet preview to `implementation.workflow` in `draft` mode only, then compares selected file hashes.

## Context Object

```json
{
  "entrypoint_hints": [
    {
      "path": "docs/agents/INVARIANTS.md",
      "symbol": null,
      "reason": "User-named documentation target."
    }
  ],
  "bounded_context": [
    {
      "id": "CTX-0001",
      "source": "read_file",
      "source_refs": [
        "docs/agents/INVARIANTS.md:11"
      ],
      "summary": "The invariant names client_order_id as the internal tracking owner."
    }
  ],
  "allowed_context_tools": [
    "structure_index",
    "git_grep",
    "read_file",
    "manual"
  ],
  "excluded_context": []
}
```

Allowed controller context tools for this workflow version:

- `structure_index`
- `git_grep`
- `read_file`
- `manual`

`codegraph_context` is available only through the narrow controller-owned `code_context.lookup` `relationship_queries` adapter in this phase. It remains excluded from direct `execution_planning.plan` context tools. Raw MCP tool names, raw Cypher, broad scans, package indexing, watcher control, bundle loading, and delete operations are not valid context tools.

## Budgets

```json
{
  "max_context_requests": 5,
  "max_files": 10,
  "max_records": 50,
  "max_model_calls": 12,
  "max_output_tokens": 4600,
  "timeout_seconds": 600
}
```

Rules:

- Unknown budget fields fail before execution.
- The controller owns budget enforcement.
- The model may recommend fewer requests, but it may not expand budgets.
- Exceeding a budget returns `budget_exceeded` with partial artifacts preserved.

## Artifact Layout

Artifacts are written under `CONTROLLER_OUTPUT_ROOT`, not under `target_root`:

```text
<CONTROLLER_OUTPUT_ROOT>/execution-planning/<run-id>/
  request.json
  request-triage.json
  scope-and-assumptions.json
  entrypoint-finder.json
  context-plan.json
  context-results.json
  impact-map.json
  execution-plan.json
  implementation-packet-candidates.json
  packet-preview.json
  verification-plan.json
  implementation-workflow-report.json
  feedback-record.json
  run-state.json
```

Mode-specific artifact rules:

- `investigation_only` omits packet, verification, and implementation workflow artifacts unless a stopped plan needs feedback.
- `implementation_prep` may write `packet-preview.json` but does not invoke `implementation.workflow`.
- `dry_run` writes `implementation-workflow-report.json` after invoking `implementation.workflow` in draft mode.

## Response Schema

Compact response:

```json
{
  "run_id": "20260603T120000000000Z",
  "workflow": "execution_planning.plan",
  "status": "completed",
  "mode": "dry_run",
  "artifacts": {
    "request": ".../request.json",
    "request_triage": ".../request-triage.json",
    "scope_and_assumptions": ".../scope-and-assumptions.json",
    "entrypoint_finder": ".../entrypoint-finder.json",
    "context_plan": ".../context-plan.json",
    "context_results": ".../context-results.json",
    "impact_map": ".../impact-map.json",
    "execution_plan": ".../execution-plan.json",
    "implementation_packet_candidates": ".../implementation-packet-candidates.json",
    "packet_preview": ".../packet-preview.json",
    "verification_plan": ".../verification-plan.json",
    "implementation_workflow_report": ".../implementation-workflow-report.json",
    "feedback_record": ".../feedback-record.json",
    "run_state": ".../run-state.json"
  },
  "summary": {
    "request_type": "documentation",
    "selected_entrypoint": {
      "path": "docs/agents/INVARIANTS.md",
      "symbol": null,
      "confidence": "high"
    },
    "plan_mode": "implementation_prep",
    "packet_candidates": 1,
    "verification_commands": [
      [
        "python",
        "-m",
        "pytest",
        "tests/unit/test_order_id_and_followup_rules.py"
      ]
    ],
    "repo_mutated": false,
    "next_required_decision": "review packet preview and approve or reject follow-up work"
  },
  "warnings": [],
  "failures": [],
  "resume_key": {
    "schema_version": 1,
    "run_state": ".../run-state.json"
  },
  "tool_policy": {
    "workflow": "execution_planning.plan",
    "role_id": "architect/default",
    "controller_tool_ids": [
      "structure_index",
      "git_grep",
      "read_file"
    ],
    "model_visible_tool_ids": [],
    "denied_tool_ids": [],
    "controller_actions": []
  },
  "non_mutation": {
    "checked": true,
    "selected_files": [
      "docs/agents/INVARIANTS.md",
      "core/stealth_order_manager.py",
      "tests/unit/test_order_id_and_followup_rules.py",
      "tests/regression/test_order_id_regression.py"
    ],
    "changed_files": []
  }
}
```

## Harness Response

The harness adapter returns the normal OpenAI-style chat completion wrapper plus `agentic_controller_response`:

```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "execution_planning.plan completed. Artifacts were written under .../execution-planning/<run-id>."
      }
    }
  ],
  "agentic_controller_response": {
    "run_id": "20260603T120000000000Z",
    "workflow": "execution_planning.plan",
    "status": "completed",
    "artifacts": {},
    "summary": {}
  }
}
```

The assistant message must stay compact. Full details stay in artifact files.

## Refusal Cases

| Code | Condition |
| --- | --- |
| `unsupported_workflow` | `workflow` is not `execution_planning.plan` on the direct endpoint. |
| `missing_controller_envelope` | Harness request does not contain `agentic_controller_request`. |
| `target_root_not_allowed` | `target_root` is outside `CONTROLLER_ALLOWED_TARGET_ROOTS`. |
| `unsupported_mode` | `mode` is not one of the schema modes. |
| `unsupported_skill` | `skill_chain` names a skill outside the allowlist. |
| `missing_skill` | A required `SKILL.md` is absent. |
| `unsupported_context_tool` | Request or model output asks for a disallowed context tool. |
| `raw_codegraph_not_allowed` | Request asks for raw CodeGraphContext, raw Cypher, indexing control, watcher control, or package indexing. |
| `missing_packet_design_approval` | Packet creation is requested without packet-design approval. |
| `missing_packet_operations` | `implementation_prep` or `dry_run` omits explicit packet operations. |
| `apply_mode_not_supported` | Request asks to apply edits or approve repository mutation. |
| `budget_exceeded` | Controller budget is exhausted before completion. |
| `invalid_skill_output` | Model output is not parseable JSON or misses required top-level keys after the bounded retry. |
| `draft_mutation_detected` | Selected target file hashes changed during a dry run. |

## Tool Policy

`runtime/workflows.json` includes:

```json
{
  "id": "execution_planning.plan",
  "description": "Controller-owned execution planning through bounded project-local skills.",
  "default_role_id": "architect/default",
  "allowed_role_ids": [
    "architect/default"
  ],
  "controller_tool_ids": [
    "structure_index",
    "git_grep",
    "read_file"
  ],
  "conditional_controller_tool_ids": [],
  "controller_actions": [
    {
      "tool_id": "structure_index",
      "action": "discover_symbols_and_file_structure",
      "scope": "target_root",
      "result_artifacts": [
        "context_results",
        "impact_map"
      ]
    },
    {
      "tool_id": "git_grep",
      "action": "bounded_exact_string_lookup",
      "scope": "target_root",
      "result_artifacts": [
        "context_results",
        "impact_map"
      ]
    },
    {
      "tool_id": "read_file",
      "action": "read_selected_context_files",
      "scope": "target_root",
      "result_artifacts": [
        "context_results",
        "execution_plan"
      ]
    }
  ],
  "model_visible_tool_ids": []
}
```

If `implementation.workflow` is invoked in `dry_run`, it is invoked by the controller as an internal workflow call, not as a model-visible tool.

## Validation Matrix

Minimum implementation proof:

1. Direct controller endpoint accepts a valid `dry_run` request. Covered by regression.
2. Direct controller endpoint rejects apply mode. Covered by regression.
3. Direct controller endpoint rejects raw CodeGraphContext requests. Covered by regression.
4. Harness adapter accepts top-level `agentic_controller_request`. Covered by regression.
5. Harness adapter accepts message-content JSON `agentic_controller_request` and selects the latest message envelope when older history contains prior envelopes. Covered by regression and live AnythingLLM validation.
6. Harness adapter rejects ordinary natural language. Covered by regression.
7. Bash-side request through the current controller stack completes. Live validation passed.
8. AnythingLLM can send the explicit envelope and receive bounded artifacts. Live dry-run validation passed through gateway `8300` for both frozen fixtures.
9. Frozen Coinbase repo selected file hashes remain unchanged. Covered by regression and live matrix validation.
10. `pytest tests/regression/ -v` passes after implementation. Required for completion.

## Implementation Boundary

The workflow currently prepares plans and packet previews only. Apply behavior remains outside this workflow and must go through the existing `implementation.workflow` apply policy after separate approval.
