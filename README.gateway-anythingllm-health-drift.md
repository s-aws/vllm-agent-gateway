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
- `wrong_backend_target`: gateway or AnythingLLM points at the wrong model, route, controller path, or gateway. This also covers AnythingLLM API-base drift where the configured API origin returns `404` for AnythingLLM API routes, such as when another local web app is serving on port `3001`.
- `auth_failure`: AnythingLLM authorized endpoints returned `401` or `403`, or the API key is unavailable.
- `unexpected_response`: HTTP and connectivity worked, but semantic validation failed.
- `unclassified_failure`: guard failure because a doctor failure was not diagnosable enough.

## Run

```bash
python3 scripts/validate_gateway_anythingllm_health_drift.py \
  --output-path runtime-state/gateway-anythingllm-health-drift/phase141/phase141-health-drift-report.json
```

For AnythingLLM auth checks from Windows into WSL, inject the Windows API key into the WSL process explicitly.

```powershell
$key=$env:ANYTHINGLLM_API_KEY
if (-not $key) { throw 'ANYTHINGLLM_API_KEY is not set in Windows environment' }
wsl.exe --cd /mnt/c/agentic_agents -- env "ANYTHINGLLM_API_KEY=$key" python3 scripts/validate_gateway_anythingllm_health_drift.py
```

## Output

The report is written under `runtime-state/gateway-anythingllm-health-drift/phase141/` and includes:

- the linked first-time-user doctor report path and hash
- checked categories and featured port check IDs
- findings with `kind`, check ID, URL, HTTP status, message, next action, and available recovery commands
- summary counts by drift kind

The gate passes only when the doctor passes and all required health surfaces are represented.

## Known Drift Example

If `http://127.0.0.1:3001` is reachable but is not the AnythingLLM API, the guard should fail with `wrong_backend_target`, not `auth_failure` or `unclassified_failure`.

On the current Windows/WSL host, the failure was caused by `node.exe` listening on `127.0.0.1:3001` while `AnythingLLM.exe` listened on `0.0.0.0:3001`. The working API bases were:

- `http://192.168.0.208:3001`
- `http://100.100.12.45:3001`

Use the working API base with `--anythingllm-api-base-url` and keep Bash-side gateway validation on `http://127.0.0.1:8500/v1`.

Expected failed summary shape:

```json
{
  "status": "failed",
  "summary": {
    "kind_counts": {
      "wrong_backend_target": 3,
      "auth_failure": 0,
      "unclassified_failure": 0
    },
    "unclassified_finding_count": 0
  }
}
```
