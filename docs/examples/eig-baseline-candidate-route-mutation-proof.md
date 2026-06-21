# EIG Baseline Candidate Route And Mutation Proof Examples

Run the focused regression:

```bash
cd /mnt/c/agentic_agents
python3 -m pytest tests/regression/test_eig_baseline_candidate_route_mutation_proof.py -q
```

Validate the repaired live replay:

```bash
python3 scripts/validate_eig_baseline_candidate_route_mutation_proof.py \
  --live-replay-report-path runtime-state/eig-baseline-candidate-live-replay/phase314-after-pii-repair-live.json \
  --output-path runtime-state/eig-baseline-candidate-route-mutation-proof/phase315-validation.json
```

Expected marker:

```text
EIG BASELINE CANDIDATE ROUTE MUTATION PROOF PASS
```

Inspect the summary:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/eig-baseline-candidate-route-mutation-proof/phase315-validation.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
PY
```

Expected fields:

```text
connector_result_count=6
privacy_result_count=8
route_proof_recorded=true
no_mutation_proof_recorded=true
stable_corpus_mutated=false
stable_corpus_promotion_allowed=false
remaining_missing_evidence=["founder_approval","holdout"]
phase316_ready=true
```

This closes route and no-mutation evidence only. Stable baseline promotion remains blocked on holdout proof and founder approval.
