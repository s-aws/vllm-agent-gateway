# Stable Handoff Examples

## Validate Stable Channel Metadata

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_release_channels.py \
  --channel stable \
  --release-candidate-report runtime/release_proofs/v1-1-release-candidate-stable-proof.json \
  --output-path runtime-state/release-channels/stable-readiness.json
```

Expected result:

```text
RELEASE CHANNEL PASS
```

## Run Stable Smoke

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

Expected result:

```text
STABLE HANDOFF PASS
```

The smoke can still report a warning for the git-enabled frozen fixture when Bash sees Windows/WSL line-ending dirtiness. Continue only when watched hashes are unchanged and protected fixture state is not changed.

## Send The First Stable Prompt

Use a fresh AnythingLLM thread:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, explain what find_stealth_order_by_placed_order_id does in core/stealth_order_manager.py. Read only. Include key inputs, outputs, side effects, and tests.
```

Expected high-level result:

- chat-visible answer content appears under `Answer:`
- route explanation shows `code_investigation.plan`
- response includes a `workflow-router-...` run ID
- no protected fixture files change

## Record Feedback

```text
Record feedback for run workflow-router-REPLACE_ME: useful: the answer appeared in chat. wrong: none. missing: related tests should be more specific.
```

Expected high-level result:

- `workflow_feedback.record` appears in the response
- a `workflow-feedback-...` run ID is returned
- feedback is linked to the target workflow-router run

## Roll Back To Release Candidate

If stable smoke fails, keep the external tester on the release-candidate instructions until the failed check is fixed:

```bash
python3 scripts/validate_v1_acceptance.py \
  --profile v1.1-release-candidate \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github
```
