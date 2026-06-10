# Founder Field Round 1 Examples

Run from Bash/WSL.

## Run The Live Field Round

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_founder_field_round1.py \
  --run-live \
  --output-path runtime-state/founder-field-round1/phase157/phase157-founder-field-round1-report.json \
  --markdown-output-path runtime-state/founder-field-round1/phase157/phase157-founder-field-round1-report.md \
  --field-report-path runtime-state/founder-field-round1/phase157/phase157-founder-field-run.json \
  --field-markdown-output-path runtime-state/founder-field-round1/phase157/phase157-founder-field-run.md \
  --timeout-seconds 900
```

Expected markers:

- `FOUNDER FIELD PASS`
- `PHASE157 FOUNDER FIELD ROUND REPORT ...`
- `PHASE157 FOUNDER FIELD ROUND SUMMARY ...`
- `PHASE157 FOUNDER FIELD ROUND PASS`

## Run With Explicit API Key Forwarding

Use this from PowerShell when WSL does not inherit `ANYTHINGLLM_API_KEY`:

```powershell
wsl.exe --cd /mnt/c/agentic_agents -- env "ANYTHINGLLM_API_KEY=$env:ANYTHINGLLM_API_KEY" python3 scripts/validate_founder_field_round1.py --run-live
```

## Validate An Existing Field Report

```bash
python3 scripts/validate_founder_field_round1.py \
  --field-report-path runtime-state/founder-field-round1/phase157/phase157-founder-field-run.json \
  --output-path runtime-state/founder-field-round1/phase157/phase157-founder-field-round1-report.json \
  --markdown-output-path runtime-state/founder-field-round1/phase157/phase157-founder-field-round1-report.md
```

## Inspect Case Outcomes

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/founder-field-round1/phase157/phase157-founder-field-round1-report.json").read_text())
print(report["status"], report["quality_status"])
print(report["summary"])
for case in report["case_results"]:
    print(case["case_id"], case["quality_classification"], case["run_id"])
PY
```

## Interpretation

`status=passed` means the field-test evidence is complete and trustworthy. `quality_status=advisory` or `quality_status=failed` means Phase 158 should classify the advisory/blocker cases before any repair work starts.

## Continue The Closeout Chain

```bash
python3 scripts/validate_transcript_quality_feedback_intake.py \
  --output-path runtime-state/transcript-quality-feedback-intake/phase158/phase158-transcript-quality-feedback-intake-report.json \
  --markdown-output-path runtime-state/transcript-quality-feedback-intake/phase158/phase158-transcript-quality-feedback-intake-report.md
python3 scripts/validate_priority0_repair_loop.py \
  --output-path runtime-state/priority0-repair-loop/phase159/phase159-priority0-repair-loop-report.json \
  --markdown-output-path runtime-state/priority0-repair-loop/phase159/phase159-priority0-repair-loop-report.md
python3 scripts/validate_stable_release_refresh.py \
  --run-refresh \
  --execute-reset-start \
  --execute-recovery \
  --output-path runtime-state/stable-release-refresh/phase160/phase160-stable-release-refresh-report.json \
  --markdown-output-path runtime-state/stable-release-refresh/phase160/phase160-stable-release-refresh-report.md
python3 scripts/validate_skill_tool_gap_batch_proposal.py \
  --output-path runtime-state/skill-tool-gap-batch-proposal/phase161/phase161-skill-tool-gap-batch-proposal-report.json \
  --markdown-output-path runtime-state/skill-tool-gap-batch-proposal/phase161/phase161-skill-tool-gap-batch-proposal-report.md
```

Current expected closeout:

```text
PHASE161 SKILL TOOL GAP BATCH PROPOSAL PASS
decision=no_new_batch_justified
```
