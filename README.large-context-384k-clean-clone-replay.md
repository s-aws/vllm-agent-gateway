# Large-Context 384k Clean Clone Replay

This Phase 264 gate proves the accepted 384k-token project path from a remote branch clone, not from the active workspace.

It is a proof-packaging gate. It does not add a new large-context runtime path. It reuses the existing 384k contract, fixture/index readiness, stale-index rejection, and live acceptance validators.

## What It Proves

- The source is a remote branch clone of `s-aws/vllm-agent-gateway`.
- The clone is on `codex/m14-release-clone-proof`.
- The clone starts clean before replay and remains clean after replay.
- `runtime-state/` remains local-only and ignored.
- Phase 251, Phase 258, Phase 259, and Phase 260 pass from the clone.
- Phase 261 live acceptance passes from the clone through gateway and AnythingLLM.
- The 384k target remains project usability through governed context strategy, not raw prompt stuffing.

## Command

Create or refresh a disposable remote branch clone:

```bash
rm -rf /tmp/agentic_agents_phase264_remote_clone
git clone -b codex/m14-release-clone-proof \
  https://github.com/s-aws/vllm-agent-gateway.git \
  /tmp/agentic_agents_phase264_remote_clone
cd /tmp/agentic_agents_phase264_remote_clone
git status --short
```

Run from the clone after vLLM, the gateway/proxies, the controller, and AnythingLLM are running:

```bash
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_large_context_384k_clean_clone_replay.py \
  --live \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --anythingllm-workflow-router-base-url http://127.0.0.1:8500/v1 \
  --timeout-seconds 1200
```

For split Windows/WSL setups, replace only `--anythingllm-workflow-router-base-url` with the workflow-router network URL printed by `start-agent-prompt-proxies.sh`.

## Pass Marker

```text
PHASE264 LARGE CONTEXT 384K CLEAN CLONE REPLAY PASS
```

## Artifacts

Primary artifacts are written under the clone-local `runtime-state/phase264/` directory:

```text
phase264-large-context-384k-clean-clone-replay-report.json
phase264-large-context-384k-clean-clone-replay-report.md
phase264-phase251-large-context-384k-objective-rebaseline-report.json
phase264-phase258-large-context-384k-usability-acceptance-contract-report.json
phase264-phase259-large-context-384k-fixture-index-readiness-report.json
phase264-phase260-large-context-384k-stale-index-rejection-report.json
phase264-phase261-large-context-384k-live-acceptance-report.json
```

## Boundary

This gate does not approve post-384k expansion or raw 384k prompt stuffing. It proves the accepted 384k project-usability path can be reproduced from a clean remote branch clone.
