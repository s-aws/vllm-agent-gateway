# Productized Setup Examples

These examples use `scripts/run_productized_setup.py`, the single command surface for local harness setup and recovery.

## Plan Everything

```bash
cd /mnt/c/agentic_agents
python3 scripts/run_productized_setup.py plan \
  --output-path runtime-state/productized-setup/plan.json
```

Expected markers:

- `PRODUCTIZED SETUP REPORT ...`
- `PRODUCTIZED SETUP SUMMARY ...`
- `PRODUCTIZED SETUP PASS`

## Start

```bash
python3 scripts/run_productized_setup.py start --execute \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --output-path runtime-state/productized-setup/start.json
```

This runs the existing `start-agent-prompt-proxies.sh` with:

- `CONTROLLER_ALLOWED_TARGET_ROOTS` including the project root and both frozen fixtures
- `CONTROLLER_DEFAULT_ROLE_BASE_URL=http://127.0.0.1:8300/v1`

## Validate

```bash
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/run_productized_setup.py validate --execute \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --output-path runtime-state/productized-setup/validate.json
```

This runs:

- first-time user doctor
- release-channel validation
- security policy validation

## Reset

```bash
python3 scripts/run_productized_setup.py reset --execute \
  --output-path runtime-state/productized-setup/reset.json
```

The reset action only stops the harness through `stop-agent-prompt-proxies.sh`. It does not delete artifacts, source files, or frozen fixtures.

## Rerun Stable Smoke

```bash
python3 scripts/run_productized_setup.py rerun --execute \
  --release-candidate-report runtime/release_proofs/v1-1-release-candidate-stable-proof.json \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --output-path runtime-state/productized-setup/rerun-stable.json
```

This runs the existing stable handoff smoke and records child report paths.

## Failure Guidance

If a report fails, inspect `summary.failed_check_ids` and `failure_guidance`.

Common mappings:

- `port.*`: reset, confirm `8000/v1/models`, then start.
- `anythingllm.api_key`: expose `ANYTHINGLLM_API_KEY` to Bash.
- `anythingllm.target_url`: point AnythingLLM to `http://127.0.0.1:8500/v1`.
- `controller.allowed_roots`: restart with project and fixture roots in `CONTROLLER_ALLOWED_TARGET_ROOTS`.
- `fixtures.*`: stop prompt testing and inspect fixture snapshots.
