# Stable Chat Quality Release Examples

## Run The Release Gate

```bash
python3 scripts/validate_stable_chat_quality_release.py \
  --require-artifacts \
  --output-path runtime-state/stable-chat-quality-release/phase130/phase130-stable-chat-quality-release-report.json
```

Expected current result:

```text
STABLE CHAT QUALITY RELEASE {"advisory_count": 0, "blocked_gate_count": 0, "blocker_count": 0, "gate_count": 11, "next_action": "continue founder testing", "passed_gate_count": 11, "readiness": "ready_for_founder_testing"}
STABLE CHAT QUALITY RELEASE PASS
```

## Inspect Blockers

```bash
python3 -c 'import json; from pathlib import Path; report=json.loads(Path("runtime-state/stable-chat-quality-release/phase130/phase130-stable-chat-quality-release-report.json").read_text()); print(json.dumps(report["errors"], indent=2))'
```

Expected current blockers:

```json
[]
```

## Inspect Gate Results

```bash
python3 -c 'import json; from pathlib import Path; report=json.loads(Path("runtime-state/stable-chat-quality-release/phase130/phase130-stable-chat-quality-release-report.json").read_text()); print(json.dumps(report["gate_results"], indent=2, sort_keys=True))'
```

Each gate result includes:

- gate ID
- artifact path
- artifact SHA-256
- pass or blocked status
- blockers
- summary

## Ready State

The gate is ready only when the report contains:

```json
{
  "readiness": "ready_for_founder_testing",
  "status": "passed"
}
```

Do not treat a top-level upstream `passed` report as enough if this release gate still reports blockers.
