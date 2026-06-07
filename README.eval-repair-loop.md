# Eval Repair Loop

Eval repair loop reporting turns failed validation artifacts into Phase 104 repair recommendations.

It is read-only. It does not call the model, controller, gateway, AnythingLLM, or target repositories, and it does not mutate prompt catalogs, workflow rules, skill metadata, tool catalogs, or fixtures.

## When To Use It

Use this after a founder field test, V1 acceptance run, model portability run, artifact diff, failure taxonomy report, or bounded recursive blind-testing report shows a miss.

The report answers:

- what repair category the miss belongs to
- which evidence supports that classification
- which file or artifact surface should be inspected first
- what the smallest likely repair is
- what command should validate the repair
- which target prompt and holdout prompt must be rerun for accepted current-phase tightening

## Repair Categories

Phase 104 uses a smaller repair classification layer on top of the existing failure taxonomy:

- `route_rule`
- `skill_metadata`
- `tool_availability`
- `prompt_ambiguity`
- `model_quality`
- `docs_setup_issue`
- `unsupported_scope`

These categories intentionally differ from the lower-level failure taxonomy categories. The taxonomy says what failed; the eval repair loop says where to repair next.

## Inputs

Supported inputs:

- `failure_taxonomy_report`
- `recursive_blind_testing_report`

For raw failed validation runs, generate taxonomy first:

```bash
python scripts/report_failure_taxonomy.py \
  --report runtime-state/founder-field-tests/<failed-run>.json \
  --label failed-field-run \
  --output-path runtime-state/failure-taxonomy/<failed-run>-taxonomy.json
```

Then generate repair recommendations:

```bash
python scripts/report_eval_repair_loop.py \
  --failure-taxonomy-report runtime-state/failure-taxonomy/<failed-run>-taxonomy.json \
  --target-prompt-case-id P01 \
  --holdout-prompt-case-id P02
```

## Output

Reports are written under:

```text
runtime-state/eval-repair-loop/
```

Each recommendation includes:

- `failure_category`
- `evidence_refs`
- `target_file_or_artifact`
- `minimal_repair_recommendation`
- `validation_command`
- `target_prompt_case_id`
- `target_rerun_command`
- `target_result_status`
- `holdout_prompt_case_id`
- `holdout_rerun_command`
- `holdout_result_status`
- `repair_cycle_count`
- `advisory_only`
- `current_phase_tightening`
- `fixture_mutation_guard`
- `accepted_repair_status`

## Pass And Fail Rules

A report cannot pass when:

- a failed eval has no classified recommendation
- evidence, target artifact, or validation command is missing
- repair cycle count exceeds `2`
- current-phase tightening lacks target and holdout rerun commands
- current-phase tightening lacks `target_result_status=passed`
- current-phase tightening lacks `holdout_result_status=passed`
- a recursive report ended by round exhaustion
- unresolved critical or high recursive findings remain
- the recursive score is below the policy threshold
- protected fixture mutation is detected
- non-current-phase recommendations are marked actionable instead of advisory

## Safety

All recommendations are advisory unless a later phase explicitly accepts them as current-phase tightening and validates both the target prompt and at least one holdout prompt.

Fixture mutation is a hard stop, not a repair suggestion.

## Regression

Focused regression:

```bash
python -m pytest tests/regression/test_eval_repair_loop.py tests/regression/test_failure_taxonomy.py tests/regression/test_recursive_blind_testing.py -q
```

All non-agent code changes still require:

```bash
python -m pytest tests/regression/ -v
```
