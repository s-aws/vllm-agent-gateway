# Founder Field Prompt Evaluation

- Status: passed
- Created at: 20260606T003520753977Z
- AnythingLLM workspace: my-workspace
- Prompt count: 2
- Passed: 2
- Failed: 0

## Results

| Case | Status | Expected workflow | Run ID | Initial difference | Miss suggestion |
| --- | --- | --- | --- | --- | --- |
| P07 | passed | code_investigation.plan | workflow-router-20260606T003522168983Z | No marker-level difference from the baseline target. |  |
| P17 | passed | code_investigation.plan | workflow-router-20260606T003533903801Z | No marker-level difference from the baseline target. |  |

## Prompt Baselines

### P07

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, summarize this pytest failure and tell me the next bounded inspection step. Do not edit files. FAILED tests/unit/test_order_id_and_followup_rules.py::test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - AssertionError: expected client_order_id index

Baseline target: A pasted-failure summary with failed test, primary error, likely cause, and next bounded inspection step.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T003522168983Z`

### P17

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, choose the smallest, medium, and broad validation commands for placed_order_id stealth lookup. Read only. Explain why each command matters and what risk remains.

Baseline target: A test-selection plan with smallest, medium, and broad commands, rationale, risks, confidence, and gaps.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T003533903801Z`

