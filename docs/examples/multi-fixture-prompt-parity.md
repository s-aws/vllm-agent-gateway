# Multi-Fixture Prompt Parity Examples

Run this after restarting the local model, gateway, proxies, and AnythingLLM.

## Readiness First

From Windows PowerShell:

```powershell
$key=$env:ANYTHINGLLM_API_KEY
wsl.exe --cd /mnt/c/agentic_agents -- env "ANYTHINGLLM_API_KEY=$key" python3 scripts/validate_post_restart_runtime_readiness.py `
  --output-path runtime-state/multi-fixture-prompt-parity/readiness.json `
  --timeout-seconds 120
```

The readiness report should return `decision=ready_after_restart`.

## Gateway-Only Matrix

```bash
python3 scripts/validate_multi_repo_fixtures_live.py \
  --port-health \
  --timeout-seconds 900 \
  --output-path runtime-state/multi-fixture-prompt-parity/gateway-report.json
```

Expected summary shape:

```json
{
  "case_count": 15,
  "client_case_count": 15,
  "fixture_count": 5,
  "prompt_family_count": 6,
  "clients": ["gateway"],
  "error_count": 0
}
```

## Gateway Plus AnythingLLM Matrix

From Windows PowerShell, inject the Windows API key into WSL:

```powershell
$key=$env:ANYTHINGLLM_API_KEY
wsl.exe --cd /mnt/c/agentic_agents -- env "ANYTHINGLLM_API_KEY=$key" python3 scripts/validate_multi_repo_fixtures_live.py `
  --port-health `
  --live-anythingllm `
  --timeout-seconds 900 `
  --output-path runtime-state/multi-fixture-prompt-parity/anythingllm-report.json
```

Expected summary shape:

```json
{
  "case_count": 15,
  "client_case_count": 30,
  "fixture_count": 5,
  "prompt_family_count": 6,
  "clients": ["anythingllm", "gateway"],
  "error_count": 0
}
```

Inspect `parity_matrix` in the report. A pass has no `fixture_specific_deltas` and no `shared_workflow_deltas`.

## Selected Case Rerun

Use selected case IDs when repairing one prompt family:

```bash
python3 scripts/validate_multi_repo_fixtures_live.py \
  --port-health \
  --case-id coinbase-schema-lookup \
  --case-id coinbase-git-schema-lookup \
  --case-id python-service-schema-lookup \
  --timeout-seconds 900 \
  --output-path runtime-state/multi-fixture-prompt-parity/schema-lookup-rerun.json
```

If one fixture fails and the rest pass, treat it as fixture-specific. If every case in the family fails, treat it as a shared workflow or output-contract gap.
