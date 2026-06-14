# Release-Candidate Runtime Health Restoration Examples

Run the gate from Bash after the runtime stack is restarted:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$ANYTHINGLLM_API_KEY"
python3 scripts/validate_release_candidate_runtime_health_restoration.py --timeout-seconds 240 --health-timeout-seconds 20
```

If vLLM is still loading, the report will fail with `runtime_health.*` blockers. Wait for:

```bash
curl -sS http://127.0.0.1:8000/v1/models
```

Then restart the gateway/proxy stack from the release-candidate checkout and rerun:

```bash
bash ./stop-agent-prompt-proxies.sh || true
bash ./start-agent-prompt-proxies.sh
python3 scripts/validate_release_candidate_runtime_health_restoration.py --timeout-seconds 240 --health-timeout-seconds 20
```

After Phase 245 passes, rerun the release decision:

```bash
python3 scripts/validate_v1_release_candidate_decision_gate.py --health-timeout-seconds 20
```
