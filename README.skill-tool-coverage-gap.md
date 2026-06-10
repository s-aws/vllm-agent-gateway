# Skill/Tool Coverage Gap Gate

Phase 129 decides whether current Priority 0 chat-quality evidence requires a missing deterministic skill or tool.

This gate does not add skills or tools. It classifies evidence and fails closed if a real `skill_tool_selection` miss does not include a proposed capability, eval gate, validation tier, and approval boundary.

## Inputs

- Priority 0 gap taxonomy report
- Phase 128 prompt-tightening recommendation report
- Phase 93 natural-language capability gap backlog
- prompt-to-skill coverage registry
- Phase 129 policy

## Current Result

The current local-model evidence has:

- `skill_tool_finding_count=0`
- `gap_candidate_count=0`
- `new_capability_required=false`
- `prompt_tightening_candidate_count=1`

The one open prompt-tightening candidate from Phase 128 is classified as `not_skill_tool_gap`.

## Primary Command

From Bash/WSL:

```bash
python3 scripts/validate_skill_tool_coverage_gap.py \
  --require-artifacts \
  --priority0-gap-taxonomy-path runtime-state/priority0-gap-taxonomy/phase129-priority0-gap-taxonomy-report.json \
  --prompt-tightening-report-path runtime-state/prompt-tightening-recommendations/phase128/phase128-prompt-tightening-recommendations-report.json \
  --output-path runtime-state/skill-tool-coverage-gap/phase129/skill-tool-coverage-gap-report.json
```

Expected pass marker:

```text
SKILL TOOL COVERAGE GAP PASS
```

## Failure Rules

The gate rejects:

- failed Priority 0 taxonomy input
- failed prompt-tightening input
- `skill_tool_selection` findings without a gap candidate
- candidates missing `capability_type`, `capability_id`, `proposal_summary`, `eval_gate`, `validation_tier`, or `approval_boundary`
- ungoverned validation tiers or approval boundaries
- prompt-tightening candidates reclassified as skill/tool gaps

If the gate finds a real skill/tool gap, the next step is roadmap approval for that capability. Do not add the skill or tool in this gate.
