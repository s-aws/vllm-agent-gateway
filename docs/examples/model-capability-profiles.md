# Model Capability Profile Examples

Generate profiles from existing model-portability reports.

## Live Current Candidate

```bash
python scripts/generate_model_capability_profile.py \
  --portability-report-path runtime-state/model-portability/phase72-live-current.json \
  --output-path runtime-state/model-capability-profiles/phase78-live-current-profile.json \
  --markdown-output-path runtime-state/model-capability-profiles/phase78-live-current-profile.md
```

Expected markers:

```text
MODEL CAPABILITY PROFILE REPORT ...
MODEL CAPABILITY PROFILE MARKDOWN ...
MODEL CAPABILITY PROFILE SUMMARY ...
MODEL CAPABILITY PROFILE GENERATED
```

## Offline Baseline

```bash
python scripts/generate_model_capability_profile.py \
  --portability-report-path runtime-state/model-portability/phase72-offline-baseline.json \
  --output-path runtime-state/model-capability-profiles/phase78-offline-baseline-profile.json \
  --markdown-output-path runtime-state/model-capability-profiles/phase78-offline-baseline-profile.md
```

## Review The JSON

Check the status and task policy:

```bash
python - <<'PY'
import json
from pathlib import Path

profile = json.loads(Path("runtime-state/model-capability-profiles/phase78-live-current-profile.json").read_text())
print(profile["status"])
print(profile["capabilities"])
print(profile["task_policy"])
PY
```

## Review The Markdown

Open:

```text
runtime-state/model-capability-profiles/phase78-live-current-profile.md
```

The table should show:

- `route_stability=proven`
- `output_contract_reliability=proven`
- `semantic_answer_quality=proven`
- `latency=unknown`
- `timeout_behavior=proven`
- `safe_apply_readiness=partially_proven`
- `automatic_model_selection=not_approved`
- `real_apply=not_approved`

## Interpret Warnings

`warning` is expected for Phase 78 profiles when the source model passes functional acceptance but does not include timing metrics.

Do not treat a warning profile as approval for automatic model routing. Phase 78 is advisory only.
