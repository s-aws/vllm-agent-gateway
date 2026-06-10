# Founder Field Round 2 Examples

Run Phase 164 after Phase 163 reports `decision=ready_after_restart`.

## PowerShell To WSL

```powershell
$env:ANYTHINGLLM_API_KEY=[Environment]::GetEnvironmentVariable('ANYTHINGLLM_API_KEY','User')
$env:WSLENV='ANYTHINGLLM_API_KEY/u'
wsl.exe --cd /mnt/c/agentic_agents -- python3 scripts/validate_founder_field_round2.py --run-live `
  --timeout-seconds 900 `
  --output-path runtime-state/founder-field-round2/phase164/phase164-founder-field-round2-report.json `
  --markdown-output-path runtime-state/founder-field-round2/phase164/phase164-founder-field-round2-report.md
```

Expected marker:

```text
PHASE164 FOUNDER FIELD ROUND 2 PASS
```

## Bash

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_founder_field_round2.py --run-live \
  --timeout-seconds 900 \
  --output-path runtime-state/founder-field-round2/phase164/phase164-founder-field-round2-report.json \
  --markdown-output-path runtime-state/founder-field-round2/phase164/phase164-founder-field-round2-report.md
```

## Inspect The Report

```bash
python3 - <<'PY'
import json
from pathlib import Path

path = Path("runtime-state/founder-field-round2/phase164/phase164-founder-field-round2-report.json")
report = json.loads(path.read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
for case in report["case_evidence"]:
    print(case["case_id"], case["quality_classification"], case["score"], case["response_artifact_path"])
PY
```

Passing evidence summary shape:

```json
{
  "case_count": 16,
  "phase165_required": true,
  "phase169_required": false,
  "validation_error_count": 0
}
```
