# Current-Model Compatibility Matrix

Phase 150 summarizes what the current localhost model is proven to support through the existing harness evidence.

This matrix does not expand the product surface. It records what is currently supported, conditional, monitored, not governed, or not approved.

## What It Reads

Policy:

```text
runtime/current_model_compatibility_matrix_policy.json
```

Required evidence includes:

```text
runtime-state/model-capability-profiles/phase100-current-profile.json
runtime/model_capability_routing.json
runtime/prompt_skill_coverage.json
runtime-state/founder-test-prompt-pack/phase137/phase137-founder-test-prompt-pack.json
runtime-state/fresh-local-model-drift/phase127/phase127-fresh-local-model-drift-report.json
runtime-state/output-format-parity/phase124-output-format-parity-live.json
runtime-state/natural-output-format-preference/phase144/phase144-natural-output-format-preference-live.json
runtime/local_model_regression_watchlist.json
runtime-state/local-model-regression-watchlist/phase139/phase139-local-model-regression-watchlist-report.json
runtime-state/contextless-audit-scorecard/phase149/phase149-contextless-audit-scorecard-report.json
```

## What It Produces

JSON:

```text
runtime-state/current-model-compatibility-matrix/phase150/phase150-current-model-compatibility-matrix-report.json
```

Markdown:

```text
runtime-state/current-model-compatibility-matrix/phase150/phase150-current-model-compatibility-matrix-report.md
```

The matrix includes:

- current localhost model identity and profile status
- L1/L2 prompt-family compatibility
- selected workflow, route rule, skills, and tools per prompt family
- governed output format support
- AnythingLLM compatibility status
- known monitored failure modes
- known boundaries such as latency, real apply, automatic model selection, and non-governed output formats

## Run

```bash
python3 scripts/validate_current_model_compatibility_matrix.py \
  --require-artifacts \
  --output-path runtime-state/current-model-compatibility-matrix/phase150/phase150-current-model-compatibility-matrix-report.json \
  --markdown-output-path runtime-state/current-model-compatibility-matrix/phase150/phase150-current-model-compatibility-matrix-report.md
```

Expected current marker:

```text
CURRENT MODEL COMPATIBILITY PASS
```

Expected current summary:

```json
{
  "l1_prompt_family_count": 21,
  "l2_prompt_family_count": 12,
  "supported_prompt_family_count": 33,
  "governed_output_format_count": 2,
  "anythingllm_compatibility_status": "supported",
  "known_failure_mode_count": 14,
  "model_profile_status": "warning"
}
```

## Boundaries

- `format_a` and `json` are the only governed output formats.
- AnythingLLM is supported through the current `my-workspace` path and existing gateway evidence.
- `real_apply` is not approved by the model compatibility matrix.
- Automatic model selection is not approved by the matrix.
- Latency remains monitored because the active model profile records it as unknown.
- Known failure modes are monitored risks, not current failing gates.

Examples: [docs/examples/current-model-compatibility.md](docs/examples/current-model-compatibility.md).
