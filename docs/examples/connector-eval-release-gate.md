# Connector Eval Release Gate Examples

Run the default sample release packet:

```bash
python scripts/validate_connector_eval_release_gate.py
```

Expected pass marker:

```text
CONNECTOR EVAL RELEASE GATE PASS
```

Validate a custom packet:

```bash
python scripts/validate_connector_eval_release_gate.py \
  --packet-path runtime-state/connector-release-packets/ticketing-stub.json \
  --output-path runtime-state/connector-eval-release-gate/ticketing-stub-report.json
```

Minimum pass requirements:

```text
connector_validation.status = passed
connector_validation.connector_id matches packet.connector_id
each operation_id has an operation_evals entry
each operation has at least two prompt cases
each operation has at least one holdout
blind_baseline.status = passed
blind_baseline.collected_before_local_output = true
raw_mcp_bypass negative control = passed
direct_model_tool_bypass negative control = passed
unknown_connector_or_operation negative control = passed
controller surface result = passed
release_decision.decision = ship when connector_enabled_requested = true
```

When a connector is exposed to natural-language workflows, add these local stack results for each operation:

```json
[
  {"surface": "workflow_router_gateway", "status": "passed"},
  {"surface": "anythingllm", "status": "passed"}
]
```

Common rejection codes:

```text
missing_connector_validation
connector_validation_mismatch
missing_operation_eval
missing_prompt_coverage
missing_holdout_coverage
missing_blind_baseline
late_blind_baseline
missing_negative_controls
missing_controller_surface
missing_natural_workflow_surfaces
blocking_connector_eval_finding
enabled_without_ship_decision
ship_with_blockers
```

Focused regression:

```bash
python -m pytest tests/regression/test_connector_eval_release_gate.py -v
```
