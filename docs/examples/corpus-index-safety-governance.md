# Corpus Index Safety Governance Examples

Validate Phase 216:

```bash
python3 scripts/validate_corpus_index_safety_governance.py
```

Run focused regression:

```bash
python3 -m pytest tests/regression/test_corpus_index_safety_governance.py -q
```

Inspect the generated summary:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase216/phase216-corpus-index-safety-governance-report.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
for case in report["negative_control_results"]:
    print(case["case_id"], case["actual_decision"], case["actual_reasons"])
PY
```

Expected result:

- `negative_control_count` is `13`.
- `negative_control_passed_count` is `13`.
- `admitted_count` is `1`.
- `rejected_count` is `12`.
- `durable_index_implementation_in_scope` is `false`.
- `retrieval_backed_chat_integration_in_scope` is `false`.
- `phase217_ready` is `true`.

The report must not contain rejected source text or the dummy secret-like fixture value.
