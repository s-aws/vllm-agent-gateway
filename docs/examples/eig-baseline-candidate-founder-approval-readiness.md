# EIG Baseline Candidate Founder Approval Readiness Examples

Run the current-state readiness gate:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_eig_baseline_candidate_founder_approval_readiness.py \
  --output-path runtime-state/eig-baseline-candidate-founder-approval-readiness/phase317-validation.json
```

Expected marker:

```text
EIG BASELINE CANDIDATE FOUNDER APPROVAL READINESS PASS
```

Inspect the summary:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/eig-baseline-candidate-founder-approval-readiness/phase317-validation.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
PY
```

Expected fields:

```text
ready_for_founder_decision=true
missing_evidence=["founder_approval"]
founder_approval_recorded=false
promotion_allowed=false
stable_corpus_mutated=false
phase318_ready=true
```

If any prerequisite report is missing, rerun the corresponding Phase 312, 314, 315, or 316 validator before using this gate.
