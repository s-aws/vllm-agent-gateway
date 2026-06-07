# Founder Field Prompt Evaluation

- Status: passed
- Created at: 20260606T230756172062Z
- AnythingLLM workspace: my-workspace
- Prompt count: 34
- Passed: 34
- Failed: 0

## Results

| Case | Status | Output contract | Semantic quality | Expected workflow | Run ID | Initial difference | Miss suggestion | Refined prompt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P01 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T230757328536Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find the first source point that creates or populates the placed_order_id stealth lookup key. Read only. Include evidence files, related tests, and confidence. |
| P02 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T230804422225Z | No marker-level or semantic difference from the baseline target. |  |  |
| P03 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T230811372104Z | No marker-level or semantic difference from the baseline target. |  |  |
| P04 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T230818101391Z | No marker-level or semantic difference from the baseline target. |  |  |
| P05 | passed | passed | passed | code_context.lookup | workflow-router-20260606T230827838562Z | No marker-level or semantic difference from the baseline target. |  |  |
| P06 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T230838858799Z | No marker-level or semantic difference from the baseline target. |  |  |
| P07 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T230845838990Z | No marker-level or semantic difference from the baseline target. |  |  |
| P08 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T230853462921Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp.github, follow the request_stealth_orders handler branch through the snapshot function. Read only. Return handler file, source refs, and related tests. |
| P09 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T230903460498Z | No marker-level or semantic difference from the baseline target. |  |  |
| P10 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T230910738003Z | No marker-level or semantic difference from the baseline target. |  |  |
| P11 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T230918338481Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find only the stealth_orders table schema. Read only. Return model files, schema field names, and source refs. |
| P12 | passed | passed | passed | code_context.lookup | workflow-router-20260606T230925585247Z | No marker-level or semantic difference from the baseline target. |  |  |
| P13 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T230939211080Z | No marker-level or semantic difference from the baseline target. |  |  |
| P14 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T230950866195Z | No marker-level or semantic difference from the baseline target. |  |  |
| P15 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T230958525564Z | No marker-level or semantic difference from the baseline target. |  |  |
| P16 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T231008369784Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp.github, locate the trading-engine CLI or script entrypoint, not the dashboard-only server. Read only. Return the command and source refs. |
| P17 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T231015344077Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp.github, choose the smallest, medium, and broad Bash validation commands for placed_order_id stealth lookup. Read only. Explain why each command matters and what risk remains. |
| P18 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T231022298823Z | No marker-level or semantic difference from the baseline target. |  |  |
| P19 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T231030525812Z | No marker-level or semantic difference from the baseline target. |  |  |
| P20 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T231040185825Z | No marker-level or semantic difference from the baseline target. |  |  |
| P21 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T231047482867Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp.github, identify files to touch and files not to touch for a minimal safe placed_order_id stealth lookup change. Read only and stop before implementation. |
| P22 | passed | passed | passed | task.decompose | workflow-router-20260606T231054910590Z | No marker-level or semantic difference from the baseline target. |  |  |
| P23 | passed | passed | passed | execution_planning.plan | workflow-router-20260606T231055730272Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp.github, draft a unified diff only for docs/agents/INVARIANTS.md that adds a note saying the stealth manager placed-order index is the authoritative lookup key. Do not mutate files. Include the verification command. |
| P24 | passed | passed | passed | execution_planning.plan | workflow-router-20260606T231058194137Z | No marker-level or semantic difference from the baseline target. |  |  |
| P25 | passed | passed | passed | execution_planning.plan | workflow-router-20260606T231100896703Z | No marker-level or semantic difference from the baseline target. |  |  |
| P26 | passed | passed | passed | execution_planning.plan | workflow-router-20260606T231103109930Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp.github, approved disposable copy apply only. Apply this exact packet only to a disposable copy and prove source_changed is false: {"packet_operations":[{"kind":"replace_text","path":"docs/agents/INVARIANTS.md","old":"- Use `client_order_id` for internal tra |
| P27 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T231127525506Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp.github, follow handler branch trace for request_stealth_orders through the downstream snapshot function as a request flow map. Read only. Return flow steps, participating files, evidence refs, related tests, risks, gaps, and verification. |
| P28 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T231134959990Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp, follow handler branch trace for request_stealth_orders through the downstream snapshot function as a request flow map. Read only. Return flow steps, participating files, evidence refs, related tests, risks, gaps, and verification. |
| P29 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T231148821674Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find only the persisted stealth_orders table schema. Read only. Return schema field names, model files, and source refs. Exclude runtime dictionary fields. |
| P30 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T231156051539Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp, find only the persisted stealth_orders table schema. Read only. Return schema field names, model files, and source refs. Exclude runtime dictionary fields. |
| P31 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T231204992680Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp.github, locate the trading-engine runtime entrypoint and exclude the dashboard server path. Read only. Return command, source refs, and excluded adjacent entrypoints. |
| P32 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T231214829338Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp, locate the trading-engine runtime entrypoint and exclude the dashboard server path. Read only. Return command, source refs, and excluded adjacent entrypoints. |
| P33 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T231226765825Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp.github, summarize the change boundary for placed_order_id stealth lookup by listing files to touch and files not to touch. Read only and stop before implementation. Return risks, gaps, and verification commands. |
| P34 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T231234110058Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp, summarize the change boundary for placed_order_id stealth lookup by listing files to touch and files not to touch. Read only and stop before implementation. Return risks, gaps, and verification commands. |

## Prompt Baselines

### P01

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, where does the placed_order_id stealth lookup start? Read only and give me the beginning point, evidence files, related tests, and confidence.

Baseline target: A read-only beginning-point answer with the first relevant source location, evidence files, related tests, recommended commands, and a confidence statement.

Expected workflow: `code_investigation.plan`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find the first source point that creates or populates the placed_order_id stealth lookup key. Read only. Include evidence files, related tests, and confidence.

Prompt risk: Ambiguous 'start' wording can be interpreted as related-test discovery or a later usage point.

Run ID: `workflow-router-20260606T230757328536Z`

### P02

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, explain find_stealth_order_by_placed_order_id in core/stealth_order_manager.py. I need inputs, return value, side effects, and tests that cover it. Read only.

Baseline target: A function explanation with inputs, outputs, side effects, related tests, and source refs.

Expected workflow: `code_investigation.plan`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: None

Prompt risk: None

Run ID: `workflow-router-20260606T230804422225Z`

### P03

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, what tests should I look at for placed_order_id stealth lookup? Read only. Include exact test files and the smallest useful pytest command.

Baseline target: A related-test answer with exact test files and the smallest useful pytest command.

Expected workflow: `code_investigation.plan`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: None

Prompt risk: None

Run ID: `workflow-router-20260606T230811372104Z`

### P04

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, does the repo already have placed_order_id stealth lookup behavior? Read only. Answer yes/no/unknown with evidence.

Baseline target: A conservative yes/no/unknown behavior-existence answer with evidence and no invented absence claim.

Expected workflow: `code_investigation.plan`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: None

Prompt risk: None

Run ID: `workflow-router-20260606T230818101391Z`

### P05

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find every caller or usage of find_stealth_order_by_placed_order_id and group them by file. Read only.

Baseline target: A usage summary grouped by file, with short explanations and source refs.

Expected workflow: `code_context.lookup`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: None

Prompt risk: None

Run ID: `workflow-router-20260606T230827838562Z`

### P06

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, where is COINBASE_API_KEY used and what does it affect at runtime? Read only. Do not expose any secret values.

Baseline target: A configuration answer showing references and runtime effect without exposing secret values.

Expected workflow: `code_investigation.plan`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: None

Prompt risk: None

Run ID: `workflow-router-20260606T230838858799Z`

### P07

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, summarize this pytest failure and tell me the next bounded inspection step. Do not edit files. FAILED tests/unit/test_order_id_and_followup_rules.py::test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - AssertionError: expected client_order_id index

Baseline target: A pasted-failure summary with failed test, primary error, likely cause, and next bounded inspection step.

Expected workflow: `code_investigation.plan`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: None

Prompt risk: None

Run ID: `workflow-router-20260606T230845838990Z`

### P08

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find the dashboard handler for request_stealth_orders. Read only. Return the handler file, related source refs, and related tests.

Baseline target: An endpoint/handler lookup with handler file, source refs, and related tests.

Expected workflow: `code_investigation.plan`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, follow the request_stealth_orders handler branch through the snapshot function. Read only. Return handler file, source refs, and related tests.

Prompt risk: Handler prompts can stop at a UI sender unless the handler branch is named.

Run ID: `workflow-router-20260606T230853462921Z`

### P09

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find the source of the error message "Missing 'type' field in message". Read only. Return file, line, and why it is raised.

Baseline target: An error-message source lookup with source file, line/ref, and role.

Expected workflow: `code_investigation.plan`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: None

Prompt risk: None

Run ID: `workflow-router-20260606T230903460498Z`

### P10

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, summarize core/stealth_order_manager.py for a new maintainer. Read only. Include responsibilities, important definitions, related tests, and risks.

Baseline target: A module summary with responsibilities, definitions, related tests, and risks.

Expected workflow: `code_investigation.plan`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: None

Prompt risk: None

Run ID: `workflow-router-20260606T230910738003Z`

### P11

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find the stealth_orders database schema fields. Read only. Return model files, field names, and source refs.

Baseline target: A data model/schema lookup with model files, fields, and source refs.

Expected workflow: `code_investigation.plan`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find only the stealth_orders table schema. Read only. Return model files, schema field names, and source refs.

Prompt risk: Schema prompts can return runtime dictionary fields instead of table schema.

Run ID: `workflow-router-20260606T230918338481Z`

### P12

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, list the imports and local dependencies of core/stealth_order_manager.py. Read only. Group external and internal dependencies.

Baseline target: A dependency lookup grouped into imports and internal/local dependencies.

Expected workflow: `code_context.lookup`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: None

Prompt risk: None

Run ID: `workflow-router-20260606T230925585247Z`

### P13

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp, find recent or local changes. Read only. If this is not a git repo, say that directly and list what can still be inspected.

Baseline target: A local-change summary that honestly reports non-git limitations and does not invent commit history.

Expected workflow: `code_investigation.plan`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: None

Prompt risk: None

Run ID: `workflow-router-20260606T230939211080Z`

### P14

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, identify test coverage gaps for placed_order_id stealth lookup. Read only. Include covered tests, missing scenarios, and verification commands.

Baseline target: A coverage-gap summary with covered tests, missing scenarios, and verification commands.

Expected workflow: `code_investigation.plan`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: None

Prompt risk: None

Run ID: `workflow-router-20260606T230950866195Z`

### P15

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find documentation for request_stealth_orders dashboard behavior. Read only. Return docs, source refs, and gaps.

Baseline target: A documentation lookup with docs, source refs, and explicit gaps.

Expected workflow: `code_investigation.plan`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: None

Prompt risk: None

Run ID: `workflow-router-20260606T230958525564Z`

### P16

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, locate the CLI or script entrypoint for running the trading engine. Read only. Return the command and source refs.

Baseline target: A CLI entrypoint answer with file, command, and source refs.

Expected workflow: `code_investigation.plan`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, locate the trading-engine CLI or script entrypoint, not the dashboard-only server. Read only. Return the command and source refs.

Prompt risk: Entrypoint prompts can confuse the trading engine with a dashboard service.

Run ID: `workflow-router-20260606T231008369784Z`

### P17

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, choose the smallest, medium, and broad validation commands for placed_order_id stealth lookup. Read only. Explain why each command matters and what risk remains.

Baseline target: A test-selection plan with smallest, medium, and broad commands, rationale, risks, confidence, and gaps.

Expected workflow: `code_investigation.plan`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, choose the smallest, medium, and broad Bash validation commands for placed_order_id stealth lookup. Read only. Explain why each command matters and what risk remains.

Prompt risk: Validation prompts can omit shell surface, which matters because live validation should prefer Bash.

Run ID: `workflow-router-20260606T231015344077Z`

### P18

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, diagnose this runtime stack trace for request_stealth_orders. Read only. Traceback (most recent call last): File "dashboard_server.py", line 10, in handle_websocket_message core.exceptions.WebSocketMessageError: Missing 'type' field in message

Baseline target: A runtime-error diagnosis with observed error, likely cause, evidence files, next inspection, risks, gaps, and verification.

Expected workflow: `code_investigation.plan`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: None

Prompt risk: None

Run ID: `workflow-router-20260606T231022298823Z`

### P19

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, map the request/data flow for request_stealth_orders from dashboard message to stealth order snapshot. Read only. Include flow steps, participating files, risks, and gaps.

Baseline target: A request/data-flow map with ordered flow steps, participating files, risks, gaps, and verification.

Expected workflow: `code_investigation.plan`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: None

Prompt risk: None

Run ID: `workflow-router-20260606T231030525812Z`

### P20

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, compare the placed_order_id stealth lookup path with the client_order_id index path. Read only. Return candidate paths, evidence, risks, recommended path if supported, and gaps.

Baseline target: A code-path comparison with candidate paths, evidence, risks, recommendation if supported, and gaps.

Expected workflow: `code_investigation.plan`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: None

Prompt risk: None

Run ID: `workflow-router-20260606T231040185825Z`

### P21

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, identify the minimal safe change surface for changing placed_order_id stealth lookup behavior. Read only and stop before implementation.

Baseline target: A change-surface summary with files to review, related tests, risk level, gaps, and no implementation.

Expected workflow: `code_investigation.plan`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, identify files to touch and files not to touch for a minimal safe placed_order_id stealth lookup change. Read only and stop before implementation.

Prompt risk: Change-surface prompts should name both touch and do-not-touch boundaries.

Run ID: `workflow-router-20260606T231047482867Z`

### P22

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, break down the work to add a safer placed_order_id lookup change. Do not implement. I want dependencies, approval gates, verification strategy, and risks.

Baseline target: A task decomposition with work packages, dependencies, approval gates, verification strategy, risks, and uncertainty.

Expected workflow: `task.decompose`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: None

Prompt risk: None

Run ID: `workflow-router-20260606T231054910590Z`

### P23

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, draft a small documentation edit to docs/agents/INVARIANTS.md that adds a note saying the stealth manager placed-order index is the authoritative lookup key. Do not mutate files. Show exact proposed change and verification command.

Baseline target: A draft-only implementation proposal with exact file, operation, safety checks, verification command, and no source mutation.

Expected workflow: `execution_planning.plan`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, draft a unified diff only for docs/agents/INVARIANTS.md that adds a note saying the stealth manager placed-order index is the authoritative lookup key. Do not mutate files. Include the verification command.

Prompt risk: Draft documentation prompts are easier to review when the requested output shape is explicit.

Run ID: `workflow-router-20260606T231055730272Z`

### P24

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, draft a small unit test for sync_exchange_order_id_for_placed_order setting exchange_order_id when it is missing. Do not mutate files. Show the proposed test file and pytest command.

Baseline target: A draft-only unit-test proposal with target test file, proposed test body/operation, verification command, and no source mutation.

Expected workflow: `execution_planning.plan`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: None

Prompt risk: None

Run ID: `workflow-router-20260606T231058194137Z`

### P25

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, inspect this failing test and propose the smallest fix. Draft only; do not apply until approved. FAILED tests/unit/test_order_id_and_followup_rules.py::test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - AssertionError: expected find_stealth_order_by_placed_order_id docstring to mention client_order_id

Baseline target: A draft-only simple-fix proposal with exact proposed operation, verification command, and approval gate.

Expected workflow: `execution_planning.plan`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: None

Prompt risk: None

Run ID: `workflow-router-20260606T231100896703Z`

### P26

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, apply this exact packet only to a disposable copy and prove the source repo did not change: {"packet_operations":[{"kind":"replace_text","path":"docs/agents/INVARIANTS.md","old":"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, and DB\n  local rows.","new":"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, DB\n  local rows, and stealth manager placed-order index keys."}]}

Baseline target: A disposable-copy apply proof that mutates only the copy, rolls it back, and reports source_changed false.

Expected workflow: `execution_planning.plan`

Expected skill: `not asserted`

Expected artifact: `not asserted`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, approved disposable copy apply only. Apply this exact packet only to a disposable copy and prove source_changed is false: {"packet_operations":[{"kind":"replace_text","path":"docs/agents/INVARIANTS.md","old":"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, and DB\n  local rows.","new":"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, DB\n  local rows, and stealth manager placed-order index keys."}]}

Prompt risk: Disposable-copy apply prompts need older-client-safe copy-only approval wording.

Run ID: `workflow-router-20260606T231103109930Z`

### P27

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, follow handler branch trace for request_stealth_orders as a request flow through the downstream snapshot function. Read only. Return flow steps, participating files, evidence refs, related tests, risks, gaps, and verification.

Baseline target: A handler-branch trace that selects the Batch D handler skill and returns a request-flow map.

Expected workflow: `code_investigation.plan`

Expected skill: `handler-branch-tracer`

Expected artifact: `downstream_request_flow_map`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, follow handler branch trace for request_stealth_orders through the downstream snapshot function as a request flow map. Read only. Return flow steps, participating files, evidence refs, related tests, risks, gaps, and verification.

Prompt risk: Handler prompts can select a generic endpoint lookup unless handler-branch and downstream snapshot language is explicit.

Run ID: `workflow-router-20260606T231127525506Z`

### P28

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp, follow handler branch trace for request_stealth_orders as a request flow through the downstream snapshot function. Read only. Return flow steps, participating files, evidence refs, related tests, risks, gaps, and verification.

Baseline target: A non-git fixture handler-branch trace that selects the Batch D handler skill and returns a request-flow map.

Expected workflow: `code_investigation.plan`

Expected skill: `handler-branch-tracer`

Expected artifact: `downstream_request_flow_map`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp, follow handler branch trace for request_stealth_orders through the downstream snapshot function as a request flow map. Read only. Return flow steps, participating files, evidence refs, related tests, risks, gaps, and verification.

Prompt risk: Non-git handler prompts still need explicit handler-branch and downstream snapshot language.

Run ID: `workflow-router-20260606T231134959990Z`

### P29

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find the stealth_orders table schema only. Read only. Return schema field names, model files, and source refs. Exclude runtime fields.

Baseline target: A table-schema-only answer that selects the Batch D schema isolator and avoids runtime dictionary fields.

Expected workflow: `code_investigation.plan`

Expected skill: `table-schema-isolator`

Expected artifact: `downstream_data_model_lookup`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find only the persisted stealth_orders table schema. Read only. Return schema field names, model files, and source refs. Exclude runtime dictionary fields.

Prompt risk: Schema prompts can mix persisted table fields with runtime dictionary fields unless the persisted table boundary is named.

Run ID: `workflow-router-20260606T231148821674Z`

### P30

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp, find the stealth_orders table schema only. Read only. Return schema field names, model files, and source refs. Exclude runtime fields.

Baseline target: A non-git fixture table-schema-only answer that selects the Batch D schema isolator and avoids runtime dictionary fields.

Expected workflow: `code_investigation.plan`

Expected skill: `table-schema-isolator`

Expected artifact: `downstream_data_model_lookup`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp, find only the persisted stealth_orders table schema. Read only. Return schema field names, model files, and source refs. Exclude runtime dictionary fields.

Prompt risk: Non-git schema prompts can mix persisted table fields with runtime dictionary fields unless the persisted table boundary is named.

Run ID: `workflow-router-20260606T231156051539Z`

### P31

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, locate the runtime entrypoint for the trading engine entrypoint, not dashboard server. Read only. Return command, source refs, and exclusions.

Baseline target: A runtime-entrypoint answer that selects the Batch D entrypoint disambiguator and excludes adjacent UI services.

Expected workflow: `code_investigation.plan`

Expected skill: `runtime-entrypoint-disambiguator`

Expected artifact: `downstream_cli_entrypoint_lookup`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, locate the trading-engine runtime entrypoint and exclude the dashboard server path. Read only. Return command, source refs, and excluded adjacent entrypoints.

Prompt risk: Entrypoint prompts can select dashboard_server.py unless the runtime subsystem and exclusion are explicit.

Run ID: `workflow-router-20260606T231204992680Z`

### P32

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp, locate the runtime entrypoint for the trading engine entrypoint, not dashboard server. Read only. Return command, source refs, and exclusions.

Baseline target: A non-git fixture runtime-entrypoint answer that selects the Batch D entrypoint disambiguator and excludes adjacent UI services.

Expected workflow: `code_investigation.plan`

Expected skill: `runtime-entrypoint-disambiguator`

Expected artifact: `downstream_cli_entrypoint_lookup`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp, locate the trading-engine runtime entrypoint and exclude the dashboard server path. Read only. Return command, source refs, and excluded adjacent entrypoints.

Prompt risk: Non-git entrypoint prompts can select dashboard_server.py unless the runtime subsystem and exclusion are explicit.

Run ID: `workflow-router-20260606T231214829338Z`

### P33

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, identify files to touch and files not to touch for the minimal safe change surface and change boundary for placed_order_id stealth lookup behavior. Read only and stop before implementation. Return risks, gaps, and verification commands.

Baseline target: A change-boundary answer that selects the Batch D boundary summarizer and stops before implementation.

Expected workflow: `code_investigation.plan`

Expected skill: `change-boundary-summarizer`

Expected artifact: `downstream_change_surface_summary`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, summarize the change boundary for placed_order_id stealth lookup by listing files to touch and files not to touch. Read only and stop before implementation. Return risks, gaps, and verification commands.

Prompt risk: Change-surface prompts can drift into implementation planning unless the boundary and stop condition are explicit.

Run ID: `workflow-router-20260606T231226765825Z`

### P34

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp, identify files to touch and files not to touch for the minimal safe change surface and change boundary for placed_order_id stealth lookup behavior. Read only and stop before implementation. Return risks, gaps, and verification commands.

Baseline target: A non-git fixture change-boundary answer that selects the Batch D boundary summarizer and stops before implementation.

Expected workflow: `code_investigation.plan`

Expected skill: `change-boundary-summarizer`

Expected artifact: `downstream_change_surface_summary`

Output contract: passed

Semantic quality: passed

Missing semantic markers: []

Forbidden markers found: []

Initial difference: No marker-level or semantic difference from the baseline target.

Suggested prompt if missed: None

Refined prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp, summarize the change boundary for placed_order_id stealth lookup by listing files to touch and files not to touch. Read only and stop before implementation. Return risks, gaps, and verification commands.

Prompt risk: Non-git change-surface prompts can drift into implementation planning unless the boundary and stop condition are explicit.

Run ID: `workflow-router-20260606T231234110058Z`

