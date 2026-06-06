# Run Observability Examples

Use run observability after live AnythingLLM or gateway validation to review recent controller runs without opening each artifact manually.

## Text Dashboard

```bash
python scripts/report_run_observability.py \
  --controller-output-root /mnt/c/private_agentic_agents/runtime-state/controller-artifacts \
  --workflow workflow_router.plan \
  --limit 10
```

Expected markers:

- `Run Observability Report`
- `Run count:`
- `Route status:`
- `Selected workflow:`
- `Approval status:`
- `Downstream status:`
- `Recent runs:`
- per-run `model=`, `approval=`, `downstream=`, `skills=`, `tools=`, `artifacts=`, and `duration=`

## Durable JSON Report

```bash
python scripts/report_run_observability.py \
  --controller-output-root /mnt/c/private_agentic_agents/runtime-state/controller-artifacts \
  --workflow workflow_router.plan \
  --limit 30 \
  --format json \
  --output-path runtime-state/run-observability/latest-workflow-router.json
```

Expected JSON markers:

- `kind=controller_run_observability_report`
- `metrics.by_selected_workflow`
- `metrics.by_approval_status`
- `metrics.by_downstream_status`
- `metrics.duration_seconds`
- `runs[].model_router_status`
- `runs[].selected_skills`
- `runs[].selected_tools`
- `runs[].mutation_proof`

## Filtered Report

```bash
python scripts/report_run_observability.py \
  --controller-output-root /mnt/c/private_agentic_agents/runtime-state/controller-artifacts \
  --workflow workflow_router.plan \
  --prompt-family execution_planning_terms \
  --skill execution-plan-writer \
  --model-status accepted \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --route-status ready \
  --semantic-status completed_no_failures \
  --limit 5
```

Available filters:

- `--workflow`
- `--prompt-family`
- `--skill`
- `--model-status`
- `--target-root`
- `--route-status`
- `--semantic-status`
- `--failure-category`

## Fixture Coverage Check

After a live validation suite, the report should include recent runs for both protected frozen fixtures:

- `/mnt/c/coinbase_testing_repo_frozen_tmp`
- `/mnt/c/coinbase_testing_repo_frozen_tmp.github`

The report is read-only. It does not call localhost `8000`, controller/gateway ports, AnythingLLM, or mutate target repositories.
