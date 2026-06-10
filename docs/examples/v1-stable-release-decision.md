# V1 Stable Release Decision Examples

Run from Bash/WSL.

## Generate The Final Decision

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_v1_stable_release_decision.py \
  --output-path runtime-state/v1-stable-release-decision/phase156/phase156-v1-stable-release-decision-report.json \
  --markdown-output-path runtime-state/v1-stable-release-decision/phase156/phase156-v1-stable-release-decision-report.md
```

Expected markers:

- `V1 STABLE RELEASE DECISION REPORT ...`
- `V1 STABLE RELEASE DECISION SUMMARY ...`
- `V1 STABLE RELEASE DECISION PASS`

## Inspect The Decision

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/v1-stable-release-decision/phase156/phase156-v1-stable-release-decision-report.json").read_text())
print(report["decision"])
print(report["summary"]["release_blocker_count"])
print(report["rollback_path"])
print(report["next_roadmap_batch"])
PY
```

Expected decision:

```text
release_for_founder_testing
```

## Inspect Evidence Links

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/v1-stable-release-decision/phase156/phase156-v1-stable-release-decision-report.json").read_text())
for source_id, ref in sorted(report["source_refs"].items()):
    print(source_id, ref["status"], ref["path"], ref["sha256"])
PY
```

Every required source should have a path and SHA-256 hash.

## Inspect Blockers

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/v1-stable-release-decision/phase156/phase156-v1-stable-release-decision-report.json").read_text())
for blocker in report["release_blockers"]:
    print(blocker["id"], blocker["source"], blocker["message"])
PY
```

No blockers should print for a passing release decision.

## Interpretation

`release_for_founder_testing` means the current V1 harness can be used for local founder testing within the listed scope. It does not release production deployment, broad advanced refactor orchestration, direct protected-fixture mutation, unsupported output formats, or automatic model selection.
