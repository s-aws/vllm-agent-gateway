# Prompt Corpus Governance V2

Phase 179 governs prompt corpus roles without rewriting the prompt text catalog.

Use this to prevent overfitting when a repair succeeds on one tuned prompt. The policy makes targets, holdouts, regression cases, promotion candidates, and retired cases explicit, then validates that promotion cannot happen from target-only evidence.

## What It Proves

- every prompt catalog case has a corpus role
- target repair prompts have explicit independent holdouts
- holdouts are validated through the Phase 178 blind-baseline delta report when available
- promotion candidates remain blocked without founder approval
- stable corpus promotion still requires a separate phase
- retired prompts cannot stay active in target, holdout, regression, or promotion roles

## Inputs

- Policy: `runtime/prompt_corpus_governance_v2.json`
- Prompt catalog: `runtime/prompt_catalogs/founder_field_v1.json`
- Delta report: `runtime-state/phase178/phase178-blind-baseline-delta-report-final.json`

The policy is a governance overlay. It references prompt case IDs from the existing catalog; it does not duplicate prompt text or create a second prompt catalog.

## Run

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_prompt_corpus_governance_v2.py \
  --output-path runtime-state/phase179/phase179-prompt-corpus-governance-v2-report.json \
  --markdown-output-path runtime-state/phase179/phase179-prompt-corpus-governance-v2-report.md
```

Expected marker:

```text
PHASE179 PROMPT CORPUS GOVERNANCE V2 PASS
```

## Output

Default report:

```text
runtime-state/phase179/phase179-prompt-corpus-governance-v2-report.json
```

Default markdown:

```text
runtime-state/phase179/phase179-prompt-corpus-governance-v2-report.md
```

The report includes:

- source catalog and delta report paths and hashes
- role counts
- target-to-holdout links
- promotion candidate group state
- blocked candidate count
- validation errors
- next action

## Failure Meaning

`status=failed` means prompt governance is unsafe or incomplete. Common causes are unassigned prompt cases, missing holdout links, self-holdouts, stale or missing delta proof, approved promotion without founder approval, or a promoted status inside the governance phase.
