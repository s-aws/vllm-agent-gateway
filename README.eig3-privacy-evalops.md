# EIG-3 Privacy EvalOps

Status: Phase 301.

This feature turns the EIG-3 synthetic privacy and memory-safety fixtures into a release-blocking EvalOps gate.

It does not run production DLP, ingest real private data, or approve persistent hidden memory. It validates a synthetic prompt pack that references fixture IDs, blind-baseline expectations, local policy proof, memory lifecycle proof, holdouts, negative controls, and release-blocking privacy thresholds.

## Files

- `runtime/eig3_privacy_evalops_policy.json`: release-blocking privacy EvalOps thresholds and required dimensions.
- `runtime/eig3_privacy_evalops_prompt_pack.json`: synthetic prompt cases built from Phase 297-300 fixture IDs.
- `vllm_agent_gateway/acceptance/eig3_privacy_evalops.py`: single validator path.
- `scripts/validate_eig3_privacy_evalops.py`: CLI wrapper.

## Validation

```bash
python scripts/validate_eig3_privacy_evalops.py \
  --output-path runtime-state/eig3-privacy-evalops/phase301-validation.json
```

Expected result:

- `status=passed`
- `case_count=16`
- `archetype_count=3`
- `dimension_count=8`
- `phase302_ready=true`
- no raw source content retained in the report

## Safety Boundary

The committed prompt pack stores fixture IDs, safe baseline summaries, local proof summaries, and scoring dimensions. It must not store raw private values, raw secrets, or raw confidential fixture text.

If a prompt case is marked `chat_exposed=true`, the gate requires both workflow-router gateway proof and AnythingLLM proof before it can pass. Phase 302 performs that runtime chat proof.
