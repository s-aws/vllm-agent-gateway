# Run Artifact Diffing

Run artifact diffing compares two existing acceptance, founder-field, or model-portability reports and summarizes what changed.

It is read-only. It does not call the model, controller, gateway, AnythingLLM, or target repositories.

## What It Compares

Supported report kinds:

- `v1_acceptance_report`
- `founder_field_prompt_evaluation`
- `model_portability_report`

The diff extracts:

- report status and kind
- V1 suite status changes
- localhost health status changes
- founder-field case status changes
- route rule expectation changes
- selected skill expectation changes
- semantic and output-contract miss changes
- model-portability classification deltas
- artifact count deltas
- protected fixture state signature changes

For `model_portability_report`, the diff follows `acceptance_report_path` and compares the nested V1 acceptance report too.

## Run

```bash
python scripts/diff_run_artifacts.py \
  --left-report runtime-state/v1-acceptance/phase71-v1-acceptance.json \
  --right-report runtime-state/v1-acceptance/phase72-model-portability-v1.json \
  --left-label phase71 \
  --right-label phase72
```

Expected markers:

```text
RUN ARTIFACT DIFF REPORT ...
RUN ARTIFACT DIFF SUMMARY ...
RUN ARTIFACT DIFF PASS
```

Reports are written under:

```text
runtime-state/run-artifact-diffs/
```

## Interpreting Results

Start with:

```text
diff.status_changed
diff.suite_status_changes
diff.semantic_miss_changes
diff.output_miss_changes
diff.fixture_state_changes
diff.classification_summary_delta
recommendations
```

No material diff means the compared runs had the same high-signal outcome for route, semantic, suite, classification, and fixture state. It does not mean the text output was byte-for-byte identical.

## Safety

- Reads JSON reports only.
- Does not mutate source or runtime fixtures.
- Does not rerun validation.
- Does not promote a model, skill, or release channel.
