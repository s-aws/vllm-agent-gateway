# Founder Field Prompt Evaluation

- Status: passed
- Created at: 20260606T002620057820Z
- AnythingLLM workspace: my-workspace
- Prompt count: 6
- Passed: 6
- Failed: 0

## Results

| Case | Status | Expected workflow | Run ID | Initial difference | Miss suggestion |
| --- | --- | --- | --- | --- | --- |
| P02 | passed | code_investigation.plan | workflow-router-20260606T002621963126Z | No marker-level difference from the baseline target. |  |
| P04 | passed | code_investigation.plan | workflow-router-20260606T002631955335Z | No marker-level difference from the baseline target. |  |
| P06 | passed | code_investigation.plan | workflow-router-20260606T002640724088Z | No marker-level difference from the baseline target. |  |
| P10 | passed | code_investigation.plan | workflow-router-20260606T002654380397Z | No marker-level difference from the baseline target. |  |
| P23 | passed | execution_planning.plan | workflow-router-20260606T002705229584Z | No marker-level difference from the baseline target. |  |
| P26 | passed | execution_planning.plan | workflow-router-20260606T002711268855Z | No marker-level difference from the baseline target. |  |

## Prompt Baselines

### P02

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, explain find_stealth_order_by_placed_order_id in core/stealth_order_manager.py. I need inputs, return value, side effects, and tests that cover it. Read only.

Baseline target: A function explanation with inputs, outputs, side effects, related tests, and source refs.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T002621963126Z`

### P04

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, does the repo already have placed_order_id stealth lookup behavior? Read only. Answer yes/no/unknown with evidence.

Baseline target: A conservative yes/no/unknown behavior-existence answer with evidence and no invented absence claim.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T002631955335Z`

### P06

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, where is COINBASE_API_KEY used and what does it affect at runtime? Read only. Do not expose any secret values.

Baseline target: A configuration answer showing references and runtime effect without exposing secret values.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T002640724088Z`

### P10

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, summarize core/stealth_order_manager.py for a new maintainer. Read only. Include responsibilities, important definitions, related tests, and risks.

Baseline target: A module summary with responsibilities, definitions, related tests, and risks.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T002654380397Z`

### P23

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, draft a small documentation edit to docs/agents/INVARIANTS.md that adds a note saying the stealth manager placed-order index is the authoritative lookup key. Do not mutate files. Show exact proposed change and verification command.

Baseline target: A draft-only implementation proposal with exact file, operation, safety checks, verification command, and no source mutation.

Expected workflow: `execution_planning.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T002705229584Z`

### P26

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, apply this exact packet only to a disposable copy and prove the source repo did not change: {"packet_operations":[{"kind":"replace_text","path":"docs/agents/INVARIANTS.md","old":"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, and DB\n  local rows.","new":"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, DB\n  local rows, and stealth manager placed-order index keys."}]}

Baseline target: A disposable-copy apply proof that mutates only the copy, rolls it back, and reports source_changed false.

Expected workflow: `execution_planning.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T002711268855Z`

