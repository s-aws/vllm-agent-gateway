# External Tester Onboarding

This is the contextless tester path for the current release-candidate channel.

It is intentionally smaller than the founder field suite. It uses a curated set of read-only L1 prompts so a tester can prove the harness works through AnythingLLM before trying broader workflows.

## Source Of Truth

Prompt pack:

```text
runtime/external_tester_onboarding.json
```

Validator:

```bash
python scripts/validate_external_tester_onboarding.py
```

Reports:

```text
runtime-state/external-tester-onboarding/
```

## What It Proves

- The onboarding prompt pack is valid and tied to the `release-candidate` channel.
- First-test prompts are read-only and do not include deferred advanced refactor or mutation paths.
- Expected output markers and artifact keys are documented before testing.
- Feedback templates exist for confusion, routing misses, answer-quality misses, and setup failures.
- Live validation can run at least one onboarding prompt through AnythingLLM and link feedback to the returned run ID.

## Before Prompt Testing

Run release-channel and setup validation from Bash:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_release_channels.py
python3 scripts/run_first_time_user_doctor.py
```

AnythingLLM must point at:

```text
http://127.0.0.1:8500/v1
```

## Static Onboarding Validation

```bash
python3 scripts/validate_external_tester_onboarding.py \
  --output-path runtime-state/external-tester-onboarding/current.json
```

Expected markers:

```text
EXTERNAL TESTER ONBOARDING REPORT ...
EXTERNAL TESTER ONBOARDING SUMMARY ...
EXTERNAL TESTER ONBOARDING PASS
```

## Live Onboarding Validation

Run one representative first-test prompt through AnythingLLM and record linked feedback:

```bash
python3 scripts/validate_external_tester_onboarding.py \
  --live-anythingllm \
  --include-feedback \
  --case-id ONB-001 \
  --output-path runtime-state/external-tester-onboarding/live-onb-001.json
```

Expected result:

```text
EXTERNAL TESTER ONBOARDING PASS
```

The report includes the workflow-router `run_id`, the `workflow-feedback` run ID, and fixture mutation proof through unchanged protected fixture state.

The full V1 release-candidate command also runs this live onboarding check as suite `external_tester_onboarding`.

## First Manual Prompt

Use this first in a fresh AnythingLLM thread:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, explain what find_stealth_order_by_placed_order_id does in core/stealth_order_manager.py. Read only. Include key inputs, outputs, side effects, and tests.
```

Expected markers:

- `workflow_router.plan completed`
- `run_id: workflow-router-...`
- `Skill Selection:`
- `Answer:`
- `StealthOrderManager.find_stealth_order_by_placed_order_id`
- `Inputs:`
- `Outputs:`
- `Side effects:`
- `Related tests:`
- `downstream_code_explanation`

## Feedback Capture

After a prompt returns `run_id: workflow-router-...`, testers can paste a feedback template as normal chat.

Confusing response:

```text
Record feedback for run workflow-router-YYYYMMDDTHHMMSSffffffZ: confusing: the onboarding response was hard to understand. missing: clearer next action for a first-time tester.
```

Routing miss:

```text
Record feedback for run workflow-router-YYYYMMDDTHHMMSSffffffZ: wrong: onboarding prompt selected the wrong workflow or skill. missing: expected the documented onboarding workflow.
```

Answer-quality miss:

```text
Record feedback for run workflow-router-YYYYMMDDTHHMMSSffffffZ: useful: onboarding response was visible in chat. missing: expected one of the documented answer markers or source references.
```

Setup failure after setup is restored:

```text
Record feedback for run workflow-router-YYYYMMDDTHHMMSSffffffZ: missing: setup failed before prompt testing. confusing: first-time setup instructions did not identify the blocker quickly enough.
```

Expected feedback markers:

- `workflow_feedback.record`
- `run_id: workflow-feedback-...`
- `target_run_id`
- `feedback_record`
- `linked_run_found`

## Boundary

Do not use broad refactor, approval continuation, disposable-copy apply, or mutation-capable prompts in first-test onboarding. Those remain later-stage validation paths.

Examples: [docs/examples/external-tester-onboarding.md](docs/examples/external-tester-onboarding.md).
