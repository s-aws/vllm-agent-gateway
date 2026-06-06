# First-Time User Doctor Examples

Run these before first-time AnythingLLM prompt testing.

## Default Doctor

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/run_first_time_user_doctor.py
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
```

## Review Order

1. Fix failed port checks first.
2. Fix gateway routing and controller allowed roots.
3. Fix AnythingLLM API key, workspace, and target URL.
4. Fix protected fixture status.
5. Then run the L1/L2 or V1 acceptance validators.
