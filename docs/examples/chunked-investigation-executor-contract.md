# Chunked Investigation Executor Contract Examples

Validate the Phase 222 contract:

```bash
python3 scripts/validate_chunked_investigation_executor_contract.py
```

Focused regression:

```bash
python3 -m pytest tests/regression/test_chunked_investigation_executor_contract.py -q
```

Inspect the report:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase222/phase222-chunked-investigation-executor-contract-report.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
for stage in report["stage_contracts"]:
    print(stage["stage_id"])
for artifact in report["artifact_contracts"]:
    print(artifact["artifact_id"], len(artifact["required_fields"]))
PY
```

The contract is ready for implementation when:

- `phase223_ready` is `true`
- `stage_count` is `7`
- `artifact_contract_count` is `6`
- `negative_control_count` is `10`
- `validation_error_count` is `0`
