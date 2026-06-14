# Runtime Recovery Reliability Rebaseline

Phase 231 proves the local tester can restart the runtime stack and continue chat-quality validation without session-specific troubleshooting.

Use this after changing restart scripts, gateway/controller wiring, AnythingLLM target setup, vLLM launch assumptions, or any workflow that depends on post-restart localhost behavior.

## What It Proves

- vLLM is actually restarted and responds on `8000`.
- The repo-managed gateway/proxy/controller stack is actually restarted through the project scripts.
- Post-restart readiness passes for model `8000`, LLM gateway `8300`, controller `8400`, workflow-router gateway `8500`, role ports, AnythingLLM target URL, and greeting/session behavior.
- A small-repo prompt passes through both workflow-router gateway and AnythingLLM after recovery.
- A large-context prompt passes through both workflow-router gateway and AnythingLLM after recovery.
- The final report links restart, readiness, small-repo, and large-context artifacts by path and hash.

## Single Path

This gate composes existing validators:

- `scripts/validate_post_restart_runtime_readiness.py`
- `scripts/validate_multi_repo_fixtures_live.py`
- `scripts/validate_large_context_usability_live_closeout.py`

It does not add a parallel port checker, duplicate AnythingLLM chat runner, or bypass the workflow-router gateway.

## Run

From PowerShell, expose the AnythingLLM API key to WSL and run the Phase 231 gate:

```powershell
$old=$env:WSLENV
if ($old -and $old -notmatch 'ANYTHINGLLM_API_KEY') {
  $env:WSLENV = $old + ':ANYTHINGLLM_API_KEY/u'
} elseif (-not $old) {
  $env:WSLENV = 'ANYTHINGLLM_API_KEY/u'
}

bash -lc "cd /mnt/c/agentic_agents && python3 scripts/validate_runtime_recovery_reliability_rebaseline.py --restart-managed-stack --restart-vllm-container vllm-qwen3 --timeout-seconds 900"
```

Expected marker:

```text
PHASE231 RUNTIME RECOVERY RELIABILITY REBASELINE PASS
```

## Output

Default final report:

```text
runtime-state/phase231/phase231-runtime-recovery-reliability-rebaseline-report.json
```

Child reports:

- `runtime-state/phase231/phase231-restart-evidence.json`
- `runtime-state/phase231/phase231-post-restart-runtime-readiness-report.json`
- `runtime-state/phase231/phase231-small-repo-live-report.json`
- `runtime-state/phase231/phase231-large-context-live-report.json`
- `runtime-state/phase231/phase231-large-context-live-report.md`

Examples: [docs/examples/runtime-recovery-reliability-rebaseline.md](docs/examples/runtime-recovery-reliability-rebaseline.md)
