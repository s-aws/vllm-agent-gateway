# Fresh Local-Model Drift Examples

## Run The Live Gate

From Bash/WSL:

```bash
python3 scripts/validate_fresh_local_model_drift.py \
  --output-path runtime-state/fresh-local-model-drift/phase127/fresh-local-model-drift-report.json \
  --timeout-seconds 300 \
  --command-timeout-seconds 1800
```

Expected pass marker:

```text
PHASE127 FRESH LOCAL MODEL DRIFT PASS
```

## Review The Summary

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/fresh-local-model-drift/phase127/fresh-local-model-drift-report.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
PY
```

Expected stable summary shape:

```json
{
  "critical_finding_count": 0,
  "drift_status": "no_drift_detected",
  "error_count": 0,
  "failed_family_count": 0,
  "family_count": 4,
  "gap_categories": {},
  "high_finding_count": 0,
  "passed_response_count": 16,
  "response_count": 16,
  "selected_case_count": 8
}
```

## Validate Catalog Only

```bash
python3 - <<'PY'
from pathlib import Path
from vllm_agent_gateway.acceptance.fresh_local_model_drift import (
    read_json_object,
    validate_fresh_local_model_drift_catalog,
)

root = Path(".").resolve()
catalog = read_json_object(root / "runtime/fresh_local_model_drift_cases.json")
corpus = read_json_object(root / "runtime/baseline_corpus.json")
errors = validate_fresh_local_model_drift_catalog(
    catalog,
    config_root=root,
    baseline_corpus=corpus,
    require_baseline_artifacts=False,
)
print(errors)
PY
```

Expected output:

```text
[]
```

## Common Failure Classes

- `responses must exactly include gateway and anythingllm`: one live route was skipped or failed.
- `case_ids must cover exactly both frozen Coinbase target roots`: the drift subset no longer covers both protected fixtures.
- `fresh_*_sha256 is stale or missing`: the report points at an old, missing, or changed artifact.
- `minimum_route_score regressed below prior accepted result`: the current model/harness is worse than accepted baseline proof.
- `runtime_changed_files must be empty`: the read-only eval changed governed runtime metadata.
