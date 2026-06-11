# First-Time User Doctor

The first-time user doctor checks the local setup before a tester runs natural-language prompts through AnythingLLM.

It is a preflight tool, not an acceptance suite. It does not send coding prompts, run model evaluations, mutate fixtures, or apply changes.

## What It Checks

- vLLM `/v1/models` on `8000`
- ordinary model gateway on `8300`
- workflow-router gateway on `8500`
- controller `/health` on `8400`
- role proxy ports from `runtime/roles.json`
- gateway routing configuration
- controller allowed roots
- AnythingLLM API key availability
- AnythingLLM workspace presence
- AnythingLLM `GenericOpenAiBasePath`, when exposed by `/api/v1/system`
- protected fixture manifest and watched-file hashes
- git cleanliness or line-ending-only warning status for git-enabled protected fixtures

## Run

From Windows PowerShell into WSL:

```powershell
$key=$env:ANYTHINGLLM_API_KEY
if (-not $key) { throw 'ANYTHINGLLM_API_KEY is not set in Windows environment' }
wsl.exe --cd /mnt/c/agentic_agents -- env "ANYTHINGLLM_API_KEY=$key" python3 scripts/run_first_time_user_doctor.py
```

Expected markers:

```text
FIRST TIME USER DOCTOR REPORT ...
FIRST TIME USER DOCTOR SUMMARY ...
FIRST TIME USER DOCTOR PASS
```

Reports are written under:

```text
runtime-state/first-time-user-doctor/
```

## Interpreting Results

Start with:

```text
summary.status_counts
summary.failed_check_ids
summary.warning_check_ids
checks[].next_action
```

A warning means the doctor could not prove a non-blocking detail, usually because a third-party endpoint did not expose a setting. A failed check means first-time AnythingLLM testing is not ready.

The most common blocking failures are:

- `anythingllm.api_key`: set `ANYTHINGLLM_API_KEY` in Windows and inject it into WSL with the command shown in `checks[].details.powershell_wsl_env_example`.
- `anythingllm.target_url`: point AnythingLLM at `http://127.0.0.1:8500/v1`.
- `controller.allowed_roots`: restart the stack with the project and both frozen repos in `CONTROLLER_ALLOWED_TARGET_ROOTS`.
- `port.workflow_router_gateway`: restart the local harness from Bash.
- `fixtures.coinbase-frozen-git`: restore the git-enabled frozen fixture if content changed; line-ending-only Bash git noise is reported as a warning.

## Safety

- Reads health endpoints and local fixture metadata only.
- Does not invoke workflow-router prompts.
- Does not mutate source, fixtures, skills, or registry files.
- Does not replace the full V1 acceptance gate.
