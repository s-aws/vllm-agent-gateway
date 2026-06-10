# Gateway And AnythingLLM Health Drift

Phase 141 adds a diagnostic guard over the existing first-time user doctor. It does not add a second health probing path. The guard runs the doctor, consumes the doctor checks, and classifies setup drift into deterministic failure kinds.

Use this before founder or AnythingLLM prompt testing when chat quality appears blocked by setup behavior instead of model output.

## What It Checks

- localhost model port `8000`
- LLM gateway `8300`
- workflow-router gateway `8500`
- controller `8400`
- featured role proxy ports from `runtime/roles.json`
- AnythingLLM API key, workspace, and configured Generic OpenAI base URL
- frozen Coinbase fixture readiness through the doctor report

## Drift Kinds

- `unreachable_port`: no listener, refused connection, or no response headers.
- `headers_without_body_timeout`: response headers arrived, but body bytes timed out.
- `wrong_backend_target`: gateway or AnythingLLM points at the wrong model, route, controller path, or gateway.
- `auth_failure`: AnythingLLM authorized endpoints returned `401` or `403`, or the API key is unavailable.
- `unexpected_response`: HTTP and connectivity worked, but semantic validation failed.
- `unclassified_failure`: guard failure because a doctor failure was not diagnosable enough.

## Run

```bash
python3 scripts/validate_gateway_anythingllm_health_drift.py \
  --output-path runtime-state/gateway-anythingllm-health-drift/phase141/phase141-health-drift-report.json
```

For AnythingLLM auth checks from Windows into Bash, export the key through `WSLENV` first.

```powershell
$env:ANYTHINGLLM_API_KEY=[Environment]::GetEnvironmentVariable('ANYTHINGLLM_API_KEY','User')
$env:WSLENV='ANYTHINGLLM_API_KEY/u'
wsl.exe --cd /mnt/c/agentic_agents -- python3 scripts/validate_gateway_anythingllm_health_drift.py
```

## Output

The report is written under `runtime-state/gateway-anythingllm-health-drift/phase141/` and includes:

- the linked first-time-user doctor report path and hash
- checked categories and featured port check IDs
- findings with `kind`, check ID, URL, HTTP status, message, and next action
- summary counts by drift kind

The gate passes only when the doctor passes and all required health surfaces are represented.
