# Evidence Boundary Schema Gate Examples

## Regression Gate

```bash
python3 -m pytest tests/regression/test_chat_response_contract.py tests/regression/test_fixture_manager.py -q
```

This proves malformed governed artifacts render `Evidence Boundary Gate:` instead of normal answer text.

## Live Target And Holdout Gate

From Windows PowerShell:

```powershell
$key=$env:ANYTHINGLLM_API_KEY
if (-not $key) { throw 'ANYTHINGLLM_API_KEY is not set in Windows environment' }
wsl.exe --cd /mnt/c/agentic_agents -- env "ANYTHINGLLM_API_KEY=$key" python3 scripts/validate_multi_repo_fixtures_live.py `
  --port-health `
  --live-anythingllm `
  --case-id coinbase-schema-lookup `
  --case-id coinbase-git-schema-lookup `
  --case-id python-service-schema-lookup `
  --case-id coinbase-change-surface `
  --case-id coinbase-git-change-surface `
  --case-id python-service-change-surface `
  --timeout-seconds 900 `
  --output-path runtime-state/evidence-boundary-schema-gate/phase189-live-report.json
```

Expected summary:

```json
{
  "case_count": 6,
  "client_case_count": 12,
  "clients": ["anythingllm", "gateway"],
  "error_count": 0,
  "prompt_family_count": 2
}
```

Inspect boundary status:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/evidence-boundary-schema-gate/phase189-live-report.json").read_text())
for case in report["cases"]:
    print(case["client"], case["case_id"], case.get("evidence_boundary_status"), case.get("evidence_boundary_error_count"))
PY
```

Every schema and change-surface case should report `passed` and `0`.

## Failure Shape

A malformed governed artifact should produce:

```text
Evidence Boundary Gate:
- Evidence boundary status: failed
- Artifact: data_model_lookup
- Blocking issues: ...
- Next action: repair the controller artifact evidence boundary before accepting this chat answer
```

That failure is intentional. Do not work around it with prompt wording; repair the controller artifact evidence.
