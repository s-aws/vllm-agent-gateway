# Multi-Repo Live Generalization Rerun Examples

Use these commands from Bash/WSL.

## Preflight

```bash
python3 scripts/validate_multi_repo_live_generalization_rerun.py
```

The default preflight report is written separately from the live closeout report.

## Gateway-Only Holdout Smoke

```bash
python3 scripts/validate_multi_repo_live_generalization_rerun.py --live --allow-partial \
  --skip-anythingllm \
  --case-id P212-HO-CB-GIT-001
```

## Full Live Gate

Make sure the local model, gateway/proxies, controller, and AnythingLLM are running. Then run:

```bash
python3 scripts/validate_multi_repo_live_generalization_rerun.py --live --timeout-seconds 900
```

When running from Windows and the API key is stored in the Windows environment, export it into WSL:

```powershell
$env:WSLENV='ANYTHINGLLM_API_KEY/u'
wsl.exe --cd /mnt/c/agentic_agents -- bash -lc "python3 scripts/validate_multi_repo_live_generalization_rerun.py --live --timeout-seconds 900"
```

## Report Review

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase212/phase212-multi-repo-live-generalization-rerun-report.json").read_text())
print(report["status"], report["summary"])
for item in report.get("responses", []):
    print(item["surface"], item["case_id"], item["score"], item["gap_classes"], item["run_id"])
PY
```
