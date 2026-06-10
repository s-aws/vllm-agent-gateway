# Stable Release Reset Rehearsal

Phase 153 proves the stable local testing path can be reset and recovered without deleting real `runtime-state`, changing source files, or mutating the protected frozen Coinbase fixtures.

Use this when a founder or tester needs to rehearse the stable recovery path before continuing AnythingLLM field testing.

## What It Checks

- `runtime-state/` remains local-only, ignored, and untracked.
- Productized reset uses the existing `stop-agent-prompt-proxies.sh` path.
- Productized start uses `start-agent-prompt-proxies.sh` with both frozen target roots in the controller allowlist.
- A disposable runtime-state rehearsal path can be cleared and regenerated.
- The stable recovery proof uses the existing productized `rerun` path, which calls stable handoff.
- Watched source files, git source snapshot, and protected fixture state are unchanged before and after rehearsal.

The gate distinguishes repo-local generated reports under `runtime-state/` from process/log/PID state managed by the harness scripts. The rehearsal must not delete the real repo-local `runtime-state/` tree.

## Dry Rehearsal

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_stable_release_reset_rehearsal.py \
  --output-path runtime-state/stable-release-reset-rehearsal/phase153/phase153-dry-report.json
```

Dry rehearsal validates the reset/start/rerun command plan and disposable runtime-state proof without stopping or starting the live harness.

## Live Rehearsal

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

Live rehearsal stops the harness through the productized reset command, starts it again through the productized start command, and runs productized stable handoff recovery through the existing `rerun` command.

## Output

The report includes:

- `checks[]`: policy, runtime-state hygiene, command contract, disposable rehearsal, reset/start execution, stable handoff recovery, fixture preservation, and source preservation.
- `summary.failed_check_ids`: exact blocker IDs.
- child report paths for runtime-state hygiene, productized reset/start, and productized rerun.

The report passes only when all checks pass.

## Safety Boundaries

This feature is a rehearsal gate, not a new reset implementation. It must not add another reset path.

Forbidden reset behavior includes broad deletion, `git reset`, `git checkout`, deleting real `runtime-state`, mutating protected fixtures, or relying on ignored historical reports for stable recovery.

See examples in [docs/examples/stable-release-reset-rehearsal.md](docs/examples/stable-release-reset-rehearsal.md).
