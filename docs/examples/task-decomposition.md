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
- `task-decomposition.json.work_package_schema_version: 3`
- `task-decomposition.json.work_packages[].acceptance_criteria`
- `task-decomposition.json.work_packages[].scope_boundary`
- `task-decomposition.json.tenet_contract.phase: 113`

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
- `- Work-package schema: 3`
- `- Work packages:`
- `- Acceptance criteria:`
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
- `task_decomposition_contract.work_package_schema_version: 3`
- `task_decomposition_contract.tenet_contract.phase: 113`
- `task_decomposition_contract.work_packages[].stage`
- `task_decomposition_contract.work_packages[].acceptance_criteria`
- `task_decomposition_contract.work_packages[].scope_boundary`
- `task_decomposition_contract.work_packages[].stop_conditions`
- `task_decomposition_contract.approval_gates`

## Requirements Translation

Prompt:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, translate this business requirement into technical requirements and estimate effort: users need the stealth order lookup answer to say whether placed_order_id evidence was found. Return the answer in the default format.
```

Expected chat-visible markers:

- `Requirements Translation:`
- `- Business requirements:`
- `- Technical requirements:`
- `- Explicit assumptions:`
- `- Rejected assumptions:`
- `- Effort estimate:`
- `- Revision triggers:`
- `- Source mutation: False`

JSON output includes:

- `task_decomposition_contract.prompt_family: requirements_translation`
- `task_decomposition_contract.tenet_contract.phase: 114`
- `task_decomposition_contract.requirements_translation.source_business_requirements`
- `task_decomposition_contract.requirements_translation.technical_requirements`
- `task_decomposition_contract.requirements_translation.explicit_assumptions`
- `task_decomposition_contract.requirements_translation.rejected_assumptions`
- `task_decomposition_contract.requirements_translation.effort_estimate`
- `task_decomposition_contract.requirements_translation.estimate_revision`

Estimate revision prompt:

```text
In /mnt/c/agentic_agents/tests/fixtures/generalization/python_service_fixture, translate this business requirement into technical requirements and revise estimate because scope changed: the create-order response should show resolved order status and now also include a requirement note without changing files yet.
```

## Incremental Implementation Plan

Prompt:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, create an incremental implementation plan for adding a requirement note to the stealth order lookup answer. Include isolated changesets, verification commands, and meaningful commit messages. Do not change files. Return the answer in the default format.
```

Expected chat-visible markers:

- `Incremental Implementation Plan:`
- `- Changesets:`
- `- Changeset verification:`
- `- Commit messages:`
- `- Commit order:`
- `- Branch:`
- `- Version-control policy:`
- `- Source apply policy: blocked_in_task_decompose`
- `- Source mutation: False`

JSON output includes:

- `task_decomposition_contract.prompt_family: incremental_implementation_plan`
- `task_decomposition_contract.tenet_contract.phase: 115`
- `task_decomposition_contract.incremental_implementation_plan.changesets`
- `task_decomposition_contract.incremental_implementation_plan.version_control_plan.commit_order`
- `task_decomposition_contract.incremental_implementation_plan.source_apply_policy.status: blocked_in_task_decompose`

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

## Oversized Request

Prompt:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, break down this task into independently reviewable steps with dependencies and acceptance criteria: rewrite the whole project so every module has better architecture.
```

Expected response:

- `summary.decomposition_status: needs_clarification`
- `summary.prompt_family: oversized`
- `summary.next_action: ask_blocking_question`
- `task-decomposition.json.decomposition_guidance`
- no implementation packet artifacts

## Phase 113 Case Catalog

```bash
python3 scripts/validate_task_decomposition_phase113_cases.py \
  --output-path runtime-state/task-decomposition/phase113-case-catalog.json
```

Expected markers:

- `TASK DECOMPOSITION PHASE113 CASES ...`
- `"status": "passed"`
- prompt families include `feature`, `bug`, `requirement`, and `oversized`

## Phase 114 Case Catalog

```bash
python3 scripts/validate_requirements_translation_phase114_cases.py \
  --output-path runtime-state/task-decomposition/phase114-case-catalog.json
```

Expected markers:

- `REQUIREMENTS TRANSLATION PHASE114 CASES ...`
- `"status": "passed"`
- case types include `business_to_technical` and `estimate_revision`

## Phase 115 Case Catalog

```bash
python3 scripts/validate_incremental_implementation_phase115_cases.py \
  --output-path runtime-state/task-decomposition/phase115-case-catalog.json
```

Expected markers:

- `INCREMENTAL IMPLEMENTATION PHASE115 CASES ...`
- `"status": "passed"`
- case types include `feature_implementation_plan` and `test_update_plan`

## Live Gate

Run from Bash:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_task_decomposition_live.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --target-root /mnt/c/agentic_agents/tests/fixtures/generalization/python_service_fixture \
  --timeout-seconds 900
```

The live gate exercises feature, bug, and requirement prompts through direct controller, workflow-router gateway, and AnythingLLM for each target root.

Run the Phase 114 requirements translation live gate from Bash:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_requirements_translation_live.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --target-root /mnt/c/agentic_agents/tests/fixtures/generalization/python_service_fixture \
  --timeout-seconds 900
```

The Phase 114 live gate exercises business-to-technical and estimate-revision prompts through direct controller, workflow-router gateway, and AnythingLLM for each target root.

Run the Phase 115 incremental implementation live gate from Bash:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_incremental_implementation_live.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --target-root /mnt/c/agentic_agents/tests/fixtures/generalization/python_service_fixture \
  --timeout-seconds 900
```

The Phase 115 live gate exercises feature-implementation and test-update planning prompts through direct controller, workflow-router gateway, and AnythingLLM for each target root.

Validate a single emitted decomposition artifact:

```bash
python3 scripts/validate_task_decomposition_quality.py \
  runtime-state/controller-artifacts/task-decompositions/<run-id>/task-decomposition.json
```
