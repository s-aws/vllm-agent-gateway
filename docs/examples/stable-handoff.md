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

## Refresh Field-Test Closeout

```bash
python3 scripts/validate_stable_release_refresh.py \
  --run-refresh \
  --execute-reset-start \
  --execute-recovery \
  --output-path runtime-state/stable-release-refresh/phase160/phase160-stable-release-refresh-report.json \
  --markdown-output-path runtime-state/stable-release-refresh/phase160/phase160-stable-release-refresh-report.md
python3 scripts/validate_skill_tool_gap_batch_proposal.py \
  --output-path runtime-state/skill-tool-gap-batch-proposal/phase161/phase161-skill-tool-gap-batch-proposal-report.json \
  --markdown-output-path runtime-state/skill-tool-gap-batch-proposal/phase161/phase161-skill-tool-gap-batch-proposal-report.md
```

Expected current result:

```text
PHASE160 STABLE RELEASE REFRESH PASS
PHASE161 SKILL TOOL GAP BATCH PROPOSAL PASS
```

The current Phase 161 decision is `no_new_batch_justified`.

## Run The 384k Acceptance Gate

```bash
python3 scripts/validate_large_context_384k_live_acceptance.py \
  --live \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --anythingllm-workflow-router-base-url http://127.0.0.1:8500/v1 \
  --timeout-seconds 1200
```

For split Windows/WSL setups, replace only `--anythingllm-workflow-router-base-url` with the workflow-router network URL printed by `start-agent-prompt-proxies.sh`.

Expected result:

```text
PHASE261 LARGE CONTEXT 384K LIVE ACCEPTANCE PASS
```

This is the current large-context proof path for usable 384k-token projects. It is not a raw prompt-stuffing proof.

## Run The 384k Release Decision Gate

```bash
python3 scripts/validate_large_context_384k_release_candidate_decision_gate.py \
  --phase264-report-path /tmp/agentic_agents_phase264_remote_clone/runtime-state/phase264/phase264-large-context-384k-clean-clone-replay-report.json \
  --health-timeout-seconds 10
```

Expected result:

```text
PHASE265 LARGE CONTEXT 384K RELEASE CANDIDATE DECISION GATE PASS
```

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
