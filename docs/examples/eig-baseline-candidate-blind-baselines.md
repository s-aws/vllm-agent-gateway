# EIG Baseline Candidate Blind Baselines Examples

Run the Phase 312 blind-baseline evidence gate:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_eig_baseline_candidate_blind_baselines.py \
  --output-path runtime-state/eig-baseline-candidate-blind-baselines/phase312-validation.json
```

Expected marker:

```text
EIG BASELINE CANDIDATE BLIND BASELINES PASS
```

Inspect the summary:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/eig-baseline-candidate-blind-baselines/phase312-validation.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
PY
```

Expected fields:

```text
case_count=7
expected_case_count=7
contextless_agent_first=true
local_model_output_seen=false
recorded_evidence=["blind_baseline"]
promotion_allowed=false
stable_corpus_mutation_allowed=false
validation_error_count=0
phase313_ready=true
```

The blind-baseline artifact is:

```text
runtime/eig_baseline_candidate_blind_baselines.json
```

Do not treat this as promotion approval. It only closes the `blind_baseline` evidence item for later EIG baseline-candidate promotion review.
