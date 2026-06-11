# Post-Restart Runtime Readiness Examples

Run after restarting vLLM, the gateway/proxies, controller service, or AnythingLLM.

## PowerShell To WSL

```powershell
$key=$env:ANYTHINGLLM_API_KEY
if (-not $key) { throw 'ANYTHINGLLM_API_KEY is not set in Windows environment' }
wsl.exe --cd /mnt/c/agentic_agents -- env "ANYTHINGLLM_API_KEY=$key" python3 scripts/validate_post_restart_runtime_readiness.py `
  --timeout-seconds 120 `
  --output-path runtime-state/post-restart-runtime-readiness/phase163/phase163-post-restart-runtime-readiness-report.json
```

Expected marker:

```text
POST RESTART RUNTIME READINESS PASS
```

## Bash

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_post_restart_runtime_readiness.py \
  --timeout-seconds 120 \
  --output-path runtime-state/post-restart-runtime-readiness/phase163/phase163-post-restart-runtime-readiness-report.json
```

## Inspect The Report

```bash
python3 - <<'PY'
import json
from pathlib import Path

path = Path("runtime-state/post-restart-runtime-readiness/phase163/phase163-post-restart-runtime-readiness-report.json")
report = json.loads(path.read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
print("missing:", report["missing_required_surfaces"])
for action in report.get("diagnostic_actions", []):
    print(f"{action['source']} {action['check_id']}: {action['next_action']}")
    if action.get("recovery_command"):
        print("  recovery:", action["recovery_command"])
    if action.get("powershell_wsl_env_example"):
        print("  key bridge:", action["powershell_wsl_env_example"])
for artifact in report["source_artifacts"]:
    print(f"{artifact['name']}: {artifact['status']} {artifact['path']}")
PY
```

Passing summary shape:

```json
{
  "blocking_diagnostic_action_count": 0,
  "decision": "ready_after_restart",
  "diagnostic_action_count": 0,
  "failed_source_report_count": 0,
  "missing_required_surface_count": 0,
  "validation_error_count": 0
}
```
