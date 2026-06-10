# Stable Release Blocker Closure Examples

## Run Phase 131

```bash
python3 scripts/validate_stable_release_blocker_closure.py \
  --require-artifacts \
  --output-path runtime-state/stable-release-blocker-closure/phase131/phase131-stable-release-blocker-closure-report.json
```

Expected output:

```text
STABLE RELEASE BLOCKER CLOSURE {"founder_feedback_blocker_count": 3, "founder_feedback_closed_count": 3, "prompt_tightening_blocker_count": 1, "prompt_tightening_closed_count": 1, "unresolved_blocker_count": 0}
STABLE RELEASE BLOCKER CLOSURE PASS
```

## Inspect Closures

```bash
python3 -c 'import json; from pathlib import Path; report=json.loads(Path("runtime-state/stable-release-blocker-closure/phase131/phase131-stable-release-blocker-closure-report.json").read_text()); print(json.dumps(report["summary"], indent=2, sort_keys=True))'
```

## Rerun Release Gate

```bash
python3 scripts/validate_stable_chat_quality_release.py \
  --require-artifacts \
  --output-path runtime-state/stable-chat-quality-release/phase130/phase130-stable-chat-quality-release-report.json
```

Expected output:

```text
STABLE CHAT QUALITY RELEASE PASS
```

The release report should include `readiness=ready_for_founder_testing`, `passed_gate_count=11`, and `blocker_count=0`.
