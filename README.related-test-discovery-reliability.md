# Related-Test Discovery Reliability

Phase 183 hardens related-test answers for local coding-agent prompts.

The goal is to make test recommendations evidence-backed and honest. A response may recommend a narrow test command only when bounded repo evidence supports that test. If bounded discovery finds no related tests, the chat answer must say so instead of inventing coverage.

## What It Covers

- Classifies test evidence as `direct`, `adjacent`, or `weak`.
- Adds confidence labels to related-test records and verification commands.
- Preserves source refs and evidence refs for why a test was selected.
- Exposes related-test confidence in chat output.
- Makes no-test-found cases visible in chat with `verification_tests_not_found`.
- Validates direct-test and no-test scenarios through gateway and AnythingLLM on both frozen Coinbase fixtures.

## Validation

Synthetic gate:

```bash
python3 scripts/validate_related_test_discovery_reliability.py \
  --output-path runtime-state/related-test-discovery-reliability/phase183-synthetic-report.json \
  --markdown-output-path runtime-state/related-test-discovery-reliability/phase183-synthetic-report.md
```

Live gate:

```bash
python3 scripts/validate_related_test_discovery_reliability.py --live \
  --output-path runtime-state/related-test-discovery-reliability/phase183-live-report.json \
  --markdown-output-path runtime-state/related-test-discovery-reliability/phase183-live-report.md
```

If WSL does not inherit the Windows `ANYTHINGLLM_API_KEY`, pass it explicitly from PowerShell:

```powershell
$key=$env:ANYTHINGLLM_API_KEY
wsl.exe --cd /mnt/c/agentic_agents -- env "ANYTHINGLLM_API_KEY=$key" python3 scripts/validate_related_test_discovery_reliability.py --live
```

Policy lives in `runtime/related_test_discovery_reliability_policy.json`.
