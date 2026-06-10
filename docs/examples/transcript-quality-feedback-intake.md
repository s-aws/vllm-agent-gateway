# Transcript Quality Feedback Intake Examples

Run from Bash/WSL.

## Build The Phase 158 Report

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_transcript_quality_feedback_intake.py \
  --output-path runtime-state/transcript-quality-feedback-intake/phase158/phase158-transcript-quality-feedback-intake-report.json \
  --markdown-output-path runtime-state/transcript-quality-feedback-intake/phase158/phase158-transcript-quality-feedback-intake-report.md
```

Expected marker:

```text
PHASE158 TRANSCRIPT QUALITY FEEDBACK INTAKE PASS
```

## Add Optional Founder Notes

Create a local-only notes file under `runtime-state/`:

```json
{
  "kind": "transcript_quality_founder_notes",
  "phase": 158,
  "notes": [
    {
      "note_id": "FN-001",
      "case_id": "P01",
      "category": "model_capability",
      "severity": "medium",
      "text": "The answer did not include the confidence statement I expected in chat."
    }
  ]
}
```

Then run:

```bash
python3 scripts/validate_transcript_quality_feedback_intake.py \
  --founder-notes-path runtime-state/founder-field-round1/phase157/founder-notes.json
```

## Inspect Accepted Findings

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/transcript-quality-feedback-intake/phase158/phase158-transcript-quality-feedback-intake-report.json").read_text())
print(report["status"], report["phase159_required"])
for finding in report["accepted_findings"]:
    print(
        finding["finding_id"],
        finding["case_id"],
        finding["category"],
        finding["decision"],
        finding["phase159_eligible"],
    )
PY
```

## Interpret The Current Field Round

The current Phase 157 field round produces monitoring-only prompt-risk findings:

```text
accepted_finding_count=14
category_counts.prompt_issue=14
phase159_eligible_count=0
phase159_required=false
```

That means Phase 159 has no required repairs from Phase 157 unless new accepted founder notes or later validation creates repair-eligible findings.
