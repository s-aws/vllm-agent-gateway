# AnythingLLM UI E2E Examples

## Full UI Proof

Run from PowerShell after the harness is started and AnythingLLM is pointed at `http://127.0.0.1:8500/v1`:

```powershell
$env:ANYTHINGLLM_API_KEY=[Environment]::GetEnvironmentVariable('ANYTHINGLLM_API_KEY','User')
python scripts\validate_anythingllm_ui_e2e.py `
  --anythingllm-api-base-url http://127.0.0.1:3001 `
  --workspace my-workspace `
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp `
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github `
  --timeout-seconds 420 `
  --output-path runtime-state\anythingllm-ui\manual-ui-e2e.json
```

The report should include:

- `status=passed`
- one case per target root
- `stream_chat_seen=true`
- marker hits for `workflow_router.plan completed`, `selected_workflow: code_investigation.plan`, `run_id:`, and `Answer:`
- semantic marker hits for the submitted case, such as `Beginning point:`, `Related tests:`, and `Recommended commands:` for `L1-001`
- no rejected markers, such as `Entrypoints:` for the `L1-001` behavior-start case
- `fixture_unchanged=true`
- before/after screenshots for each prompt

## Reuse An Extracted UI Bundle

If `runtime-state/anythingllm-ui/asar-dist/dist` already exists, the validator reuses it by default.

To force a fresh extraction:

```powershell
python scripts\validate_anythingllm_ui_e2e.py --refresh-extract
```

To point at a known extracted `dist` directory:

```powershell
python scripts\validate_anythingllm_ui_e2e.py `
  --ui-dist-root runtime-state\anythingllm-ui\asar-dist\dist
```

## Common Failures

`Python Playwright is not installed`

Run:

```powershell
pip install playwright
```

`Executable doesn't exist`

The Python package is installed, but the selected Playwright browser is not. Install bundled Chromium with `python -m playwright install chromium`, or pass a working system channel such as `--browser-channel chrome` from Windows.

`npx was not found`

Install Node.js/npm or pass `--npx-command` to a working `npx` executable.

`AnythingLLM preflight failed`

Check that AnythingLLM Desktop is running on `http://127.0.0.1:3001`, the API key is correct, and the workspace slug exists.

`AnythingLLM browser UI validation failed`

Open the JSON report and screenshots under `runtime-state/anythingllm-ui/`. Check `page_errors`, `non_ignored_request_failures`, `responses_tail`, and the per-case `segment_after_tag_tail`.
