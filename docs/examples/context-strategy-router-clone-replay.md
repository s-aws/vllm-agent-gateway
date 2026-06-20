# Context Strategy Router Clone Replay Examples

Run the Phase 320 clone-safe replay:

```bash
python3 scripts/validate_context_strategy_router_clone_replay.py
```

Run focused regression:

```bash
python3 -m pytest tests/regression/test_context_strategy_router_clone_replay.py -q
```

Inspect the report:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase320/phase320-context-strategy-router-clone-replay-report.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
print(report["bootstrap_fixture"]["target_root"])
print(report["phase319_report_path"])
PY
```

Expected markers:

- `phase319_status` is `passed`
- `phase319_case_count` is `11`
- `phase319_passed_case_count` is `11`
- `persistent_runtime_state_required` is `false`
- `raw_500k_prompt_support_proven` is `false`
- `phase321_ready` is `true`
