# EIG Baseline Candidate Intake Examples

Run the Phase 307 candidate intake gate:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_eig_baseline_candidate_intake.py \
  --output-path runtime-state/eig-baseline-candidate-intake/phase307-validation.json
```

Expected marker:

```text
EIG BASELINE CANDIDATE INTAKE PASS
```

Inspect the candidate summary:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/eig-baseline-candidate-intake/phase307-validation.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
PY
```

Expected fields:

```text
candidate_count=2
total_source_case_count=7
stable_corpus_entry_count=5
stable_corpus_mutated=false
candidate_pending_live_replay_count=2
phase308_ready=true
```

This phase intentionally stops before live replay or stable corpus promotion. Use the report to prepare Phase 308 live gateway and AnythingLLM replay.
