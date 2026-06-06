# Run Inspector

The run inspector summarizes controller run records without requiring a user to open the controller artifact tree by hand.

Use it after a workflow-router, feedback, lifecycle, or release validation run when you need a compact view of:

- run ID, workflow, status, and semantic status
- route decision, selected workflow, selected skills, selected tools, and route rules
- downstream workflow and artifact keys
- warnings, failures, resume key, and mutation proof
- durable artifact paths for deeper audit

The inspector is read-only. It does not contact the model, controller, gateway, AnythingLLM, or target repositories. It reads controller run records under `controller-runs/` and small JSON artifacts referenced by those records.

## CLI

Inspect the latest workflow-router run from the default or detected controller artifact root:

```bash
python scripts/inspect_latest_run.py --workflow workflow_router.plan
```

Inspect an explicit controller artifact root:

```bash
python scripts/inspect_latest_run.py \
  --controller-output-root /mnt/c/private_agentic_agents/runtime-state/controller-artifacts \
  --workflow workflow_router.plan
```

Write a durable JSON inspection report:

```bash
python scripts/inspect_latest_run.py \
  --controller-output-root /mnt/c/private_agentic_agents/runtime-state/controller-artifacts \
  --workflow workflow_router.plan \
  --format json \
  --output-path runtime-state/run-inspector/latest-workflow-router.json
```

Inspect a specific run:

```bash
python scripts/inspect_latest_run.py \
  --controller-output-root /mnt/c/private_agentic_agents/runtime-state/controller-artifacts \
  --run-id workflow-router-20260606T094508530797Z
```

## Artifact Roots

When `--controller-output-root` is omitted, the inspector checks:

- `CONTROLLER_OUTPUT_ROOT`
- `AGENTIC_AGENTS_STATE_ROOT/controller-artifacts`
- `runtime-state/controller-artifacts` under the repo
- `C:/private_agentic_agents/runtime-state/controller-artifacts`
- `/mnt/c/private_agentic_agents/runtime-state/controller-artifacts`

On Windows, it can read artifact paths stored as `/mnt/c/...` by converting them to `C:\...` before loading JSON.

## Safety

- Read-only artifact inspection only.
- No target repository mutation.
- No controller cleanup or cancellation.
- No model calls.
- No full artifact dumps in text mode.

## Examples

See [docs/examples/run-inspector.md](docs/examples/run-inspector.md).
