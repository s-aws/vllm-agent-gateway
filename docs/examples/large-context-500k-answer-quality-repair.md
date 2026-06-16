# Large-Context 500k Answer-Quality Repair Examples

Run the Phase 274 closure gate:

```bash
python3 scripts/validate_large_context_500k_answer_quality_repair.py
```

Inspect the generated report:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase274/phase274-large-context-500k-answer-quality-repair-report.json").read_text())
print(report["decision"])
print(report["summary"]["phase273_critical_or_high_finding_count"])
print(report["summary"]["phase275_ready"])
PY
```

Expected values:

```text
no_repair_required
0
True
```

This gate should fail if Phase 273 has accepted high or critical findings. In that case, implement the smallest targeted repair and rerun the affected prompt plus holdouts before closing Phase 274.
