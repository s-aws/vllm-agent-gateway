# Remote-Clone Non-Coinbase Generalization Replay Examples

Run from the release-candidate clone:

```bash
export ANYTHINGLLM_API_KEY="$ANYTHINGLLM_API_KEY"
python3 scripts/validate_remote_clone_non_coinbase_generalization_replay.py \
  --output-path runtime-state/remote-clone-non-coinbase-generalization-replay/phase240/phase240-remote-clone-non-coinbase-generalization-replay-report.json \
  --timeout-seconds 600
```

Inspect failed responses:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/remote-clone-non-coinbase-generalization-replay/phase240/phase240-remote-clone-non-coinbase-generalization-replay-report.json").read_text())
for response in report["responses"]:
    if response["gap_classes"] != ["none"]:
        print(response["surface"], response["case_id"], response["gap_classes"], response["errors"])
PY
```
