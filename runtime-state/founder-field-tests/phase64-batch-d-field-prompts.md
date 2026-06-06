# Founder Field Prompt Evaluation

- Status: passed
- Created at: 20260606T044827018215Z
- AnythingLLM workspace: my-workspace
- Prompt count: 8
- Passed: 8
- Failed: 0

## Results

| Case | Status | Output contract | Semantic quality | Expected workflow | Run ID | Initial difference | Miss suggestion | Refined prompt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P27 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T044832624939Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp.github, follow handler branch trace for request_stealth_orders through the downstream snapshot function as a request flow map. Read only. Return flow steps, participating files, evidence refs, related tests, risks, gaps, and verification. |
| P28 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T044843184508Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp, follow handler branch trace for request_stealth_orders through the downstream snapshot function as a request flow map. Read only. Return flow steps, participating files, evidence refs, related tests, risks, gaps, and verification. |
| P29 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T044858997182Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find only the persisted stealth_orders table schema. Read only. Return schema field names, model files, and source refs. Exclude runtime dictionary fields. |
| P30 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T044910845132Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp, find only the persisted stealth_orders table schema. Read only. Return schema field names, model files, and source refs. Exclude runtime dictionary fields. |
| P31 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T044922057524Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp.github, locate the trading-engine runtime entrypoint and exclude the dashboard server path. Read only. Return command, source refs, and excluded adjacent entrypoints. |
| P32 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T044930044073Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp, locate the trading-engine runtime entrypoint and exclude the dashboard server path. Read only. Return command, source refs, and excluded adjacent entrypoints. |
| P33 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T044951382652Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp.github, summarize the change boundary for placed_order_id stealth lookup by listing files to touch and files not to touch. Read only and stop before implementation. Return risks, gaps, and verification commands. |
| P34 | passed | passed | passed | code_investigation.plan | workflow-router-20260606T045000971513Z | No marker-level or semantic difference from the baseline target. |  | In /mnt/c/coinbase_testing_repo_frozen_tmp, summarize the change boundary for placed_order_id stealth lookup by listing files to touch and files not to touch. Read only and stop before implementation. Return risks, gaps, and verification commands. |

## Prompt Baselines

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

Run ID: `workflow-router-20260606T044832624939Z`

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

Run ID: `workflow-router-20260606T044843184508Z`

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

Run ID: `workflow-router-20260606T044858997182Z`

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

Run ID: `workflow-router-20260606T044910845132Z`

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

Run ID: `workflow-router-20260606T044922057524Z`

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

Run ID: `workflow-router-20260606T044930044073Z`

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

Run ID: `workflow-router-20260606T044951382652Z`

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

Run ID: `workflow-router-20260606T045000971513Z`

