# Context Strategy Router Examples

Validate the Phase 220 strategy router:

```bash
python3 scripts/validate_context_strategy_router.py
```

Focused regression:

```bash
python3 -m pytest tests/regression/test_context_strategy_router.py -q
```

Inspect the generated report:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase220/phase220-context-strategy-router-report.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
for case in report["decision_case_results"]:
    print(case["case_id"], case["selected_strategy"], case["execution_path"], case["passed"])
PY
```

Expected summary markers:

- `all_strategies_covered` is `true`
- `decision_passed_count` equals `6`
- `negative_control_passed_count` equals `4`
- `phase221_ready` is `true`

Example natural prompt:

```text
In /mnt/c/agentic_agents/runtime-state/phase214/generated-large-corpus, produce a long evidence report with all relevant top files for the order replay pipeline.
```

The default chat output should remain answer-first and include `selected_context_strategy`, `context_strategy_execution_path`, and retrieval paging metadata.
