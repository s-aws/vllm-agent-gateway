# Remote-Clone Priority 0 Chat-Quality Replay Examples

Run from the release-candidate clone:

```bash
export ANYTHINGLLM_API_KEY="$ANYTHINGLLM_API_KEY"
python3 scripts/validate_remote_clone_priority0_chat_quality_replay.py \
  --output-path runtime-state/remote-clone-priority0-chat-quality-replay/phase239/phase239-remote-clone-priority0-chat-quality-replay-report.json \
  --timeout-seconds 240
```

Expected terminal marker:

```text
REMOTE CLONE PRIORITY0 CHAT QUALITY REPLAY PASS
```

Inspect failed cases:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/remote-clone-priority0-chat-quality-replay/phase239/phase239-remote-clone-priority0-chat-quality-replay-report.json").read_text())
for case in report["cases"]:
    if case["status"] != "passed":
        print(case["case_id"], case["findings"])
PY
```
