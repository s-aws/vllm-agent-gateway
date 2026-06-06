# Prompt Skill Coverage Map

Phase 79 makes prompt-to-skill coverage explicit.

The source of truth is:

```text
runtime/prompt_skill_coverage.json
```

## Entry Shape

Implemented entries include:

- `id`
- `prompt_family`
- `level`
- `status`
- `selected_workflow`
- `route_rule`
- `skill_ids`
- `tool_ids`
- `eval_case_ids`
- `expected_artifacts`
- `validation_suites`
- `docs_examples`

Controller-owned entries may omit `skill_ids` and `eval_case_ids` only when they set `controller_owned=true` and include `regression_test_refs`.

## Gap Backlog

Gaps use:

- `id`
- `prompt_family`
- `status`
- `source`
- `reason`
- `suggested_next_phase`

Allowed gap statuses are:

- `planned`
- `deferred`

The advanced single-path refactor prompt must remain recorded as `deferred` until a later advanced roadmap phase explicitly reactivates it.

## Validation

Run:

```bash
python scripts/validate_prompt_skill_coverage.py \
  --output-path runtime-state/prompt-skill-coverage/phase79-current.json
```

The validator checks the coverage map against:

- `runtime/workflows.json`
- `runtime/tools.json`
- `runtime/skills.json`
- `runtime/skill_evals.json`
- `runtime/prompt_catalogs/founder_field_v1.json`
- `vllm_agent_gateway/controllers/workflow_router/plan.py`
- linked docs and examples

## Current Coverage

Phase 79 covers:

- `L1-001` through `L1-021`
- `D1-004` through `D1-006`
- `L2-001`, `L2-002`, `L2-003`, and `L2-005` through `L2-009`
- `task-decomposition`
- `disposable-copy-apply`

Phase 79 backlog includes:

- `GAP-L2-004`: approved draft implementation prep
- `GAP-ADV-REFACTOR-SINGLE-PATH`: deferred advanced refactor orchestration

## Update Workflow

When adding or changing a prompt family:

1. Add or update the route rule and controller behavior.
2. Add or update the skill metadata and eval case if the family is skill-backed.
3. Add the coverage entry.
4. Add docs/examples links.
5. Run the coverage validator.
6. Run focused regression for the workflow.
7. Run full regression for runtime-facing changes.

Do not add a prompt family to `implemented` unless it has either skill eval coverage or controller-owned regression coverage.
