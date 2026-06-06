# AnythingLLM UI E2E

This validator proves the browser-visible AnythingLLM Desktop chat path, not only the AnythingLLM workspace API.

AnythingLLM Desktop exposes its backend API on `http://127.0.0.1:3001`, but the Desktop UI is packaged inside `app.asar` instead of being served from that port. The validator extracts or reuses the packaged UI bundle, serves it locally with `http-server`, injects the minimal Electron renderer startup shim, opens it with Playwright and system Chrome, and sends natural-language prompts through the real AnythingLLM backend.

## What This Proves

- the Desktop UI bundle renders in a browser automation context
- the UI receives the same backend API base that Desktop normally receives from Electron
- the UI submits through AnythingLLM `/stream-chat`
- AnythingLLM reaches the workflow-router gateway configured at `http://127.0.0.1:8500/v1`
- chat-visible output contains workflow-router markers after the new prompt tag, not from stale history
- both frozen Coinbase fixtures remain unchanged
- screenshots and JSON proof are written for review

## Prerequisites

- AnythingLLM Desktop is installed and running.
- AnythingLLM is configured to use `http://127.0.0.1:8500/v1`.
- `ANYTHINGLLM_API_KEY` is available in the Windows user environment.
- Python Playwright is installed: `pip install playwright`.
- System Chrome is installed. The validator uses Playwright channel `chrome`.
- Node/npm `npx` is available. The validator uses `npx asar` when extraction is needed and `npx http-server` for the static UI bundle.

## Run

From PowerShell:

```powershell
$env:ANYTHINGLLM_API_KEY=[Environment]::GetEnvironmentVariable('ANYTHINGLLM_API_KEY','User')
python scripts\validate_anythingllm_ui_e2e.py `
  --anythingllm-api-base-url http://127.0.0.1:3001 `
  --workspace my-workspace `
  --timeout-seconds 420
```

Expected final marker:

```text
ANYTHINGLLM UI E2E PASS
```

Reports and screenshots are written under:

```text
runtime-state/anythingllm-ui/
```

## Safety

The validator sends read-only L1 investigation prompts to both frozen fixtures:

- `/mnt/c/coinbase_testing_repo_frozen_tmp`
- `/mnt/c/coinbase_testing_repo_frozen_tmp.github`

It records watched-file hashes and git status before and after the UI run. The run fails if protected fixture state changes.

## Notes

Run this from Windows PowerShell, not Bash. The gateway/controller runtime remains Bash-hosted, but this specific proof targets the Windows Desktop UI bundle and system Chrome.

See [docs/examples/anythingllm-ui-e2e.md](docs/examples/anythingllm-ui-e2e.md) for commands and troubleshooting.
