# Stable Handoff

Stable is the external-tester channel promoted from the passed V1.1 release-candidate proof.

Use this handoff only for the current product surface: natural-language L1/L2 read-only prompts, draft-only small implementation plans, approved disposable-copy apply proof, feedback capture, setup validation, security policy validation, and run observability. Advanced broad refactor orchestration remains deferred.

## What Stable Means

- `runtime/release_channels.json` marks `stable` as `active`.
- Stable activation points at the committed proof `runtime/release_proofs/v1-1-release-candidate-stable-proof.json`.
- Generated `runtime-state/` reports are local-only; committed proof metadata is the clean-clone source of truth.
- The activation report is a passed `v1_acceptance_report` with profile `v1.1-release-candidate`.
- First-time testers still use AnythingLLM pointed at `http://127.0.0.1:8500/v1`.
- The stable smoke command reruns setup, release-channel validation, security policy, one live onboarding prompt, feedback capture, and protected-fixture checks.

Stable does not mean every coding-agent task is supported. It means the current documented tester path is ready for external use under the stated boundaries.

## Prerequisites

- vLLM model endpoint is healthy at `http://127.0.0.1:8000/v1`.
- Harness ports are healthy at `8300`, `8500`, `8400`, and role ports.
- AnythingLLM is running at `http://127.0.0.1:3001`.
- AnythingLLM is configured to use `http://127.0.0.1:8500/v1`.
- `ANYTHINGLLM_API_KEY` is available.
- Both frozen fixtures exist:
  - `/mnt/c/coinbase_testing_repo_frozen_tmp`
  - `/mnt/c/coinbase_testing_repo_frozen_tmp.github`

The git-enabled fixture may show many modified files when inspected from Bash because of Windows/WSL line-ending behavior. This is a warning, not a blocker, when the stable smoke report says watched hashes are unchanged and protected fixture state `changed` is `false`. Treat it as a blocker only if watched hashes change, the warning is not line-ending-only, or the smoke reports fixture mutation.

## Stable Smoke

Run from Bash:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_stable_handoff.py \
  --release-candidate-report runtime/release_proofs/v1-1-release-candidate-stable-proof.json \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900 \
  --command-timeout-seconds 3600 \
  --output-path runtime-state/stable-handoff/stable-smoke.json
```

Expected markers:

```text
STABLE HANDOFF REPORT ...
STABLE HANDOFF SUMMARY ...
STABLE HANDOFF PASS
```

The report lists the child setup, release-channel, security, and onboarding reports.

## First Tester Prompt

Use a fresh AnythingLLM thread and send:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, explain what find_stealth_order_by_placed_order_id does in core/stealth_order_manager.py. Read only. Include key inputs, outputs, side effects, and tests.
```

Expected response markers include:

- `workflow_router.plan completed`
- `run_id: workflow-router-`
- `Selected workflow:`
- `Selected skills:`
- `Selected tools:`
- `Answer:`
- `Inputs:`
- `Outputs:`
- `Side effects:`
- `Related tests:`

## Feedback

When a tester sees a confusing answer, wrong route, setup failure, unsafe output, or missing capability, record feedback in the same AnythingLLM chat using the returned `run_id`.

Example:

```text
Record feedback for run workflow-router-REPLACE_ME: useful: the answer was visible in chat. missing: the related tests section was too vague.
```

Feedback artifacts are written through `workflow_feedback.record` and should be reviewed before planning the next roadmap phase.

## Rollback

If stable smoke fails, stop tester handoff and use `release-candidate` until the failing check is fixed.

Restart the harness from Bash:

```bash
cd /mnt/c/agentic_agents
./stop-agent-prompt-proxies.sh
./start-agent-prompt-proxies.sh
```

Then rerun:

```bash
python3 scripts/run_first_time_user_doctor.py
python3 scripts/validate_stable_handoff.py \
  --release-candidate-report runtime/release_proofs/v1-1-release-candidate-stable-proof.json
```

If protected fixture state changes, do not run more live tests until fixture hashes and git status are inspected.

Examples: [docs/examples/stable-handoff.md](docs/examples/stable-handoff.md).
