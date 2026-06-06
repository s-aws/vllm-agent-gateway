---
name: impact-map-builder
description: Build a read-only impact map from scoped objectives, selected entry points, bounded context plans, and completed context results before execution-plan-writer. Use after context-plan-builder when the agent must summarize affected behavior paths, files, symbols, dependencies, tests, duplicate or parallel paths, risks, and unknowns without invoking tools, editing files, deciding implementation order, or hiding uncertainty.
---

# Impact Map Builder

Use this skill after `context-plan-builder` and completed bounded context gathering.

This skill completes the evidence-mapping part of problem-solving Step 4: identify possible causes, affected paths, and validating evidence. It does not gather more context, plan implementation steps, run tests, invoke tools, or decide the edit sequence.

## Inputs

Use only:

- request classification from `request-triage`
- problem, goal, scope, assumptions, approvals, and stop conditions from `scope-and-assumptions`
- selected entry point and candidates from `entrypoint-finder`
- context requests from `context-plan-builder`
- completed bounded context results with source references
- user-named files, symbols, workflows, tests, or constraints

If completed context results are missing, produce a stopped impact map that routes back to `context-plan-builder` or `execution-plan-writer` with a `gather_context` step. Do not invent affected files from intuition.

## Workflow

1. Refuse to proceed if any prior `stop.required` is true.
2. Confirm that completed context results exist and include source references.
3. Extract behavior paths from entry point through callers, callees, workflows, routes, commands, tests, or configs.
4. Record affected files only when named by the user or supported by bounded context.
5. Record affected symbols only when supported by bounded context.
6. Record dependencies as read-only relationships, not as proposed changes.
7. Record related tests only when a context result identifies a test file, test symbol, assertion, fixture, or test gap.
8. Record duplicate or parallel paths only when two paths have explicit evidence for shared behavior, shared branch conditions, shared status handling, or repeated logic.
9. Attach evidence references to every non-empty claim.
10. Put unsupported possibilities in `unknowns`, not in affected files or duplicate paths.
11. Route to `execution-plan-writer` only when the impact map is specific enough to support an action plan.

## Evidence Rules

Use source references as strings from the available bounded context, such as:

- `path/to/file.py:42`
- `path/to/file.py:function_name`
- `context_result:CTX-0002`
- `user_request`

If a source reference is unavailable, set `stop.required` to `true` unless the item is explicitly recorded as an unknown.

Use confidence conservatively:

- `high`: direct source reference identifies the path, symbol, or test and its role.
- `medium`: bounded context identifies the item, but its role needs confirmation.
- `low`: item is a plausible candidate from bounded context but not enough to plan edits.

Do not use high confidence for duplicate or parallel paths unless both sides have evidence and the shared behavior is stated.

## Output

Return exactly one JSON object:

```json
{
  "impact_map_id": "IMPACT-0001",
  "objective": "one sentence",
  "basis": {
    "request_type": "investigation|implementation|refactor|test_fix|documentation|workflow|unknown",
    "entrypoint": {
      "path": "repo-relative path or null",
      "symbol": "name or null",
      "confidence": "low|medium|high|null"
    },
    "context_plan_id": "CTXPLAN-0001 or null",
    "context_result_refs": []
  },
  "behavior_paths": [
    {
      "id": "PATH-0001",
      "name": "short behavior name",
      "entrypoint_ref": "path, symbol, context result, or null",
      "path_refs": [],
      "role": "primary|alternate|error|test|config|unknown",
      "confidence": "low|medium|high",
      "evidence_refs": [],
      "notes": []
    }
  ],
  "affected_files": [
    {
      "path": "repo-relative path",
      "role": "entrypoint|caller|callee|test|config|doc|workflow|unknown",
      "reason": "why this file is affected",
      "confidence": "low|medium|high",
      "evidence_refs": []
    }
  ],
  "affected_symbols": [
    {
      "path": "repo-relative path",
      "symbol": "name or null",
      "kind": "function|class|method|route|command|workflow|test|config|unknown",
      "role": "entrypoint|caller|callee|state_owner|adapter|validator|test|unknown",
      "confidence": "low|medium|high",
      "evidence_refs": []
    }
  ],
  "dependencies": [
    {
      "from": "path/symbol or context result",
      "to": "path/symbol or context result",
      "relationship": "calls|imports|configures|tests|documents|emits|consumes|unknown",
      "confidence": "low|medium|high",
      "evidence_refs": []
    }
  ],
  "related_tests": [
    {
      "path": "repo-relative path or null",
      "test_name": "name or null",
      "coverage_for": [],
      "status": "existing|missing|unknown",
      "confidence": "low|medium|high",
      "evidence_refs": []
    }
  ],
  "duplicate_or_parallel_paths": [
    {
      "id": "DUP-0001",
      "path_a_refs": [],
      "path_b_refs": [],
      "shared_behavior": "specific shared behavior or null",
      "duplication_confidence": "low|medium|high",
      "requires_confirmation": [],
      "evidence_refs": []
    }
  ],
  "risks": [
    {
      "id": "RISK-0001",
      "risk": "specific risk",
      "severity": "low|medium|high",
      "affected_refs": [],
      "mitigation_needed": "what must be checked before implementation",
      "evidence_refs": []
    }
  ],
  "unknowns": [
    {
      "id": "UNK-0001",
      "unknown": "specific unknown",
      "why_it_matters": "planning consequence",
      "needed_context": "bounded context needed or user decision",
      "blocks_execution_plan": true
    }
  ],
  "next_step": {
    "suggested_skill": "execution-plan-writer|context-plan-builder|entrypoint-finder|none",
    "reason": "short explanation"
  },
  "stop": {
    "required": false,
    "reason": "string or null",
    "open_questions": []
  }
}
```

Use empty arrays when there is no item. Use `null` for unknown scalar values.

## Routing

- Route to `execution-plan-writer` when affected paths, files, symbols, tests, risks, and unknowns are specific enough to create an investigation or implementation-prep plan.
- Route to `context-plan-builder` when missing context can be requested with bounded read-only requests.
- Route to `entrypoint-finder` when no defensible entry point exists.
- Route to `none` when the work is blocked by unsafe scope, missing user intent, missing approval, or prior stop conditions.

## Must Not

- Do not invoke tools.
- Do not read files.
- Do not run tests.
- Do not edit files.
- Do not propose implementation steps.
- Do not decide patch order.
- Do not invent source references.
- Do not hide uncertainty.
- Do not treat similar names as duplicate behavior without explicit evidence.
- Do not mark root cause confirmed unless the bounded context directly validates it.
- Do not expand beyond the context budget from `context-plan-builder`.

## Examples

Input context:

```json
{
  "request_type": "refactor",
  "objective": "Determine whether controller-service run status handling has duplicate behavior paths.",
  "entrypoint": {
    "path": "vllm_agent_gateway/controller_service/server.py",
    "symbol": "get_run_status",
    "confidence": "medium"
  },
  "context_plan_id": "CTXPLAN-0001",
  "context_results": [
    {
      "id": "CTX-0001",
      "summary": "server.py defines get_run_status and _serialize_run_status.",
      "source_refs": [
        "vllm_agent_gateway/controller_service/server.py:get_run_status",
        "vllm_agent_gateway/controller_service/server.py:_serialize_run_status"
      ]
    },
    {
      "id": "CTX-0002",
      "summary": "test_controller_service.py asserts run status lookup responses.",
      "source_refs": [
        "tests/regression/test_controller_service.py:test_get_run_status"
      ]
    }
  ]
}
```

Output:

```json
{
  "impact_map_id": "IMPACT-0001",
  "objective": "Map controller-service run status handling before planning a duplicate-path refactor.",
  "basis": {
    "request_type": "refactor",
    "entrypoint": {
      "path": "vllm_agent_gateway/controller_service/server.py",
      "symbol": "get_run_status",
      "confidence": "medium"
    },
    "context_plan_id": "CTXPLAN-0001",
    "context_result_refs": ["CTX-0001", "CTX-0002"]
  },
  "behavior_paths": [
    {
      "id": "PATH-0001",
      "name": "Controller-service run status lookup",
      "entrypoint_ref": "vllm_agent_gateway/controller_service/server.py:get_run_status",
      "path_refs": ["vllm_agent_gateway/controller_service/server.py:get_run_status", "vllm_agent_gateway/controller_service/server.py:_serialize_run_status"],
      "role": "primary",
      "confidence": "medium",
      "evidence_refs": ["context_result:CTX-0001"],
      "notes": []
    }
  ],
  "affected_files": [
    {
      "path": "vllm_agent_gateway/controller_service/server.py",
      "role": "entrypoint",
      "reason": "The bounded context identifies run status lookup and serialization in this file.",
      "confidence": "medium",
      "evidence_refs": ["context_result:CTX-0001"]
    },
    {
      "path": "tests/regression/test_controller_service.py",
      "role": "test",
      "reason": "The bounded context identifies an existing run status lookup regression test.",
      "confidence": "medium",
      "evidence_refs": ["context_result:CTX-0002"]
    }
  ],
  "affected_symbols": [
    {
      "path": "vllm_agent_gateway/controller_service/server.py",
      "symbol": "get_run_status",
      "kind": "function",
      "role": "entrypoint",
      "confidence": "medium",
      "evidence_refs": ["vllm_agent_gateway/controller_service/server.py:get_run_status"]
    },
    {
      "path": "vllm_agent_gateway/controller_service/server.py",
      "symbol": "_serialize_run_status",
      "kind": "function",
      "role": "callee",
      "confidence": "medium",
      "evidence_refs": ["vllm_agent_gateway/controller_service/server.py:_serialize_run_status"]
    }
  ],
  "dependencies": [
    {
      "from": "vllm_agent_gateway/controller_service/server.py:get_run_status",
      "to": "vllm_agent_gateway/controller_service/server.py:_serialize_run_status",
      "relationship": "calls",
      "confidence": "medium",
      "evidence_refs": ["context_result:CTX-0001"]
    }
  ],
  "related_tests": [
    {
      "path": "tests/regression/test_controller_service.py",
      "test_name": "test_get_run_status",
      "coverage_for": ["vllm_agent_gateway/controller_service/server.py:get_run_status"],
      "status": "existing",
      "confidence": "medium",
      "evidence_refs": ["tests/regression/test_controller_service.py:test_get_run_status"]
    }
  ],
  "duplicate_or_parallel_paths": [],
  "risks": [
    {
      "id": "RISK-0001",
      "risk": "Changing serialization without mapping all callers could alter controller-service responses.",
      "severity": "medium",
      "affected_refs": ["vllm_agent_gateway/controller_service/server.py:_serialize_run_status"],
      "mitigation_needed": "Confirm callers and response tests before implementation packet design.",
      "evidence_refs": ["context_result:CTX-0001"]
    }
  ],
  "unknowns": [
    {
      "id": "UNK-0001",
      "unknown": "Whether another status serialization path exists outside the bounded context.",
      "why_it_matters": "A single-path refactor cannot be planned until parallel paths are confirmed or ruled out.",
      "needed_context": "Bounded exact-string or structure lookup for status serialization references.",
      "blocks_execution_plan": false
    }
  ],
  "next_step": {
    "suggested_skill": "execution-plan-writer",
    "reason": "The impact map identifies affected files, symbols, tests, risks, and remaining unknowns."
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
  "request_type": "refactor",
  "objective": "Make this have one path.",
  "entrypoint": {
    "path": null,
    "symbol": null,
    "confidence": null
  },
  "context_results": []
}
```

Output:

```json
{
  "impact_map_id": "IMPACT-0001",
  "objective": "Make this have one path.",
  "basis": {
    "request_type": "refactor",
    "entrypoint": {
      "path": null,
      "symbol": null,
      "confidence": null
    },
    "context_plan_id": null,
    "context_result_refs": []
  },
  "behavior_paths": [],
  "affected_files": [],
  "affected_symbols": [],
  "dependencies": [],
  "related_tests": [],
  "duplicate_or_parallel_paths": [],
  "risks": [],
  "unknowns": [
    {
      "id": "UNK-0001",
      "unknown": "The target behavior and entry point are unspecified.",
      "why_it_matters": "Impact cannot be mapped without a behavior target or bounded context.",
      "needed_context": "User must identify the behavior, file, symbol, command, workflow, or test target.",
      "blocks_execution_plan": true
    }
  ],
  "next_step": {
    "suggested_skill": "entrypoint-finder",
    "reason": "A defensible entry point is required before impact mapping."
  },
  "stop": {
    "required": true,
    "reason": "Impact mapping is blocked because no entry point or completed context results are available.",
    "open_questions": ["What behavior, file, symbol, command, workflow, or test should be mapped?"]
  }
}
```
