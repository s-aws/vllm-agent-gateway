# Founder Field Prompt Matrix

- Status: passed
- Created at: 20260606T092613525993Z
- Prompt count: 50
- Passed: 50
- Failed: 0

## Results

| Case | Variant | Status | Expected workflow | Actual workflow | Expected rule | Actual rule | Conflict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P01 | original | passed | code_investigation.plan | code_investigation.plan | l1_find_behavior_start_terms | l1_find_behavior_start_terms |  |
| P02 | original | passed | code_investigation.plan | code_investigation.plan | l1_explain_code_terms | l1_explain_code_terms |  |
| P03 | original | passed | code_investigation.plan | code_investigation.plan | l1_find_related_tests_terms | l1_find_related_tests_terms |  |
| P04 | original | passed | code_investigation.plan | code_investigation.plan | l1_behavior_exists_terms | l1_behavior_exists_terms |  |
| P05 | original | passed | code_context.lookup | code_context.lookup | l1_callers_usages_terms | l1_callers_usages_terms |  |
| P06 | original | passed | code_investigation.plan | code_investigation.plan | l1_configuration_effect_summary_terms | l1_configuration_effect_summary_terms |  |
| P07 | original | passed | code_investigation.plan | code_investigation.plan | l1_test_failure_summary_terms | l1_test_failure_summary_terms |  |
| P08 | original | passed | code_investigation.plan | code_investigation.plan | l1_endpoint_route_lookup_terms | l1_endpoint_route_lookup_terms |  |
| P09 | original | passed | code_investigation.plan | code_investigation.plan | l1_message_source_lookup_terms | l1_message_source_lookup_terms |  |
| P10 | original | passed | code_investigation.plan | code_investigation.plan | l1_module_summary_terms | l1_module_summary_terms |  |
| P11 | original | passed | code_investigation.plan | code_investigation.plan | l1_data_model_lookup_terms | l1_data_model_lookup_terms |  |
| P12 | original | passed | code_context.lookup | code_context.lookup | l1_dependency_import_lookup_terms | l1_dependency_import_lookup_terms |  |
| P13 | original | passed | code_investigation.plan | code_investigation.plan | l1_local_change_summary_terms | l1_local_change_summary_terms |  |
| P14 | original | passed | code_investigation.plan | code_investigation.plan | l1_coverage_gap_summary_terms | l1_coverage_gap_summary_terms |  |
| P15 | original | passed | code_investigation.plan | code_investigation.plan | l1_documentation_lookup_terms | l1_documentation_lookup_terms |  |
| P16 | original | passed | code_investigation.plan | code_investigation.plan | l1_cli_entrypoint_lookup_terms | l1_cli_entrypoint_lookup_terms |  |
| P17 | original | passed | code_investigation.plan | code_investigation.plan | l2_test_selection_terms | l2_test_selection_terms |  |
| P18 | original | passed | code_investigation.plan | code_investigation.plan | l2_runtime_error_diagnosis_terms | l2_runtime_error_diagnosis_terms |  |
| P19 | original | passed | code_investigation.plan | code_investigation.plan | l2_request_flow_map_terms | l2_request_flow_map_terms |  |
| P20 | original | passed | code_investigation.plan | code_investigation.plan | l2_code_path_comparison_terms | l2_code_path_comparison_terms |  |
| P21 | original | passed | code_investigation.plan | code_investigation.plan | l2_change_surface_summary_terms | l2_change_surface_summary_terms |  |
| P22 | original | passed | task.decompose | task.decompose | task_decomposition_terms | task_decomposition_terms |  |
| P23 | original | passed | execution_planning.plan | execution_planning.plan | l1_small_text_edit_terms | l1_small_text_edit_terms |  |
| P24 | original | passed | execution_planning.plan | execution_planning.plan | l1_small_unit_test_terms | l1_small_unit_test_terms |  |
| P25 | original | passed | execution_planning.plan | execution_planning.plan | l1_simple_failing_test_fix_terms | l1_simple_failing_test_fix_terms |  |
| P26 | original | passed | execution_planning.plan | execution_planning.plan | disposable_apply_terms | disposable_apply_terms |  |
| P27 | original | passed | code_investigation.plan | code_investigation.plan | l2_request_flow_map_terms | l2_request_flow_map_terms |  |
| P28 | original | passed | code_investigation.plan | code_investigation.plan | l2_request_flow_map_terms | l2_request_flow_map_terms |  |
| P29 | original | passed | code_investigation.plan | code_investigation.plan | l1_data_model_lookup_terms | l1_data_model_lookup_terms |  |
| P30 | original | passed | code_investigation.plan | code_investigation.plan | l1_data_model_lookup_terms | l1_data_model_lookup_terms |  |
| P31 | original | passed | code_investigation.plan | code_investigation.plan | l1_cli_entrypoint_lookup_terms | l1_cli_entrypoint_lookup_terms |  |
| P32 | original | passed | code_investigation.plan | code_investigation.plan | l1_cli_entrypoint_lookup_terms | l1_cli_entrypoint_lookup_terms |  |
| P33 | original | passed | code_investigation.plan | code_investigation.plan | l2_change_surface_summary_terms | l2_change_surface_summary_terms |  |
| P34 | original | passed | code_investigation.plan | code_investigation.plan | l2_change_surface_summary_terms | l2_change_surface_summary_terms |  |
| P01-V1 | refined | passed | code_investigation.plan | code_investigation.plan | l1_find_behavior_start_terms | l1_find_behavior_start_terms |  |
| P08-V1 | refined | passed | code_investigation.plan | code_investigation.plan | l1_endpoint_route_lookup_terms | l1_endpoint_route_lookup_terms |  |
| P11-V1 | refined | passed | code_investigation.plan | code_investigation.plan | l1_data_model_lookup_terms | l1_data_model_lookup_terms |  |
| P16-V1 | refined | passed | code_investigation.plan | code_investigation.plan | l1_cli_entrypoint_lookup_terms | l1_cli_entrypoint_lookup_terms |  |
| P17-V1 | refined | passed | code_investigation.plan | code_investigation.plan | l2_test_selection_terms | l2_test_selection_terms |  |
| P21-V1 | refined | passed | code_investigation.plan | code_investigation.plan | l2_change_surface_summary_terms | l2_change_surface_summary_terms |  |
| P23-V1 | refined | passed | execution_planning.plan | execution_planning.plan | l1_small_text_edit_terms | l1_small_text_edit_terms |  |
| P26-V1 | refined | passed | execution_planning.plan | execution_planning.plan | disposable_apply_terms | disposable_apply_terms |  |
| P27-V1 | refined | passed | code_investigation.plan | code_investigation.plan | l2_request_flow_map_terms | l2_request_flow_map_terms |  |
| P28-V1 | refined | passed | code_investigation.plan | code_investigation.plan | l2_request_flow_map_terms | l2_request_flow_map_terms |  |
| P29-V1 | refined | passed | code_investigation.plan | code_investigation.plan | l1_data_model_lookup_terms | l1_data_model_lookup_terms |  |
| P30-V1 | refined | passed | code_investigation.plan | code_investigation.plan | l1_data_model_lookup_terms | l1_data_model_lookup_terms |  |
| P31-V1 | refined | passed | code_investigation.plan | code_investigation.plan | l1_cli_entrypoint_lookup_terms | l1_cli_entrypoint_lookup_terms |  |
| P32-V1 | refined | passed | code_investigation.plan | code_investigation.plan | l1_cli_entrypoint_lookup_terms | l1_cli_entrypoint_lookup_terms |  |
| P33-V1 | refined | passed | code_investigation.plan | code_investigation.plan | l2_change_surface_summary_terms | l2_change_surface_summary_terms |  |
| P34-V1 | refined | passed | code_investigation.plan | code_investigation.plan | l2_change_surface_summary_terms | l2_change_surface_summary_terms |  |

## Prompt Notes

### P01

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, where does the placed_order_id stealth lookup start? Read only and give me the beginning point, evidence files, related tests, and confidence.

Note: A read-only beginning-point answer with the first relevant source location, evidence files, related tests, recommended commands, and a confidence statement.

Rules: `l1_find_behavior_start_terms`

### P02

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, explain find_stealth_order_by_placed_order_id in core/stealth_order_manager.py. I need inputs, return value, side effects, and tests that cover it. Read only.

Note: A function explanation with inputs, outputs, side effects, related tests, and source refs.

Rules: `l1_explain_code_terms`

### P03

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, what tests should I look at for placed_order_id stealth lookup? Read only. Include exact test files and the smallest useful pytest command.

Note: A related-test answer with exact test files and the smallest useful pytest command.

Rules: `l1_find_related_tests_terms`

### P04

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, does the repo already have placed_order_id stealth lookup behavior? Read only. Answer yes/no/unknown with evidence.

Note: A conservative yes/no/unknown behavior-existence answer with evidence and no invented absence claim.

Rules: `l1_behavior_exists_terms`

### P05

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find every caller or usage of find_stealth_order_by_placed_order_id and group them by file. Read only.

Note: A usage summary grouped by file, with short explanations and source refs.

Rules: `l1_callers_usages_terms`

### P06

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, where is COINBASE_API_KEY used and what does it affect at runtime? Read only. Do not expose any secret values.

Note: A configuration answer showing references and runtime effect without exposing secret values.

Rules: `l1_configuration_effect_summary_terms`

### P07

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, summarize this pytest failure and tell me the next bounded inspection step. Do not edit files. FAILED tests/unit/test_order_id_and_followup_rules.py::test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - AssertionError: expected client_order_id index

Note: A pasted-failure summary with failed test, primary error, likely cause, and next bounded inspection step.

Rules: `l1_test_failure_summary_terms`

### P08

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find the dashboard handler for request_stealth_orders. Read only. Return the handler file, related source refs, and related tests.

Note: An endpoint/handler lookup with handler file, source refs, and related tests.

Rules: `l1_endpoint_route_lookup_terms`

### P09

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find the source of the error message "Missing 'type' field in message". Read only. Return file, line, and why it is raised.

Note: An error-message source lookup with source file, line/ref, and role.

Rules: `l1_message_source_lookup_terms`

### P10

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, summarize core/stealth_order_manager.py for a new maintainer. Read only. Include responsibilities, important definitions, related tests, and risks.

Note: A module summary with responsibilities, definitions, related tests, and risks.

Rules: `l1_module_summary_terms`

### P11

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find the stealth_orders database schema fields. Read only. Return model files, field names, and source refs.

Note: A data model/schema lookup with model files, fields, and source refs.

Rules: `l1_data_model_lookup_terms`

### P12

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, list the imports and local dependencies of core/stealth_order_manager.py. Read only. Group external and internal dependencies.

Note: A dependency lookup grouped into imports and internal/local dependencies.

Rules: `l1_dependency_import_lookup_terms`

### P13

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp, find recent or local changes. Read only. If this is not a git repo, say that directly and list what can still be inspected.

Note: A local-change summary that honestly reports non-git limitations and does not invent commit history.

Rules: `l1_local_change_summary_terms`

### P14

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, identify test coverage gaps for placed_order_id stealth lookup. Read only. Include covered tests, missing scenarios, and verification commands.

Note: A coverage-gap summary with covered tests, missing scenarios, and verification commands.

Rules: `l1_coverage_gap_summary_terms`

### P15

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find documentation for request_stealth_orders dashboard behavior. Read only. Return docs, source refs, and gaps.

Note: A documentation lookup with docs, source refs, and explicit gaps.

Rules: `l1_documentation_lookup_terms`

### P16

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, locate the CLI or script entrypoint for running the trading engine. Read only. Return the command and source refs.

Note: A CLI entrypoint answer with file, command, and source refs.

Rules: `l1_cli_entrypoint_lookup_terms`

### P17

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, choose the smallest, medium, and broad validation commands for placed_order_id stealth lookup. Read only. Explain why each command matters and what risk remains.

Note: A test-selection plan with smallest, medium, and broad commands, rationale, risks, confidence, and gaps.

Rules: `l2_test_selection_terms`

### P18

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, diagnose this runtime stack trace for request_stealth_orders. Read only. Traceback (most recent call last): File "dashboard_server.py", line 10, in handle_websocket_message core.exceptions.WebSocketMessageError: Missing 'type' field in message

Note: A runtime-error diagnosis with observed error, likely cause, evidence files, next inspection, risks, gaps, and verification.

Rules: `l2_runtime_error_diagnosis_terms`

### P19

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, map the request/data flow for request_stealth_orders from dashboard message to stealth order snapshot. Read only. Include flow steps, participating files, risks, and gaps.

Note: A request/data-flow map with ordered flow steps, participating files, risks, gaps, and verification.

Rules: `l2_request_flow_map_terms`

### P20

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, compare the placed_order_id stealth lookup path with the client_order_id index path. Read only. Return candidate paths, evidence, risks, recommended path if supported, and gaps.

Note: A code-path comparison with candidate paths, evidence, risks, recommendation if supported, and gaps.

Rules: `l2_code_path_comparison_terms`

### P21

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, identify the minimal safe change surface for changing placed_order_id stealth lookup behavior. Read only and stop before implementation.

Note: A change-surface summary with files to review, related tests, risk level, gaps, and no implementation.

Rules: `l2_change_surface_summary_terms`

### P22

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, break down the work to add a safer placed_order_id lookup change. Do not implement. I want dependencies, approval gates, verification strategy, and risks.

Note: A task decomposition with work packages, dependencies, approval gates, verification strategy, risks, and uncertainty.

Rules: `task_decomposition_terms`

### P23

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, draft a small documentation edit to docs/agents/INVARIANTS.md that adds a note saying the stealth manager placed-order index is the authoritative lookup key. Do not mutate files. Show exact proposed change and verification command.

Note: A draft-only implementation proposal with exact file, operation, safety checks, verification command, and no source mutation.

Rules: `l1_small_text_edit_terms`

### P24

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, draft a small unit test for sync_exchange_order_id_for_placed_order setting exchange_order_id when it is missing. Do not mutate files. Show the proposed test file and pytest command.

Note: A draft-only unit-test proposal with target test file, proposed test body/operation, verification command, and no source mutation.

Rules: `l1_small_unit_test_terms`

### P25

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, inspect this failing test and propose the smallest fix. Draft only; do not apply until approved. FAILED tests/unit/test_order_id_and_followup_rules.py::test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - AssertionError: expected find_stealth_order_by_placed_order_id docstring to mention client_order_id

Note: A draft-only simple-fix proposal with exact proposed operation, verification command, and approval gate.

Rules: `l1_simple_failing_test_fix_terms`

### P26

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, apply this exact packet only to a disposable copy and prove the source repo did not change: {"packet_operations":[{"kind":"replace_text","path":"docs/agents/INVARIANTS.md","old":"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, and DB\n  local rows.","new":"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, DB\n  local rows, and stealth manager placed-order index keys."}]}

Note: A disposable-copy apply proof that mutates only the copy, rolls it back, and reports source_changed false.

Rules: `disposable_apply_terms`

### P27

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, follow handler branch trace for request_stealth_orders as a request flow through the downstream snapshot function. Read only. Return flow steps, participating files, evidence refs, related tests, risks, gaps, and verification.

Note: A handler-branch trace that selects the Batch D handler skill and returns a request-flow map.

Rules: `l2_request_flow_map_terms`

### P28

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp, follow handler branch trace for request_stealth_orders as a request flow through the downstream snapshot function. Read only. Return flow steps, participating files, evidence refs, related tests, risks, gaps, and verification.

Note: A non-git fixture handler-branch trace that selects the Batch D handler skill and returns a request-flow map.

Rules: `l2_request_flow_map_terms`

### P29

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find the stealth_orders table schema only. Read only. Return schema field names, model files, and source refs. Exclude runtime fields.

Note: A table-schema-only answer that selects the Batch D schema isolator and avoids runtime dictionary fields.

Rules: `l1_data_model_lookup_terms`

### P30

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp, find the stealth_orders table schema only. Read only. Return schema field names, model files, and source refs. Exclude runtime fields.

Note: A non-git fixture table-schema-only answer that selects the Batch D schema isolator and avoids runtime dictionary fields.

Rules: `l1_data_model_lookup_terms`

### P31

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, locate the runtime entrypoint for the trading engine entrypoint, not dashboard server. Read only. Return command, source refs, and exclusions.

Note: A runtime-entrypoint answer that selects the Batch D entrypoint disambiguator and excludes adjacent UI services.

Rules: `l1_cli_entrypoint_lookup_terms`

### P32

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp, locate the runtime entrypoint for the trading engine entrypoint, not dashboard server. Read only. Return command, source refs, and exclusions.

Note: A non-git fixture runtime-entrypoint answer that selects the Batch D entrypoint disambiguator and excludes adjacent UI services.

Rules: `l1_cli_entrypoint_lookup_terms`

### P33

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, identify files to touch and files not to touch for the minimal safe change surface and change boundary for placed_order_id stealth lookup behavior. Read only and stop before implementation. Return risks, gaps, and verification commands.

Note: A change-boundary answer that selects the Batch D boundary summarizer and stops before implementation.

Rules: `l2_change_surface_summary_terms`

### P34

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp, identify files to touch and files not to touch for the minimal safe change surface and change boundary for placed_order_id stealth lookup behavior. Read only and stop before implementation. Return risks, gaps, and verification commands.

Note: A non-git fixture change-boundary answer that selects the Batch D boundary summarizer and stops before implementation.

Rules: `l2_change_surface_summary_terms`

### P01-V1

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find the first source point that creates or populates the placed_order_id stealth lookup key. Read only. Include evidence files, related tests, and confidence.

Note: Ambiguous 'start' wording can be interpreted as related-test discovery or a later usage point.

Rules: `l1_find_behavior_start_terms`

### P08-V1

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, follow the request_stealth_orders handler branch through the snapshot function. Read only. Return handler file, source refs, and related tests.

Note: Handler prompts can stop at a UI sender unless the handler branch is named.

Rules: `l1_endpoint_route_lookup_terms`

### P11-V1

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find only the stealth_orders table schema. Read only. Return model files, schema field names, and source refs.

Note: Schema prompts can return runtime dictionary fields instead of table schema.

Rules: `l1_data_model_lookup_terms`

### P16-V1

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, locate the trading-engine CLI or script entrypoint, not the dashboard-only server. Read only. Return the command and source refs.

Note: Entrypoint prompts can confuse the trading engine with a dashboard service.

Rules: `l1_cli_entrypoint_lookup_terms`

### P17-V1

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, choose the smallest, medium, and broad Bash validation commands for placed_order_id stealth lookup. Read only. Explain why each command matters and what risk remains.

Note: Validation prompts can omit shell surface, which matters because live validation should prefer Bash.

Rules: `l2_test_selection_terms`

### P21-V1

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, identify files to touch and files not to touch for a minimal safe placed_order_id stealth lookup change. Read only and stop before implementation.

Note: Change-surface prompts should name both touch and do-not-touch boundaries.

Rules: `l2_change_surface_summary_terms`

### P23-V1

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, draft a unified diff only for docs/agents/INVARIANTS.md that adds a note saying the stealth manager placed-order index is the authoritative lookup key. Do not mutate files. Include the verification command.

Note: Draft documentation prompts are easier to review when the requested output shape is explicit.

Rules: `l1_small_text_edit_terms`

### P26-V1

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, approved disposable copy apply only. Apply this exact packet only to a disposable copy and prove source_changed is false: {"packet_operations":[{"kind":"replace_text","path":"docs/agents/INVARIANTS.md","old":"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, and DB\n  local rows.","new":"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, DB\n  local rows, and stealth manager placed-order index keys."}]}

Note: Disposable-copy apply prompts need older-client-safe copy-only approval wording.

Rules: `disposable_apply_terms`

### P27-V1

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, follow handler branch trace for request_stealth_orders through the downstream snapshot function as a request flow map. Read only. Return flow steps, participating files, evidence refs, related tests, risks, gaps, and verification.

Note: Handler prompts can select a generic endpoint lookup unless handler-branch and downstream snapshot language is explicit.

Rules: `l2_request_flow_map_terms`

### P28-V1

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp, follow handler branch trace for request_stealth_orders through the downstream snapshot function as a request flow map. Read only. Return flow steps, participating files, evidence refs, related tests, risks, gaps, and verification.

Note: Non-git handler prompts still need explicit handler-branch and downstream snapshot language.

Rules: `l2_request_flow_map_terms`

### P29-V1

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find only the persisted stealth_orders table schema. Read only. Return schema field names, model files, and source refs. Exclude runtime dictionary fields.

Note: Schema prompts can mix persisted table fields with runtime dictionary fields unless the persisted table boundary is named.

Rules: `l1_data_model_lookup_terms`

### P30-V1

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp, find only the persisted stealth_orders table schema. Read only. Return schema field names, model files, and source refs. Exclude runtime dictionary fields.

Note: Non-git schema prompts can mix persisted table fields with runtime dictionary fields unless the persisted table boundary is named.

Rules: `l1_data_model_lookup_terms`

### P31-V1

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, locate the trading-engine runtime entrypoint and exclude the dashboard server path. Read only. Return command, source refs, and excluded adjacent entrypoints.

Note: Entrypoint prompts can select dashboard_server.py unless the runtime subsystem and exclusion are explicit.

Rules: `l1_cli_entrypoint_lookup_terms`

### P32-V1

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp, locate the trading-engine runtime entrypoint and exclude the dashboard server path. Read only. Return command, source refs, and excluded adjacent entrypoints.

Note: Non-git entrypoint prompts can select dashboard_server.py unless the runtime subsystem and exclusion are explicit.

Rules: `l1_cli_entrypoint_lookup_terms`

### P33-V1

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, summarize the change boundary for placed_order_id stealth lookup by listing files to touch and files not to touch. Read only and stop before implementation. Return risks, gaps, and verification commands.

Note: Change-surface prompts can drift into implementation planning unless the boundary and stop condition are explicit.

Rules: `l2_change_surface_summary_terms`

### P34-V1

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp, summarize the change boundary for placed_order_id stealth lookup by listing files to touch and files not to touch. Read only and stop before implementation. Return risks, gaps, and verification commands.

Note: Non-git change-surface prompts can drift into implementation planning unless the boundary and stop condition are explicit.

Rules: `l2_change_surface_summary_terms`

