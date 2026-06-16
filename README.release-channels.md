# Release Channels

Release channels define which validation path a tester should trust before using the local harness through AnythingLLM.

The source of truth is:

```text
runtime/release_channels.json
```

The validator is:

```bash
python scripts/validate_release_channels.py
```

It is read-only except for writing a report under `runtime-state/release-channels/`.

Generated `runtime-state/` reports are local-only. Durable release proof metadata belongs under `runtime/release_proofs/`; see [README.runtime-state.md](README.runtime-state.md).

## Channels

- `dev`: maintainer channel for fast local iteration and setup readiness.
- `release-candidate`: tester channel for current V1-style founder testing through the workflow-router gateway, AnythingLLM, and both frozen Coinbase fixtures.
- `stable`: active external-tester channel promoted from the passed V1.1 release-candidate report and refreshed for governed 500k-token project usability.

Use `stable` for the current documented tester path after the stable handoff smoke passes. Use `release-candidate` when validating new changes before another stable promotion.

## Validate Channel Metadata

From the project root:

```bash
python scripts/validate_release_channels.py \
  --output-path runtime-state/release-channels/current.json
```

Expected markers:

```text
RELEASE CHANNEL REPORT ...
RELEASE CHANNEL SUMMARY ...
RELEASE CHANNEL PASS
```

The report includes:

- harness and component versions
- channel IDs
- required docs, examples, runtime files, ports, env vars, and fixtures
- setup validator command
- acceptance validator command
- stable readiness status
- runtime-state hygiene status for ignored generated reports and committed proof metadata

## First-Time Tester Path

From Bash:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/run_first_time_user_doctor.py
```

If the doctor passes, run the release-candidate acceptance gate:

```bash
python3 scripts/validate_v1_acceptance.py \
  --profile v1.1-release-candidate \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github
```

The V1.1 profile includes setup doctor, docs-index, release-channel, security policy, workflow, AnythingLLM, JSON output, feedback, observability, model-probe, and protected-fixture proof in one report.

AnythingLLM must point at:

```text
http://127.0.0.1:8500/v1
```

The release-candidate acceptance gate includes the external tester onboarding live prompt and linked feedback proof.

Before broader tester distribution, also run the security policy gate:

```bash
python3 scripts/validate_security_policy.py \
  --output-path runtime-state/security-policy/release-candidate.json
```

That gate checks secret exposure, filesystem boundaries, protected fixture policy, command fragments, and onboarding prompt safety. See [README.security-policy.md](README.security-policy.md).

## Stable Readiness

Stable may only be marked active after a release-candidate acceptance report passes. Because `runtime-state/` is local-only, the current committed activation proof is:

```text
runtime/release_proofs/v1-1-release-candidate-stable-proof.json
```

When stable is active, validate it with:

```bash
python scripts/validate_release_channels.py \
  --channel stable \
  --release-candidate-report runtime/release_proofs/v1-1-release-candidate-stable-proof.json
```

The supplied report must contain:

- `kind=v1_acceptance_report`
- `status=passed`
- `profile=release-candidate` or `profile=v1.1-release-candidate`

For the current large-context product target, stable also relies on the Phase 276 500k decision gate and the Phase 277 handoff refresh. Phase 276 must return `decision=ship` with `phase277_ready=true`, and Phase 277 must return `stable_500k_handoff_refreshed`, before stable handoff text is treated as current for 500k testing. The 384k-token project usability baseline remains preserved as lineage.

Run the full stable handoff smoke before sending testers to the stable channel:

```bash
python3 scripts/validate_stable_handoff.py \
  --release-candidate-report runtime/release_proofs/v1-1-release-candidate-stable-proof.json \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github
```

See [README.stable-handoff.md](README.stable-handoff.md).

## Rollback

For setup failures:

```bash
bash stop-agent-prompt-proxies.sh
bash start-agent-prompt-proxies.sh
```

Then rerun:

```bash
python3 scripts/run_first_time_user_doctor.py
```

If AnythingLLM was changed, set the Generic OpenAI base URL back to `http://127.0.0.1:8500/v1`.

If a frozen fixture check fails, inspect the fixture state before running more live tests. Protected fixture source files should remain unchanged during release-channel validation.

Examples: [docs/examples/release-channels.md](docs/examples/release-channels.md).
