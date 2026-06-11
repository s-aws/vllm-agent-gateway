# AnythingLLM UI E2E

This validator proves the browser-visible AnythingLLM Desktop chat path, not only the AnythingLLM workspace API.

AnythingLLM Desktop exposes its backend API on `http://127.0.0.1:3001`, but the Desktop UI is packaged inside `app.asar` instead of being served from that port. The validator extracts or reuses the packaged UI bundle, serves it locally with Python's static server, injects the minimal Electron renderer startup shim, opens it with Playwright, and sends natural-language prompts through the real AnythingLLM backend.

## What This Proves

- the Desktop UI bundle renders in a browser automation context
- the UI receives the same backend API base that Desktop normally receives from Electron
- the UI submits through AnythingLLM `/stream-chat`
- AnythingLLM reaches the workflow-router gateway configured at `http://127.0.0.1:8500/v1`
- chat-visible output contains workflow-router markers after the new prompt tag, not from stale history
- chat-visible output passes case-specific semantic markers for the submitted prompt family
- stable Priority 0 UI cases pass the same answer-usefulness contract used by the API-level chat-quality gate
- generic and vague no-target prompts, such as `hi`, `what can you do?`, and `find the bug`, remain useful and do not start repository workflows
- known wrong-answer markers, such as an `Entrypoints:` answer for the `L1-001` behavior-start prompt, are rejected
- both frozen Coinbase fixtures remain unchanged
- screenshots and JSON proof are written for review

## Prerequisites

- AnythingLLM Desktop is installed and running.
- AnythingLLM is configured to use `http://127.0.0.1:8500/v1`.
- `ANYTHINGLLM_API_KEY` is available in the Windows user environment.
- Python Playwright is installed: `pip install playwright`.
- A Playwright browser is installed. The default uses bundled Chromium; run `python -m playwright install chromium` if needed.
- Node/npm `npx` is available only when extraction is needed. The validator uses `npx asar` to extract `app.asar`; serving the static UI bundle does not require `npx`.

## Run

From PowerShell:

```powershell
$env:ANYTHINGLLM_API_KEY=[Environment]::GetEnvironmentVariable('ANYTHINGLLM_API_KEY','User')
python scripts\validate_anythingllm_ui_e2e.py `
  --anythingllm-api-base-url http://127.0.0.1:3001 `
  --workspace my-workspace `
  --prompt-catalog-path runtime\anythingllm_ui_prompt_cases.json `
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

The validator sends read-only prompts to the frozen fixtures. The governed prompt catalog is:

```text
runtime/anythingllm_ui_prompt_cases.json
```

The catalog includes the original L1 smoke cases:

- `L1-001`: behavior-start lookup for the `placed_order_id` stealth lookup
- `L1-002`: function explanation for `find_stealth_order_by_placed_order_id`

Phase 126 adds stable Priority 0 UI cases:

- code quality and self-review, one case per frozen fixture
- defect diagnosis, one case per frozen fixture
- engineering judgment, one case per frozen fixture
- delivery mentorship, one case per frozen fixture

Phase 167 adds no-target UI replay cases:

- `UI167-GENCHAT-001`: greeting guidance with `Selected workflow: none`
- `UI167-GENHELP-001`: coding-agent capability guidance without a repository target
- `UI167-VAGUE-001`: vague coding prompt guidance that asks for `target_root` and refuses to start repository work

Phase 184 adds repaired Priority 0 replay cases:

- `UI184-ERR-001`: evidence relevance ranking for change-surface answers
- `UI184-RTD-001`: direct related-test discovery evidence and confidence
- `UI184-RTD-002`: honest no-bounded-test-evidence reporting

Each case records transport markers, semantic required markers, rejected markers, screenshots, parsed run ID, `/stream-chat` proof, and answer-usefulness status where applicable.

No-target cases use the same browser replay path, but they do not require `Artifacts:` because no repository workflow should start.

Phase 168 tightens those no-target cases with ordered semantic markers. `Answer:` must appear before the workflow-router status block, so the UI gate fails the older tool-log-shaped response even if all route markers are present.

The target fixtures are:

- `/mnt/c/coinbase_testing_repo_frozen_tmp`
- `/mnt/c/coinbase_testing_repo_frozen_tmp.github`

It records watched-file hashes and git status before and after the UI run. The run fails if protected fixture state changes.

## Notes

The validator can run from Bash or PowerShell when the selected Playwright browser is available. Pass `--browser-channel chrome` only when intentionally using a Windows/system Chrome channel.

See [docs/examples/anythingllm-ui-e2e.md](docs/examples/anythingllm-ui-e2e.md) for commands and troubleshooting.
