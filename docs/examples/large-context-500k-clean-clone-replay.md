# Large-Context 500k Clean Clone Replay Examples

Clone the remote branch and run Phase 275:

```bash
rm -rf /tmp/agentic_agents_phase275_remote_clone
git clone --branch codex/m14-release-clone-proof https://github.com/s-aws/vllm-agent-gateway.git /tmp/agentic_agents_phase275_remote_clone
cd /tmp/agentic_agents_phase275_remote_clone
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_large_context_500k_clean_clone_replay.py \
  --live \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --anythingllm-workflow-router-base-url http://PRINTED_WSL_WORKFLOW_ROUTER_HOST:8500/v1 \
  --timeout-seconds 1200
```

Inspect the generated report:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase275/phase275-large-context-500k-clean-clone-replay-report.json").read_text())
print(report["decision"])
print(report["summary"]["passed_gate_count"])
print(report["summary"]["source_dirty_line_count_before"])
print(report["summary"]["source_dirty_line_count_after"])
print(report["summary"]["phase276_ready"])
PY
```

Expected values:

```text
phase275_clean_clone_500k_candidate_ready
6
0
0
True
```

`runtime-state/` must remain ignored. If the clone is dirty before or after replay, the gate fails.
