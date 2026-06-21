# Context Strategy Router Rebaseline Examples

Run the Phase 319 rebaseline after Phase 318 has produced a local context-ceiling benchmark report:

```bash
python3 scripts/validate_context_strategy_router_rebaseline.py
```

Run focused regression:

```bash
python3 -m pytest tests/regression/test_context_strategy_router_rebaseline.py -q
```

Inspect the report:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase319/phase319-context-strategy-router-rebaseline-report.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
for case in report["case_results"]:
    print(case["case_id"], case["kind"], case["selected_strategy"], case["decision_reason"], case["passed"])
PY
```

Expected markers:

- `all_strategies_covered` is `true`
- `deterministic_replay_passed` is `true`
- `sensitive_or_secret_request_refused` is `true`
- `raw_500k_prompt_support_proven` is `false`
- `phase320_ready` is `true`
