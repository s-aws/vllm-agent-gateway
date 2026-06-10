# Skill/Tool Gap Batch Proposal Examples

Run from Bash/WSL.

## Generate The Proposal Report

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_skill_tool_gap_batch_proposal.py \
  --output-path runtime-state/skill-tool-gap-batch-proposal/phase161/phase161-skill-tool-gap-batch-proposal-report.json \
  --markdown-output-path runtime-state/skill-tool-gap-batch-proposal/phase161/phase161-skill-tool-gap-batch-proposal-report.md
```

Expected marker:

```text
PHASE161 SKILL TOOL GAP BATCH PROPOSAL PASS
```

## Inspect The Current Decision

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/skill-tool-gap-batch-proposal/phase161/phase161-skill-tool-gap-batch-proposal-report.json").read_text())
print(report["status"], report["decision"])
print(report["implementation_authorized"])
print(report["summary"])
for candidate in report["gap_candidates"]:
    print(candidate["candidate_id"], candidate["capability_id"], candidate["eval_gate"])
PY
```

## Expected Current Result

The current Phase 157-160 chain should show:

```text
status=passed
decision=no_new_batch_justified
implementation_authorized=False
missing_skill_tool_finding_count=0
gap_candidate_count=0
non_batch_finding_count=14
```

## Failure Review

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/skill-tool-gap-batch-proposal/phase161/phase161-skill-tool-gap-batch-proposal-report.json").read_text())
for error in report["validation_errors"]:
    print(error["id"], error["source"], error["message"])
PY
```

If the decision is `propose_batch_for_founder_approval`, inspect every candidate before approving implementation:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/skill-tool-gap-batch-proposal/phase161/phase161-skill-tool-gap-batch-proposal-report.json").read_text())
for candidate in report["gap_candidates"]:
    print(json.dumps(candidate, indent=2, sort_keys=True))
PY
```
