# Prompt Skill Coverage Examples

Validate the prompt-to-skill coverage registry.

## Validate Current Registry

```bash
python scripts/validate_prompt_skill_coverage.py \
  --output-path runtime-state/prompt-skill-coverage/phase79-current.json
```

Expected markers:

```text
PROMPT SKILL COVERAGE REPORT ...
PROMPT SKILL COVERAGE SUMMARY ...
PROMPT SKILL COVERAGE PASS
```

## Inspect Summary

```bash
python - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/prompt-skill-coverage/phase79-current.json").read_text())
print(report["status"])
print(report["summary"])
PY
```

Phase 79 proof should show:

```text
entry_count=34
implemented_count=34
founder_field_rule_count=26
covered_founder_field_rule_count=26
gap_count=2
error_count=0
```

## Review Gaps

Open:

```text
runtime/prompt_skill_coverage.json
```

Review `gap_backlog`.

The advanced refactor prompt should remain:

```text
GAP-ADV-REFACTOR-SINGLE-PATH status=deferred
```

Do not remove that gap unless a later approved roadmap phase reintroduces advanced refactor orchestration.
