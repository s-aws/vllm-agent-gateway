# Code Context Lookup

`code_context.lookup` is a controller-owned read-only workflow for bounded source lookup and curated relationship lookup.

It does not call the model, does not expose raw CodeGraphContext/Cypher/MCP operations, and does not mutate the target repository.

## When To Use It

Use this workflow when a tester or agent needs to:

- find exact text matches in a target repository
- get a bounded structure-index slice
- read snippets from explicitly named files
- ask curated relationship questions for callers, callees, and imports through `relationship_queries`
- produce inspectable lookup artifacts before planning or refactoring

Do not use it for broad repository scans, raw Cypher, package indexing, watcher control, raw MCP calls, or edits.

## Endpoints

Direct controller endpoint:

```text
POST /v1/controller/code-context/lookups
```

OpenAI-style harness endpoint:

```text
POST /v1/controller/harness/chat/completions
```

The harness endpoint requires an explicit `agentic_controller_request` envelope.

## Request Shape

```json
{
  "workflow": "code_context.lookup",
  "schema_version": 1,
  "target_root": "/mnt/c/agentic_agents",
  "query": "select_latest_controller_envelope",
  "paths": [
    "vllm_agent_gateway/controller_envelope.py"
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
      "symbol": "select_latest_controller_envelope",
      "max_results": 10
    }
  ],
  "max_results": 25,
  "max_files": 5
}
```

## Artifacts

Artifacts are written under:

```text
CONTROLLER_OUTPUT_ROOT/code-context/<run-id>/
```

Typical artifacts:

- `request.json`
- `lookup-results.json`
- `relationship-results.json` when `relationship_queries` are requested
- `run-state.json`

The compact response includes the run ID, artifact paths, a summary, warnings, and the controller tool-policy audit record.

## Validation

Regression covers:

- direct endpoint lookup with bounded artifacts
- harness adapter lookup with prior envelope history
- raw CodeGraphContext rejection
- curated `codegraph_context` relationship artifacts and invalid relationship-query rejection

Live Bash validation has also passed through:

- direct controller endpoint on `8400`
- gateway controller-envelope route on `8300`
- AnythingLLM workspace chat with AnythingLLM pointed at `http://127.0.0.1:8300/v1`
- both frozen validation fixtures, with selected file hashes unchanged

Examples: [docs/examples/code-context.md](docs/examples/code-context.md).
