# Runtime Recovery Reliability Rebaseline Examples

Phase 231 is a recovery proof, not only a health probe. It must restart the model and repo-managed stack, then prove chat-quality validation still works through gateway and AnythingLLM.

## Full Recovery Gate

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

## Inspect The Final Report

```bash
cd /mnt/c/agentic_agents
python3 - <<'PY'
import json
from pathlib import Path

path = Path("runtime-state/phase231/phase231-runtime-recovery-reliability-rebaseline-report.json")
report = json.loads(path.read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
print("missing:", report["missing_required_surfaces"])
for item in report["source_artifacts"]:
    print(f"{item['name']}: {item['status']} {item['path']} {item['sha256']}")
PY
```

## Focused Component Reruns

Post-restart readiness:

```bash
python3 scripts/validate_post_restart_runtime_readiness.py \
  --timeout-seconds 120 \
  --output-path runtime-state/phase231/phase231-post-restart-runtime-readiness-report.json \
  --health-drift-output-path runtime-state/phase231/phase231-health-drift-report.json \
  --doctor-output-path runtime-state/phase231/phase231-first-time-user-doctor.json \
  --session-recovery-output-path runtime-state/phase231/phase231-session-recovery-report.json
```

Small-repo prompt through gateway and AnythingLLM:

```bash
python3 scripts/validate_multi_repo_fixtures_live.py \
  --case-id python-service-code-explanation \
  --live-anythingllm \
  --port-health \
  --output-path runtime-state/phase231/phase231-small-repo-live-report.json
```

Large-context prompt through gateway and AnythingLLM:

```bash
python3 scripts/validate_large_context_usability_live_closeout.py \
  --live \
  --allow-partial \
  --case-id P221-LC-001 \
  --output-path runtime-state/phase231/phase231-large-context-live-report.json \
  --markdown-output-path runtime-state/phase231/phase231-large-context-live-report.md \
  --timeout-seconds 900
```

## Failure Interpretation

- Missing `restart.managed_stack` means the repo start/stop scripts were not proven.
- Missing `restart.vllm_model` means the model container was not proven restarted and ready.
- Missing `small_repo.anythingllm` means post-recovery AnythingLLM did not complete the small-repo prompt.
- Missing `large_context.anythingllm` means post-recovery AnythingLLM did not complete the large-context prompt.
