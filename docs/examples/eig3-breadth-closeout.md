# EIG-3 Breadth Closeout Examples

Run the live closeout gate:

```bash
python3 scripts/validate_eig3_breadth_closeout.py \
  --anythingllm-api-base-url http://100.100.12.45:3001 \
  --output-path runtime-state/eig3-breadth-closeout/phase303-validation.json
```

Run the focused EIG-3 regression set:

```bash
python -m pytest \
  tests/regression/test_eig3_sensitive_data.py \
  tests/regression/test_eig3_output_surface_policy.py \
  tests/regression/test_eig3_memory_lifecycle.py \
  tests/regression/test_eig3_privacy_evalops.py \
  tests/regression/test_eig3_privacy_runtime_routing.py \
  tests/regression/test_eig3_privacy_runtime_chat.py \
  tests/regression/test_eig3_breadth_closeout.py \
  -v
```

Run docs validation:

```bash
python scripts/check_docs_index.py
```

Run final full regression:

```bash
python3 -m pytest tests/regression/ -v
```

Do not use `--no-live-runtime` or `--skip-anythingllm` as release evidence. Those modes only validate report shape and prerequisite wiring.
