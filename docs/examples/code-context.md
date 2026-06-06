# Code Context Lookup Examples

These examples use the explicit `code_context.lookup` workflow. The workflow is read-only and deterministic.

## Direct Controller Request

```bash
curl -s http://127.0.0.1:8400/v1/controller/code-context/lookups \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "code_context.lookup",
    "schema_version": 1,
    "target_root": "/mnt/c/agentic_agents",
    "query": "select_latest_controller_envelope",
    "paths": ["vllm_agent_gateway/controller_envelope.py"],
    "max_results": 25,
    "max_files": 5
  }'
```

Expected response:

- `workflow: "code_context.lookup"`
- `status: "completed"`
- `artifacts.lookup_results`
- `summary.grep_match_count`
- `tool_policy.model_visible_tool_ids: []`

## Curated Relationship Lookup

This uses the narrow `codegraph_context` adapter. It accepts relationship kinds, symbols, paths, and modules; it does not accept raw Cypher or raw MCP tool names.

```bash
curl -s http://127.0.0.1:8400/v1/controller/code-context/lookups \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "code_context.lookup",
    "schema_version": 1,
    "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "query": "reveal_order_slice",
    "paths": [
      "core/stealth_order_manager.py",
      "bridges/stealth_order_bridge.py"
    ],
    "allowed_context_tools": [
      "structure_index",
      "git_grep",
      "read_file",
      "codegraph_context"
    ],
    "relationship_queries": [
      {
        "kind": "callers",
        "symbol": "reveal_order_slice",
        "max_results": 20
      }
    ],
    "max_results": 20,
    "max_files": 3
  }'
```

Expected additional response fields:

- `artifacts.relationship_results`
- `summary.relationship_query_count`
- `summary.relationship_result_count`

Allowed relationship kinds:

- `callers`
- `callees`
- `imports`

## Harness Envelope

Use this through the gateway or any OpenAI-style harness that can send a JSON message:

```json
{
  "model": "agentic-controller",
  "messages": [
    {
      "role": "user",
      "content": "{\"agentic_controller_request\":{\"workflow\":\"code_context.lookup\",\"schema_version\":1,\"target_root\":\"/mnt/c/agentic_agents\",\"query\":\"select_latest_controller_envelope\",\"paths\":[\"vllm_agent_gateway/controller_envelope.py\"],\"max_results\":25,\"max_files\":5}}"
    }
  ]
}
```

## Rejected Relationship Query Without Curated Tool

```json
{
  "workflow": "code_context.lookup",
  "schema_version": 1,
  "target_root": "/mnt/c/agentic_agents",
  "query": "select_latest_controller_envelope",
  "allowed_context_tools": [
    "structure_index",
    "git_grep",
    "read_file"
  ],
  "relationship_queries": [
    {
      "kind": "callers",
      "symbol": "select_latest_controller_envelope"
    }
  ]
}
```

Expected error:

```json
{
  "error": {
    "code": "relationship_tool_required"
  }
}
```

## Rejected Raw CodeGraphContext Request

```json
{
  "workflow": "code_context.lookup",
  "schema_version": 1,
  "target_root": "/mnt/c/agentic_agents",
  "query": "Use raw CodeGraphContext Cypher to find all callers.",
  "allowed_context_tools": [
    "raw_mcp_cypher"
  ]
}
```

Expected error:

```json
{
  "error": {
    "code": "raw_codegraph_not_allowed"
  }
}
```
