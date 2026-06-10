# Skill/Tool Coverage Gap Examples

## Refresh Source Inputs

```bash
python3 scripts/validate_priority0_gap_taxonomy.py \
  --output-path runtime-state/priority0-gap-taxonomy/phase129-priority0-gap-taxonomy-report.json

python3 scripts/validate_prompt_skill_coverage.py \
  --output-path runtime-state/prompt-skill-coverage/phase129-prompt-skill-coverage-report.json

python3 scripts/validate_capability_gap_backlog.py \
  --output-path runtime-state/capability-gap-backlog/phase129-capability-gap-backlog-report.json
```

## Run The Gate

```bash
python3 scripts/validate_skill_tool_coverage_gap.py \
  --require-artifacts \
  --priority0-gap-taxonomy-path runtime-state/priority0-gap-taxonomy/phase129-priority0-gap-taxonomy-report.json \
  --prompt-tightening-report-path runtime-state/prompt-tightening-recommendations/phase128/phase128-prompt-tightening-recommendations-report.json \
  --output-path runtime-state/skill-tool-coverage-gap/phase129/phase129-skill-tool-coverage-gap-report.json
```

Expected output:

```text
SKILL TOOL COVERAGE GAP PASS
```

## Review The Summary

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/skill-tool-coverage-gap/phase129/phase129-skill-tool-coverage-gap-report.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
PY
```

Expected current summary:

```json
{
  "error_count": 0,
  "gap_candidate_count": 0,
  "implemented_coverage_entry_count": 38,
  "new_capability_required": false,
  "next_action": "none",
  "prompt_tightening_candidate_count": 1,
  "skill_tool_finding_count": 0
}
```

## When A Gap Appears

A real skill/tool gap candidate must include:

- capability type
- capability ID
- proposal summary
- eval gate
- validation tier
- approval boundary

The gate records the candidate. It does not install or implement it.
