# Prompt Tightening Recommendations

Phase 128 adds a Priority 0 gate for reviewable prompt-tightening suggestions.

This is not a prompt optimizer and it does not rewrite user prompts or prompt catalogs. It produces deterministic recommendation records only when existing proof shows a prompt may need clarification.

## When It Creates A Candidate

A candidate is allowed only when it is tied to at least one trigger:

- failed route
- unresolved finding
- non-empty gap category
- recommended repair in the comparison artifact
- low-confidence pass at the accepted score floor
- fresh drift watch or failure

The current policy defines low-confidence as a route score at or below `85`.

## Current Phase 128 Result

The initial report creates one pending candidate:

- `PTR-phase117_defect_diagnosis-DD117-009`
- trigger: `low_confidence_pass`
- score: `85` on both gateway and AnythingLLM
- suggestion: require the answer to start with `Diagnosable` or `Not Diagnosable` and justify the decision
- status: `pending_review`

No prompt catalog was changed.

## Primary Command

From Bash/WSL:

```bash
python3 scripts/validate_prompt_tightening_recommendations.py \
  --require-artifacts \
  --output-path runtime-state/prompt-tightening-recommendations/phase128/prompt-tightening-recommendations-report.json
```

Expected pass marker:

```text
PROMPT TIGHTENING RECOMMENDATIONS PASS
```

## Decision Rules

Every candidate has one of these statuses:

- `pending_review`
- `accepted`
- `rejected`

Pending candidates must not include rerun proof.

Accepted candidates require:

- reviewer rationale
- approval record
- target rerun proof
- holdout rerun proof
- gateway and AnythingLLM route proof

Rejected candidates require a rationale.

## Safety Rules

The gate rejects candidates that:

- are not traceable to governed baseline and comparison artifacts
- exist only because a blind baseline has a suggestion
- include rewritten prompt text
- claim prompt catalog mutation
- weaken read-only, approval, mutation, fixture, or evidence boundaries
- claim accepted repair without approval and rerun proof
