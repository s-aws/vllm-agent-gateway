# Founder Field Prompt Evaluation

- Status: failed
- Created at: 20260606T001557214472Z
- AnythingLLM workspace: my-workspace
- Prompt count: 26
- Passed: 20
- Failed: 6

## Results

| Case | Status | Expected workflow | Run ID | Initial difference | Miss suggestion |
| --- | --- | --- | --- | --- | --- |
| P01 | passed | code_investigation.plan | workflow-router-20260606T001558672132Z | No marker-level difference from the baseline target. |  |
| P02 | failed | code_investigation.plan | workflow-router-20260606T001610127793Z | Response missed baseline chat markers: Inputs:, Outputs:, Side effects:, StealthOrderManager.find_stealth_order_by_placed_order_id | Name the function and file, and request inputs, outputs, side effects, and tests. |
| P03 | passed | code_investigation.plan | workflow-router-20260606T001628327515Z | No marker-level difference from the baseline target. |  |
| P04 | failed | code_investigation.plan | workflow-router-20260606T001641365226Z | Response missed baseline chat markers: Evidence files:, Result: yes | Ask for yes/no/unknown with evidence and keep the request read-only. |
| P05 | passed | code_context.lookup | workflow-router-20260606T001656650291Z | No marker-level difference from the baseline target. |  |
| P06 | failed | code_investigation.plan | workflow-router-20260606T001713226374Z | Response missed baseline chat markers: COINBASE_API_KEY, Runtime effect: | Ask for configuration references and runtime effect, plus a no-secret-values constraint. |
| P07 | passed | code_investigation.plan | workflow-router-20260606T001729665929Z | No marker-level difference from the baseline target. |  |
| P08 | passed | code_investigation.plan | workflow-router-20260606T001743836071Z | No marker-level difference from the baseline target. |  |
| P09 | passed | code_investigation.plan | workflow-router-20260606T001759541673Z | No marker-level difference from the baseline target. |  |
| P10 | failed | code_investigation.plan | workflow-router-20260606T001810381007Z | Response missed baseline chat markers: Definitions:, Responsibilities:, Target module: core/stealth_order_manager.py | Name the target module and ask for responsibilities, definitions, tests, and risks. |
| P11 | passed | code_investigation.plan | workflow-router-20260606T001821390186Z | No marker-level difference from the baseline target. |  |
| P12 | passed | code_context.lookup | workflow-router-20260606T001836117636Z | No marker-level difference from the baseline target. |  |
| P13 | passed | code_investigation.plan | workflow-router-20260606T001852234700Z | No marker-level difference from the baseline target. |  |
| P14 | passed | code_investigation.plan | workflow-router-20260606T001912779150Z | No marker-level difference from the baseline target. |  |
| P15 | passed | code_investigation.plan | workflow-router-20260606T001924324650Z | No marker-level difference from the baseline target. |  |
| P16 | passed | code_investigation.plan | workflow-router-20260606T001938449354Z | No marker-level difference from the baseline target. |  |
| P17 | passed | code_investigation.plan | workflow-router-20260606T001949697354Z | No marker-level difference from the baseline target. |  |
| P18 | passed | code_investigation.plan | workflow-router-20260606T002000926684Z | No marker-level difference from the baseline target. |  |
| P19 | passed | code_investigation.plan | workflow-router-20260606T002014856987Z | No marker-level difference from the baseline target. |  |
| P20 | passed | code_investigation.plan | workflow-router-20260606T002026466933Z | No marker-level difference from the baseline target. |  |
| P21 | passed | code_investigation.plan | workflow-router-20260606T002037391412Z | No marker-level difference from the baseline target. |  |
| P22 | passed | task.decompose | workflow-router-20260606T002050679564Z | No marker-level difference from the baseline target. |  |
| P23 | failed | execution_planning.plan | workflow-router-20260606T002053155365Z | Response missed baseline chat markers: Draft proposal:, Source mutation: false, docs/agents/INVARIANTS.md | Use 'draft' or 'do not mutate files' and ask for exact proposed change plus verification command. |
| P24 | passed | execution_planning.plan | workflow-router-20260606T002055819691Z | No marker-level difference from the baseline target. |  |
| P25 | passed | execution_planning.plan | workflow-router-20260606T002101365969Z | No marker-level difference from the baseline target. |  |
| P26 | failed | execution_planning.plan | workflow-router-20260606T002105704323Z | Response missed baseline chat markers: disposable_copy_changed: True, downstream_workflow: implementation.workflow | Say 'approved disposable copy apply only' if the router refuses the less rigid wording. |

## Prompt Baselines

### P01

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, where does the placed_order_id stealth lookup start? Read only and give me the beginning point, evidence files, related tests, and confidence.

Baseline target: A read-only beginning-point answer with the first relevant source location, evidence files, related tests, recommended commands, and a confidence statement.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T001558672132Z`

### P02

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, explain find_stealth_order_by_placed_order_id in core/stealth_order_manager.py. I need inputs, return value, side effects, and tests that cover it. Read only.

Baseline target: A function explanation with inputs, outputs, side effects, related tests, and source refs.

Expected workflow: `code_investigation.plan`

Initial difference: Response missed baseline chat markers: Inputs:, Outputs:, Side effects:, StealthOrderManager.find_stealth_order_by_placed_order_id

Suggested prompt if missed: Name the function and file, and request inputs, outputs, side effects, and tests.

Run ID: `workflow-router-20260606T001610127793Z`

### P03

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, what tests should I look at for placed_order_id stealth lookup? Read only. Include exact test files and the smallest useful pytest command.

Baseline target: A related-test answer with exact test files and the smallest useful pytest command.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T001628327515Z`

### P04

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, does the repo already have placed_order_id stealth lookup behavior? Read only. Answer yes/no/unknown with evidence.

Baseline target: A conservative yes/no/unknown behavior-existence answer with evidence and no invented absence claim.

Expected workflow: `code_investigation.plan`

Initial difference: Response missed baseline chat markers: Evidence files:, Result: yes

Suggested prompt if missed: Ask for yes/no/unknown with evidence and keep the request read-only.

Run ID: `workflow-router-20260606T001641365226Z`

### P05

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find every caller or usage of find_stealth_order_by_placed_order_id and group them by file. Read only.

Baseline target: A usage summary grouped by file, with short explanations and source refs.

Expected workflow: `code_context.lookup`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T001656650291Z`

### P06

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, where is COINBASE_API_KEY used and what does it affect at runtime? Read only. Do not expose any secret values.

Baseline target: A configuration answer showing references and runtime effect without exposing secret values.

Expected workflow: `code_investigation.plan`

Initial difference: Response missed baseline chat markers: COINBASE_API_KEY, Runtime effect:

Suggested prompt if missed: Ask for configuration references and runtime effect, plus a no-secret-values constraint.

Run ID: `workflow-router-20260606T001713226374Z`

### P07

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, summarize this pytest failure and tell me the next bounded inspection step. Do not edit files. FAILED tests/unit/test_order_id_and_followup_rules.py::test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - AssertionError: expected client_order_id index

Baseline target: A pasted-failure summary with failed test, primary error, likely cause, and next bounded inspection step.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T001729665929Z`

### P08

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find the dashboard handler for request_stealth_orders. Read only. Return the handler file, related source refs, and related tests.

Baseline target: An endpoint/handler lookup with handler file, source refs, and related tests.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T001743836071Z`

### P09

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find the source of the error message "Missing 'type' field in message". Read only. Return file, line, and why it is raised.

Baseline target: An error-message source lookup with source file, line/ref, and role.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T001759541673Z`

### P10

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, summarize core/stealth_order_manager.py for a new maintainer. Read only. Include responsibilities, important definitions, related tests, and risks.

Baseline target: A module summary with responsibilities, definitions, related tests, and risks.

Expected workflow: `code_investigation.plan`

Initial difference: Response missed baseline chat markers: Definitions:, Responsibilities:, Target module: core/stealth_order_manager.py

Suggested prompt if missed: Name the target module and ask for responsibilities, definitions, tests, and risks.

Run ID: `workflow-router-20260606T001810381007Z`

### P11

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find the stealth_orders database schema fields. Read only. Return model files, field names, and source refs.

Baseline target: A data model/schema lookup with model files, fields, and source refs.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T001821390186Z`

### P12

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, list the imports and local dependencies of core/stealth_order_manager.py. Read only. Group external and internal dependencies.

Baseline target: A dependency lookup grouped into imports and internal/local dependencies.

Expected workflow: `code_context.lookup`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T001836117636Z`

### P13

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp, find recent or local changes. Read only. If this is not a git repo, say that directly and list what can still be inspected.

Baseline target: A local-change summary that honestly reports non-git limitations and does not invent commit history.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T001852234700Z`

### P14

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, identify test coverage gaps for placed_order_id stealth lookup. Read only. Include covered tests, missing scenarios, and verification commands.

Baseline target: A coverage-gap summary with covered tests, missing scenarios, and verification commands.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T001912779150Z`

### P15

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find documentation for request_stealth_orders dashboard behavior. Read only. Return docs, source refs, and gaps.

Baseline target: A documentation lookup with docs, source refs, and explicit gaps.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T001924324650Z`

### P16

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, locate the CLI or script entrypoint for running the trading engine. Read only. Return the command and source refs.

Baseline target: A CLI entrypoint answer with file, command, and source refs.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T001938449354Z`

### P17

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, choose the smallest, medium, and broad validation commands for placed_order_id stealth lookup. Read only. Explain why each command matters and what risk remains.

Baseline target: A test-selection plan with smallest, medium, and broad commands, rationale, risks, confidence, and gaps.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T001949697354Z`

### P18

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, diagnose this runtime stack trace for request_stealth_orders. Read only. Traceback (most recent call last): File "dashboard_server.py", line 10, in handle_websocket_message core.exceptions.WebSocketMessageError: Missing 'type' field in message

Baseline target: A runtime-error diagnosis with observed error, likely cause, evidence files, next inspection, risks, gaps, and verification.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T002000926684Z`

### P19

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, map the request/data flow for request_stealth_orders from dashboard message to stealth order snapshot. Read only. Include flow steps, participating files, risks, and gaps.

Baseline target: A request/data-flow map with ordered flow steps, participating files, risks, gaps, and verification.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T002014856987Z`

### P20

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, compare the placed_order_id stealth lookup path with the client_order_id index path. Read only. Return candidate paths, evidence, risks, recommended path if supported, and gaps.

Baseline target: A code-path comparison with candidate paths, evidence, risks, recommendation if supported, and gaps.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T002026466933Z`

### P21

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, identify the minimal safe change surface for changing placed_order_id stealth lookup behavior. Read only and stop before implementation.

Baseline target: A change-surface summary with files to review, related tests, risk level, gaps, and no implementation.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T002037391412Z`

### P22

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, break down the work to add a safer placed_order_id lookup change. Do not implement. I want dependencies, approval gates, verification strategy, and risks.

Baseline target: A task decomposition with work packages, dependencies, approval gates, verification strategy, risks, and uncertainty.

Expected workflow: `task.decompose`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T002050679564Z`

### P23

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, draft a small documentation edit to docs/agents/INVARIANTS.md that adds a note saying the stealth manager placed-order index is the authoritative lookup key. Do not mutate files. Show exact proposed change and verification command.

Baseline target: A draft-only implementation proposal with exact file, operation, safety checks, verification command, and no source mutation.

Expected workflow: `execution_planning.plan`

Initial difference: Response missed baseline chat markers: Draft proposal:, Source mutation: false, docs/agents/INVARIANTS.md

Suggested prompt if missed: Use 'draft' or 'do not mutate files' and ask for exact proposed change plus verification command.

Run ID: `workflow-router-20260606T002053155365Z`

### P24

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, draft a small unit test for sync_exchange_order_id_for_placed_order setting exchange_order_id when it is missing. Do not mutate files. Show the proposed test file and pytest command.

Baseline target: A draft-only unit-test proposal with target test file, proposed test body/operation, verification command, and no source mutation.

Expected workflow: `execution_planning.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T002055819691Z`

### P25

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, inspect this failing test and propose the smallest fix. Draft only; do not apply until approved. FAILED tests/unit/test_order_id_and_followup_rules.py::test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - AssertionError: expected find_stealth_order_by_placed_order_id docstring to mention client_order_id

Baseline target: A draft-only simple-fix proposal with exact proposed operation, verification command, and approval gate.

Expected workflow: `execution_planning.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T002101365969Z`

### P26

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, apply this exact packet only to a disposable copy and prove the source repo did not change: {"packet_operations":[{"kind":"replace_text","path":"docs/agents/INVARIANTS.md","old":"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, and DB\n  local rows.","new":"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, DB\n  local rows, and stealth manager placed-order index keys."}]}

Baseline target: A disposable-copy apply proof that mutates only the copy, rolls it back, and reports source_changed false.

Expected workflow: `execution_planning.plan`

Initial difference: Response missed baseline chat markers: disposable_copy_changed: True, downstream_workflow: implementation.workflow

Suggested prompt if missed: Say 'approved disposable copy apply only' if the router refuses the less rigid wording.

Run ID: `workflow-router-20260606T002105704323Z`

