# Large-Corpus Context Budget Inventory Examples

Use these commands from Bash/WSL.

## Generate And Validate Inventory

```bash
python3 scripts/validate_large_corpus_context_budget_inventory.py
```

## Focused Regression

```bash
python3 -m pytest tests/regression/test_large_corpus_context_budget_inventory.py -q
```

## Inspect The Report

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase214/phase214-large-corpus-context-budget-inventory-report.json").read_text())
print(report["status"], report["summary"])
print(report["context_budget"])
PY
```

## Important Boundary

Do not use this generated corpus to claim raw 1M-token prompt support. It is a planning fixture for retrieval-first large-corpus usability.
