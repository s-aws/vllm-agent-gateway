# Retrieval-First Context Strategy Design Examples

Validate the Phase 215 strategy design:

```bash
python3 scripts/validate_retrieval_first_context_strategy_design.py
```

Run the focused regression tests:

```bash
python3 -m pytest tests/regression/test_retrieval_first_context_strategy_design.py -q
```

Inspect the generated report:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase215/phase215-retrieval-first-context-strategy-design-report.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
for case in report["decision_cases"]:
    print(case["case_id"], "->", case["expected_strategy"])
PY
```

Expected result:

- `strategy_count` is `6`.
- `phase216_ready` is `true`.
- `raw_1m_prompt_support_proven` is `false`.
- `retrieval_index_implementation_in_scope` is `false`.
- `retrieval_backed_chat_integration_in_scope` is `false`.

If the validator fails, do not continue to Phase 216. Fix the policy gap first.
