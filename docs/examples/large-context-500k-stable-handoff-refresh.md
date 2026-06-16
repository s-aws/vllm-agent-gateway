# Large-Context 500k Stable Handoff Refresh Examples

## Validate The Refresh

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_large_context_500k_stable_handoff_refresh.py \
  --phase276-report-path runtime-state/phase276/phase276-large-context-500k-candidate-decision-gate-report.json \
  --output-path runtime-state/phase277/phase277-large-context-500k-stable-handoff-refresh-report.json \
  --markdown-output-path runtime-state/phase277/phase277-large-context-500k-stable-handoff-refresh-report.md
```

Expected result:

```text
PHASE277 LARGE CONTEXT 500K STABLE HANDOFF REFRESH PASS
```

## Validate Supporting Stable Metadata

```bash
python3 scripts/validate_release_channels.py \
  --channel stable \
  --release-candidate-report runtime/release_proofs/v1-1-release-candidate-stable-proof.json \
  --output-path runtime-state/release-channels/stable-500k-refresh.json
```

Expected result:

```text
RELEASE CHANNEL PASS
```

## Re-run The Live 500k Candidate Gate

```bash
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_large_context_500k_live_acceptance.py \
  --live \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --anythingllm-workflow-router-base-url http://127.0.0.1:8500/v1 \
  --timeout-seconds 1200
```

For Windows AnythingLLM pointed at a WSL network URL, replace only `--anythingllm-workflow-router-base-url` with the printed network workflow-router URL and keep the internal Bash URL on `http://127.0.0.1:8500/v1`.

This validates governed 500k-token project usability. It does not validate raw 500k prompt serving.
