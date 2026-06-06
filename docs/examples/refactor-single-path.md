# Refactor Single Path Examples

These examples use the explicit `refactor.single_path` workflow. The workflow is read-only unless `dry_run` is approved, and even then it writes draft artifacts only.

## Investigation Only

```bash
curl -s http://127.0.0.1:8400/v1/controller/refactor/single-path \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "refactor.single_path",
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

- `workflow: "refactor.single_path"`
- `status: "completed"`
- `summary.refactor_status: "approval_required"`
- `artifacts.investigation_investigation_plan`
- `artifacts.refactor_plan`

## Approved Dry Run

```bash
curl -s http://127.0.0.1:8400/v1/controller/refactor/single-path \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "refactor.single_path",
    "schema_version": 1,
    "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "mode": "dry_run",
    "user_request": "Prepare draft packet candidates for an approved invariant wording refactor. Do not mutate the repository.",
    "behavior": "client_order_id invariant wording",
    "entrypoint_hints": [
      {
        "path": "docs/agents/INVARIANTS.md",
        "symbol": null,
        "reason": "Approved documentation target."
      }
    ],
    "queries": ["client_order_id"],
    "paths": ["docs/agents/INVARIANTS.md"],
    "approval": {
      "status": "approved_for_packet_design",
      "scope": "packet_design_only",
      "apply_allowed": false,
      "approval_refs": ["founder:approved packet design only"]
    },
    "packet_operations": [
      {
        "kind": "replace_text",
        "path": "docs/agents/INVARIANTS.md",
        "old": "exact existing text",
        "new": "exact proposed text"
      }
    ],
    "budgets": {
      "max_context_requests": 5,
      "max_files": 10,
      "max_records": 50,
      "max_model_calls": 12,
      "max_output_tokens": 4600
    }
  }'
```

Expected response:

- `summary.refactor_status: "draft_packet_ready"`
- `artifacts.execution_planning_packet_preview`
- `artifacts.execution_planning_implementation_workflow_report`
- selected target files unchanged

## Harness Envelope

```json
{
  "model": "agentic-controller",
  "messages": [
    {
      "role": "user",
      "content": "{\"agentic_controller_request\":{\"workflow\":\"refactor.single_path\",\"schema_version\":1,\"target_root\":\"/mnt/c/coinbase_testing_repo_frozen_tmp\",\"user_request\":\"Investigate whether StealthOrderManager.find_stealth_order_by_placed_order_id has one path before planning a refactor.\",\"behavior\":\"placed_order_id stealth lookup\",\"queries\":[\"find_stealth_order_by_placed_order_id\",\"placed_order_id\"],\"entrypoint_hints\":[{\"path\":\"core/stealth_order_manager.py\",\"symbol\":\"StealthOrderManager.find_stealth_order_by_placed_order_id\",\"reason\":\"Known owner of placed-order lookup behavior.\"}],\"paths\":[\"core/stealth_order_manager.py\",\"tests/unit/test_order_id_and_followup_rules.py\",\"tests/regression/test_order_id_regression.py\"],\"max_results\":50,\"max_files\":10}}"
    }
  ]
}
```
