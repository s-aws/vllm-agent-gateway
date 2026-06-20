# EIG Baseline Candidate Promotion Readiness Examples

Run the Phase 311 promotion-readiness gate against the live PR evidence:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_eig_baseline_candidate_promotion_readiness.py \
  --output-path runtime-state/eig-baseline-candidate-promotion-readiness/phase311-validation.json
```

Expected marker:

```text
EIG BASELINE CANDIDATE PROMOTION READINESS PASS
```

Inspect the summary:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/eig-baseline-candidate-promotion-readiness/phase311-validation.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
PY
```

Expected fields:

```text
candidate_count=2
blocked_candidate_count=2
approved_candidate_count=0
promoted_candidate_count=0
promotion_allowed=false
stable_corpus_mutated=false
stable_corpus_mutation_allowed=false
stable_corpus_update_requires_separate_phase=true
founder_approval_recorded=false
validation_error_count=0
```

For local static troubleshooting without GitHub CLI access:

```bash
python3 scripts/validate_eig_baseline_candidate_promotion_readiness.py --skip-github
```

Use `--skip-github` only for local policy and dependency checks. The real Phase 311 proof requires PR evidence to be checked.

Do not edit `runtime/baseline_corpus.json` from this phase. A later explicit promotion phase must collect the missing evidence, record founder approval, and perform stable-corpus mutation separately.
