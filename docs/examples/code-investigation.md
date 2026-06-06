# Code Investigation Examples

These examples use the explicit `code_investigation.plan` workflow. The workflow is read-only and deterministic.

## Direct Controller Request

```bash
curl -s http://127.0.0.1:8400/v1/controller/code-investigation/plans \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "code_investigation.plan",
    "schema_version": 1,
    "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "user_request": "Investigate whether StealthOrderManager.find_stealth_order_by_placed_order_id has one path before planning a refactor.",
    "behavior": "placed_order_id stealth lookup",
    "entrypoint_hints": [
      {
        "path": "core/stealth_order_manager.py",
        "symbol": "StealthOrderManager.find_stealth_order_by_placed_order_id",
        "reason": "Known owner of placed-order lookup behavior."
      }
    ],
    "queries": ["find_stealth_order_by_placed_order_id", "placed_order_id"],
    "paths": [
      "core/stealth_order_manager.py",
      "tests/unit/test_order_id_and_followup_rules.py",
      "tests/regression/test_order_id_regression.py"
    ],
    "max_results": 50,
    "max_files": 10
  }'
```

Expected response:

- `workflow: "code_investigation.plan"`
- `status: "completed"`
- `artifacts.investigation_evidence`
- `artifacts.investigation_plan`
- `summary.beginning_point_status`
- `summary.multiple_path_status`
- `summary.verification_command_count`
- `artifacts.investigation_plan` with `verification_plan.verification_commands`
- `tool_policy.model_visible_tool_ids: []`

The verification plan emits commands only from discovered test-file evidence, for example:

```json
{
  "command": ["python", "-m", "pytest", "tests/unit/test_order_id_and_followup_rules.py"],
  "source_refs": ["tests/unit/test_order_id_and_followup_rules.py:8:def test_find_stealth_order_by_placed_order_id_uses_client_order_id_index():"]
}
```

## Harness Envelope

Use this through the gateway or any OpenAI-style harness that can send a JSON message:

```json
{
  "model": "agentic-controller",
  "messages": [
    {
      "role": "user",
      "content": "{\"agentic_controller_request\":{\"workflow\":\"code_investigation.plan\",\"schema_version\":1,\"target_root\":\"/mnt/c/coinbase_testing_repo_frozen_tmp\",\"user_request\":\"Investigate whether StealthOrderManager.find_stealth_order_by_placed_order_id has one path before planning a refactor.\",\"behavior\":\"placed_order_id stealth lookup\",\"queries\":[\"find_stealth_order_by_placed_order_id\",\"placed_order_id\"],\"entrypoint_hints\":[{\"path\":\"core/stealth_order_manager.py\",\"symbol\":\"StealthOrderManager.find_stealth_order_by_placed_order_id\",\"reason\":\"Known owner of placed-order lookup behavior.\"}],\"paths\":[\"core/stealth_order_manager.py\",\"tests/unit/test_order_id_and_followup_rules.py\",\"tests/regression/test_order_id_regression.py\"],\"max_results\":50,\"max_files\":10}}"
    }
  ]
}
```

## Rejected Raw CodeGraphContext Request

```json
{
  "workflow": "code_investigation.plan",
  "schema_version": 1,
  "target_root": "/mnt/c/agentic_agents",
  "user_request": "Use raw CodeGraphContext Cypher to find all callers.",
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
