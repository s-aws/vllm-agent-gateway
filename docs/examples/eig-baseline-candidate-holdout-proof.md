# EIG Baseline Candidate Holdout Proof Examples

Run the shape-only validator:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_eig_baseline_candidate_holdout_proof.py \
  --no-live \
  --skip-anythingllm \
  --output-path runtime-state/eig-baseline-candidate-holdout-proof/phase316-shape-validation.json
```

Run the live gateway and AnythingLLM holdout proof:

```bash
export ANYTHINGLLM_API_KEY="<redacted>"
python3 scripts/validate_eig_baseline_candidate_holdout_proof.py \
  --output-path runtime-state/eig-baseline-candidate-holdout-proof/phase316-live-validation.json \
  --anythingllm-api-base-url http://192.168.0.208:3001 \
  --timeout-seconds 240
```

Expected marker:

```text
EIG BASELINE CANDIDATE HOLDOUT PROOF PASS
```

Inspect the summary:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/eig-baseline-candidate-holdout-proof/phase316-live-validation.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
PY
```

Expected fields:

```text
holdout_case_count=7
result_count=14
passed_result_count=14
failed_result_count=0
surface_count=2
recorded_evidence=["holdout"]
remaining_missing_evidence=["founder_approval"]
phase317_ready=true
```

This closes holdout evidence only. Stable corpus promotion still requires explicit founder approval.
