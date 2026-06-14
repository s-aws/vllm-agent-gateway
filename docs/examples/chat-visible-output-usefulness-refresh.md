# Chat-Visible Output Usefulness Refresh Examples

Bridge the AnythingLLM API key from Windows into WSL without printing it:

```powershell
$env:WSLENV = "ANYTHINGLLM_API_KEY/u"
```

Run the live parity suite:

```bash
python3 scripts/validate_output_format_parity_live.py \
  --output-path runtime-state/phase202/phase202-output-format-parity-live.json \
  --timeout-seconds 900
```

Run the usefulness contract:

```bash
python3 scripts/validate_anythingllm_answer_usefulness.py \
  --require-artifacts \
  --output-path runtime-state/phase202/phase202-answer-usefulness-report.json
```

Close Phase 202:

```bash
python3 scripts/validate_chat_visible_output_usefulness_refresh.py
```

Inspect the closeout summary:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase202/phase202-chat-visible-output-usefulness-refresh-report.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
PY
```

Expected passing shape:

```json
{
  "answer_usefulness_checked_case_count": 40,
  "answer_usefulness_error_count": 0,
  "live_case_count": 8,
  "m2_ready": true,
  "phase203_ready": true,
  "surface_pass_counts": {
    "anythingllm": 8,
    "gateway": 8
  },
  "validation_error_count": 0
}
```
