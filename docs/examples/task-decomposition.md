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
    "user_request": "Decompose this multi-step task into work packages with dependencies, approval gates, and verification strategy: add a focused unit test for placed_order_id stealth lookup after investigating related tests."
  }'
```

Expected response fields:

- `workflow: task.decompose`
- `status: completed`
- `summary.decomposition_status: ready`
- `summary.prompt_family: feature_or_small_change`
- `summary.target_repository_changed: false`
- `artifacts.task_decomposition`
- `task-decomposition.json.work_package_schema_version: 2`

## AnythingLLM Prompt Through Workflow Router

Point AnythingLLM to:

```text
http://127.0.0.1:8500/v1
```

Prompt:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, decompose this multi-step task into work packages with dependencies, approval gates, and verification strategy: add a focused unit test for placed_order_id stealth lookup after investigating related tests. Return the answer in the default format.
```

Expected chat-visible markers:

- `Result:`
- `- Selected workflow: task.decompose`
- `Task Decomposition:`
- `- Work-package schema: 2`
- `- Work packages:`
- `- Dependencies:`
- `- Approval gates:`
- `- Stop conditions:`
- `- Package verification:`
- `- Uncertainty:`
- `- Verification:`
- `- Source mutation: False`

## JSON Output

Prompt:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, decompose this multi-step task into work packages with dependencies, approval gates, and verification strategy: add a focused unit test for placed_order_id stealth lookup after investigating related tests. Return JSON.
```

Expected JSON:

- `output_format: json`
- `chat_contract.selected_workflow: task.decompose`
- `chat_contract.next_action: none` after read-only execution completes
- `summary.downstream_workflow: task.decompose`
- `artifacts.downstream_task_decomposition`
- `task_decomposition_contract.work_package_schema_version: 2`
- `task_decomposition_contract.work_packages[].stage`
- `task_decomposition_contract.work_packages[].stop_conditions`
- `task_decomposition_contract.approval_gates`

## Deferred Advanced Refactor

Broad single-path refactor orchestration is intentionally deferred until Phase 105 readiness.

Prompt:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, decompose this multi-step task into work packages with dependencies, approval gates, and verification strategy: refactor the placed_order_id stealth lookup so there is one code path. Return JSON.
```

Expected JSON:

- `task_decomposition_contract.status: blocked`
- `task_decomposition_contract.prompt_family: advanced_refactor_deferred`
- `task_decomposition_contract.deferred_to_phase: 105`
- `task_decomposition_contract.work_packages[0].id: DEFER1`
- no implementation packet artifacts

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
