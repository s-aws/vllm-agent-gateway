# Post-Restart Runtime Readiness

Phase 163 adds one post-reboot/post-restart gate for founder testing. It composes existing readiness checks instead of creating another health-check implementation.

Use this after restarting vLLM, the gateway/proxies, the controller, or AnythingLLM.

## What It Proves

- localhost model `8000` responds through the OpenAI-compatible model endpoint.
- LLM gateway `8300` and workflow-router gateway `8500` are reachable and correctly targeted.
- controller `8400` is healthy and allowlists the project plus both frozen Coinbase fixtures.
- configured role proxy ports respond.
- AnythingLLM API key, workspace, and target URL are valid.
- `hi` and same-session greeting recovery produce a safe, useful chat response through AnythingLLM without triggering repository work.

## Single Path

This gate does not probe ports or run AnythingLLM chat directly. It calls:

- first-time user doctor through the health-drift guard
- gateway/AnythingLLM health-drift guard
- AnythingLLM session-recovery smoke

The Phase 163 report links those source reports by path and SHA-256 hash.

## Run

From PowerShell, pass the AnythingLLM key into WSL:

```powershell
$env:ANYTHINGLLM_API_KEY=[Environment]::GetEnvironmentVariable('ANYTHINGLLM_API_KEY','User')
$env:WSLENV='ANYTHINGLLM_API_KEY/u'
wsl.exe --cd /mnt/c/agentic_agents -- python3 scripts/validate_post_restart_runtime_readiness.py
```

Expected marker:

```text
POST RESTART RUNTIME READINESS PASS
```

## Output

Default report:

```text
runtime-state/post-restart-runtime-readiness/phase163/phase163-post-restart-runtime-readiness-report.json
```

The report includes:

- child report paths and hashes
- required and covered restart surfaces
- missing restart surfaces
- source report summaries
- validation errors
- next action

If it passes, the next action is Phase 164 founder field test round 2.
