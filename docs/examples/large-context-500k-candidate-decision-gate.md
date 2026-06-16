# Large-Context 500k Candidate Decision Gate Examples

Run Phase 276 with the explicit Phase 275 clean-clone report:

```bash
python3 scripts/validate_large_context_500k_candidate_decision_gate.py \
  --phase275-report-path /tmp/agentic_agents_phase275_remote_clone/runtime-state/phase275/phase275-large-context-500k-clean-clone-replay-report.json
```

Inspect the generated report:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase276/phase276-large-context-500k-candidate-decision-gate-report.json").read_text())
print(report["decision"])
print(report["summary"]["blocker_count"])
print(report["summary"]["phase275_decision"])
print(report["summary"]["candidate_estimated_project_tokens"])
print(report["summary"]["phase277_ready"])
PY
```

Expected values after a passing clean-clone replay and healthy runtime:

```text
ship
0
phase275_clean_clone_500k_candidate_ready
500000
True
```
