# Productized Setup

`scripts/run_productized_setup.py` is the single command surface for first-time local harness setup and recovery.

It does not create a new runtime path. It plans or runs the existing scripts and validators:

- `start-agent-prompt-proxies.sh`
- `stop-agent-prompt-proxies.sh`
- `scripts/run_first_time_user_doctor.py`
- `scripts/validate_release_channels.py`
- `scripts/validate_security_policy.py`
- `scripts/validate_stable_handoff.py`
- `scripts/validate_runtime_recovery_reliability_rebaseline.py`

## Actions

Use `plan` first. It writes the full command sequence without executing it.

```bash
python3 scripts/run_productized_setup.py plan
```

The supported actions are:

- `install`: verify package import and required setup scripts.
- `start`: start the gateway, workflow-router gateway, controller service, and role proxies.
- `validate`: run setup doctor, release-channel validation, and security policy validation.
- `reset`: stop the local harness through the existing stop script. This does not delete artifacts or fixtures.
- `rerun`: rerun stable handoff smoke after reset/start.

Add `--execute` to run an action:

```bash
python3 scripts/run_productized_setup.py validate --execute
```

## AnythingLLM Target

For natural workflow testing, AnythingLLM must point to:

```text
http://127.0.0.1:8500/v1
```

Use `8300/v1` only for ordinary model/gateway chat. Do not use `8400`; it is the controller HTTP API, not an OpenAI-compatible model endpoint.

## Reset Guidance

Use reset when:

- a port check fails
- AnythingLLM gets stale gateway behavior
- controller roots were started incorrectly
- a PID file points at a dead process

Reset command:

```bash
python3 scripts/run_productized_setup.py reset --execute
```

Then start again:

```bash
python3 scripts/run_productized_setup.py start --execute
```

For runtime recovery reliability after a reboot or gateway/model restart, run the Phase 231 gate:

```bash
python3 scripts/validate_runtime_recovery_reliability_rebaseline.py \
  --restart-managed-stack \
  --restart-vllm-container vllm-qwen3 \
  --timeout-seconds 900
```

This proves the restart path and post-recovery chat validation, not just open ports.

## Reports

Each action writes a JSON report under:

```text
runtime-state/productized-setup/
```

Reports include:

- planned commands
- required files
- execution results when `--execute` is used
- failure guidance for ports, AnythingLLM API key, AnythingLLM target URL, controller roots, and protected fixtures

## References

- Examples: [docs/examples/productized-setup.md](docs/examples/productized-setup.md)
- Getting started: [README.getting-started.md](README.getting-started.md)
- Setup doctor: [README.first-time-user-doctor.md](README.first-time-user-doctor.md)
- Stable handoff: [README.stable-handoff.md](README.stable-handoff.md)
