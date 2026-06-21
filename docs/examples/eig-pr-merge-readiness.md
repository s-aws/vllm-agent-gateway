# EIG PR Merge Readiness Examples

Run the Phase 310 merge-readiness gate:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_eig_pr_merge_readiness.py \
  --output-path runtime-state/eig-pr-merge-readiness/phase310-validation.json
```

Expected marker:

```text
EIG PR MERGE READINESS PASS
```

Inspect the summary:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/eig-pr-merge-readiness/phase310-validation.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
PY
```

Expected fields:

```text
pr_state=OPEN
pr_merge_state_status=CLEAN
source_clean=true
merge_allowed=false
main_mutation_allowed=false
stable_corpus_promotion_allowed=false
ready_for_founder_merge_decision=true
```

For local static troubleshooting without GitHub CLI access:

```bash
python3 scripts/validate_eig_pr_merge_readiness.py --skip-github
```

Use `--skip-github` only to debug local docs and source hygiene. The real Phase 310 proof requires GitHub PR state.
