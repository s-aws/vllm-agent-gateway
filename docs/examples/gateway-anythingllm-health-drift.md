# Gateway And AnythingLLM Health Drift Examples

Run the Phase 141 diagnostic guard from Bash:

```bash
python3 scripts/validate_gateway_anythingllm_health_drift.py \
  --timeout-seconds 45 \
  --output-path runtime-state/gateway-anythingllm-health-drift/phase141/phase141-health-drift-report.json
```

Run it from Windows while passing the AnythingLLM API key into WSL:

```powershell
$env:ANYTHINGLLM_API_KEY=[Environment]::GetEnvironmentVariable('ANYTHINGLLM_API_KEY','User')
$env:WSLENV='ANYTHINGLLM_API_KEY/u'
wsl.exe --cd /mnt/c/agentic_agents -- python3 scripts/validate_gateway_anythingllm_health_drift.py `
  --timeout-seconds 45 `
  --output-path runtime-state/gateway-anythingllm-health-drift/phase141/phase141-health-drift-report.json
```

Inspect failure kinds:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/gateway-anythingllm-health-drift/phase141/phase141-health-drift-report.json").read_text())
print(json.dumps(report["summary"]["kind_counts"], indent=2, sort_keys=True))
for finding in report["findings"]:
    print(f"{finding['kind']}: {finding['check_id']} -> {finding['next_action']}")
PY
```

Expected pass shape:

```json
{
  "status": "passed",
  "summary": {
    "finding_count": 0,
    "unclassified_finding_count": 0
  }
}
```
