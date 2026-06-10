# AnythingLLM Session Recovery Examples

Run the live greeting smoke:

```bash
python3 scripts/validate_anythingllm_session_recovery.py \
  --anythingllm-api-base-url http://127.0.0.1:3001 \
  --workspace my-workspace \
  --timeout-seconds 120 \
  --output-path runtime-state/anythingllm-session-recovery/phase140/phase140-anythingllm-session-recovery-report.json
```

Inspect the case statuses:

```bash
python3 -c 'import json; from pathlib import Path; report=json.loads(Path("runtime-state/anythingllm-session-recovery/phase140/phase140-anythingllm-session-recovery-report.json").read_text()); print(json.dumps(report["summary"], indent=2, sort_keys=True))'
```

Review failures:

```bash
python3 -c 'import json; from pathlib import Path; report=json.loads(Path("runtime-state/anythingllm-session-recovery/phase140/phase140-anythingllm-session-recovery-report.json").read_text()); print(json.dumps([case for case in report["cases"] if case["status"] != "passed"], indent=2, sort_keys=True))'
```
