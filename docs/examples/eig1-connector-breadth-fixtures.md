# EIG-1 Connector Breadth Fixture Examples

Run the Phase 289 validator:

```bash
python3 scripts/validate_eig1_connector_breadth.py
```

Run the focused regression:

```bash
python3 -m pytest tests/regression/test_eig1_connector_breadth.py -q
```

Write a report to a specific path:

```bash
python3 scripts/validate_eig1_connector_breadth.py \
  --output-path runtime-state/eig1-connector-breadth/manual-eig1-report.json
```

Expected success markers:

```text
EIG1 CONNECTOR BREADTH PASS
```

The report should show:

```json
{
  "status": "passed",
  "summary": {
    "connector_manifest_count": 3,
    "archetype_count": 3,
    "positive_invocation_count": 6,
    "negative_control_count": 10,
    "runtime_registry_changed": false,
    "target_repository_changed": false,
    "phase290_ready": true
  }
}
```
