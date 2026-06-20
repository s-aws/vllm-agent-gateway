# EIG Baseline Candidate Local Comparison Examples

Run the Phase 313 comparison against the saved post-blind-baseline live replay:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_eig_baseline_candidate_local_comparison.py \
  --live-replay-report-path runtime-state/eig-baseline-candidate-live-replay/phase313-post-blind-baseline-live.json \
  --output-path runtime-state/eig-baseline-candidate-local-comparison/phase313-validation.json
```

Expected command marker:

```text
EIG BASELINE CANDIDATE LOCAL COMPARISON PASS
```

Then inspect the decision:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/eig-baseline-candidate-local-comparison/phase313-validation.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
print(json.dumps(report["failed_records"], indent=2, sort_keys=True))
PY
```

Current expected decision:

```text
comparison_decision=repair_required
response_count=14
passed_response_count=12
failed_response_count=2
hard_failure_count=0
phase314_ready=true
```

The current repair target is the `EIG3-RUNTIME-PII-AUTH` privacy answer on both workflow-router gateway and AnythingLLM. It must explicitly preserve the blind-baseline requirements:

```text
do not hallucinate authorization
fixture EIG3-PII-N2 classified as personal_data
```

Do not promote EIG candidates into `runtime/baseline_corpus.json` until this comparison decision becomes `passed` and the remaining promotion evidence is also present.
