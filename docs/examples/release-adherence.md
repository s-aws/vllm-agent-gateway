# Release Adherence Examples

## Run Current Localhost Gate

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_release_adherence.py \
  --candidate-id current-localhost-model \
  --candidate-model-base-url http://127.0.0.1:8000/v1 \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --anythingllm-api-base-url http://127.0.0.1:3001 \
  --workspace my-workspace \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900 \
  --command-timeout-seconds 3600 \
  --output-path runtime-state/release-adherence/current.json
```

Expected result:

```text
RELEASE ADHERENCE PASS
```

## Use An Explicit UI Bundle

When validating from a fresh Bash session, pass the UI bundle paths if automatic discovery is not enough:

```bash
python3 scripts/validate_release_adherence.py \
  --app-asar-path /mnt/c/Users/<user>/AppData/Local/Programs/AnythingLLM/resources/app.asar \
  --extract-root runtime-state/anythingllm-ui/asar-dist \
  --refresh-extract \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --output-path runtime-state/release-adherence/current.json
```

## Review Findings

If the command fails, inspect:

```text
runtime-state/release-adherence/current.json
runtime-state/release-adherence/current.md
```

Use `findings[].classification` to route repair work:

- `semantic_quality`: answer content or skill output missed required meaning
- `answer_renderer`: chat-visible output format missed the contract
- `route`: workflow or route rule selected the wrong path
- `anythingllm_config`: API key, workspace, `/stream-chat`, or AnythingLLM target URL problem
- `fixture_mutation`: protected fixture state changed and live testing should stop
- `latency`: timing evidence is missing or unacceptable
