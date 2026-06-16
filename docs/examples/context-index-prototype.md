# Context Index Prototype Examples

Validate Phase 217:

```bash
python3 scripts/validate_context_index_prototype.py
```

Run focused regression:

```bash
python3 -m pytest tests/regression/test_context_index_prototype.py -q
```

Inspect the report summary:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase217/phase217-context-index-prototype-report.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
for case in report["query_smoke_results"]:
    print(case["case_id"], case["match_count"], case["top_matches"][:2])
PY
```

Expected result:

- `indexed_file_count` is at least `220`.
- `chunk_count` is at least `220`.
- `estimated_indexed_token_count` is at least `384000`.
- `query_smoke_passed_count` is `3`.
- `negative_control_passed_count` is `7`.
- `source_text_retention` is `metadata_only`.
- `store_source_text` is `false`.
- `phase218_ready` is `true`.

The index and report must not contain source text, snippets, rejected-source content, or secret-like fixture values.
