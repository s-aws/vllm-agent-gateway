# Transcript Quality Feedback Intake

Phase 158 converts Phase 157 founder field-test evidence into governed feedback findings.

It does not rerun prompts and it does not repair anything. It reads the Phase 157 report, preserves links back to the raw field-test transcript evidence, and decides whether each advisory, blocker, or founder-note item is monitoring-only or eligible for the Phase 159 repair loop.

## What It Reads

Policy:

```text
runtime/transcript_quality_feedback_intake_policy.json
```

Required Phase 157 evidence:

```text
runtime-state/founder-field-round1/phase157/phase157-founder-field-round1-report.json
runtime-state/founder-field-round1/phase157/phase157-founder-field-run.json
runtime-state/founder-field-round1/phase157/phase157-founder-field-run.md
```

Optional founder notes:

```text
runtime-state/founder-field-round1/phase157/founder-notes.json
```

Founder notes must use `kind=transcript_quality_founder_notes`, `phase=158`, a valid Phase 157 `case_id`, a known category, a known severity, and concrete feedback text. Vague or unlinked notes are rejected and are not turned into implementation work.

## What It Produces

JSON:

```text
runtime-state/transcript-quality-feedback-intake/phase158/phase158-transcript-quality-feedback-intake-report.json
```

Markdown:

```text
runtime-state/transcript-quality-feedback-intake/phase158/phase158-transcript-quality-feedback-intake-report.md
```

The report includes:

- accepted findings
- rejected findings
- case ID, target root, selected workflow, and run ID
- raw transcript reference paths and response hashes
- category, severity, decision, owner path, and required rerun gate
- whether Phase 159 repair is required

## Classifications

Phase 157 advisory prompt-risk cases become `prompt_issue` findings with `accepted_for_monitoring`. They do not trigger Phase 159 repair by themselves.

Phase 157 blockers and accepted founder notes in repairable categories can become `accepted_for_phase159`. Those items must go through the Priority 0 repair loop before any stable release refresh.

Repairable categories are governed by policy:

```text
harness_issue
missing_skill_tool
model_capability
```

## Run

Run from Bash/WSL:

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

Examples: [docs/examples/transcript-quality-feedback-intake.md](docs/examples/transcript-quality-feedback-intake.md).
