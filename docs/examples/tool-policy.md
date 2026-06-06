# Tool Policy Examples

Inspect role tool assignments:

```bash
python -m json.tool runtime/roles.json
```

Inspect the tool catalog:

```bash
python -m json.tool runtime/tools.json
```

Inspect workflow tool policy:

```bash
python -m json.tool runtime/workflows.json
```

Documenter tracked discovery requires these controller tools:

```text
git_ls_files
read_file
```

Documenter all-file bootstrap discovery additionally requires:

```text
scan_files
```

The controller service records the resolved policy in each run record:

```bash
curl -s http://127.0.0.1:8400/v1/controller/runs/<run-id> \
  | python -m json.tool
```

Look for:

```json
{
  "tool_policy": {
    "workflow": "documenter.review",
    "role_id": "documenter/default",
    "controller_tool_ids": ["git_ls_files", "read_file", "scan_files"],
    "model_visible_tool_ids": [],
    "denied_tool_ids": [],
    "controller_actions": [
      {
        "tool_id": "scan_files",
        "action": "discover_all_files",
        "scope": "target_root",
        "result_artifacts": ["document_manifest", "review_plan", "json_report"]
      }
    ]
  }
}
```

Denied model-visible tools are rejected before artifacts are created:

```bash
curl -s http://127.0.0.1:8400/v1/controller/documenter/reviews \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "documenter.review",
    "target_root": "/repo/agentic_agents",
    "seed_doc": "README.md",
    "mode": "full",
    "model_visible_tool_ids": ["read_file"],
    "dry_run": true
  }'
```

Expected error code:

```text
tool_policy_denied
```

Implementation verification uses controller-declared pytest commands through:

```text
run_tests
```

Curated code relationship lookup uses:

```text
codegraph_context
```

`codegraph_context` accepts bounded `relationship_queries` for `callers`, `callees`, and `imports`. It does not expose raw Cypher, watcher control, package indexing, delete operations, or raw MCP calls.

Run the tool mediator regression tests:

```bash
pytest tests/regression/test_tool_mediator.py -v
```

Expected mediator flow:

```text
tool schema -> model tool call -> local execution -> tool result -> final model answer
```

Raw tool-call-shaped assistant text is rejected as incomplete execution; a real local tool call must run before the final answer is accepted.

## Tool Catalog Governance

Validate a proposed tool admission manifest without mutating runtime metadata. In the default project runtime, this `scan_files` example is expected to be rejected because the tool already exists:

```bash
curl -s http://127.0.0.1:8400/v1/controller/tool-catalog/validations \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "tool_catalog.validate",
    "schema_version": 1,
    "tool_manifest": {
      "schema_version": 1,
      "kind": "tool_admission_manifest",
      "tool": {
        "id": "scan_files",
        "owner": "agentic_agents",
        "kind": "filesystem_read",
        "description": "Scan repository files for first-run or bootstrap discovery.",
        "read_only": true,
        "args_schema": {
          "ignored_dirs": {"type": "array", "required": false}
        },
        "input_schema": {
          "type": "object",
          "properties": {
            "ignored_dirs": {"type": "array", "items": {"type": "string"}}
          },
          "required": []
        },
        "output_schema": {
          "type": "object",
          "properties": {
            "paths": {"type": "array", "items": {"type": "string"}}
          },
          "required": ["paths"]
        },
        "safety_class": "read_only",
        "mutation_policy": "no_repository_mutation",
        "allowed_workflows": ["documenter.review"],
        "allowed_roles": ["documenter/default"]
      }
    }
  }' | python -m json.tool
```

Expected canonical-runtime marker:

```text
"tool_already_registered"
```

Registering a tool requires an explicit approval object and appends only to `runtime/tools.json`. Successful registration is tested against a controlled runtime copy so the canonical project catalog is not damaged.

Expected controlled-copy registration markers from the focused test:

```text
"registration_status": "installed"
"changed_runtime_files": ["runtime/tools.json"]
```

Run the focused governance regression tests:

```bash
python -m pytest tests/regression/test_tool_catalog.py -q
```
