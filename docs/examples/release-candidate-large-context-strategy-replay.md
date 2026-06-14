# Release-Candidate Large-Context Strategy Replay Examples

Run from the release-candidate checkout:

```bash
export ANYTHINGLLM_API_KEY="$ANYTHINGLLM_API_KEY"
python3 scripts/validate_release_candidate_large_context_strategy_replay.py \
  --output-path runtime-state/release-candidate-large-context-strategy-replay/phase241/phase241-release-candidate-large-context-strategy-replay-report.json \
  --timeout-seconds 1200
```

Inspect the decision summary:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/release-candidate-large-context-strategy-replay/phase241/phase241-release-candidate-large-context-strategy-replay-report.json").read_text())
print(report["decision"])
print(json.dumps(report["summary"], indent=2, sort_keys=True))
PY
```

List live run IDs:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/release-candidate-large-context-strategy-replay/phase241/phase241-release-candidate-large-context-strategy-replay-report.json").read_text())
for group, run_ids in report["run_ids"].items():
    for run_id in run_ids:
        print(group, run_id)
PY
```
