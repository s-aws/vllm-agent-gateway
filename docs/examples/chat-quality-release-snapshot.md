# Chat Quality Release Snapshot Examples

## Create Snapshot

```bash
python3 scripts/create_chat_quality_release_snapshot.py \
  --require-artifacts \
  --output-path runtime-state/chat-quality-release-snapshot/phase136/phase136-chat-quality-release-snapshot.json
```

Expected output:

```text
CHAT QUALITY RELEASE SNAPSHOT {"actionable_feedback_count": 0, "artifact_count": 4, "doc_count": 7, "founder_smoke_failed": 0, "missing_artifact_count": 0, "missing_doc_count": 0, "release_readiness": "ready_for_founder_testing"}
CHAT QUALITY RELEASE SNAPSHOT PASS
```

## Inspect Artifact Hashes

```bash
python3 -c 'import json; from pathlib import Path; report=json.loads(Path("runtime-state/chat-quality-release-snapshot/phase136/phase136-chat-quality-release-snapshot.json").read_text()); print(json.dumps(report["artifacts"], indent=2, sort_keys=True))'
```
