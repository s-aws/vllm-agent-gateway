# Skill/Tool Gap Proposal Intake

Phase 143 governs when a Priority 0 chat-quality miss can become a proposed deterministic skill or tool.

This feature does not create, register, or implement skills/tools. It validates proposal intake only. Implementation requires a later approved roadmap phase.

## Intake Rule

A proposal is allowed only when the source Phase 129 skill/tool coverage gap report contains a real `skill_tool_selection` gap candidate. Prompt-tightening, formatter, routing, model-quality, or documentation misses must stay in their existing repair lanes.

Every proposal must include:

- source gap candidate ID
- capability type and ID
- concrete scope
- eval gate
- validation tier
- approval boundary
- implementation status of `not_started`
- `auto_register=false`
- `source_mutation_required=false`
- proof that prompt or formatter repair is insufficient

## Current State

The current Phase 129 source report has no active skill/tool gap candidates, so Phase 143 passes with zero proposals.

## Run

```bash
python3 scripts/validate_skill_tool_gap_proposal_intake.py \
  --require-artifacts \
  --output-path runtime-state/skill-tool-gap-proposal-intake/phase143/phase143-skill-tool-gap-proposal-intake-report.json
```

Expected current pass shape:

```json
{
  "status": "passed",
  "summary": {
    "source_gap_candidate_count": 0,
    "proposal_count": 0,
    "error_count": 0
  }
}
```
