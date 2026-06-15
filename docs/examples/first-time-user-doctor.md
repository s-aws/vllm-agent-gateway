# First-Time User Doctor Examples

Run these before first-time AnythingLLM prompt testing.

## Default Doctor

```powershell
$key=$env:ANYTHINGLLM_API_KEY
if (-not $key) { throw 'ANYTHINGLLM_API_KEY is not set in Windows environment' }
wsl.exe --cd /mnt/c/agentic_agents -- env "ANYTHINGLLM_API_KEY=$key" python3 scripts/run_first_time_user_doctor.py
```

Expected markers:

```text
FIRST TIME USER DOCTOR REPORT ...
FIRST TIME USER DOCTOR SUMMARY ...
FIRST TIME USER DOCTOR PASS
```

## Write A Named Report

```bash
python3 scripts/run_first_time_user_doctor.py \
  --output-path runtime-state/first-time-user-doctor/phase76-live.json
```

## Custom Workspace

```bash
python3 scripts/run_first_time_user_doctor.py \
  --workspace my-workspace \
  --anythingllm-api-base-url http://127.0.0.1:3001 \
  --expected-anythingllm-llm-base-url http://127.0.0.1:8500/v1
```

## Windows AnythingLLM To WSL Network Target

If Windows clients can connect to WSL localhost ports but hang while waiting for response body bytes, use the WSL network workflow-router URL printed by `start-agent-prompt-proxies.sh` for AnythingLLM while keeping Bash health checks on localhost:

```powershell
$key=[Environment]::GetEnvironmentVariable('ANYTHINGLLM_API_KEY','User')
wsl.exe --cd /mnt/c/agentic_agents -- env "ANYTHINGLLM_API_KEY=$key" python3 scripts/run_first_time_user_doctor.py `
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 `
  --expected-anythingllm-llm-base-url http://<wsl-network-ip>:8500/v1
```

## Expected JSON Fields

```text
kind=first_time_user_doctor_report
status=passed|failed
summary.status_counts={...}
summary.failed_check_ids=[...]
summary.warning_check_ids=[...]
checks[].id=...
checks[].status=passed|failed|warning|skipped
checks[].next_action=...
checks[].details.recovery_command=...
checks[].details.powershell_wsl_env_example=...
```

## Review Order

1. Fix failed port checks first.
2. Fix gateway routing and controller allowed roots.
3. Fix AnythingLLM API key, workspace, and target URL.
4. Fix protected fixture status.
5. Then run the L1/L2 or V1 acceptance validators.
