# EIG Baseline Candidate Privacy Repair Examples

Run focused regression for the deterministic privacy repair and comparison gate:

```bash
cd /mnt/c/agentic_agents
python3 -m pytest \
  tests/regression/test_eig3_privacy_runtime_routing.py \
  tests/regression/test_eig3_privacy_runtime_chat.py \
  tests/regression/test_eig_baseline_candidate_local_comparison.py \
  -q
```

Restart the Bash-hosted stack so workflow-router and AnythingLLM use the repaired controller service:

```bash
cd /mnt/c/agentic_agents
./stop-agent-prompt-proxies.sh || true
WORKFLOW_ROUTER_GATEWAY_BIND_HOST=0.0.0.0 ./start-agent-prompt-proxies.sh
```

Run the repaired live replay:

```bash
export ANYTHINGLLM_API_KEY="<redacted>"
python3 scripts/validate_eig_baseline_candidate_live_replay.py \
  --output-path runtime-state/eig-baseline-candidate-live-replay/phase314-after-pii-repair-live.json \
  --anythingllm-api-base-url http://192.168.0.208:3001 \
  --timeout-seconds 240
```

Expected marker:

```text
EIG BASELINE CANDIDATE LIVE REPLAY PASS
```

Run the blind-baseline comparison against the repaired replay:

```bash
python3 scripts/validate_eig_baseline_candidate_local_comparison.py \
  --live-replay-report-path runtime-state/eig-baseline-candidate-live-replay/phase314-after-pii-repair-live.json \
  --output-path runtime-state/eig-baseline-candidate-local-comparison/phase314-after-pii-repair-comparison.json
```

Expected decision:

```text
comparison_decision=passed
passed_response_count=14
failed_response_count=0
recorded_evidence=["blind_baseline","local_model_comparison"]
remaining_missing_evidence=["founder_approval","holdout","no_mutation_proof","route_proof"]
```

This does not approve promotion. It only closes the local-model comparison evidence item for the current EIG baseline candidates.
