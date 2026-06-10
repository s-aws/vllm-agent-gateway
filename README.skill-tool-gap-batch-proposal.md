# Skill/Tool Gap Batch Proposal

Phase 161 decides whether the latest founder field-test chain proves that a new deterministic skill or tool batch is justified.

This is a proposal-only gate. It does not create skills, register tools, mutate source fixtures, or authorize implementation.

## When To Use It

Run this after:

- Phase 157 founder field testing
- Phase 158 transcript quality feedback intake
- Phase 159 Priority 0 repair-loop closure
- Phase 160 stable release refresh

The gate answers one question:

```text
Does the current evidence prove a missing deterministic skill/tool capability?
```

## Outputs

JSON:

```text
runtime-state/skill-tool-gap-batch-proposal/phase161/phase161-skill-tool-gap-batch-proposal-report.json
```

Markdown:

```text
runtime-state/skill-tool-gap-batch-proposal/phase161/phase161-skill-tool-gap-batch-proposal-report.md
```

The report includes:

- source report hashes for Phases 157-160
- the release readiness and decision from Phase 160
- prompt-only or non-batch findings
- proposed skill/tool candidates, if any are justified
- validation errors
- `implementation_authorized=false`

## Decisions

`no_new_batch_justified` means the evidence does not prove a missing deterministic skill/tool capability. Prompt-only, formatter, documentation, model-quality, and unsupported-scope issues stay out of skill implementation.

`propose_batch_for_founder_approval` means one or more Phase 158 findings prove a missing deterministic skill/tool capability. Candidates include eval gates, validation tiers, safety boundaries, and founder approval requirements.

`blocked` means the Phase 157-160 evidence chain is not clean enough to make a proposal decision.

## Safety Boundaries

Every proposed candidate must remain:

- proposal-only
- founder-approved before implementation
- no source mutation
- no automatic registration
- target-plus-holdout evaluated
- validated through AnythingLLM chat quality

## Run

Run from Bash/WSL:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_skill_tool_gap_batch_proposal.py \
  --output-path runtime-state/skill-tool-gap-batch-proposal/phase161/phase161-skill-tool-gap-batch-proposal-report.json \
  --markdown-output-path runtime-state/skill-tool-gap-batch-proposal/phase161/phase161-skill-tool-gap-batch-proposal-report.md
```

Expected current marker:

```text
PHASE161 SKILL TOOL GAP BATCH PROPOSAL PASS
```

Examples: [docs/examples/skill-tool-gap-batch-proposal.md](docs/examples/skill-tool-gap-batch-proposal.md).
