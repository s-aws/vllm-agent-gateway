# EIG-3 Sensitive Data Fixtures

Status: Phase 298.

This feature validates the first synthetic privacy and memory-safety fixture pack for EIG-3.

It does not process real private data. The fixture pack uses synthetic personal-data, secret-like, and confidential-business examples to prove the classifier and fixture metadata are broad enough for later masking, memory, and privacy EvalOps phases.

## Files

- `docs/EIG3_SENSITIVE_DATA_ARCHETYPE_MATRIX.md`: Phase 297 matrix and case definitions.
- `runtime/eig3_sensitive_data_fixtures.json`: Phase 298 synthetic fixture pack.
- `vllm_agent_gateway/acceptance/eig3_sensitive_data.py`: single validator path.
- `scripts/validate_eig3_sensitive_data.py`: CLI wrapper.

## Validation

```bash
python scripts/validate_eig3_sensitive_data.py \
  --output-path runtime-state/eig3-sensitive-data/phase298-validation.json
```

Expected result:

- `status=passed`
- `fixture_count=30`
- `archetype_count=3`
- `phase299_ready=true`
- no raw fixture text retained in the report

## Safety Boundary

Reports store fixture IDs, detected classes, expected decisions, status, error IDs, and text hashes. They do not store raw fixture text.

Real DLP integrations, real OAuth token handling, production data clean rooms, cloud secret validation, and real sensitive-data ingestion remain out of scope.
