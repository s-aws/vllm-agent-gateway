# Release Adherence

Release adherence is the consolidated Phase 109 gate for answering one question:

```text
Can the current localhost model and harness be trusted for normal founder/testing use through AnythingLLM?
```

It does not replace the lower-level validators. It runs them and produces one JSON plus one Markdown report for review.

## What It Runs

The gate orchestrates:

- V1.1 acceptance through localhost `8000`, workflow-router gateway `8500`, controller `8400`, AnythingLLM, and both frozen Coinbase fixtures
- browser-rendered AnythingLLM UI semantic E2E
- model portability classification from the V1.1 acceptance report
- model capability profile generation
- fixture mutation checks inherited from the V1.1 and UI E2E reports
- timing capture for suite commands and top-level gate steps

## Run

From Bash:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_release_adherence.py \
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

The command also writes a Markdown report next to the JSON report.

If the AnythingLLM UI bundle is already extracted, pass it explicitly:

```bash
python3 scripts/validate_release_adherence.py \
  --ui-dist-root runtime-state/anythingllm-ui/asar-dist/dist \
  --output-path runtime-state/release-adherence/current.json
```

If extraction is needed from Bash, the validator can discover `/mnt/c/Users/*/AppData/Local/Programs/AnythingLLM/resources/app.asar`. You can also pass:

```bash
--app-asar-path /mnt/c/Users/<user>/AppData/Local/Programs/AnythingLLM/resources/app.asar
--extract-root runtime-state/anythingllm-ui/asar-dist
--refresh-extract
--npx-command npx
```

## Findings

Findings are classified as:

- `blocker`: release is not ready
- `warning`: release can proceed only when the warning is understood and documented
- `info`: non-blocking evidence

Failure classes include setup, route, skill/tool selection, answer renderer, semantic quality, output contract, model quality, latency, AnythingLLM config, fixture mutation, stale artifact confusion, and security.

## Warning Policy

A model capability profile warning is acceptable only when latency is measured and the remaining warning is caused by the intentional real-apply boundary. Real repository mutation is still not approved by the stable tester path.

If latency remains unknown, the release-adherence gate blocks.

The gate also blocks if a later model probe fails, if required V1.1 suites or health ports are missing, if UI semantic cases are incomplete, or if fixture mutation proof is absent.

Examples: [docs/examples/release-adherence.md](docs/examples/release-adherence.md).
