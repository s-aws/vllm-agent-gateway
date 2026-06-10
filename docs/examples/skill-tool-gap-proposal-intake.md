# Skill/Tool Gap Proposal Intake Examples

Validate the current proposal intake policy:

```bash
python3 scripts/validate_skill_tool_gap_proposal_intake.py \
  --require-artifacts \
  --output-path runtime-state/skill-tool-gap-proposal-intake/phase143/phase143-skill-tool-gap-proposal-intake-report.json
```

Inspect proposal state:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/skill-tool-gap-proposal-intake/phase143/phase143-skill-tool-gap-proposal-intake-report.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
for proposal in report["proposals"]:
    print(proposal["proposal_id"], proposal["capability_id"], proposal["status"])
PY
```

The expected current state is zero source gap candidates and zero proposals. That means the project should continue improving current chat-quality paths instead of adding a new skill or tool.
