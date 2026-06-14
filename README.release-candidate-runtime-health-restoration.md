# Release-Candidate Runtime Health Restoration

Phase 245 verifies that a restarted release-candidate stack is usable before the release decision is rerun.

Use this gate after manually restarting vLLM, the gateway/proxies, controller, and AnythingLLM. It checks the localhost model, every featured gateway/controller role port, the workflow-router gateway, AnythingLLM target settings, one minimal read-only workflow-router prompt through the gateway, the same prompt through AnythingLLM, and protected fixture mutation state.

The gate is intentionally narrower than the release decision gate. Phase 245 answers whether runtime health is restored. Phase 246 reruns the Phase 244 ship/hold/repair decision after this gate passes.

## Command

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_release_candidate_runtime_health_restoration.py --timeout-seconds 240 --health-timeout-seconds 20
```

The validator writes:

- `runtime-state/release-candidate-runtime-health-restoration/phase245/phase245-release-candidate-runtime-health-restoration-report.json`

The report is local runtime evidence and should not be committed.

## Pass Criteria

- `http://127.0.0.1:8000/v1/models` responds from Bash.
- Ports `8300`, `8400`, `8500`, `8101`, `8102`, and `8201` through `8205` respond from Bash.
- AnythingLLM is reachable at `http://127.0.0.1:3001`.
- AnythingLLM uses the workflow-router gateway target `http://127.0.0.1:8500/v1`.
- Gateway and AnythingLLM both return a chat-visible workflow-router answer for the minimal read-only prompt.
- `/mnt/c/coinbase_testing_repo_frozen_tmp` and `/mnt/c/coinbase_testing_repo_frozen_tmp.github` remain unchanged.

## Failure Handling

If the command fails, inspect the `blockers` field in the report before changing code. Runtime-health failures normally mean the model or proxy stack is still starting, misconfigured, or pointed at the wrong port.
