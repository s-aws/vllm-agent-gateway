# Run Observability

Run observability summarizes recent controller run records so a tester can review route decisions, selected skills, selected tools, approval state, artifacts, failures, mutation proof, and timing without opening the artifact tree by hand.

Use it after AnythingLLM, gateway, or live validation runs when you need to answer:

- which workflow was selected
- whether model routing was available for the run
- which skills and tools were selected
- whether approval is waiting, finished, blocked, denied, or not required
- which downstream workflow ran
- how many artifacts were written
- whether failures or warnings were recorded
- whether source or disposable-copy mutation proof exists

The report is read-only. It does not call the model, controller, gateway, AnythingLLM, or target repositories.

## CLI

Generate a text report for recent workflow-router runs:

```bash
python scripts/report_run_observability.py \
  --controller-output-root /mnt/c/private_agentic_agents/runtime-state/controller-artifacts \
  --workflow workflow_router.plan \
  --limit 10
```

Write a durable JSON report:

```bash
python scripts/report_run_observability.py \
  --controller-output-root /mnt/c/private_agentic_agents/runtime-state/controller-artifacts \
  --workflow workflow_router.plan \
  --limit 20 \
  --format json \
  --output-path runtime-state/run-observability/latest-workflow-router.json
```

Filter a report:

```bash
python scripts/report_run_observability.py \
  --controller-output-root /mnt/c/private_agentic_agents/runtime-state/controller-artifacts \
  --workflow workflow_router.plan \
  --prompt-family l1_documentation_lookup_terms \
  --skill documentation-lookup \
  --model-status accepted \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --route-status ready \
  --semantic-status completed_no_failures \
  --limit 10
```

## Output

Text output starts with `Run Observability Report`, then shows route-status counts, selected-workflow counts, approval-state counts, downstream-status counts, duration metrics when available, and a compact recent-run list.

JSON output uses `kind=controller_run_observability_report` and includes:

- `filters`
- `metrics.by_route_status`
- `metrics.by_selected_workflow`
- `metrics.by_approval_status`
- `metrics.by_downstream_status`
- `metrics.duration_seconds`
- `runs[].model_router_status`
- `runs[].selected_skills`
- `runs[].selected_tools`
- `runs[].approval_status`
- `runs[].failure_categories`
- `runs[].artifact_count`
- `runs[].mutation_proof`

## Relationship To Run Inspector

Use [README.run-inspector.md](README.run-inspector.md) for one specific run. Use this observability report for a recent-run dashboard across multiple runs.

## Validation

Focused regression:

```powershell
python -m pytest tests\regression\test_run_inspector.py -q
```

Bash-side live artifact review:

```bash
python scripts/report_run_observability.py \
  --controller-output-root /mnt/c/private_agentic_agents/runtime-state/controller-artifacts \
  --workflow workflow_router.plan \
  --limit 30 \
  --format json \
  --output-path runtime-state/run-observability/latest-workflow-router.json
```

## Examples

See [docs/examples/observability.md](docs/examples/observability.md).
