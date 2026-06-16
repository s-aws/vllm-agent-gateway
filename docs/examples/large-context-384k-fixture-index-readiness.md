# Large-Context 384k Fixture And Index Readiness Examples

Run the full Bash bootstrap gate:

```bash
python3 scripts/validate_large_context_384k_fixture_index_readiness.py
```

Inspect the accepted token and index counts:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase259/phase259-large-context-384k-fixture-index-readiness-report.json").read_text())
print(report["summary"]["corpus_estimated_token_count"])
print(report["summary"]["estimated_indexed_token_count"])
print(report["summary"]["indexed_file_count"])
print(report["summary"]["chunk_count"])
print(report["summary"]["phase260_ready"])
PY
```

Expected minimum:

```text
384000
```

If a local Windows symlink policy prevents rerunning Phase 216, diagnose with existing reports only:

```bash
python3 scripts/validate_large_context_384k_fixture_index_readiness.py --reuse-existing-reports
```
