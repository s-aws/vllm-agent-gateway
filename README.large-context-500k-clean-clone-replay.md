# Large-Context 500k Clean Clone Replay

This gate proves the 500k candidate path can be replayed from a remote branch clone instead of depending on active workspace state.

It is intended to run from a fresh clone of `s-aws/vllm-agent-gateway` on branch `codex/m14-release-clone-proof`. It verifies the clone starts clean, `runtime-state/` is ignored, Phase 270 through Phase 274 pass, and the clone remains clean after validation.

The live controller/gateway stack must be started from the clone before this gate runs. If the controller is still hosted from `/mnt/c/agentic_agents`, the gate fails during controller preflight because that would prove the active workspace, not the clean clone.

## What This Proves

- The 500k candidate proof chain exists in git and is not only local runtime state.
- Phase 270 candidate rebaseline passes.
- Phase 271 fixture/index readiness passes.
- Phase 272 stale-index rejection passes.
- Phase 273 live gateway and AnythingLLM acceptance passes.
- Phase 274 closes as `no_repair_required`.
- Controller preflight proves `/health` reports the clean clone as `config_root`.
- The remote branch clone stays clean except for ignored local runtime artifacts.

## Command

```bash
cd /mnt/c/agentic_agents
bash stop-agent-prompt-proxies.sh
rm -rf /tmp/agentic_agents_phase275_remote_clone
git clone --branch codex/m14-release-clone-proof https://github.com/s-aws/vllm-agent-gateway.git /tmp/agentic_agents_phase275_remote_clone
cd /tmp/agentic_agents_phase275_remote_clone
GATEWAY_BIND_HOST=0.0.0.0 \
WORKFLOW_ROUTER_GATEWAY_BIND_HOST=0.0.0.0 \
CONTROLLER_BIND_HOST=0.0.0.0 \
bash start-agent-prompt-proxies.sh
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_large_context_500k_clean_clone_replay.py \
  --live \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --anythingllm-workflow-router-base-url http://PRINTED_WSL_WORKFLOW_ROUTER_HOST:8500/v1 \
  --timeout-seconds 1200
```

Expected marker:

```text
PHASE275 LARGE CONTEXT 500K CLEAN CLONE REPLAY PASS
```

## Scope Boundary

This phase does not promote 500k to stable. It proves reproducibility from a clean clone. The Phase 276 decision gate still determines whether the 500k candidate ships, holds, or requires repair.
