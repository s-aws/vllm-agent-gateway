# Task Decomposition

`task.decompose` is a controller-owned read-only workflow for breaking a larger coding request into ordered work packages before implementation starts.

It does not read source files, create implementation packets, apply changes, or mutate runtime registries. It uses registered workflow, skill, and tool metadata to classify the request, choose the next safe workflows, mark approval gates, and show uncertainty where repository evidence has not been gathered yet.

## When To Use It

Use this workflow when a request is larger than a single L1/L2 lookup and the tester needs a deterministic execution shape before starting work.

Example:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, decompose this multi-step task into work packages with dependencies, approval gates, and verification strategy: refactor the placed_order_id stealth lookup so there is one code path.
```

Expected route through natural chat:

```text
workflow_router.plan -> task.decompose
```

## Endpoint

```text
POST /v1/controller/task-decompositions
POST /v1/controller/workflow-router/chat/completions
```

Direct controller payload:

```json
{
  "workflow": "task.decompose",
  "schema_version": 1,
  "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
  "user_request": "Decompose this multi-step task into work packages with dependencies, approval gates, and verification strategy: refactor the placed_order_id stealth lookup so there is one code path."
}
```

## Output

The main artifact is `task-decomposition.json`.

It includes:

- prompt family and risk level
- ordered work packages
- dependency edges
- selected registered workflows
- selected registered skills and tools
- approval gates
- verification strategy
- uncertainty markers
- mutation proof fields

The default AnythingLLM/chat output uses `format_a` and includes a chat-visible `Task Decomposition:` section. JSON output includes the normal `chat_contract` and artifact paths.

## Safety Boundary

- Source files are not read by this workflow.
- Repository files are not changed.
- Runtime registry files are not changed.
- Non-null workflow references must exist in `runtime/workflows.json`.
- Missing apply capability is represented as an approval gate, not as an invented workflow.
- Ambiguous requests return `needs_clarification` and `next_action=ask_blocking_question`.

## Validation

Focused regression:

```bash
python -m pytest tests/regression/test_task_decomposition.py -q
```

Live validation:

```bash
python3 scripts/validate_task_decomposition_live.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900
```

## References

- Roadmap: [docs/ACTIONABLE_WORKFLOW_ROADMAP.md](docs/ACTIONABLE_WORKFLOW_ROADMAP.md)
- Examples: [docs/examples/task-decomposition.md](docs/examples/task-decomposition.md)
