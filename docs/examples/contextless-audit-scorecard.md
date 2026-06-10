# Contextless Audit Scorecard Examples

## Run Current Gate

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_contextless_audit_scorecard.py \
  --require-artifacts \
  --output-path runtime-state/contextless-audit-scorecard/phase149/phase149-contextless-audit-scorecard-report.json \
  --markdown-output-path runtime-state/contextless-audit-scorecard/phase149/phase149-contextless-audit-scorecard-report.md
```

Expected result:

```text
CONTEXTLESS AUDIT SCORECARD PASS
```

## Review JSON

Start with:

```text
summary.release_readiness_signal
summary.aggregate_score
summary.hard_blocker_count
summary.high_or_critical_residual_risk_count
scorecard.dimension_scores[]
scorecard.source_scores[]
scorecard.audit_records[]
scorecard.hard_blockers[]
```

Current expected state:

```text
release_readiness_signal=candidate_ready_for_founder_review
hard_blocker_count=0
high_or_critical_residual_risk_count=0
```

This signal means the evidence package is ready for founder review. It does not mean the scorecard approved a release.

## Review Markdown

Open:

```text
runtime-state/contextless-audit-scorecard/phase149/phase149-contextless-audit-scorecard-report.md
```

The Markdown is generated from the JSON report and is only a compact review surface.

## Failure Review

If the gate fails, inspect:

```text
scorecard.hard_blockers[].code
scorecard.hard_blockers[].source_id
scorecard.hard_blockers[].message
scorecard.dimension_scores[].blocker_codes
errors[]
```

Do not fix failures by editing the scorecard output. Fix the source artifact, rerun the source gate, then rerun this scorecard.
