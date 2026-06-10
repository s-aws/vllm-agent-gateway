# Task Decomposition

`task.decompose` is a controller-owned read-only workflow for breaking a larger coding request into ordered work packages before implementation starts.

It does not read source files, create implementation packets, apply changes, or mutate runtime registries. It uses registered workflow, skill, and tool metadata to classify the request, choose the next safe workflows, mark approval gates, and show uncertainty where repository evidence has not been gathered yet.

## When To Use It

Use this workflow when a request is larger than a single L1/L2 lookup and the tester needs a deterministic execution shape before starting work.

Example:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, decompose this multi-step task into work packages with dependencies, approval gates, and verification strategy: add a focused unit test for placed_order_id stealth lookup after investigating related tests.
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
  "user_request": "Decompose this multi-step task into work packages with dependencies, approval gates, and verification strategy: add a focused unit test for placed_order_id stealth lookup after investigating related tests."
}
```

## Output

The main artifact is `task-decomposition.json`.

It includes:

- prompt family and risk level
- `work_package_schema_version: 3`
- ordered work packages with stage, dependency contract, entry conditions, exit criteria, objective acceptance criteria, independent review boundary, stop conditions, and per-package verification status
- dependency edges
- selected registered workflows
- selected registered skills and tools
- approval gates derived from the package contract
- verification strategy
- Phase 113 tenet contract for decomposition and acceptance criteria, Phase 114 tenet contract for requirements translation and estimation, or Phase 115 tenet contract for incremental implementation and version-control planning
- optional `requirements_translation` contract with source business requirements, derived technical requirements, explicit assumptions, rejected assumptions, effort estimate, scope drivers, and revision triggers
- optional `incremental_implementation_plan` contract with isolated changesets, functional outcomes, verification commands, acceptance checks, meaningful commit messages, commit order, branch guidance, traceability artifacts, and a blocked source-apply policy
- uncertainty markers
- mutation proof fields

The default AnythingLLM/chat output uses `format_a` and includes a chat-visible `Task Decomposition:` section with package stages, stop conditions, package verification, approval gates, and mutation proof. Requirements prompts also include a chat-visible `Requirements Translation:` section with business requirements, technical requirements, assumptions, rejected assumptions, effort estimate, and revision triggers. Incremental implementation prompts also include an `Incremental Implementation Plan:` section with changesets, verification, commit messages, commit order, branch guidance, and source-apply policy. JSON output includes the normal `chat_contract`, artifact paths, and an inline `task_decomposition_contract` so users can review the plan without opening artifact files.
The chat output also includes acceptance-criteria IDs so a tester can see whether the plan is objective before opening artifacts.

## Safety Boundary

- Source files are not read by this workflow.
- Repository files are not changed.
- Runtime registry files are not changed.
- Non-null workflow references must exist in `runtime/workflows.json`.
- Missing apply capability is represented as an approval gate, not as an invented workflow.
- Ambiguous requests return `needs_clarification` and `next_action=ask_blocking_question`.
- Oversized requests such as whole-project rewrites return `needs_clarification`, `prompt_family=oversized`, and further-decomposition guidance instead of implementation packages.
- Broad single-path or one-code-path refactor orchestration is blocked as `advanced_refactor_deferred` until Phase 105 readiness.

## Validation

Focused regression:

```bash
python -m pytest tests/regression/test_task_decomposition.py -q
```

Artifact quality gate:

```bash
python scripts/validate_task_decomposition_quality.py path/to/task-decomposition.json
```

Phase 113 prompt and audit case catalog:

```bash
python scripts/validate_task_decomposition_phase113_cases.py \
  --output-path runtime-state/task-decomposition/phase113-case-catalog.json
```

Phase 114 requirements translation prompt and audit case catalog:

```bash
python scripts/validate_requirements_translation_phase114_cases.py \
  --output-path runtime-state/task-decomposition/phase114-case-catalog.json
```

Phase 115 incremental implementation prompt and audit case catalog:

```bash
python scripts/validate_incremental_implementation_phase115_cases.py \
  --output-path runtime-state/task-decomposition/phase115-case-catalog.json
```

Live validation:

```bash
python3 scripts/validate_task_decomposition_live.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --target-root /mnt/c/agentic_agents/tests/fixtures/generalization/python_service_fixture \
  --timeout-seconds 900
```

The live gate exercises feature, bug, and requirement decomposition prompts through direct controller, workflow-router gateway, and AnythingLLM for each target root.

Requirements translation live validation:

```bash
python3 scripts/validate_requirements_translation_live.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --target-root /mnt/c/agentic_agents/tests/fixtures/generalization/python_service_fixture \
  --timeout-seconds 900
```

The requirements live gate exercises business-to-technical and estimate-revision prompts through direct controller, workflow-router gateway, and AnythingLLM for each target root.

Incremental implementation live validation:

```bash
python3 scripts/validate_incremental_implementation_live.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --target-root /mnt/c/agentic_agents/tests/fixtures/generalization/python_service_fixture \
  --timeout-seconds 900
```

The incremental implementation live gate exercises feature-implementation and test-update planning prompts through direct controller, workflow-router gateway, and AnythingLLM for each target root.

## References

- Roadmap: [docs/ACTIONABLE_WORKFLOW_ROADMAP.md](docs/ACTIONABLE_WORKFLOW_ROADMAP.md)
- Examples: [docs/examples/task-decomposition.md](docs/examples/task-decomposition.md)
