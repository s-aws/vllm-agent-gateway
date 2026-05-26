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
    "doc": "README.md",
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

Run the tool mediator regression tests:

```bash
pytest tests/regression/test_tool_mediator.py -v
```

Expected mediator flow:

```text
tool schema -> model tool call -> local execution -> tool result -> final model answer
```

Raw tool-call-shaped assistant text is rejected as incomplete execution; a real local tool call must run before the final answer is accepted.
