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

Run this before handing the stable channel to testers. The current stable activation proof is committed under `runtime/release_proofs/` because `runtime-state/` is local-only.

```bash
python3 scripts/validate_release_channels.py \
  --channel stable \
  --release-candidate-report runtime/release_proofs/v1-1-release-candidate-stable-proof.json \
  --output-path runtime-state/release-channels/stable-readiness.json
```

Expected result:

```text
RELEASE CHANNEL PASS
```

If the report fails, stop stable handoff and continue using `release-candidate` until the failed check is fixed.

## Run Stable Handoff Smoke

```bash
python3 scripts/validate_stable_handoff.py \
  --release-candidate-report runtime/release_proofs/v1-1-release-candidate-stable-proof.json \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --output-path runtime-state/stable-handoff/stable-smoke.json
```

Expected result:

```text
STABLE HANDOFF PASS
```
