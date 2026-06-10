# Stable Release Reset Rehearsal Examples

Run these from Bash/WSL.

## Plan-Safe Dry Run

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_stable_release_reset_rehearsal.py \
  --output-path runtime-state/stable-release-reset-rehearsal/phase153/phase153-dry-report.json
```

Expected markers:

- `STABLE RELEASE RESET REHEARSAL REPORT ...`
- `STABLE RELEASE RESET REHEARSAL SUMMARY ...`
- `STABLE RELEASE RESET REHEARSAL PASS`

The dry run does not stop or start the live harness.

## Live Reset And Recovery

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_stable_release_reset_rehearsal.py \
  --execute-reset-start \
  --execute-recovery \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --output-path runtime-state/stable-release-reset-rehearsal/phase153/phase153-live-report.json
```

This uses:

- productized `reset --execute`
- productized `start --execute`
- productized `rerun --execute`, which invokes stable handoff

## Inspect Failures

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/stable-release-reset-rehearsal/phase153/phase153-live-report.json").read_text())
print(report["status"])
print(report["summary"]["failed_check_ids"])
for check in report["checks"]:
    if check["status"] == "failed":
        print(check["id"], check["next_action"])
PY
```

## Safety Confirmation

```bash
git ls-files runtime-state
git check-ignore -v runtime-state/stable-release-reset-rehearsal/phase153/phase153-live-report.json
```

`git ls-files runtime-state` should print nothing. `git check-ignore -v ...` should show the ignore rule.
