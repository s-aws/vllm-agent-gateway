# Post-Restart Runtime Readiness Examples

Run after restarting vLLM, the gateway/proxies, controller service, or AnythingLLM.

## PowerShell To WSL

```powershell
$env:ANYTHINGLLM_API_KEY=[Environment]::GetEnvironmentVariable('ANYTHINGLLM_API_KEY','User')
$env:WSLENV='ANYTHINGLLM_API_KEY/u'
wsl.exe --cd /mnt/c/agentic_agents -- python3 scripts/validate_post_restart_runtime_readiness.py `
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
for artifact in report["source_artifacts"]:
    print(f"{artifact['name']}: {artifact['status']} {artifact['path']}")
PY
```

Passing summary shape:

```json
{
  "decision": "ready_after_restart",
  "failed_source_report_count": 0,
  "missing_required_surface_count": 0,
  "validation_error_count": 0
}
```
