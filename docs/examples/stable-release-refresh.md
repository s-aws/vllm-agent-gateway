# Stable Release Refresh Examples

Run from Bash/WSL.

## Run The Live Refresh

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_stable_release_refresh.py \
  --policy-path runtime/stable_release_refresh_phase170_policy.json \
  --run-refresh \
  --execute-reset-start \
  --execute-recovery \
  --output-path runtime-state/stable-release-refresh/phase170/phase170-stable-release-refresh-report.json \
  --markdown-output-path runtime-state/stable-release-refresh/phase170/phase170-stable-release-refresh-report.md
```

Expected marker:

```text
PHASE170 STABLE RELEASE REFRESH PASS
```

## Inspect The Refresh Summary

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/stable-release-refresh/phase170/phase170-stable-release-refresh-report.json").read_text())
print(report["status"], report["readiness"], report["decision"])
print(report["summary"])
for item in report["refresh_results"]:
    print(item["id"], item["returncode"])
    print(item["outputs"])
PY
```

## Expected Current Result

The current release path should show:

```text
status=passed
readiness=ready_for_founder_testing
decision=release_for_founder_testing
phase159_repair_mode=no_repair_required
model_ids=["Qwen3-Coder-30B-A3B-Instruct"]
phase169_proposal_count=6
phase169_release_blocker_count=0
```

## Failure Review

If Phase 170 fails, inspect:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/stable-release-refresh/phase170/phase170-stable-release-refresh-report.json").read_text())
for error in report["validation_errors"]:
    print(error["id"], error["source"], error["message"])
for command in report["refresh_results"]:
    if command["returncode"] != 0:
        print(command["id"])
        print(command["stdout_tail"])
        print(command["stderr_tail"])
    for output in command.get("outputs", []):
        if not output.get("exists") or not output.get("sha256"):
            print("bad output", command["id"], output)
PY
```
