# Failure Taxonomy

Failure taxonomy reporting reads existing validation artifacts and classifies failures into a stable set of categories.

It is read-only. It does not call the model, controller, gateway, AnythingLLM, or target repositories.

## What It Classifies

Supported input report kinds:

- `v1_acceptance_report`
- `founder_field_prompt_evaluation`
- `model_portability_report`
- `run_artifact_diff`

Failure categories:

- `routing_miss`
- `semantic_miss`
- `output_contract_miss`
- `evidence_miss`
- `prompt_ambiguity`
- `fixture_mutation`
- `anythingllm_config_error`
- `model_timeout`
- `approval_boundary_miss`
- `model_quality`
- `harness_error`
- `unknown`

Each finding includes severity, source report, source location, matched terms when available, evidence, and a recommended next action.

## Run

```bash
python scripts/report_failure_taxonomy.py \
  --report runtime-state/v1-acceptance/phase72-model-portability-v1.json \
  --label phase72-v1 \
  --report runtime-state/model-portability/phase72-live-current.json \
  --label phase72-portability
```

Expected markers:

```text
FAILURE TAXONOMY REPORT ...
FAILURE TAXONOMY SUMMARY ...
FAILURE TAXONOMY PASS
```

Reports are written under:

```text
runtime-state/failure-taxonomy/
```

The CLI writes both JSON and Markdown. The Markdown report is the quick review surface for testers.

## Interpreting Results

Start with:

```text
summary.finding_count
summary.highest_severity
summary.category_counts
findings[].category
findings[].recommended_next_action
```

A passed taxonomy report means the taxonomy reader completed successfully. It does not mean the original validation run passed; check `summary.finding_count` and `findings`.

If `unknown` appears repeatedly, add a narrower classification rule instead of treating the raw log as a one-off.

## Safety

- Reads JSON reports only.
- Does not mutate source or runtime fixtures.
- Does not rerun validation.
- Does not promote a model, skill, route, or release channel.
- Preserves the existing validator output contract by producing a separate derived report.
