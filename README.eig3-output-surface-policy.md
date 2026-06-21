# EIG-3 Output Surface Policy

Status: Phase 299.

This feature validates the masking/refusal output matrix for EIG-3 synthetic sensitive-data fixtures.

The policy decides whether each output surface should allow, mask, refuse, summarize, or omit sensitive content. It covers:

- chat-visible default output,
- JSON output,
- generated artifacts,
- connector audit summaries,
- run-state summaries,
- memory.

## Files

- `runtime/eig3_output_surface_policy.json`: output-surface policy matrix.
- `runtime/eig3_sensitive_data_fixtures.json`: source fixture pack from Phase 298.
- `vllm_agent_gateway/acceptance/eig3_output_surface_policy.py`: validator.
- `scripts/validate_eig3_output_surface_policy.py`: CLI wrapper.

## Validation

```bash
python scripts/validate_eig3_output_surface_policy.py \
  --output-path runtime-state/eig3-output-surface-policy/phase299-validation.json
```

Expected result:

- `status=passed`
- `fixture_count=30`
- `surface_count=6`
- `phase300_ready=true`
- no raw fixture text retained in the report

## Safety Boundary

The report stores fixture IDs, decisions, status, error IDs, and safe sample hashes. It does not store raw fixture text or rendered raw sensitive values.

Runtime chat proof is not part of Phase 299. That is reserved for Phase 302.
