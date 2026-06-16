# Large-Context 384k Release-Candidate Decision Gate Examples

Run the decision gate against the accepted clean-clone Phase 264 report:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_large_context_384k_release_candidate_decision_gate.py \
  --phase264-report-path /tmp/agentic_agents_phase264_remote_clone/runtime-state/phase264/phase264-large-context-384k-clean-clone-replay-report.json \
  --health-timeout-seconds 10
```

Inspect the generated decision:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase265/phase265-large-context-384k-release-candidate-decision-gate-report.json").read_text())
print(report["decision"])
print(report["summary"]["blocker_count"])
print(report["summary"]["phase264_decision"])
print(report["summary"]["target_estimated_project_tokens"])
print(report["summary"]["phase266_ready"])
PY
```

Expected ship-ready result:

```text
ship
0
phase264_clean_clone_384k_usability_ready
384000
True
```

If the decision is `hold`, restore vLLM, the repo-managed stack, AnythingLLM, and role ports, then rerun the gate. If the decision is `repair_required`, repair the named proof gap and rerun Phase 264 before rerunning Phase 265.
