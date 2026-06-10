# Contextless Audit Scorecard

Phase 149 consolidates contextless audit and blind-baseline evidence into one deterministic scorecard.

This is an evidence packaging gate. It is not a substitute for blind-baseline-first chat-quality testing, and it does not approve a release by itself.

## What It Reads

Policy:

```text
runtime/contextless_audit_scorecard_policy.json
```

Required source artifacts include:

```text
runtime-state/baseline-corpus/phase120-baseline-corpus-report.json
runtime-state/fresh-local-model-drift/phase127/phase127-fresh-local-model-drift-report.json
runtime-state/founder-field-tests/phase134-founder-smoke.json
runtime-state/chat-transcript-quality/phase138/phase138-chat-transcript-quality-report.json
runtime-state/recursive-blind-testing/phase113-task-decomposition-recursive-report.json
runtime-state/recursive-blind-testing/phase114-requirements-translation-recursive-report.json
runtime-state/recursive-blind-testing/phase115-incremental-implementation-recursive-report.json
runtime-state/external-tester-dry-run/phase147/phase147-external-tester-dry-run.json
runtime-state/failure-to-roadmap/phase148/phase148-failure-to-roadmap-report.json
```

## What It Produces

JSON scorecard:

```text
runtime-state/contextless-audit-scorecard/phase149/phase149-contextless-audit-scorecard-report.json
```

Markdown view generated from the same JSON:

```text
runtime-state/contextless-audit-scorecard/phase149/phase149-contextless-audit-scorecard-report.md
```

The scorecard includes:

- source artifact refs and hashes
- per-source scores
- per-dimension scores
- audit records for prompt, blind baseline, local answer, difference, repair, rerun, and residual risk
- hard blockers that override aggregate score
- residual risks
- release readiness signal for founder review

## Run

```bash
python3 scripts/validate_contextless_audit_scorecard.py \
  --require-artifacts \
  --output-path runtime-state/contextless-audit-scorecard/phase149/phase149-contextless-audit-scorecard-report.json \
  --markdown-output-path runtime-state/contextless-audit-scorecard/phase149/phase149-contextless-audit-scorecard-report.md
```

Expected current marker:

```text
CONTEXTLESS AUDIT SCORECARD PASS
```

Expected current summary:

```json
{
  "aggregate_score": 94,
  "hard_blocker_count": 0,
  "high_or_critical_residual_risk_count": 0,
  "release_readiness_signal": "candidate_ready_for_founder_review"
}
```

## Hard Blockers

The scorecard fails closed when a required artifact is missing, malformed, failed, stale, or mismatched.

The following cannot be averaged away:

- blind evaluator release authority
- context leakage into a contextless audit
- missing blind-baseline-before-local evidence
- missing gateway or AnythingLLM evidence
- protected fixture mutation
- missing repair/rerun trace
- unresolved critical or high risk
- source or aggregate score below floor

Examples: [docs/examples/contextless-audit-scorecard.md](docs/examples/contextless-audit-scorecard.md).
