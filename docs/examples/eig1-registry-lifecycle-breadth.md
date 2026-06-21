# EIG-1 Registry Lifecycle Breadth Examples

Run the Phase 292 lifecycle validator:

```bash
python3 scripts/validate_eig1_registry_lifecycle_breadth.py
```

Run focused regression:

```bash
python3 -m pytest tests/regression/test_eig1_registry_lifecycle_breadth.py -q
```

Expected success marker:

```text
EIG1 REGISTRY LIFECYCLE BREADTH PASS
```

Expected summary shape:

```json
{
  "status": "passed",
  "summary": {
    "connector_count": 3,
    "scenario_count": 18,
    "uses_disposable_runtime_copy": true,
    "real_runtime_registry_changed": false,
    "future_gap_documented": true,
    "phase296_ready": true
  }
}
```
