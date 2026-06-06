# Failure Taxonomy Examples

These examples classify existing validation reports. They do not contact localhost services.

## Classify The Current V1 And Portability Proof

```bash
cd /mnt/c/agentic_agents
python3 scripts/report_failure_taxonomy.py \
  --report runtime-state/v1-acceptance/phase72-model-portability-v1.json \
  --label phase72-v1 \
  --report runtime-state/model-portability/phase72-live-current.json \
  --label phase72-portability \
  --output-path runtime-state/failure-taxonomy/phase75-current.json \
  --markdown-output-path runtime-state/failure-taxonomy/phase75-current.md
```

Expected markers:

```text
FAILURE TAXONOMY REPORT ...
FAILURE TAXONOMY SUMMARY ...
FAILURE TAXONOMY PASS
```

## Classify Artifact Diffs

```bash
python3 scripts/report_failure_taxonomy.py \
  --report runtime-state/run-artifact-diffs/phase73-phase71-vs-phase72.json \
  --label phase71-vs-phase72 \
  --report runtime-state/run-artifact-diffs/phase73-portability-offline-vs-live.json \
  --label portability-offline-vs-live
```

## Expected JSON Fields

```text
kind=failure_taxonomy_report
status=passed|failed
summary.finding_count=...
summary.highest_severity=none|critical|high|medium|low
summary.category_counts={...}
findings[].category=...
findings[].severity=...
findings[].source=...
findings[].recommended_next_action=...
markdown_report_path=...
```

## Review Order

1. Check `summary.highest_severity`.
2. Check `fixture_mutation` and `approval_boundary_miss` findings first.
3. Check `anythingllm_config_error` and `model_timeout` before changing prompts.
4. Check `routing_miss`, `output_contract_miss`, and `semantic_miss`.
5. Only then inspect `prompt_ambiguity`, `model_quality`, `harness_error`, and `unknown`.
