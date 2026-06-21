# EIG-3 Output Surface Policy

Run the Phase 299 output-surface policy validator:

```bash
python scripts/validate_eig3_output_surface_policy.py \
  --output-path runtime-state/eig3-output-surface-policy/phase299-validation.json
```

Inspect the report:

```bash
python -m json.tool runtime-state/eig3-output-surface-policy/phase299-validation.json
```

The summary should show:

- `status`: `passed`
- `fixture_count`: `30`
- `surface_count`: `6`
- `phase300_ready`: `true`
- `raw_fixture_text_retained_in_report`: `false`

Run focused regression:

```bash
python -m pytest tests/regression/test_eig3_sensitive_data.py tests/regression/test_eig3_output_surface_policy.py -v
```

Do not use this validator as runtime chat proof. Runtime proof belongs to Phase 302.
