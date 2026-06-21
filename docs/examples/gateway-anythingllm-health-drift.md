# Gateway And AnythingLLM Health Drift Examples

Run the Phase 141 diagnostic guard from Bash:

```bash
python3 scripts/validate_gateway_anythingllm_health_drift.py \
  --timeout-seconds 45 \
  --output-path runtime-state/gateway-anythingllm-health-drift/phase141/phase141-health-drift-report.json
```

Run it from Windows while passing the AnythingLLM API key into WSL:

```powershell
$key=$env:ANYTHINGLLM_API_KEY
if (-not $key) { throw 'ANYTHINGLLM_API_KEY is not set in Windows environment' }
wsl.exe --cd /mnt/c/agentic_agents -- env "ANYTHINGLLM_API_KEY=$key" python3 scripts/validate_gateway_anythingllm_health_drift.py `
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
    if finding.get("recovery_command"):
        print("  recovery:", finding["recovery_command"])
    if finding.get("powershell_wsl_env_example"):
        print("  key bridge:", finding["powershell_wsl_env_example"])
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

Expected wrong API-base drift shape when port `3001` is serving a non-AnythingLLM app:

```json
{
  "status": "failed",
  "summary": {
    "kind_counts": {
      "wrong_backend_target": 3
    },
    "unclassified_finding_count": 0
  }
}
```

The three findings should map to `anythingllm.ping`, `anythingllm.workspace`, and `anythingllm.target_url`. This means the local model and workflow-router gateway can still be evaluated separately; AnythingLLM prompt testing is blocked until the API base points at the real AnythingLLM API.

Rerun against the reachable network API base:

```powershell
$env:WSLENV='ANYTHINGLLM_API_KEY/u'
wsl bash -lc 'cd /mnt/c/agentic_agents && . .venv/bin/activate && python scripts/validate_gateway_anythingllm_health_drift.py --anythingllm-api-base-url http://192.168.0.208:3001 --expected-anythingllm-llm-base-url http://100.100.12.45:8500/v1'
```

Expected recovered shape:

```json
{
  "status": "passed",
  "summary": {
    "finding_count": 0,
    "unclassified_finding_count": 0
  }
}
```
