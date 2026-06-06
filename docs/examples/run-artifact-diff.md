# Run Artifact Diff Examples

These examples compare existing run reports. They do not contact localhost services.

## Compare Two V1 Acceptance Runs

```bash
cd /mnt/c/agentic_agents
python3 scripts/diff_run_artifacts.py \
  --left-report runtime-state/v1-acceptance/phase71-v1-acceptance.json \
  --right-report runtime-state/v1-acceptance/phase72-model-portability-v1.json \
  --left-label phase71 \
  --right-label phase72 \
  --output-path runtime-state/run-artifact-diffs/phase73-phase71-vs-phase72.json
```

Expected markers:

```text
RUN ARTIFACT DIFF REPORT ...
RUN ARTIFACT DIFF SUMMARY ...
RUN ARTIFACT DIFF PASS
```

## Compare A Portability Report To Its Baseline

```bash
python3 scripts/diff_run_artifacts.py \
  --left-report runtime-state/model-portability/phase72-offline-baseline.json \
  --right-report runtime-state/model-portability/phase72-live-current.json \
  --left-label offline-baseline \
  --right-label live-current
```

For model portability reports, the diff follows `acceptance_report_path` and includes the nested V1 acceptance summary when the file is available.

## Expected JSON Fields

```text
kind=run_artifact_diff
left.summary.kind=...
right.summary.kind=...
diff.status_changed=true|false
diff.suite_status_changes.changed_count=...
diff.semantic_miss_changes.added=[...]
diff.output_miss_changes.added=[...]
diff.fixture_state_changes=[...]
diff.classification_summary_delta={...}
recommendations=[...]
```

## Review Order

1. Check `diff.status_changed`.
2. Check `diff.fixture_state_changes`.
3. Check `diff.suite_status_changes`.
4. Check `diff.semantic_miss_changes` and `diff.output_miss_changes`.
5. For model portability reports, check `diff.classification_summary_delta`.
