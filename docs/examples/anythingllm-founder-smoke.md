# AnythingLLM Founder Smoke Examples

## Run The Current Smoke Set

```powershell
$env:ANYTHINGLLM_API_KEY=[Environment]::GetEnvironmentVariable('ANYTHINGLLM_API_KEY','User')
$env:WSLENV='ANYTHINGLLM_API_KEY/u'
wsl.exe --cd /mnt/c/agentic_agents -- python3 scripts/run_founder_field_prompt_eval.py `
  --case-id P01 `
  --case-id P02 `
  --case-id P03 `
  --case-id P22 `
  --anythingllm-api-base-url http://127.0.0.1:3001 `
  --workspace my-workspace `
  --timeout-seconds 900 `
  --output-path runtime-state/founder-field-tests/phase134-founder-smoke.json `
  --markdown-output-path runtime-state/founder-field-tests/phase134-founder-smoke.md
```

Expected output:

```text
FIELD PROMPT P01 PASSED
FIELD PROMPT P02 PASSED
FIELD PROMPT P03 PASSED
FIELD PROMPT P22 PASSED
FOUNDER FIELD PASS
```

## Review Summary

```bash
python3 -c 'import json; from pathlib import Path; report=json.loads(Path("runtime-state/founder-field-tests/phase134-founder-smoke.json").read_text()); print(json.dumps({"status": report["status"], "summary": report["summary"], "case_ids": [case["case_id"] for case in report["cases"]], "fixture_unchanged": report["fixture_state_before"] == report["fixture_state_after"]}, indent=2, sort_keys=True))'
```

Expected current summary:

```json
{
  "case_ids": [
    "P01",
    "P02",
    "P03",
    "P22"
  ],
  "fixture_unchanged": true,
  "status": "passed",
  "summary": {
    "failed": 0,
    "passed": 4
  }
}
```
