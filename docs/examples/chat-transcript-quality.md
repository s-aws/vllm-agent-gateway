# Chat Transcript Quality Examples

Validate the current founder smoke transcript artifact:

```bash
python3 scripts/validate_chat_transcript_quality.py \
  --require-artifacts \
  --output-path runtime-state/chat-transcript-quality/phase138/phase138-chat-transcript-quality-report.json
```

Inspect the summary:

```bash
python3 -c 'import json; from pathlib import Path; report=json.loads(Path("runtime-state/chat-transcript-quality/phase138/phase138-chat-transcript-quality-report.json").read_text()); print(json.dumps(report["summary"], indent=2, sort_keys=True))'
```

Review blockers:

```bash
python3 -c 'import json; from pathlib import Path; report=json.loads(Path("runtime-state/chat-transcript-quality/phase138/phase138-chat-transcript-quality-report.json").read_text()); print(json.dumps([case for case in report["cases"] if case["quality_status"] == "blocker"], indent=2, sort_keys=True))'
```
