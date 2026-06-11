# Founder Trial Execution Round Examples

Run the live founder trial through AnythingLLM:

```powershell
$key=$env:ANYTHINGLLM_API_KEY
wsl.exe --cd /mnt/c/agentic_agents -- env "ANYTHINGLLM_API_KEY=$key" `
  python3 scripts/validate_founder_trial_execution_round.py --run-live --timeout-seconds 900
```

Validate an existing field-run report without rerunning prompts:

```bash
python3 scripts/validate_founder_trial_execution_round.py
```

Inspect case outcomes:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase197/phase197-founder-trial-execution-round-report.json").read_text())
print(report["status"], report["quality_status"])
for case in report["case_results"]:
    print(case["case_id"], case["quality_classification"], case["run_id"], case["initial_difference"])
PY
```

Inspect full response artifacts:

```bash
find runtime-state/phase197/phase197-founder-trial-execution-run/responses -type f -maxdepth 1 -print
```
