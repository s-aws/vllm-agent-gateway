# Connector Eval Release Gate

The connector eval release gate prevents a connector from being treated as shippable or enabled unless its validation, prompt coverage, holdouts, blind baseline, negative controls, local-stack proof, and release decision all pass.

Current status: Phase 283 acceptance gate. It validates connector release packets. It does not enable connectors by itself.

## When To Use It

Use this gate before enabling a connector or exposing it to natural-language workflows.

It checks:

- connector admission validation passed
- each declared operation has eval coverage
- each operation has target prompt cases and holdouts
- blind baselines were collected before local output
- required negative controls passed
- controller-surface proof exists
- gateway and AnythingLLM proof exist when natural workflow exposure is requested
- no unresolved critical or high findings remain
- connector enablement is paired with a `ship` release decision

## Command

Validate the built-in sample release packet:

```bash
python scripts/validate_connector_eval_release_gate.py
```

Validate an explicit release packet:

```bash
python scripts/validate_connector_eval_release_gate.py \
  --packet-path runtime-state/connector-release-packets/ticketing-stub.json \
  --output-path runtime-state/connector-eval-release-gate/ticketing-stub-report.json
```

## Release Packet Shape

```json
{
  "schema_version": 1,
  "kind": "connector_release_packet",
  "connector_id": "ticketing_stub",
  "connector_enabled_requested": true,
  "natural_workflow_exposed": false,
  "connector_validation": {
    "status": "passed",
    "connector_id": "ticketing_stub",
    "operation_ids": ["lookup_ticket"]
  },
  "operation_evals": [
    {
      "operation_id": "lookup_ticket",
      "prompt_cases": ["ticketing_stub.lookup_ticket.target"],
      "holdouts": ["ticketing_stub.lookup_ticket.holdout"],
      "blind_baseline": {
        "status": "passed",
        "collected_before_local_output": true
      },
      "negative_controls": [
        {"id": "raw_mcp_bypass", "status": "passed"},
        {"id": "direct_model_tool_bypass", "status": "passed"},
        {"id": "unknown_connector_or_operation", "status": "passed"}
      ],
      "local_stack_results": [
        {"surface": "controller", "status": "passed"}
      ],
      "findings": []
    }
  ],
  "release_decision": {
    "decision": "ship",
    "blockers": [],
    "advisories": [],
    "approval_refs": ["phase283-release-review"]
  }
}
```

When `natural_workflow_exposed=true`, each operation must also include passed `workflow_router_gateway` and `anythingllm` local-stack results.

## Related Docs

- [Connector Catalog](README.connector-catalog.md)
- [Project Milestones](docs/PROJECT_MILESTONES.md)
- [Examples](docs/examples/connector-eval-release-gate.md)
