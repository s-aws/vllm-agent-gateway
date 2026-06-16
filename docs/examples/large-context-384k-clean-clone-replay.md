# Large-Context 384k Clean Clone Replay Examples

Create a remote branch clone:

```bash
rm -rf /tmp/agentic_agents_phase264_remote_clone
git clone -b codex/m14-release-clone-proof \
  https://github.com/s-aws/vllm-agent-gateway.git \
  /tmp/agentic_agents_phase264_remote_clone
cd /tmp/agentic_agents_phase264_remote_clone
git status --short
```

Run the Phase 264 live replay:

```bash
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_large_context_384k_clean_clone_replay.py \
  --live \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --anythingllm-workflow-router-base-url http://127.0.0.1:8500/v1 \
  --timeout-seconds 1200
```

Run with a split Windows/WSL AnythingLLM target:

```bash
python3 scripts/validate_large_context_384k_clean_clone_replay.py \
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

report = json.loads(Path("runtime-state/phase264/phase264-large-context-384k-clean-clone-replay-report.json").read_text())
summary = report["summary"]
print(summary["decision"])
print(summary["source_branch"])
print(summary["source_dirty_line_count_before"])
print(summary["source_dirty_line_count_after"])
print(summary["target_estimated_project_tokens"])
print(summary["strategy_ids"])
PY
```

Expected result:

```text
phase264_clean_clone_384k_usability_ready
codex/m14-release-clone-proof
0
0
384000
```

The strategy list should include `retrieval`, `artifact_paging`, `summarization`, `refusal`, and `chunked_investigation`.
