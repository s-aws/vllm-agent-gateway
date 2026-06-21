# EIG-1 Connector Release Gate Breadth Examples

Run the Phase 291 release-gate breadth validator:

```bash
python3 scripts/validate_eig1_connector_release_gate_breadth.py
```

Run focused regression:

```bash
python3 -m pytest tests/regression/test_eig1_connector_release_gate_breadth.py -q
```

Expected success marker:

```text
EIG1 CONNECTOR RELEASE GATE BREADTH PASS
```

Expected summary shape:

```json
{
  "status": "passed",
  "summary": {
    "ship_packet_count": 3,
    "failure_class_count": 6,
    "runtime_registry_changed": false,
    "target_repository_changed": false,
    "phase292_ready": true
  }
}
```
