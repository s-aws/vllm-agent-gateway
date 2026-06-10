# Prompt Advisory Closure Examples

Run Phase 165 after Phase 164 reports `PHASE164 FOUNDER FIELD ROUND 2 PASS`.

## PowerShell To WSL

```powershell
$env:ANYTHINGLLM_API_KEY=[Environment]::GetEnvironmentVariable('ANYTHINGLLM_API_KEY','User')
$env:WSLENV='ANYTHINGLLM_API_KEY/u'
wsl.exe --cd /mnt/c/agentic_agents -- python3 scripts/validate_prompt_advisory_closure.py --run-live `
  --timeout-seconds 900 `
  --output-path runtime-state/prompt-advisory-closure/phase165/phase165-prompt-advisory-closure-report.json `
  --markdown-output-path runtime-state/prompt-advisory-closure/phase165/phase165-prompt-advisory-closure-report.md
```

Expected marker:

```text
PHASE165 PROMPT ADVISORY CLOSURE PASS
```

## Bash

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_prompt_advisory_closure.py --run-live \
  --timeout-seconds 900 \
  --output-path runtime-state/prompt-advisory-closure/phase165/phase165-prompt-advisory-closure-report.json \
  --markdown-output-path runtime-state/prompt-advisory-closure/phase165/phase165-prompt-advisory-closure-report.md
```

## Inspect The Report

```bash
python3 - <<'PY'
import json
from pathlib import Path

path = Path("runtime-state/prompt-advisory-closure/phase165/phase165-prompt-advisory-closure-report.json")
report = json.loads(path.read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
for record in report["closure_records"]:
    print(record["case_id"], record["decision"], record["refined_score"], record["refined_run_id"])
PY
```
