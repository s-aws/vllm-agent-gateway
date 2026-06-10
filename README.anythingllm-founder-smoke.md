# AnythingLLM Founder Smoke Suite

Phase 134 runs a small founder smoke suite through AnythingLLM after the stable release gate reports `ready_for_founder_testing`.

This is not the full 34-prompt founder field suite. It is a fast live check that the current founder path works through the real AnythingLLM workspace, workflow-router gateway, controller, and local model.

## Smoke Cases

Current Phase 134 cases:

- `P01`: find where the placed-order lookup begins
- `P02`: explain `find_stealth_order_by_placed_order_id`
- `P03`: find related tests and smallest useful pytest command
- `P22`: decompose a safer lookup change without implementation

## Command

From PowerShell:

```powershell
$env:ANYTHINGLLM_API_KEY=[Environment]::GetEnvironmentVariable('ANYTHINGLLM_API_KEY','User')
$env:WSLENV='ANYTHINGLLM_API_KEY/u'
wsl.exe --cd /mnt/c/agentic_agents -- python3 scripts/run_founder_field_prompt_eval.py `
  --case-id P01 `
  --case-id P02 `
  --case-id P03 `
  --case-id P22 `
  --anythingllm-api-base-url http://127.0.0.1:3001 `
  --workspace my-workspace `
  --timeout-seconds 900 `
  --output-path runtime-state/founder-field-tests/phase134-founder-smoke.json `
  --markdown-output-path runtime-state/founder-field-tests/phase134-founder-smoke.md
```

Expected marker:

```text
FOUNDER FIELD PASS
```

## Current Result

The current Phase 134 smoke passed:

- `passed=4`
- `failed=0`
- fixture state unchanged
- report: `runtime-state/founder-field-tests/phase134-founder-smoke.json`
- markdown review: `runtime-state/founder-field-tests/phase134-founder-smoke.md`

## Failure Handling

If a smoke case fails, do not tune the prompt directly. Classify the miss in Phase 135 as one of:

- baseline candidate
- holdout candidate
- repair follow-up
- rejected finding
- skill/tool gap
