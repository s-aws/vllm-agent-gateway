# Task Decomposition Examples

These examples exercise `task.decompose`, the read-only workflow for turning larger coding requests into ordered work packages.

## Direct Controller Request

```bash
curl -sS http://127.0.0.1:8400/v1/controller/task-decompositions \
  -H "Content-Type: application/json" \
  -d '{
    "workflow": "task.decompose",
    "schema_version": 1,
    "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    "user_request": "Decompose this multi-step task into work packages with dependencies, approval gates, and verification strategy: refactor the placed_order_id stealth lookup so there is one code path."
  }'
```

Expected response fields:

- `workflow: task.decompose`
- `status: completed`
- `summary.decomposition_status: ready`
- `summary.prompt_family: multi_step_refactor`
- `summary.target_repository_changed: false`
- `artifacts.task_decomposition`

## AnythingLLM Prompt Through Workflow Router

Point AnythingLLM to:

```text
http://127.0.0.1:8500/v1
```

Prompt:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, decompose this multi-step task into work packages with dependencies, approval gates, and verification strategy: refactor the placed_order_id stealth lookup so there is one code path. Return the answer in the default format.
```

Expected chat-visible markers:

- `Result:`
- `- Selected workflow: task.decompose`
- `Task Decomposition:`
- `- Work packages:`
- `- Dependencies:`
- `- Approval gates:`
- `- Uncertainty:`
- `- Verification:`
- `- Source mutation: False`

## JSON Output

Prompt:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, decompose this multi-step task into work packages with dependencies, approval gates, and verification strategy: refactor the placed_order_id stealth lookup so there is one code path. Return JSON.
```

Expected JSON:

- `output_format: json`
- `chat_contract.selected_workflow: task.decompose`
- `chat_contract.next_action: none` after read-only execution completes
- `summary.downstream_workflow: task.decompose`
- `artifacts.downstream_task_decomposition`

## Ambiguous Request

```bash
curl -sS http://127.0.0.1:8400/v1/controller/task-decompositions \
  -H "Content-Type: application/json" \
  -d '{
    "workflow": "task.decompose",
    "schema_version": 1,
    "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    "user_request": "fix it"
  }'
```

Expected response:

- `summary.decomposition_status: needs_clarification`
- `summary.next_action: ask_blocking_question`
- `summary.package_count: 0`
- no implementation packet artifacts

## Live Gate

Run from Bash:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_task_decomposition_live.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900
```
