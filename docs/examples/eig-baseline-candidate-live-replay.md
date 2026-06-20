# EIG Baseline Candidate Live Replay Examples

Run a static preflight without live calls:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_eig_baseline_candidate_live_replay.py --no-live
```

The static preflight should pass, but `phase309_ready` remains `false` because live replay did not run.

Run the live Phase 308 replay:

```bash
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_eig_baseline_candidate_live_replay.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --anythingllm-api-base-url http://192.168.0.208:3001 \
  --timeout-seconds 240 \
  --output-path runtime-state/eig-baseline-candidate-live-replay/phase308-validation.json
```

Expected marker:

```text
EIG BASELINE CANDIDATE LIVE REPLAY PASS
```

Inspect the summary:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/eig-baseline-candidate-live-replay/phase308-validation.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
PY
```

Expected fields:

```text
candidate_count=2
total_source_case_count=7
live_result_count=14
covered_surface_count=2
missing_surface_count=0
stable_corpus_promotion_allowed=false
founder_approval_recorded=false
phase309_ready=true
```

Do not promote the stable corpus from this report alone. Phase 308 creates replay evidence; promotion still requires founder approval and a separate stable-corpus update phase.
