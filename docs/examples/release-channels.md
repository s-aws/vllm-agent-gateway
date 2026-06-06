# Release Channel Examples

## Validate Current Channel Metadata

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_release_channels.py \
  --output-path runtime-state/release-channels/current.json
```

Expected result:

```text
RELEASE CHANNEL PASS
```

## Validate Release Candidate Setup

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/run_first_time_user_doctor.py \
  --output-path runtime-state/first-time-user-doctor/release-candidate-setup.json
```

Expected result:

```text
FIRST TIME USER DOCTOR PASS
```

## Run Release Candidate Acceptance

```bash
python3 scripts/validate_v1_acceptance.py \
  --profile v1.1-release-candidate \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --output-path runtime-state/v1-acceptance/release-candidate.json
```

Expected result:

```text
V1 ACCEPTANCE PASS
```

The report profile should be `v1.1-release-candidate`.

## Prove Stable Readiness

Only run this after the release-candidate acceptance report passed and `runtime/release_channels.json` marks `stable` as `active`.

```bash
python3 scripts/validate_release_channels.py \
  --channel stable \
  --release-candidate-report runtime-state/v1-acceptance/release-candidate.json \
  --output-path runtime-state/release-channels/stable-readiness.json
```

Expected result:

```text
RELEASE CHANNEL PASS
```

If the report fails, keep `stable` blocked and continue using `release-candidate`.
