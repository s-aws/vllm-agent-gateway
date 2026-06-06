---
name: codegraph-context-lookup
description: Create bounded curated relationship lookup requests for code_context.lookup when a task needs callers, callees, imports, or module dependency context for a known path, symbol, or module. Use after entrypoint-finder or context-plan-builder when the agent must decide whether to request the controller-owned codegraph_context adapter; never use for raw CodeGraphContext MCP, Cypher, indexing, watching, deletion, package loading, visualization, broad repo traversal, edits, or tests.
---

# Codegraph Context Lookup

Use this skill when a scoped investigation, impact map, or refactor plan needs read-only relationship context for a known target.

This skill extends problem-solving Step 4: identify possible causes by requesting bounded relationship data. It does not gather context, invoke tools, inspect files, run tests, plan edits, or expose raw graph operations.

The only supported runtime path is the controller-owned `code_context.lookup` workflow with `allowed_context_tools` containing `codegraph_context`.

## Inputs

Use only:

- scoped objective and stop conditions from prior skills
- selected entry point from `entrypoint-finder`
- context requests from `context-plan-builder`
- user-named path, symbol, module, route, command, or workflow
- allowed context tools from runtime or controller policy
- target root when already available

## Workflow

1. Refuse to proceed if any prior `stop.required` is true.
2. Confirm the request needs relationship context, not ordinary structure, grep, or file reading.
3. Confirm `codegraph_context` is allowed. If not, set `status` to `blocked`.
4. Require a bounded target: repo-relative `path`, `symbol`, or `module`.
5. Choose relationship kinds deterministically:
   - `callers`: impact, upstream usage, "who uses this", entrypoint reachability, before refactor, or single-path consolidation.
   - `callees`: downstream behavior, "what this calls", dependency path, or control-flow expansion from a known function.
   - `imports`: importers, module dependency, coupling, package/module usage, or import relationship.
6. Emit at most 3 relationship queries unless the input explicitly provides a smaller complete list.
7. Keep `max_results` between 1 and 25.
8. Put reasons in `relationship_rationale`, not inside `relationship_queries`.
9. Route to `impact-map-builder` only when a ready relationship lookup can support impact mapping.

## Output

Return exactly one JSON object:

```json
{
  "lookup_plan_id": "CGCTX-0001",
  "status": "ready|not_needed|blocked",
  "input_target": {
    "target_root": "string or null",
    "path": "repo-relative path or null",
    "symbol": "name or null",
    "module": "module name or null",
    "confidence": "low|medium|high|null"
  },
  "relationship_queries": [
    {
      "kind": "callers|callees|imports",
      "symbol": "name or null",
      "path": "repo-relative path or null",
      "module": "module name or null",
      "max_results": 25
    }
  ],
  "relationship_rationale": [
    {
      "kind": "callers|callees|imports",
      "reason": "why this relationship is needed",
      "evidence_refs": []
    }
  ],
  "controller_request_delta": {
    "workflow": "code_context.lookup",
    "query": "short bounded lookup purpose",
    "paths": [],
    "allowed_context_tools": ["codegraph_context"],
    "relationship_queries": []
  },
  "excluded_operations": [
    {
      "operation": "string",
      "reason": "raw_codegraph_not_allowed|unbounded|write_or_runtime_action|unsupported|not_needed"
    }
  ],
  "next_step": {
    "suggested_skill": "impact-map-builder|context-plan-builder|none",
    "reason": "short explanation"
  },
  "stop": {
    "required": false,
    "reason": "string or null",
    "open_questions": []
  }
}
```

Use empty arrays when no item exists. Use `null` for unknown target fields.

## Query Rules

- `relationship_queries` and `controller_request_delta.relationship_queries` must be valid adapter objects. Each item may contain only `kind`, `symbol`, `path`, `module`, and `max_results`.
- Use only these `kind` values: `callers`, `callees`, `imports`.
- For `callers` and `callees`, include `symbol` when available. Include `path` only when it is repo-relative and helps bound the lookup.
- For `imports`, include `module`, `path`, or `symbol`; prefer `module` for package/module lookup and `path` for one-file import extraction.
- Do not include absolute paths, `..`, globs, regex, shell commands, or free-form graph expressions in query fields.
- If the input asks for raw CodeGraphContext, Cypher, visualization, repository indexing, watching, deletion, package loading, broad traversal, edits, or test execution, set `status` to `blocked`, leave `relationship_queries` empty, and record the request in `excluded_operations`.
- If relationship context is not needed, set `status` to `not_needed`, leave `relationship_queries` empty, and route to `context-plan-builder` or `impact-map-builder` based on available evidence.

## Routing

- `impact-map-builder`: use when `status` is `ready` and the relationship query can validate affected paths, callers, callees, imports, dependencies, or duplicate paths.
- `context-plan-builder`: use when relationship context is not needed or a non-relationship bounded lookup should be planned instead.
- `none`: use when blocked by missing target, unavailable `codegraph_context`, prior stop, or an unsafe/raw graph request.

## Must Not

- Do not invoke `code_context.lookup`.
- Do not call shell, MCP, CodeGraphContext, Cypher, browser, or test tools.
- Do not expose raw CodeGraphContext operations.
- Do not create implementation steps or packet candidates.
- Do not approve writes, apply mode, test execution, or broad repository traversal.
- Do not claim relationships were found; this skill only prepares lookup requests.

## Examples

Input context:

```json
{
  "objective": "Map who calls reveal_order_slice before a single-path refactor.",
  "selected_entrypoint": {
    "path": "core/stealth_order_manager.py",
    "symbol": "reveal_order_slice",
    "confidence": "high"
  },
  "allowed_context_tools": ["structure_index", "git_grep", "read_file", "codegraph_context"],
  "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github"
}
```

Output:

```json
{
  "lookup_plan_id": "CGCTX-0001",
  "status": "ready",
  "input_target": {
    "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    "path": "core/stealth_order_manager.py",
    "symbol": "reveal_order_slice",
    "module": null,
    "confidence": "high"
  },
  "relationship_queries": [
    {
      "kind": "callers",
      "symbol": "reveal_order_slice",
      "path": "core/stealth_order_manager.py",
      "module": null,
      "max_results": 25
    }
  ],
  "relationship_rationale": [
    {
      "kind": "callers",
      "reason": "Caller context is needed to map impact before a single-path refactor.",
      "evidence_refs": ["selected_entrypoint"]
    }
  ],
  "controller_request_delta": {
    "workflow": "code_context.lookup",
    "query": "Find callers of reveal_order_slice before impact mapping.",
    "paths": ["core/stealth_order_manager.py"],
    "allowed_context_tools": ["codegraph_context"],
    "relationship_queries": [
      {
        "kind": "callers",
        "symbol": "reveal_order_slice",
        "path": "core/stealth_order_manager.py",
        "module": null,
        "max_results": 25
      }
    ]
  },
  "excluded_operations": [],
  "next_step": {
    "suggested_skill": "impact-map-builder",
    "reason": "The caller lookup can provide bounded relationship evidence for impact mapping."
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
  "objective": "Use raw Cypher to visualize every dependency in the repository.",
  "selected_entrypoint": {
    "path": null,
    "symbol": null,
    "confidence": null
  },
  "allowed_context_tools": ["codegraph_context"]
}
```

Output:

```json
{
  "lookup_plan_id": "CGCTX-0001",
  "status": "blocked",
  "input_target": {
    "target_root": null,
    "path": null,
    "symbol": null,
    "module": null,
    "confidence": null
  },
  "relationship_queries": [],
  "relationship_rationale": [],
  "controller_request_delta": {
    "workflow": "code_context.lookup",
    "query": "Blocked unsafe raw graph request.",
    "paths": [],
    "allowed_context_tools": ["codegraph_context"],
    "relationship_queries": []
  },
  "excluded_operations": [
    {
      "operation": "raw Cypher repository visualization",
      "reason": "raw_codegraph_not_allowed"
    }
  ],
  "next_step": {
    "suggested_skill": "none",
    "reason": "Raw graph operations and unbounded visualization are not allowed."
  },
  "stop": {
    "required": true,
    "reason": "The request asks for raw graph behavior outside the curated controller adapter.",
    "open_questions": []
  }
}
```
