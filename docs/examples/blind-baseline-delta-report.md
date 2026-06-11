# Blind-Baseline Delta Report Examples

Run the Phase 178 delta report after Phase 177 has refreshed the live AnythingLLM field evidence.

## Build The Report

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_blind_baseline_delta_report.py \
  --output-path runtime-state/phase178/phase178-blind-baseline-delta-report.json \
  --markdown-output-path runtime-state/phase178/phase178-blind-baseline-delta-report.md
```

Expected marker:

```text
PHASE178 BLIND BASELINE DELTA REPORT PASS
```

## Inspect Summary

```bash
python3 - <<'PY'
import json
from pathlib import Path

path = Path("runtime-state/phase178/phase178-blind-baseline-delta-report.json")
report = json.loads(path.read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
PY
```

Current passing summary shape:

```json
{
  "blocking_gap_count": 0,
  "delta_count": 13,
  "min_score": 94,
  "unique_case_count": 8,
  "validation_error_count": 0
}
```

## Inspect Deltas

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase178/phase178-blind-baseline-delta-report.json").read_text())
for delta in report["deltas"]:
    print(delta["family"], delta["role"], delta["case_id"], delta["score"], ",".join(delta["gap_classes"]))
PY
```

Use `backlog_candidates` when `blocking_gap_count` is non-zero. Do not repair blocking misses inside the report phase unless the roadmap explicitly approves the new scope.
