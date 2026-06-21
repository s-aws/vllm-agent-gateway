# AnythingLLM UI E2E Examples

## Full UI Proof

Run from PowerShell after the harness is started, AnythingLLM is pointed at `http://127.0.0.1:8500/v1`, and the workspace chat mode is `chat`:

```powershell
$env:ANYTHINGLLM_API_KEY=[Environment]::GetEnvironmentVariable('ANYTHINGLLM_API_KEY','User')
python scripts\validate_anythingllm_ui_e2e.py `
  --anythingllm-api-base-url http://127.0.0.1:3001 `
  --workspace my-workspace `
  --prompt-catalog-path runtime\anythingllm_ui_prompt_cases.json `
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

## Current Bash/WSL Split-Address Replay

Use this shape when the validator runs from Bash/WSL and AnythingLLM is reachable from Bash on the Windows host network address:

```bash
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_anythingllm_ui_e2e.py \
  --anythingllm-api-base-url http://192.168.0.208:3001 \
  --workspace my-workspace \
  --ui-dist-root runtime-state/anythingllm-ui/asar-dist/dist \
  --timeout-seconds 900 \
  --output-path runtime-state/anythingllm-ui/phase335/phase335-priority0-ui-replay.json \
  --case-id UI126-CQ116-001 \
  --case-id UI126-CQ116-009 \
  --case-id UI126-DD117-001 \
  --case-id UI126-DD117-002 \
  --case-id UI126-EJ118-001 \
  --case-id UI126-EJ118-002 \
  --case-id UI126-DM119-001 \
  --case-id UI126-DM119-002 \
  --case-id UI167-GENCHAT-001
```

Expected result:

```text
ANYTHINGLLM UI E2E PASS
```

## Phase 126 Stable Corpus UI Subset

Run the bounded stable-corpus UI proof:

```powershell
$env:ANYTHINGLLM_API_KEY=[Environment]::GetEnvironmentVariable('ANYTHINGLLM_API_KEY','User')
python scripts\validate_anythingllm_ui_e2e.py `
  --anythingllm-api-base-url http://127.0.0.1:3001 `
  --workspace my-workspace `
  --ui-dist-root runtime-state\anythingllm-ui\asar-dist\dist `
  --timeout-seconds 300 `
  --output-path runtime-state\anythingllm-ui\phase126-corpus-ui-usefulness.json `
  --case-id UI126-CQ116-001 `
  --case-id UI126-CQ116-009 `
  --case-id UI126-DD117-001 `
  --case-id UI126-DD117-002 `
  --case-id UI126-EJ118-001 `
  --case-id UI126-EJ118-002 `
  --case-id UI126-DM119-001 `
  --case-id UI126-DM119-002
```

The report should include:

- `status=passed`
- `case_count=8`
- `fixture_unchanged=true`
- all cases have `stream_chat_seen=true`
- all cases have screenshot status `passed`
- all stable cases have `answer_usefulness.usefulness_status=passed`
- `case_target_roots` includes both frozen Coinbase fixtures

## Phase 167 No-Target UI Replay Gate

Run the generic/vague prompt UI replay slice:

```powershell
$env:ANYTHINGLLM_API_KEY=[Environment]::GetEnvironmentVariable('ANYTHINGLLM_API_KEY','User')
python scripts\validate_anythingllm_ui_e2e.py `
  --anythingllm-api-base-url http://127.0.0.1:3001 `
  --workspace my-workspace `
  --ui-dist-root runtime-state\anythingllm-ui\asar-dist\dist `
  --timeout-seconds 300 `
  --output-path runtime-state\anythingllm-ui\phase167\phase167-ui-replay.json `
  --case-id UI167-GENCHAT-001 `
  --case-id UI167-GENHELP-001 `
  --case-id UI167-VAGUE-001
```

The report should include:

- `status=passed`
- three browser-visible no-target cases
- `stream_chat_seen=true` for each case
- `Answer:` appears before `I completed workflow_router.plan.`
- `Selected workflow: none`
- route statuses `general_chat_no_target`, `general_help_no_target`, and `missing_target_root_for_coding_request`
- `Artifacts:` absent from the no-target response segments
- `fixture_unchanged=true` for both frozen Coinbase fixtures

## Phase 184 Priority 0 Repair Replay Gate

Run the repaired evidence relevance and related-test discovery UI slice:

```powershell
$env:ANYTHINGLLM_API_KEY=[Environment]::GetEnvironmentVariable('ANYTHINGLLM_API_KEY','User')
python scripts\validate_anythingllm_ui_e2e.py `
  --anythingllm-api-base-url http://127.0.0.1:3001 `
  --workspace my-workspace `
  --prompt-catalog-path runtime\anythingllm_ui_prompt_cases.json `
  --timeout-seconds 900 `
  --output-path runtime-state\anythingllm-ui\phase184-ui-replay-report.json `
  --case-id UI184-ERR-001 `
  --case-id UI184-RTD-001 `
  --case-id UI184-RTD-002
```

The report should include:

- `status=passed`
- `case_count=6` because each case runs against both frozen Coinbase fixtures
- `stream_chat_seen=true` for each case
- semantic status `passed` for each case
- direct related-test evidence for the `placed_order_id` lookup prompt
- `Related tests: none found in bounded evidence` for the no-bounded-test prompt
- `fixture_unchanged=true` for both frozen Coinbase fixtures
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

Check that AnythingLLM Desktop is running on the selected API base, the API key is correct, the workspace slug exists, and the workspace `chatMode` is `chat`. If `127.0.0.1:3001` is a different local app, pass the working network API base, such as `http://192.168.0.208:3001`.

`AnythingLLM browser UI validation failed`

Open the JSON report and screenshots under `runtime-state/anythingllm-ui/`. Check `page_errors`, `non_ignored_request_failures`, `responses_tail`, and the per-case `segment_after_tag_tail`.

If `segment_after_tag_tail` contains `@agent: Swapping over to agent chat`, change the AnythingLLM workspace chat mode from `automatic` to `chat`; automatic mode invokes AnythingLLM's agent layer before the workflow-router answer can render.
