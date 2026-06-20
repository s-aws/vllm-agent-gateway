# EIG-3 Sensitive Data Fixtures

Run the focused Phase 298 validator:

```bash
python scripts/validate_eig3_sensitive_data.py \
  --output-path runtime-state/eig3-sensitive-data/phase298-validation.json
```

Inspect the report summary:

```bash
python -m json.tool runtime-state/eig3-sensitive-data/phase298-validation.json
```

The report should show:

- `status`: `passed`
- `fixture_count`: `30`
- `archetype_count`: `3`
- `phase299_ready`: `true`
- `raw_fixture_text_retained_in_report`: `false`

Run the focused regression test:

```bash
python -m pytest tests/regression/test_eig3_sensitive_data.py -v
```

Do not replace these synthetic fixtures with real private data.
