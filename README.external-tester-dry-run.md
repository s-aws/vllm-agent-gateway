# External Tester Dry Run

Phase 147 validates the smallest current path for a contextless external tester.

It does not create a new workflow. It wraps the existing stable release-channel validator, first-time user doctor, release-notes validator, external onboarding pack validator, and one live AnythingLLM onboarding prompt with linked feedback.

## When To Use

Use this before asking a new tester to run broader founder-field, L1/L2, UI, or V1 acceptance suites.

The dry run proves:

- the current tester channel is `stable`
- public docs name one minimum path
- AnythingLLM is expected at `http://127.0.0.1:3001`
- AnythingLLM routes workflow testing to `http://127.0.0.1:8500/v1`
- `ANYTHINGLLM_API_KEY` is available for API validation
- setup doctor passes for localhost `8000`, `8300`, `8400`, `8500`, role ports, AnythingLLM, and both frozen fixtures
- `ONB-001` returns chat-visible answer content
- linked feedback capture works
- protected frozen fixtures remain unchanged

## Run

Run from Bash/WSL:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_external_tester_dry_run.py \
  --live-runtime \
  --include-feedback \
  --output-path runtime-state/external-tester-dry-run/phase147/phase147-external-tester-dry-run.json
```

Expected marker:

```text
EXTERNAL TESTER DRY RUN PASS
```

## Output

Primary report:

```text
runtime-state/external-tester-dry-run/phase147/phase147-external-tester-dry-run.json
```

Child reports are written under:

```text
runtime-state/external-tester-dry-run/phase147/children/
```

## Boundaries

Advanced broad refactor orchestration is not released.

Do not use broad refactor, approval continuation, disposable-copy apply, or mutation-capable prompts in first external tester onboarding.

Examples: [docs/examples/external-tester-dry-run.md](docs/examples/external-tester-dry-run.md).
