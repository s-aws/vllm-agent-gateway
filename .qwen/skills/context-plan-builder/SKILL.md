---
name: context-plan-builder
description: Build a bounded context-gathering plan from scoped objectives, selected entry points, and follow-up context needs before impact mapping or execution planning. Use after entrypoint-finder when the agent must decide which deterministic context requests are needed without invoking tools, reading files, or expanding repository traversal.
---

# Context Plan Builder

Use this skill after `entrypoint-finder` when there is a selected entry point or a clear bounded lookup need.

This skill continues problem-solving Step 4: identify and validate possible causes by deciding what data is needed. It does not gather the data, validate root cause, plan edits, or run tools.

## Inputs

Use only:

- scoped objective and stop conditions from `scope-and-assumptions`
- anchors, selected entry point, candidates, and follow-up needs from `entrypoint-finder`
- allowed tool names from runtime or controller policy
- user-named files, symbols, commands, routes, workflows, or tests
- bounded context results already available

## Workflow

1. Refuse to proceed if `entrypoint-finder.stop.required` is true.
2. Confirm that each requested context item has a bounded purpose.
3. Convert follow-up needs into explicit context requests.
4. Prefer deterministic structure and exact-string lookup before file reads.
5. Only request `read_file` for a specific known file and a specific reason.
6. Keep each request small enough for a smaller model or controller to execute and inspect.
7. Order requests so broadest-safe discovery happens before targeted reads.
8. Record excluded or deferred context that would be unsafe, unbounded, unavailable, or premature.
9. Route to impact mapping only when the plan has enough bounded requests to validate affected paths.

## Tool Selection

Use exactly one suggested tool per context request:

- `structure_index`: symbols, imports, config keys, document links, known file structure.
- `git_grep`: exact strings, routes, workflow IDs, command names, status names, test names.
- `read_file`: one known repo-relative file for a narrow purpose.
- `codegraph_context`: relationship questions only after a curated read-only adapter exists.
- `manual`: user clarification or a non-tool decision.

Do not suggest raw MCP tools, shell commands, unbounded scans, repository-wide reads, or generated artifact reads unless the artifact was explicitly named and is relevant.

## Output

Return exactly one JSON object:

```json
{
  "context_plan_id": "CTXPLAN-0001",
  "entrypoint": {
    "path": "repo-relative path or null",
    "symbol": "name or null",
    "confidence": "medium|high|null"
  },
  "context_requests": [
    {
      "id": "CTX-0001",
      "purpose": "callers|callees|tests|config|docs|imports|similar_code|route_handler|workflow_policy|file_structure|manual_clarification",
      "suggested_tool": "structure_index|git_grep|read_file|codegraph_context|manual",
      "query": "bounded query or null",
      "targets": [],
      "max_results": 25,
      "max_files": 5,
      "required": true,
      "reason": "why this context is needed",
      "safety_constraints": []
    }
  ],
  "request_order": ["CTX-0001"],
  "context_budget": {
    "max_requests": 5,
    "max_files": 10,
    "max_records": 50,
    "allow_broad_scan": false
  },
  "excluded_context": [
    {
      "purpose": "string",
      "reason": "unsafe|unbounded|premature|unavailable|not_relevant"
    }
  ],
  "next_step": {
    "suggested_skill": "impact-map-builder|entrypoint-finder|none",
    "reason": "short explanation"
  },
  "stop": {
    "required": false,
    "reason": "string or null",
    "open_questions": []
  }
}
```

Use empty arrays when there is no item. Use `null` for unknown selected-entrypoint values.

## Request Rules

- Assign request IDs sequentially as `CTX-0001`, `CTX-0002`, and so on.
- Keep `context_requests` at or below `context_budget.max_requests`.
- Keep `targets` repo-relative when paths are present.
- Set `required` to `true` only for context needed before impact mapping.
- Put speculative or nice-to-have context in `excluded_context` unless it is bounded and clearly useful.
- Use `manual` when the next safe action is a user decision, not a tool lookup.
- Do not include both broad search and read requests for the same uncertainty unless the read target is already known.

## Ordering

Use this order unless the input gives a stronger reason:

1. `structure_index` for a known file or symbol.
2. `git_grep` for exact strings that identify related paths.
3. `read_file` for one known file after structure or grep identifies the narrow target.
4. `codegraph_context` for caller/callee relationships only through a curated adapter.
5. `manual` when the plan is blocked by ambiguity or approval.

## Routing

- Route to `impact-map-builder` when the plan contains bounded requests that can validate behavior paths, affected files, tests, or duplicate paths.
- Route back to `entrypoint-finder` when the plan only discovers an entry point and no selected entry point exists.
- Route to `none` when the request is blocked, unbounded, unsafe, or missing approval.

## Must Not

- Do not invoke tools.
- Do not read files.
- Do not claim source evidence.
- Do not identify root cause.
- Do not create implementation steps.
- Do not choose verification commands beyond test-discovery context requests.
- Do not request unbounded scans.
- Do not expose raw CodeGraphContext MCP operations.
- Do not request writes, apply mode, broad traversal, or unsafe commands.
- Do not proceed when containment is blocked.

## Examples

Input context:

```json
{
  "selected_entrypoint": {
    "path": "vllm_agent_gateway/controller_service/server.py",
    "symbol": null,
    "confidence": "medium"
  },
  "followup_context_needed": [
    {
      "purpose": "callees",
      "suggested_tool": "structure_index",
      "query": "vllm_agent_gateway/controller_service/server.py",
      "max_results": 25,
      "reason": "Need function-level structure before impact mapping."
    },
    {
      "purpose": "tests",
      "suggested_tool": "git_grep",
      "query": "run status",
      "max_results": 25,
      "reason": "Need related tests before planning changes."
    }
  ]
}
```

Output:

```json
{
  "context_plan_id": "CTXPLAN-0001",
  "entrypoint": {
    "path": "vllm_agent_gateway/controller_service/server.py",
    "symbol": null,
    "confidence": "medium"
  },
  "context_requests": [
    {
      "id": "CTX-0001",
      "purpose": "file_structure",
      "suggested_tool": "structure_index",
      "query": "vllm_agent_gateway/controller_service/server.py",
      "targets": ["vllm_agent_gateway/controller_service/server.py"],
      "max_results": 25,
      "max_files": 1,
      "required": true,
      "reason": "Function-level structure is needed before impact mapping.",
      "safety_constraints": ["Read-only structure index only.", "Do not read full repository."]
    },
    {
      "id": "CTX-0002",
      "purpose": "tests",
      "suggested_tool": "git_grep",
      "query": "run status",
      "targets": ["tests/regression"],
      "max_results": 25,
      "max_files": 5,
      "required": true,
      "reason": "Related tests are needed before planning behavior-preserving changes.",
      "safety_constraints": ["Exact-string search only.", "Do not run tests from this skill."]
    }
  ],
  "request_order": ["CTX-0001", "CTX-0002"],
  "context_budget": {
    "max_requests": 5,
    "max_files": 10,
    "max_records": 50,
    "allow_broad_scan": false
  },
  "excluded_context": [
    {
      "purpose": "callers",
      "reason": "unavailable"
    }
  ],
  "next_step": {
    "suggested_skill": "impact-map-builder",
    "reason": "The planned requests can identify structure and related tests for impact mapping."
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
  "selected_entrypoint": {
    "path": null,
    "symbol": null,
    "confidence": null
  },
  "followup_context_needed": [
    {
      "purpose": "similar_code",
      "suggested_tool": "git_grep",
      "query": "run status",
      "max_results": 25,
      "reason": "A bounded exact-string search is needed before selecting a code entry point."
    }
  ]
}
```

Output:

```json
{
  "context_plan_id": "CTXPLAN-0001",
  "entrypoint": {
    "path": null,
    "symbol": null,
    "confidence": null
  },
  "context_requests": [
    {
      "id": "CTX-0001",
      "purpose": "similar_code",
      "suggested_tool": "git_grep",
      "query": "run status",
      "targets": [],
      "max_results": 25,
      "max_files": 5,
      "required": true,
      "reason": "An exact-string lookup is needed before an entry point can be selected.",
      "safety_constraints": ["Search only.", "Do not read files yet."]
    }
  ],
  "request_order": ["CTX-0001"],
  "context_budget": {
    "max_requests": 5,
    "max_files": 10,
    "max_records": 50,
    "allow_broad_scan": false
  },
  "excluded_context": [],
  "next_step": {
    "suggested_skill": "entrypoint-finder",
    "reason": "The lookup is intended to produce entrypoint candidates before impact mapping."
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
  "stop": {
    "required": true,
    "reason": "The problem target is unspecified."
  }
}
```

Output:

```json
{
  "context_plan_id": "CTXPLAN-0001",
  "entrypoint": {
    "path": null,
    "symbol": null,
    "confidence": null
  },
  "context_requests": [],
  "request_order": [],
  "context_budget": {
    "max_requests": 5,
    "max_files": 10,
    "max_records": 50,
    "allow_broad_scan": false
  },
  "excluded_context": [],
  "next_step": {
    "suggested_skill": "none",
    "reason": "Context planning is blocked because the prior step requires a stop."
  },
  "stop": {
    "required": true,
    "reason": "The problem target is unspecified.",
    "open_questions": []
  }
}
```
