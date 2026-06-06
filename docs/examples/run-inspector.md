# Run Inspector Examples

These examples inspect controller artifacts. They do not call localhost model, gateway, controller, or AnythingLLM services.

## Latest Workflow Router Run

```bash
cd /mnt/c/agentic_agents
python3 scripts/inspect_latest_run.py \
  --controller-output-root /mnt/c/private_agentic_agents/runtime-state/controller-artifacts \
  --workflow workflow_router.plan
```

Expected text markers:

```text
Latest Run Inspection
- Run ID: workflow-router-
- Workflow: workflow_router.plan
- Semantic status:
- Route:
- Selected skills:
- Artifacts:
- Mutation proof:
```

## JSON Report

```bash
cd /mnt/c/agentic_agents
python3 scripts/inspect_latest_run.py \
  --controller-output-root /mnt/c/private_agentic_agents/runtime-state/controller-artifacts \
  --workflow workflow_router.plan \
  --format json \
  --output-path runtime-state/run-inspector/latest-workflow-router.json
```

Expected JSON fields:

```text
kind=controller_run_inspection
run_id=workflow-router-...
workflow=workflow_router.plan
route.selected_workflow=...
selected_skills=[...]
artifact_keys=[...]
mutation_proof.source_changed=false
```

## Specific Run

```bash
python3 scripts/inspect_latest_run.py \
  --controller-output-root /mnt/c/private_agentic_agents/runtime-state/controller-artifacts \
  --run-id workflow-router-20260606T094508530797Z
```

Use this after a tester reports a specific `run_id:` from AnythingLLM.
