# Large-Context 500k Fixture And Index Readiness Examples

Run the full Phase 271 readiness gate, including delegated bootstrap of the existing Phase 259 readiness path:

```bash
python3 scripts/validate_large_context_500k_fixture_index_readiness.py
```

Run the gate against existing Phase 214, Phase 216, and Phase 217 reports:

```bash
python3 scripts/validate_large_context_500k_fixture_index_readiness.py --reuse-existing-reports
```

Inspect the generated report:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase271/phase271-large-context-500k-fixture-index-readiness-report.json").read_text())
print(report["summary"]["candidate_estimated_project_tokens"])
print(report["summary"]["corpus_estimated_token_count"])
print(report["summary"]["estimated_indexed_token_count"])
print(report["summary"]["phase272_ready"])
PY
```

Expected minimum values:

```text
500000
>= 500000
>= 500000
True
```

This gate is intentionally non-live. It proves the fixture and metadata-first index are ready for the 500k candidate; it does not prove live gateway, AnythingLLM, or raw 500k-token prompting.
