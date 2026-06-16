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

Start the managed stack from that clone. Use the bind-host settings when AnythingLLM is a Windows client pointed at the WSL network URL:

```bash
bash stop-agent-prompt-proxies.sh
GATEWAY_BIND_HOST=0.0.0.0 \
WORKFLOW_ROUTER_GATEWAY_BIND_HOST=0.0.0.0 \
CONTROLLER_BIND_HOST=0.0.0.0 \
CONTROLLER_ALLOWED_TARGET_ROOTS="/tmp/agentic_agents_phase264_remote_clone:/mnt/c/coinbase_testing_repo_frozen_tmp:/mnt/c/coinbase_testing_repo_frozen_tmp.github" \
CONTROLLER_DEFAULT_ROLE_BASE_URL="http://127.0.0.1:8300/v1" \
bash start-agent-prompt-proxies.sh
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
