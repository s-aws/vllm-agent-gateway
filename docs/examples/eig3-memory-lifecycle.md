# EIG-3 Memory Lifecycle

Run the Phase 300 memory lifecycle validator:

```bash
python scripts/validate_eig3_memory_lifecycle.py \
  --output-path runtime-state/eig3-memory-lifecycle/phase300-validation.json
```

Inspect the report:

```bash
python -m json.tool runtime-state/eig3-memory-lifecycle/phase300-validation.json
```

The summary should show:

- `status`: `passed`
- `record_count`: `8`
- `allowed_record_count`: `1`
- `denied_record_count`: `7`
- `phase301_ready`: `true`
- `raw_memory_content_retained_in_report`: `false`

Run focused regression:

```bash
python -m pytest tests/regression/test_eig3_sensitive_data.py tests/regression/test_eig3_output_surface_policy.py tests/regression/test_eig3_memory_lifecycle.py -v
```

Do not treat this as runtime memory enablement. It is a lifecycle gate for future memory work.
