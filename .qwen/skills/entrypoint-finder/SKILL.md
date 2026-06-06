---
name: entrypoint-finder
description: Identify likely logic entry points for a scoped behavior, workflow, endpoint, command, class, function, test failure, documentation path, or refactor target before broad context gathering or execution planning. Use after scope-and-assumptions when the task needs a read-only starting point for investigation.
---

# Entrypoint Finder

Use this skill after `scope-and-assumptions` when the next safe step is to find where investigation should begin.

This skill covers the first part of problem-solving Step 4: identify possible causes by finding the logic beginning point. It does not validate root cause, plan actions, or implement changes.

## Inputs

Use only information already available from the user, `request-triage`, `scope-and-assumptions`, and explicitly allowed bounded context results.

Useful inputs include:

- scoped objective
- request type
- known symbol, route, command, file, class, function, test name, or behavior phrase
- available data and needed data from `scope-and-assumptions`
- allowed context tools
- containment and stop conditions

## Workflow

1. Extract explicit anchors from the scoped request: symbol names, commands, routes, filenames, workflow IDs, error names, test names, or behavior phrases.
2. Classify each anchor by kind.
3. Propose the smallest bounded lookup needed for each anchor.
4. Record candidate entry points only when there is direct user-provided evidence or a bounded context result.
5. Assign confidence based on evidence quality.
6. Select one entry point only when confidence is `medium` or `high`.
7. Recommend the next bounded context needed to confirm callers, callees, tests, configs, docs, or duplicate paths.
8. Stop when confidence is low or required context is unavailable.

## Anchor Kinds

Use exactly one kind per anchor:

- `symbol`: function, method, class, constant, enum, or variable name.
- `route`: HTTP route, API path, CLI route, controller endpoint, or message path.
- `command`: CLI command, script name, startup command, or test command.
- `file`: explicit repo-relative file path or filename.
- `workflow`: controller workflow ID, role ID, phase, or named process.
- `test`: test file, test function, CI check, or failure name.
- `behavior`: plain-language behavior when no stronger anchor exists.
- `unknown`: anchor cannot be classified safely.

## Confidence

- `high`: exact path and symbol, route, command, workflow ID, or test name is available from the user or bounded context.
- `medium`: likely path or symbol is available, but callers, callees, or related files still need confirmation.
- `low`: only plain-language behavior is available, or multiple unrelated candidates remain.

Do not select a `low` confidence candidate as the entry point.

## Output

Return exactly one JSON object:

```json
{
  "anchors": [
    {
      "value": "string",
      "kind": "symbol|route|command|file|workflow|test|behavior|unknown",
      "source": "user|scope-and-assumptions|bounded_context",
      "reason": "short explanation"
    }
  ],
  "entrypoint_candidates": [
    {
      "path": "repo-relative path or unknown",
      "symbol": "name or null",
      "kind": "module|function|class|method|route|command|workflow|test|document|unknown",
      "line_range": [1, 1],
      "confidence": "low|medium|high",
      "basis": "source reference or bounded context result",
      "needs_confirmation": []
    }
  ],
  "selected_entrypoint": {
    "path": "repo-relative path or null",
    "symbol": "name or null",
    "confidence": "medium|high|null",
    "selection_reason": "short explanation or null"
  },
  "followup_context_needed": [
    {
      "purpose": "callers|callees|tests|config|docs|imports|similar_code|route_handler|workflow_policy",
      "suggested_tool": "structure_index|git_grep|read_file|codegraph_context|manual",
      "query": "bounded query",
      "max_results": 25,
      "reason": "why this context is needed"
    }
  ],
  "stop": {
    "required": false,
    "reason": "string or null",
    "open_questions": []
  }
}
```

Use `null` for unknown selected-entrypoint values. Use `unknown` for unknown candidate path values.

## Tool Guidance

This skill may recommend tools, but it must not invoke them.

Prefer recommendations in this order:

1. `structure_index` for known files, symbols, imports, config keys, or document links.
2. `git_grep` for exact strings, routes, workflow IDs, command names, or test names.
3. `read_file` only for a specific known file and bounded purpose.
4. `codegraph_context` only for relationship questions after a narrow adapter exists.
5. `manual` when user clarification is needed before safe lookup.

Never recommend raw CodeGraphContext MCP operations, broad repository scans, or generated artifact reads unless the artifact is explicitly named and relevant.

## Routing

- Route to `context-plan-builder` when a `medium` or `high` confidence entry point is selected and more bounded context is needed.
- Route to `execution-plan-writer` only when the entry point is `high` confidence and the task has enough evidence to plan without more context.
- Route to `none` through `stop.required = true` when confidence is low, anchors are missing, containment blocks progress, or approval is required.

## Must Not

- Do not read files.
- Do not invoke tools.
- Do not claim source evidence without a source reference or bounded context result.
- Do not select low-confidence candidates.
- Do not identify root cause.
- Do not create implementation steps.
- Do not choose verification commands.
- Do not approve writes, apply mode, broad traversal, or unsafe commands.
- Do not continue when `scope-and-assumptions` says containment is blocked.

## Examples

Input context:

```json
{
  "request_type": "refactor",
  "scope": {
    "in_scope": ["Read-only investigation of controller service run status behavior."],
    "stop_conditions": ["Unable to identify a likely entry point with bounded context."]
  },
  "needed_data": ["Current logic entry point.", "Known run status paths.", "Related tests."],
  "user_request": "Refactor the controller service so run status is handled through one path."
}
```

Output:

```json
{
  "anchors": [
    {
      "value": "controller service",
      "kind": "workflow",
      "source": "user",
      "reason": "The user named the controller service as the target area."
    },
    {
      "value": "run status",
      "kind": "behavior",
      "source": "user",
      "reason": "The user named the behavior to investigate."
    }
  ],
  "entrypoint_candidates": [],
  "selected_entrypoint": {
    "path": null,
    "symbol": null,
    "confidence": null,
    "selection_reason": null
  },
  "followup_context_needed": [
    {
      "purpose": "similar_code",
      "suggested_tool": "git_grep",
      "query": "run status",
      "max_results": 25,
      "reason": "A bounded exact-string search is needed before selecting a code entry point."
    },
    {
      "purpose": "workflow_policy",
      "suggested_tool": "git_grep",
      "query": "controller_service",
      "max_results": 25,
      "reason": "The request names controller service behavior but no file or symbol."
    }
  ],
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
  "scope": {
    "in_scope": ["Read-only investigation of controller service run status behavior."]
  },
  "bounded_context": [
    {
      "tool": "git_grep",
      "query": "run status",
      "matches": ["vllm_agent_gateway/controller_service/server.py:257:        \"status\": value.get(\"status\")"]
    }
  ]
}
```

Output:

```json
{
  "anchors": [
    {
      "value": "vllm_agent_gateway/controller_service/server.py",
      "kind": "file",
      "source": "bounded_context",
      "reason": "Bounded search returned a controller service file containing status handling."
    }
  ],
  "entrypoint_candidates": [
    {
      "path": "vllm_agent_gateway/controller_service/server.py",
      "symbol": null,
      "kind": "module",
      "line_range": [257, 257],
      "confidence": "medium",
      "basis": "git_grep match for run status handling",
      "needs_confirmation": ["Find surrounding function.", "Find callers and related tests."]
    }
  ],
  "selected_entrypoint": {
    "path": "vllm_agent_gateway/controller_service/server.py",
    "symbol": null,
    "confidence": "medium",
    "selection_reason": "The bounded search found the target behavior in the controller service module."
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
  ],
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
  "user_request": "Fix it.",
  "scope": {
    "stop_conditions": ["Problem target remains unspecified."]
  }
}
```

Output:

```json
{
  "anchors": [],
  "entrypoint_candidates": [],
  "selected_entrypoint": {
    "path": null,
    "symbol": null,
    "confidence": null,
    "selection_reason": null
  },
  "followup_context_needed": [],
  "stop": {
    "required": true,
    "reason": "The problem target is unspecified, so no safe entry point can be identified.",
    "open_questions": ["What behavior, file, command, workflow, or test should be investigated?"]
  }
}
```
