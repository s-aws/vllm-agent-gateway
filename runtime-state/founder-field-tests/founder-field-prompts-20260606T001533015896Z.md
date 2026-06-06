# Founder Field Prompt Evaluation

- Status: passed
- Created at: 20260606T001533015928Z
- AnythingLLM workspace: my-workspace
- Prompt count: 1
- Passed: 1
- Failed: 0

## Results

| Case | Status | Expected workflow | Run ID | Initial difference | Miss suggestion |
| --- | --- | --- | --- | --- | --- |
| P01 | passed | code_investigation.plan | workflow-router-20260606T001534804157Z | No marker-level difference from the baseline target. |  |

## Prompt Baselines

### P01

Prompt: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, where does the placed_order_id stealth lookup start? Read only and give me the beginning point, evidence files, related tests, and confidence.

Baseline target: A read-only beginning-point answer with the first relevant source location, evidence files, related tests, recommended commands, and a confidence statement.

Expected workflow: `code_investigation.plan`

Initial difference: No marker-level difference from the baseline target.

Suggested prompt if missed: None

Run ID: `workflow-router-20260606T001534804157Z`

