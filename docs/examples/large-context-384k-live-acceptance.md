# Large-Context 384k Live Acceptance Examples

Run the live gate:

```bash
python3 scripts/validate_large_context_384k_live_acceptance.py --live
```

Run with a split Windows/WSL AnythingLLM target:

```bash
python3 scripts/validate_large_context_384k_live_acceptance.py \
  --live \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --anythingllm-workflow-router-base-url http://100.100.12.45:8500/v1
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
PY
```

Expected target:

```text
384000
```

The report should show all five strategy IDs: retrieval, artifact paging, summarization, refusal, and chunked investigation.
