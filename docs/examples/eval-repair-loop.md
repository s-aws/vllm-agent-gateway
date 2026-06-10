# Eval Repair Loop Examples

These examples generate repair recommendations from existing artifacts and, when explicitly requested, run the Phase 111 closed-loop target/holdout validation through localhost services.

The advisory examples do not contact localhost services. The closed-loop example does.

## From A Failed Founder Field Run

First classify the failed run:

```bash
cd /mnt/c/agentic_agents
python3 scripts/report_failure_taxonomy.py \
  --report runtime-state/founder-field-tests/<failed-run>.json \
  --label failed-field-run \
  --output-path runtime-state/failure-taxonomy/<failed-run>-taxonomy.json \
  --markdown-output-path runtime-state/failure-taxonomy/<failed-run>-taxonomy.md
```

Then generate repair recommendations:

```bash
python3 scripts/report_eval_repair_loop.py \
  --failure-taxonomy-report runtime-state/failure-taxonomy/<failed-run>-taxonomy.json \
  --target-prompt-case-id P01 \
  --holdout-prompt-case-id P02 \
  --output-path runtime-state/eval-repair-loop/<failed-run>-repair.json \
  --markdown-output-path runtime-state/eval-repair-loop/<failed-run>-repair.md
```

Expected markers:

```text
EVAL REPAIR LOOP REPORT ...
EVAL REPAIR LOOP SUMMARY ...
EVAL REPAIR LOOP PASS
```

## From A Recursive Blind-Testing Report

```bash
python3 scripts/report_eval_repair_loop.py \
  --recursive-report runtime-state/recursive-blind-testing/phase92-feedback-triage-recursive-report.json \
  --target-prompt-case-id P01 \
  --holdout-prompt-case-id P02
```

Recursive reports can contribute accepted findings and blind findings, but the repair loop still applies hard stops for unresolved critical/high findings, low scores, round exhaustion, fixture mutation, and holdout regression.

## Closed-Loop Target And Holdout Proof

Use this when a current-phase repair has already been accepted and needs executable proof instead of advisory status:

```bash
cd /mnt/c/agentic_agents
export WSLENV=ANYTHINGLLM_API_KEY/u
python3 scripts/validate_closed_loop_eval_repair.py \
  --execute-live \
  --include-port-health \
  --timeout-seconds 900 \
  --output-path runtime-state/eval-repair-loop/phase111-live-closed-loop-final.json
```

Expected markers:

```text
CLOSED LOOP EVAL REPAIR REPORT ...
CLOSED LOOP EVAL REPAIR SUMMARY ...
CLOSED LOOP EVAL REPAIR PASS
```

The current Phase 111 target is `L1-001`; the holdout is `L1-002`. The gate runs both through the workflow-router gateway and AnythingLLM on `/mnt/c/coinbase_testing_repo_frozen_tmp` and `/mnt/c/coinbase_testing_repo_frozen_tmp.github`.

If Bash cannot see `ANYTHINGLLM_API_KEY`, the target and holdout may pass gateway but fail AnythingLLM. Set `WSLENV=ANYTHINGLLM_API_KEY/u` in the Windows environment or for the current command invocation.

To prove the gate fails closed without live validation:

```bash
python3 scripts/validate_closed_loop_eval_repair.py \
  --output-path runtime-state/eval-repair-loop/phase111-offline-dry-run.json
```

Expected result: failed status with `target_result_status=not_run_required` and `holdout_result_status=not_run_required`.

## Expected JSON Fields

```text
kind=eval_repair_loop_report
status=passed|failed
summary.source_finding_count=...
summary.recommendation_count=...
summary.repair_category_counts={...}
recommendations[].failure_category=route_rule|skill_metadata|tool_availability|prompt_ambiguity|model_quality|docs_setup_issue|unsupported_scope
recommendations[].evidence_refs=[...]
recommendations[].target_file_or_artifact=[...]
recommendations[].minimal_repair_recommendation=...
recommendations[].validation_command=...
recommendations[].target_rerun_command=...
recommendations[].target_result_status=passed|failed|regressed|not_run_advisory|not_run_required
recommendations[].holdout_rerun_command=...
recommendations[].holdout_result_status=passed|failed|regressed|not_run_advisory|not_run_required
blocking_errors=[...]
validation_errors=[...]
markdown_report_path=...
```

Closed-loop execution reports use:

```text
kind=closed_loop_eval_repair_execution_report
status=passed|failed
before_failure_capture.status=failed_controlled_negative
repair_packet.accepted_repair_status=accepted_current_phase
execution.target_result_status=passed|failed|not_run_required
execution.holdout_result_status=passed|failed|not_run_required
deterministic_adjudication.status=accepted|partial
protected_fixture_mutation=false
final_eval_repair_report.status=passed|failed
validation_errors=[...]
```

## Review Order

1. Check `blocking_errors`; fixture mutation and holdout regression stop the loop.
2. Check `repair_category_counts` to see whether the issue is routing, skill metadata, tools, prompt ambiguity, model quality, setup, or unsupported scope.
3. For each recommendation, inspect `evidence_refs` before changing anything.
4. Run the listed `validation_command`.
5. For accepted current-phase tightening, rerun both `target_rerun_command` and `holdout_rerun_command`; both result statuses must be `passed`.
