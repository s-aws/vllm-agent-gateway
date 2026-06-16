# Large-Context 500k Live Acceptance Examples

Run the live Phase 273 gate from Bash:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_large_context_500k_live_acceptance.py \
  --live \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --anythingllm-workflow-router-base-url http://127.0.0.1:8500/v1 \
  --timeout-seconds 1200
```

Inspect the generated report:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase273/phase273-large-context-500k-live-acceptance-report.json").read_text())
print(report["summary"]["candidate_estimated_project_tokens"])
print(report["summary"]["response_count"])
print(report["summary"]["gateway_response_count"])
print(report["summary"]["anythingllm_response_count"])
print(report["summary"]["phase274_ready"])
PY
```

Expected values:

```text
500000
18
9
9
True
```

This gate proves live 500k candidate behavior through the governed workflow path. It does not prove raw 500k-token prompt serving or promote 500k to stable.
