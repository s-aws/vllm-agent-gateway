# Onboarding And Release Handoff Refresh Examples

Phase 232 is the contextless tester handoff gate after Phase 231 recovery proof.

## Run The Gate

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_onboarding_release_handoff_refresh.py
```

Expected marker:

```text
PHASE232 ONBOARDING RELEASE HANDOFF REFRESH PASS
```

## Runtime Recovery Command Referenced By The Handoff

```bash
python3 scripts/validate_runtime_recovery_reliability_rebaseline.py \
  --restart-managed-stack \
  --restart-vllm-container vllm-qwen3 \
  --timeout-seconds 900
```

That command proves vLLM, gateway/proxies, controller, AnythingLLM, small-repo prompt validation, and large-context prompt validation recover together.

## Inspect Missing Markers

```bash
python3 - <<'PY'
import json
from pathlib import Path

path = Path("runtime-state/phase232/phase232-onboarding-release-handoff-refresh-report.json")
report = json.loads(path.read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
for doc in report["docs"]:
    if doc["missing_required_markers"] or doc["present_forbidden_markers"]:
        print(doc["path"])
        print("  missing:", doc["missing_required_markers"])
        print("  forbidden:", doc["present_forbidden_markers"])
PY
```
