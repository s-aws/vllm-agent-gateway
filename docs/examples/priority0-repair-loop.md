# Priority 0 Repair Loop Examples

Run from Bash/WSL.

## Build The Phase 159 Report

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_priority0_repair_loop.py \
  --output-path runtime-state/priority0-repair-loop/phase159/phase159-priority0-repair-loop-report.json \
  --markdown-output-path runtime-state/priority0-repair-loop/phase159/phase159-priority0-repair-loop-report.md
```

Expected marker:

```text
PHASE159 PRIORITY0 REPAIR LOOP PASS
```

## Current Expected Result

The current Phase 158 report contains no repair-eligible findings, so Phase 159 should produce:

```text
repair_mode=no_repair_required
phase159_eligible_count=0
monitoring_only_count=14
closed_repair_count=0
open_repair_count=0
```

## Repair Records Shape

Only create this file when Phase 158 has `phase159_eligible=true` findings:

```json
{
  "kind": "priority0_repair_loop_records",
  "phase": 159,
  "records": [
    {
      "finding_id": "phase158-P01-blocker",
      "closure_status": "closed_with_target_holdout_proof",
      "required_rerun_gate": "phase159_target_plus_holdout",
      "live_surfaces": ["gateway", "anythingllm"],
      "target_result_status": "passed",
      "holdout_result_status": "passed",
      "mutation_status": "unchanged",
      "target_report_path": "runtime-state/priority0-repair-loop/phase159/target.json",
      "holdout_report_path": "runtime-state/priority0-repair-loop/phase159/holdout.json",
      "repair_summary": "Closed with target and holdout proof."
    }
  ]
}
```

Closed records must point to readable JSON proof reports. The target proof report must use `kind=priority0_repair_target_proof`, `status=passed`, and `result_status=passed`. The holdout proof report must use `kind=priority0_repair_holdout_proof`, `status=passed`, and `result_status=passed`.

Open blockers are allowed only when they are explicit. They produce `status=blocked`, so the validator exits non-zero until the blocker is closed:

```json
{
  "finding_id": "phase158-P01-blocker",
  "closure_status": "open_blocked",
  "blocker_reason": "The target repair needs a deterministic tool that is not approved yet.",
  "next_action": "Add a skill or tool gap proposal before implementation work continues."
}
```

## Inspect The Report

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/priority0-repair-loop/phase159/phase159-priority0-repair-loop-report.json").read_text())
print(report["status"], report["repair_mode"])
print(report["summary"])
PY
```
