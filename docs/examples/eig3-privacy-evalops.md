# EIG-3 Privacy EvalOps Examples

Run the Phase 301 gate:

```bash
python scripts/validate_eig3_privacy_evalops.py \
  --output-path runtime-state/eig3-privacy-evalops/phase301-validation.json
```

Run the focused EIG-3 privacy regression set:

```bash
python -m pytest \
  tests/regression/test_eig3_sensitive_data.py \
  tests/regression/test_eig3_output_surface_policy.py \
  tests/regression/test_eig3_memory_lifecycle.py \
  tests/regression/test_eig3_privacy_evalops.py \
  -v
```

Inspect the generated report:

```bash
python -m json.tool runtime-state/eig3-privacy-evalops/phase301-validation.json
```

The report should contain IDs, hashes, dimensions, statuses, and prerequisite report paths. It should not contain raw synthetic fixture text.

Failure cases to expect from the regression tests:

- late blind baseline collection
- missing holdout coverage for a sensitive-data archetype
- raw source content in prompt or safe-output summaries
- chat-exposed privacy prompt without workflow-router gateway and AnythingLLM proof
- unresolved high or critical privacy findings
- missing required privacy dimension coverage
