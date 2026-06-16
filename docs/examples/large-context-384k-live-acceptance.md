# Large-Context 384k Live Acceptance Examples

Run the live gate:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_large_context_384k_live_acceptance.py \
  --live \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --anythingllm-workflow-router-base-url http://127.0.0.1:8500/v1 \
  --timeout-seconds 1200
```

Run with a split Windows/WSL AnythingLLM target:

```bash
python3 scripts/validate_large_context_384k_live_acceptance.py \
  --live \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --anythingllm-workflow-router-base-url http://PRINTED_WSL_WORKFLOW_ROUTER_HOST:8500/v1 \
  --timeout-seconds 1200
```

Inspect the generated summary:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase261/phase261-large-context-384k-live-acceptance-report.json").read_text())
print(report["status"])
print(report["summary"]["target_estimated_project_tokens"])
print(report["summary"]["strategy_ids"])
print(report["summary"]["json_default_parity_status"])
print(report["summary"]["critical_or_high_finding_count"])
print(report["summary"]["failed_small_repo_regression_count"])
PY
```

Expected target:

```text
384000
```

The report should show all five strategy IDs: retrieval, artifact paging, summarization, refusal, and chunked investigation.

The report should also show `json_default_parity_status=passed`, `critical_or_high_finding_count=0`, and `failed_small_repo_regression_count=0`.

Primary proof artifacts:

```text
runtime-state/phase261/phase261-large-context-384k-live-acceptance-report.json
runtime-state/phase261/phase261-phase221-large-context-usability-live-closeout-report.json
runtime-state/phase261/phase261-phase223-chunked-investigation-executor-implementation-report.json
runtime-state/phase261/phase261-blind-baseline-artifacts.json
runtime-state/phase261/phase261-blind-baseline-comparisons.json
```
