# Founder Field Prompt Evaluation

- Status: passed
- Created at: 20260606T005029609466Z
- AnythingLLM workspace: my-workspace
- Prompt count: 26
- Passed: 26
- Failed: 0

## Results

| Case | Status | Expected workflow | Run ID | Initial difference | Miss suggestion |
| --- | --- | --- | --- | --- | --- |
| P01 | passed | code_investigation.plan | workflow-router-20260606T005031499736Z | No marker-level difference from the baseline target. |  |
| P02 | passed | code_investigation.plan | workflow-router-20260606T005040534201Z | No marker-level difference from the baseline target. |  |
| P03 | passed | code_investigation.plan | workflow-router-20260606T005049658378Z | No marker-level difference from the baseline target. |  |
| P04 | passed | code_investigation.plan | workflow-router-20260606T005102271013Z | No marker-level difference from the baseline target. |  |
| P05 | passed | code_context.lookup | workflow-router-20260606T005110727490Z | No marker-level difference from the baseline target. |  |
| P06 | passed | code_investigation.plan | workflow-router-20260606T005126141531Z | No marker-level difference from the baseline target. |  |
| P07 | passed | code_investigation.plan | workflow-router-20260606T005140449864Z | No marker-level difference from the baseline target. |  |
| P08 | passed | code_investigation.plan | workflow-router-20260606T005152471040Z | No marker-level difference from the baseline target. |  |
| P09 | passed | code_investigation.plan | workflow-router-20260606T005206694276Z | No marker-level difference from the baseline target. |  |
| P10 | passed | code_investigation.plan | workflow-router-20260606T005217423981Z | No marker-level difference from the baseline target. |  |
| P11 | passed | code_investigation.plan | workflow-router-20260606T005228637508Z | No marker-level difference from the baseline target. |  |
| P12 | passed | code_context.lookup | workflow-router-20260606T005244135385Z | No marker-level difference from the baseline target. |  |
| P13 | passed | code_investigation.plan | workflow-router-20260606T005300416290Z | No marker-level difference from the baseline target. |  |
| P14 | passed | code_investigation.plan | workflow-router-20260606T005317634426Z | No marker-level difference from the baseline target. |  |
| P15 | passed | code_investigation.plan | workflow-router-20260606T005328558923Z | No marker-level difference from the baseline target. |  |
| P16 | passed | code_investigation.plan | workflow-router-20260606T005339530589Z | No marker-level difference from the baseline target. |  |
| P17 | passed | code_investigation.plan | workflow-router-20260606T005353585151Z | No marker-level difference from the baseline target. |  |
| P18 | passed | code_investigation.plan | workflow-router-20260606T005404667286Z | No marker-level difference from the baseline target. |  |
| P19 | passed | code_investigation.plan | workflow-router-20260606T005421041679Z | No marker-level difference from the baseline target. |  |
| P20 | passed | code_investigation.plan | workflow-router-20260606T005431772005Z | No marker-level difference from the baseline target. |  |
| P21 | passed | code_investigation.plan | workflow-router-20260606T005442153691Z | No marker-level difference from the baseline target. |  |
| P22 | passed | task.decompose | workflow-router-20260606T005457678654Z | No marker-level difference from the baseline target. |  |
| P23 | passed | execution_planning.plan | workflow-router-20260606T005501625245Z | No marker-level difference from the baseline target. |  |
| P24 | passed | execution_planning.plan | workflow-router-20260606T005504463494Z | No marker-level difference from the baseline target. |  |
| P25 | passed | execution_planning.plan | workflow-router-20260606T005510416790Z | No marker-level difference from the baseline target. |  |
| P26 | passed | execution_planning.plan | workflow-router-20260606T005515208642Z | No marker-level difference from the baseline target. |  |

## Prompt Baselines

### P01

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, where does the placed_order_id stealth lookup start? Read only and give me the beginning point, evidence files, related tests, and confidence.

Baseline target: A read-only beginning-point answer with the first relevant source location, evidence files, related tests, recommended commands, and a confidence statement.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005031499736Z`

### P02

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, explain find_stealth_order_by_placed_order_id in core/stealth_order_manager.py. I need inputs, return value, side effects, and tests that cover it. Read only.

Baseline target: A function explanation with inputs, outputs, side effects, related tests, and source refs.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005040534201Z`

### P03

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, what tests should I look at for placed_order_id stealth lookup? Read only. Include exact test files and the smallest useful pytest command.

Baseline target: A related-test answer with exact test files and the smallest useful pytest command.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005049658378Z`

### P04

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, does the repo already have placed_order_id stealth lookup behavior? Read only. Answer yes/no/unknown with evidence.

Baseline target: A conservative yes/no/unknown behavior-existence answer with evidence and no invented absence claim.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005102271013Z`

### P05

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find every caller or usage of find_stealth_order_by_placed_order_id and group them by file. Read only.

Baseline target: A usage summary grouped by file, with short explanations and source refs.

Expected workflow: `code_context.lookup`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005110727490Z`

### P06

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, where is COINBASE_API_KEY used and what does it affect at runtime? Read only. Do not expose any secret values.

Baseline target: A configuration answer showing references and runtime effect without exposing secret values.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005126141531Z`

### P07

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, summarize this pytest failure and tell me the next bounded inspection step. Do not edit files. FAILED tests/unit/test_order_id_and_followup_rules.py::test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - AssertionError: expected client_order_id index

Baseline target: A pasted-failure summary with failed test, primary error, likely cause, and next bounded inspection step.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005140449864Z`

### P08

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find the dashboard handler for request_stealth_orders. Read only. Return the handler file, related source refs, and related tests.

Baseline target: An endpoint/handler lookup with handler file, source refs, and related tests.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005152471040Z`

### P09

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find the source of the error message "Missing 'type' field in message". Read only. Return file, line, and why it is raised.

Baseline target: An error-message source lookup with source file, line/ref, and role.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005206694276Z`

### P10

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, summarize core/stealth_order_manager.py for a new maintainer. Read only. Include responsibilities, important definitions, related tests, and risks.

Baseline target: A module summary with responsibilities, definitions, related tests, and risks.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005217423981Z`

### P11

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find the stealth_orders database schema fields. Read only. Return model files, field names, and source refs.

Baseline target: A data model/schema lookup with model files, fields, and source refs.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005228637508Z`

### P12

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, list the imports and local dependencies of core/stealth_order_manager.py. Read only. Group external and internal dependencies.

Baseline target: A dependency lookup grouped into imports and internal/local dependencies.

Expected workflow: `code_context.lookup`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005244135385Z`

### P13

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp, find recent or local changes. Read only. If this is not a git repo, say that directly and list what can still be inspected.

Baseline target: A local-change summary that honestly reports non-git limitations and does not invent commit history.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005300416290Z`

### P14

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, identify test coverage gaps for placed_order_id stealth lookup. Read only. Include covered tests, missing scenarios, and verification commands.

Baseline target: A coverage-gap summary with covered tests, missing scenarios, and verification commands.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005317634426Z`

### P15

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find documentation for request_stealth_orders dashboard behavior. Read only. Return docs, source refs, and gaps.

Baseline target: A documentation lookup with docs, source refs, and explicit gaps.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005328558923Z`

### P16

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, locate the CLI or script entrypoint for running the trading engine. Read only. Return the command and source refs.

Baseline target: A CLI entrypoint answer with file, command, and source refs.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005339530589Z`

### P17

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, choose the smallest, medium, and broad validation commands for placed_order_id stealth lookup. Read only. Explain why each command matters and what risk remains.

Baseline target: A test-selection plan with smallest, medium, and broad commands, rationale, risks, confidence, and gaps.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005353585151Z`

### P18

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, diagnose this runtime stack trace for request_stealth_orders. Read only. Traceback (most recent call last): File "dashboard_server.py", line 10, in handle_websocket_message core.exceptions.WebSocketMessageError: Missing 'type' field in message

Baseline target: A runtime-error diagnosis with observed error, likely cause, evidence files, next inspection, risks, gaps, and verification.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005404667286Z`

### P19

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, map the request/data flow for request_stealth_orders from dashboard message to stealth order snapshot. Read only. Include flow steps, participating files, risks, and gaps.

Baseline target: A request/data-flow map with ordered flow steps, participating files, risks, gaps, and verification.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005421041679Z`

### P20

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, compare the placed_order_id stealth lookup path with the client_order_id index path. Read only. Return candidate paths, evidence, risks, recommended path if supported, and gaps.

Baseline target: A code-path comparison with candidate paths, evidence, risks, recommendation if supported, and gaps.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005431772005Z`

### P21

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, identify the minimal safe change surface for changing placed_order_id stealth lookup behavior. Read only and stop before implementation.

Baseline target: A change-surface summary with files to review, related tests, risk level, gaps, and no implementation.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005442153691Z`

### P22

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, break down the work to add a safer placed_order_id lookup change. Do not implement. I want dependencies, approval gates, verification strategy, and risks.

Baseline target: A task decomposition with work packages, dependencies, approval gates, verification strategy, risks, and uncertainty.

Expected workflow: `task.decompose`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005457678654Z`

### P23

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, draft a small documentation edit to docs/agents/INVARIANTS.md that adds a note saying the stealth manager placed-order index is the authoritative lookup key. Do not mutate files. Show exact proposed change and verification command.

Baseline target: A draft-only implementation proposal with exact file, operation, safety checks, verification command, and no source mutation.

Expected workflow: `execution_planning.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005501625245Z`

### P24

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, draft a small unit test for sync_exchange_order_id_for_placed_order setting exchange_order_id when it is missing. Do not mutate files. Show the proposed test file and pytest command.

Baseline target: A draft-only unit-test proposal with target test file, proposed test body/operation, verification command, and no source mutation.

Expected workflow: `execution_planning.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005504463494Z`

### P25

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, inspect this failing test and propose the smallest fix. Draft only; do not apply until approved. FAILED tests/unit/test_order_id_and_followup_rules.py::test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - AssertionError: expected find_stealth_order_by_placed_order_id docstring to mention client_order_id

Baseline target: A draft-only simple-fix proposal with exact proposed operation, verification command, and approval gate.

Expected workflow: `execution_planning.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005510416790Z`

### P26

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, apply this exact packet only to a disposable copy and prove the source repo did not change: {"packet_operations":[{"kind":"replace_text","path":"docs/agents/INVARIANTS.md","old":"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, and DB\n  local rows.","new":"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, DB\n  local rows, and stealth manager placed-order index keys."}]}

Baseline target: A disposable-copy apply proof that mutates only the copy, rolls it back, and reports source_changed false.

Expected workflow: `execution_planning.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T005515208642Z`

